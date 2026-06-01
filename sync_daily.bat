@echo off
cd /d "%~dp0"

set LOG_DIR=etl\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set LOG_FILE=%LOG_DIR%\sync_%date:~10,4%%date:~4,2%%date:~7,2%.log

echo ============================================ >> "%LOG_FILE%"
echo  NFPC Daily Sync - %date% %time%            >> "%LOG_FILE%"
echo  Mode: --days 2 (yesterday + today)         >> "%LOG_FILE%"
echo ============================================ >> "%LOG_FILE%"

python etl\extract.py --days 2 >> "%LOG_FILE%" 2>&1

if %ERRORLEVEL% == 0 (
    echo [SUCCESS] Sync completed at %time% >> "%LOG_FILE%"
) else (
    echo [FAILED]  Sync failed at %time% - check log >> "%LOG_FILE%"
)
