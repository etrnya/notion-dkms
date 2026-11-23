"""V4 YouTube Blind-Spot Enricher (Local RTX 4060 ASR + Toggle Transcript + $0 Key Summary).

- Calls sibling `yt-transcript-cascade-mcp` engine locally (L1 yt-dlp -> L2 RTX 4060 faster-whisper).
- Strictly disables cloud Colab upload and paid Vertex AI.
- Writes full transcript into bottom gray Toggle Block (`AI 逐字稿(...)`) — idempotent & resumable.
- Optionally generates a 300-word key summary + 3~5 concepts at the top Callout block via $0 Free Tier.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from v4_config import (
    FreeTierLLMClient,
    NotionClientLight,
    TAG_WHITELIST,
    filter_whitelist_tags,
    get_runtime_env,
    parse_json_silentfix,
)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

YT_CASCADE_SRC = Path(__file__).resolve().parent.parent / "yt-transcript-cascade-mcp" / "src"
if str(YT_CASCADE_SRC) not in sys.path:
    sys.path.insert(0, str(YT_CASCADE_SRC))


def summarize_transcript(llm: FreeTierLLMClient, title: str, transcript: str) -> tuple[str, list[str]]:
    whitelist_str = "、".join(t for t in TAG_WHITELIST if t not in ("待補正文", "抓取失敗"))
    prompt = (
        "請針對以下 YouTube 影片逐字稿，用繁體中文提煉精華，只輸出合法 JSON：\n"
        f"標籤白名單（選 1～2 個）：[{whitelist_str}]\n"
        '輸出格式：{"summary": "【一句話結論】...\\n【3～5 個核心概念】\\n1. ...\\n2. ...\\n3. ...", "tags": ["標籤1"]}\n\n'
        f"影片標題：{title}\n"
        f"逐字稿節錄：\n{transcript[:12000]}\n"
    )
    raw, _ = llm.generate(prompt)
    parsed = parse_json_silentfix(raw)
    summary = str(parsed.get("summary", "")).strip()[:1900]
    tags = filter_whitelist_tags(parsed.get("tags", []), max_tags=2)
    return summary, tags


def run_youtube_enrichment(limit: int = 0, with_summary: bool = True, delay_sec: float = 2.0) -> dict[str, int]:
    from yt_transcript_cascade.application.orchestrator import CascadeOrchestrator
    from yt_transcript_cascade.domain.models import ExecutionMode, GetTranscriptInput, OutputFormat

    env = get_runtime_env()
    notion = NotionClientLight(env["NOTION_API_KEY"], env["NOTION_DATABASE_ID"])
    llm = FreeTierLLMClient(env) if with_summary else None
    orch = CascadeOrchestrator()

    stats = {"scanned": 0, "enriched": 0, "skipped": 0, "failed": 0}
    pages = notion.query_all_pages(
        filter_obj={
            "or": [
                {"property": "URL", "url": {"contains": "youtube.com/watch"}},
                {"property": "URL", "url": {"contains": "youtu.be/"}},
                {"property": "URL", "url": {"contains": "youtube.com/shorts/"}},
            ]
        },
        sorts=[{"timestamp": "created_time", "direction": "descending"}],
    )
    print(f"[INFO] Prefetched {len(pages)} YouTube pages.", flush=True)

    for page in pages:
        if limit > 0 and stats["enriched"] >= limit:
            return stats
        stats["scanned"] += 1
        pid = page["id"]
        pr = page["properties"]
        title = "".join(t.get("plain_text", "") for t in pr.get("Name", {}).get("title", [])).strip() or "無標題"
        url = pr.get("URL", {}).get("url") or ""

        try:
            existing = notion.get_blocks(pid, page_size=50)
            has_transcript = any(
                b.get("type") == "toggle"
                and "".join(x.get("plain_text", "") for x in b["toggle"].get("rich_text", [])).startswith("AI 逐字稿")
                for b in existing
            )
            if has_transcript:
                stats["skipped"] += 1
                continue

            t0 = time.time()
            req = GetTranscriptInput(
                url=url,
                languages=["zh-Hant", "zh-Hans", "zh", "en"],
                execution_mode=ExecutionMode.AUTO,
                enable_colab_fallback=False,
                allow_cloud_processing=False,
                output_format=OutputFormat.MARKDOWN,
                max_output_chars=120000,
                timeout_sec=360,
            )
            out = orch.get_transcript(req)
            if not out.get("ok"):
                stats["failed"] += 1
                print(f"[YT-FAIL] {title[:45]} -> {out.get('error', {}).get('code')}", flush=True)
                continue

            meta = out.get("result", {})
            content = out.get("rendered_text", "")
            tier = meta.get("tier_used", "")
            src = meta.get("source_type", "")
            eng = meta.get("engine_used") or "yt-dlp"
            dev = meta.get("device_used") or "cpu"
            lang = meta.get("source_language", "")
            header = f"AI 逐字稿（{tier} / {src} | {eng}@{dev} | 語言: {lang} | 字數: {len(content)}）"

            if with_summary and llm and len(content) > 200:
                try:
                    summary, tags = summarize_transcript(llm, title, content)
                    if summary:
                        notion.append_blocks(
                            pid,
                            [
                                {
                                    "object": "block",
                                    "type": "callout",
                                    "callout": {
                                        "icon": {"type": "emoji", "emoji": "💡"},
                                        "color": "blue_background",
                                        "rich_text": [{"type": "text", "text": {"content": summary[:1900]}}],
                                    },
                                }
                            ],
                        )
                        notion.patch_page_properties(
                            pid,
                            {
                                "AI 摘要": {"rich_text": [{"type": "text", "text": {"content": summary[:1900]}}]},
                                "AI 標籤": {"multi_select": [{"name": t} for t in tags]},
                                "AI 已處理": {"checkbox": True},
                            },
                        )
                        time.sleep(delay_sec)
                except Exception as se:
                    print(f"  [WARN] Summary skipped for {title[:30]}: {se}", flush=True)

            notion.append_toggle_text(pid, "AI 逐字稿", header, content)
            elapsed = round(time.time() - t0, 1)
            stats["enriched"] += 1
            print(f"[YT-OK #{stats['enriched']}] ({tier}, {len(content)} chars, {elapsed}s) {title[:45]}", flush=True)
        except Exception as e:
            stats["failed"] += 1
            print(f"[YT-ERR] {title[:45]} -> {e}", flush=True)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="V4 YouTube Blind-Spot Enricher (Local RTX 4060)")
    parser.add_argument("--limit", type=int, default=0, help="Max videos to enrich (0 = all)")
    parser.add_argument("--no-summary", action="store_true", help="Skip $0 LLM summary (0-token transcript only)")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay seconds after summary LLM call")
    args = parser.parse_args()
    stats = run_youtube_enrichment(limit=args.limit, with_summary=not args.no_summary, delay_sec=args.delay)
    print(f"\n=== YOUTUBE ENRICH V4 DONE === {stats}")


if __name__ == "__main__":
    main()
