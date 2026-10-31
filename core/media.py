"""上傳檔案處理：圖片壓縮、HEIC 轉檔、讀取教學檔案文字、轉成 Claude 可讀的內容區塊。"""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # 沒裝 pillow-heif 時，HEIC 會被當成「無法讀取」
    pass

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".bmp"}
MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_TEXT = 30000


@dataclass
class Upload:
    name: str
    data: bytes
    mime: str = ""
    kind: str = field(init=False)  # image / pdf / docx / pptx / text / other

    def __post_init__(self):
        ext = Path(self.name).suffix.lower()
        if ext in IMAGE_EXT or self.mime.startswith("image/"):
            self.kind = "image"
        elif ext == ".pdf" or self.mime == "application/pdf":
            self.kind = "pdf"
        elif ext == ".docx":
            self.kind = "docx"
        elif ext == ".pptx":
            self.kind = "pptx"
        elif ext in {".txt", ".md", ".csv"}:
            self.kind = "text"
        else:
            self.kind = "other"


def open_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img)  # 手機照片轉正
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def to_jpeg(data: bytes, max_side: int, quality: int) -> bytes:
    img = open_image(data)
    img.thumbnail((max_side, max_side))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=quality, optimize=True)
    return out.getvalue()


def fit_size(jpg: bytes, max_w_cm: float, max_h_cm: float) -> tuple[float, float]:
    """照片等比例縮到框內，回傳 (寬, 高) 公分。"""
    w, h = Image.open(io.BytesIO(jpg)).size
    scale = min(max_w_cm / w, max_h_cm / h)
    return w * scale, h * scale


def docx_text(data: bytes) -> str:
    import docx

    d = docx.Document(io.BytesIO(data))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            parts.append("｜".join(c.text.strip() for c in row.cells))
    return "\n".join(parts)


def pptx_text(data: bytes) -> str:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    out = []
    for i, slide in enumerate(prs.slides, 1):
        lines = []
        for shp in slide.shapes:
            if shp.has_text_frame:
                lines += [p.text for p in shp.text_frame.paragraphs if p.text.strip()]
            elif getattr(shp, "has_table", False) and shp.has_table:
                for row in shp.table.rows:
                    lines.append("｜".join(c.text.strip() for c in row.cells))
        if slide.has_notes_slide:
            note = slide.notes_slide.notes_text_frame.text.strip()
            if note:
                lines.append(f"（備註）{note}")
        out.append(f"【投影片 {i}】\n" + "\n".join(lines))
    return "\n".join(out)


def _b64(b: bytes) -> str:
    return base64.standard_b64encode(b).decode("ascii")


def content_blocks(uploads: list[Upload], label: str) -> tuple[list[dict], list[str]]:
    """把上傳檔案轉成 Claude 內容區塊。回傳 (blocks, warnings)。"""
    blocks: list[dict] = []
    warnings: list[str] = []
    for i, up in enumerate(uploads, 1):
        head = {"type": "text", "text": f"{label} #{i}：{up.name}"}
        try:
            if up.kind == "image":
                blocks += [head, {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": _b64(to_jpeg(up.data, 1280, 80))}}]
            elif up.kind == "pdf":
                if len(up.data) > MAX_PDF_BYTES:
                    warnings.append(f"{up.name} 超過 25MB，AI 不讀取此檔")
                    continue
                blocks += [head, {"type": "document", "source": {
                    "type": "base64", "media_type": "application/pdf", "data": _b64(up.data)}}]
            elif up.kind == "docx":
                blocks += [head, {"type": "text", "text": docx_text(up.data)[:MAX_TEXT]}]
            elif up.kind == "pptx":
                blocks += [head, {"type": "text", "text": pptx_text(up.data)[:MAX_TEXT]}]
            elif up.kind == "text":
                blocks += [head, {"type": "text", "text": up.data.decode("utf-8", "replace")[:MAX_TEXT]}]
            else:
                warnings.append(f"{up.name} 格式不支援（請改存成 PDF、PPTX 或 DOCX），AI 不讀取此檔")
        except Exception as e:  # 單一檔案壞掉不影響其他檔案
            warnings.append(f"{up.name} 讀取失敗：{e}")
    return blocks, warnings


def safe_name(s: str, limit: int = 40) -> str:
    bad = '\\/:*?"<>|\n\r\t'
    s = "".join("_" if ch in bad else ch for ch in s).strip()
    return s[:limit] or "未命名"
