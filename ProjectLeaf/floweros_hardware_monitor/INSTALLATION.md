# Installation Stack

The bundle is self-contained apart from Python. It creates a local `.venv`,
installs the package in editable mode, and runs a one-shot smoke check.

## Requirements

- Python 3.9 or newer.
- Internet access for first install unless `psutil` and `rich` are already cached.
- Optional: `nvidia-smi`, `lm-sensors`, LibreHardwareMonitor, or OpenHardwareMonitor
  for deeper hardware telemetry.

## Windows

```powershell
Set-Location .\floweros_hardware_monitor
.\install.ps1
.\run.ps1
```

If script execution is blocked for the current shell:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\install.ps1
```

## Linux, macOS, or WSL

```bash
cd floweros_hardware_monitor
chmod +x install.sh run.sh
./install.sh
./run.sh
```

## Smoke Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -m floweros_hwmon --once
```

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m floweros_hwmon --once
```

## Notes on Fan Speed

Fan readings are highly dependent on motherboard, laptop firmware, and driver
support. When real RPM or percent is unavailable, the monitor uses a visible
`EST` value based on temperature/load. That estimate is deliberately labeled and
does not change hardware fan behavior.
