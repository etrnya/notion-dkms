"""V4 Second-Brain Configuration, Whitelist, Safe Notion Client & $0 Free-Tier LLM Client.

Safety Invariants:
- ZERO Vertex AI Postpaid calls: strictly restricted to Google AI Studio Free Tier
  and NVIDIA NIM Free Tier to eliminate postpaid billing-storm risk.
- Notion block chunking <= 60 blocks per request (Rule A: <= 80).
- Paragraph text chunking <= 1800 chars (Notion API max: 2000).
- Deterministic Facebook login-wall & empty-card pre-filtering (0 LLM tokens).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
CHECKPOINTS_DIR = PROJECT_ROOT / "checkpoints"
EXPORTS_DIR = PROJECT_ROOT / "exports"

# Approved 18-Category Fixed Whitelist (V4)
TAG_WHITELIST: tuple[str, ...] = (
    # A. AI 與開發核心 (6)
    "AI實戰案例",
    "AI工具與模型",
    "AI開發與Agent",
    "提示詞與工作流",
    "軟體架構與資安",
    "辦公與效率工具",
    # B. 職涯、商業與管理 (5)
    "職涯與職場溝通",
    "產品與專案管理",
    "一人公司與副業",
    "行銷與內容創作",
    "投資理財與買房",
    # C. 專業領域與自我成長 (3)
    "醫檢與法規證照",
    "思維與自我成長",
    "親子教養與家庭",
    # D. 生活與資料狀態 (4)
    "生活技巧與資訊",
    "硬體與3C設備",
    "待補正文",
    "抓取失敗",
)

TAG_WHITELIST_SET = frozenset(TAG_WHITELIST)

FB_LOGIN_WALL_PATTERNS: tuple[str, ...] = (
    "臉書登入教學",
    "登入或註冊",
    "Log in or sign up",
    "Facebook 的標準登入介面",
    "忘記帳號",
    "建立新帳號",
    "You must log in to continue",
)


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_runtime_env() -> dict[str, str]:
    """Load notion-dkms/.env plus fallback NVIDIA_API_KEY from model-hub-agent/.env if unset."""
    env = load_env_file(PROJECT_ROOT / ".env")
    hub_env = load_env_file(PROJECT_ROOT.parent / "model-hub-agent" / ".env")
    for k in ("NVIDIA_API_KEY", "GEMINI_API_KEY"):
        if not env.get(k) and hub_env.get(k):
            env[k] = hub_env[k]
    for k, v in os.environ.items():
        if v and k not in env:
            env[k] = v
    return env


def is_login_wall(title: str, body: str) -> bool:
    combined = f"{title}\n{body[:600]}"
    hits = sum(1 for pat in FB_LOGIN_WALL_PATTERNS if pat.lower() in combined.lower())
    if hits >= 2:
        return True
    if any(p in title for p in ("登入或註冊", "臉書登入教學", "Log in or sign up")):
        return True
    return False


def filter_whitelist_tags(raw_tags: list[str], max_tags: int = 2) -> list[str]:
    valid: list[str] = []
    for t in raw_tags:
        clean = str(t).strip()
        if clean in TAG_WHITELIST_SET and clean not in valid:
            valid.append(clean)
        if len(valid) >= max_tags:
            break
    return valid or ["生活技巧與資訊"]


def split_text_chunks(text: str, max_len: int = 1800) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for line in text.splitlines():
        if len(line) > max_len:
            if buf:
                chunks.append("\n".join(buf))
                buf, buf_len = [], 0
            for i in range(0, len(line), max_len):
                chunks.append(line[i : i + max_len])
            continue
        if buf_len + len(line) + 1 > max_len and buf:
            chunks.append("\n".join(buf))
            buf, buf_len = [line], len(line)
        else:
            buf.append(line)
            buf_len += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return [c for c in chunks if c.strip()]


def parse_json_silentfix(raw_text: str) -> dict[str, Any]:
    """Strip markdown fences and parse JSON cleanly."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return json.loads(cleaned)


