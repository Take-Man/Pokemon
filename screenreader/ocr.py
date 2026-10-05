"""OCRバックエンド（差し替え可能）。macOS は Vision、それ以外は tesseract（jpn）。"""
from __future__ import annotations

import io
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


_cached: OCR | None = None


def get_backend(prefer: str | None = None) -> OCR:
    global _cached
    if _cached and not prefer:
        return _cached
    order = [prefer] if prefer else ["vision", "tesseract"]
    errs = []
    for n in order:
        try:
            b = VisionOCR() if n == "vision" else TesseractOCR()
            if n == "tesseract" and not b.has_jpn:
                raise OCRUnavailable("tesseract の日本語データ(jpn)が無い")
            if not prefer:
                _cached = b
            return b
        except OCRUnavailable as e:
            errs.append(f"{n}: {e}")
    raise OCRUnavailable("使えるOCRが無い（" + " / ".join(errs) + "）")
