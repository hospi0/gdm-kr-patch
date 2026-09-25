#!/usr/bin/env python3
"""
Build the Grandia JP->EN reference dictionary from the three parallel corpora we
captured (all under dictionary/sources/):

  * official_saturn_script_shotgunnova.txt  -- the OFFICIAL Sony PSX localization
        script (what the TrekkiesUnite Saturn English patch uses). Canonical EN.
  * alent_saturn_guide.txt                  -- the _Alent_ Project FAN translation
        of the Saturn game (romaji JP + literal English, ~50% of dialogue).
  * jp_wikipedia_grandia.txt                -- canonical Japanese KANA names.

Outputs (committed):
  dictionary/glossary.json            curated JP(kana)->EN term dictionary
  dictionary/parallel_corpus.json     best-effort romaji<->EN sentence pairs
                                      from the Alent guide's [J/E] chapters
  dictionary/review/index.html        review webpage: every term whose Japanese
                                      maps to MORE THAN ONE distinct English
                                      rendering (official vs fan vs variant)
  docs/translation-discrepancies.md   the discrepancy report

The glossary is hand-curated but every entry is grounded in the sources above;
`sources` lists where each came from. `official_en` is the canonical column
(PSX/TrekkiesUnite); `fan_en` is the Alent fan rendering when it differs.
"""
import json, os, re, html, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, "dictionary", "sources")
TODAY = "2026-06-18"

