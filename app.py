import os
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, jsonify, session
from flask_session import Session
from dotenv import load_dotenv

load_dotenv()

from main import admission_enquiry
from graph import lead_gen_node, scheduler_node
from tools import get_openai_client

base_dir = os.path.dirname(os.path.abspath(__file__))
template_dir = os.path.join(base_dir, "templates")

app = Flask(__name__, template_folder=template_dir)
app.secret_key = os.getenv("SECRET_KEY", "super-secret-key-nit-surat-agent")

session_dir = os.path.join(base_dir, "flask_session")
os.makedirs(session_dir, exist_ok=True)
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = session_dir
app.config["SESSION_PERMANENT"] = False
Session(app)

FINAL_KEYWORDS = [
    "thank you", "thanks", "done",
    "no more questions", "that's all", "bye"
]

SCHEDULER_KEYWORDS = [
    "schedule", "appointment", "call", "book", "meeting", "counselling",
    "counseling", "slot", "talk to counsellor", "counsellor call"
]

INACTIVITY_TIMEOUT = 60 * 60  # 1 hour in seconds


def detect_intent(user_message: str) -> str:
    """
    Decides intent:
    - 'instruction' for scheduling requests (Calendly)
    - 'prompt' for general queries (RAG)
    """
    client = get_openai_client()
    if client:
        try:
            prompt = f"""
Decide if the user's message is asking to schedule an appointment/call/counselling session or a general college query.
Respond with only one word: 'instruction' if user wants to schedule an appointment,
or 'prompt' if it's a general question.
User message: "{user_message}"
Answer with only one word.
"""
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            word = response.choices[0].message.content.strip().lower()
            return "instruction" if "instruction" in word else "prompt"
        except Exception as e:
            print(f"[DEBUG] OpenAI intent detection fallback: {e}")

    # Heuristic fallback if LLM is unavailable or unconfigured
    msg_lower = user_message.lower()
    if any(keyword in msg_lower for keyword in SCHEDULER_KEYWORDS):
        return "instruction"
    return "prompt"


@app.route("/")
def AdmissionEnquiry():
    return render_template('admission_agent.html')


@app.route("/admission-message", methods=["POST"])
def admission_message():
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    user_name = data.get("name")
    user_mobile = data.get("mobile")
    now = datetime.now(timezone.utc)

    print(f"\n[LOG] Incoming message: {user_message}")

    # ---------------------------
    # SESSION INITIALIZATION
    # ---------------------------
    if "queries" not in session:
        session["queries"] = []
        session["scheduler_slots"] = {}

    # Reset session if inactive
    last_activity = session.get("last_activity", now.isoformat())
    try:
        last_activity_dt = datetime.fromisoformat(last_activity)
        if last_activity_dt.tzinfo is None:
            last_activity_dt = last_activity_dt.replace(tzinfo=timezone.utc)
    except Exception:
        last_activity_dt = now

    if (now - last_activity_dt).total_seconds() > INACTIVITY_TIMEOUT:
        print("[LOG] Session inactive. Clearing old queries and scheduler slots.")
        session["queries"] = []
        session["scheduler_slots"] = {}
    session["last_activity"] = now.isoformat()

    # Store current user message
    session["queries"].append({"role": "user", "message": user_message})

    # ---------------------------
    # SCHEDULER FLOW (multi-turn)
    # ---------------------------
    if session.get("scheduler_slots"):  # ongoing scheduling
        print("[LOG] Using scheduler block (multi-turn ongoing)")
        bot_reply_data = scheduler_node(user_message, session["scheduler_slots"], user_name=user_name)
        bot_reply = bot_reply_data.get("response", "")
        session["scheduler_slots"] = bot_reply_data.get("scheduler_slots", {})

        if bot_reply_data.get("done", False):
            print("[LOG] Scheduler completed. Resetting scheduler state.")
            session["scheduler_slots"] = {}

    else:
        # ---------------------------
        # INTENT DETECTION
        # ---------------------------
        intent = detect_intent(user_message)
        print(f"[LOG] Intent detected: {intent}")

        if intent == "instruction":
            print("[LOG] Starting scheduler flow")
            bot_reply_data = scheduler_node(
                user_message,
                session.get("scheduler_slots", {}),
                user_name=user_name
            )

            bot_reply = bot_reply_data.get("response", "")
            session["scheduler_slots"] = bot_reply_data.get("scheduler_slots", {})

            if bot_reply_data.get("done", False):
                print("[LOG] Scheduler completed. Resetting scheduler state.")
                session["scheduler_slots"] = {}

        else:
            # ---------------------------
            # RAG FLOW
            # ---------------------------
            print("[LOG] Using RAG block")
            history_text = "\n".join(f"{q['role']}: {q['message']}" for q in session["queries"])
            bot_reply = admission_enquiry(history_text)

    # ---------------------------
    # CLEAN REPLY
    # ---------------------------
    bot_reply = bot_reply or "I'm sorry, I couldn't process your request. Please try again."
    clean_reply = re.sub(r'(\*{1,3}|#{1,6}|~{2}|`{1,3})', '', bot_reply)
    clean_reply = "\n".join(line.strip() for line in clean_reply.splitlines() if line.strip())

    # Store bot reply in session
    session["queries"].append({"role": "bot", "message": clean_reply})

    print(f"[LOG] Bot reply: {clean_reply}")

    # ---------------------------
    # FINAL LEAD GENERATION
    # ---------------------------
    keyword_trigger = any(k in user_message.lower() for k in FINAL_KEYWORDS)
    timeout_trigger = (now - last_activity_dt).total_seconds() > INACTIVITY_TIMEOUT

    if not session.get("lead_generated", False) and (keyword_trigger or timeout_trigger):
        print("[LOG] Triggering lead generation")
        lead_state = {
            "name": user_name,
            "mob": user_mobile,
            "queries": session["queries"]
        }
        lead_res = lead_gen_node(lead_state)
        session["lead_generated"] = True
        print("[LOG] Lead generated:", lead_res)
        session.clear()

    return jsonify({"reply": clean_reply})


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"\n🚀 Starting College Admission Agent on http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
