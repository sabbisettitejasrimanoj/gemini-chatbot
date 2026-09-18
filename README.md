# Lumen RAG Chatbot

Python FastAPI chatbot with a browser frontend, MongoDB persistence, and Gemini-powered retrieval-augmented generation.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=lumen_chatbot
GEMINI_API_KEY=your_gemini_key_here
```

Start MongoDB, then run:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`. Use **Add documents** to store knowledge, then ask questions about it. Without `GEMINI_API_KEY`, the app uses lexical retrieval and returns matching context as a local fallback.

API documentation is available at `http://127.0.0.1:8000/docs`.