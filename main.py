"""
PICP Agent — Progyny Infinite Command Project
Autonomous context ingestion and brain update agent.
"""

import os
import json
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import uvicorn

# --- Google Drive / Docs ---
from google.oauth2 import service_account
from googleapiclient.discovery import build as google_build

app = FastAPI(title="PICP Agent", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

DATA_DIR = "/app/data"
NOTES_FILE = f"{DATA_DIR}/notes.md"
LIBRARY_FILE = f"{DATA_DIR}/library.md"
LOG_FILE = f"{DATA_DIR}/agent.log"

os.makedirs(DATA_DIR, exist_ok=True)

# --- Google auth setup ---
# documents scope is FULL (read + write) so the agent can edit docs via batchUpdate.
# drive stays readonly — we only list files, never change Drive structure.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents",
]


def get_google_creds():
    """Load the service account key from the Railway env variable."""
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        raise HTTPException(status_code=500, detail="GOOGLE_SERVICE_ACCOUNT_JSON not set on picp-agent")
    try:
        info = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Service account JSON is malformed: {e}")
    return service_account.Credentials.from_service_account_info(info, scopes=GOOGLE_SCOPES)


def drive_service():
    return google_build("drive", "v3", credentials=get_google_creds(), cache_discovery=False)


def docs_service():
    return google_build("docs", "v1", credentials=get_google_creds(), cache_discovery=False)


def log(message: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    print(entry)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(entry)
    except Exception:
        pass


def read_file(path: str) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def write_file(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)


class ContextDocument(BaseModel):
    content: str
    source: str = "manual"


class QueryRequest(BaseModel):
    question: str


class AppendRequest(BaseModel):
    text: str


@app.get("/")
def health():
    return {
        "status": "PICP Agent online",
        "version": "1.2.0",
        "brain": "Progyny Infinite Command Project",
        "operator": "Randy Wain Nutt"
    }


@app.get("/status")
def status():
    notes = read_file(NOTES_FILE)
    library = read_file(LIBRARY_FILE)
    log_content = read_file(LOG_FILE)
    last_lines = "\n".join(log_content.strip().split("\n")[-10:]) if log_content else "No logs yet"
    return {
        "notes_size": len(notes),
        "library_size": len(library),
        "notes_exists": bool(notes),
        "library_exists": bool(library),
        "recent_log": last_lines
    }


# ---------------- GOOGLE DRIVE ENDPOINTS ----------------

@app.get("/drive/test")
def drive_test():
    """Proves the Google connection works end to end. Lists docs the robot can see."""
    try:
        service = drive_service()
        results = service.files().list(
            q="mimeType='application/vnd.google-apps.document' and trashed=false",
            pageSize=25,
            fields="files(id, name)",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()
        files = results.get("files", [])
        log(f"/drive/test OK — {len(files)} docs visible")
        return {
            "connection": "SUCCESS",
            "docs_visible": len(files),
            "documents": files
        }
    except HTTPException:
        raise
    except Exception as e:
        log(f"/drive/test FAILED — {e}")
        return {"connection": "FAILED", "error": str(e)}


@app.get("/drive/read/{doc_id}")
def drive_read(doc_id: str):
    """Opens one Google Doc by ID and returns its plain text."""
    try:
        service = docs_service()
        doc = service.documents().get(documentId=doc_id).execute()
        title = doc.get("title", "Untitled")
        text = ""
        for element in doc.get("body", {}).get("content", []):
            paragraph = element.get("paragraph")
            if not paragraph:
                continue
            for run in paragraph.get("elements", []):
                text_run = run.get("textRun")
                if text_run:
                    text += text_run.get("content", "")
        log(f"/drive/read OK — '{title}' ({len(text)} chars)")
        return {"title": title, "doc_id": doc_id, "text": text}
    except HTTPException:
        raise
    except Exception as e:
        log(f"/drive/read FAILED — {e}")
        return {"error": str(e)}


@app.post("/drive/append/{doc_id}")
def drive_append(doc_id: str, req: AppendRequest):
    """Appends text to the end of a Google Doc via batchUpdate. WRITE path.
    Append-only by design — adds a new line, never overwrites or deletes existing content."""
    try:
        service = docs_service()
        doc = service.documents().get(documentId=doc_id).execute()
        content = doc.get("body", {}).get("content", [])
        end_index = content[-1].get("endIndex", 1) if content else 1
        insert_at = max(1, end_index - 1)
        requests = [
            {
                "insertText": {
                    "location": {"index": insert_at},
                    "text": "\n" + req.text
                }
            }
        ]
        service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests}
        ).execute()
        log(f"/drive/append OK — {len(req.text)} chars into {doc_id}")
        return {
            "write": "SUCCESS",
            "doc_id": doc_id,
            "appended_chars": len(req.text)
        }
    except HTTPException:
        raise
    except Exception as e:
        log(f"/drive/append FAILED — {e}")
        return {"write": "FAILED", "error": str(e)}


