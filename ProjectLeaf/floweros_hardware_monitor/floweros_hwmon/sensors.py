from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

try:
    import psutil
except Exception:  # pragma: no cover - installer supplies this, fallback keeps import readable.
    psutil = None  # type: ignore[assignment]


Number = int | float


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text.upper() in {"N/A", "NA", "NONE", "--"}:
        return None
    for suffix in ("%", "RPM", "rpm", "C", "W", "MHz", "MiB", "MB"):
        text = text.replace(suffix, "")
    try:
        return float(text.strip())
    except ValueError:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _run_command(command: list[str], timeout: float) -> tuple[int, str, str]:
    startupinfo = None
    creationflags = 0
    if platform.system().lower() == "windows":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        proc = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout,
            startupinfo=startupinfo,
            creationflags=creationflags,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, "", str(exc)


@dataclass
class SensorCollector:
    fan_min_rpm: int = 700
    fan_max_rpm: int = 4200
    external_sensor_interval: float = 5.0
    include_external: bool = True
    _last_disk_io: Any = field(default=None, init=False)
    _last_net_io: dict[str, Any] = field(default_factory=dict, init=False)
    _last_rate_time: float = field(default_factory=time.monotonic, init=False)
    _last_external_read: float = field(default=0.0, init=False)
    _external_cache: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {"temps": [], "fans": [], "gpus": [], "notes": []},
        init=False,
    )
    _primed: bool = field(default=False, init=False)

    def sample(self) -> dict[str, Any]:
        now = time.monotonic()
        rate_dt = max(now - self._last_rate_time, 0.001)
        cpu = self._cpu()
        memory = self._memory()
        disks, disk_io = self._disks(rate_dt)
        network = self._network(rate_dt)
        battery = self._battery()
        sensors = self._sensors(cpu.get("percent", 0.0))
        self._last_rate_time = now

        return {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "host": socket.gethostname(),
            "platform": self._platform_summary(),
            "uptime_seconds": self._uptime_seconds(),
            "cpu": cpu,
            "memory": memory,
            "disks": disks,
            "disk_io": disk_io,
            "network": network,
            "battery": battery,
            "temperatures": sensors["temps"],
            "fans": sensors["fans"],
            "gpus": sensors["gpus"],
            "notes": sensors["notes"],
        }

    def _platform_summary(self) -> str:
        release = platform.release()
        machine = platform.machine()
        return f"{platform.system()} {release} {machine}".strip()

    def _uptime_seconds(self) -> float | None:
        if psutil is None:
            return None
        try:
            return max(0.0, time.time() - psutil.boot_time())
        except Exception:
            return None

    def _cpu(self) -> dict[str, Any]:
        if psutil is None:
            return {"percent": 0.0, "per_core": [], "physical": None, "logical": os.cpu_count()}
        try:
            total = psutil.cpu_percent(interval=0.08 if not self._primed else None)
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            self._primed = True
        except Exception:
            total, per_core = 0.0, []
        try:
            freq = psutil.cpu_freq()
        except Exception:
            freq = None
        load_avg = None
        if hasattr(os, "getloadavg"):
            try:
                load_avg = os.getloadavg()
            except OSError:
                load_avg = None
        return {
            "percent": float(total),
            "per_core": [float(value) for value in per_core],
            "physical": psutil.cpu_count(logical=False),
            "logical": psutil.cpu_count(logical=True),
            "frequency_mhz": {
                "current": getattr(freq, "current", None),
                "min": getattr(freq, "min", None),
                "max": getattr(freq, "max", None),
            }
            if freq
            else None,
            "load_avg": load_avg,
        }

    def _memory(self) -> dict[str, Any]:
        if psutil is None:
            return {"ram": None, "swap": None}
        try:
            ram = psutil.virtual_memory()._asdict()
        except Exception:
            ram = None
        try:
            swap = psutil.swap_memory()._asdict()
        except Exception:
            swap = None
        return {"ram": ram, "swap": swap}

    def _disks(self, rate_dt: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        disks: list[dict[str, Any]] = []
        disk_io = {"read_bps": 0.0, "write_bps": 0.0}
        if psutil is None:
            return disks, disk_io
        try:
            partitions = psutil.disk_partitions(all=False)
        except Exception:
            partitions = []
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (OSError, PermissionError):
                continue
            disks.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            )
        try:
            current = psutil.disk_io_counters()
        except Exception:
            current = None
        if current is not None and self._last_disk_io is not None:
            disk_io = {
                "read_bps": max(0.0, (current.read_bytes - self._last_disk_io.read_bytes) / rate_dt),
                "write_bps": max(0.0, (current.write_bytes - self._last_disk_io.write_bytes) / rate_dt),
                "read_count": current.read_count,
                "write_count": current.write_count,
            }
        if current is not None:
            self._last_disk_io = current
        return disks, disk_io

    def _network(self, rate_dt: float) -> list[dict[str, Any]]:
        if psutil is None:
            return []
        try:
            counters = psutil.net_io_counters(pernic=True)
            stats = psutil.net_if_stats()
        except Exception:
            return []
        rows: list[dict[str, Any]] = []
        for name, current in counters.items():
            stat = stats.get(name)
            last = self._last_net_io.get(name)
            recv_bps = sent_bps = 0.0
            if last is not None:
                recv_bps = max(0.0, (current.bytes_recv - last.bytes_recv) / rate_dt)
                sent_bps = max(0.0, (current.bytes_sent - last.bytes_sent) / rate_dt)
            is_up = bool(getattr(stat, "isup", False))
            if not is_up and current.bytes_recv == 0 and current.bytes_sent == 0:
                self._last_net_io[name] = current
                continue
            rows.append(
                {
                    "name": name,
                    "is_up": is_up,
                    "speed_mbps": getattr(stat, "speed", None),
                    "bytes_recv": current.bytes_recv,
                    "bytes_sent": current.bytes_sent,
                    "recv_bps": recv_bps,
                    "sent_bps": sent_bps,
                }
            )
            self._last_net_io[name] = current
        rows.sort(key=lambda item: (not item["is_up"], item["name"].lower()))
        return rows

    def _battery(self) -> dict[str, Any] | None:
        if psutil is None or not hasattr(psutil, "sensors_battery"):
            return None
        try:
            battery = psutil.sensors_battery()
        except Exception:
            return None
        if battery is None:
            return None
        return {
            "percent": battery.percent,
            "plugged": battery.power_plugged,
            "secsleft": battery.secsleft,
        }

    def _sensors(self, cpu_percent: float) -> dict[str, list[dict[str, Any]]]:
        temps: list[dict[str, Any]] = []
        fans: list[dict[str, Any]] = []
        gpus: list[dict[str, Any]] = []
        notes: list[dict[str, Any]] = []

        self._read_psutil_sensors(temps, fans)
        if self.include_external:
            now = time.monotonic()
            if now - self._last_external_read >= self.external_sensor_interval:
                self._external_cache = self._read_external_sensors()
                self._last_external_read = now
            temps.extend(self._external_cache.get("temps", []))
            fans.extend(self._external_cache.get("fans", []))
            gpus.extend(self._external_cache.get("gpus", []))
            notes.extend(self._external_cache.get("notes", []))

        if not fans:
            fans.append(self._estimated_fan(cpu_percent, temps))
            notes.append(
                {
                    "level": "estimate",
                    "message": "No readable fan sensor found; fan speed is estimated from temperature and CPU load.",
                }
            )
        elif not self._has_non_gpu_real_fan(fans):
            fans.append(self._estimated_fan(cpu_percent, temps))
            notes.append(
                {
                    "level": "estimate",
                    "message": "No readable system fan sensor found; system fan speed is estimated while GPU fan data remains real.",
                }
            )
        return {"temps": temps, "fans": fans, "gpus": gpus, "notes": notes}

    @staticmethod
    def _has_non_gpu_real_fan(fans: Iterable[dict[str, Any]]) -> bool:
        for fan in fans:
            if fan.get("estimated"):
                continue
            label = f"{fan.get('name', '')} {fan.get('source', '')}".lower()
            if "gpu" not in label and "nvidia" not in label:
                return True
        return False

    def _read_psutil_sensors(self, temps: list[dict[str, Any]], fans: list[dict[str, Any]]) -> None:
        if psutil is None:
            return
        if hasattr(psutil, "sensors_temperatures"):
            try:
                for chip, entries in psutil.sensors_temperatures(fahrenheit=False).items():
                    for entry in entries:
                        current = _to_float(getattr(entry, "current", None))
                        if current is None:
                            continue
                        label = " ".join(part for part in [chip, getattr(entry, "label", "")] if part)
                        temps.append(
                            {
                                "name": label or chip,
                                "celsius": round(current, 1),
                                "high": _to_float(getattr(entry, "high", None)),
                                "critical": _to_float(getattr(entry, "critical", None)),
                                "source": "psutil",
                            }
                        )
            except Exception:
                pass
        if hasattr(psutil, "sensors_fans"):
            try:
                for chip, entries in psutil.sensors_fans().items():
                    for entry in entries:
                        rpm = _to_float(getattr(entry, "current", None))
                        if rpm is None or rpm <= 0:
                            continue
                        label = " ".join(part for part in [chip, getattr(entry, "label", "")] if part)
                        fans.append(
                            {
                                "name": label or chip,
                                "rpm": round(rpm),
                                "percent": None,
                                "source": "psutil",
                                "estimated": False,
                            }
                        )
            except Exception:
                pass

    def _read_external_sensors(self) -> dict[str, list[dict[str, Any]]]:
        found = {"temps": [], "fans": [], "gpus": [], "notes": []}
        self._read_nvidia_smi(found)
        if platform.system().lower() == "windows":
            self._read_windows_cim(found)
        else:
            self._read_linux_sensors(found)
        return found

    def _read_nvidia_smi(self, found: dict[str, list[dict[str, Any]]]) -> None:
        tool = shutil.which("nvidia-smi")
        if not tool:
            return
        query = (
            "index,name,temperature.gpu,fan.speed,utilization.gpu,"
            "memory.used,memory.total,power.draw,power.limit"
        )
        command = [tool, f"--query-gpu={query}", "--format=csv,noheader,nounits"]
        code, stdout, _ = _run_command(command, timeout=2.0)
        if code != 0 or not stdout.strip():
            return
        for row in csv.reader(stdout.splitlines()):
            columns = [column.strip() for column in row]
            if len(columns) < 9:
                continue
            index, name = columns[0], columns[1]
            temp_c = _to_float(columns[2])
            fan_percent = _to_float(columns[3])
            util = _to_float(columns[4])
            mem_used = _to_float(columns[5])
            mem_total = _to_float(columns[6])
            power_draw = _to_float(columns[7])
            power_limit = _to_float(columns[8])
            gpu = {
                "index": index,
                "name": name,
                "temperature_c": temp_c,
                "fan_percent": fan_percent,
                "utilization_percent": util,
                "memory_used_mib": mem_used,
                "memory_total_mib": mem_total,
                "power_draw_w": power_draw,
                "power_limit_w": power_limit,
                "source": "nvidia-smi",
            }
            found["gpus"].append(gpu)
            if temp_c is not None:
                found["temps"].append(
                    {
                        "name": f"{name} GPU",
                        "celsius": round(temp_c, 1),
                        "high": None,
                        "critical": None,
                        "source": "nvidia-smi",
                    }
                )
            if fan_percent is not None:
                found["fans"].append(
                    {
                        "name": f"{name} GPU fan",
                        "rpm": None,
                        "percent": round(fan_percent, 1),
                        "source": "nvidia-smi",
                        "estimated": False,
                    }
                )

    def _read_linux_sensors(self, found: dict[str, list[dict[str, Any]]]) -> None:
        tool = shutil.which("sensors")
        if not tool:
            return
        code, stdout, _ = _run_command([tool, "-j"], timeout=2.0)
        if code != 0 or not stdout.strip():
            return
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return

        def walk(node: Any, path: list[str]) -> None:
            if not isinstance(node, dict):
                return
            for key, value in node.items():
                if key.endswith("_input") and isinstance(value, (int, float)):
                    lower = key.lower()
                    label = " / ".join(path + [key.removesuffix("_input")])
                    if "fan" in lower:
                        found["fans"].append(
                            {
                                "name": label,
                                "rpm": round(float(value)),
                                "percent": None,
                                "source": "lm-sensors",
                                "estimated": False,
                            }
                        )
                    elif "temp" in lower:
                        found["temps"].append(
                            {
                                "name": label,
                                "celsius": round(float(value), 1),
                                "high": None,
                                "critical": None,
                                "source": "lm-sensors",
                            }
                        )
                elif isinstance(value, dict):
                    walk(value, path + [key])

        walk(payload, [])

    def _read_windows_cim(self, found: dict[str, list[dict[str, Any]]]) -> None:
        shell = shutil.which("pwsh") or shutil.which("powershell") or shutil.which("powershell.exe")
        if not shell:
            return
        script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$hardware = @()
