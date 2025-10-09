#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Meshy Animation Library → Local KB & English Retrieval
Source page: https://docs.meshy.ai/zh/api/animation-library
Outputs:
  - meshy_animation_kb.json
  - meshy_animation_kb.jsonl
CLI:
  - build  : fetch & parse 0–696 animation entries
  - search : English query → best-matching action_id
"""

import re, json, sys, html, argparse, pathlib, time
from urllib.request import urlopen, Request
from difflib import SequenceMatcher

SRC_URL = "https://docs.meshy.ai/zh/api/animation-library"
OUT_JSON = "tools/knowledgebase/meshy_animation_kb.json"
OUT_JSONL = "tools/knowledgebase/meshy_animation_kb.jsonl"

# English aliases / normalization helpers
EN_ALIAS = {
    "runfast": ["run_fast","fast_run","sprint","quick_run","fastrunning","quickrunning"],
    "jog": ["light_run","slow_run","jogging"],
    "walk": ["walking","stroll","strut","slowwalk","fastwalk"],
    "run": ["running"],
    "idle": ["stand","neutral","rest","stationary","idlepose","standing"],
    "kick": ["kicking","foot_kick"],
    "punch": ["boxing","hit","strike","jab","hook","uppercut"],
    "bow": ["salute","gentleman_bow"],
    "wave": ["hello","greet","greeting","hand_wave"],
    "dance": ["dancing","groove","pop_dance"],
    "shoot": ["gun","side_shot","firing","fire"],
    "slash": ["sword","left_slash","cut","saber"],
    "phone": ["call","phone_call","talk_on_phone"],
    "jump": ["jumping","hop","leap"],
    "clap": ["clapping","applause"],
    "cheer": ["victory","celebrate","yay"],
    "hit": ["behit","get_hit","impact"],
    "die": ["dead","death","dying"],
    "transition": ["blend","enter","exit","start","stop","rise","sit_to_stand","stand_to_sit"],
}

# Whitelist of known categories observed on the page
KNOWN_CATEGORIES = {"DailyActions", "WalkAndRun", "Fighting", "Dancing", "BodyMovements"}

def fetch_page(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def tokenize(s: str):
    s = s.lower().replace("_", " ")
    return [t for t in re.split(r"[^a-z0-9]+", s) if t]

def explode_alias(name: str):
    toks = tokenize(name)
    out = []
    for t in toks:
        out.append(t)
        # attach alias families
        for k, vs in EN_ALIAS.items():
            if t == k or t in vs:
                out.extend([k] + vs)
    # simple composites
    if "run" in toks and "fast" in toks:
        out += ["runfast","sprint","quick","quick_run","fast_run"]
    if "walk" in toks and "injured" in toks:
        out += ["injured_walk","hurt_walk","limp"]
    return list(set(out))

def parse_items(html_text: str):
    """
    Parse items from the Meshy docs page (ID, Name, Category, Subcategory).
    We strip tags and regex-scan lines like:
      "14 Run_02 WalkAndRun Running"
    """
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html_text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n+", "\n", text)

    pat = re.compile(
        r"\b(\d{1,3})\s+([A-Za-z0-9_]+)\s+([A-Za-z][A-Za-z]+)\s+([A-Za-z][A-Za-z]+)\b"
    )
    items, seen = [], set()
    for m in pat.finditer(text):
        aid = int(m.group(1))
        name = m.group(2)
        cat = m.group(3)
        sub = m.group(4)
        if cat not in KNOWN_CATEGORIES:
            continue
        if aid in seen:
            continue
        seen.add(aid)
        tokens = list(set(tokenize(name) + [cat.lower(), sub.lower()] + explode_alias(name)))
        items.append({
            "action_id": aid,
            "name": name,
            "category": cat,
            "subcategory": sub,
            "tokens": tokens
        })
    items.sort(key=lambda x: x["action_id"])
    return items

def build():
    print(f"[build] Fetching: {SRC_URL}")
    html_txt = fetch_page(SRC_URL)
    items = parse_items(html_txt)
    if not items or len(items) < 600:
        print(f"[warn] Parsed {len(items)} items (expected ≈697). The page may have changed; adjust the regex if needed.")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"source": SRC_URL, "updated_at": int(time.time()), "count": len(items), "items": items},
                  f, ensure_ascii=False, indent=2)
    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"[build] OK → {OUT_JSON} , {OUT_JSONL}  (count={len(items)})")

def score_query(item, query: str):
    """
    Hybrid scoring:
      - token overlap between query tokens and item tokens
      - fuzzy similarity via SequenceMatcher
      - category/subcategory bonuses for obvious intents (run/walk/idle/etc.)
    """
    q = query.strip().lower()
    qtok = set(tokenize(q))
    tokens = set(item["tokens"])

    # token overlap
    overlap = len(tokens & qtok)

    # fuzzy similarity
    base = " ".join([str(item["action_id"]), item["name"], item["category"], item["subcategory"]] + item["tokens"]).lower()
    approx = SequenceMatcher(None, q, base).ratio()

    # category/subcategory bonuses
    bonus = 0.0
    if any(w in {"run","runfast","sprint","jog","quick","fast"} for w in qtok):
        if item["category"].lower() == "walkandrun" and item["subcategory"].lower() == "running":
            bonus += 0.25
    if any(w in {"walk","stroll","strut","slowwalk","fastwalk"} for w in qtok):
        if item["category"].lower() == "walkandrun" and item["subcategory"].lower() == "walking":
            bonus += 0.20
    if any(w in {"idle","stand","rest","stationary"} for w in qtok):
        if item["subcategory"].lower() in {"idle","transitioning"}:
            bonus += 0.12
    if any(w in {"punch","boxing","jab","hook","uppercut"} for w in qtok):
        if item["category"].lower() == "fighting":
            bonus += 0.20
    if any(w in {"kick"} for w in qtok):
        if "kick" in tokens or item["category"].lower() == "fighting":
            bonus += 0.20
    if any(w in {"dance","dancing","groove"} for w in qtok):
        if item["category"].lower() == "dancing":
            bonus += 0.20
    if any(w in {"wave","hello","greet","greeting"} for w in qtok):
        if "wave" in tokens or "hello" in tokens:
            bonus += 0.18
    if any(w in {"phone","call","phone_call"} for w in qtok):
        if "phone" in tokens or "call" in tokens:
            bonus += 0.18
    if any(w in {"jump","leap","hop"} for w in qtok):
        if "jump" in tokens:
            bonus += 0.15

    return overlap * 0.6 + approx * 0.6 + bonus

def search(q: str, topk: int = 5):
    data = json.load(open(OUT_JSON, "r", encoding="utf-8"))
    kb = data["items"]
    scored = [(score_query(it, q), it) for it in kb]
    scored.sort(key=lambda x: x[0], reverse=True)
    print(f'Query: "{q}"')
    for i, (s, it) in enumerate(scored[:topk], 1):
        print(f"{i:>2}. action_id={it['action_id']:<3}  name={it['name']:<24}  cat={it['category']}/{it['subcategory']:<12}  score={s:.3f}")
    if scored:
        best = scored[0][1]
        print(f"\nBest action_id: {best['action_id']}  ({best['name']})")
    return best

def main():
    ap = argparse.ArgumentParser(description="Build and query a local KB of Meshy animations (English only).")
    ap.add_argument("cmd", choices=["build","search"], help="build: create KB; search: English retrieval")
    ap.add_argument("query", nargs="?", help="English query text (e.g., 'fast run', 'wave hello')")
    args = ap.parse_args()

    if args.cmd == "build":
        build()
    elif args.cmd == "search":
        if not pathlib.Path(OUT_JSON).exists():
            print("[info] KB not found; building first …")
            build()
        if not args.query:
            print('Usage: python meshy_anim_kb_en.py search "fast run"')
            sys.exit(1)
        search(args.query)

if __name__ == "__main__":
    main()
