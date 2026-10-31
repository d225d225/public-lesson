"""把資料填進學校的公開授課三項表件（Word 範本）。

範本：templates/高.docx、templates/國.docx（兩份只差表件一上方的兩個網址）。
表格順序：
  0 表件一 教學活動設計
  1 表件二 教學省思心得（第 6 列內含 2×2 照片表）
  2 表件三 基本資料
  3 表件三 教學目標／學生經驗＋A 層面觀察
  4 表件三 B 層面觀察
"""
from __future__ import annotations

import copy
import datetime as dt
import io
from pathlib import Path

import docx
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm
from docx.table import _Cell

from core import media

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
FONT = "DFKai-SB"  # 標楷體，與範本相同
WEEKDAYS = "一二三四五六日"
CHECK = "✓"

# 表件三觀察指標（與範本列順序一致）；只有「A-3-1」這種細項需要填寫
OBS_A = [
    "A-3", "A-3-1", "A-3-2", "A-3-3",
    "A-4", "A-4-1", "A-4-2", "A-4-3", "A-4-4", "A-4-5", "A-4-6", "A-4-7",
    "A-5", "A-5-1", "A-5-2", "A-5-3", "A-5-4", "A-5-5", "A-5-6", "A-5-7", "A-5-8",
    "A-6", "A-6-1", "A-6-2", "A-6-3", "A-6-4",
    "A-7", "A-7-1", "A-7-3", "A-7-4",
]
OBS_GROUPS = ["A-3", "A-4", "A-5", "A-6", "A-7", "B-1", "B-2", "B-4"]
OBS_B = ["B-1", "B-1-3", "B-1-4", "B-1-5", "B-2", "B-2-1", "B-2-2", "B-2-3", "B-2-4", "B-4", "B-4-3"]
RATINGS = ["值得推薦", "通過", "待改進", "不適用"]


def is_item(code: str) -> bool:
    return code.count("-") == 2


def roc_date(d: dt.date) -> str:
    return f"{d.year - 1911}/{d.month}/{d.day}"


# ---------------------------------------------------------------- XML 小工具

def _w(tag: str) -> str:
    return qn(f"w:{tag}")


def _children(el, tag: str) -> list:
    return el.findall(_w(tag))


def _rpr(size: int | None = None, bold: bool = False):
    rpr = OxmlElement("w:rPr")
    f = OxmlElement("w:rFonts")
    for k in ("ascii", "hAnsi", "eastAsia", "cs"):
        f.set(qn(f"w:{k}"), FONT)
    rpr.append(f)
    if bold:
        rpr.append(OxmlElement("w:b"))
    col = OxmlElement("w:color")
    col.set(_w("val"), "000000")
    rpr.append(col)
    if size:
        for t in ("sz", "szCs"):
            s = OxmlElement(f"w:{t}")
            s.set(_w("val"), str(size))
            rpr.append(s)
    return rpr


def _run(text: str, size=None, bold=False):
    r = OxmlElement("w:r")
    r.append(_rpr(size, bold))
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = text
    r.append(t)
    return r


def _para(ppr_src, parts, align: str | None = None, indent_hanging: bool = False):
    """parts：[(文字, size, bold), ...]。ppr_src：沿用範本段落格式。"""
    p = OxmlElement("w:p")
    ppr = copy.deepcopy(ppr_src) if ppr_src is not None else OxmlElement("w:pPr")
    for tag in ("jc", "ind", "rPr"):
        for old in ppr.findall(_w(tag)):
            ppr.remove(old)
    if indent_hanging:
        ind = OxmlElement("w:ind")
        ind.set(_w("left"), "240")
        ind.set(_w("hanging"), "240")
        ppr.append(ind)
    if align:
        jc = OxmlElement("w:jc")
        jc.set(_w("val"), align)
        ppr.append(jc)
    p.append(ppr)
    for text, size, bold in parts:
        p.append(_run(text, size, bold))
    return p


