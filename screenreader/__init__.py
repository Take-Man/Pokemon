"""ゲーム画面のスクリーンショットから、パーティの情報を読み取る（ルールベース）。

OCRで読んだ文字を、図鑑の辞書・実数値の整合性チェックで確かめる。OCRはローカル版は端末内（macOS の Vision・tesseract）、
サービス版は Google Cloud Vision（呼び出しをまとめて1回の取り込みで3〜4回）。
"""
from .team_screen import parse_team_screens  # noqa: F401
