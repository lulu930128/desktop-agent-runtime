# Kuro Study Tools

Local read-only study scanners and progress trackers for Kuro.

Current first version:

- Read the workbook from `KURO_STUDY_VOCAB_FILE`, or from
  `Open-LLM-VTuber/private/study/vocab.xlsx` by default
- Build a stable vocab index
- Keep learning progress outside the source workbook
- Generate a daily study snapshot for Dashboard / pet integration

Private outputs are written under:

```text
Open-LLM-VTuber/private/study/
```

That directory is ignored by Git through `Open-LLM-VTuber/.gitignore`.

## Commands

```powershell
$env:KURO_STUDY_VOCAB_FILE = "C:\path\to\vocab.xlsx"
python Open-LLM-VTuber/local_mcp/study_tools/vocab_tracker.py scan
python Open-LLM-VTuber/local_mcp/study_tools/vocab_tracker.py today
python Open-LLM-VTuber/local_mcp/study_tools/vocab_tracker.py stats
python Open-LLM-VTuber/local_mcp/study_tools/vocab_tracker.py mark --word-id "N3:..." --result correct
python Open-LLM-VTuber/local_mcp/study_tools/vocab_quiz_ui.py
```

Use `--help` on each command for options.

If `vocab_quiz_ui.py` is copied outside this repository, set
`KURO_OPEN_LLM_ROOT`, `KURO_STUDY_TRACKER_PATH`, or `KURO_STUDY_STATE_DIR` so it
can locate the tracker and private progress files.
