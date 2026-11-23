"""V4 Second-Brain Batch Processor ($0 Free Tier Only, 18-Category Whitelist).

Upgrades from V3:
- Drops subjective `可信度` and `可執行性` scores.
- Enforces the fixed 18-category `TAG_WHITELIST` (1~2 tags per card).
- Deterministically catches Facebook login walls (`抓取失敗`) & empty cards (`待補正文`) at 0 LLM tokens.
- Uses strictly $0 Free Tier channels (Google AI Studio <-> NVIDIA NIM), NEVER Vertex AI Postpaid.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from v4_config import (
    FreeTierLLMClient,
    NotionClientLight,
    TAG_WHITELIST,
    filter_whitelist_tags,
    get_runtime_env,
    is_login_wall,
    parse_json_silentfix,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def build_prompt(title: str, url: str, body: str) -> str:
    whitelist_str = "、".join(t for t in TAG_WHITELIST if t not in ("待補正文", "抓取失敗"))
    return (
        "你是嚴謹的繁體中文知識庫索引員。請閱讀以下筆記並只輸出合法 JSON（不要加任何說明文字）。\n"
        f"可用標籤白名單（只能從中挑選 1～2 個，嚴禁自造新標籤）：[{whitelist_str}]\n\n"
        "輸出格式：\n"
        '{"summary": "【一句話結論】...\\n【核心重點】\\n1. ...\\n2. ...", "tags": ["標籤1"]}\n\n'
        f"標題：{title}\n"
        f"網址：{url or '無'}\n"
        f"內文：\n{body[:3500]}\n"
    )


def get_page_title(page: dict[str, Any]) -> str:
    title_objs = page.get("properties", {}).get("Name", {}).get("title", [])
    return "".join(t.get("plain_text", "") for t in title_objs).strip() or "無標題"


def run_batch(limit: int = 0, delay_sec: float = 2.0, dry_run: bool = False) -> dict[str, int]:
    env = get_runtime_env()
    notion = NotionClientLight(env["NOTION_API_KEY"], env["NOTION_DATABASE_ID"])
    llm = FreeTierLLMClient(env)

    stats = {"processed": 0, "llm_ok": 0, "login_wall": 0, "empty_body": 0, "errors": 0}
    pages = notion.query_all_pages(
        filter_obj={"property": "AI 已處理", "checkbox": {"equals": False}},
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    print(f"[INFO] Prefetched {len(pages)} unprocessed pages.", flush=True)

    for page in pages:
        if limit > 0 and stats["processed"] >= limit:
            return stats
        pid = page["id"]
        title = get_page_title(page)
        url = page.get("properties", {}).get("URL", {}).get("url") or ""

        try:
            text = notion.extract_page_text(pid, include_toggles=True)
            # 1. Zero-token deterministic pre-filters
            if is_login_wall(title, text):
                summary = "【抓取失敗】原網頁為登入牆或無效頁面，建議忽略或重新擷取。"
                tags = ["抓取失敗"]
                provider = "rule:login_wall"
                stats["login_wall"] += 1
            elif len(text.strip()) < 40:
                summary = "【待補正文】目前僅有標題/網址，尚無足夠正文可供提煉。"
                tags = ["待補正文"]
                provider = "rule:empty_body"
                stats["empty_body"] += 1
            else:
                prompt = build_prompt(title, url, text)
                raw, provider = llm.generate(prompt)
                parsed = parse_json_silentfix(raw)
                summary = str(parsed.get("summary", "")).strip()[:1900]
                tags = filter_whitelist_tags(parsed.get("tags", []), max_tags=2)
                if not summary:
                    raise ValueError("Empty summary from LLM")
                stats["llm_ok"] += 1
                time.sleep(delay_sec)

            if not dry_run:
                notion.patch_page_properties(
                    pid,
                    {
                        "AI 摘要": {"rich_text": [{"type": "text", "text": {"content": summary}}]},
                        "AI 標籤": {"multi_select": [{"name": t} for t in tags]},
                        "AI 已處理": {"checkbox": True},
                    },
                )

            stats["processed"] += 1
            print(f"[{stats['processed']}] ({provider}) {tags} | {title[:42]}", flush=True)
        except Exception as e:
            stats["errors"] += 1
            print(f"[ERR] {title[:40]} -> {e}", flush=True)
            time.sleep(2.0)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="V4 Second-Brain Batch Processor ($0 Free Tier)")
    parser.add_argument("--limit", type=int, default=0, help="Max cards to process (0 = all unprocessed)")
    parser.add_argument("--delay", type=float, default=2.2, help="Delay seconds between LLM calls")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Notion")
    args = parser.parse_args()
    stats = run_batch(limit=args.limit, delay_sec=args.delay, dry_run=args.dry_run)
    print(f"\n=== BATCH V4 DONE === {stats}")


if __name__ == "__main__":
    main()
