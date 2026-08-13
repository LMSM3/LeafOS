@echo off
"%~dp0.venv\Scripts\python.exe" -m leaf_models.install_cli %*
exit /b %ERRORLEVEL%