def set_cell(tc, lines, size=None, bold=False, align=None, keep_nested=True, hanging=False):
    """清空儲存格段落（保留內嵌表格），寫入多行文字。lines 可為字串或 [(文字,size,bold)...] 的串列。"""
    paras = _children(tc, "p")
    ppr = paras[0].find(_w("pPr")) if paras else None
    ppr = copy.deepcopy(ppr) if ppr is not None else None
    for p in paras:
        tc.remove(p)
    if isinstance(lines, str):
        lines = lines.split("\n")
    lines = list(lines) or [""]
    anchor = None
    if keep_nested:
        nested = _children(tc, "tbl")
        anchor = nested[0] if nested else None
    for ln in lines:
        parts = ln if isinstance(ln, list) else [(ln, size, bold)]
        p = _para(ppr, parts, align, hanging)
        if anchor is not None:
            anchor.addprevious(p)
        else:
            tc.append(p)
    if keep_nested and anchor is not None and anchor.getnext() is None:
        tc.append(_para(ppr, [("", size, False)]))  # 儲存格必須以段落結尾


def rows(tbl) -> list:
    return _children(tbl, "tr")


def cells(tr) -> list:
    return _children(tr, "tc")


def nested_table(tc):
    t = _children(tc, "tbl")
    return t[0] if t else None


# ---------------------------------------------------------------- 填寫

def header_values(info: dict) -> dict:
    d: dt.date = info["date"]
    sem1 = "■" if info["sem"] == 1 else "□"
    sem2 = "■" if info["sem"] == 2 else "□"
    return {
        "year": str(info["year"]),
        "sem": f"{sem1}第一學期    {sem2}第二學期",
        "domain": info["domain"],
        "unit": info["unit"],
        "klass": info["klass"],
        "date": f"{d.year - 1911} 年 {d.month} 月 {d.day} 日 週{WEEKDAYS[d.weekday()]} 第 {info['period']} 節",
        "teacher": info["teacher"],
        "periods": f"共 {info['total_periods']} 節，授課為本單元第 {info['this_period']} 節",
    }


def fill_header(tbl, info: dict):
    v = header_values(info)
    r = rows(tbl)
    layout = [("year", "sem"), ("domain", "unit"), ("klass", "date"), ("teacher", "periods")]
    for i, (left, right) in enumerate(layout):
        c = cells(r[i])
        set_cell(c[1], v[left], align="center" if left != "domain" else "center")
        set_cell(c[3], v[right])


def _bullets(items: list[str]) -> list[str]:
    items = [s.strip() for s in items if s and s.strip()]
    if len(items) <= 1:
        return items
    return [f"{i}. {s}" for i, s in enumerate(items, 1)]


def fill_form1(tbl, info: dict, c: dict):
    fill_header(tbl, info)
    r = rows(tbl)
    # 共備教師：本格與「共同備課重點」內嵌框
    co = cells(r[4])[1]
    set_cell(co, f"{info['domain']}領域教師")
    nt = nested_table(co)
    if nt is not None:
        box = cells(rows(nt)[0])[0]
        lines = [[("共同備課重點：", 20, True)]] + [[(s, 20, False)] for s in _bullets(c.get("coprep", []))]
        set_cell(box, lines)
    # 教材來源：勾選自編教材
    src = cells(r[5])[1]
    for t in src.iter(_w("t")):
        if t.text and "□" in t.text:
            t.text = t.text.replace("□", "■", 1)
            break
    set_cell(cells(r[6])[1], _bullets(c.get("indicators", [])), hanging=True)
    set_cell(cells(r[7])[1], _bullets(c.get("goals", [])), hanging=True)
    _fill_flow(r[9], c.get("flow", []), info)
    set_cell(cells(r[11])[0], _bullets(c.get("references", [])) or [""], hanging=True)
    set_cell(cells(r[13])[0], _bullets(c.get("appendix", [])) or [""], hanging=True)


PART_TITLES = {"準備": "壹、準備活動", "發展": "貳、發展活動", "綜合": "参、綜合活動"}


