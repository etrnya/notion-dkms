"""Build a single-file offline HTML Hub collecting all `exports/teacher_*.md` articles.

Features:
- Scans `exports/teacher_*.md` (newest first) while keeping all original `.md` files intact.
- Pure local single-file HTML (zero CDN dependencies, works offline via double-click).
- Left sidebar with instant article switching, live keyword filter, light/dark theme toggle.
- Safe client-side Markdown renderer (tables, headings, lists, bold/italic, code, clickable links).
- Escapes `</script>` (`\\u003c`) inside embedded JSON payload.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from v4_config import EXPORTS_DIR

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB_FILENAME = "AI_Teacher_Hub.html"


def parse_teacher_md_meta(path: Path) -> dict[str, str]:
    raw = path.read_text(encoding="utf-8")
    title = path.stem
    date_str = ""
    meta_line = ""

    m_name = re.match(r"^teacher_(.+)_(\d{4}-\d{2}-\d{2})$", path.stem)
    if m_name:
        title = m_name.group(1).replace("_", " ")
        date_str = m_name.group(2)

    for line in raw.splitlines()[:10]:
        s = line.strip()
        if s.startswith("# "):
            title = s[2:].replace("🎓 AI 老師專題晶體：", "").strip() or title
        elif s.startswith("> 生成日期："):
            meta_line = s[2:].strip()
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", meta_line)
            if dm:
                date_str = dm.group(1)

    return {
        "id": path.stem,
        "filename": path.name,
        "title": title,
        "date": date_str or "未知日期",
        "meta": meta_line,
        "markdown": raw,
    }


def _escape_script_json(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def build_teacher_hub(exports_dir: Path | None = None) -> Path:
    target_dir = exports_dir or EXPORTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    md_files = sorted(target_dir.glob("teacher_*.md"), key=lambda p: (p.stat().st_mtime, p.name), reverse=True)
    articles = [parse_teacher_md_meta(p) for p in md_files]

    payload_json = _escape_script_json(articles)
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>🎓 AI 老師知識晶體總覽庫 (AI Teacher Hub)</title>
<style>
  :root {{
    --bg: #0f172a;
    --panel: #1e293b;
    --panel-hover: #283548;
    --border: #334155;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #38bdf8;
    --accent-soft: rgba(56, 189, 248, 0.14);
    --table-head: #172033;
    --table-stripe: rgba(255, 255, 255, 0.025);
    --code-bg: #0b1220;
  }}
  [data-theme="light"] {{
    --bg: #f8fafc;
    --panel: #ffffff;
    --panel-hover: #f1f5f9;
    --border: #e2e8f0;
    --text: #1e293b;
    --muted: #64748b;
    --accent: #0284c7;
    --accent-soft: rgba(2, 132, 199, 0.10);
    --table-head: #f1f5f9;
    --table-stripe: #f8fafc;
    --code-bg: #f1f5f9;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", "PingFang TC", sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    height: 100vh;
    overflow: hidden;
  }}
  aside {{
    width: 310px;
    min-width: 260px;
    background: var(--panel);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    height: 100vh;
  }}
  .brand {{
    padding: 18px 18px 12px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }}
  .brand h1 {{
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    letter-spacing: 0.2px;
  }}
  .brand small {{
    display: block;
    color: var(--muted);
    font-size: 12px;
    margin-top: 2px;
  }}
  .theme-btn {{
    background: var(--accent-soft);
    color: var(--accent);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 13px;
    white-space: nowrap;
  }}
  .search-box {{
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
  }}
  .search-box input {{
    width: 100%;
    padding: 9px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text);
    font-size: 13px;
    outline: none;
  }}
  .search-box input:focus {{ border-color: var(--accent); }}
  .nav-list {{
    flex: 1;
    overflow-y: auto;
    padding: 10px;
  }}
  .nav-item {{
    padding: 11px 12px;
    border-radius: 10px;
    cursor: pointer;
    margin-bottom: 6px;
    border: 1px solid transparent;
    transition: background 0.15s, border-color 0.15s;
  }}
  .nav-item:hover {{ background: var(--panel-hover); }}
  .nav-item.active {{
    background: var(--accent-soft);
    border-color: var(--accent);
  }}
  .nav-title {{
    font-size: 14px;
    font-weight: 600;
    line-height: 1.4;
  }}
  .nav-meta {{
    font-size: 11.5px;
    color: var(--muted);
    margin-top: 4px;
  }}
  main {{
    flex: 1;
    overflow-y: auto;
    padding: 28px 42px 60px;
  }}
  .article-wrap {{
    max-width: 1080px;
    margin: 0 auto;
    line-height: 1.75;
    font-size: 15px;
  }}
  .article-wrap h1 {{
    font-size: 26px;
    margin: 0 0 12px;
    padding-bottom: 10px;
    border-bottom: 2px solid var(--border);
  }}
  .article-wrap h2 {{
    font-size: 20px;
    margin: 28px 0 12px;
    color: var(--accent);
  }}
  .article-wrap h3 {{
    font-size: 17px;
    margin: 20px 0 8px;
  }}
  .article-wrap blockquote {{
    margin: 12px 0 20px;
    padding: 10px 16px;
    border-left: 4px solid var(--accent);
    background: var(--accent-soft);
    border-radius: 0 8px 8px 0;
    color: var(--text);
    font-size: 13.5px;
  }}
  .article-wrap hr {{
    border: 0;
    border-top: 1px solid var(--border);
    margin: 22px 0;
  }}
  .table-scroll {{
    overflow-x: auto;
    margin: 14px 0 22px;
    border: 1px solid var(--border);
    border-radius: 10px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  th, td {{
    padding: 11px 13px;
    border-bottom: 1px solid var(--border);
    text-align: left;
    vertical-align: top;
  }}
  th {{
    background: var(--table-head);
    font-weight: 700;
    white-space: nowrap;
  }}
  tbody tr:nth-child(even) {{ background: var(--table-stripe); }}
  tbody tr:hover {{ background: var(--accent-soft); }}
  a {{
    color: var(--accent);
    text-decoration: none;
    font-weight: 600;
  }}
  a:hover {{ text-decoration: underline; }}
  code {{
    background: var(--code-bg);
    padding: 2px 6px;
    border-radius: 5px;
    font-family: Consolas, Monaco, monospace;
    font-size: 13px;
  }}
  ul, ol {{ padding-left: 24px; }}
  li {{ margin: 5px 0; }}
  .empty-state {{
    text-align: center;
    padding: 80px 20px;
    color: var(--muted);
  }}
  @media (max-width: 820px) {{
    body {{ flex-direction: column; height: auto; overflow: auto; }}
    aside {{ width: 100%; height: auto; max-height: 280px; border-right: 0; border-bottom: 1px solid var(--border); }}
    main {{ padding: 20px 18px 40px; }}
  }}
</style>
</head>
<body>
  <aside>
    <div class="brand">
      <div>
        <h1>🎓 AI 老師知識庫</h1>
        <small id="countLabel">共 0 篇專題晶體</small>
      </div>
      <button class="theme-btn" id="themeToggle" type="button">☀️ 淺色</button>
    </div>
    <div class="search-box">
      <input id="searchInput" type="search" placeholder="搜尋專題標題或內文關鍵字..." />
    </div>
    <div class="nav-list" id="navList"></div>
  </aside>
  <main>
    <div class="article-wrap" id="articleView">
      <div class="empty-state">尚未有專題文章，請執行 ask_teacher.py 生成。</div>
    </div>
  </main>

<script id="articlesData" type="application/json">{payload_json}</script>
<script>
(function() {{
  const articles = JSON.parse(document.getElementById("articlesData").textContent || "[]");
  const navList = document.getElementById("navList");
  const articleView = document.getElementById("articleView");
  const searchInput = document.getElementById("searchInput");
  const countLabel = document.getElementById("countLabel");
  const themeToggle = document.getElementById("themeToggle");

  let activeId = articles.length ? articles[0].id : null;

  // Theme persistence
  const savedTheme = localStorage.getItem("ai_teacher_hub_theme") || "dark";
  applyTheme(savedTheme);
  themeToggle.addEventListener("click", () => {{
    const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
    applyTheme(next);
    localStorage.setItem("ai_teacher_hub_theme", next);
  }});
  function applyTheme(t) {{
    if (t === "light") {{
      document.documentElement.setAttribute("data-theme", "light");
      themeToggle.textContent = "🌙 深色";
    }} else {{
      document.documentElement.removeAttribute("data-theme");
      themeToggle.textContent = "☀️ 淺色";
    }}
  }}

  // Safe inline Markdown -> DOM Fragment (0 innerHTML for untrusted raw HTML)
  function renderInline(text) {{
    const frag = document.createDocumentFragment();
    const tokenRe = /(\\[[^\\]]+\\]\\(https?:\\/\\/[^\\s)]+\\)|\\*\\*[^*]+\\*\\*|`[^`]+`|https?:\\/\\/[^\\s<>)]+)/g;
    let lastIdx = 0;
    let m;
    while ((m = tokenRe.exec(text)) !== null) {{
      if (m.index > lastIdx) {{
        frag.appendChild(document.createTextNode(text.slice(lastIdx, m.index)));
      }}
      const tok = m[0];
      if (tok.startsWith("[")) {{
        const lm = tok.match(/^\\[([^\\]]+)\\]\\((https?:\\/\\/[^\\s)]+)\\)$/);
        if (lm) {{
          const a = document.createElement("a");
          a.href = lm[2];
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = lm[1];
          frag.appendChild(a);
        }}
      }} else if (tok.startsWith("**")) {{
        const strong = document.createElement("strong");
        strong.textContent = tok.slice(2, -2);
        frag.appendChild(strong);
      }} else if (tok.startsWith("`")) {{
        const code = document.createElement("code");
        code.textContent = tok.slice(1, -1);
        frag.appendChild(code);
      }} else if (tok.startsWith("http")) {{
        const a = document.createElement("a");
        a.href = tok;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = tok;
        frag.appendChild(a);
      }}
      lastIdx = tokenRe.lastIndex;
    }}
    if (lastIdx < text.length) {{
      frag.appendChild(document.createTextNode(text.slice(lastIdx)));
    }}
    return frag;
  }}

  function splitTableRow(line) {{
    return line.trim().replace(/^\\|/, "").replace(/\\|$/, "").split("|").map(c => c.trim());
  }}

  function renderMarkdown(md) {{
    const container = document.createElement("div");
    const lines = md.replace(/\\r\\n/g, "\\n").split("\\n");
    let i = 0;

    while (i < lines.length) {{
      const line = lines[i];
      const trimmed = line.trim();
      if (!trimmed) {{ i++; continue; }}

      if (trimmed === "---" || trimmed === "***") {{
        container.appendChild(document.createElement("hr"));
        i++; continue;
      }}

      const hm = trimmed.match(/^(#{{1,3}})\\s+(.*)$/);
      if (hm) {{
        const h = document.createElement("h" + hm[1].length);
        h.appendChild(renderInline(hm[2]));
        container.appendChild(h);
        i++; continue;
      }}

      if (trimmed.startsWith("> ")) {{
        const bq = document.createElement("blockquote");
        bq.appendChild(renderInline(trimmed.slice(2)));
        container.appendChild(bq);
        i++; continue;
      }}

      // Markdown table
      if (trimmed.startsWith("|") && i + 1 < lines.length && /^\\|?[\\s:-]+\\|/.test(lines[i + 1].trim())) {{
        const wrap = document.createElement("div");
        wrap.className = "table-scroll";
        const table = document.createElement("table");
        const thead = document.createElement("thead");
        const headTr = document.createElement("tr");
        splitTableRow(trimmed).forEach(col => {{
          const th = document.createElement("th");
          th.appendChild(renderInline(col));
          headTr.appendChild(th);
        }});
        thead.appendChild(headTr);
        table.appendChild(thead);
        i += 2;

        const tbody = document.createElement("tbody");
        while (i < lines.length && lines[i].trim().startsWith("|")) {{
          const tr = document.createElement("tr");
          splitTableRow(lines[i]).forEach(col => {{
            const td = document.createElement("td");
            td.appendChild(renderInline(col));
            tr.appendChild(td);
          }});
          tbody.appendChild(tr);
          i++;
        }}
        table.appendChild(tbody);
        wrap.appendChild(table);
        container.appendChild(wrap);
        continue;
      }}

      // Unordered or ordered list
      if (/^[-*]\\s+/.test(trimmed) || /^\\d+\\.\\s+/.test(trimmed)) {{
        const isOrdered = /^\\d+\\.\\s+/.test(trimmed);
        const listEl = document.createElement(isOrdered ? "ol" : "ul");
        while (i < lines.length) {{
          const cur = lines[i].trim();
          const lm = cur.match(/^(?:[-*]|\\d+\\.)\\s+(.*)$/);
          if (!lm) break;
          const li = document.createElement("li");
          li.appendChild(renderInline(lm[1]));
          listEl.appendChild(li);
          i++;
        }}
        container.appendChild(listEl);
        continue;
      }}

      const p = document.createElement("p");
      p.appendChild(renderInline(trimmed));
      container.appendChild(p);
      i++;
    }}
    return container;
  }}

  function renderNav(filterText = "") {{
    const q = filterText.trim().toLowerCase();
    const filtered = articles.filter(a =>
      !q || a.title.toLowerCase().includes(q) || a.markdown.toLowerCase().includes(q)
    );
    countLabel.textContent = `共 ${{filtered.length}} / ${{articles.length}} 篇專題晶體`;
    navList.textContent = "";

    filtered.forEach(a => {{
      const item = document.createElement("div");
      item.className = "nav-item" + (a.id === activeId ? " active" : "");
      const t = document.createElement("div");
      t.className = "nav-title";
      t.textContent = a.title;
      const m = document.createElement("div");
      m.className = "nav-meta";
      m.textContent = `${{a.date}} · ${{a.filename}}`;
      item.appendChild(t);
      item.appendChild(m);
      item.addEventListener("click", () => {{
        activeId = a.id;
        renderNav(searchInput.value);
        renderActive();
      }});
      navList.appendChild(item);
    }});
  }}

  function renderActive() {{
    const art = articles.find(a => a.id === activeId) || articles[0];
    articleView.textContent = "";
    if (!art) {{
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "找不到符合的專題文章。";
      articleView.appendChild(empty);
      return;
    }}
    articleView.appendChild(renderMarkdown(art.markdown));
  }}

  searchInput.addEventListener("input", () => renderNav(searchInput.value));
  renderNav();
  renderActive();
}})();
</script>
</body>
</html>
"""
    hub_path = target_dir / HUB_FILENAME
    hub_path.write_text(html, encoding="utf-8")
    print(f"[HUB-OK] articles={len(articles)}, saved={hub_path}")
    return hub_path


if __name__ == "__main__":
    build_teacher_hub()
