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