# ---------------- EXISTING BRAIN ENDPOINTS ----------------

@app.post("/ingest")
async def ingest_context(doc: ContextDocument):
    log(f"Ingesting context from source: {doc.source} ({len(doc.content)} chars)")

    current_notes = read_file(NOTES_FILE)
    current_library = read_file(LIBRARY_FILE)

    extraction_prompt = f"""You are the PICP Agent for Randy Wain Nutt's Progyny Infinite business brain.

A new context document has arrived. Extract and categorize what's in it.

CONTEXT DOCUMENT:
{doc.content}

You MUST respond with ONLY valid JSON, no other text, no markdown, no backticks. Example format:
{{"new_decisions": ["decision 1", "decision 2"], "project_updates": ["update 1"], "new_items": ["item 1"], "resolved_flags": [], "new_flags": ["flag 1"], "session_observation": "one sentence observation", "summary": "2-3 sentence summary of this session"}}"""

    extracted = None
    try:
        extraction_response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1000,
            messages=[{"role": "user", "content": extraction_prompt}]
        )
        raw = extraction_response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        extracted = json.loads(raw)
        log("JSON extraction successful")
    except Exception as e:
        log(f"JSON parse failed ({e}) — using fallback summary")
        try:
            fallback = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=500,
                messages=[{"role": "user", "content": f"Summarize this context document in 3 sentences:\n\n{doc.content}"}]
            )
            summary = fallback.content[0].text.strip()
        except Exception:
            summary = f"Context document ingested from {doc.source}."

        extracted = {
            "summary": summary,
            "new_decisions": [],
            "project_updates": [],
            "new_items": [],
            "resolved_flags": [],
            "new_flags": [],
            "session_observation": ""
        }

    today = datetime.datetime.now().strftime("%B %d, %Y")
    new_note = f"\n---\n**{today} — {doc.source}**\n{extracted.get('summary', '')}\n"

    if extracted.get('new_decisions'):
        new_note += "\n**Decisions:**\n" + "\n".join(f"- {d}" for d in extracted['new_decisions']) + "\n"
    if extracted.get('new_flags'):
        new_note += "\n**New Flags:**\n" + "\n".join(f"- {f}" for f in extracted['new_flags']) + "\n"
    if extracted.get('session_observation'):
        new_note += f"\n**Observation:** {extracted['session_observation']}\n"

    write_file(NOTES_FILE, (current_notes or "") + new_note)

    if extracted.get('new_decisions') or extracted.get('project_updates') or extracted.get('new_items'):
        try:
            library_prompt = f"""You are the PICP Agent. Update the knowledge library with this new information.

CURRENT LIBRARY (last 2000 chars):
{current_library[-2000:] if len(current_library) > 2000 else current_library}

NEW INFO:
Decisions: {extracted.get('new_decisions', [])}
Updates: {extracted.get('project_updates', [])}
New items: {extracted.get('new_items', [])}

Write ONLY the delta — new or changed sections in markdown. Start with: ## UPDATES — {today}"""

            lib_response = client.messages.create(
                model="claude-opus-4-8",
                max_tokens=1000,
                messages=[{"role": "user", "content": library_prompt}]
            )
            delta = lib_response.content[0].text
            write_file(LIBRARY_FILE, (current_library or "") + "\n\n" + delta)
            log("Library updated")
        except Exception as e:
            log(f"Library update failed: {e}")

    log(f"Ingest complete — decisions: {len(extracted.get('new_decisions', []))}, flags: {len(extracted.get('new_flags', []))}")

    return {
        "status": "ingested",
        "summary": extracted.get('summary', 'Ingested.'),
        "decisions_captured": len(extracted.get('new_decisions', [])),
        "flags_captured": len(extracted.get('new_flags', [])),
        "library_updated": bool(extracted.get('new_decisions') or extracted.get('project_updates'))
    }


@app.post("/query")
async def query_brain(req: QueryRequest):
    notes = read_file(NOTES_FILE)
    library = read_file(LIBRARY_FILE)

    if not notes and not library:
        return {"answer": "Brain is empty — ingest some context documents first."}

    response = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""You are the PICP Agent brain for Randy Wain Nutt's Progyny Infinite business.

LIBRARY:
{library[-3000:] if len(library) > 3000 else library}

NOTES:
{notes[-2000:] if len(notes) > 2000 else notes}

QUESTION: {req.question}

Answer directly and concisely. If you don't know, say so."""
        }]
    )

    return {"answer": response.content[0].text}


@app.get("/export/notes")
def export_notes():
    return {"content": read_file(NOTES_FILE)}


@app.get("/export/library")
def export_library():
    return {"content": read_file(LIBRARY_FILE)}


@app.get("/log")
def get_log():
    log_content = read_file(LOG_FILE)
    lines = log_content.strip().split("\n") if log_content else []
    return {"log": lines[-50:]}


if __name__ == "__main__":
    log("PICP Agent v1.2.0 starting up")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
