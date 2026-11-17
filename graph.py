# graph.py
import os
import re
import time
from typing import TypedDict, List, Dict, Any
from datetime import datetime, timedelta
import pytz
import dateparser
from dotenv import load_dotenv
from openai import OpenAI

from langgraph.graph import StateGraph, START, END
from tools import (
    extract_text_from_docx,
    extract_text_from_pdf,
    chunk_text,
    store_embeddings_in_chromadb,
    rag_search,
    lead_gen,
    generate_with_gpt,
    get_openai_client
)
from calendly_tool import schedule_calendly_meeting

load_dotenv()

IST = pytz.timezone("Asia/Kolkata")

class RAGState(TypedDict, total=False):
    file_path: str
    content: str
    chunks_ingested: int
    docs: List[Dict[str, Any]]
    query: str
    answer: str

class queryState(TypedDict, total=False):
    query: str
    answer: str

class LeadState(TypedDict, total=False):
    name: str
    mob: Any
    query: str
    queries: List[Dict[str, str]]

class SchedulerSlots(TypedDict, total=False):
    """TypedDict for storing scheduling info (multi-turn slot filling)"""
    name: str
    email: str
    start_time: str  # ISO 8601 UTC format
    duration_minutes: int
    location: str


def extract_slots_llm(user_input: str) -> SchedulerSlots:
    """
    Uses GPT-4o to extract name, email, start_time from natural language.
    Returns a SchedulerSlots dict with extracted values or empty if missing.
    """
    client = get_openai_client()
    if not client:
        return SchedulerSlots()

    prompt = f"""
Extract the following information from the user's message.
Return JSON only with keys "name", "email", "start_time". If information is missing, set it to null.

Fields:
- name
- email
- start_time (natural language is fine, e.g., 'tomorrow 4 PM IST')

User message: "{user_input}"
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        import json
        raw_content = response.choices[0].message.content.strip()
        # Clean markdown fences if any
        if raw_content.startswith("```"):
            raw_content = re.sub(r"^```(?:json)?\n?|\n?```$", "", raw_content, flags=re.MULTILINE).strip()
        data = json.loads(raw_content)
        return SchedulerSlots(
            name=data.get("name"),
            email=data.get("email"),
            start_time=data.get("start_time")
        )
    except Exception as e:
        print(f"[DEBUG] LLM slot extraction exception: {e}")
        return SchedulerSlots()


def parse_start_time(text: str):
    text = text.lower().strip()

    # Already ISO (assume UTC)
    if "t" in text and text.endswith("z"):
        return text

    now_ist = datetime.now(IST)

    # Day resolution
    if "tomorrow" in text:
        base_date = now_ist + timedelta(days=1)
    elif "today" in text:
        base_date = now_ist
    else:
        # Try dateparser
        parsed = dateparser.parse(
            text,
            settings={'RELATIVE_BASE': now_ist, 'TIMEZONE': 'Asia/Kolkata', 'RETURN_AS_TIMEZONE_AWARE': True}
        )
        if parsed:
            utc_dt = parsed.astimezone(pytz.utc)
            return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return None

    # Time extraction (supports 2pm, 2:30 pm, 14:30)
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    meridian = match.group(3)

    if meridian == "pm" and hour != 12:
        hour += 12
    if meridian == "am" and hour == 12:
        hour = 0

    ist_dt = base_date.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0
    )

    utc_dt = ist_dt.astimezone(pytz.utc)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def extract_email_regex(text: str):
    match = re.search(
        r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
        text
    )
    return match.group(0) if match else None


def scheduler_node(
    user_message: str,
    scheduler_slots: Dict = None,
    user_name: str = None
) -> Dict:
    """
    Multi-turn scheduling node (Calendly)
    Required slots:
    - name
    - email
    - start_time
    """
    print("In scheduler_node...\n")

    if scheduler_slots is None or not isinstance(scheduler_slots, dict):
        scheduler_slots = {}

    for key in ["name", "email", "start_time"]:
        scheduler_slots.setdefault(key, None)

    # Pre-fill name if already known
    if not scheduler_slots["name"] and user_name:
        scheduler_slots["name"] = user_name

    # Slot extraction (deterministic regex & parser)
    if not scheduler_slots["email"]:
        email = extract_email_regex(user_message)
        if email:
            scheduler_slots["email"] = email

    if not scheduler_slots["start_time"]:
        parsed_time = parse_start_time(user_message)
        if parsed_time:
            scheduler_slots["start_time"] = parsed_time

    if not scheduler_slots["name"]:
        # If user provides just a name (1 to 3 words, no time or email)
        if len(user_message.split()) <= 3 and not extract_email_regex(user_message) and not parse_start_time(user_message):
            scheduler_slots["name"] = user_message.strip()

    print("[LOG] Scheduler slots:", scheduler_slots)

    # Ask for missing slot (ONE AT A TIME)
    if not scheduler_slots["name"]:
        return {
            "response": "May I know your full name for booking the counselling call?",
            "scheduler_slots": scheduler_slots,
            "done": False
        }

    if not scheduler_slots["email"]:
        return {
            "response": f"Thanks {scheduler_slots['name']}! Please share your email address so I can send the calendar invite.",
            "scheduler_slots": scheduler_slots,
            "done": False
        }

    if not scheduler_slots["start_time"]:
        return {
            "response": "What date and time would work best for your counselling call? (e.g. 'Tomorrow at 4 PM')",
            "scheduler_slots": scheduler_slots,
            "done": False
        }

    # All slots collected -> Call Calendly
    print("[LOG] Calling Calendly tool...")
    event_type_uri = os.getenv(
        "CALENDLY_EVENT_TYPE_URI",
        "https://api.calendly.com/event_types/3677b0d0-1e8d-458e-98ea-575bb00c1cb0"
    )

    result = schedule_calendly_meeting(
        event_type_uri=event_type_uri,
        name=scheduler_slots["name"],
        email=scheduler_slots["email"],
        start_time=scheduler_slots["start_time"]
    )

    if result.get("success"):
        response = (
            f"🎉 Your counselling call has been scheduled successfully!\n\n"
            f"📅 Time: {scheduler_slots['start_time']} (UTC)\n"
            f"📧 Confirmation sent to: {scheduler_slots['email']}"
        )
    else:
        response = f"⚠️ Could not complete Calendly booking: {result.get('message', '')}"

    return {
        "response": response,
        "scheduler_slots": scheduler_slots,
        "done": True
    }


def read_document(state: RAGState) -> RAGState:
    file_path = state.get("file_path", "")
    if not os.path.isabs(file_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(base_dir, file_path)

    _, extension = os.path.splitext(file_path)
    extension = extension.lower()

    text = ""
    if extension == '.pdf':
        text = extract_text_from_pdf(file_path)
    elif extension == '.docx':
        text = extract_text_from_docx(file_path)

    state["content"] = text
    return state


def toVector(state: RAGState) -> RAGState:
    text = state.get("content", "")
    chunks = chunk_text(text, chunk_size=1000)
    store_embeddings_in_chromadb(chunks)
    state["chunks_ingested"] = len(chunks)
    return state


def rag_query(state: queryState) -> queryState:
    query = state.get("query", "")
    response = rag_search(query)
    state["answer"] = response
    return state


def check_node(state: RAGState):
    state["query"] = input("Enter your query: ")
    end_statement = ["exit", "quit", "done", "bye"]
    if state["query"].lower() in end_statement:
        return END
    else:
        return rag_query(state)


def lead_gen_node(state: LeadState) -> LeadState:
    queries_text = ""
    if "queries" in state and isinstance(state["queries"], list):
        queries_text = "\n".join(f"{q.get('role', '')}: {q.get('message', '')}" for q in state["queries"])
    else:
        queries_text = str(state.get("query", ""))

    prompt = f"""
