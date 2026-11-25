# Deployment Guide — FortivexAI Sales Agent

## 1. Local Windows Deployment (MVP)

### Prerequisites
- Windows 10 or 11
- Python 3.11+ (tested on Python 3.13)
- 4 GB+ RAM (8 GB recommended when running Faster-Whisper locally)
- Internet access for initial package install, Edge TTS audio synthesis, and optional Gemini API calls

### Step-by-Step Setup

1. **Create and activate a virtual environment**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

2. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

3. **Configure environment variables**
   ```powershell
   copy .env.example .env
   ```
   - Leave `APP_MODE=demo` and `GEMINI_API_KEY=` blank to run in deterministic Demo Mode.
   - Or obtain a Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey), set `GEMINI_API_KEY=<your-key>`, and set `APP_MODE=production`.

4. **Generate & validate datasets + initialize SQLite CRM**
   ```powershell
   python scripts/generate_dataset.py
   ```

5. **Index knowledge base into local ChromaDB**
   ```powershell
   python scripts/index_knowledge.py
   ```

6. **Run automated tests**
   ```powershell
   pytest tests/ -v
   ```

7. **Start the application**
   ```powershell
   streamlit run app.py
   ```
   Open **http://localhost:8501** in your browser.

---

## 2. Persistence & Restart Verification

- Customer records, leads, conversation turns, appointments, and call summaries persist in `data/dreamhome.db` (SQLite with WAL mode).
- Vector embeddings persist in `chroma_db/`.
- Restarting `streamlit run app.py` automatically preserves all stored CRM records and knowledge index entries.

---

## 3. Troubleshooting

| Issue | Resolution |
|---|---|
| `GEMINI_MODEL` unavailable / 404 | Update `GEMINI_MODEL` in `.env` (e.g., `gemini-2.5-flash` or `gemini-2.0-flash`) or change it on the Settings page |
| Faster-Whisper slow on CPU | Set `WHISPER_MODEL=tiny` in `.env` |
| Edge TTS silent offline | Edge TTS requires internet access; text responses still work offline |
| Knowledge base outdated | Run `python scripts/index_knowledge.py --force` or click **Force Reindex** on the Knowledge Base page |

---

## 4. Production Deployment Considerations

For production deployment beyond a local student demo:
- Containerize backend API (FastAPI) and frontend separately using Docker
- Replace SQLite with managed PostgreSQL and local ChromaDB with a managed vector database
- Terminate TLS (HTTPS) behind a reverse proxy / cloud load balancer
- Add authentication, consent banners, and secret management (see [`docs/security.md`](security.md) and [`docs/scalability.md`](scalability.md))
