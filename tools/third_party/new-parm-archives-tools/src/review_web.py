#!/usr/bin/env python3
"""Build a self-contained interactive review web app from the current translation.

Reads every script/<MDT>_en.py + ja.json (via review.collect_rows) and writes script/review.html:
a JP↔EN review tool with per-line "flag for fix" + notes (saved in the browser), a TODO/flag
filter, and an Export that produces markdown to paste back. Pairs with the CLAUDE.md rule that
review requests are served as a hosted page.

    python3 src/review_web.py                # build script/review.html for all translated MDTs
    python3 src/review_web.py --serve [PORT]  # build + serve on PORT (default 8765), print URL
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import review as review_mod  # noqa: E402

# Short scene labels for the sidebar (fallback = MDT code).
LABELS = {
    "E800": "Intro — after the fall", "E81C": "FINALE — Liete's farewell",
    "E804": "Theater (Pakon)", "E808": "Archives (Darlin)", "E80C": "Library (Derlin/Jin)",
    "E810": "Screening Room (Dorlin)", "E818": "Cloud Bridge (hub)",
    "EB18": "Frog Room (Leen)", "EC00": "Gios Tower — entry",
    "EA04": "Norza: Moon", "EA08": "Norza: Star", "EA10": "Norza: Dark Room",
    "EA14": "Norza: Corridor", "EC04": "Gios 1F", "EC08": "Gios: Outer Wall",
    "EC0C": "Gios 2F", "EC10": "Gios 3F",
}


def build_data() -> dict:
    data = {}
    for en in sorted((ROOT / "script").glob("*_en.py")):
        base = en.stem[:-3]  # strip _en
        try:
            rows = review_mod.collect_rows(base)
        except FileNotFoundError:
            continue
        if not rows:
            continue
        data[base] = {"label": LABELS.get(base, base), "rows": rows}
    return data


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Grandia DM — translation review</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#222734;--ink:#e7e9ee;--mut:#8b93a7;--acc:#6aa6ff;
--ok:#46c08a;--warn:#e0a13a;--todo:#e0573a;}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--ink)}
#app{display:grid;grid-template-columns:260px 1fr;height:100vh}
#side{background:var(--panel);border-right:1px solid var(--line);overflow:auto;padding:12px}
#side h1{font-size:14px;margin:4px 6px 12px;color:var(--acc)}
.mdt{display:block;width:100%;text-align:left;background:none;border:0;color:var(--ink);
padding:8px 10px;border-radius:8px;cursor:pointer;font:inherit}
.mdt:hover{background:#1e2330}.mdt.active{background:#243049}
.mdt .code{font-weight:600}.mdt .meta{color:var(--mut);font-size:12px}
.mdt .badge{float:right;font-size:11px;color:var(--warn)}
#main{overflow:auto;padding:18px 22px}
#bar{position:sticky;top:0;background:var(--bg);padding-bottom:12px;display:flex;gap:10px;
align-items:center;flex-wrap:wrap}
#bar h2{margin:0;font-size:18px}#bar .sp{flex:1}
button.btn{background:#243049;color:var(--ink);border:1px solid var(--line);border-radius:8px;
padding:7px 12px;cursor:pointer}button.btn:hover{background:#2c3a57}
select,input[type=text]{background:#10131a;color:var(--ink);border:1px solid var(--line);
border-radius:8px;padding:6px 8px}
.piece{color:var(--mut);font-size:12px;letter-spacing:.04em;text-transform:uppercase;
margin:18px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}
.row{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px;
margin:8px 0}.row.flag{border-color:var(--warn);background:#221d12}
.row.todo{border-color:var(--todo)}
.row .id{font-size:11px;color:var(--mut);font-family:ui-monospace,monospace}
.row .sp{display:inline-block;font-size:11px;background:#243049;border-radius:6px;padding:1px 7px;
margin-left:6px;color:var(--acc)}
.jp{font-family:ui-monospace,"Hiragino Kaku Gothic Pro",monospace;color:#c6cfe0;margin:6px 0 2px}
.en{font-size:15px;margin:2px 0}.en.todo{color:var(--todo);font-style:italic}
.ctl{display:flex;gap:10px;align-items:center;margin-top:8px}
.ctl label{font-size:12px;color:var(--mut);cursor:pointer;user-select:none}
.ctl input[type=text]{flex:1}
.b{font-size:11px;color:var(--mut)}
#sum{font-size:12px;color:var(--mut)}
</style></head><body><div id="app">
<div id="side"><h1>GDM Review</h1><div id="list"></div></div>
<div id="main">
 <div id="bar"><h2 id="title"></h2><span id="sum"></span><span class="sp"></span>
  <select id="filter"><option value="all">All lines</option>
   <option value="flag">Flagged only</option><option value="todo">TODO only</option></select>
  <button class="btn" id="export">Export review ▾</button>
  <button class="btn" id="reset">Clear my notes</button></div>
 <div id="rows"></div></div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('data').textContent);
const KEY='gdm-review-v1';
let store=JSON.parse(localStorage.getItem(KEY)||'{}');
let cur=Object.keys(DATA)[0];
const save=()=>localStorage.setItem(KEY,JSON.stringify(store));
const rid=(m,r)=>`${m}/${r.piece}/${r.kind}${r.key}`;
function counts(m){let f=0,t=0,n=DATA[m].rows.length;for(const r of DATA[m].rows){
 const s=store[rid(m,r)]||{};if(s.flag)f++;if(!r.en)t++;}return{n,f,t};}
function renderList(){const L=document.getElementById('list');L.innerHTML='';
 for(const m in DATA){const c=counts(m);const b=document.createElement('button');
  b.className='mdt'+(m===cur?' active':'');
  b.innerHTML=`<span class="code">${m}</span>${c.f?`<span class="badge">⚑${c.f}</span>`:''}`+
   `<div class="meta">${DATA[m].label} · ${c.n} lines${c.t?` · ${c.t} TODO`:''}</div>`;
  b.onclick=()=>{cur=m;render();};L.appendChild(b);} }
function render(){renderList();
 document.getElementById('title').textContent=cur+' — '+DATA[cur].label;
 const c=counts(cur);document.getElementById('sum').textContent=
  `${c.n} lines · ${c.f} flagged · ${c.t} TODO`;
 const f=document.getElementById('filter').value;const box=document.getElementById('rows');
 box.innerHTML='';let piece=null;
 for(const r of DATA[cur].rows){const id=rid(cur,r);const s=store[id]||{};
  if(f==='flag'&&!s.flag)continue;if(f==='todo'&&r.en)continue;
  if(r.piece!==piece){piece=r.piece;const h=document.createElement('div');h.className='piece';
   h.textContent='piece '+piece+'  ['+r.cat+']';box.appendChild(h);}
  const d=document.createElement('div');d.className='row'+(s.flag?' flag':'')+(r.en?'':' todo');
  const who=r.speaker?`<span class="sp">${r.speaker}</span>`:'';
  d.innerHTML=`<span class="id">${id}</span>${who} <span class="b">b${r.budget}</span>`+
   `<div class="jp">${esc(r.jp)}</div>`+
   (r.en?`<div class="en">${esc(r.en)}</div>`:`<div class="en todo">— not yet translated —</div>`)+
   `<div class="ctl"><label><input type="checkbox" ${s.flag?'checked':''}> flag for fix</label>`+
   `<input type="text" placeholder="note / correction…" value="${esc(s.note||'')}"></div>`;
  const cb=d.querySelector('input[type=checkbox]'),tx=d.querySelector('input[type=text]');
  cb.onchange=()=>{store[id]={...store[id],flag:cb.checked};save();render();};
  tx.oninput=()=>{store[id]={...store[id],note:tx.value};save();};
  box.appendChild(d);} }
function esc(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
document.getElementById('filter').onchange=render;
document.getElementById('reset').onclick=()=>{if(confirm('Clear all your flags & notes?')){store={};save();render();}};
document.getElementById('export').onclick=()=>{let out='# Grandia DM translation review notes\\n\\n';
 for(const m in DATA){let lines='';for(const r of DATA[m].rows){const s=store[rid(m,r)]||{};
   if(!s.flag&&!s.note)continue;
   lines+=`- \`${rid(m,r)}\` ${s.flag?'⚑ ':''}\\n  JP: ${r.jp}\\n  EN: ${r.en||'(TODO)'}\\n`+
    (s.note?`  NOTE: ${s.note}\\n`:'');}
  if(lines)out+=`## ${m} — ${DATA[m].label}\\n${lines}\\n`;}
 const blob=new Blob([out],{type:'text/markdown'});const a=document.createElement('a');
 a.href=URL.createObjectURL(blob);a.download='gdm-review-notes.md';a.click();
 navigator.clipboard&&navigator.clipboard.writeText(out);};
render();
</script></body></html>"""


def build() -> Path:
    data = build_data()
    page = PAGE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = ROOT / "script" / "review.html"
    out.write_text(page, encoding="utf-8")
    n = sum(len(v["rows"]) for v in data.values())
    print(f"wrote {out}  ({len(data)} MDTs, {n} lines)")
    return out


def main() -> int:
    build()
    if "--serve" in sys.argv:
        import http.server
        import socketserver
        i = sys.argv.index("--serve")
        port = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) and sys.argv[i + 1].isdigit() else 8765
        import os
        os.chdir(ROOT)
        with socketserver.TCPServer(("127.0.0.1", port), http.server.SimpleHTTPRequestHandler) as s:
            print(f"serving review at http://127.0.0.1:{port}/script/review.html  (Ctrl-C to stop)")
            s.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
