@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)
if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)
if not defined PYTHON_CMD (
  echo [ERROR] Python 3.10 or newer was not found.
  echo Install Python from https://www.python.org/downloads/windows/
  echo During installation, enable Add python.exe to PATH.
  pause
  exit /b 1
)
echo Using %PYTHON_CMD%
echo.
echo 1: Download the pinned Spider-ACL input dataset
echo 2: Install Spider SQLite databases from a downloaded ZIP
echo 3: Spider database preflight
echo 4: Offline D1 baselines (deny_only and rule)
echo 5: API pilot first 20 D1 rows (3 model methods)
echo 6: API full D1 corpus (resume supported)
echo 7: D3 frozen-scenario experiment (requires API key for LLM methods)
echo 8: SQLite execution audit of accepted D1 SQL
echo.
set /p CHOICE=Choose 1-8: 
if "%CHOICE%"=="1" %PYTHON_CMD% scripts\download_access_control_dataset.py
if "%CHOICE%"=="2" goto INSTALL_SPIDER
if "%CHOICE%"=="3" %PYTHON_CMD% preflight_spider.py
if "%CHOICE%"=="4" %PYTHON_CMD% run_unified.py --dataset D1 --methods deny_only rule --out baseline_results
if "%CHOICE%"=="5" %PYTHON_CMD% run_unified.py --dataset D1 --methods naive_retry sql_aware_retry diagnostic_revision --max-cases 20 --enable-api --out pilot_results
if "%CHOICE%"=="6" %PYTHON_CMD% run_unified.py --dataset D1 --methods naive_retry sql_aware_retry diagnostic_revision --enable-api --out results
if "%CHOICE%"=="7" %PYTHON_CMD% run_unified.py --dataset D3 --methods deny_only rule naive_retry sql_aware_retry diagnostic_revision --enable-api --out results
if "%CHOICE%"=="8" %PYTHON_CMD% verify_sqlite.py --results results\D1
if "%CHOICE%"=="2" goto END
if not "%CHOICE%"=="1" if not "%CHOICE%"=="3" if not "%CHOICE%"=="4" if not "%CHOICE%"=="5" if not "%CHOICE%"=="6" if not "%CHOICE%"=="7" if not "%CHOICE%"=="8" echo Invalid choice.
goto END

:INSTALL_SPIDER
set /p SPIDER_ARCHIVE=Enter full path to downloaded Spider ZIP: 
%PYTHON_CMD% scripts\install_spider_database.py --archive "%SPIDER_ARCHIVE%"
:END
pause
