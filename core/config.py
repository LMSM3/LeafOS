from __future__ import annotations

import configparser
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    root: Path
    model_dirs: tuple[Path, ...]
    llama_cli: str
    context: int
    gpu_layers: int | None

    @property
    def inventory_path(self) -> Path:
        return self.root / "logs" / "models.json"

    @property
    def state_path(self) -> Path:
        return self.root / "logs" / "state.json"

    @property
    def events_path(self) -> Path:
        return self.root / "logs" / "events.jsonl"

    @property
    def packs_dir(self) -> Path:
        return self.root / "packs"


def leaf_root() -> Path:
    override = os.environ.get("LEAFOS_HOME")
    return Path(override).expanduser().resolve() if override else Path(__file__).resolve().parents[1]


def load_settings(root: Path | None = None) -> Settings:
    root = (root or leaf_root()).resolve()
    config_path = Path(os.environ.get("LEAFOS_CONFIG", root / "config" / "leaf.conf")).expanduser()
    parser = configparser.ConfigParser()
    if not config_path.is_file():
        raise ConfigError(f"configuration is missing: {config_path}")
    try:
        parser.read(config_path, encoding="utf-8")
        backend = parser.get("runtime", "backend").strip()
        llama_cli = parser.get("runtime", "llama_cli").strip()
        context = parser.getint("runtime", "context")
        layers_raw = parser.get("runtime", "gpu_layers").strip().lower()
        path_values = parser.get("models", "paths")
    except (configparser.Error, KeyError, ValueError) as error:
        raise ConfigError(f"invalid configuration: {error}") from error
    if backend != "llama.cpp":
        raise ConfigError("runtime.backend must be llama.cpp")
    if not llama_cli:
        raise ConfigError("runtime.llama_cli cannot be empty")
    if not 256 <= context <= 1_048_576:
        raise ConfigError("runtime.context must be between 256 and 1048576")
    if layers_raw == "auto":
        gpu_layers = None
    else:
        try:
            gpu_layers = int(layers_raw)
        except ValueError as error:
            raise ConfigError("runtime.gpu_layers must be auto or a non-negative integer") from error
        if gpu_layers < 0:
            raise ConfigError("runtime.gpu_layers cannot be negative")
    raw_paths = [value.strip() for value in path_values.replace("\n", os.pathsep).split(os.pathsep)]
    resolved_paths = [Path(value).expanduser().resolve() for value in raw_paths if value]
    if os.environ.get("WSL_DISTRO_NAME"):
        windows_models = Path("/mnt/c/Users") / Path.home().name / ".leaf" / "models"
        if windows_models.is_dir() and windows_models not in resolved_paths:
            resolved_paths.append(windows_models)
    model_dirs = tuple(resolved_paths)
    if not model_dirs:
        raise ConfigError("models.paths must contain at least one directory")
    return Settings(root, model_dirs, llama_cli, context, gpu_layers)


def resolve_llama_cli(settings: Settings) -> Path | None:
    if settings.llama_cli.lower() == "auto":
        found = shutil.which("llama-cli") or shutil.which("llama-cli.exe")
        return Path(found).resolve() if found else None
    candidate = Path(settings.llama_cli).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    found = shutil.which(settings.llama_cli)
    return Path(found).resolve() if found else None
