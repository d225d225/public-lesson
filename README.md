# 永平高中・公開授課表件產生器

教師填寫基本資料、上傳教學檔案與上課照片，AI 自動完成公開授課三項表件：
【表件一】教學活動設計、【表件二】教學省思心得、【表件三】教學觀察紀錄表。

- 高中部用 `templates/高.docx`，國中部用 `templates/國.docx`（學校原始表件）
- 共備教師一律寫「○○領域教師」，教材來源一律勾「自編教材」
- 產生 Word、Google 文件、PDF，並在雲端硬碟「公開授課表件」資料夾建立 `高-數學-王小明老師` 子資料夾
- 不需密碼，直接使用

## 架構

| 檔案 | 用途 |
|---|---|
| `app.py` | Streamlit 介面：① 填寫資料 → ② AI 撰寫 → ③ 確認內容 → ④ 下載表件 |
| `core/ai.py` | Claude 讀教學檔案與照片，撰寫三項表件內容 |
| `core/forms.py` | 把內容填進 Word 範本（保留學校格式） |
| `core/drive.py` | 呼叫 Apps Script，存到雲端硬碟並轉成 Google 文件與 PDF |
| `apps_script/Code.gs` | Apps Script 程式（真實 SECRET 版在不上傳的 `Code.txt`） |

## 部署

1. **Apps Script**（用 d225@yphs.tw 登入）：新增專案 → 貼上 `Code.txt` 全部內容 → 選函式 `authorize` 按「執行」並授權 →
   「部署」→「新增部署作業」→ 類型「網頁應用程式」，執行身分「我」，存取權「任何人」→ 複製網址。
2. **Streamlit Cloud**：New app → repo `d225d225/public-lesson`、檔案 `app.py`、Python 3.12 →
   Secrets 填入：

   ```toml
   ANTHROPIC_API_KEY_B64 = "（與優高檢核表相同）"
   GAS_WEBHOOK_URL = "（第 1 步複製的網址）"
   GAS_SECRET = "（Code.txt 裡的 SECRET）"
   ```

3. 程式更新推送後，到 share.streamlit.io →「⋮」→ Reboot（重新啟動）。
