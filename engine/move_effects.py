"""変化技の効果文（ダメ計の結果欄に出す）。

- EFFECT_JA: 技ごとの短い説明（自作の要約。ゲーム内の説明文ではない）
- describe(): 説明に、その対面での補足（無効になる理由・回復量の実数・ランクの変化・設置技の削り量など）を足す
"""
from __future__ import annotations

from typing import Optional

from .damage import Field, Side, type_effectiveness
from .data import dex, to_id

EFFECT_JA: dict[str, str] = {
    # 守る系
    "protect": "そのターン相手の技を防ぐ。連続で使うと失敗しやすい",
    "detect": "そのターン相手の技を防ぐ。連続で使うと失敗しやすい",
    "banefulbunker": "そのターン相手の技を防ぎ、直接攻撃してきた相手をどく状態にする",
    "kingsshield": "そのターン相手の攻撃技を防ぎ、直接攻撃してきた相手の攻撃を1段階下げる",
    "spikyshield": "そのターン相手の技を防ぎ、直接攻撃してきた相手に最大HPの1/8のダメージ",
    "endure": "そのターンはHPが1残る",
    "quickguard": "そのターン味方への先制技を防ぐ",
    "wideguard": "そのターン味方への全体技を防ぐ",
    # 積み技
    "swordsdance": "自分の攻撃を2段階上げる",
    "nastyplot": "自分の特攻を2段階上げる",
    "dragondance": "自分の攻撃と素早さを1段階ずつ上げる",
    "calmmind": "自分の特攻と特防を1段階ずつ上げる",
    "bulkup": "自分の攻撃と防御を1段階ずつ上げる",
    "quiverdance": "自分の特攻・特防・素早さを1段階ずつ上げる",
    "shellsmash": "自分の攻撃・特攻・素早さを2段階上げ、防御・特防を1段階下げる",
    "shiftgear": "自分の素早さを2段階、攻撃を1段階上げる",
    "coil": "自分の攻撃・防御・命中率を1段階ずつ上げる",
    "growth": "自分の攻撃と特攻を1段階ずつ上げる（晴れなら2段階ずつ）",
    "howl": "自分の攻撃を1段階上げる",
    "agility": "自分の素早さを2段階上げる",
    "rockpolish": "自分の素早さを2段階上げる",
    "amnesia": "自分の特防を2段階上げる",
    "acidarmor": "自分の防御を2段階上げる",
    "irondefense": "自分の防御を2段階上げる",
    "shelter": "自分の防御を2段階上げる",
    "cottonguard": "自分の防御を3段階上げる",
    "cosmicpower": "自分の防御と特防を1段階ずつ上げる",
    "charge": "自分の特防を1段階上げ、次に使うでんき技の威力を2倍にする",
    "clangoroussoul": "HPを最大HPの1/3減らし、自分の全能力を1段階ずつ上げる",
    "noretreat": "自分の全能力を1段階ずつ上げる。以後交代できない",
    "doubleteam": "自分の回避率を1段階上げる",
    "minimize": "自分の回避率を2段階上げる",
    "focusenergy": "自分の急所ランクを2段階上げる",
    "stockpile": "たくわえを1つ増やし、防御と特防を1段階ずつ上げる（3回まで）",
    "bellydrum": "HPを最大HPの半分減らし、攻撃を最大（+6）まで上げる",
    "stuffcheeks": "持っているきのみを食べ、防御を2段階上げる",
    "tidyup": "場の設置物とみがわりを消し、自分の攻撃と素早さを1段階ずつ上げる",
    "acupressure": "ランダムな能力を2段階上げる",
    "powertrick": "自分の攻撃と防御の実数値を入れ替える",
    "magnetrise": "5ターン、じめん技を受けなくなる",
    "aquaring": "毎ターン終わりに最大HPの1/16回復する",
    "ingrain": "毎ターン終わりに最大HPの1/16回復する。以後交代できない",
    # 回復
    "recover": "最大HPの半分回復する",
    "slackoff": "最大HPの半分回復する",
    "milkdrink": "最大HPの半分回復する",
    "roost": "最大HPの半分回復する。そのターンはひこうタイプを失う",
    "moonlight": "HPを回復する（通常1/2、晴れ2/3、それ以外の天気1/4）",
    "morningsun": "HPを回復する（通常1/2、晴れ2/3、それ以外の天気1/4）",
    "synthesis": "HPを回復する（通常1/2、晴れ2/3、それ以外の天気1/4）",
    "lifedew": "自分と味方のHPを最大HPの1/4回復する",
    "wish": "次のターンの終わりに、その場のポケモンが使用者の最大HPの半分回復する",
    "rest": "HPと状態異常を全回復し、2ターン眠る",
    "swallow": "たくわえた数に応じて回復する（1つ1/4、2つ1/2、3つ全回復）",
    "healingwish": "自分は倒れ、次に出るポケモンのHPと状態異常を全回復する",
    "healpulse": "相手のHPを最大HPの半分回復する",
    "strengthsap": "相手の攻撃の実数値ぶん回復し、相手の攻撃を1段階下げる",
    "painsplit": "自分と相手の残りHPを合計して半分ずつに分け合う",
    "healbell": "味方全員の状態異常を治す",
    # 状態異常
    "thunderwave": "相手をまひ状態にする",
    "stunspore": "相手をまひ状態にする",
    "glare": "相手をまひ状態にする",
    "willowisp": "相手をやけど状態にする",
    "toxic": "相手をもうどく状態にする",
    "poisonpowder": "相手をどく状態にする",
    "toxicthread": "相手をどく状態にし、素早さを2段階下げる",
    "hypnosis": "相手をねむり状態にする",
    "sing": "相手をねむり状態にする",
    "sleeppowder": "相手をねむり状態にする",
    "yawn": "次のターンの終わりに相手をねむり状態にする",
    "confuseray": "相手をこんらん状態にする",
    "sweetkiss": "相手をこんらん状態にする",
    "teeterdance": "周りのポケモンをこんらん状態にする",
    "swagger": "相手の攻撃を2段階上げ、こんらん状態にする",
    "flatter": "相手の特攻を1段階上げ、こんらん状態にする",
    "attract": "異性の相手をメロメロ状態にする",
    "leechseed": "毎ターン相手の最大HPの1/8を吸い取って回復する",
    "curse": "ゴーストタイプ: HPを最大HPの半分減らし、相手に毎ターン最大HPの1/4のダメージ。それ以外: 攻撃・防御+1、素早さ-1",
    # 能力を下げる
    "charm": "相手の攻撃を2段階下げる",
    "featherdance": "相手の攻撃を2段階下げる",
    "babydolleyes": "相手の攻撃を1段階下げる",
    "nobleroar": "相手の攻撃と特攻を1段階ずつ下げる",
    "tearfullook": "相手の攻撃と特攻を1段階ずつ下げる",
    "tickle": "相手の攻撃と防御を1段階ずつ下げる",
    "screech": "相手の防御を2段階下げる",
    "faketears": "相手の特防を2段階下げる",
    "metalsound": "相手の特防を2段階下げる",
    "eerieimpulse": "相手の特攻を2段階下げる",
    "scaryface": "相手の素早さを2段階下げる",
    "cottonspore": "相手の素早さを2段階下げる",
    "stringshot": "相手の素早さを2段階下げる",
    "sweetscent": "相手の回避率を2段階下げる",
    "spicyextract": "相手の攻撃を2段階上げ、防御を2段階下げる",
    "memento": "自分は倒れ、相手の攻撃と特攻を2段階ずつ下げる",
    "partingshot": "相手の攻撃と特攻を1段階ずつ下げ、控えと交代する",
    "decorate": "味方の攻撃と特攻を2段階ずつ上げる",
    "coaching": "味方の攻撃と防御を1段階ずつ上げる",
    "aromaticmist": "味方の特防を1段階上げる",
    "dragoncheer": "味方の急所ランクを上げる",
    "helpinghand": "そのターン味方の技の威力を1.5倍にする",
    # 妨害
    "taunt": "3ターン、相手は変化技を出せない",
    "encore": "3ターン、相手は最後に使った技しか出せない",
    "disable": "4ターン、相手が最後に使った技を出せなくする",
    "torment": "相手は同じ技を連続で出せなくなる",
    "imprison": "自分が覚えている技を相手が出せなくなる",
    "spite": "相手が最後に使った技のPPを4減らす",
    "gastroacid": "相手の特性を消す",
    "worryseed": "相手の特性をふみんにする",
    "simplebeam": "相手の特性をたんじゅんにする",
    "entrainment": "相手の特性を自分と同じにする",
    "skillswap": "自分と相手の特性を入れ替える",
    "roleplay": "自分の特性を相手と同じにする",
    "soak": "相手をみずタイプ単体にする",
    "magicpowder": "相手をエスパータイプ単体にする",
    "trickortreat": "相手にゴーストタイプを追加する",
    "forestscurse": "相手にくさタイプを追加する",
    "reflecttype": "自分のタイプを相手と同じにする",
    "electrify": "そのターン相手の技をでんきタイプにする",
    "trick": "自分と相手の持ち物を入れ替える",
    "switcheroo": "自分と相手の持ち物を入れ替える",
    "block": "相手を交代できなくする",
    "meanlook": "相手を交代できなくする",
    "octolock": "相手を交代できなくし、毎ターン防御と特防を1段階ずつ下げる",
    "fairylock": "次のターン、全員が交代できない",
    "perishsong": "場のポケモン全員が3ターン後に倒れる（交代すれば解除）",
    "destinybond": "次の自分の行動までに相手の攻撃で倒れると、相手も倒れる",
    "roar": "相手を強制的に交代させる（後攻）",
    "whirlwind": "相手を強制的に交代させる（後攻）",
    "haze": "場の全員の能力ランクを元に戻す",
    "topsyturvy": "相手の能力ランクの上下を反転する",
    "psychup": "相手の能力ランクをコピーする",
    "guardswap": "自分と相手の防御・特防のランクを入れ替える",
    "powerswap": "自分と相手の攻撃・特攻のランクを入れ替える",
    "speedswap": "自分と相手の素早さの実数値を入れ替える",
    "guardsplit": "自分と相手の防御・特防の実数値を平均する",
    "powersplit": "自分と相手の攻撃・特攻の実数値を平均する",
    "transform": "相手に変身する",
    "lockon": "次のターン、自分の技が必ず当たる",
    "corrosivegas": "周りのポケモンの持ち物を使えなくする",
    "defog": "相手の回避率を1段階下げ、両者の設置物と相手の壁を消す",
    "courtchange": "自分と相手の場の設置物・壁などを入れ替える",
    "instruct": "相手に最後に使った技をもう一度使わせる",
    "afteryou": "相手をこのターン自分の直後に行動させる",
    "quash": "相手の行動をこのターンの最後にする",
    "copycat": "直前に使われた技を出す",
    "sleeptalk": "ねむり中に、覚えている技をランダムに出す",
    "recycle": "使った持ち物を復活させる",
    "teatime": "場の全員が持っているきのみを食べる",
    "followme": "そのターン相手の技を自分に引き付ける",
    "ragepowder": "そのターン相手の技を自分に引き付ける",
    "allyswitch": "味方と場所を入れ替える",
    "magneticflux": "特性プラス・マイナスの味方の防御と特防を上げる",
    # 交代
    "batonpass": "能力ランクなどを引き継いで控えと交代する",
    "shedtail": "HPを最大HPの半分減らしてみがわりを作り、控えに引き継いで交代する",
    "chillyreception": "天気を雪にして控えと交代する",
    "revivalblessing": "倒れた味方1体をHP半分で復活させる",
    "substitute": "HPを最大HPの1/4減らしてみがわりを作る",
    # 場
    "reflect": "5ターン、味方が受ける物理技のダメージを半減する",
    "lightscreen": "5ターン、味方が受ける特殊技のダメージを半減する",
    "auroraveil": "5ターン、味方が受ける物理・特殊技のダメージを半減する（雪のときのみ成功）",
    "safeguard": "5ターン、味方が状態異常・こんらんにならない",
    "tailwind": "4ターン、味方の素早さを2倍にする",
    "stealthrock": "相手の場に岩を撒く。交代で出てきた相手にいわタイプの相性に応じたダメージ",
    "spikes": "相手の場にまきびしを撒く（3回まで）。交代で出てきた地面にいる相手にダメージ",
    "toxicspikes": "相手の場にどくびしを撒く（2回まで）。交代で出てきた地面にいる相手をどく（2回でもうどく）にする",
    "stickyweb": "相手の場にねばねばネットを張る。交代で出てきた地面にいる相手の素早さを1段階下げる",
    "sunnyday": "5ターン、天気を晴れにする",
    "raindance": "5ターン、天気を雨にする",
    "sandstorm": "5ターン、天気を砂嵐にする",
    "snowscape": "5ターン、天気を雪にする",
    "electricterrain": "5ターン、エレキフィールドにする",
    "grassyterrain": "5ターン、グラスフィールドにする",
    "mistyterrain": "5ターン、ミストフィールドにする",
    "psychicterrain": "5ターン、サイコフィールドにする",
    "trickroom": "5ターン、素早さの遅いポケモンから行動する",
    "gravity": "5ターン、全員が地面にいる扱いになり、命中率が上がる",
    "magicroom": "5ターン、全員の持ち物の効果が無くなる",
    "wonderroom": "5ターン、全員の防御と特防の実数値が入れ替わる",
}

