"""V4 Offline Image OCR Enricher (RapidOCR ONNX, $0 / 0 LLM Token, Resumable Checkpoint).

- Scans Notion database for cards containing `image` blocks.
- Runs local offline `rapidocr-onnxruntime` (PaddleOCR PP-OCRv4/v5 ONNX).
- Appends extracted text into a bottom gray Toggle Block (`圖片 OCR 文字(...)`).
- Saves cursor & processed page IDs in `checkpoints/ocr_checkpoint.json` for safe resume.
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import time
import urllib.request
from typing import Any

from PIL import Image
from rapidocr_onnxruntime import RapidOCR

from v4_config import CHECKPOINTS_DIR, NotionClientLight, get_runtime_env

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def download_image(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except Exception:
        return None


def load_checkpoint() -> set[str]:
    cp_file = CHECKPOINTS_DIR / "ocr_scanned_ids.json"
    if cp_file.exists():
        try:
            return set(json.loads(cp_file.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_checkpoint(scanned_ids: set[str]) -> None:
    CHECKPOINTS_DIR.mkdir(parents=True, exist_ok=True)
    cp_file = CHECKPOINTS_DIR / "ocr_scanned_ids.json"
    tmp = cp_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(sorted(scanned_ids)), encoding="utf-8")
    tmp.replace(cp_file)


def run_ocr_enrichment(limit_enriched: int = 0) -> dict[str, int]:
    env = get_runtime_env()
    notion = NotionClientLight(env["NOTION_API_KEY"], env["NOTION_DATABASE_ID"])
    ocr = RapidOCR()
    scanned_ids = load_checkpoint()

    stats = {"scanned": 0, "skipped_cp": 0, "enriched": 0, "images_ok": 0, "chars": 0, "errors": 0}
    cursor = None

    while True:
        body: dict[str, Any] = {
            "page_size": 50,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        }
        if cursor:
            body["start_cursor"] = cursor
        res = notion.query_database(body)
        pages = res.get("results", [])
        if not pages:
            break

        for page in pages:
            if limit_enriched > 0 and stats["enriched"] >= limit_enriched:
                save_checkpoint(scanned_ids)
                return stats
            pid = page["id"]
            if pid in scanned_ids:
                stats["skipped_cp"] += 1
                continue

            stats["scanned"] += 1
            title = "".join(t.get("plain_text", "") for t in page["properties"].get("Name", {}).get("title", [])).strip() or "無標題"
            try:
                blocks = notion.get_blocks(pid, page_size=60)
                has_ocr = any(
                    b.get("type") == "toggle"
                    and "".join(x.get("plain_text", "") for x in b["toggle"].get("rich_text", [])).startswith("圖片 OCR 文字")
                    for b in blocks
                )
                if has_ocr:
                    scanned_ids.add(pid)
                    continue

                img_urls: list[str] = []
                for b in blocks:
                    if b.get("type") == "image":
                        io_obj = b["image"]
                        it = io_obj.get("type")
                        u = io_obj.get(it, {}).get("url", "") if it else ""
                        if u:
                            img_urls.append(u)

                if not img_urls:
                    scanned_ids.add(pid)
                    if stats["scanned"] % 50 == 0:
                        save_checkpoint(scanned_ids)
                        print(f"[OCR-SCAN] scanned={stats['scanned']} enriched={stats['enriched']} chars={stats['chars']}")
                    continue

                page_texts: list[str] = []
                ok_cnt = 0
                for img_i, u in enumerate(img_urls, 1):
                    raw = download_image(u)
                    if not raw:
                        continue
                    try:
                        img = Image.open(io.BytesIO(raw)).convert("RGB")
                        ocr_res, _ = ocr(img)
                        if ocr_res:
                            lines = [item[1].strip() for item in ocr_res if item[1] and item[1].strip()]
                            if lines:
                                ok_cnt += 1
                                stats["images_ok"] += 1
                                page_texts.append(f"【圖片 {img_i}】\n" + "\n".join(lines))
                    except Exception:
                        continue

                combined = "\n\n".join(page_texts)
                if combined:
                    header = f"圖片 OCR 文字（RapidOCR 離線辨識 | 成功 {ok_cnt}/{len(img_urls)} 張 | 共 {len(combined)} 字）"
                    notion.append_toggle_text(pid, "圖片 OCR 文字", header, combined)
                    stats["enriched"] += 1
                    stats["chars"] += len(combined)
                    print(f"[OCR-OK #{stats['enriched']}] ({ok_cnt}/{len(img_urls)} imgs, {len(combined)} chars) {title[:42]}")

                scanned_ids.add(pid)
                if stats["scanned"] % 20 == 0:
                    save_checkpoint(scanned_ids)
                time.sleep(0.2)
            except Exception as e:
                stats["errors"] += 1
                print(f"[OCR-ERR] {title[:40]} -> {e}")
                time.sleep(1.0)

        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    save_checkpoint(scanned_ids)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="V4 Offline Image OCR Enricher (RapidOCR, $0)")
    parser.add_argument("--limit", type=int, default=0, help="Max image pages to enrich (0 = scan all)")
    args = parser.parse_args()
    stats = run_ocr_enrichment(limit_enriched=args.limit)
    print(f"\n=== OCR ENRICH V4 DONE === {stats}")


if __name__ == "__main__":
    main()
