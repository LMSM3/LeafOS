#!/usr/bin/env python3
"""Keyboard state machine for TUI navigation and confirmed actions."""

from __future__ import annotations

from dataclasses import dataclass


PAGE_COUNT = 7


@dataclass
class RouterState:
    page_index: int = 0
    selection: int = 0
    scroll: int = 0
    follow: bool = True
    frozen: bool = False
    help_visible: bool = False
    command_buffer: str = ""
    command_mode: bool = False
    confirmation: str = ""
    confirmation_action: str = ""
    confirmation_task_id: str = ""
    pending_command: str = ""
    message: str = ""


def route_key(state: RouterState, key: str) -> str | None:
    """Update presentation state and return a requested controller action."""
    if state.confirmation:
        if key in {"ENTER", "\r", "\n"}:
            value = state.command_buffer.strip()
            expected = state.confirmation
            action = state.confirmation_action
            state.command_buffer = ""
            state.confirmation = ""
            state.confirmation_action = ""
            if value == expected:
                state.message = f"{action.replace('_', ' ')} request sent to the inlet controller."
                return action
            state.confirmation_task_id = ""
            state.message = "Confirmation did not match; no action taken."
            return None
        if key == "ESC":
            state.command_buffer = ""
            state.confirmation = ""
            state.confirmation_action = ""
            state.confirmation_task_id = ""
            state.message = "Stop cancelled."
            return None
        if key == "BACKSPACE":
            state.command_buffer = state.command_buffer[:-1]
        elif len(key) == 1 and key.isprintable():
            state.command_buffer += key
        return None

    if state.command_mode:
        if key in {"ENTER", "\r", "\n"}:
            command = state.command_buffer.strip()
            state.command_mode = False
            state.command_buffer = ""
            if command == ":stop":
                state.confirmation = "STOP"
                state.confirmation_action = "stop"
                state.message = "Type STOP and press Enter to stop the run: "
            else:
                state.pending_command = command
                state.message = "Sending command to the live project inlet."
                return "live_command"
            return None
        if key == "ESC":
            state.command_mode = False
            state.command_buffer = ""
        elif key == "BACKSPACE":
            state.command_buffer = state.command_buffer[:-1]
        elif len(key) == 1 and key.isprintable():
            state.command_buffer += key
        return None

    if key in {"TAB", "\t"}:
        state.page_index = (state.page_index + 1) % PAGE_COUNT
    elif key == "SHIFT_TAB":
        state.page_index = (state.page_index - 1) % PAGE_COUNT
    elif key in "1234567":
        state.page_index = int(key) - 1
    elif key in {"j", "DOWN"}:
        state.selection += 1
        state.scroll += 1
        state.follow = False
    elif key in {"k", "UP"}:
        state.selection = max(0, state.selection - 1)
        state.scroll = max(0, state.scroll - 1)
        state.follow = False
    elif key == " ":
        state.frozen = not state.frozen
        state.message = "View updates frozen; inference continues." if state.frozen else "Live view resumed."
    elif key == "l":
        state.follow = True
        state.frozen = False
        state.message = "Following live state."
    elif key == "?":
        state.help_visible = not state.help_visible
    elif key == "p":
        return "pause_toggle"
    elif key == "a":
        return "approve"
    elif key == "A":
        return "task_approve"
    elif key == "r":
        return "task_retry"
    elif key == "x":
        state.confirmation = "CANCEL"
        state.confirmation_action = "task_cancel"
        state.command_buffer = ""
        state.message = "Type CANCEL and press Enter to cancel the selected task: "
    elif key == "[":
        return "task_priority_up"
    elif key == "]":
        return "task_priority_down"
    elif key == "n":
        return "project_wizard"
    elif key == ":":
        state.command_mode = True
        state.command_buffer = ":"
    elif key == "q":
        return "quit"
    return None


def prompt(state: RouterState) -> str:
    if state.confirmation:
        return f"Type {state.confirmation} to confirm: {state.command_buffer}"
    if state.command_mode:
        return state.command_buffer
    return state.message