STATUS_JA = {"brn": "やけど", "par": "まひ", "psn": "どく", "tox": "もうどく", "slp": "ねむり", "frz": "こおり"}
BOOST_JA = {"atk": "攻撃", "def": "防御", "spa": "特攻", "spd": "特防", "spe": "素早さ", "accuracy": "命中率", "evasion": "回避率"}
WEATHER_ROCK = {"sunnyday": "heatrock", "raindance": "damprock", "sandstorm": "smoothrock", "snowscape": "icyrock",
                "chillyreception": "icyrock"}
WEATHER_OF = {"sunnyday": "sun", "raindance": "rain", "sandstorm": "sand", "snowscape": "snow", "chillyreception": "snow"}
STATUS_IMMUNE_ABIL = {
    "par": {"limber": "じゅうなん"},
    "slp": {"insomnia": "ふみん", "vitalspirit": "やるき", "sweetveil": "スイートベール"},
    "psn": {"immunity": "めんえき", "pastelveil": "パステルベール"},
    "brn": {"waterveil": "みずのベール", "waterbubble": "すいほう", "thermalexchange": "ねつこうかん"},
}
ALL_STATUS_IMMUNE_ABIL = {"purifyingsalt": "きよめのしお", "comatose": "ぜったいねむり"}
NO_DROP_ABIL = {"clearbody": "クリアボディ", "whitesmoke": "しろいけむり", "fullmetalbody": "メタルプロテクト"}


