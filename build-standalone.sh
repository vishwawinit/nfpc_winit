#!/bin/bash
set -e

# ─────────────────────────────────────────────────────────────
# Builds the APPLICATION package only (frontend + backend API).
# ETL runs on a separate server — it is NOT included here.
# ─────────────────────────────────────────────────────────────

echo "Building NFPC Reports — application package..."

# ── Clean ──────────────────────────────────────────────────────
rm -rf dist-standalone
rm -f  nfpc-reports.zip

# ── 1. Build Vite frontend ──────────────────────────────────────
echo "[1/4] Building frontend..."
cd frontend
npm ci --silent
npm run build
cd ..
echo "      Done -> frontend/dist/"

# ── 2. Assemble package ─────────────────────────────────────────
echo "[2/4] Assembling package..."
mkdir -p dist-standalone/frontend

# Backend API only — NO etl/ directory
cp -r api            dist-standalone/
cp -r frontend/dist  dist-standalone/frontend/dist
cp    Dockerfile     dist-standalone/
cp    railway.toml   dist-standalone/

# App-only requirements (no pymssql — that is only for ETL server)
cat > dist-standalone/requirements.txt << 'REQEOF'
fastapi
uvicorn[standard]
psycopg2-binary
python-dotenv
REQEOF

# ── 3. Write helper scripts ─────────────────────────────────────
echo "[3/4] Writing scripts..."

# .env template — app only needs PostgreSQL credentials
cat > dist-standalone/.env.example << 'ENVEOF'
# PostgreSQL Reporting DB (shared with ETL server)
PG_HOST=
PG_PORT=5432
PG_DATABASE=railway
PG_USER=postgres
PG_PASSWORD=

# Optional
GOOGLE_MAPS_API_KEY=
ENVEOF

# Linux / Mac — start app
cat > dist-standalone/start.sh << 'STARTEOF'
#!/bin/bash
PORT=${PORT:-8000}
echo "Starting NFPC Reports on port $PORT ..."
uvicorn api.main:app --host 0.0.0.0 --port "$PORT"
STARTEOF
chmod +x dist-standalone/start.sh

# Windows — start app
cat > dist-standalone/start.bat << 'BATEOF'
@echo off
set PORT=8000
echo Starting NFPC Reports on port %PORT% ...
uvicorn api.main:app --host 0.0.0.0 --port %PORT%
BATEOF

# ── 4. README ──────────────────────────────────────────────────
cat > dist-standalone/README.md << 'READMEEOF'
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
READMEEOF

# ── 5. Zip ──────────────────────────────────────────────────────
echo "[4/4] Creating zip..."
python -c "
import zipfile, os, pathlib

src = pathlib.Path('dist-standalone')
out = pathlib.Path('nfpc-reports.zip')

with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
    for f in src.rglob('*'):
        if f.suffix == '.pyc': continue
        parts = f.relative_to(src).parts
        if '__pycache__' in parts: continue
        if f.is_file():
            zf.write(f, f.relative_to(src))

print(f'Created: {out}  ({out.stat().st_size // 1024} KB)')
"

echo ""
echo "Build complete."
echo ""
echo "  Package : dist-standalone/"
echo "  Archive : nfpc-reports.zip"
echo ""
echo "  Contents:"
echo "    api/              FastAPI backend"
echo "    frontend/dist/    Pre-built React SPA"
echo "    requirements.txt  Python deps (app only)"
echo "    start.sh / .bat   Launch scripts"
echo "    Dockerfile"
echo ""
echo "Deployment:"
echo "  1. Copy nfpc-reports.zip to app server and unzip"
echo "  2. pip install -r requirements.txt"
echo "  3. cp .env.example .env  (fill in PostgreSQL credentials)"
echo "  4. ./start.sh            (starts on port 8000)"