You are an advanced lead scoring engine for an admissions assistant.
Analyze the user's queries to determine the quality and seriousness of their interest (conversion likelihood).

Scoring Criteria (0-100):
* Score 90-100 (High Quality/High Intent): Immediate commitment factors (application deadlines, exact fees, required documents, direct request for application link).
* Score 50-89 (Medium Quality/Medium Intent): General course details, eligibility criteria, comparing two programs.
* Score 0-49 (Low Quality/Low Intent): Vague or greeting queries ("hi", "tell me about college").

Strict Output Instruction:
Return ONLY a single integer between 0 and 100. Do not include any text, explanations, markdown, or punctuation.

USER CONVERSATION TO SCORE:
{queries_text}
"""
    lead_score_str = generate_with_gpt(prompt)
    score_match = re.search(r'\b\d{1,3}\b', str(lead_score_str))
    score = int(score_match.group(0)) if score_match else 50
    score = max(0, min(100, score))

    lead_gen(state.get("name", "Unknown"), state.get("mob", ""), score)
    return state


def scheduler_node_wrapper(user_message: str, scheduler_slots: SchedulerSlots = None) -> Dict[str, Any]:
    return scheduler_node(user_message, scheduler_slots)


# Build LangGraph pipelines
RAGAgent = StateGraph(RAGState)
queryAgent = StateGraph(queryState)

RAGAgent.add_node("read_document", read_document)
RAGAgent.add_node("toVector", toVector)
queryAgent.add_node("rag_query", rag_query)
RAGAgent.add_node("check_node", check_node)

RAGAgent.add_edge(START, "read_document")
RAGAgent.add_edge("read_document", "toVector")
RAGAgent.add_edge("toVector", END)

queryAgent.add_edge(START, "rag_query")
queryAgent.add_edge("rag_query", END)

rag_app = RAGAgent.compile()
res = queryAgent.compile()

schedulerAgent = StateGraph(SchedulerSlots)
schedulerAgent.add_node("scheduler_node", scheduler_node_wrapper)
schedulerAgent.add_edge(START, "scheduler_node")
schedulerAgent.add_edge("scheduler_node", END)
scheduler_app = schedulerAgent.compile()