def _types(side: Side) -> list[str]:
    return dex().pokemon[side.build.species]["types"]


def _abil(side: Side) -> str:
    return to_id(side.build.ability or "")


def _item(side: Side) -> str:
    return "" if side.item_consumed else to_id(side.build.item or "")


def _grounded(side: Side) -> bool:
    return "Flying" not in _types(side) and _abil(side) != "levitate" and _item(side) != "airballoon"


def _hp(side: Side) -> tuple[int, int]:
    mx = side.build.stats()["hp"]
    return int(mx * side.hp_percent / 100), mx


def _ja(table: str, x: Optional[str]) -> str:
    return dex().ja(table, x) if x else ""


def _stage(cur: int, delta: int) -> int:
    return max(-6, min(6, cur + delta))


def _boost_line(who: str, side: Side, boosts: dict, from_foe: bool) -> tuple[list[str], bool]:
    """能力変化の補足。戻り値の bool は「効果なし」のとき True。"""
    notes: list[str] = []
    ab = _abil(side)
    if from_foe and any(v < 0 for v in boosts.values()):
        if ab in NO_DROP_ABIL:
            return [f"{who}の特性{NO_DROP_ABIL[ab]}で能力が下がらない"], True
        if ab == "mirrorarmor":
            return [f"{who}の特性ミラーアーマーで下がる効果を跳ね返す"], True
    mult = -1 if ab == "contrary" else 2 if ab == "simple" else 1
    parts, moved = [], False
    for k, v in boosts.items():
        d = v * mult
        cur = side.boosts.get(k, 0)
        new = _stage(cur, d)
        moved = moved or new != cur
        parts.append(f"{BOOST_JA.get(k, k)} {cur:+d}→{new:+d}")
    if mult == -1:
        notes.append(f"{who}の特性あまのじゃくで上下が逆になる")
    elif mult == 2:
        notes.append(f"{who}の特性たんじゅんで変化が2倍")
    notes.append(f"{who}のランク: " + " ".join(parts) + ("（これ以上変わらない）" if not moved else ""))
    if from_foe and any(v < 0 for v in boosts.values()):
        if ab == "defiant":
            notes.append(f"{who}の特性まけんきで攻撃+2")
        elif ab == "competitive":
            notes.append(f"{who}の特性かちきで特攻+2")
    return notes, not moved


