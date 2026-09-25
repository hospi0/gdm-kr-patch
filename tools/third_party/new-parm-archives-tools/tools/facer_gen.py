#!/usr/bin/env python3
"""facer_gen.py — author docs/menus/expressions-en.json from the FACE2.DAT dump.

Full-width UPPERCASE tbl; nameplate box hard-clips at 11 glyphs (measured in-harness:
"FEENA SMILE"=11 fully visible, "JUSTIN THINK"=12 clips). Rule: name + 1 space +
caption <= 11. Keep the shipped character name (terms.json); translate the expression
caption with a consistent vocabulary that has a <=4-glyph SHORT fallback for the
6-glyph names (JUSTIN/GADWIN/MULLEN). Variant digits (普通１/２, 涙目１/２ ...) are
dropped for width (near-identical poses) EXCEPT bare-number captions (アルカダ族 1/2).
Anything still over budget is truncated (stored short so it renders un-clipped) and
logged. Run: python3 tools/facer_gen.py  (writes the JSON + prints an exceptions report)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

MAXW = 11

# Character name JP -> EN (shipped/dictionary forms; * = added here, minor NPCs)
NAMES = {
    "ジャスティン": "JUSTIN", "フィーナ": "FEENA", "スー": "SUE",
    "スー１７さい": "SUE 17", "プーイ": "PUFFY", "ガドイン": "GADWIN",
    "ラップ": "RAPP", "ミルダ": "MILDA", "ギド": "GUIDO", "ミューレン": "MULLEN",
    "リーン": "LEEN", "バール": "BAAL", "リリィ": "LILLY", "館長": "CURATOR",
    "ガンツ": "GANTZ", "テンツ": "TENTZ", "ジン": "JIN", "船長": "CAPTAIN",
    "パコン": "PAKON", "サキ": "SAKI", "ナナ": "NANA", "ミオ": "MIO",
    "レム": "REM", "アルマ": "ALMA", "ナイナ": "NAINA", "ダンダ": "DANDA",
    "リエーテ": "LIETE", "リエーテ幻影": "LIETE", "リエーテ逆光": "LIETE",
    "人魚": "MERMAID", "ニッキ": "NICKY", "ダーリン": "DARLIN", "ドーリン": "DORLIN",
    "デーリン": "DERLIN", "城主": "LORD", "女幽霊": "GHOST", "コズル": "KOZURU",
    "グース": "GOOSE", "ゴンツ": "GONTZ", "ナザリ": "NAZARI", "チット": "CHITT",
    "受付嬢": "CLERK", "ガンボの村長": "GUMBO ELDER", "ルクの村長": "LUC ELDER",
    "ダイトの長老": "DIGHT ELDER", "アルカダ族": "ALKADA", "パラト鳥": "PARATO",
    "ガンツの母": "GANTZ MOM", "ジャスティンの子": "JUSTINS KID",
    # 未 (未 表示 = unused placeholder slot) is intentionally kept as-is (never shown).
}

# Expression JP -> (primary EN, short<=4 EN). Consistent vocabulary; uppercase.
EXPR = {
    "普通": ("NORMAL", "CALM"), "笑顔": ("SMILE", "GRIN"), "思考": ("THINK", "MUSE"),
    "笑い": ("LAUGH", "HAHA"), "笑う": ("LAUGH", "HAHA"), "怒り": ("ANGRY", "MAD"),
    "驚き": ("SHOCK", "GASP"), "驚く": ("SHOCK", "GASP"), "真剣": ("SERIOUS", "GRIM"),
    "得意": ("PROUD", "SMUG"), "気絶": ("FAINT", "OUT"), "真っ赤": ("BLUSH", "RED"),
    "ねむい": ("SLEEPY", "DOZE"), "発見": ("EUREKA", "AHA"), "喜び": ("JOY", "JOY"),
    "心配": ("WORRY", "FRET"), "泣き": ("CRYING", "CRY"), "泣く": ("CRY", "CRY"),
    "でれでれ": ("GOOFY", "GAGA"), "マジメ": ("EARNEST", "PRIM"),
    "うれしい": ("HAPPY", "GLAD"), "幸せ": ("HAPPY", "GLAD"), "おやっ": ("HUH?", "HUH?"),
    "いてー": ("OUCH", "OW!"), "いて": ("OUCH", "OW!"),
    "ＯＫ！": ("OK!", "OK!"), "やった": ("YAY!", "YAY!"),
    "何だよ": ("WHAT?", "WHAT"), "寝ぼけ": ("DROWSY", "DOZE"), "強気": ("BOLD", "BOLD"),
    "混乱": ("DAZED", "DAZE"), "叫び": ("SHOUT", "YELL"), "にらみ": ("GLARE", "EYE"),
    "にらむ": ("GLARE", "EYE"), "こまる": ("UNSURE", "LOST"), "逆さ": ("UPSIDE", "FLIP"),
    "活気": ("LIVELY", "PEP"), "気取り": ("POSER", "POSE"), "てれ": ("SHY", "SHY"),
    "涙目": ("TEARY", "TEAR"), "信頼": ("TRUST", "TRUST"), "さるぐつわ": ("GAGGED", "GAG"),
    "困わく": ("PUZZLED", "LOST"), "不快": ("GRUMPY", "SULK"), "沈黙": ("SILENT", "MUTE"),
    "演説": ("SPEECH", "TALK"), "いじわる": ("MEAN", "MEAN"), "ばかぁ": ("IDIOT", "FOOL"),
    "怒り泣き": ("TANTRUM", "FIT"), "おねーさま": ("MY LADY", "LADY"),
    "苦しい": ("PAIN", "ACHE"), "おすまし": ("PRIM", "PRIM"), "うふ": ("HEHE", "HEHE"),
    "にこ": ("GRIN", "GRIN"), "小言": ("SCOLD", "NAG"), "なんでよ": ("WHY?!", "WHY?"),
    "うつむく": ("GLUM", "GLUM"), "鼻ほじり": ("NOSE", "NOSE"), "怒る": ("ANGRY", "MAD"),
    "優しい": ("KIND", "KIND"), "嫌い": ("HATE", "HATE"), "狂乱状態": ("FRENZY", "WILD"),
    "切れる": ("SNAP", "SNAP"), "目星": ("HUNCH", "LEAD"), "ふふん": ("HMPH", "HMPH"),
    "びっくり": ("SHOCK", "GASP"), "大笑い": ("GUFFAW", "ROAR"), "なにか？": ("WHAT?", "WHAT"),
    "無表情": ("BLANK", "MEH"), "怒鳴る": ("YELL", "YELL"), "止める": ("STOP", "STOP"),
    "なぜ": ("WHY?", "WHY?"), "公人": ("FORMAL", "FORM"), "私人": ("CASUAL", "CAS"),
    "号令": ("ORDERS", "CMD"), "沈み": ("GLUM", "GLUM"), "暗い": ("DARK", "DARK"),
    "いや": ("NO!", "NO!"), "強がり": ("BLUFF", "BOLD"), "いやーん": ("NOOO", "NOO"),
    "ずぶぬれ": ("SOAKED", "WET"), "苦悩": ("AGONY", "ACHE"), "フフフ": ("HEHEHE", "HEH"),
    "高笑い": ("CACKLE", "HAH"), "ふうっ": ("WHEW", "WHEW"), "ウィンク": ("WINK", "WINK"),
    "涙": ("TEARS", "TEAR"), "語る": ("TALK", "TALK"), "へへん": ("HEH!", "HEH"),
    "大声": ("LOUD", "LOUD"), "ぐっ": ("URGH", "URGH"), "おろっ": ("OOPS", "OOPS"),
    "優しげ": ("GENTLE", "KIND"), "悪": ("EVIL", "EVIL"), "う～": ("UGH", "UGH"),
    "薄目": ("SQUINT", "PEEK"), "つまんない": ("BORED", "BORE"), "真顔": ("SOBER", "GRIM"),
    "お願い": ("PLEASE", "PLEA"), "願い": ("WISH", "WISH"), "ボケる": ("DOPEY", "DOPE"),
    "女": ("GIRL", "GIRL"), "男": ("BOY", "BOY"), "化物": ("BEAST", "BEAST"),
}

DIGITS = {"１": "1", "２": "2", "３": "3"}

# Per-record (name_en, cap_en) hard overrides for compound labels that need to keep a
# distinction the generic rules would drop (record index -> (name_en, cap_en)).
OVERRIDES = {
    251: ("KID GIRL", None),  # ジャスティンの子 女 (Justin's imagined child, girl)
    252: ("KID BOY", None),   # ジャスティンの子 男 (Justin's imagined child, boy)
}


def translate_caption(cap_jp, budget):
    """Return (en, note). Drops variant digit unless caption is bare-number."""
    if cap_jp == "":
        return "", None
    # bare-number caption (e.g. アルカダ族 '１'/'２')
    if cap_jp in DIGITS:
        return DIGITS[cap_jp], None
    base = cap_jp
    dropped = None
    if base and base[-1] in DIGITS:
        dropped = DIGITS[base[-1]]
        base = base[:-1]
    if base not in EXPR:
        return None, f"UNTRANSLATED CAPTION {cap_jp!r}"
    primary, short = EXPR[base]
    note = None
    en = primary
    if len(en) > budget:
        en = short
        if len(en) > budget:
            en = short[:budget] if budget > 0 else ""
            note = f"caption {cap_jp!r}->{primary!r} truncated to {en!r} (budget {budget})"
    if dropped:
        note = (note + "; " if note else "") + f"dropped variant #{dropped}"
    return en, note


def main():
    dump = json.load(open(ROOT / "work/pN_facer/dump.json"))
    out = {"_note": "Character-expressions viewer nameplates (FACER.BIN/FACE2.DAT). "
                    "Full-width UPPERCASE tbl, <=11 glyphs (name+space+caption). "
                    "Generated by tools/facer_gen.py.",
           "records": []}
    exceptions = []
    for r in dump["records"]:
        i, ctrl = r["i"], r["ctrl"]
        njp, cjp = r["name_jp"], r["cap_jp"]
        if njp == "未":  # unused placeholder slot — keep JP, never displayed
            out["records"].append({"i": i, "ctrl": ctrl, "name_jp": njp, "cap_jp": cjp,
                                   "name_en": "", "cap_en": ""})
            continue
        if i in OVERRIDES:
            name_en, cap_en = OVERRIDES[i]
            out["records"].append({"i": i, "ctrl": ctrl, "name_jp": njp, "cap_jp": cjp,
                                   "name_en": name_en, "cap_en": cap_en})
            continue
        if njp not in NAMES:
            exceptions.append(f"rec {i}: UNTRANSLATED NAME {njp!r}")
            name_en = ""
        else:
            name_en = NAMES[njp]
        budget = MAXW - len(name_en) - (1 if cjp else 0)
        # If the name is so long that no readable (>=4 glyph) caption fits, show the
        # name alone rather than an ugly 1-3 char fragment.
        if name_en and cjp and budget < 4:
            exceptions.append(f"rec {i}: {name_en!r} name-only (caption {cjp!r} dropped, budget {budget})")
            cap_en = None  # explicit "no caption" sentinel (distinct from ""=keep-JP)
        elif cjp == "":
            cap_en = None  # single-label record (name only) — no caption
        else:
            cap_en, note = translate_caption(cjp, budget)
            if cap_en is None:
                exceptions.append(f"rec {i}: {note}")
                cap_en = ""
            elif note:
                exceptions.append(f"rec {i}: {name_en} / {cjp!r} -> {cap_en!r}: {note}")
        # final width guard
        w = len(name_en) + (1 + len(cap_en) if cap_en else 0)
        if name_en and w > MAXW:
            exceptions.append(f"rec {i}: {name_en!r} {cap_en!r} = {w} > {MAXW} (WILL CLIP)")
        out["records"].append({"i": i, "ctrl": ctrl, "name_jp": njp, "cap_jp": cjp,
                               "name_en": name_en, "cap_en": cap_en})
    p = ROOT / "docs/menus/expressions-en.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"wrote {p} ({len(out['records'])} records)")
    print(f"\n{len(exceptions)} notes/exceptions:")
    for e in exceptions:
        print(" ", e)


if __name__ == "__main__":
    main()
