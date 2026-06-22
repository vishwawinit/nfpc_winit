@echo off
set PORT=8000
echo Starting NFPC Reports on port %PORT% ...
uvicorn api.main:app --host 0.0.0.0 --port %PORT%
