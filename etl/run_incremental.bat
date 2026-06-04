@echo off
REM NFPC Daily Incremental ETL
REM Syncs last 3 days (safety window) using upsert mode — no data wipe.
REM Schedule in Windows Task Scheduler to run daily at e.g. 02:00 AM.
REM
REM For FULL RELOAD run:  run_full_etl.bat

cd /d "%~dp0"

REM Get yesterday's date via PowerShell
for /f %%D in ('powershell -NoProfile -Command "(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')"') do set YESTERDAY=%%D

echo ============================================================
echo   NFPC Incremental ETL -- %date% %time%
echo   Syncing last 3 days (from %YESTERDAY%)
echo ============================================================

REM extract.py --days 3 = last 2 days + today, upsert mode (no delete)
echo.
echo [1/2] Running extract.py --days 3 (all tables)...
python etl\extract.py --days 3
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: extract.py failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

REM sync_rsic_from_trx.py with yesterday as start date
echo.
echo [2/2] Running sync_rsic_from_trx.py --from-date %YESTERDAY%...
python etl\sync_rsic_from_trx.py --from-date %YESTERDAY%
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: sync_rsic_from_trx.py failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo   Done -- %date% %time%
echo ============================================================
