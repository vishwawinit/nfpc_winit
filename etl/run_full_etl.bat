@echo off
REM NFPC Full ETL — Reloads ALL data from 2026-01-01 to today.
REM Takes 30-90 minutes. Only run when you need a complete fresh load.
REM For daily incremental use:  run_incremental.bat

cd /d "%~dp0"

echo ============================================================
echo   NFPC FULL ETL -- %date% %time%
echo   Range: 2026-01-01 to today
echo   WARNING: This will take 30-90 minutes
echo ============================================================

python etl\extract.py --from-date 2026-01-01
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: extract.py failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

python etl\sync_rsic_from_trx.py --from-date 2026-01-01
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: sync_rsic_from_trx.py failed with code %ERRORLEVEL%
    exit /b %ERRORLEVEL%
)

echo.
echo ============================================================
echo   Full ETL Done -- %date% %time%
echo ============================================================
