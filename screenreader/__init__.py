"""ゲーム画面のスクリーンショットから、パーティの情報を読み取る（ルールベース）。

外部のAPIには依存せず、端末内のOCRと図鑑の辞書・実数値の整合性チェックで読み取る。
"""
from .team_screen import parse_team_screens  # noqa: F401