# ---------------------------------------------------------------------------
# Curated glossary.  Each entry is grounded in the captured sources:
#   jp        : Japanese as it appears in the game encoding (kana/kanji)
#   romaji    : reading
#   category  : character | place | civilization | term | creature
#   official  : canonical English (Sony PSX localization == TrekkiesUnite patch)
#   fan       : _Alent_ Project fan rendering, when known/different ("" = same/unknown)
#   variants  : other spellings observed (kept for the reviewer)
#   sources   : which corpora attest this entry
#   note      : disambiguation / caveat
# Sources legend: O=official-script  A=alent-guide  W=jp-wikipedia  F=fandom-wiki
# ---------------------------------------------------------------------------
G = [
    # ---- Party / main cast ----------------------------------------------
    ("ジャスティン","Jasutin","character","Justin","Justin",[],"OAWF","protagonist"),
    ("フィーナ","Fiina","character","Feena","Feena",[],"OAWF","heroine"),
    ("スー","Suu","character","Sue","Sue",[],"OAWF","young companion"),
    ("プーイ","Puui","character","Puffy","Pooy",[],"OAWF","Sue's pet creature (Moge)"),
    ("ぷう","Puu","term","Puff","Pu",["Pu! Pu!"],"OA","Puffy's cry; canonical 'Puff Puff!'"),
    ("ガドイン","Gadoin","character","Gadwin","Gadwyn",[],"OAWF","knight of Dight; Spirit of Sword"),
    ("ラップ","Rappu","character","Rapp","Rapp",[],"OAWF","Cafu youth who joins"),
    ("ミルダ","Miruda","character","Milda","Milda",[],"OAWF","strong Laine warrior"),
    ("ギド","Gido","character","Guido","Guido",["Gid"],"OAWF","wandering Moge merchant"),
    ("リエーテ","Rieete","character","Liete","Liete",["Riete"],"OAWF",
        "Alent priestess/guide; builds the Digital Museum"),
    # ---- Garlyle / antagonists ------------------------------------------
    ("バール","Baaru","character","Baal","Baal",["General Baal"],"OAWF","Garlyle general"),
    ("ミューレン","Myuuren","character","Mullen","Myuren",["Colonel Mullen"],"OAWF",
        "Baal's son; Garlyle colonel"),
    ("リーン","Riin","character","Leen","Leen",[],"OAWF","Mullen's aide; ties to Liete"),
    ("サキ","Saki","character","Saki","Saki",[],"OWF","Desert Moon trio"),
    ("ナナ","Nana","character","Nana","Nana",[],"OWF","Desert Moon trio"),
    ("ミオ","Mio","character","Mio","Mio",[],"OWF","Desert Moon trio"),
    ("ガイア","Gaia","creature","Gaia","Gaia",[],"OAWF","the world-devouring monster"),
    # ---- Notable NPCs ---------------------------------------------------
    ("リリィ","Ririi","character","Lilly","Lilly",[],"OWF","Justin's mother; ex-pirate"),
    ("ガンツ","Gantsu","character","Gantz","Gantz",[],"OWF","Parm bully"),
    ("ゴンツ","Gontsu","character","Gontz","Gontz",[],"OWF","Gantz's brother"),
    ("テンツ","Tentsu","character","Tentz","Tentz",[],"WF","Gantz's younger brother"),
    ("コズル","Kozuru","character","Kozuru","Kozuru",[],"WF","Gantz's crony"),
    ("グース","Guusu","character","Goose","Goose",[],"WF","Gantz's crony"),
    ("パコン","Pakon","character","Pakon","Pakon",[],"OWF","New Parm Society head"),
    ("レム","Remu","character","Rem","Rem",[],"OWF","Luc village child"),
    ("アルマ","Aruma","character","Alma","Alma",["Doctor Alma"],"OWF","Dight doctor"),
    ("ニッキ","Nikki","character","Nicky","Nicky",[],"OWF","Cafu boy, Rapp's follower"),
    ("ダーリン","Daarin","character","Darlin","Darlin",[],"OWF","Laine sage (Milda's husband)"),
    ("デーリン","Deerin","character","Derlin","Derlin",[],"OWF","Laine sage"),
    ("ドーリン","Doorin","character","Dorlin","Dorlin",[],"OWF","Laine sage"),
    ("チャン","Chan","character","Chang","Chang",[],"WF","Pakon's bodyguard; cook"),
    # ---- Places (official names from script table of contents) ----------
    ("パーム","Paamu","place","Parm","Parm",[],"OAWF","port hometown"),
    ("ニューパーム","Nyuu Paamu","place","New Parm","New Parm",[],"OAWF","city across the sea"),
    ("サルト遺跡","Saruto Iseki","place","Sult Ruins","Saruto Ruins",[],"OAW","Angelou ruins near Parm"),
    ("レック鉱山","Rekku Kouzan","place","Leck Mines","Reck Mines",[],"OAW","mines outside Parm"),
    ("ドム遺跡","Domu Iseki","place","Dom Ruins","Domu Ruins",[],"OAW","ruins past New Parm"),
    ("ガーライル","Gaarairu","place","Garlyle Base","Garlysle Base",[],"OAW",
        "the Garlyle Forces / their base"),
    ("ルクの村","Ruku no Mura","place","Luc Village","Ruku Village",[],"OAW","sub-human village"),
    ("ダイトの村","Daito no Mura","place","Dight Village","Daito Village",[],"OAW","seaside village"),
    ("ガンボの村","Ganbo no Mura","place","Gumbo Village","Gumbo Village",[],"OAW","frog/hot-spring village"),
    ("カフーの村","Kafuu no Mura","place","Cafu Village","Cafu Village",[],"OAW","Rapp's village"),
    ("ジールパドン","Jiirupadon","place","Zil Padon","Jilpadon",["Zilpadon"],"OAW","desert town"),
    ("レーヌの村","Reenu no Mura","place","Laine Village","Laine Village",["Reine"],"OAW",
        "frozen village of strong women"),
    ("アレント","Arento","place","Alent","Alent",["Arent"],"OAWF",
        "sky temple at the World's End; namesake of the Digital Museum"),
    ("世界の果て","Sekai no Hate","place","End of the World","The World's End",[],"OAW",
        "the great wall dividing the continents"),
    ("飛竜の谷","Hiryuu no Tani","place","Valley of the Flying Dragon","Hiryu Valley",[],"OAW",""),
    ("雨月の塔","Ugetsu no Tou","place","Typhoon Tower","Tower of Rain and Moon",[],"OAW",
        "poison-rain tower near Dight"),
    ("荒神山","Koujin Yama","place","Lama Mountains","Koujin Mountain",[],"OAW",""),
    ("ツインタワー","Tsuin Tawaa","place","The Twin Towers","Twin Towers",[],"OAW",""),
    ("グランドール","Gurandooru","place","The Grandeur","Grandall",[],"OAW",
        "Garlyle's flying battleship"),
    # ---- Civilization / lore terms --------------------------------------
    ("エンジュール文明","Enjuuru Bunmei","civilization","Angelou","Enjule",
        ["Angelou civilization"],"OAW","ancient magic civilization"),
    ("エンジュール","Enjuuru","civilization","Angelou","Enjule",[],"OAW","short form of the above"),
    ("アレント博物館","Arento Hakubutsukan","place","Alent Museum","",["Arent Museum"],"W",
        "Liete's museum in Digital Museum; seed dict used 'Arent' -- official romanizes アレント as 'Alent'"),
    ("エンジュール博物館","Enjuuru Hakubutsukan","place","Angelou Museum","",[],"OW",
        "the Parm museum exhibiting Angelou relics; its head NPC is the 'Curator'"),
    ("精霊石","Seireiseki","term","Spirit Stone","Spirit Stone",[],"OAW",
        "proof of a pact between human and spirit"),
    ("精霊","Seirei","term","Spirit","Spirit",[],"OAW","elemental spirits"),
    ("光翼人","Kouyokujin","term","Icarian","Winged People",["Icarian race"],"OAW",
        "the winged ancients of Angelou"),
    ("冒険者","Boukensha","term","Adventurer","Adventurer",[],"OAW",""),
    ("冒険者協会","Boukensha Kyoukai","term","Adventurers' Society","Adventurers' Guild",[],"OAW",""),
    ("勇者","Yuusha","term","Hero","Hero",[],"OA",""),
    ("館長","Kanchou","character","Curator","",[],"OW","head of the Angelou Museum in Parm"),
    ("モゲ","Moge","creature","Moge","Moge",[],"OAW","the small creature race (Puffy, Guido)"),
]

