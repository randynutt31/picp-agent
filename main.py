"""
PICP Agent — Progyny Infinite Command Project
Autonomous context ingestion and brain update agent.

What it does:
- Receives context documents via a simple web endpoint
- Processes them through Claude API
- Updates the PICP knowledge files automatically
- Logs every update with timestamp

Deploy on Railway. Runs 24/7. No manual steps after setup.
"""

import os
import json
import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic
import uvicorn

app = FastAPI(title="PICP Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# In-memory brain store (Railway persistent volume path: /app/data/)
DATA_DIR = "/app/data"
NOTES_FILE = f"{DATA_DIR}/notes.md"
LIBRARY_FILE = f"{DATA_DIR}/library.md"
LOG_FILE = f"{DATA_DIR}/agent.log"

os.makedirs(DATA_DIR, exist_ok=True)


def log(message: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    print(entry)
    with open(LOG_FILE, "a") as f:
        f.write(entry)


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
    source: str = "manual"  # manual, extraction, session


class QueryRequest(BaseModel):
    question: str


@app.get("/")
def health():
    return {
        "status": "PICP Agent online",
        "version": "1.0.0",
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


@app.post("/ingest")
async def ingest_context(doc: ContextDocument):
    """
    Main ingestion endpoint.
    Send any context document here — the agent processes it and updates the brain.
    """
    log(f"Ingesting context from source: {doc.source} ({len(doc.content)} chars)")
    
    current_notes = read_file(NOTES_FILE)
    current_library = read_file(LIBRARY_FILE)
    
    # Step 1: Extract key information from the context document
    extraction_prompt = f"""You are the PICP Agent for Randy Wain Nutt's Progyny Infinite business brain.

A new context document has arrived. Extract and categorize what's in it:

CONTEXT DOCUMENT:
{doc.content}

Extract the following in JSON format:
{{
  "new_decisions": ["list of new locked decisions"],
  "project_updates": ["list of project status changes"],
  "new_items": ["list of new pipeline items, tools, or initiatives"],
  "resolved_flags": ["list of open flags that are now resolved"],
  "new_flags": ["list of new open items or blockers"],
  "session_observation": "one sentence about what this session reveals about how Randy works best",
  "summary": "2-3 sentence summary of what happened in this session"
}}

Return only valid JSON. No other text."""

    extraction_response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": extraction_prompt}]
    )
    
    try:
        extracted = json.loads(extraction_response.content[0].text)
    except json.JSONDecodeError:
        log("JSON parse failed — storing raw context")
        extracted = {
            "summary": "Raw context stored — parse failed",
            "new_decisions": [],
            "project_updates": [],
            "new_items": [],
            "resolved_flags": [],
            "new_flags": [],
            "session_observation": ""
        }

    # Step 2: Update notes.md with session entry
    today = datetime.datetime.now().strftime("%B %d, %Y")
    
    new_note_entry = f"""
---
**{today} — {doc.source}**
{extracted.get('summary', 'Session processed.')}

"""
    if extracted.get('new_decisions'):
        new_note_entry += "**New Decisions:**\n"
        for d in extracted['new_decisions']:
            new_note_entry += f"- {d}\n"
        new_note_entry += "\n"
    
    if extracted.get('new_flags'):
        new_note_entry += "**New Flags:**\n"
        for f in extracted['new_flags']:
            new_note_entry += f"- {f}\n"
        new_note_entry += "\n"

    if extracted.get('session_observation'):
        new_note_entry += f"**Observation:** {extracted['session_observation']}\n"

    updated_notes = current_notes + new_note_entry if current_notes else new_note_entry
    write_file(NOTES_FILE, updated_notes)
    
    # Step 3: Check if library needs updating
    if extracted.get('new_decisions') or extracted.get('project_updates') or extracted.get('new_items'):
        library_update_prompt = f"""You are the PICP Agent managing Randy's business brain library.

CURRENT LIBRARY (excerpt — last 2000 chars):
{current_library[-2000:] if len(current_library) > 2000 else current_library}

NEW INFORMATION TO INTEGRATE:
Decisions: {extracted.get('new_decisions', [])}
Project updates: {extracted.get('project_updates', [])}
New items: {extracted.get('new_items', [])}
Resolved flags: {extracted.get('resolved_flags', [])}

Write ONLY the updated sections that need to change. Format as markdown.
Keep it concise. Do not rewrite the entire library — just the delta.
Start with: ## LIBRARY UPDATES — {today}"""

        library_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": library_update_prompt}]
        )
        
        library_delta = library_response.content[0].text
        updated_library = current_library + "\n\n" + library_delta
        write_file(LIBRARY_FILE, updated_library)
        log("Library updated with new delta")
    
    log(f"Ingestion complete — {len(extracted.get('new_decisions', []))} decisions, {len(extracted.get('new_flags', []))} flags")
    
    return {
        "status": "ingested",
        "summary": extracted.get('summary'),
        "decisions_captured": len(extracted.get('new_decisions', [])),
        "flags_captured": len(extracted.get('new_flags', [])),
        "library_updated": bool(extracted.get('new_decisions') or extracted.get('project_updates'))
    }


@app.post("/query")
async def query_brain(req: QueryRequest):
    """
    Ask the brain a question. Returns answer based on everything ingested.
    """
    notes = read_file(NOTES_FILE)
    library = read_file(LIBRARY_FILE)
    
    if not notes and not library:
        return {"answer": "Brain is empty — ingest some context documents first."}
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""You are the PICP Agent brain for Randy Wain Nutt's Progyny Infinite business.

LIBRARY:
{library[-3000:] if len(library) > 3000 else library}

RECENT NOTES:
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
    log("PICP Agent starting up")
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
