"""V4 「AI 當老師」On-Demand Topic Synthesizer (Evidence-First Structured Knowledge Crystal).

Replaces V3 random blind-sampling with user-directed topic synthesis:
- Retrieves ONLY notes matching a user-specified whitelist tag or keyword (including OCR & YT transcripts).
- Outputs a structured Markdown Case Table / Knowledge Crystal:
  Pain Point -> Solution & Toolchain -> Key Insight / Limitation -> Original Notion URL.
- Strictly uses $0 Free Tier channels (Google AI Studio <-> NVIDIA NIM), NEVER Vertex AI Postpaid.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import Any

from v4_config import EXPORTS_DIR, FreeTierLLMClient, NotionClientLight, get_runtime_env, is_login_wall

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def collect_topic_notes(
    notion: NotionClientLight,
    topic: str,
    tag: str | None = None,
    max_notes: int = 12,
) -> list[dict[str, str]]:
    notes: list[dict[str, str]] = []
    cursor = None
    scanned = 0

    while len(notes) < max_notes and scanned < 300:
        body: dict[str, Any] = {
            "page_size": 50,
            "sorts": [{"timestamp": "created_time", "direction": "descending"}],
        }
        if tag:
            body["filter"] = {"property": "AI 標籤", "multi_select": {"contains": tag}}
        if cursor:
            body["start_cursor"] = cursor

        res = notion.query_database(body)
        pages = res.get("results", [])
        if not pages:
            break

        for p in pages:
            scanned += 1
            if len(notes) >= max_notes:
                break
            pid = p["id"]
            notion_url = p.get("url", f"https://www.notion.so/{pid.replace('-', '')}")
            pr = p["properties"]
            title = "".join(t.get("plain_text", "") for t in pr.get("Name", {}).get("title", [])).strip() or "無標題"
            summ = "".join(t.get("plain_text", "") for t in pr.get("AI 摘要", {}).get("rich_text", [])).strip()
            tags = [t["name"] for t in pr.get("AI 標籤", {}).get("multi_select", [])]

            if "抓取失敗" in tags or is_login_wall(title, summ):
                continue

            if not tag and topic.lower() not in f"{title}\n{summ}\n{' '.join(tags)}".lower():
                continue

            text = notion.extract_page_text(pid, include_toggles=True)
            if len(text.strip()) < 80 or is_login_wall(title, text):
                continue

            notes.append({
                "title": title,
                "notion_url": notion_url,
                "summary": summ,
                "excerpt": text[:2000],
            })

        if not res.get("has_more"):
            break
        cursor = res.get("next_cursor")

    return notes


def ask_teacher(topic: str, tag: str | None = None, max_notes: int = 12) -> Path:
    env = get_runtime_env()
    notion = NotionClientLight(env["NOTION_API_KEY"], env["NOTION_DATABASE_ID"])
    llm = FreeTierLLMClient(env)

    notes = collect_topic_notes(notion, topic=topic, tag=tag, max_notes=max_notes)
    if not notes:
        raise RuntimeError(f"找不到符合主題 '{topic}'（標籤: {tag}）的有效筆記。")

    material = "\n\n".join(
        f"### 素材 {i}\n- 標題：{n['title']}\n- Notion 連結：{n['notion_url']}\n- 摘要：{n['summary']}\n- 內文節錄：\n{n['excerpt']}"
        for i, n in enumerate(notes, 1)
    )

    prompt = (
        f"你是使用者的專屬「AI 老師」。請嚴格根據以下 {len(notes)} 篇來自使用者個人第二大腦的真實筆記，針對主題「{topic}」提煉成一份【結構化知識晶體與實戰案例手冊】（繁體中文 Markdown）。\n"
        "嚴格規則：\n"
        "1. 絕不腦補或編造未出現在素材中的案例或網址。\n"
        "2. 必須先輸出一個總覽對照表：`| 案例/觀念 | 解決的痛點 | 核心工具或方法 | 適用限制/提醒 | 原始 Notion 連結 |`。\n"
        "3. 接著歸納 3～5 條可跨案例複用的「底層心法（知識晶體）」，每條標註出自哪幾篇素材。\n"
        "4. 最後列出 2～3 個具體可執行的「下一步小實驗」。\n\n"
        f"{material}\n"
    )

    crystal_md, provider = llm.generate(prompt)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", topic)[:40]
    today = datetime.date.today().isoformat()
    out_path = EXPORTS_DIR / f"teacher_{safe_name}_{today}.md"
    header = (
        f"# 🎓 AI 老師專題晶體：{topic}\n\n"
        f"> 生成日期：{today}｜素材來源：{len(notes)} 篇 Notion 原文｜模型：{provider}（$0 Free Tier）\n\n"
    )
    out_path.write_text(header + crystal_md, encoding="utf-8")
    print(f"[TEACHER-OK] notes={len(notes)}, provider={provider}, saved={out_path}")
    try:
        from build_teacher_hub import build_teacher_hub
        build_teacher_hub(EXPORTS_DIR)
    except Exception as e:
        print(f"[WARN] Failed to rebuild HTML Hub: {e}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="V4 AI Teacher On-Demand Structured Synthesis")
    parser.add_argument("--topic", required=True, help="Topic to synthesize, e.g. 'AI實戰案例'")
    parser.add_argument("--tag", default=None, help="Optional exact whitelist tag filter")
    parser.add_argument("--max-notes", type=int, default=12, help="Max source notes to include")
    args = parser.parse_args()
    ask_teacher(topic=args.topic, tag=args.tag, max_notes=args.max_notes)


if __name__ == "__main__":
    main()
