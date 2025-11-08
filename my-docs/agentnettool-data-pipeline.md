# AgentNetTool Data Pipeline Handoff

_Last updated: 2025-11-08_

## Context Snapshot
- **Repo**: `OpenCUA`
- **Working dir**: `data/data-process/`
- **Goal**: take raw AgentNetTool recordings and produce CoT-ready assets (JSONL + PNG frames) compatible with `data/cot-generate`.
- **Status**: End-to-end export script completed (`src/standardized_to_cot_input.py`), assets regenerated under `datasets/cot_input.jsonl` and `datasets/cot_images/`.
- **Pending**: decide whether to propagate human-authored action text into downstream datasets (see notes below).

## Timeline & Actions

### 1. Environment & Data Prep
- Installed Python 3.11 venv inside `data/data-process/.venv` (`python3.11 -m venv .venv` then `source .venv/bin/activate`).
- Ran `pip install -r requirements.txt` (includes `opencv-python`, `pydantic`, `pyautogui>=0.9.54`, etc.).
- Symlinked local AgentNetTool recordings into `datasets/raw/`:
  - `~/Documents/AgentNetRecordings/*` → `data/data-process/datasets/raw/` (three runs linked: `2ab32727...`, `734178cb...`, `f914922c...`).
- Cleared old outputs (`datasets/raw/*` etc.) before processing.

### 2. Baseline Pipeline Execution
- Ran stage scripts:
  ```bash
  ./scripts/extract_raw.sh -1      # raw events + frames → datasets/raw_trajs/
  ./scripts/raw_to_standardized.sh -1  # standardized trajectories → datasets/standardized/
  ```
- Verified outputs:
  - `datasets/raw_trajs/*.json` (contains textual `action` fields + base64 screen captures).
  - `datasets/standardized/*.json` (Pydantic `Trajectory` objects; action label stored as `"instruction"`).

### 3. Custom Export Script
- Created `data/data-process/src/standardized_to_cot_input.py` (invoked via `python -m src.standardized_to_cot_input`).
- Responsibilities:
  1. Iterate standardized trajectories.
  2. Decode embedded screenshots to PNG (handles `data:image/png;base64,...` URIs and malformed padding/whitespace).
  3. Build CoT input JSONL with step-by-step `pyautogui...` code (via `PyAutoGUIAction.to_command()` / `ComputerAction.to_command()`).
  4. Sanitize image subfolder names (derived from `example_id`).
  5. Optionally (commented in code) provide a hook to keep human-authored `instruction` strings.
- Summary of tricky bits implemented:
  - **Base64 cleanup**: remove `data:` prefix, strip illegal chars, trim until `(len % 4 != 1)`, pad with `=`.
  - **Sanitized folders**: `sanitize_name()` ensures filesystem-friendly directory names.
  - **Overwrite safety**: `--overwrite` flag clears previous JSONL and PNGs.
  - CLI defaults: standardized dir = `datasets/standardized`, output = `datasets/cot_input.jsonl`, frames = `datasets/cot_images/`.

### 4. Command to Regenerate Assets
Run from `data/data-process/` (after activating venv):
```bash
python -m src.standardized_to_cot_input --overwrite
```
Outputs now located at:
- `datasets/cot_input.jsonl`
- `datasets/cot_images/<example_id>/0000.png ...`

Validated with macOS `Preview` + `file` command (PNG headers recognized).

### 5. Manual Validation
- Spot-checked JSONL entries.
- Confirmed first task: `20241106114028_e0599885_gmail.com_2c05b...` includes 15 steps with matching frames.
- Confirmed second task `f914922c-5533-4031-8dc8-c42179ba4bf8` (the one with renamed action label) retains the text inside standardized JSON (`"instruction": "Click on the google search bar"`).
- Observed that the final `cot_input.jsonl` currently omits that instruction; see next section.

## Key Learnings & Open Questions

### Human-Authored Action Text
- AgentNetTool UI allows renaming steps (e.g., "Click on the google search bar").
- Pipeline currently keeps the string through `raw_trajs` → `standardized` (as `instruction`).
- Export script discards it because the CoT generator historically synthesizes its own prose.
- **If we want to keep it**, modify `trajectory.append(...)` in `standardized_to_cot_input.py` to include `item.get("instruction")` alongside `code`—just ensure the downstream CoT script tolerates the extra field.

### Data URI Edge Case
- Some standardized files embed screenshots as full data URIs; ignoring the prefix causes corrupt frames. Fix implemented.

### File Organization
- `datasets/cot_images` now has per-recording folders using sanitized example IDs.
- `cot_input.jsonl` references those relative paths.

### Git Status Snapshot
- New untracked outputs: `datasets/cot_images/`, `datasets/cot_input.jsonl`.
- New script tracked: `src/standardized_to_cot_input.py`.
- Some original raw recording files show as deleted because they were symlinked (safe to ignore or restore).

## How to Pick Up
1. **Review** `data/data-process/src/standardized_to_cot_input.py` for any tweaks (e.g., keep human instructions).
2. **Regenerate** after changes: activate venv, rerun `python -m src.standardized_to_cot_input --overwrite`.
3. **Feed CoT generator**:
   - `traj_path` → `datasets/cot_input.jsonl`
   - `image_folder` → `datasets/cot_images`
   - Ensure required API key (`API_KEY`) is exported before invoking `data/cot-generate/gen_cot.py`.
4. **If adding more recordings**: symlink/copy into `datasets/raw/`, re-run `extract_raw.sh` + `raw_to_standardized.sh`, then regenerate CoT inputs.

## Troubleshooting Checklist
- `Preview` error opening PNG → rerun exporter (should use fixed base64 cleaning).
- Missing frames or JSON lines → check Standardized JSON for `image_observation` entries (some steps may lack screenshots; exporter will skip steps without them).
- Instruction text missing downstream → add to JSONL as described above.

## Useful Commands
```bash
# Activate environment
cd data/data-process
source .venv/bin/activate

# Rebuild raw/standardized (optional)
./scripts/extract_raw.sh -1
./scripts/raw_to_standardized.sh -1

# Export CoT input
python -m src.standardized_to_cot_input --overwrite

# Inspect JSONL
head -n 5 datasets/cot_input.jsonl | jq

# Validate PNG headers
file datasets/cot_images/<folder>/0000.png
```

## Next Steps (suggested)
- Decide whether to persist human-curated action descriptions in final JSONL/COT outputs.
- Integrate exporter into automated pipeline (e.g., add `make` target or bash script wrapper).
- Run `data/cot-generate/gen_cot.py` with newly generated assets to produce CoT narratives.

_This document should give the next agent all necessary context to keep the pipeline running or extend it further._
