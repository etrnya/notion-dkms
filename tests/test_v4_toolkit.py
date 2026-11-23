"""Offline Unit & Safety Invariant Tests for notion-dkms V4 Second-Brain Toolkit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from v4_config import (
    FreeTierLLMClient,
    TAG_WHITELIST,
    filter_whitelist_tags,
    is_login_wall,
    parse_json_silentfix,
    split_text_chunks,
)


class TestV4Toolkit(unittest.TestCase):
    def test_whitelist_has_18_unique_categories(self):
        self.assertEqual(len(TAG_WHITELIST), 18)
        self.assertEqual(len(set(TAG_WHITELIST)), 18)
        self.assertIn("AI實戰案例", TAG_WHITELIST)
        self.assertIn("待補正文", TAG_WHITELIST)
        self.assertIn("抓取失敗", TAG_WHITELIST)

    def test_filter_whitelist_tags_drops_hallucinated_tags(self):
        out = filter_whitelist_tags(["鏤空字體", "AI實戰案例", "GPT輸入法", "AI開發與Agent", "辦公與效率工具"], max_tags=2)
        self.assertEqual(out, ["AI實戰案例", "AI開發與Agent"])
        fallback = filter_whitelist_tags(["完全不存在的標籤"])
        self.assertEqual(fallback, ["生活技巧與資訊"])

    def test_login_wall_detector(self):
        self.assertTrue(is_login_wall("臉書登入教學密碼掃碼帳號管理", "標準登入介面"))
        self.assertTrue(is_login_wall("一般標題", "請先登入或註冊，忘記帳號或建立新帳號"))
        self.assertFalse(is_login_wall("Claude Code 自動剪輯工作流", "整合 Whisper 與 ffmpeg 自動剪輯短影音"))

    def test_split_text_chunks_respects_notion_limit(self):
        long_text = "\n".join([f"第 {i} 行測試內容 " + "A" * 120 for i in range(40)])
        chunks = split_text_chunks(long_text, max_len=1800)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 1800)

    def test_silentfix_json_parser(self):
        raw = '```json\n{"summary": "測試摘要", "tags": ["AI實戰案例",],}\n```'
        parsed = parse_json_silentfix(raw)
        self.assertEqual(parsed["summary"], "測試摘要")
        self.assertEqual(parsed["tags"], ["AI實戰案例"])

    def test_zero_vertex_postpaid_invariant(self):
        client = FreeTierLLMClient(env={})
        self.assertFalse(client.ALLOW_VERTEX_POSTPAID)


if __name__ == "__main__":
    unittest.main(verbosity=2)