def _status_block(st: str, mv: dict, att: Side, dfd: Side, fld: Field) -> Optional[str]:
    """状態異常が入らない理由（入るなら None）。"""
    tys, ab = _types(dfd), _abil(dfd)
    if dfd.status:
        return f"相手はすでに{STATUS_JA.get(dfd.status, dfd.status)}状態"
    if ab in ALL_STATUS_IMMUNE_ABIL:
        return f"相手の特性{ALL_STATUS_IMMUNE_ABIL[ab]}"
    key = "psn" if st == "tox" else st
    if ab in STATUS_IMMUNE_ABIL.get(key, {}):
        return f"相手の特性{STATUS_IMMUNE_ABIL[key][ab]}"
    if ab == "leafguard" and fld.weather == "sun":
        return "晴れで相手の特性リーフガードが働く"
    if key == "par" and "Electric" in tys:
        return "でんきタイプはまひにならない"
    if key == "brn" and "Fire" in tys:
        return "ほのおタイプはやけどにならない"
    if key == "psn" and ("Poison" in tys or "Steel" in tys) and _abil(att) != "corrosion":
        return "どく・はがねタイプはどくにならない"
    if _grounded(dfd):
        if fld.terrain == "misty":
            return "ミストフィールドで地面にいる相手は状態異常にならない"
        if key == "slp" and fld.terrain == "electric":
            return "エレキフィールドで地面にいる相手は眠らない"
    return None


