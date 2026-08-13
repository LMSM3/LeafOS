# FlowerOS Hardware Monitor

FlowerOS Hardware Monitor is a branded terminal dashboard for CPU, memory,
storage, network, battery, thermal, GPU, and fan telemetry.

It reads real sensors when the platform exposes them:

- `psutil` for CPU, memory, disk, network, battery, and platform sensors.
- `nvidia-smi` for NVIDIA GPU temperature, fan percent, utilization, memory, and power.
- `sensors -j` from `lm-sensors` on Linux.
- Windows CIM plus optional LibreHardwareMonitor or OpenHardwareMonitor WMI namespaces.

If no fan sensor can be read, the dashboard shows `EST` and computes a fan speed
estimate from hottest available temperature plus CPU load. That estimate is for
monitoring only; it is not fan control.

## Quick Start

Windows PowerShell:

```powershell
.\install.ps1
.\run.ps1
```

Linux, macOS, or WSL:

```bash
chmod +x install.sh run.sh
./install.sh
./run.sh
```

Installed console commands:

```bash
floweros-hwmon
flower-hwmon --once
flower-hwmon --json
```

## Better Fan and Temperature Data

Windows motherboard fan RPM often is not exposed to normal user-space APIs. For
better readings, run LibreHardwareMonitor or OpenHardwareMonitor with WMI enabled.
The monitor checks both `root\LibreHardwareMonitor` and `root\OpenHardwareMonitor`.

Linux fan and temperature data improves after configuring `lm-sensors`:

```bash
sudo sensors-detect
sensors
```

## Useful Options

```bash
floweros-hwmon --interval 1
floweros-hwmon --once
floweros-hwmon --json
floweros-hwmon --no-external-sensors
floweros-hwmon --fan-min-rpm 600 --fan-max-rpm 5000
```

`Ctrl+C` exits the live TUI.
