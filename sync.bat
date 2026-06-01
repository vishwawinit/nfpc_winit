@echo off
cd /d "%~dp0"

set DAYS=%1
if "%DAYS%"=="" set DAYS=2

echo ============================================
echo  NFPC Incremental Sync
echo  Days : %DAYS%
echo  Mode : upsert (no delete)
echo ============================================

python etl\extract.py --days %DAYS%

if %ERRORLEVEL% == 0 (
    echo [SUCCESS] Sync completed.
) else (
    echo [FAILED]  Sync failed. Check etl\logs\ for details.
)