def _fill_flow(tpl_row, flow: list[dict], info: dict):
    """教學流程：每段活動一列，節次欄上下合併。"""
    parent = tpl_row.getparent()
    seen = set()
    new_rows = []
    for i, seg in enumerate(flow):
        tr = copy.deepcopy(tpl_row)
        cs = cells(tr)
        part = seg.get("part", "發展")
        lines = []
        if part not in seen:
            seen.add(part)
            lines.append([(PART_TITLES.get(part, part), None, True)])
        if seg.get("title"):
            lines.append([(seg["title"], None, True)])
        lines += [[(s, 22, False)] for s in seg.get("details", []) if s.strip()]
        set_cell(cs[1], lines)
        set_cell(cs[2], seg.get("time", ""), size=22, align="center")
        set_cell(cs[3], seg.get("resources", ""), size=22)
        set_cell(cs[4], seg.get("assessment", ""), size=22)
        # 節次欄
        tcpr = cs[0].find(_w("tcPr"))
        vm = OxmlElement("w:vMerge")
        if i == 0:
            vm.set(_w("val"), "restart")
            set_cell(cs[0], f"第{info['this_period']}節", align="center")
        else:
            set_cell(cs[0], "")
        tcpr.append(vm)
        if len(flow) == 1:
            tcpr.remove(vm)
        new_rows.append(tr)
    for tr in new_rows:
        tpl_row.addprevious(tr)
    if new_rows:
        parent.remove(tpl_row)


def fill_form2(doc, tbl, info: dict, c: dict, photos: list[bytes]):
    fill_header(tbl, info)
    r = rows(tbl)
    paras = [p for p in c.get("reflection", []) if p.strip()]
    set_cell(cells(r[5])[0], [[("　　" + p, None, False)] for p in paras] or [""])
    holder = cells(r[6])[0]
    nt = nested_table(holder)
    if nt is None:
        return
    pr = rows(nt)
    caps = c.get("captions", [])
    slots = [(0, 0), (0, 1), (2, 0), (2, 1)]
    for k, (ri, ci) in enumerate(slots):
        tc = cells(pr[ri])[ci]
        cap_tc = cells(pr[ri + 1])[ci]
        cap = caps[k] if k < len(caps) else ""
        set_cell(cap_tc, f"說明：{cap}", size=22)
        if k < len(photos):
            set_cell(tc, "", align="center")
            cell = _Cell(tc, doc.tables[1])
            run = cell.paragraphs[0].add_run()
            w, h = media.fit_size(photos[k], 8.0, 6.0)
            run.add_picture(io.BytesIO(photos[k]), width=Cm(w), height=Cm(h))


def fill_form3(tbl_head, tbl_a, tbl_b, info: dict, c: dict):
    fill_header(tbl_head, info)
    # 教學目標／學生經驗
    top = cells(rows(tbl_a)[0])
    set_cell(top[0], [[("教學目標：", None, True)]] + [[(s, 20, False)] for s in _bullets(c.get("goals", []))],
             hanging=True)
    set_cell(top[1], [[("學生經驗：", 20, True)], [(c.get("obs_student", ""), 20, False)]])
    groups = c.get("obs_groups", {})
    ratings = c.get("ratings", {})
    for tbl, codes, first in ((tbl_a, OBS_A, 3), (tbl_b, OBS_B, 2)):
        rs = rows(tbl)
        for k, code in enumerate(codes):
            cs = cells(rs[first + k])
            group = "-".join(code.split("-")[:2])
            # 文字敘述欄依層面分組上下合併，只寫在每組合併的第一格
            vm = cs[2].find(_w("tcPr") + "/" + _w("vMerge"))
            if vm is not None and vm.get(_w("val")) == "restart":
                set_cell(cs[2], groups.get(group, ""), size=20)
            if not is_item(code):
                continue
            rating = ratings.get(code, "")
            for j, name in enumerate(RATINGS):
                set_cell(cs[3 + j], CHECK if rating == name else "", align="center", size=20)


def build_docx(info: dict, content: dict, photos: list[bytes]) -> bytes:
    doc = docx.Document(str(TEMPLATE_DIR / f"{info['level']}.docx"))
    t = [tb._tbl for tb in doc.tables]
    fill_form1(t[0], info, content)
    fill_form2(doc, t[1], info, content, photos)
    fill_form3(t[2], t[3], t[4], info, content)
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