def to_entry(t):
    jp, romaji, cat, off, fan, variants, srcs, note = t
    srcmap = {"O":"official-script","A":"alent-guide","W":"jp-wikipedia","F":"fandom-wiki"}
    sources = [srcmap[c] for c in srcs]
    # distinct english renderings seen for this Japanese term
    renders = []
    for r in [off, fan] + list(variants):
        if r and r not in renders:
            renders.append(r)
    review = (fan != "" and fan != off) or len(renders) > 1
    return {
        "jp": jp, "romaji": romaji, "category": cat,
        "official_en": off, "fan_en": fan, "variants": variants,
        "renderings": renders, "sources": sources,
        "review": review, "note": note,
    }

def build_glossary():
    entries = [to_entry(t) for t in G]
    out = {
        "_meta": {
            "description": "Curated JP(kana)->EN reference dictionary for Grandia, "
                           "cross-referencing the official PSX/TrekkiesUnite localization, "
                           "the _Alent_ Project fan translation, and Japanese Wikipedia.",
            "official_en": "canonical column = Sony PSX localization (== TrekkiesUnite Saturn patch)",
            "fan_en": "the _Alent_ Project Saturn fan translation rendering (blank = same/unknown)",
            "generated": TODAY,
            "count": len(entries),
        },
        "entries": entries,
    }
    p = os.path.join(ROOT, "dictionary", "glossary.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("wrote", p, "(%d entries)" % len(entries))
    return entries

# ---------------------------------------------------------------------------
# Parse the Alent guide's bilingual [J/E] chapters into romaji<->EN pairs.
# Format inside a speaker block:  SPEAKER \n <romaji line(s)> \n <english line(s)>.
# We split romaji vs english heuristically. Labeled APPROXIMATE.
# ---------------------------------------------------------------------------
EN_STOP = set("the a an of to and is are was you i we he she it his her my your "
              "that this with for not but have has do does will can what why how "
              "there here me him them they our who when then than into out about".split())
ROMAJI_PARTICLE = set("wa ga wo no ni de to mo ya ka na yo ne da desu masu kara made "
                      "koto mono nai dakedo mitai shika dake nan nani watashi anata "
                      "ore omae boku kimi sou darou deshou".split())

def looks_romaji(line):
    words = re.findall(r"[A-Za-z'\-]+", line.lower())
    if not words:
        return None
    en = sum(w in EN_STOP for w in words)
    ro = sum(w in ROMAJI_PARTICLE for w in words)
    if ro > en:  return True
    if en > 0 and ro == 0: return False
    # fall back: romaji tends to have no 'l', 'v', 'x', and many vowel-heavy tokens
    if re.search(r"[lvxq]", line.lower()): return False
    return None

def build_corpus():
    txt = open(os.path.join(SRC, "alent_saturn_guide.txt"), encoding="utf-8").read()
    lines = txt.split("\n")
    pairs = []
    block_speaker, romaji_buf, en_buf = None, [], []
    def flush():
        if romaji_buf and en_buf:
            pairs.append({
                "speaker": block_speaker,
                "jp_romaji": " ".join(s.strip() for s in romaji_buf).strip(),
                "en": " ".join(s.strip() for s in en_buf).strip(),
            })
    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        # speaker label: short, mostly caps, indented
        if re.match(r"^\s{4,}[A-Z][A-Za-z .'()/-]{0,30}$", line) and len(s) <= 28 and s.isupper() is False and s[:1].isupper():
            # treat a Title/CAPS short line as a new speaker only if next lines exist
            pass
        if re.match(r"^[A-Z][A-Z .'!?]{2,30}$", s):  # ALL CAPS speaker (bilingual style)
            flush(); romaji_buf, en_buf = [], []
            block_speaker = s.title(); continue
        if not s or s.startswith("***") or s.startswith("(") or s.startswith("*"):
            flush(); romaji_buf, en_buf = [], []
            continue
        verdict = looks_romaji(s)
        if verdict is True and not en_buf:
            romaji_buf.append(s)
        elif verdict is False:
            en_buf.append(s)
        else:
            if romaji_buf and not en_buf:   # ambiguous, after romaji -> english
                en_buf.append(s)
            elif romaji_buf or en_buf:
                en_buf.append(s)
    flush()
    # keep only plausible pairs (romaji side actually romaji-ish)
    pairs = [p for p in pairs if p["jp_romaji"] and p["en"] and
             looks_romaji(p["jp_romaji"]) is not False]
    out = {
        "_meta": {
            "description": "APPROXIMATE romaji-JP <-> English sentence pairs auto-extracted "
                           "from the _Alent_ Project fan guide's bilingual [J/E] chapters. "
                           "Heuristic split; verify before relying on any single pair.",
            "source": "dictionary/sources/alent_saturn_guide.txt",
            "generated": TODAY,
            "count": len(pairs),
        },
        "pairs": pairs,
    }
    p = os.path.join(ROOT, "dictionary", "parallel_corpus.json")
    json.dump(out, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("wrote", p, "(%d pairs)" % len(pairs))
    return pairs

# ---------------------------------------------------------------------------
# Review webpage: terms whose Japanese maps to >1 distinct English rendering.
# ---------------------------------------------------------------------------
def build_webpage(entries):
    review = [e for e in entries if len(e["renderings"]) > 1 or e["review"]]
    review.sort(key=lambda e: (e["category"], e["jp"]))
    rows = []
    for e in review:
        chips = "".join(
            f'<span class="chip {"off" if r==e["official_en"] else ("fan" if r==e["fan_en"] else "var")}">{html.escape(r)}</span>'
            for r in e["renderings"])
        rows.append(f"""      <tr>
        <td class="jp">{html.escape(e['jp'])}<div class="ro">{html.escape(e['romaji'])}</div></td>
        <td class="cat">{html.escape(e['category'])}</td>
        <td class="off">{html.escape(e['official_en']) or '&mdash;'}</td>
        <td class="fan">{html.escape(e['fan_en']) or '&mdash;'}</td>
        <td class="ren">{chips}</td>
        <td class="note">{html.escape(e['note'])}</td>
      </tr>""")
    body = "\n".join(rows)
    htmlpage = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grandia JP&rarr;EN &mdash; terms needing review</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif; margin:0; background:#0f1115; color:#e6e6e6; }}
  header {{ padding:24px 28px; background:#171a21; border-bottom:1px solid #2a2f3a; }}
  h1 {{ margin:0 0 6px; font-size:20px; }}
  header p {{ margin:4px 0; color:#9aa3b2; }}
  .wrap {{ padding:20px 28px 60px; }}
  table {{ border-collapse:collapse; width:100%; }}
  th,td {{ text-align:left; padding:10px 12px; border-bottom:1px solid #232833; vertical-align:top; }}
  th {{ position:sticky; top:0; background:#1b1f27; color:#cdd5e0; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  td.jp {{ font-size:18px; white-space:nowrap; }}
  .ro {{ font-size:11px; color:#7e8696; }}
  td.cat {{ color:#9aa3b2; font-size:12px; }}
  td.off {{ color:#8ee6a0; font-weight:600; }}
  td.fan {{ color:#e6c98e; }}
  td.note {{ color:#9aa3b2; font-size:13px; max-width:320px; }}
  .chip {{ display:inline-block; padding:2px 8px; margin:2px 4px 2px 0; border-radius:10px; font-size:12px; border:1px solid #333a47; }}
  .chip.off {{ background:#16351f; border-color:#2c6b3d; color:#9ff0b0; }}
  .chip.fan {{ background:#3a2f16; border-color:#7a5e23; color:#f0d79a; }}
  .chip.var {{ background:#2a2f3a; color:#c4ccd8; }}
  .legend span {{ margin-right:14px; }}
  tr:hover td {{ background:#141821; }}
</style></head>
<body>
<header>
  <h1>Grandia &mdash; Japanese terms with more than one English rendering</h1>
  <p>{len(review)} terms where the <b>official</b> Sony/TrekkiesUnite localization, the
     <b>_Alent_</b> fan translation, and/or other variants disagree. Pick the canonical English for each.</p>
  <p class="legend">
     <span class="chip off">official (canonical)</span>
     <span class="chip fan">_Alent_ fan</span>
     <span class="chip var">variant</span></p>
  <p style="color:#7e8696">Generated {TODAY} from dictionary/glossary.json</p>
</header>
<div class="wrap">
  <table>
    <thead><tr>
      <th>Japanese</th><th>Type</th><th>Official EN</th><th>Fan EN (_Alent_)</th>
      <th>All renderings seen</th><th>Note</th>
    </tr></thead>
    <tbody>
{body}
    </tbody>
  </table>
</div>
</body></html>"""
    d = os.path.join(ROOT, "dictionary", "review")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "index.html")
    open(p, "w", encoding="utf-8").write(htmlpage)
    print("wrote", p, "(%d review terms)" % len(review))
    return review

# ---------------------------------------------------------------------------
# Discrepancy report.
# ---------------------------------------------------------------------------
def build_report(entries, review):
    lines = []
    lines.append("# Translation discrepancies — Grandia JP→EN\n")
    lines.append(f"_Generated {TODAY} by `src/build_dictionary.py`._\n")
    lines.append("Cross-references three captured corpora (all in `dictionary/sources/`):\n")
    lines.append("- **official-script** — Shotgunnova's transcript of the official Sony PSX "
                 "localization (the script the TrekkiesUnite Saturn patch ships). Treated as **canonical**.")
    lines.append("- **alent-guide** — the _Alent_ Project Saturn **fan** translation (romaji + literal English).")
    lines.append("- **jp-wikipedia** — canonical Japanese kana names.\n")
    lines.append("## Terms where official ≠ fan (canonical naming differences)\n")
    lines.append("| Japanese | Romaji | Official (canonical) | _Alent_ fan | Notes |")
    lines.append("|---|---|---|---|---|")
    for e in sorted(entries, key=lambda x:x["category"]):
        if e["fan_en"] and e["fan_en"] != e["official_en"]:
            lines.append(f"| {e['jp']} | {e['romaji']} | **{e['official_en']}** | {e['fan_en']} | {e['note']} |")
    lines.append("\n## Flagged for review (seed-dictionary / spelling caveats)\n")
    # specific call-outs
    lines.append("- **アレント博物館** — the seed `dictionary/terms.json` recorded this as "
                 "*\"Arent Museum\"*. JP Wikipedia confirms the kana is correct (Liete builds the "
                 "「アレント博物館」 in Digital Museum), but the **official localization romanizes "
                 "アレント as \"Alent\"**, so the canonical form should be *\"Alent Museum\"* "
                 "(`Arent` → `Alent`). Logged to `exceptions.json` for your decision.")
    lines.append("- **エンジュール vs アレント** — these are two different things and must not be "
                 "conflated: エンジュール = the ancient **Angelou** civilization (and the Parm "
                 "「エンジュール博物館」/*Angelou Museum* whose NPC is the *Curator*); アレント = "
                 "**Alent**, the sky temple, and the name of Liete's Digital Museum.")
    lines.append("- **光翼人** — official **\"Icarian\"**; the fan guide uses a literal "
                 "\"winged people\". Use *Icarian*.")
    lines.append("- **グランドール** — official **\"The Grandeur\"** (Garlyle's battleship); "
                 "fan/romaji \"Grandall\".")
    lines.append("\n## Consistency notes\n")
    lines.append(f"- Glossary entries: {len(entries)}; of these {len(review)} have >1 English "
                 "rendering across sources (see `dictionary/review/index.html`).")
    lines.append("- The official localization is internally consistent for the main cast and "
                 "places; nearly all divergence is official-vs-fan romanization, not "
                 "official-internal contradiction.")
    p = os.path.join(ROOT, "docs", "translation-discrepancies.md")
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("wrote", p)

if __name__ == "__main__":
    entries = build_glossary()
    pairs = build_corpus()
    review = build_webpage(entries)
    build_report(entries, review)
    print("done.")
