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

app = FastAPI(title="PICP Agent", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.g