foreach ($ns in @('root\LibreHardwareMonitor','root\OpenHardwareMonitor')) {
  $items = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction SilentlyContinue
  foreach ($item in $items) {
    if ($item.SensorType -in @('Temperature','Fan','Load','Power','Clock','Voltage')) {
      $hardware += [pscustomobject]@{
        Namespace = $ns
        Name = $item.Name
        SensorType = $item.SensorType
        Value = $item.Value
        Identifier = $item.Identifier
      }
    }
  }
}
$acpi = @()
$zones = Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue
foreach ($zone in $zones) {
  $acpi += [pscustomobject]@{
    Name = $zone.InstanceName
    CurrentTemperature = $zone.CurrentTemperature
  }
}
$fans = @()
$winFans = Get-CimInstance -ClassName Win32_Fan -ErrorAction SilentlyContinue
foreach ($fan in $winFans) {
  $fans += [pscustomobject]@{
    Name = $fan.Name
    DesiredSpeed = $fan.DesiredSpeed
    Status = $fan.Status
  }
}
[pscustomobject]@{ HardwareMonitor = $hardware; Acpi = $acpi; Fans = $fans } |
  ConvertTo-Json -Depth 5 -Compress
"""
        code, stdout, _ = _run_command(
            [shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            timeout=4.0,
        )
        if code != 0 or not stdout.strip():
            return
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError:
            return
        for item in _as_list(payload.get("HardwareMonitor")):
            sensor_type = str(item.get("SensorType", "")).lower()
            value = _to_float(item.get("Value"))
            name = str(item.get("Name") or item.get("Identifier") or "Hardware sensor")
            namespace = str(item.get("Namespace") or "Windows hardware monitor")
            source = namespace.replace("root\\", "")
            if value is None:
                continue
            if sensor_type == "temperature":
                found["temps"].append(
                    {
                        "name": name,
                        "celsius": round(value, 1),
                        "high": None,
                        "critical": None,
                        "source": source,
                    }
                )
            elif sensor_type == "fan":
                found["fans"].append(
                    {
                        "name": name,
                        "rpm": round(value) if value > 100 else None,
                        "percent": round(value, 1) if value <= 100 else None,
                        "source": source,
                        "estimated": False,
                    }
                )
        for zone in _as_list(payload.get("Acpi")):
            raw = _to_float(zone.get("CurrentTemperature"))
            if raw is None or raw <= 0:
                continue
            celsius = raw / 10.0 - 273.15
            if -20 <= celsius <= 130:
                found["temps"].append(
                    {
                        "name": str(zone.get("Name") or "ACPI thermal zone"),
                        "celsius": round(celsius, 1),
                        "high": None,
                        "critical": None,
                        "source": "Windows ACPI",
                    }
                )
        for fan in _as_list(payload.get("Fans")):
            speed = _to_float(fan.get("DesiredSpeed"))
            if speed is None or speed <= 0:
                continue
            found["fans"].append(
                {
                    "name": str(fan.get("Name") or "Windows fan"),
                    "rpm": round(speed),
                    "percent": None,
                    "source": "Win32_Fan",
                    "estimated": False,
                }
            )

    def _estimated_fan(self, cpu_percent: float, temps: Iterable[dict[str, Any]]) -> dict[str, Any]:
        hottest = None
        for temp in temps:
            value = _to_float(temp.get("celsius"))
            if value is not None:
                hottest = value if hottest is None else max(hottest, value)
        if hottest is None:
            synthetic_temp = 34.0 + _clamp(cpu_percent, 0.0, 100.0) * 0.42
            basis = f"CPU load {cpu_percent:.0f}%"
            temp_for_curve = synthetic_temp
        else:
            basis = f"hottest sensor {hottest:.1f} C plus CPU load {cpu_percent:.0f}%"
            temp_for_curve = hottest
        percent = max(self._fan_curve(temp_for_curve), 18.0 + _clamp(cpu_percent, 0.0, 100.0) * 0.45)
        percent = _clamp(percent, 15.0, 100.0)
        rpm = self.fan_min_rpm + (self.fan_max_rpm - self.fan_min_rpm) * (percent / 100.0)
        return {
            "name": "System fan estimate",
            "rpm": round(rpm),
            "percent": round(percent, 1),
            "source": "estimated",
            "estimated": True,
            "basis": basis,
        }

    @staticmethod
    def _fan_curve(temp_c: float) -> float:
        points = [(30.0, 15.0), (40.0, 22.0), (55.0, 38.0), (70.0, 68.0), (82.0, 92.0), (92.0, 100.0)]
        if temp_c <= points[0][0]:
            return points[0][1]
        for (left_temp, left_pct), (right_temp, right_pct) in zip(points, points[1:]):
            if temp_c <= right_temp:
                span = right_temp - left_temp
                ratio = (temp_c - left_temp) / span
                return left_pct + ratio * (right_pct - left_pct)
        return 100.0
