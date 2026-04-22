@echo off
setlocal EnableExtensions

REM ============================================================
REM  Run Neurokey autotests.
REM
REM  Usage examples:
REM    run_tests.bat                        - все тесты на dev
REM    run_tests.bat --env prod             - все тесты на prod
REM    run_tests.bat -m smoke               - только smoke
REM    run_tests.bat -m "login or auth"     - несколько маркеров
REM    run_tests.bat -k test_login_page     - фильтр по имени
REM    run_tests.bat -n 4                   - parallel (pytest-xdist)
REM    run_tests.bat --env dev -m smoke -n 2
REM ============================================================

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else if exist "venv\Scripts\activate.bat" (
    call "venv\Scripts\activate.bat"
)

where pytest >nul 2>nul
if errorlevel 1 (
    echo [ERROR] pytest not found. Install dependencies first:
    echo     pip install -r requirements.txt
    echo     playwright install chromium
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Running Neurokey tests...
echo ============================================================
echo.

if "%~1"=="" (
    pytest --env dev
) else (
    pytest %*
)
set "EXITCODE=%ERRORLEVEL%"

where allure >nul 2>nul
if not errorlevel 1 (
    echo.
    echo ============================================================
    echo  Generating Allure report...
    echo ============================================================
    allure generate allure-results --clean -o allure-report
    echo.
    echo Report: %CD%\allure-report\index.html
    echo Open:   allure open allure-report
)

echo.
echo ============================================================
echo  Done. pytest exit code: %EXITCODE%
echo    0  = all tests passed
echo    1  = some tests failed
echo    2+ = runner error
echo ============================================================
echo.
pause
endlocal ^& exit /b %EXITCODE%
