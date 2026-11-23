"""V4 Notion -> ZeroRAG Markdown Exporter.

Exports clean, login-wall-filtered Notion notes (including YouTube transcripts and OCR text)
into a single structured Markdown file under `exports/` (gitignored) for ZeroRAG semantic search.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from v4_config import EXPORTS_DIR, NotionClientLight, get_runtime_env, is_login_wall

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def export_notes(limit: int = 100, tag_filter: str | None = None, output_name: str | None = None) -> Path:
    env = get_runtime_env()
    notion = NotionClientLight(env["NOTION_API_KEY"], env["NOTION_DATABASE_ID"])
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    exported = 0
    skipped = 0
    parts = [
        f"# Notion 第二大腦精選匯出（ZeroRAG 語意檢索用）\n\n",
        f"> 篩選標籤：`{tag_filter or '全部'}`｜已自動過濾空白頁與登入牆\n\n",
    ]
    cursor = None

    while exported < limit:
        body: dict[str, Any] = {
            "page_size": 50,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        }
        if tag_filter:
            body["filter"] = {"property": "AI 標籤", "multi_select": {"contains": tag_filter}}
        if cursor:
            body["start_cursor"] = cursor

        res = notion.query_database(body)
        pages = res.get("results", [])
        if not pages:
            break

        for p in pages:
            if exported >= limit:
                break
            pid = p["id"]
            notion_url = p.get("url", f"https://www.notion.so/{pid.replace('-', '')}")
            pr = p["properties"]
            title = "".join(t.get("plain_text", "") for t in pr.get("Name", {}).get("title", [])).strip() or "無標題"
            src_url = pr.get("URL", {}).get("url") or ""
            summ = "".join(t.get("plain_text", "") for t in pr.get("AI 摘要", {}).get("rich_text", [])).strip()
            tags = [t["name"] for t in pr.get("AI 標籤", {}).get("multi_select", [])]
            created = p.get("created_time", "")[:10]

            if "抓取失敗" in tags or is_login_wall(title, summ):
                skipped += 1
                continue

            text = notion.extract_page_text(pid, include_toggles=True)
            if len(text.strip()) < 60 or is_login_wall(title, text):
                skipped += 1
                continue

            parts.append(
                f"## {title}\n"
                f"- **建立日期**: {created}\n"
                f"- **Notion 連結**: {notion_url}\n"
                f"- **原始來源**: {src_url or '無'}\n"
                + (f"- **AI 標籤**: {', '.join(tags)}\n" if tags else "")
                + (f"- **AI 摘要**: {summ}\n" if summ else "")
                + f"\n{text}\n\n---\n\n"
            )
            exported += 1

        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    fname = output_name or f"notion_zerorag_{tag_filter or 'all'}_{exported}.md"
    out_path = EXPORTS_DIR / fname
    content = "".join(parts)
    out_path.write_text(content, encoding="utf-8")
    print(f"[EXPORT-OK] exported={exported}, skipped={skipped}, file={out_path} ({round(len(content.encode('utf-8'))/1024, 1)} KB)")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export clean Notion notes to Markdown for ZeroRAG")
    parser.add_argument("--limit", type=int, default=100, help="Max clean notes to export")
    parser.add_argument("--tag", type=str, default=None, help="Optional AI 標籤 whitelist filter")
    parser.add_argument("--out", type=str, default=None, help="Optional output filename under exports/")
    args = parser.parse_args()
    export_notes(limit=args.limit, tag_filter=args.tag, output_name=args.out)


if __name__ == "__main__":
    main()
