"""永平高中・公開授課表件產生器（秋楓樣式）。

執行：streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import os

import streamlit as st

from core import ai, forms, media, style
from core.drive import Drive, DriveError

st.set_page_config(page_title="公開授課表件產生器", layout="wide", initial_sidebar_state="collapsed")
st.markdown(style.CSS, unsafe_allow_html=True)

DOMAINS = {
    "高": ["國語文", "英語文", "數學", "自然科學", "社會", "藝術", "綜合活動", "科技", "健康與體育",
          "全民國防教育", "第二外國語文", "本土語文", "特殊教育"],
    "國": ["國語文", "英語文", "本土語文", "數學", "自然科學", "社會", "藝術", "綜合活動", "科技",
          "健康與體育", "特殊教育"],
}
OTHER = "其他（自行輸入）"
MAX_PHOTOS = 4


# ---------------------------------------------------------------- 設定

def secret(key: str) -> str:
    try:
        v = st.secrets.get(key, "")
    except Exception:  # 沒有 secrets.toml 時
        v = ""
    return str(v or os.environ.get(key, "")).strip().strip("　")


API_KEY = secret("GEMINI_API_KEY")  # Google AI Studio 免費金鑰
MODELS = [m for m in [secret("GEMINI_MODEL")] if m] + ai.MODELS
GAS_URL = secret("GAS_WEBHOOK_URL")
drive = Drive(GAS_URL, secret("GAS_SECRET")) if GAS_URL else None


def school_year(d: dt.date) -> tuple[int, int]:
    """依日期判斷學年度與學期：8～1 月為第一學期，2～7 月為第二學期。"""
    roc = d.year - 1911
    if d.month >= 8:
        return roc, 1
    if d.month == 1:
        return roc - 1, 1
    return roc - 1, 2


def sem_label(y: int, s: int) -> str:
    return f"{y} 學年度 第{'一' if s == 1 else '二'}學期"


ss = st.session_state
ss.setdefault("step", 1)
# 回到第 1 步時保留已填的欄位（Streamlit 會清掉沒畫出來的元件狀態）
INPUT_KEYS = ["level_name", "teacher", "sem", "domain_高", "domain_國", "domain_other", "unit", "klass",
              "date", "period", "total_periods", "this_period", "links"]
for _k in INPUT_KEYS:
    if _k in ss:
        ss[_k] = ss[_k]


def go(step: int):
    ss.step = step
    st.rerun()


# ---------------------------------------------------------------- 頁首

st.markdown(style.hero("公開授課表件產生器", "新北市立永平高級中學・教學活動設計／教學省思心得／教學觀察紀錄表",
                       "填好資料、上傳教學檔案與照片，AI 自動完成三項表件"), unsafe_allow_html=True)
st.markdown(style.steps(ss.step), unsafe_allow_html=True)


# ---------------------------------------------------------------- ① 填寫資料

def step_input():
    with st.container(key="picker"):
        level_name = st.segmented_control("部別", ["高中部", "國中部"], key="level_name", default="高中部")
    level = "國" if level_name == "國中部" else "高"

    c1, c2 = st.columns(2)
    with c1:
        teacher = st.text_input("教師姓名", key="teacher", placeholder="例：王小明")
        y, s = school_year(dt.date.today())
        options = [(y - 1, 2), (y, 1), (y, 2), (y + 1, 1)]
        sem = st.selectbox("學期", options, index=1 if s == 1 else 2, format_func=lambda o: sem_label(*o), key="sem")
        domain = st.selectbox("教學領域", DOMAINS[level] + [OTHER], key=f"domain_{level}")
        if domain == OTHER:
            domain = st.text_input("請輸入教學領域", key="domain_other")
        unit = st.text_input("教學單元", key="unit", placeholder="例：三角函數的圖形")
    with c2:
        klass = st.text_input("授課班級", key="klass", placeholder="例：201" if level == "高" else "例：801")
        d1, d2 = st.columns(2)
        date = d1.date_input("教學日期", key="date", format="YYYY/MM/DD")
        period = d2.selectbox("節次", list(range(1, 9)), format_func=lambda n: f"第 {n} 節", key="period")
        p1, p2 = st.columns(2)
        total = p1.number_input("本單元共幾節", 1, 30, 1, key="total_periods")
        this = p2.number_input("本次授課為第幾節", 1, 30, 1, key="this_period")
        links = st.text_area("教學相關連結（一行一個，可不填）", key="links", height=96,
                             placeholder="例：https://www.youtube.com/…\nhttps://docs.google.com/…")

    st.markdown("#### 上傳檔案")
    u1, u2 = st.columns(2)
    files = u1.file_uploader("教學檔案（簡報、教案、學習單：PDF／PPTX／DOCX／圖片）", accept_multiple_files=True,
                             type=["pdf", "pptx", "docx", "txt", "jpg", "jpeg", "png", "heic"], key="files")
    photos = u2.file_uploader(f"學生上課照片（最多 {MAX_PHOTOS} 張，會放進表件二）", accept_multiple_files=True,
                              type=["jpg", "jpeg", "png", "heic", "heif", "webp"], key="photos")
    if photos and len(photos) > MAX_PHOTOS:
        u2.warning(f"只會使用前 {MAX_PHOTOS} 張照片")
    ups = [media.Upload(f.name, f.getvalue(), f.type or "") for f in (files or [])]
    pics = [media.Upload(f.name, f.getvalue(), f.type or "") for f in (photos or [])[:MAX_PHOTOS]]
    # 回上一步時檔案上傳框會清空，沿用上次上傳的檔案
    if not ups and ss.get("saved_ups"):
        ups = ss.saved_ups
        u1.caption(f"沿用上次上傳的 {len(ups)} 個教學檔案（重新上傳即可替換）")
    if not pics and ss.get("saved_pics"):
        pics = ss.saved_pics
        u2.caption(f"沿用上次上傳的 {len(pics)} 張照片（重新上傳即可替換）")

    missing = [n for n, v in (("教師姓名", teacher), ("教學領域", domain), ("教學單元", unit), ("授課班級", klass)) if not str(v).strip()]
    if this > total:
        missing.append("「本次授課為第幾節」不能大於「本單元共幾節」")
    if not API_KEY:
        st.error("系統尚未設定 AI 金鑰，請聯絡管理者。")
    if st.button("✦ AI 撰寫三項表件", type="primary", disabled=bool(missing) or not API_KEY, width="stretch"):
        info = {
            "level": level, "teacher": teacher.strip().removesuffix("老師").strip(), "year": sem[0], "sem": sem[1],
            "domain": domain.strip(), "unit": unit.strip(), "klass": klass.strip(),
            "date": date, "period": period, "total_periods": int(total), "this_period": int(this),
            "links": [ln.strip() for ln in links.splitlines() if ln.strip()],
        }
        ss.saved_ups, ss.saved_pics = ups, pics
        run_ai(info, ups, pics)
    elif missing:
        st.caption("請先填寫：" + "、".join(missing))


def run_ai(info: dict, ups: list, pics: list):
    with st.status("AI 正在閱讀教學檔案並撰寫表件（約 1～3 分鐘，免費版忙線時會自動重試）…", expanded=True) as status:
        file_blocks, warns = media.content_blocks(ups, "教學檔案")
        photo_blocks, w2 = media.content_blocks(pics, "上課照片")
        for w in warns + w2:
            st.warning(w)
        photo_jpgs = []
        for p in pics:
            try:
                photo_jpgs.append(media.to_jpeg(p.data, 1000, 78))
            except Exception as e:
                st.warning(f"{p.name} 無法讀取：{e}")
        try:
            content = ai.draft_forms(API_KEY, info, file_blocks, photo_blocks, MODELS)
        except ai.AIError as e:
            status.update(label="AI 撰寫失敗", state="error")
            st.error(str(e))
            return
        status.update(label="AI 撰寫完成", state="complete")
    ss.info, ss.content, ss.photo_jpgs = info, content, photo_jpgs
    ss.pop("result", None)
    ss.edit_rev = ss.get("edit_rev", 0) + 1  # 重新撰寫時，讓編輯欄位換新
    go(3)


# ---------------------------------------------------------------- ③ 確認內容

def lines_area(label: str, items: list[str], key: str, height: int = 120) -> list[str]:
    txt = st.text_area(label, "\n".join(items), key=key, height=height)
    return [ln.strip() for ln in txt.splitlines() if ln.strip()]


def step_review():
    info, c = ss.info, ss.content
    rev = ss.edit_rev
    st.markdown(
        f'<div class="card"><b>{info["teacher"]} 老師</b>｜{"高中部" if info["level"] == "高" else "國中部"}｜'
        f'{info["domain"]}｜{info["unit"]}｜{info["klass"]}｜{sem_label(info["year"], info["sem"])}｜'
        f'{forms.header_values(info)["date"]}</div>', unsafe_allow_html=True)
    st.caption("AI 已撰寫好內容，可以直接修改；確認後按最下方「產生表件」。")
    new = {}
    t1, t2, t3 = st.tabs(["表件一　教學活動設計", "表件二　教學省思心得", "表件三　教學觀察紀錄表"])
    with t1:
        st.markdown(f"**共備教師**：{info['domain']}領域教師　　**教材來源**：■自編教材")
        new["coprep"] = lines_area("共同備課重點（一行一點）", c["coprep"], f"coprep{rev}")
        new["indicators"] = lines_area("能力指標（一行一項）", c["indicators"], f"ind{rev}")
        new["goals"] = lines_area("教學目標（一行一項）", c["goals"], f"goals{rev}")
        st.markdown("##### 教學流程")
        flow = []
        parts = ["準備", "發展", "綜合"]
        for i, seg in enumerate(c["flow"]):
            with st.container(border=True):
                a, b, t = st.columns([1, 3, 1])
                part = a.selectbox("部分", parts, parts.index(seg["part"]) if seg["part"] in parts else 1,
                                   key=f"fp{rev}_{i}", format_func=lambda p: forms.PART_TITLES[p])
                title = b.text_input("活動名稱", seg["title"], key=f"ft{rev}_{i}")
                time = t.text_input("時間", seg["time"], key=f"fm{rev}_{i}")
                details = lines_area("教學活動內容（一行一步驟）", seg["details"], f"fd{rev}_{i}", 110)
                r1, r2 = st.columns(2)
                res = r1.text_input("教學資源", seg["resources"], key=f"fr{rev}_{i}")
                ass = r2.text_input("評量方式", seg["assessment"], key=f"fa{rev}_{i}")
                flow.append({"part": part, "title": title, "details": details, "time": time,
                             "resources": res, "assessment": ass})
        new["flow"] = flow
        new["references"] = lines_area("參考資料（一行一項）", c["references"], f"ref{rev}")
        new["appendix"] = lines_area("附錄：學習單或其他相關資料（一行一項）", c["appendix"], f"app{rev}", 90)
    with t2:
        txt = st.text_area("教學省思心得（段落之間空一行）", "\n\n".join(c["reflection"]), key=f"refl{rev}", height=360)
        new["reflection"] = [p.strip().replace("\n", "") for p in txt.split("\n\n") if p.strip()]
        caps = []
        if ss.photo_jpgs:
            cols = st.columns(len(ss.photo_jpgs))
            for i, jpg in enumerate(ss.photo_jpgs):
                with cols[i]:
                    st.image(jpg, width="stretch")
                    old = c["captions"][i] if i < len(c["captions"]) else ""
                    caps.append(st.text_input(f"照片 {i + 1} 說明", old, key=f"cap{rev}_{i}"))
        else:
            st.info("沒有上傳上課照片，表件二的照片欄會留白。")
        new["captions"] = caps
    with t3:
        new["obs_student"] = st.text_area("學生經驗", c["obs_student"], key=f"stu{rev}", height=80)
        groups, ratings = {}, {}
        for g in forms.OBS_GROUPS:
            with st.container(border=True):
                groups[g] = st.text_area(f"{g} {ai.OBS_LABELS[g]}｜文字敘述", c["obs_groups"].get(g, ""),
                                         key=f"og{rev}_{g}", height=80)
                items = [x for x in ai.ITEMS if x.startswith(g + "-")]
                for code in items:
                    old = c["ratings"].get(code, "通過")
                    ratings[code] = st.radio(f"{code} {ai.OBS_LABELS[code]}", forms.RATINGS,
                                             forms.RATINGS.index(old) if old in forms.RATINGS else 1,
                                             horizontal=True, key=f"or{rev}_{code}")
        new["obs_groups"], new["ratings"] = groups, ratings

    st.divider()
    b1, b2 = st.columns([1, 3])
    if b1.button("← 回上一步修改資料", width="stretch"):
        go(1)
    if b2.button("產生表件（Word、PDF、Google 文件）", type="primary", width="stretch"):
        ss.content = new
        build(info, new)


def folder_name(info: dict) -> str:
    return media.safe_name(f"{info['level']}-{info['domain']}-{info['teacher']}老師", 60)


def file_name(info: dict) -> str:
    return media.safe_name(f"{info['year']}-{info['sem']}_公開授課表件_{info['teacher']}_{info['unit']}", 80)


def build(info: dict, content: dict):
    with st.spinner("產生 Word 檔…"):
        docx = forms.build_docx(info, content, ss.photo_jpgs)
    result = {"docx": docx, "pdf": None, "links": None, "error": None}
    if drive:
        try:
            with st.spinner("存到雲端硬碟並轉成 Google 文件、PDF（約 30 秒）…"):
                photos = [(f"照片{i + 1}.jpg", b) for i, b in enumerate(ss.photo_jpgs)]
                res = drive.publish(folder_name(info), file_name(info), docx, photos)
            result["pdf"] = res.pop("pdf")
            result["links"] = res
        except DriveError as e:
            result["error"] = str(e)
    else:
        result["error"] = "系統尚未設定雲端硬碟連線，目前只能下載 Word 檔。"
    ss.result = result
    go(4)


# ---------------------------------------------------------------- ④ 下載

def step_done():
    info, r = ss.info, ss.result
    name = file_name(info)
    st.success(f"{info['teacher']} 老師的公開授課表件已完成！")
    links = r.get("links")
    if links:
        st.markdown(f'<div class="card">雲端資料夾：<b>{folder_name(info)}</b>，裡面有 Word、Google 文件與 PDF 三種檔案。</div>',
                    unsafe_allow_html=True)
    if r.get("error"):
        st.warning(r["error"])
    c1, c2, c3 = st.columns(3)
    with c1:
        if links:
            st.link_button("開啟 Google 文件", links["docUrl"], width="stretch")
        else:
            st.button("Google 文件（未連線雲端）", disabled=True, width="stretch")
    with c2:
        st.download_button("下載 Word 檔", r["docx"], f"{name}.docx", width="stretch",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    with c3:
        if r.get("pdf"):
            st.download_button("下載 PDF 檔", r["pdf"], f"{name}.pdf", mime="application/pdf", width="stretch")
        else:
            st.button("PDF（未連線雲端）", disabled=True, width="stretch")
    if links:
        st.link_button("開啟雲端資料夾", links["folderUrl"], width="stretch")

    st.divider()
    b1, b2 = st.columns(2)
    if b1.button("← 回去修改內容", width="stretch"):
        go(3)
    if b2.button("幫另一位老師產生", width="stretch"):
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()


if ss.step == 3 and "content" in ss:
    step_review()
elif ss.step == 4 and "result" in ss:
    step_done()
else:
    ss.step = 1
    step_input()
