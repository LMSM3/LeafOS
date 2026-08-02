from __future__ import annotations

from typing import Iterable

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.prompt import Confirm, Prompt
except Exception:  # pragma: no cover - fallback for extremely cursed installs
    Console = None
    Panel = None
    Table = None
    Confirm = None
    Prompt = None


class UI:
    def __init__(self) -> None:
        self.console = Console() if Console else None

    def print(self, *args, **kwargs) -> None:
        if self.console:
            self.console.print(*args, **kwargs)
        else:
            print(*args)

    def banner(self) -> None:
        text = (
            "☠ Leaf Model Puller ☠\n"
            "Safe, allowlisted GGUF downloader for local-model tinkering.\n"
            "No arbitrary shell execution. No mystery repo roulette. Tragic, but responsible."
        )
        if self.console and Panel:
            self.console.print(Panel.fit(text, title="Project New Leaf", subtitle="human-proof-ish"))
        else:
            print(text)

    def confirm(self, message: str, default: bool = False) -> bool:
        if Confirm:
            return bool(Confirm.ask(message, default=default))
        suffix = "Y/n" if default else "y/N"
        answer = input(f"{message} [{suffix}] ").strip().lower()
        if not answer:
            return default
        return answer in {"y", "yes"}

    def prompt(self, message: str, default: str | None = None) -> str:
        if Prompt:
            return str(Prompt.ask(message, default=default))
        suffix = f" [{default}]" if default is not None else ""
        answer = input(f"{message}{suffix}: ").strip()
        return answer or (default or "")

    def choice(self, message: str, choices: Iterable[str], default: str | None = None) -> str:
        choices = list(choices)
        if Prompt:
            return str(Prompt.ask(message, choices=choices, default=default or choices[0]))
        while True:
            answer = self.prompt(f"{message} ({'/'.join(choices)})", default=default or choices[0])
            if answer in choices:
                return answer
            self.print(f"Invalid choice. Pick one of: {', '.join(choices)}")
