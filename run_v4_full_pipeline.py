"""V4 Master Sequential Full-Batch Runner (Option B Overnight / Background Pipeline).

Runs all 3 Second-Brain enrichment stages sequentially to avoid GPU/RAM/Notion rate-limit collisions:
  Stage 1: batch_processor_v4.py (all unprocessed cards, $0 Free Tier AI Studio <-> NVIDIA NIM)
  Stage 2: enrich_youtube.py (all remaining YouTube cards, local RTX 4060 ASR + $0 summary)
  Stage 3: enrich_ocr.py (all remaining image cards, local offline RapidOCR, $0)
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
YT_VENV_PYTHON = ROOT.parent / "yt-transcript-cascade-mcp" / ".venv" / "Scripts" / "python.exe"
DKMS_VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


def run_stage(name: str, cmd: list[str]) -> int:
    print(f"\n{'='*60}\n🚀 START {name}\n   CMD: {' '.join(cmd)}\n{'='*60}", flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT))
    elapsed = round((time.time() - t0) / 60, 2)
    print(f"\n🏁 END {name} | exit_code={proc.returncode} | elapsed={elapsed} min", flush=True)
    return proc.returncode


def main() -> None:
    py_ocr = str(DKMS_VENV_PYTHON) if DKMS_VENV_PYTHON.exists() else sys.executable
    py_yt = str(YT_VENV_PYTHON) if YT_VENV_PYTHON.exists() else sys.executable

    rc1 = run_stage("Stage 1: 810 Unprocessed Cards ($0 Free Tier Summary + 18-Tag Whitelist)", [py_ocr, "batch_processor_v4.py", "--delay", "2.2"])
    rc2 = run_stage("Stage 2: Remaining YouTube Cards (Local RTX 4060 ASR + Key Summary)", [py_yt, "enrich_youtube.py", "--delay", "2.2"])
    rc3 = run_stage("Stage 3: Full-DB Image Offline OCR (Local RapidOCR, $0)", [py_ocr, "enrich_ocr.py"])

    print(f"\n=== V4 FULL PIPELINE FINISHED === rc1={rc1}, rc2={rc2}, rc3={rc3}", flush=True)
    if any(rc != 0 for rc in (rc1, rc2, rc3)):
        sys.exit(1)


if __name__ == "__main__":
    main()
