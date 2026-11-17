# 🎓 Autonomous Agentic RAG Scheduling System

An autonomous, agentic AI system for college admissions, built with **Flask**, **LangGraph**, **ChromaDB**, and **OpenAI GPT-4o**. It answers prospectus-based queries via RAG, schedules counselling calls via Calendly, and captures leads automatically.

---

## ✨ Features

- 🤖 **RAG-powered Q&A** — Answers admission queries grounded in the college prospectus (PDF/DOCX) using persistent ChromaDB vector storage.
- 📅 **Calendly Scheduling** — Books counselling calls via multi-turn slot-filling (Name → Email → Date & Time).
- 🧠 **Intent Detection** — Classifies each message as a general college query (RAG) or an appointment booking request (Calendly).
- 📊 **Lead Generation & Scoring** — Automatically scores user intent (0–100) and saves contact leads to CSV on session completion.
- 💬 **Conversation Memory** — Server-side session tracking across multi-turn interactions.
- ⏱️ **Inactivity Timeout** — Auto-triggers lead capture after inactivity.
- 💻 **VS Code Ready** — Pre-configured launch profiles and environment settings for one-click execution.

---

## 🏗️ Architecture

```
User Message
     │
     ▼
Intent Detection (GPT-4o / Heuristic Fallback)
     │
     ├──► "instruction" ──► Scheduler Node (multi-turn slot fill) ──► Calendly API
     │
     └──► "prompt"      ──► RAG Node (ChromaDB + GPT-4o)          ──► Answer
                                   │
                                   ▼
                         Lead Gen Node (on session end)
                                   │
                                   ▼
                         Knowledge/Leads.csv
```

**Tech Stack:**

| Layer | Technology |
|---|---|
| Web Framework | Flask + Flask-Session |
| LLM & Embeddings | OpenAI GPT-4o / `text-embedding-3-small` |
| Agent Orchestration | LangGraph |
| Vector Database | ChromaDB (Persistent) |
| Scheduling Integration | Calendly REST API |
| Document Extraction | python-docx, PyPDF2 |
| Environment | Python 3.12+ |

---

## 📁 Project Structure

```
Autonomous-Agentic-RAG-Scheduling-System/
├── .vscode/
│   ├── launch.json              # VS Code run & debug configurations
│   └── settings.json            # VS Code Python interpreter settings
├── Knowledge/
│   ├── Prospectus.docx          # College prospectus (RAG knowledge base source)
│   └── Leads.csv                # Auto-generated lead capture database
├── templates/
│   └── admission_agent.html     # Responsive web chat interface
├── app.py                       # Flask application entry point & session manager
├── main.py                      # RAG initialization & admission inquiry service
├── graph.py                     # LangGraph state machines (RAG, Scheduler, Lead Gen)
├── tools.py                     # Document processing, ChromaDB, OpenAI client, Lead CSV
├── calendly_tool.py             # Calendly availability check & booking creation
├── test.py                      # Utility script to test Calendly credentials & event types
├── requirements.txt             # Python project dependencies
├── .env.example                 # Example environment variables template
├── .env                         # Local environment variables (API keys)
├── .gitignore                   # Git ignore file
├── LICENSE                      # MIT License
└── readme.md                    # Project documentation
```

---

## 🚀 Quickstart Guide

### 1. Clone the Repository

```bash
git clone https://github.com/Badshah1508/Autonomous-Agentic-RAG-Scheduling-System.git
cd Autonomous-Agentic-RAG-Scheduling-System
```

### 2. Set Up Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate       # On Linux / macOS
# or
venv\Scripts\activate          # On Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create your `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Open `.env` and configure your API keys:

```env
OPENAI_API_KEY=sk-proj-your-openai-api-key-here
CALENDLY_TOKEN=your-calendly-personal-access-token-here
CALENDLY_EVENT_TYPE_URI=https://api.calendly.com/event_types/your-event-type-id
SECRET_KEY=super-secret-key-nit-surat-agent
PORT=5000
```

> 💡 **Where to get keys:**
> - **OpenAI API Key**: [OpenAI Platform](https://platform.openai.com/api-keys)
> - **Calendly Token**: [Calendly Integrations / API](https://calendly.com/integrations/api_webhooks)

---

## 💻 Running in Visual Studio Code (VS Code)

This repository includes pre-configured `.vscode` configurations for seamless execution:

1. **Open the Project Folder in VS Code:**
   ```bash
   code .
   ```
2. **Select the Python Interpreter:**
   - Press `Ctrl + Shift + P` (or `Cmd + Shift + P` on Mac).
   - Type `Python: Select Interpreter`.
   - Choose `./venv/bin/python` (the project's virtual environment).
3. **Run the App:**
   - Go to the **Run & Debug** panel on the left sidebar (`Ctrl + Shift + D`).
   - Select **"Run Admission Agent (Flask Web App)"** from the dropdown.
   - Click the green **Play** button (or press `F5`).
4. **Open in Browser:**
   - Navigate to `http://127.0.0.1:5000`.

### Alternative Terminal Run

You can also run directly from the VS Code integrated terminal:

```bash
python app.py
```

---

## 🗺️ API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the web-based admission chatbot UI |
| `POST` | `/admission-message` | Processes user messages, handles slot-filling, RAG retrieval, and lead logging |

**Request Body (`/admission-message`):**

```json
{
  "message": "What are the B.Tech programs and fees for NIT Surat?",
  "name": "Badshah",
  "mobile": "9876543210"
}
```

---

## 📅 Scheduling Flow

When a user requests a call or counselling session:

1. **Name** — Collected from initial modal or requested during chat.
2. **Email** — Extracted via regex from user message.
3. **Date & Time** — Parsed from natural language expressions (e.g. `"tomorrow 3 PM IST"`, `"today at 5 PM"`).
4. **Booking** — Verified against Calendly availability and confirmed via Calendly API.

---

## 📊 Lead Scoring & Storage

Leads are scored from 0–100 by GPT-4o based on commitment level and saved to `Knowledge/Leads.csv`:

| Score Range | Intent Level | Example Inquiries |
|---|---|---|
| **90–100** | High (Ready to apply) | Specific application deadlines, exact fee breakdown, document requirements |
| **50–89** | Medium (Evaluating) | General course curriculum, hostel facilities, program comparisons |
| **0–49** | Low (Casual browsing) | Greetings, vague questions |

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 👤 Author

**Badshah**
- **GitHub**: [@Badshah1508](https://github.com/Badshah1508)
- **Repository**: [Autonomous-Agentic-RAG-Scheduling-System](https://github.com/Badshah1508/Autonomous-Agentic-RAG-Scheduling-System.git)
- **Email**: badshahkumar1508@gmail.com

---

> Built with ❤️ for autonomous AI-driven academic admissions and scheduling.