def _residual(st: str, dfd: Side) -> str:
    _, mx = _hp(dfd)
    if st == "psn":
        return f"毎ターン最大HPの1/8（{max(1, mx // 8)}）のダメージ"
    if st == "tox":
        return f"1ターン目は最大HPの1/16（{max(1, mx // 16)}）、以後毎ターン1/16ずつ増える"
    if st == "brn":
        return f"毎ターン最大HPの1/16（{max(1, mx // 16)}）のダメージ、物理技の威力が半分"
    if st == "par":
        spe = dfd.build.stats()["spe"]
        return f"素早さ半分（{spe}→{spe // 2}、ランク補正前）、25%で行動できない"
    if st == "slp":
        return "1〜3ターン行動できない"
    return ""


def describe(att: Side, dfd: Side, move_id: str, fld: Optional[Field] = None) -> dict:
    """変化技の効果文と、その対面での補足。

    戻り値: {"text": 説明, "notes": [補足...], "fails": 失敗・無効なら理由（成功しうるなら ""）}
    """
    D = dex()
    fld = fld or Field()
    mv = D.moves[move_id]
    mid = mv["id"]
    text = EFFECT_JA.get(mid, "効果の説明なし")
    notes: list[str] = []
    fails = ""
    targets_foe = mv.get("target") in ("normal", "allAdjacent", "allAdjacentFoes", "any")
    aab, dab = _abil(att), _abil(dfd)
    atypes, dtypes = _types(att), _types(dfd)
    cur, mx = _hp(att)
    ocur, omx = _hp(dfd)

    prio = mv.get("priority") or 0
    if aab == "prankster":
        prio += 1
    if prio:
        notes.append(f"優先度{prio:+d}" + ("（いたずらごころ込み）" if aab == "prankster" else ""))
    acc = mv.get("accuracy")
    if isinstance(acc, (int, float)) and not isinstance(acc, bool) and acc < 100:
        if mid == "toxic" and "Poison" in atypes:
            notes.append("使い手がどくタイプなので必中")
        else:
            notes.append(f"命中{acc:g}%")

    # 相手に向けた技が届かない理由
    if targets_foe:
        if aab == "prankster" and "Dark" in dtypes:
            fails = "いたずらごころで出した変化技はあくタイプに無効"
        elif dab == "goodasgold":
            fails = "相手の特性おうごんのからだで無効"
        elif dab == "magicbounce" and mv["flags"].get("reflectable"):
            fails = "相手の特性マジックミラーで跳ね返される"
        elif mv["flags"].get("powder") and ("Grass" in dtypes or dab == "overcoat" or _item(dfd) == "safetygoggles"):
            fails = "くさタイプ・ぼうじん・ぼうじんゴーグルには粉の技が効かない"
        elif mv["type"] == "Electric" and mv.get("status") and (type_effectiveness("Electric", dtypes) == 0):
            fails = "じめんタイプには効かない"
        elif mv["type"] == "Electric" and mv.get("status") and dab in ("voltabsorb", "lightningrod", "motordrive"):
            fails = f"相手の特性{_ja('abilities', dfd.build.ability)}で無効"
        elif mid == "willowisp" and dab == "flashfire":
            fails = "相手の特性もらいびで無効（相手のほのお技が強くなる）"

    # 状態異常
    st = mv.get("status")
    if st and not fails:
        why = _status_block(st, mv, att, dfd, fld)
        if why:
            fails = why
        else:
            notes.append(_residual(st, dfd))
    if mid == "yawn" and not fails:
        why = _status_block("slp", mv, att, dfd, fld)
        if why:
            fails = why
    if mv.get("volatileStatus") == "confusion" and not fails:
        if dab == "owntempo":
            fails = "相手の特性マイペースで混乱しない"
        elif fld.terrain == "misty" and _grounded(dfd):
            fails = "ミストフィールドで地面にいる相手は混乱しない"
    if mid in ("taunt", "attract", "encore", "disable", "torment") and dab in ("oblivious", "aromaveil") and not fails:
        if not (mid in ("encore", "disable", "torment") and dab == "oblivious"):
            fails = f"相手の特性{_ja('abilities', dfd.build.ability)}で無効"

    # 能力変化
    boosts = mv.get("boosts") or {}
    if mid == "growth" and fld.weather == "sun":
        boosts = {"atk": 2, "spa": 2}
    if mid == "curse":
        if "Ghost" in atypes:
            notes.append(f"自分のHP -{mx // 2}（{cur}→{max(0, cur - mx // 2)}）、相手に毎ターン{max(1, omx // 4)}のダメージ")
            boosts = {}
        else:
            boosts = {"atk": 1, "def": 1, "spe": -1}
    if boosts and not fails:
        if mv.get("target") == "self":
            ln, _ = _boost_line("自分", att, boosts, False)
            notes += ln
        elif targets_foe:
            ln, none = _boost_line("相手", dfd, boosts, True)
            notes += ln
            if none and not st and not mv.get("volatileStatus"):
                fails = ln[0] if "特性" in ln[0] else "相手のランクがこれ以上変わらない"
    if mid == "partingshot" and not fails:
        ln, _ = _boost_line("相手", dfd, {"atk": -1, "spa": -1}, True)
        notes += ln
    if mid == "bellydrum":
        if cur <= mx // 2:
            fails = f"HPが半分以下（{cur}/{mx}）なので失敗"
        else:
            notes.append(f"自分のHP -{mx // 2}（{cur}→{cur - mx // 2}）、攻撃{att.boosts.get('atk', 0):+d}→+6")
    if mid == "clangoroussoul":
        if cur <= mx // 3:
            fails = f"HPが1/3以下（{cur}/{mx}）なので失敗"
        else:
            notes.append(f"自分のHP -{mx // 3}（{cur}→{cur - mx // 3}）")

    # 回復
    heal = mv.get("heal")
    frac = None
    if heal and mv.get("target") != "any":
        frac = heal[0] / heal[1]
    if mid in ("moonlight", "morningsun", "synthesis"):
        w = fld.weather
        frac = 2 / 3 if w == "sun" else 1 / 4 if w in ("rain", "sand", "snow") else 1 / 2
        if w:
            notes.append({"sun": "晴れで2/3", "rain": "雨で1/4", "sand": "砂嵐で1/4", "snow": "雪で1/4"}[w])
    if mid == "wish":
        frac = 1 / 2
    if mid == "rest":
        if cur >= mx:
            fails = "HPが満タンなので失敗"
        elif aab in ("insomnia", "vitalspirit"):
            fails = f"自分の特性{_ja('abilities', att.build.ability)}で眠れず失敗"
        else:
            notes.append(f"HP {cur}→{mx}（+{mx - cur}）" + (f"、{STATUS_JA.get(att.status, '')}も治る" if att.status else ""))
    if frac is not None and mid != "rest":
        amt = int(mx * frac + 0.5)
        if mid == "wish":
            notes.append(f"次のターンの終わりに+{amt}")
        elif cur >= mx:
            notes.append(f"HPが満タン（{mx}）なので回復しない")
        else:
            notes.append(f"HP {cur}→{min(mx, cur + amt)}（+{min(amt, mx - cur)}）")
        if mid == "roost" and "Flying" in atypes:
            notes.append("このターンはじめん技が当たる")
    if mid == "strengthsap" and not fails:
        a = dfd.build.stats()["atk"]
        stg = dfd.boosts.get("atk", 0)
        a = a * (2 + max(0, stg)) // (2 - min(0, stg))
        amt = min(a, mx - cur)
        notes.append(f"回復量 {a}（HP {cur}→{min(mx, cur + a)}、+{amt}）")
        if dab in NO_DROP_ABIL:
            notes.append("相手の攻撃は下がらないが回復はする")
        elif dfd.boosts.get("atk", 0) <= -6:
            fails = "相手の攻撃が最低なので失敗"
    if mid == "painsplit":
        avg = (cur + ocur) // 2
        notes.append(f"自分 {cur}→{min(mx, avg)}、相手 {ocur}→{min(omx, avg)}")
    if mid == "substitute":
        if cur <= mx // 4:
            fails = f"HPが1/4以下（{cur}/{mx}）なので失敗"
        else:
            notes.append(f"自分のHP -{mx // 4}（{cur}→{cur - mx // 4}）")
    if mid == "shedtail":
        if cur <= mx // 2:
            fails = f"HPが半分以下（{cur}/{mx}）なので失敗"
        else:
            notes.append(f"自分のHP -{mx // 2}（{cur}→{cur - mx // 2}）")
    if mid == "leechseed" and not fails:
        if "Grass" in dtypes:
            fails = "くさタイプには効かない"
        else:
            notes.append(f"毎ターン{max(1, omx // 8)}を吸い取る")

    # 設置
    if mid == "stealthrock":
        eff = type_effectiveness("Rock", dtypes)
        dmg = int(omx * eff / 8)
        notes.append(f"{D.pokemon[dfd.build.species]['ja']}が出てくるたびに{dmg}（{eff * 12.5:g}%）")
    if mid == "spikes":
        if _grounded(dfd):
            notes.append(f"{D.pokemon[dfd.build.species]['ja']}なら1回{omx // 8}（12.5%）、2回{omx // 6}、3回{omx // 4}")
        else:
            notes.append(f"{D.pokemon[dfd.build.species]['ja']}は地面にいないので当たらない")
    if mid == "toxicspikes":
        if "Poison" in dtypes and _grounded(dfd):
            notes.append(f"{D.pokemon[dfd.build.species]['ja']}は出てくると回収する（どくタイプ）")
        elif not _grounded(dfd) or "Steel" in dtypes or "Poison" in dtypes:
            notes.append(f"{D.pokemon[dfd.build.species]['ja']}には効かない")
    if mid == "stickyweb" and not _grounded(dfd):
        notes.append(f"{D.pokemon[dfd.build.species]['ja']}は地面にいないので効かない")

    # 天気・フィールド・壁
    if mid in WEATHER_ROCK:
        turns = 8 if _item(att) == WEATHER_ROCK[mid] else 5
        if turns == 8:
            notes.append(f"{_ja('items', att.build.item)}で8ターン")
        if fld.weather == WEATHER_OF[mid] and mid != "chillyreception":
            fails = "すでに同じ天気なので失敗"
    if mv.get("terrain"):
        if _item(att) == "terrainextender":
            notes.append("グランドコートで8ターン")
        if fld.terrain and mv["terrain"].startswith(fld.terrain):
            fails = "すでに同じフィールドなので失敗"
    if mid in ("reflect", "lightscreen", "auroraveil") and _item(att) == "lightclay":
        notes.append("ひかりのねんどで8ターン")
    if mid == "auroraveil" and fld.weather != "snow":
        fails = "雪ではないので失敗"
    if mid == "tailwind":
        s = att.build.stats()["spe"]
        notes.append(f"自分の素早さ {s}→{s * 2}（ランク補正前）")
    if mid == "trickroom":
        a, b = att.build.stats()["spe"], dfd.build.stats()["spe"]
        who = "自分" if a < b else "相手" if b < a else "同速"
        notes.append(f"素早さ 自分{a} / 相手{b} → トリックルーム中は{who}が先に動く" if who != "同速" else "同速")
    if mid in ("trick", "switcheroo"):
        mine, theirs = _ja("items", att.build.item) or "なし", _ja("items", dfd.build.item) or "なし"
        if dab == "stickyhold":
            fails = "相手の特性ねんちゃくで失敗"
        elif not att.build.item and not dfd.build.item:
            fails = "両方とも持ち物が無いので失敗"
        elif any((D.items.get(x) or {}).get("megaStone") for x in (att.build.item, dfd.build.item) if x):
            fails = "メガストーンは入れ替えられない"
        else:
            notes.append(f"自分の{mine}と相手の{theirs}を入れ替える")
    if mid in ("roar", "whirlwind") and dab == "suctioncups":
        fails = "相手の特性きゅうばんで失敗"
    if mid == "soak" and dtypes == ["Water"]:
        fails = "相手はすでにみずタイプ単体"

    notes = [n for n in notes if n]
    return {"text": text, "notes": notes, "fails": fails}
