"""Google Gemini（免費版）：讀取教學檔案與上課照片，撰寫公開授課三項表件內容。"""
from __future__ import annotations

import json
import time

from google import genai
from google.genai import errors, types

from core.forms import OBS_A, OBS_B, OBS_GROUPS, RATINGS, is_item

# 免費額度用完、忙線或模型停用時依序改用下一個；可用 secrets 的 GEMINI_MODEL 指定第一順位
# 每個模型的免費額度與忙線狀況各自獨立，多列幾個輪流試
MODELS = ["gemini-3.5-flash", "gemini-flash-latest", "gemini-3.6-flash", "gemini-3-flash-preview",
          "gemini-3.5-flash-lite", "gemini-flash-lite-latest", "gemini-3.1-flash-lite"]

OBS_LABELS = {
    "A-3": "精熟任教學科領域知識", "A-3-1": "正確掌握任教單元的教材內容", "A-3-2": "有效連結學生的新舊知識或技能",
    "A-3-3": "教學內容結合學生的生活經驗",
    "A-4": "清楚呈現教材內容", "A-4-1": "說明學習目標及學習重點", "A-4-2": "有組織條理呈現教材內容",
    "A-4-3": "清楚講解重要概念、原則或技能", "A-4-4": "提供學生適當的實作或練習",
    "A-4-5": "澄清迷思概念、易錯誤類型，或引導價值觀", "A-4-6": "設計引發學生思考與討論的教學情境",
    "A-4-7": "適時歸納學習重點",
    "A-5": "運用有效教學技巧", "A-5-1": "引發並維持學生學習動機", "A-5-2": "善於變化教學活動或教學方法",
    "A-5-3": "教學活動中融入學習策略的指導", "A-5-4": "教學活動轉換與銜接能順暢進行",
    "A-5-5": "掌握時間分配和教學節奏", "A-5-6": "透過發問技巧，引導學生思考",
    "A-5-7": "使用有助於學生學習的教學媒材", "A-5-8": "根據學生個別差異實施教學活動",
    "A-6": "應用良好溝通技巧", "A-6-1": "板書正確、工整有條理", "A-6-2": "口語清晰、音量適中",
    "A-6-3": "運用肢體語言，增進師生互動", "A-6-4": "教室走動或眼神能關照多數學生",
    "A-7": "運用學習評量評估學習成效", "A-7-1": "教學過程中，適時檢視學生學習情形",
    "A-7-3": "根據學生評量結果，適時進行補救教學", "A-7-4": "學生學習成果達成預期學習目標",
    "B-1": "建立有助於學生學習的班級常規", "B-1-3": "維持良好的班級秩序", "B-1-4": "適時增強學生的良好表現",
    "B-1-5": "妥善處理學生的不當行為或偶發狀況",
    "B-2": "營造積極的班級學習氣氛", "B-2-1": "引導學生專注於學習", "B-2-2": "布置或安排有助於學生學習的環境",
    "B-2-3": "展現熱忱的教學態度", "B-2-4": "教師公平對待學生",
    "B-4": "落實學生輔導工作", "B-4-3": "敏察標籤化所產生的負向行為，採取預防措施與輔導",
}
ITEMS = [c for c in OBS_A + OBS_B if is_item(c)]

STYLE_GUIDE = """\
你是新北市立永平高級中學的教學輔導教師，協助授課教師完成「公開授課」三項表件：
【表件一】教學活動設計、【表件二】教學省思心得、【表件三】教學觀察紀錄表。

寫作規範：
- 使用台灣繁體中文與十二年國教（108 課綱）用語，語氣專業、具體、平實，不用浮誇形容詞。
- 內容必須根據教師上傳的教學檔案（簡報、教案、學習單）與上課照片撰寫，扣合教學單元。
- 能力指標：寫出本單元對應的核心素養（如「數-U-A2」）與學習表現／學習內容代碼及文字。
  國中部用國民中學教育階段（J，例如「國-J-A1」），高中部用普通型高中教育階段（U，例如「數-U-A2」）。
  代碼不確定時只寫文字描述，不要編造不存在的代碼，也不要加「代碼待確認」之類的註記。
- 教學目標：3～5 點，以學生為主詞的可評量敘述（例：「能說出…」「能運用…」）。
- 教學流程分「準備活動、發展活動、綜合活動」三部分；發展活動拆成 2～4 個活動，標題寫「活動一：○○」。
  每段 details 寫 2～5 行具體步驟（教師提問、學生任務），時間各段加總等於 50 分鐘（國中 45 分鐘）。
- 教材來源一律是「自編教材」；共備教師為同領域教師，共同備課重點寫 3～4 點（學生起點、教學設計、評量規劃、觀課焦點等）。
- 教學省思心得：以授課教師第一人稱撰寫 3～4 段，每段 100～130 字（全文 400～480 字，才能和照片排在同一頁），依序寫教學設計理念、課堂實施與學生表現
  （可對應照片中的學習情形）、議課回饋重點、未來修正方向。不要寫出學生姓名。
- 照片說明：每張一句話（15 字內），描述照片中的教學或學習活動；照片看不出課程內容時，就客觀描述畫面（例：「學生專注聆聽」）。
- 教學觀察紀錄表：以觀課教師的角度，依各層面撰寫 1～2 句具體的觀察敘述（文字敘述），
  評量勾選以「通過」為主，教學亮點可勾「值得推薦」；與本次課程無關者勾「不適用」，不要勾「待改進」。
- 表件內容是正式文件，不要提到「上傳」「檔案」「照片不符」或 AI 等字眼。
- 教師提供的教學相關連結請列入參考資料或附錄。看不出來的資訊不要編造具體數字或人名。
"""

