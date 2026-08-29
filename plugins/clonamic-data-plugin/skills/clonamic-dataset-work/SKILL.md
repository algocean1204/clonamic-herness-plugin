---
name: clonamic-dataset-work
description: "Dataset / Hugging Face pipeline procedure — pre-flight disk guard, hf CLI conventions, streaming/chunked processing, JSONL validation, upload checklist. Use for any dataset build, clean, convert, finetuning-data, or HF Hub task (데이터셋, 파인튜닝 데이터, HF 업로드)."
---

# Dataset Work

Procedure for dataset pipelines and Hugging Face Hub work. History: a full disk once triggered macOS jetsam kills mid-pipeline — the pre-flight is not optional.

## 1. Pre-flight (always)

- Disk: `df -g /` — require **≥ 30G free + estimated output size**. If low, stop and clean first (APFS snapshots are the usual culprit: `tmutil listlocalsnapshots /`).
- Workspace: use the project dir or `~/Documents/DataSet/` — never `/tmp` for large intermediates.
- Estimate output size before generating (rows × avg record size); state the estimate.

## 2. Hugging Face connection

- Already authenticated: `hf` CLI (HF_TOKEN in env) + claude.ai HF MCP. **Never re-login or ask for tokens.**
- Reads: `hf download <repo> --repo-type dataset [--include ...]` or MCP search tools. Writes: `hf upload <repo> <local> --repo-type dataset`. New repo: `hf repo create <name> --repo-type dataset --private`.

## 3. Processing discipline

- Stream line-by-line or in chunks; never load a whole large dataset into RAM.
- Checkpoint every N chunks to a resumable intermediate file — a killed run must resume, not restart.
- Delete intermediates as soon as the next stage is verified.
- Ladder applies: stdlib `json`/`csv` first; pandas/pyarrow only when the operation needs it.

## 4. Validation gate (before any upload / handoff)

- Every JSONL line parses; schema keys consistent across a sampled 1% + first/last 100 lines.
- Record counts: in == out (± documented dedup/filter delta — print the numbers).
- Eyeball 5–10 random records for content sanity (encoding, truncation, label correctness).
- UTF-8 encoding confirmed (`file` + a non-ASCII sample check).

## 5. Upload checklist

- Default **private** repo; minimal dataset card (source, size, schema, license).
- After upload: verify with the HF MCP repo-details tool (file count + sizes match local) or the file list printed by `hf upload` itself. Never invent CLI flags — check `hf <cmd> --help` before using an unfamiliar option.

## Failure playbook

Disk full mid-run → stop writes immediately, clean snapshots/intermediates, resume from last checkpoint. OOM → halve chunk size. Upload interrupted → `hf upload` is resumable; re-run same command.
