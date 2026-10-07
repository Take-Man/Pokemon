"""対戦の記録: 技の確定効果の抽出と、不発の記録を逆算から外すこと。"""
from app.matches import _certain_effects
from engine.data import dex
from engine.infer import Record, infer


def fx(move):
    return _certain_effects(dex().moves[move])


def test_certain_effects_status_and_self_boosts():
    assert fx("swordsdance")["user"] == {"atk": 2}
    assert fx("closecombat")["user"] == {"def": -1, "spd": -1}
    assert fx("flamecharge")["user"] == {"spe": 1}          # 追加効果が100%のもの
    assert fx("snarl")["target"] == {"spa": -1}
    assert fx("thunderwave")["status"] == "par"
    assert fx("stealthrock")["side"] == "stealthrock"
    assert fx("raindance")["weather"] == "RainDance"


def test_missed_record_is_not_used_for_inference():
    base = dict(id="a", kind="dealt", opp="garchomp", my={"species": "kingambit", "nature": "adamant", "sp": {"atk": 32}, "moves": ["ironhead"]},
                move="ironhead", before=100, after=100)
    miss = infer("garchomp", [Record(**base, cond={"miss": True})])
    assert miss["records"] == 0