SEGMENT = {
    "type": "object",
    "properties": {
        "part": {"type": "string", "enum": ["準備", "發展", "綜合"]},
        "title": {"type": "string", "description": "發展活動寫「活動一：○○」；準備與綜合活動可留空"},
        "details": {"type": "array", "items": {"type": "string"}},
        "time": {"type": "string", "description": "例如「5分鐘」"},
        "resources": {"type": "string", "description": "教學資源，例如「簡報、學習單」"},
        "assessment": {"type": "string", "description": "評量方式，例如「口頭問答」「實作評量」"},
    },
    "required": ["part", "title", "details", "time", "resources", "assessment"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "indicators": {"type": "array", "items": {"type": "string"}, "description": "能力指標（核心素養、學習表現、學習內容）"},
        "goals": {"type": "array", "items": {"type": "string"}},
        "coprep": {"type": "array", "items": {"type": "string"}, "description": "共同備課重點"},
        "flow": {"type": "array", "items": SEGMENT},
        "references": {"type": "array", "items": {"type": "string"}},
        "appendix": {"type": "array", "items": {"type": "string"}, "description": "附錄：學習單或其他相關資料（名稱或連結）"},
        "reflection": {"type": "array", "items": {"type": "string"}, "description": "教學省思心得，每個元素一段"},
        "captions": {"type": "array", "items": {"type": "string"}, "description": "照片說明，依照片順序"},
        "obs_student": {"type": "string", "description": "學生經驗（先備知識、起點能力），1～2 句"},
        "obs_groups": {
            "type": "object",
            "properties": {g: {"type": "string"} for g in OBS_GROUPS},
            "required": OBS_GROUPS,
            "additionalProperties": False,
        },
        "ratings": {
            "type": "object",
            "properties": {c: {"type": "string", "enum": RATINGS} for c in ITEMS},
            "required": ITEMS,
            "additionalProperties": False,
        },
    },
    "required": ["indicators", "goals", "coprep", "flow", "references", "appendix", "reflection",
                 "captions", "obs_student", "obs_groups", "ratings"],
    "additionalProperties": False,
}


class AIError(RuntimeError):
    pass


def _parts(blocks: list[dict]) -> list:
    out = []
    for b in blocks:
        if "text" in b:
            out.append(types.Part.from_text(text=b["text"]))
        else:
            out.append(types.Part.from_bytes(data=b["data"], mime_type=b["mime"]))
    return out


def _call_json(api_key: str, models: list[str], system: str, blocks: list[dict], schema: dict) -> dict:
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system, max_output_tokens=65536,
        response_mime_type="application/json", response_json_schema=schema,
    )
    parts = _parts(blocks)
    models = list(dict.fromkeys(models))
    last = None
    # 免費版常忙線（503）或達每分鐘上限（429）：輪流試每個模型，整輪失敗就等一下再來，最多約 3 分鐘
    for rnd in range(5):
        for model in list(models):
            try:
                resp = client.models.generate_content(model=model, contents=parts, config=config)
            except errors.ClientError as e:
                last = e
                if e.code == 404:  # 模型已停用
                    models.remove(model)
                    continue
                if e.code == 429:
                    continue
                if e.code in (401, 403) or "API key" in str(e):
                    raise AIError("AI 金鑰無效，請管理者檢查 secrets 的 GEMINI_API_KEY") from e
                raise AIError(f"AI 請求錯誤：{e.message}") from e
            except errors.ServerError as e:
                last = e
                continue
            if not resp.candidates:
                raise AIError("AI 無法處理這些檔案，請移除可能敏感的檔案後再試")
            if str(resp.candidates[0].finish_reason).endswith("MAX_TOKENS"):
                raise AIError("AI 回覆太長被截斷，請減少上傳的檔案後再試")
            text = resp.text or ""
            try:
                return json.loads(text[text.find("{"):text.rfind("}") + 1])
            except json.JSONDecodeError:
                last = AIError("AI 回覆格式錯誤")
                continue
        if not models:
            break
        if rnd < 4:
            time.sleep(15 + 15 * rnd)
    if isinstance(last, errors.ClientError) and last.code == 429:
        raise AIError("今天的 AI 免費額度用完了（或使用的人太多），請過幾分鐘或明天再試")
    raise AIError(f"AI 服務暫時無法使用，請稍後再試（{last}）")


def draft_forms(api_key: str, info: dict, file_blocks: list[dict], photo_blocks: list[dict],
                models: list[str] = MODELS) -> dict:
    level = "高中部（普通型高中）" if info["level"] == "高" else "國中部"
    obs_list = "\n".join(f"{c} {OBS_LABELS[c]}" for c in OBS_A + OBS_B)
    links = "\n".join(info.get("links", [])) or "（無）"
    intro = (
        f"學部：{level}\n教學領域：{info['domain']}\n教學單元：{info['unit']}\n"
        f"授課班級：{info['klass']}\n授課教師：{info['teacher']}\n"
        f"本單元共 {info['total_periods']} 節，本次為第 {info['this_period']} 節\n"
        f"教學相關連結：\n{links}\n\n"
        f"教學觀察紀錄表的指標（obs_groups 依層面寫文字敘述，ratings 每個細項勾一個）：\n{obs_list}\n\n"
        f"以下是教師上傳的教學檔案，接著是 {len(photo_blocks) // 2} 張上課照片（captions 依照片順序）。"
        "請據此撰寫三項表件的內容。"
    )
    content = [{"text": intro}] + file_blocks + photo_blocks
    if not file_blocks:
        content.append({"text": "（教師沒有上傳教學檔案，請依教學單元名稱與照片合理規劃。）"})
    return _call_json(api_key, models, STYLE_GUIDE, content, SCHEMA)
