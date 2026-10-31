"""Apps Script 橋接：在雲端硬碟建立教師資料夾，存 Word、Google 文件與 PDF。"""
from __future__ import annotations

import base64

import requests


class DriveError(RuntimeError):
    pass


class Drive:
    def __init__(self, url: str, secret: str):
        self.url = url
        self.secret = secret

    def _call(self, action: str, timeout: int = 300, **params):
        try:
            r = requests.post(self.url, json={"secret": self.secret, "action": action, **params}, timeout=timeout)
        except requests.RequestException as e:
            raise DriveError(f"連不上雲端硬碟服務：{e}") from e
        try:
            body = r.json()
        except ValueError as e:
            raise DriveError(
                f"雲端硬碟服務回傳格式錯誤（HTTP {r.status_code}）。"
                "常見原因：照片太大，或 Apps Script 部署的存取權不是「任何人」。"
            ) from e
        if not body.get("ok"):
            raise DriveError(f"雲端硬碟服務錯誤：{body.get('error')}")
        return body.get("result")

    def ping(self):
        return self._call("ping", timeout=30)

    def publish(self, folder: str, name: str, docx: bytes, photos: list[tuple[str, bytes]]) -> dict:
        res = self._call(
            "publish", folder=folder, name=name,
            docx=base64.b64encode(docx).decode("ascii"),
            photos=[{"name": n, "base64": base64.b64encode(b).decode("ascii")} for n, b in photos],
        )
        res["pdf"] = base64.b64decode(res["pdf"]) if res.get("pdf") else None
        return res
