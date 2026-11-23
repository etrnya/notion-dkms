# notion-dkms 專案 - AI 助理開發與防坑指南

本文件定義了 `notion-dkms` (動態知識代謝系統 V3.5) 專案特定的 Notion 寫入限制、雙重審計與 GCP 金鑰保護規則。

---

## 🛠️ 1. 技術棧與架構

- **核心模組**：Python 3.10+ (`synthesize_knowledge.py`, `batch_processor.py`)。
- **AI 核心**：Vertex AI & Gemini Pro/Flash。
- **數據交換**：Notion API (進行專題寫入與待辦事項自動閉環)。
- **憑證認證**：GCP 服務帳號密鑰 (`gcp-key.json`) 與 `.env` 變數。

---

## 🚫 2. 專案專屬地雷 (AI 必須遵循的防線)

### A. Notion Block 寫入限制 (Payload 溢出防範)
* **地雷原因**：在將 AI 合成的多段專題內容寫入 Notion 時，呼叫 `patch_block_children` 一次發送超過 100 個子 Block，會直接觸發 Notion API 的 Payload Size 限流，導致寫入完全失敗。
* **開發規則**：寫入前必須將 Block 陣列進行 chunking 切片，每批限制發送 80 個 Block 以下。

### B. Vertex AI 頻寬速率限制 (429 Resource Exhausted)
* **地雷原因**：DKMS 包含 Fact Layer 生成、惡魔代言人批判、主合成等多個運算步驟。若併發呼叫 LLM，會立刻觸發 Vertex AI API 額度限制。
* **開發規則**：在各個 agent 推理階段之間加入 2-5 秒的延遲，並在 API 呼叫層封裝重試邏輯，避免流程崩潰。

### C. GCP 服務帳戶 JSON 密鑰保護
* **地雷原因**：專案根目錄下的 `gcp-key.json` 與 `gemini-api-ai-assistant-xxx.json` 包含了生產環境的 GCP 讀寫權限，若遭刪除或誤寫會導致系統全面斷線。
* **開發規則**：AI 助理禁止在寫入或修改代碼時刪除、覆寫任何 `.json` 金鑰檔案，亦不可將金鑰寫入 Git 提交。

### D. SQLite 併發衝突防護
* **地雷原因**：批次處理器 `batch_processor.py` 與 `_check_taskdb.py` 會頻繁讀寫同一個本機 SQLite 數據庫。在多線程運行下易產生衝突。
* **開發規則**：連接 SQLite 時必須開啟 WAL 模式，且在每次 SQL 執行完畢後立即關閉 Connection，確保事務及時提交。