class NotionClientLight:
    """Lightweight Notion REST client with automatic retry and <= 60 block chunking."""

    def __init__(self, token: str, database_id: str):
        if not token:
            raise ValueError("NOTION_API_KEY is required")
        self.token = token
        self.database_id = database_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None, retries: int = 4) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        for attempt in range(retries):
            req = urllib.request.Request(url, data=data, headers=self.headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                    retry_after = float(e.headers.get("Retry-After", 2 * (attempt + 1)))
                    time.sleep(min(retry_after, 15))
                    continue
                raise
            except Exception:
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        raise RuntimeError(f"Notion request failed after {retries} retries: {method} {url}")

    def query_database(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"https://api.notion.com/v1/databases/{self.database_id}/query", body)

    def query_all_pages(self, filter_obj: dict[str, Any] | None = None, sorts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Prefetch all matching pages rapidly so long-running loops never hit Notion cursor expiration."""
        pages: list[dict[str, Any]] = []
        cursor = None
        while True:
            body: dict[str, Any] = {"page_size": 100}
            if filter_obj:
                body["filter"] = filter_obj
            if sorts:
                body["sorts"] = sorts
            if cursor:
                body["start_cursor"] = cursor
            res = self.query_database(body)
            pages.extend(res.get("results", []))
            if not res.get("has_more"):
                break
            cursor = res.get("next_cursor")
        return pages

    def get_blocks(self, block_id: str, page_size: int = 80) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        cursor = None
        while True:
            url = f"https://api.notion.com/v1/blocks/{block_id}/children?page_size={page_size}"
            if cursor:
                url += f"&start_cursor={cursor}"
            res = self._request("GET", url)
            blocks.extend(res.get("results", []))
            if not res.get("has_more") or len(blocks) >= 200:
                break
            cursor = res.get("next_cursor")
        return blocks

    def patch_page_properties(self, page_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", f"https://api.notion.com/v1/pages/{page_id}", {"properties": properties})

    def append_blocks(self, parent_id: str, blocks: list[dict[str, Any]], chunk_size: int = 60) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for i in range(0, len(blocks), chunk_size):
            batch = blocks[i : i + chunk_size]
            res = self._request("PATCH", f"https://api.notion.com/v1/blocks/{parent_id}/children", {"children": batch})
            results.extend(res.get("results", []))
            if i + chunk_size < len(blocks):
                time.sleep(0.35)
        return results

    def append_toggle_text(self, page_id: str, toggle_prefix: str, header_text: str, content: str) -> tuple[bool, int]:
        """Idempotently append a gray Toggle Block with chunked paragraphs (<= 60 blocks/batch)."""
        existing = self.get_blocks(page_id, page_size=50)
        for b in existing:
            if b.get("type") == "toggle":
                t = "".join(x.get("plain_text", "") for x in b["toggle"].get("rich_text", []))
                if t.startswith(toggle_prefix):
                    return False, 0

        created = self.append_blocks(
            page_id,
            [
                {
                    "object": "block",
                    "type": "toggle",
                    "toggle": {
                        "rich_text": [{"type": "text", "text": {"content": header_text[:1900]}}],
                        "color": "gray_background",
                    },
                }
            ],
        )
        toggle_id = created[0]["id"]
        chunks = split_text_chunks(content, max_len=1800)
        para_blocks = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": c}}]},
            }
            for c in chunks
        ]
        if para_blocks:
            self.append_blocks(toggle_id, para_blocks, chunk_size=60)
        return True, len(para_blocks)

    def extract_page_text(self, page_id: str, include_toggles: bool = True) -> str:
        blocks = self.get_blocks(page_id, page_size=80)
        lines: list[str] = []
        for b in blocks:
            bt = b.get("type", "")
            obj = b.get(bt, {})
            if isinstance(obj, dict) and "rich_text" in obj:
                txt = "".join(t.get("plain_text", "") for t in obj["rich_text"]).strip()
                if txt:
                    lines.append(txt)
            if include_toggles and bt == "toggle" and b.get("has_children"):
                for cb in self.get_blocks(b["id"], page_size=50):
                    cbt = cb.get("type", "")
                    cobj = cb.get(cbt, {})
                    if isinstance(cobj, dict) and "rich_text" in cobj:
                        ctxt = "".join(t.get("plain_text", "") for t in cobj["rich_text"]).strip()
                        if ctxt:
                            lines.append(ctxt)
        return "\n".join(lines)


class FreeTierLLMClient:
    """Strict $0-Only LLM Client (Google AI Studio Free Tier <-> NVIDIA NIM Free Tier).

    NEVER calls GCP Vertex AI Postpaid under any circumstance.
    """

    ALLOW_VERTEX_POSTPAID = False  # Hard billing-storm invariant

    def __init__(self, env: dict[str, str] | None = None):
        self.env = env if env is not None else get_runtime_env()
        self.gemini_key = self.env.get("GEMINI_API_KEY", "").strip()
        self.nvidia_key = self.env.get("NVIDIA_API_KEY", "").strip()
        self.gemini_models = [
            self.env.get("GEMINI_FREE_MODEL", "gemini-2.5-flash"),
            "gemini-2.5-flash-lite",
        ]
        self.nvidia_model = self.env.get("NVIDIA_NIM_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")
        self.ai_studio_cooldown_until = 0.0
        self.nvidia_cooldown_until = 0.0

    def _call_ai_studio(self, prompt: str, model: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        gen_cfg: dict[str, Any] = {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
        }
        if "json" in prompt.lower():
            gen_cfg["responseMimeType"] = "application/json"
        if "2.5-flash" in model:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_cfg,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": self.gemini_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode("utf-8"))
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()

    def _call_nvidia_nim(self, prompt: str) -> str:
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        body = {
            "model": self.nvidia_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1024,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.nvidia_key}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()

    def generate(self, prompt: str, max_attempts: int = 4) -> tuple[str, str]:
        """Return (text, provider_used). Strictly uses $0 Free Tier channels only."""
        assert self.ALLOW_VERTEX_POSTPAID is False, "Vertex AI Postpaid is strictly forbidden!"
        last_err: Exception | None = None

        for attempt in range(max_attempts):
            now = time.time()
            # 1. Try Google AI Studio Free Tier
            if self.gemini_key and now >= self.ai_studio_cooldown_until:
                for model in self.gemini_models:
                    try:
                        text = self._call_ai_studio(prompt, model)
                        if text:
                            return text, f"ai_studio:{model}"
                    except urllib.error.HTTPError as e:
                        last_err = e
                        if e.code == 429:
                            self.ai_studio_cooldown_until = time.time() + 35
                            break
                    except Exception as e:
                        last_err = e

            # 2. Fallback to NVIDIA NIM Free Tier
            if self.nvidia_key and time.time() >= self.nvidia_cooldown_until:
                try:
                    text = self._call_nvidia_nim(prompt)
                    if text:
                        return text, f"nvidia_nim:{self.nvidia_model}"
                except urllib.error.HTTPError as e:
                    last_err = e
                    if e.code in (429, 410, 404):
                        self.nvidia_cooldown_until = time.time() + (60 if e.code == 429 else 3600)
                except Exception as e:
                    last_err = e

            # Both in cooldown -> wait politely (never escalate to paid Vertex AI)
            wait_sec = min(15 * (attempt + 1), 45)
            time.sleep(wait_sec)

        raise RuntimeError(f"All $0 free-tier LLM channels failed: {last_err}")
