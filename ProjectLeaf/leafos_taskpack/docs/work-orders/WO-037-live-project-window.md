# WO-037: Live Project Window And Stack Finalization

Machine-readable authority: `WO-037-live-project-window.json`

## Objective

Finalize the top-level operator experience by cleaning obsolete stack seams and providing one easy active window for initializing, inspecting, improving, and repeatedly advancing any project with the local stack.

## Design

`leafctl live PATH` is the canonical entry. The project may be an established codebase, a documentation-only directory, or a three-file README/skeleton/JSON seed. Objectives and specialized commands are optional. Project facts drive a bounded generated work order and every later improvement uses the existing typed inlet.

## Acceptance

- One command opens or reattaches a project and enters the TUI.
- Python and native TUI command windows support `:project`, `:new`, `:improve`, `:again`, and natural-language objectives.
- A missing objective is derived from current project state.
- Repeated improvements remain ordered in one durable run and retain CPU validation.
- A new generic project begins from exactly README, skeleton, and JSON intent.
- Existing projects receive no control files during intake.
- Renderer commands use authenticated typed transport and cannot execute arbitrary shell input.
- Provider proposals remain subordinate to CPU execution, validation, journaling, and checkpoints.
- Dead placeholder paths are removed without removing test-only compatibility fixtures that still provide contract coverage.
