# Automatic Overnight Reporting

The model-free reporting supervisor generates `LIVE_REPORT.html` and a mandatory `MONDAY_AFFECT_<timestamp>.pdf` at start and every 30 minutes:

```powershell
pwsh -File bin/leaf-sandbox.ps1 report --watch --interval-minutes 30
```

Each PDF contains a labeled 16×16 heatmap of 16 explicit affect/runtime channels across the 16 most recent journaled slices. Inputs are restricted to `journal.lje`, `telemetry.jsonl`, and `actions.jsonl`; no model is started and no hidden reasoning is consumed.

A report event records the PDF path, SHA-256, viridis palette, normalized scale, generation result, and forced-open result. Chrome headless PDF failure is a blocking report-cycle failure. Browser-open failure is journaled as recoverable.

Set `LEAF_CHROME` to the Chrome executable when auto-discovery is insufficient. Use `--no-open` to suppress the interactive browser attempt while still requiring PDF generation.

Improve native linux and shell version re-tieins , and prepare for mac versioning so 3 total.