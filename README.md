# Lumen RAG Chatbot

Python FastAPI chatbot with a browser frontend, MongoDB persistence, and Groq-powered retrieval-augmented generation.

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
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=qwen/qwen3.8-27b
ADMIN_KEY=choose_a_long_admin_key
```

Start MongoDB, then run:

```powershell
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the user chat. Knowledge-base controls are available only at `http://127.0.0.1:8000/admin`; enter the configured `ADMIN_KEY` when prompted. Upload `Complete_Footwear_Product_Catalogue.docx` there once so its embedded footwear images are indexed and suggested with relevant answers. Without `GROQ_API_KEY`, the app uses lexical retrieval and returns matching context as a local fallback.

API documentation is available at `http://127.0.0.1:8000/docs`.