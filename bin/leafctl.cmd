@echo off
set "PYTHONDONTWRITEBYTECODE=1"
set "LEAF_ROOT=%~dp0.."
python "%LEAF_ROOT%\core\cli.py" %*
exit /b %ERRORLEVEL%
