# Copilot Instructions

## Project Guidelines
- Architectural boundary rule: if code directly touches local AI (ollama, local LLM invocation), it belongs in leafOS (`C:\R\ProjectLeaf\leafos_taskpack\`), not FlowerOS (`C:\R\FlowerOS\`). FlowerOS can health-check/probe for ollama, but must not directly invoke it.