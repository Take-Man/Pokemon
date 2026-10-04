"""ダメージ計算（第9世代の計算式、シングル前提）。

対応範囲は docs/spec.md の「ダメージ計算」を参照。対応外の効果は bp_override / 補正倍率の手入力で吸収する。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .data import dex, to_id
from .stats import Build, rank_mult

# ---------------------------------------------------------------------------
# 丸め
# ---------------------------------------------------------------------------


def poke_round(x: float) -> int:
    """五捨五超入（0.5ちょうどは切り捨て）。"""
    i = int(x)
    return i + 1 if x - i > 0.5 else i


def chain(mods: list[int]) -> int:
    """4096基準の補正を連結する。"""
    m = 4096
    for x in mods:
        m = (m * x + 2048) >> 12
    return m


def apply_mod(v: int, mod4096: int) -> int:
    return poke_round(v * mod4096 / 4096)


# ---------------------------------------------------------------------------
# 入力
# ---------------------------------------------------------------------------


@dataclass
class Side:
    build: Build
    boosts: dict[str, int] = field(default_factory=dict)  # atk/def/spa/spd/spe
    status: Optional[str] = None  # brn/par/psn/tox/slp/frz
    hp_percent: float = 100.0
    reflect: bool = False
    light_screen: bool = False
    aurora_veil: bool = False
    ability_active: bool = True  # もうか等の発動条件や、特性無効化を手動で切る
    item_consumed: bool = False
    supreme_overlord: int = 0  # そうだいしょう: 倒れた味方数


@dataclass
class Field:
    weather: Optional[str] = None  # sun/rain/sand/snow
    terrain: Optional[str] = None  # electric/grassy/psychic/misty


@dataclass
class Options:
    crit: bool = False
    bp_override: Optional[int] = None
    type_override: Optional[str] = None
    hits: Optional[int] = None  # 連続技の命中回数
    extra_final_mod: float = 1.0  # 未対応効果の手入力補正
    defender_has_item: Optional[bool] = None  # はたきおとす用（Noneならbuild.itemで判定）


# ---------------------------------------------------------------------------
# 定義テーブル
# ---------------------------------------------------------------------------

TYPE_ITEMS = {
    "blackbelt": "Fighting", "blackglasses": "Dark", "charcoal": "Fire", "dragonfang": "Dragon",
    "fairyfeather": "Fairy", "hardstone": "Rock", "magnet": "Electric", "metalcoat": "Steel",
    "miracleseed": "Grass", "mysticwater": "Water", "nevermeltice": "Ice", "poisonbarb": "Poison",
    "sharpbeak": "Flying", "silkscarf": "Normal", "silverpowder": "Bug", "softsand": "Ground",
    "spelltag": "Ghost", "twistedspoon": "Psychic",
}
RESIST_BERRIES = {
    "occaberry": "Fire", "passhoberry": "Water", "wacanberry": "Electric", "rindoberry": "Grass",
    "yacheberry": "Ice", "chopleberry": "Fighting", "kebiaberry": "Poison", "shucaberry": "Ground",
    "cobaberry": "Flying", "payapaberry": "Psychic", "tangaberry": "Bug", "chartiberry": "Rock",
    "kasibberry": "Ghost", "habanberry": "Dragon", "colburberry": "Dark", "babiriberry": "Steel",
    "roseliberry": "Fairy", "chilanberry": "Normal",
}
ATE_ABILITIES = {"aerilate": "Flying", "pixilate": "Fairy", "refrigerate": "Ice", "galvanize": "Electric",
                 "dragonize": "Dragon"}
PINCH_ABILITIES = {"blaze": "Fire", "torrent": "Water", "overgrow": "Grass", "swarm": "Bug"}
IMMUNITY_ABILITIES = {
    "levitate": "Ground", "eelevate": "Ground", "flashfire": "Fire", "wellbakedbody": "Fire", "waterabsorb": "Water",
    "stormdrain": "Water", "dryskin": "Water", "voltabsorb": "Electric", "lightningrod": "Electric",
    "motordrive": "Electric", "sapsipper": "Grass", "eartheater": "Ground",
}
BREAKABLE_IGNORED_BY_MOLD = True
MOLD_BREAKERS = {"moldbreaker", "teravolt", "turboblaze"}
WEIGHT_BP_TARGET = [(200, 120), (100, 100), (50, 80), (25, 60), (10, 40), (0, 20)]  # くさむすび/けたぐり
BURN_IMMUNE_ABILITIES = {"waterveil", "waterbubble", "thermalexchange"}
MIMICRY_TYPE = {"electric": "Electric", "grassy": "Grass", "misty": "Fairy", "psychic": "Psychic"}
FIXED_UNSUPPORTED = {"endeavor", "counter", "mirrorcoat", "metalburst", "comeuppance", "bide", "fling",
                     "fissure", "sheercold", "guillotine", "horndrill", "naturesmadness", "psywave"}
SPECIAL_PHYSICAL_DEF = {"psyshock", "psystrike", "secretsword"}


# ---------------------------------------------------------------------------
# 結果
# ---------------------------------------------------------------------------


@dataclass
class Result:
    rolls: list[int]
    defender_hp: int
    move: dict
    move_type: str
    category: str
    effectiveness: float
    base_power: int
    notes: list[str]
    hits: int = 1
    hit_rolls: Optional[list[list[int]]] = None  # 1発ごとの16乱数（連続技・おやこあい）。None なら rolls が1発分

    def outcomes(self) -> dict[int, float]:
        """1回使ったときの合計ダメージの分布（1発ごとに乱数を独立に引く）。"""
        dist = {0: 1.0}
        for hr in self.hit_rolls or [self.rolls]:
            p = 1 / len(hr)
            nd: dict[int, float] = {}
            for s, w in dist.items():
                for r in hr:
                    nd[s + r] = nd.get(s + r, 0) + w * p
            dist = nd
        return dist

    @property
    def min(self) -> int:
        return self.rolls[0]

    @property
    def max(self) -> int:
        return self.rolls[-1]

    def percent(self) -> tuple[float, float]:
        return (round(self.min / self.defender_hp * 100, 1), round(self.max / self.defender_hp * 100, 1))

    def ko_chance(self, n: int, current_hp: Optional[int] = None) -> float:
        """n回使って倒せる確率（乱数の組み合わせを全列挙。回復・急所ブレは考慮しない）。"""
        hp = current_hp if current_hp is not None else self.defender_hp
        if not self.rolls or self.max == 0:
            return 0.0
        one = self.outcomes()
        dist = {0: 1.0}
        for _ in range(n):
            nd: dict[int, float] = {}
            for s, w in dist.items():
                for r, q in one.items():
                    k = min(s + r, hp)
                    nd[k] = nd.get(k, 0) + w * q
            dist = nd
        return sum(w for s, w in dist.items() if s >= hp)

    def ko_label(self, current_hp: Optional[int] = None) -> str:
        if self.max == 0:
            return "ダメージなし"
        for n in range(1, 6):
            c = self.ko_chance(n, current_hp)
            if c >= 1.0:
                return f"確定{n}発"
            if c > 0:
                return f"乱数{n}発({c * 100:.1f}%)"
        return "6発以上"

    def to_dict(self, current_hp: Optional[int] = None) -> dict:
        lo, hi = self.percent()
        return {
            "move": self.move["ja"], "move_id": self.move["id"], "type": self.move_type, "category": self.category,
            "base_power": self.base_power, "effectiveness": self.effectiveness, "hits": self.hits,
            "min": self.min, "max": self.max, "defender_hp": self.defender_hp,
            "min_pct": lo, "max_pct": hi, "ko": self.ko_label(current_hp), "rolls": self.rolls, "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# 本体
# ---------------------------------------------------------------------------


def type_effectiveness(move_type: str, def_types: list[str]) -> float:
    chart = dex().type_chart
    e = 1.0
    for t in def_types:
        e *= chart[move_type][t]
    return e


def _item(side: Side) -> str:
    """効果を発揮する持ち物。ぶきよう（Klutz）なら持ち物の効果は無い。"""
    if side.item_consumed or not side.build.item or _ability(side) == "klutz":
        return ""
    return to_id(side.build.item)


def _ability(side: Side) -> str:
    return to_id(side.build.ability) if side.build.ability and side.ability_active else ""


WEATHER_NEGATE = {"cloudnine", "airlock"}


def _weather(fld: "Field", *sides: Side) -> Optional[str]:
    """ノーてんきの場合は天候なし。"""
    if any(_ability(s) in WEATHER_NEGATE for s in sides):
        return None
    return fld.weather


def battle_speed(side: Side, fld: Optional["Field"] = None, foe: Optional[Side] = None) -> int:
    """場の状態込みの素早さ（ランク・スカーフ・まひ・天候/フィールドの特性・かるわざ・はやあし）。"""
    from .stats import effective_speed
    fld = fld or Field()
    ab, it = _ability(side), _item(side)
    w = _weather(fld, side, *([foe] if foe else []))
    x2 = (ab == "swiftswim" and w == "rain") or (ab == "chlorophyll" and w == "sun") \
        or (ab == "sandrush" and w == "sand") or (ab == "slushrush" and w == "snow") \
        or (ab == "surgesurfer" and fld.terrain == "electric") \
        or (ab == "unburden" and side.item_consumed and bool(side.build.item))
    quick = ab == "quickfeet" and bool(side.status)
    return effective_speed(side.build.stats()["spe"], side.boosts.get("spe", 0), scarf=it == "choicescarf",
                           paralysis=side.status == "par" and not quick, ability_x2=x2, quick_feet=quick,
                           iron_ball=it == "ironball")


def _speed(side: Side, fld: "Field") -> int:
    return battle_speed(side, fld)


FORECAST_FORME = {"sun": "castformsunny", "rain": "castformrainy", "snow": "castformsnowy"}


def _types(side: Side, fld: "Field") -> list[str]:
    """ぎたい: フィールドに合わせたタイプ1つになる。"""
    if _ability(side) == "mimicry" and fld.terrain in MIMICRY_TYPE:
        return [MIMICRY_TYPE[fld.terrain]]
    return side.build.species_data()["types"]


def _forecast(side: Side, fld: "Field") -> Side:
    """てんきや: ポワルンは天候に合わせた姿（タイプ）で計算する。"""
    if _ability(side) != "forecast" or side.build.species_data()["baseSpecies"] != "Castform":
        return side
    forme = FORECAST_FORME.get(fld.weather or "", "castform")
    if side.build.species_data()["id"] == forme:
        return side
    return Side(**{**side.__dict__, "build": Build(**{**side.build.__dict__, "species": forme})})


def calc(attacker: Side, defender: Side, move_key: str, fld: Field | None = None,
         opt: Options | None = None) -> Result:
    D = dex()
    fld = fld or Field()
    opt = opt or Options()
    move = D.moves[move_key]
    mid = move["id"]
    notes: list[str] = []
    if move["category"] != "Status" and attacker.build.species_data()["en"] == "Aegislash" \
            and to_id(attacker.build.ability or "") == "stancechange":
        attacker = Side(**{**attacker.__dict__, "build": Build(**{**attacker.build.__dict__, "species": "aegislashblade"})})
        notes.append("バトルスイッチ: ブレードフォルムで計算")
    if attacker.status == "brn" and ("Fire" in attacker.build.species_data()["types"]
                                     or _ability(attacker) in BURN_IMMUNE_ABILITIES):
        attacker = Side(**{**attacker.__dict__, "status": None})
    # ノーてんき: 天候の効果を消す（メガソルの「自分の攻撃は晴れ扱い」は残る）
    if fld.weather and _weather(fld, attacker, defender) is None:
        fld = Field(None, fld.terrain)
        notes.append("ノーてんき: 天候の効果なし")
    attacker, defender = _forecast(attacker, fld), _forecast(defender, fld)
    atk_sp = attacker.build.species_data()
    def_sp = defender.build.species_data()
    a_types, d_types = _types(attacker, fld), _types(defender, fld)
    a_stats = attacker.build.stats()
    d_stats = defender.build.stats()
    a_abil, d_abil = _ability(attacker), _ability(defender)
    a_item, d_item = _item(attacker), _item(defender)
    mold = a_abil in MOLD_BREAKERS
    if mold:
        d_abil_eff = ""
        if d_abil:
            notes.append("かたやぶり: 防御側特性を無視")
    else:
        d_abil_eff = d_abil
    want_crit = opt.crit or bool(move.get("willCrit")) or (a_abil == "merciless" and defender.status in {"psn", "tox"})
    crit = want_crit and d_abil_eff not in {"shellarmor", "battlearmor"}
    if want_crit and not crit:
        notes.append("シェルアーマー系: 急所に当たらない")
    elif crit and not opt.crit and a_abil == "merciless":
        notes.append("ひとでなし: どく状態の相手には急所")
    category = move["category"]
    if category == "Status":
        return Result([0] * 16, d_stats["hp"], move, move["type"], category, 0, 0, ["変化技"])

    # ---- タイプ決定 --------------------------------------------------------
    mtype = opt.type_override or move["type"]
    ate_boost = False
    # メガソル: 自分の技は晴れとして扱う（ウェザーボール・天候の補正）
    a_weather = "sun" if a_abil == "megasol" else fld.weather
    if mid == "weatherball" and a_weather:
        mtype = {"sun": "Fire", "rain": "Water", "sand": "Rock", "snow": "Ice"}[a_weather]
    if mid == "terrainpulse" and fld.terrain:
        mtype = {"electric": "Electric", "grassy": "Grass", "psychic": "Psychic", "misty": "Fairy"}[fld.terrain]
    if mid == "ragingbull" and atk_sp["en"].startswith("Tauros-Paldea"):
        mtype = {"Tauros-Paldea-Combat": "Fighting", "Tauros-Paldea-Blaze": "Fire", "Tauros-Paldea-Aqua": "Water"}[atk_sp["en"]]
    if a_abil == "normalize":
        mtype = "Normal"
    elif a_abil in ATE_ABILITIES and move["type"] == "Normal" and mid not in {"weatherball", "terrainpulse"}:
        mtype = ATE_ABILITIES[a_abil]
        ate_boost = True
    elif a_abil == "liquidvoice" and move["flags"].get("sound"):
        mtype = "Water"

    # ---- 相性 --------------------------------------------------------------
    def_types = d_types
    contact = bool(move["flags"].get("contact")) and a_abil != "longreach" \
        and not (a_item == "punchingglove" and move["flags"].get("punch"))
    grounded_def = d_item == "ironball" or ("Flying" not in def_types and d_abil_eff not in {"levitate", "eelevate"}
                                            and d_item != "airballoon")
    eff = type_effectiveness(mtype, def_types)
    if mid == "freezedry" and "Water" in def_types:
        eff = eff / D.type_chart["Ice"]["Water"] * 2
    if mid == "flyingpress":
        eff *= type_effectiveness("Flying", def_types)
    if mtype == "Ground" and d_item == "ironball" and "Flying" in def_types:
        eff = 1.0  # くろいてっきゅう: ひこうタイプにはじめん技が等倍で当たる（Showdown と同じ）
    if mtype == "Ground" and d_item == "airballoon":
        eff = 0
        notes.append("ふうせん")
    if a_abil == "scrappy" or a_abil == "mindseye":
        if mtype in ("Normal", "Fighting") and "Ghost" in def_types:
            eff = type_effectiveness(mtype, [t for t in def_types if t != "Ghost"])
    if d_abil_eff in IMMUNITY_ABILITIES and IMMUNITY_ABILITIES[d_abil_eff] == mtype \
            and not (mtype == "Ground" and d_item == "ironball"):
        eff = 0
        notes.append(f"特性で無効: {D.ja('abilities', defender.build.ability)}")
    if d_abil_eff == "soundproof" and move["flags"].get("sound"):
        eff = 0
        notes.append("ぼうおん")
    if d_abil_eff == "bulletproof" and move["flags"].get("bullet"):
        eff = 0
        notes.append("ぼうだん")
    if d_abil_eff == "windrider" and move["flags"].get("wind"):
        eff = 0
    if d_abil_eff == "wonderguard" and eff <= 1:
        eff = 0
    prio = (move.get("priority") or 0) + (1 if a_abil == "galewings" and mtype == "Flying"
                                           and attacker.hp_percent >= 100 else 0)
    if fld.terrain == "psychic" and prio > 0 and grounded_def and eff != 0:
        eff = 0
        notes.append("サイコフィールド: 地面にいる相手に先制技は当たらない")
    if mid in {"seismictoss", "nightshade"}:
        dmg = 50 if eff != 0 else 0
        return Result([dmg] * 16, d_stats["hp"], move, mtype, category, eff, 0, notes + ["固定ダメージ"])
    if mid in {"superfang", "ruination"} and eff != 0:
        dmg = max(1, int(d_stats["hp"] * defender.hp_percent / 100) // 2)
        return Result([dmg] * 16, d_stats["hp"], move, mtype, category, eff, 0, notes + ["残りHPの半分"])
    if mid == "finalgambit" and eff != 0:
        dmg = int(a_stats["hp"] * attacker.hp_percent / 100)
        return Result([dmg] * 16, d_stats["hp"], move, mtype, category, eff, 0, notes + ["自分の残りHP分"])
    if mid in FIXED_UNSUPPORTED or move.get("ohko"):
        return Result([0] * 16, d_stats["hp"], move, mtype, category, eff, 0, notes + ["計算対象外（固定・反射・一撃技）"])
    if eff == 0:
        return Result([0] * 16, d_stats["hp"], move, mtype, category, 0, 0, notes)

    # ---- 威力 --------------------------------------------------------------
    bp = move["basePower"]
    a_hp_ratio = attacker.hp_percent / 100
    if opt.bp_override:
        bp = opt.bp_override
        notes.append(f"威力を{bp}に手動指定")
    elif mid in {"grassknot", "lowkick"}:
        w = def_sp["weightkg"]
        bp = next(v for th, v in WEIGHT_BP_TARGET if w >= th)
    elif mid in {"heavyslam", "heatcrash"}:
        r = atk_sp["weightkg"] / max(def_sp["weightkg"], 0.1)
        bp = 120 if r >= 5 else 100 if r >= 4 else 80 if r >= 3 else 60 if r >= 2 else 40
    elif mid in {"eruption", "waterspout", "dragonenergy"}:
        bp = max(1, int(150 * a_hp_ratio))
    elif mid in {"reversal", "flail"}:
        x = int(48 * a_hp_ratio)
        bp = 200 if x <= 1 else 150 if x <= 4 else 100 if x <= 9 else 80 if x <= 16 else 40 if x <= 32 else 20
    elif mid in {"storedpower", "powertrip"}:
        bp = 20 + 20 * sum(v for v in attacker.boosts.values() if v > 0)
    elif mid == "gyroball":
        bp = min(150, int(25 * _speed(defender, fld) / max(_speed(attacker, fld), 1)) + 1)
    elif mid == "electroball":
        r = _speed(attacker, fld) / max(_speed(defender, fld), 1)
        bp = 150 if r >= 4 else 120 if r >= 3 else 80 if r >= 2 else 60 if r >= 1 else 40
    elif mid == "weatherball" and a_weather:
        bp = 100
    elif mid == "terrainpulse" and fld.terrain:
        bp = 100
    elif mid in {"venoshock", "barbbarrage"} and defender.status in {"psn", "tox"}:
        bp *= 2
    elif mid in {"hex", "infernalparade"} and defender.status:
        bp *= 2
    elif mid == "facade" and attacker.status and attacker.status != "slp":
        bp *= 2
    elif mid == "acrobatics" and not (attacker.build.item and not attacker.item_consumed):  # ぶきようでも持っていれば等倍
        bp *= 2
    elif mid == "brine" and defender.hp_percent <= 50:
        bp *= 2
    elif mid == "lastrespects":
        bp = 50 + 50 * attacker.supreme_overlord
    _grounded_a = "Flying" not in a_types and to_id(attacker.build.ability or "") not in {"levitate", "eelevate"} \
        and _item(attacker) != "airballoon"
    if mid == "risingvoltage" and fld.terrain == "electric" and grounded_def:
        bp *= 2

    bp_mods: list[int] = []
    if mid == "expandingforce" and fld.terrain == "psychic" and _grounded_a:
        bp_mods.append(6144)
    if mid == "mistyexplosion" and fld.terrain == "misty" and _grounded_a:
        bp_mods.append(6144)
    # はたきおとす: ぶきようで効果が無い持ち物でも、持っていれば威力が上がる
    d_item_raw = "" if defender.item_consumed or not defender.build.item else to_id(defender.build.item)
    has_item = (opt.defender_has_item if opt.defender_has_item is not None else bool(d_item_raw))
    d_item_row = D.items.get(d_item_raw) if d_item_raw else None
    if d_item_row and d_item_row.get("megaStone"):
        has_item = False  # メガストーンははたき落とせない
    if mid == "knockoff" and has_item:
        bp_mods.append(6144)
    if ate_boost:
        bp_mods.append(4915)
    auras = {a_abil, d_abil}
    if ("fairyaura" in auras and mtype == "Fairy") or ("darkaura" in auras and mtype == "Dark"):
        bp_mods.append(3072 if "aurabreak" in auras else 5448)
    if a_abil == "technician" and bp <= 60:
        bp_mods.append(6144)
    if a_abil == "toughclaws" and contact:
        bp_mods.append(5325)
    if a_abil == "ironfist" and move["flags"].get("punch"):
        bp_mods.append(4915)
    if a_abil == "strongjaw" and move["flags"].get("bite"):
        bp_mods.append(6144)
    if a_abil == "megalauncher" and move["flags"].get("pulse"):
        bp_mods.append(6144)
    if a_abil == "sharpness" and move["flags"].get("slicing"):
        bp_mods.append(6144)
    if a_abil == "reckless" and move.get("recoil"):
        bp_mods.append(4915)
    if a_abil == "sheerforce" and move.get("hasSecondary"):
        bp_mods.append(5325)
        notes.append("ちからずく")
    if a_abil == "punkrock" and move["flags"].get("sound"):
        bp_mods.append(5325)
    if a_abil == "sandforce" and fld.weather == "sand" and mtype in ("Rock", "Ground", "Steel"):
        bp_mods.append(5325)
    if a_abil == "supremeoverlord" and attacker.supreme_overlord:
        bp_mods.append([4096, 4506, 4915, 5325, 5734, 6144][min(attacker.supreme_overlord, 5)])
    if d_abil_eff == "dryskin" and mtype == "Fire":
        bp_mods.append(5120)
    if a_item in TYPE_ITEMS and TYPE_ITEMS[a_item] == mtype:
        bp_mods.append(4915)
    if a_item == "muscleband" and category == "Physical":
        bp_mods.append(4505)
    if a_item == "wiseglasses" and category == "Special":
        bp_mods.append(4505)
    if a_item == "punchingglove" and move["flags"].get("punch"):
        bp_mods.append(4506)
    if a_item == "normalgem" and mtype == "Normal":
        bp_mods.append(5325)
    grounded_atk = "Flying" not in a_types and a_abil not in {"levitate", "eelevate"} and a_item != "airballoon"
    if fld.terrain == "electric" and mtype == "Electric" and grounded_atk:
        bp_mods.append(5325)
    if fld.terrain == "grassy" and mtype == "Grass" and grounded_atk:
        bp_mods.append(5325)
    if fld.terrain == "psychic" and mtype == "Psychic" and grounded_atk:
        bp_mods.append(5325)
    if fld.terrain == "misty" and mtype == "Dragon" and grounded_def:
        bp_mods.append(2048)
    if fld.terrain == "grassy" and mid in {"earthquake", "bulldoze"} and grounded_def:
        bp_mods.append(2048)
    bp_final = max(1, apply_mod(bp, chain(bp_mods))) if bp_mods else bp

    # ---- 攻撃・防御の実数値 -------------------------------------------------
    if mid == "shellsidearm":
        a_s, d_s = attacker.build.stats(), d_stats
        phys_score = a_s["atk"] * rank_mult(attacker.boosts.get("atk", 0)) / (d_s["def"] * rank_mult(defender.boosts.get("def", 0)))
        spec_score = a_s["spa"] * rank_mult(attacker.boosts.get("spa", 0)) / (d_s["spd"] * rank_mult(defender.boosts.get("spd", 0)))
        if phys_score > spec_score:
            category = "Physical"
            notes.append("シェルアームズ: 物理で計算")
    physical = category == "Physical"
    if mid == "bodypress":
        a_stat_key, atk_src = "def", attacker
    elif mid == "foulplay":
        a_stat_key, atk_src = "atk", defender
    else:
        a_stat_key, atk_src = ("atk" if physical else "spa"), attacker
    d_stat_key = "def" if (physical or mid in SPECIAL_PHYSICAL_DEF) else "spd"

    atk_raw = (atk_src.build.stats())[a_stat_key]
    atk_stage = atk_src.boosts.get(a_stat_key, 0)
    def_raw = d_stats[d_stat_key]
    def_stage = defender.boosts.get(d_stat_key, 0)
    if crit:
        atk_stage = max(atk_stage, 0)
        def_stage = min(def_stage, 0)
    if d_abil_eff == "unaware":
        atk_stage = 0
    if a_abil == "unaware":
        def_stage = 0
    atk_v = int(atk_raw * rank_mult(atk_stage))
    def_v = int(def_raw * rank_mult(def_stage))
    atk_mods: list[int] = []
    # 攻撃側の補正は技の使い手にかかる（イカサマでも自分の特性・持ち物）。ボディプレスは防御なので対象外
    if a_stat_key != "def":
        if a_abil == "hustle" and physical:
            atk_v = apply_mod(atk_v, 6144)  # はりきりは他の補正と連結せず直接かける
        if a_abil in {"hugepower", "purepower"} and a_stat_key == "atk":
            atk_mods.append(8192)
        if a_abil == "rockypayload" and mtype == "Rock":
            atk_mods.append(6144)
        if a_abil == "guts" and attacker.status and physical:
            atk_mods.append(6144)
        if a_abil in PINCH_ABILITIES and PINCH_ABILITIES[a_abil] == mtype and attacker.hp_percent <= 100 / 3:
            atk_mods.append(6144)
        if a_abil == "solarpower" and not physical and fld.weather == "sun":
            atk_mods.append(6144)
        if a_abil == "firemane" and mtype == "Fire":
            atk_mods.append(6144)
        if a_abil in {"steelworker", "steelyspirit"} and mtype == "Steel":
            atk_mods.append(6144)
        if a_abil == "transistor" and mtype == "Electric":
            atk_mods.append(5325)
        if a_abil == "dragonsmaw" and mtype == "Dragon":
            atk_mods.append(6144)
        if a_abil == "waterbubble" and mtype == "Water":
            atk_mods.append(8192)
        if a_abil == "gorillatactics" and physical:
            atk_mods.append(6144)
        if a_abil == "toxicboost" and physical and attacker.status in {"psn", "tox"}:
            atk_mods.append(6144)
        if a_abil == "flareboost" and not physical and attacker.status == "brn":
            atk_mods.append(6144)
        if a_item == "choiceband" and physical:
            atk_mods.append(6144)
        if a_item == "choicespecs" and not physical:
            atk_mods.append(6144)
        if a_item == "lightball" and atk_sp["baseSpecies"] == "Pikachu":
            atk_mods.append(8192)
        if d_abil_eff == "thickfat" and mtype in ("Fire", "Ice"):
            atk_mods.append(2048)
        if d_abil_eff == "waterbubble" and mtype == "Fire":
            atk_mods.append(2048)
        if d_abil_eff == "purifyingsalt" and mtype == "Ghost":
            atk_mods.append(2048)
        if d_abil_eff == "heatproof" and mtype == "Fire":
            atk_mods.append(2048)
    if atk_mods:
        atk_v = apply_mod(atk_v, chain(atk_mods))

    def_mods: list[int] = []
    if fld.weather == "sand" and "Rock" in def_types and d_stat_key == "spd":
        def_v = def_v * 3 // 2
    if fld.weather == "snow" and "Ice" in def_types and d_stat_key == "def":
        def_v = def_v * 3 // 2
    if d_abil_eff == "marvelscale" and defender.status and d_stat_key == "def":
        def_mods.append(6144)
    if d_abil_eff == "furcoat" and d_stat_key == "def":
        def_mods.append(8192)
    if d_abil_eff == "grasspelt" and fld.terrain == "grassy" and d_stat_key == "def":
        def_mods.append(6144)
    if d_item == "assaultvest" and d_stat_key == "spd":
        def_mods.append(6144)
    if d_item == "eviolite":
        def_mods.append(6144)
    if def_mods:
        def_v = apply_mod(def_v, chain(def_mods))
    atk_v, def_v = max(1, atk_v), max(1, def_v)

    # ---- 基本ダメージ ------------------------------------------------------
    level = 50
    base = ((2 * level // 5 + 2) * bp_final * atk_v // def_v) // 50 + 2

    # 天候（メガソルの攻撃は晴れ扱い。ハイドロスチームは晴れで1.5倍）
    weather_mod = 4096
    if a_weather == "sun" and (mtype == "Fire" or mid == "hydrosteam"):
        weather_mod = 6144
    elif a_weather == "sun" and mtype == "Water":
        weather_mod = 2048
    elif a_weather == "rain" and mtype == "Water":
        weather_mod = 6144
    elif a_weather == "rain" and mtype == "Fire":
        weather_mod = 2048
    if a_abil == "megasol" and fld.weather != "sun" and mtype in ("Fire", "Water"):
        notes.append("メガソル: 自分の攻撃は晴れ扱い")
    if crit:
        notes.append("急所")

    stab = mtype in a_types or a_abil in {"protean", "libero"}
    stab_mod = 8192 if (stab and a_abil == "adaptability") else 6144 if stab else 4096

    final_mods: list[int] = []
    if not crit and a_abil != "infiltrator":
        if physical and (defender.reflect or defender.aurora_veil):
            final_mods.append(2048)
        elif not physical and (defender.light_screen or defender.aurora_veil):
            final_mods.append(2048)
    if d_abil_eff in {"multiscale", "shadowshield"} and defender.hp_percent >= 100:
        final_mods.append(2048)
    if d_abil_eff in {"filter", "solidrock", "prismarmor"} and eff > 1:
        final_mods.append(3072)
    if d_abil_eff == "fluffy" and contact:
        final_mods.append(2048)
    if d_abil_eff == "fluffy" and mtype == "Fire":
        final_mods.append(8192)
    if d_abil_eff == "auraguard" and contact:
        final_mods.append(2048)
    if d_abil_eff == "icescales" and not physical:
        final_mods.append(2048)
    if d_abil_eff == "punkrock" and move["flags"].get("sound"):
        final_mods.append(2048)
    if a_abil == "sniper" and crit:
        final_mods.append(6144)
    if a_abil == "tintedlens" and eff < 1:
        final_mods.append(8192)
    if a_abil == "neuroforce" and eff > 1:
        final_mods.append(5120)
    if a_item == "expertbelt" and eff > 1:
        final_mods.append(4915)
    if a_item == "lifeorb":
        final_mods.append(5324)
    if d_item in RESIST_BERRIES and RESIST_BERRIES[d_item] == mtype and (eff > 1 or mtype == "Normal"):
        ripen = d_abil == "ripen"  # じゅくせい: 効果2倍（1/4）
        final_mods.append(1024 if ripen else 2048)
        notes.append(f"{D.ja('items', defender.build.item)}で{'1/4（じゅくせい）' if ripen else '半減'}")
    if mid == "collisioncourse" or mid == "electrodrift":
        if eff > 1:
            final_mods.append(5461)
    if opt.extra_final_mod != 1.0:
        final_mods.append(round(4096 * opt.extra_final_mod))
    final_mod = chain(final_mods)

    burn = attacker.status == "brn" and physical and a_abil != "guts" and mid != "facade"

    def one_hit(b: int) -> list[int]:
        """基本ダメージ（+2済み）から16乱数。Showdown の modifyDamage と同じ順。"""
        b = apply_mod(b, weather_mod) if weather_mod != 4096 else b
        if crit:
            b = int(b * 1.5)
        out = []
        for r in range(85, 101):
            d = b * r // 100
            d = apply_mod(d, stab_mod)
            d = int(d * eff)
            if burn:
                d = apply_mod(d, 2048)
            d = apply_mod(d, final_mod)
            out.append(max(1, d))
        return out

    rolls = one_hit(base)

    # ---- 連続技 ------------------------------------------------------------
    # 1発ごとに乱数を独立に引く。rolls は同じ乱数どうしの合計（最小・最大は正確）、確定数は全組み合わせで出す
    hits = 1
    mh = move.get("multihit")
    bond = a_abil == "parentalbond" and not mh
    if bond:
        hits = 1 if opt.hits == 1 else 2  # おやこあいの回数は当たった発数（1発目で倒した等なら1）
    elif opt.hits:
        hits = opt.hits
    elif mh:
        if isinstance(mh, list):
            hits = mh[1] if a_abil == "skilllink" else (4 if a_item == "loadeddice" else 3 if mh == [2, 5] else mh[0])
        else:
            hits = mh
    hit_rolls = None
    if bond and hits == 2:
        hit_rolls = [rolls, one_hit(apply_mod(base, 1024))]  # 2発目は基本ダメージの1/4
        notes.append("おやこあい（2発目は1/4）")
    elif hits > 1:
        hit_rolls = [rolls] * hits
        notes.append(f"{hits}回ヒット")
    if hit_rolls:
        rolls = [sum(x) for x in zip(*hit_rolls)]

    return Result(sorted(rolls), d_stats["hp"], move, mtype, category, eff, bp_final, notes, hits,
                  hit_rolls=hit_rolls)
