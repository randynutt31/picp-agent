# PICP Agent
## Progyny Infinite Command Project — Autonomous Brain Agent

Receives context documents, processes them through Claude, updates the knowledge base automatically. Runs 24/7 on Railway.

---

## DEPLOY TO RAILWAY — 5 STEPS

### Step 1 — Push this repo to GitHub
1. Create a new GitHub repo named `picp-agent`
2. Upload all files from this folder to it

### Step 2 — Create Railway project
1. Go to railway.app
2. Click New Project
3. Choose Deploy from GitHub repo
4. Select your `picp-agent` repo
5. Railway auto-detects Python and deploys

### Step 3 — Add environment variable
1. In Railway, go to your project → Variables
2. Add: `ANTHROPIC_API_KEY` = your Claude API key
3. Railway restarts automatically

### Step 4 — Add persistent volume
1. In Railway, go to your project → Volumes
2. Add volume, mount at `/app/data`
3. This keeps your brain data across deployments

### Step 5 — Get your URL
1. Railway gives you a public URL like `https://picp-agent-production.up.railway.app`
2. Save that URL — that's your agent's address
3. Test it: open the URL in your browser, you should see `{"status": "PICP Agent online"}`

---

## HOW TO USE IT

### Send a context document to the agent
```
POST https://your-railway-url.up.railway.app/ingest
Content-Type: application/json

{
  "content": "paste your context document here",
  "source": "session"
}
```

### Ask the brain a question
```
POST https://your-railway-url.up.railway.app/query
Content-Type: application/json

{
  "question": "What is the current status of ProgenyVault?"
}
```

### Check agent status
```
GET https://your-railway-url.up.railway.app/status
```

### View recent logs
```
GET https://your-railway-url.up.railway.app/log
```

---

## API ENDPOINTS

| Endpoint | Method | What it does |
|---|---|---|
| / | GET | Health check |
| /status | GET | Brain size, last log entries |
| /ingest | POST | Send context document to brain |
| /query | POST | Ask brain a question |
| /export/notes | GET | Download current notes |
| /export/library | GET | Download current library |
| /log | GET | Last 50 log entries |

---

## ENVIRONMENT VARIABLES

| Variable | Required | Description |
|---|---|---|
| ANTHROPIC_API_KEY | Yes | Your Claude API key |
| PORT | No | Auto-set by Railway |

---

## ARCHITECTURE

```
Context Document
      ↓
  /ingest endpoint
      ↓
  Claude API extracts:
  - New decisions
  - Project updates  
  - New flags
  - Session observation
      ↓
  Updates notes.md (every ingest)
  Updates library.md (if decisions/updates found)
      ↓
  Persistent storage at /app/data/
```

---

*PICP Agent v1.0 — Built June 27, 2026*
*Progyny Infinite — Randy Wain Nutt*
