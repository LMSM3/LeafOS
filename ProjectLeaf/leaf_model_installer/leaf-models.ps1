$ErrorActionPreference = "Stop"
& "$PSScriptRoot\.venv\Scripts\python.exe" -m leaf_models.install_cli @args
exit $LASTEXITCODE
