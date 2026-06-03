# NFPC Reports — Application Server

> **This package is the Application Server only (API + Frontend).**
> The ETL pipeline runs on a separate server and populates the shared PostgreSQL DB.

---

## Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│   ETL Server        │        │   App Server (this)  │
│                     │        │                      │
│  etl/extract.py  ──────────> │  api/  (FastAPI)     │
│  MSSQL → PostgreSQL │  shared│  frontend/dist/      │
│                     │   DB   │  (React SPA)         │
└─────────────────────┘        └──────────────────────┘
```

---

## Requirements
- Python 3.12+
- Node.js **not required** (frontend is pre-built)
- Access to the shared PostgreSQL reporting DB

---

## Setup

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Fill in PG_HOST, PG_PORT, PG_DATABASE, PG_USER, PG_PASSWORD
```

### 3. Start the application

**Linux / Mac:**
```bash
./start.sh
```

**Windows:**
```cmd
start.bat
```

**Custom port:**
```bash
PORT=9000 ./start.sh
```

Open browser: **http://localhost:8000**

---

## Docker
```bash
docker build -t nfpc-reports .
docker run -p 8000:8000 --env-file .env nfpc-reports
```

---

## Health Check
```
GET http://localhost:8000/api/health
```
