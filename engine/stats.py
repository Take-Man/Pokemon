"""実数値計算（ポケモンチャンピオンズ仕様）。

- Lv50固定、個体値は廃止（従来の31相当）
- 能力ポイント(SP): 合計66、1ステータス最大32、1ポイントで実数値+1
- HP = 種族値 + SP + 75
- その他 = floor((種族値 + SP + 20) × 性格補正)
  （Pokémon Showdown champions mod の statModify と同じ式）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .data import STATS, dex

SP_TOTAL = 66
SP_MAX = 32


def nature_mult(nature_id: str | None, stat: str) -> float:
    if not nature_id:
        return 1.0
    n = dex().natures.get(nature_id)
    if not n or not n["plus"]:
        return 1.0
    if n["plus"] == stat:
        return 1.1
    if n["minus"] == stat:
        return 0.9
    return 1.0


def calc_stat(base: int, sp: int, stat: str, nature_id: str | None = None) -> int:
    if stat == "hp":
        return base + sp + 75
    raw = base + sp + 20
    m = nature_mult(nature_id, stat)
    if m == 1.1:
        return raw * 110 // 100
    if m == 0.9:
        return raw * 90 // 100
    return raw


def validate_sp(sp: dict[str, int]) -> list[str]:
    errs = []
    total = sum(sp.get(s, 0) for s in STATS)
    if total > SP_TOTAL:
        errs.append(f"能力ポイント合計が{total}（上限{SP_TOTAL}）")
    for s in STATS:
        v = sp.get(s, 0)
        if v < 0 or v > SP_MAX:
            errs.append(f"{s}の能力ポイントが{v}（0〜{SP_MAX}）")
    return errs


@dataclass
class Build:
    """1体分の育成情報。"""
    species: str
    nature: str | None = None
    sp: dict[str, int] = field(default_factory=dict)
    ability: str | None = None
    item: str | None = None
    moves: list[str] = field(default_factory=list)

    def species_data(self) -> dict:
        return dex().pokemon[self.species]

    def stats(self) -> dict[str, int]:
        base = self.species_data()["baseStats"]
        return {s: calc_stat(base[s], self.sp.get(s, 0), s, self.nature) for s in STATS}


# 素早さ帯の定番表記
def speed_variants(base_spe: int) -> dict[str, int]:
    return {
        "最速": calc_stat(base_spe, SP_MAX, "spe", "timid"),
        "準速": calc_stat(base_spe, SP_MAX, "spe", "hardy"),
        "無振り": calc_stat(base_spe, 0, "spe", "hardy"),
        "最遅": calc_stat(base_spe, 0, "spe", "brave"),
    }


def rank_mult(stage: int) -> float:
    stage = max(-6, min(6, stage))
    return (2 + stage) / 2 if stage >= 0 else 2 / (2 - stage)


def effective_speed(spe: int, stage: int = 0, *, scarf: bool = False, tailwind: bool = False,
                    paralysis: bool = False, ability_x2: bool = False, quick_feet: bool = False,
                    iron_ball: bool = False) -> int:
    """Showdown と同じく、ランク→補正の連結（四捨五入、0.5は切り捨て）→まひ半減（切り捨て）の順。"""
    v = int(spe * rank_mult(stage))
    mod = 4096
    for on, m in ((scarf, 6144), (iron_ball, 2048), (quick_feet, 6144), (ability_x2, 8192), (tailwind, 8192)):
        if on:  # ability_x2: すいすい・ようりょくそ・すなかき・ゆきかき・サーフテール・かるわざ
            mod = (mod * m + 2048) >> 12
    if mod != 4096:
        x = v * mod / 4096
        v = int(x) + (1 if x - int(x) > 0.5 else 0)
    if paralysis:
        v = v * 50 // 100
    return v
