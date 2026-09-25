#!/usr/bin/env python3
"""Build a self-contained drama caption review page (audio synced to captions).

Reads src/theater/captions/dramaN.json + the decoded WAV, emits an HTML the user opens to:
play the drama audio, watch each caption highlight at its timecode, edit the EN, flag JP/timing
issues, and export the corrected JSON. Per CLAUDE.md review-workflow (host a page, don't dump in chat).

  python3 src/theater/review_drama.py 1            # -> work/theater/review_drama1.html
Serve from repo root:  python3 -m http.server 8765   then open /work/theater/review_drama1.html
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def build(n: int) -> Path:
    cap = json.loads((ROOT / f"src/theater/captions/drama{n}.json").read_text())
    wavs = list((ROOT / "work/theater").glob(f"drama{n}_idx*.wav"))
    wav_rel = ("/work/theater/" + wavs[0].name) if wavs else ""
    out = ROOT / f"work/theater/review_drama{n}.html"
    html = _TEMPLATE.replace("__DATA__", json.dumps(cap, ensure_ascii=False)) \
                    .replace("__WAV__", wav_rel) \
                    .replace("__N__", str(n))
    out.write_text(html, encoding="utf-8")
    return out


_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Theater drama __N__ — caption review</title>
<style>
 :root{--bg:#14121a;--panel:#1f1b29;--line:#2c2738;--hi:#3a2f55;--accent:#c9a84c;--txt:#e8e4f0}
 *{box-sizing:border-box} body{margin:0;font:14px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--txt)}
 header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);padding:12px 18px;z-index:5}
 h1{margin:0 0 6px;font-size:17px} .sub{color:#9b93ad;font-size:12px}
 audio{width:100%;margin-top:8px} .bar{display:flex;gap:10px;align-items:center;margin-top:8px;flex-wrap:wrap}
 button{background:var(--line);color:var(--txt);border:1px solid #3a3550;border-radius:6px;padding:6px 12px;cursor:pointer}
 button:hover{background:var(--hi)} .t{color:var(--accent);font-variant-numeric:tabular-nums;cursor:pointer}
 table{border-collapse:collapse;width:100%} td{border-bottom:1px solid var(--line);padding:8px 10px;vertical-align:top}
 tr.cur{background:var(--hi)} tr.flag{outline:2px solid #b5552f}
 .spk{color:#8fb6e6;font-weight:600;white-space:nowrap} .jp{color:#cfc7df;font-size:13px}
 .en{width:100%;background:#100e16;color:#fff;border:1px solid #332d46;border-radius:5px;padding:5px;font:inherit}
 .note{color:#8a8;font-size:11px;margin-top:3px} .fl{cursor:pointer;opacity:.4} .fl.on{opacity:1}
</style></head><body>
<header>
 <h1>Drama __N__ — <span id="ttl"></span></h1>
 <div class="sub" id="meta"></div>
 <audio id="au" src="__WAV__" controls preload="auto"></audio>
 <div class="bar">
  <button onclick="seek(-5)">« 5s</button><button onclick="tog()">Play/Pause</button>
  <button onclick="seek(5)">5s »</button>
  <span class="sub">click a ✎ time to jump · edit EN inline · ⚑ flags a line · </span>
  <button onclick="exp()">⬇ Export corrected JSON</button>
 </div>
</header>
<table><tbody id="rows"></tbody></table>
<script>
const D=__DATA__, L=D.lines;
document.getElementById('ttl').textContent=(D.title_en||'')+'  ('+(D.title_jp||'')+')';
document.getElementById('meta').textContent=`${L.length} lines · ${D.duration_s}s · ${(D.characters||[]).join(', ')} · ${D.review_status||''}`;
const au=document.getElementById('au'), rows=document.getElementById('rows');
const fmt=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${(t%60).toFixed(2).padStart(5,'0')}`;
L.forEach((l,i)=>{
 const tr=document.createElement('tr');tr.id='r'+i;
 tr.innerHTML=`<td class="t" onclick="au.currentTime=${l.start};au.play()">${fmt(l.start)}</td>
  <td class="spk">${l.spk}</td>
  <td><div class="jp">${l.jp||''}</div>${l.note?`<div class="note">⚠ ${l.note}</div>`:''}</td>
  <td><textarea class="en" rows="2" oninput="L[${i}].en=this.value">${l.en||''}</textarea></td>
  <td><span class="fl" title="flag" onclick="L[${i}]._flag=!L[${i}]._flag;this.classList.toggle('on');document.getElementById('r${i}').classList.toggle('flag')">⚑</span></td>`;
 rows.appendChild(tr);
});
let cur=-1;
au.addEventListener('timeupdate',()=>{
 const t=au.currentTime; let k=-1;
 for(let i=0;i<L.length;i++){ if(t>=L[i].start && t<(L[i].end>L[i].start?L[i].end:L[i].start+4)) k=i; }
 if(k!==cur){ if(cur>=0)document.getElementById('r'+cur).classList.remove('cur');
  if(k>=0){const e=document.getElementById('r'+k);e.classList.add('cur');e.scrollIntoView({block:'center',behavior:'smooth'});} cur=k; }
});
function seek(d){au.currentTime=Math.max(0,au.currentTime+d)}
function tog(){au.paused?au.play():au.pause()}
function exp(){const b=new Blob([JSON.stringify(D,null,2)],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='drama__N___reviewed.json';a.click()}
</script></body></html>"""


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    p = build(n)
    print(f"wrote {p}")
