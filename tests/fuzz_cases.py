"""Showdown比較用のランダムケースを生成する（開発用）。"""
import json, random, sys
sys.path.insert(0, '.')
from engine.data import dex
D = dex()
random.seed(int(sys.argv[2]) if len(sys.argv) > 2 else 0)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
items = ["", "Life Orb", "Expert Belt", "Charcoal", "Mystic Water", "Silk Scarf", "Muscle Band", "Wise Glasses",
         "Leftovers", "Focus Sash", "Choice Scarf", "Occa Berry", "Yache Berry", "Shuca Berry", "Chilan Berry", "Black Glasses", "Dragon Fang", "Fairy Feather",
         "Air Balloon", "Iron Ball", "Light Ball", "Magnet", "Never-Melt Ice", "Hard Stone", "Soft Sand", "Spell Tag", "Passho Berry", "Babiri Berry"]
SKIP = {"payback","assurance","avalanche","revenge","fling","endeavor","counter","mirrorcoat","metalburst","finalgambit","fissure","sheercold","guillotine","horndrill","superfang","ruination","comeuppance","terrainpulse","lashout","stompingtantrum","temperflare","ragefist","boltbeak","fishiousrend","beatup","present","magnitude","naturalgift","spitup","trumpcard","punishment","wringout","crushgrip","hardpress","retaliate","round","echoedvoice","furycutter","iceball","rollout","triplekick","tripleaxel","populationbomb","dragondarts","suckerpunch","upperhand","focuspunch","shelltrap","beakblast","synchronoise","dreameater","belch","lastrespects","ficklebeam","solarbeam","solarblade","electroshot","meteorbeam","skyattack","razorwind","skullbash","hyperbeam","gigaimpact"}
mons = [p for p in D.pokemon.rows if p["searchable"]]
natures = [n["en"] for n in D.natures.rows]
def rsp():
    sp = {}; left = 66
    for s in random.sample(["hp","atk","def","spa","spd","spe"], 6):
        v = min(left, random.choice([0,0,4,12,32,32])); sp[s] = v; left -= v
    return sp
cases = []
while len(cases) < N:
    a, d = random.choice(mons), random.choice(mons)
    dm = [m for m in a["moves"] if D.moves[m]["category"] != "Status"]
    if not dm: continue
    mv = D.moves[random.choice(dm)]
    if mv["id"] in SKIP: continue
    c = {"name": f"{a['en']}>{mv['en']}>{d['en']}", "move": mv["en"],
         "attacker": {"species": a["en"], "nature": random.choice(natures), "sp": rsp(), "ability": random.choice(a["abilities"]), "item": random.choice(items)},
         "defender": {"species": d["en"], "nature": random.choice(natures), "sp": rsp(), "ability": random.choice(d["abilities"]), "item": random.choice(items)}}
    if "Rivalry" in c["attacker"]["ability"] or "Analytic" in c["attacker"]["ability"]: continue
    if a["isMega"]: c["attacker"]["item"] = a["requiredItem"]
    if d["isMega"]: c["defender"]["item"] = d["requiredItem"]
    r = random.random()
    if r < 0.15: c["field"] = {"weather": random.choice(["sun","rain","sand","snow"])}
    elif r < 0.25: c["field"] = {"terrain": random.choice(["electric","grassy","psychic","misty"])}
    if random.random() < 0.1: c["crit"] = True
    if random.random() < 0.15: c["atkBoosts"] = {random.choice(["atk","spa"]): random.choice([-1,1,2])}
    if random.random() < 0.1: c["defBoosts"] = {random.choice(["def","spd"]): random.choice([-1,1,2])}
    if random.random() < 0.08: c["defender"]["reflect"] = True
    if random.random() < 0.08: c["defender"]["light_screen"] = True
    if random.random() < 0.05 and "Fire" not in a["types"] and c.get("field", {}).get("terrain") != "misty": c["attacker"]["status"] = "brn"
    cases.append(c)
json.dump(cases, open(sys.argv[3] if len(sys.argv) > 3 else "/tmp/fuzz.json", "w"))
