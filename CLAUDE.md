Project state lives in PROJECT-LOG.jsonl (append-only event log). Replay it
at session start via the project-log skill; append events as you work.

Sub-area rules: research/CLAUDE.md (paper: numbers, style, verification),
backend/ (benchmark pipeline — see backend/runs/TRACKER.md for run inventory).
research/RESULTS-LOG.md is the paper claim->canonical-source map; DEFECTS.md
the measurement-defect ledger. PROJECT-LOG events reference these, never
duplicate them.
