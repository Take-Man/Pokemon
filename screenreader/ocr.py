"""OCRバックエンド（差し替え可能）。macOS は Vision、それ以外は tesseract（jpn）、サービス版は Google Cloud Vision。"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


class OCRUnavailable(RuntimeError):
    pass


@dataclass
class Line:
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class OCR:
    name = "base"

    def lines(self, img: Image.Image) -> list[Line]:  # 日本語を含む行の読み取り
        raise NotImplementedError

    def number(self, img: Image.Image) -> int | None:  # 数字だけの小領域
        raise NotImplementedError

    # まとめて読む。既定は1枚ずつ。呼び出しごとに料金がかかるOCR（Google）は、1枚の画像に並べて1回で読む
    def lines_many(self, imgs: list[Image.Image]) -> list[list[Line]]:
        return [self.lines(i) for i in imgs]

    def numbers(self, imgs: list[Image.Image]) -> list[int | None]:
        return [self.number(i) for i in imgs]


class VisionOCR(OCR):
    name = "macos-vision"

    def __init__(self):
        if sys.platform != "darwin":
            raise OCRUnavailable("macOS ではない")
        try:
            import Foundation  # noqa: F401
            import Vision  # noqa: F401
        except ImportError as e:
            raise OCRUnavailable("pyobjc-framework-Vision が無い") from e

    def _run(self, img: Image.Image, langs, accurate=True):
        import Foundation
        import Vision

        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        raw = buf.getvalue()
        data = Foundation.NSData.dataWithBytes_length_(raw, len(raw))
        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate if accurate
                                 else Vision.VNRequestTextRecognitionLevelFast)
        req.setRecognitionLanguages_(list(langs))
        req.setUsesLanguageCorrection_(False)
        ok, err = handler.performRequests_error_([req], None)
        if not ok:
            raise OCRUnavailable(str(err))
        W, H = img.size
        out = []
        for r in req.results() or []:
            c = r.topCandidates_(1)[0]
            bb = r.boundingBox()
            out.append(Line(str(c.string()), float(c.confidence()), round(bb.origin.x * W),
                            round((1 - bb.origin.y - bb.size.height) * H), round(bb.size.width * W), round(bb.size.height * H)))
        return out

    def lines(self, img):
        return self._run(img, ("ja-JP", "en-US"))

    def number(self, img):
        for ls in (self._run(img, ("en-US",)),):
            txt = "".join(l.text for l in sorted(ls, key=lambda l: l.x))
            m = re.findall(r"\d+", txt)
            if m:
                return int(m[0])
        return None


class TesseractOCR(OCR):
    name = "tesseract"

    def __init__(self):
        if not shutil.which("tesseract"):
            raise OCRUnavailable("tesseract が無い")
        langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout
        self.has_jpn = "jpn" in langs.split()

    def _tsv(self, img: Image.Image, args: list[str]):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.png"
            img.convert("RGB").save(p)
            res = subprocess.run(["tesseract", str(p), "stdout", *args, "tsv"], capture_output=True, text=True)
        return res.stdout

    def lines(self, img):
        if not self.has_jpn:
            raise OCRUnavailable("tesseract の日本語データ(jpn)が無い（brew install tesseract-lang）")
        rows = [r.split("\t") for r in self._tsv(img, ["-l", "jpn", "--psm", "11"]).splitlines()[1:]]
        out = []
        for r in rows:
            if len(r) >= 12 and r[11].strip() and float(r[10]) >= 0:
                out.append(Line(r[11].strip(), float(r[10]) / 100, int(r[6]), int(r[7]), int(r[8]), int(r[9])))
        return out

    def number(self, img):
        txt = self._tsv(img, ["-l", "eng", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789"])
        for r in txt.splitlines()[1:]:
            c = r.split("\t")
            if len(c) >= 12 and c[11].strip().isdigit():
                return int(c[11].strip())
        return None


class GoogleVisionOCR(OCR):
    """Google Cloud Vision API（DOCUMENT_TEXT_DETECTION）。環境変数 GOOGLE_VISION_API_KEY が要る。

    呼び出し1回ごとに料金がかかるので、lines_many・numbers は小さな画像を1枚に並べて（モザイク）1回で読み、
    読めた語をそれぞれの枠に戻す。取り込み1回（2枚）でおよそ3〜5回の呼び出しになる。
    """
    name = "google-vision"
    ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
    MOSAIC_W = 2000  # モザイクの幅（px）
    GAP = 40  # 枠どうしの間（語が隣の枠にまたがらないように）

    def __init__(self, key: str | None = None, post=None):
        self.key = key or os.environ.get("GOOGLE_VISION_API_KEY")
        if not self.key:
            raise OCRUnavailable("GOOGLE_VISION_API_KEY が無い")
        self._post = post or self._http_post  # テストでは差し替える
        self.calls = 0

    def _http_post(self, body: dict) -> dict:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(f"{self.ENDPOINT}?key={self.key}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise OCRUnavailable(f"Google Cloud Vision: HTTP {e.code} {e.read()[:200]!r}") from e
        except OSError as e:
            raise OCRUnavailable(f"Google Cloud Vision に接続できない: {e}") from e

    def _words(self, img: Image.Image, hints: tuple[str, ...]) -> list[Line]:
        """1回の呼び出しで、語ごとの文字・確からしさ・位置を返す。"""
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "PNG")
        body = {"requests": [{"image": {"content": base64.b64encode(buf.getvalue()).decode()},
                              "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
                              "imageContext": {"languageHints": list(hints)}}]}
        self.calls += 1
        res = (self._post(body).get("responses") or [{}])[0]
        if res.get("error"):
            raise OCRUnavailable(f"Google Cloud Vision: {res['error'].get('message')}")
        out = []
        for page in (res.get("fullTextAnnotation") or {}).get("pages", []):
            for block in page.get("blocks", []):
                for para in block.get("paragraphs", []):
                    for w in para.get("words", []):
                        text = "".join(sy.get("text", "") for sy in w.get("symbols", []))
                        vs = (w.get("boundingBox") or {}).get("vertices") or []
                        if not text or not vs:
                            continue
                        xs, ys = [v.get("x", 0) for v in vs], [v.get("y", 0) for v in vs]
                        out.append(Line(text, float(w.get("confidence", 0.9)), min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)))
        return out

    @staticmethod
    def _join_lines(words: list[Line]) -> list[Line]:
        """語を行にまとめる: 高さの半分以上重なり、間が文字の高さほどまでの語を左から順につなぐ。"""
        lines: list[list[Line]] = []
        for w in sorted(words, key=lambda w: (w.x, w.y)):
            for ln in lines:
                last = ln[-1]
                overlap = min(last.y + last.h, w.y + w.h) - max(last.y, w.y)
                gap = w.x - (last.x + last.w)
                if overlap >= 0.5 * min(last.h, w.h) and -0.5 * w.h <= gap <= 0.9 * max(last.h, w.h):
                    ln.append(w)
                    break
            else:
                lines.append([w])
        out = []
        for ln in lines:
            text = ""
            for w in ln:
                if text and text[-1].isascii() and text[-1].isalnum() and w.text[0].isascii() and w.text[0].isalnum():
                    text += " "
                text += w.text
            x0, y0 = min(w.x for w in ln), min(w.y for w in ln)
            x1, y1 = max(w.x + w.w for w in ln), max(w.y + w.h for w in ln)
            out.append(Line(text, sum(w.conf for w in ln) / len(ln), x0, y0, x1 - x0, y1 - y0))
        return out

    def _mosaic(self, imgs: list[Image.Image]) -> tuple[Image.Image, list[tuple[int, int, int, int]]]:
        """画像を左から右・上から下に並べた1枚と、それぞれの位置。"""
        boxes, x, y, row_h, width = [], self.GAP, self.GAP, 0, self.GAP
        for im in imgs:
            if x > self.GAP and x + im.width + self.GAP > self.MOSAIC_W:
                x, y, row_h = self.GAP, y + row_h + self.GAP, 0
            boxes.append((x, y, x + im.width, y + im.height))
            x += im.width + self.GAP
            row_h = max(row_h, im.height)
            width = max(width, x)
        canvas = Image.new("RGB", (width, y + row_h + self.GAP), (255, 255, 255))
        for im, b in zip(imgs, boxes):
            canvas.paste(im.convert("RGB"), b[:2])
        return canvas, boxes

    def _per_cell(self, imgs: list[Image.Image], hints: tuple[str, ...]) -> list[list[Line]]:
        if not imgs:
            return []
        canvas, boxes = self._mosaic(imgs)
        cells: list[list[Line]] = [[] for _ in imgs]
        for w in self._words(canvas, hints):
            for k, (x0, y0, x1, y1) in enumerate(boxes):
                if x0 <= w.cx <= x1 and y0 <= w.cy <= y1:
                    cells[k].append(Line(w.text, w.conf, w.x - x0, w.y - y0, w.w, w.h))
                    break
        return cells

    def lines(self, img):
        return self._join_lines(self._words(img, ("ja", "en")))

    def lines_many(self, imgs):
        return [self._join_lines(ws) for ws in self._per_cell(imgs, ("ja", "en"))]

    def number(self, img):
        return self.numbers([img])[0]

    def numbers(self, imgs):
        out = []
        for ws in self._per_cell(imgs, ("en",)):
            m = re.findall(r"\d+", "".join(w.text for w in sorted(ws, key=lambda w: w.x)))
            out.append(int(m[0]) if m else None)
        return out


_cached: OCR | None = None


def get_backend(prefer: str | None = None) -> OCR:
    global _cached
    if _cached and not prefer:
        return _cached
    order = [prefer] if prefer else ["vision", "tesseract", "google"]
    errs = []
    for n in order:
        try:
            b = {"vision": VisionOCR, "tesseract": TesseractOCR, "google": GoogleVisionOCR}[n]()
            if n == "tesseract" and not b.has_jpn:
                raise OCRUnavailable("tesseract の日本語データ(jpn)が無い")
            if not prefer:
                _cached = b
            return b
        except OCRUnavailable as e:
            errs.append(f"{n}: {e}")
    raise OCRUnavailable("使えるOCRが無い（" + " / ".join(errs) + "）")
