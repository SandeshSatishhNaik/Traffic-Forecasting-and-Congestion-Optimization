"""Build a single offline HTML dashboard that replays moments from the test week.

Input : pickle written by `routing.py --save` (forecasts, speeds, reference speeds, trip estimates).
Output: one HTML file with the data embedded. It contains readings and forecasts derived from TomTom
        results, so keep the file private (do not commit it).
"""
import argparse
import json

import numpy as np
import pandas as pd

import prepare

CHAINS = [
    ("ORR eastbound (Silk Board to KR Puram)", ["orr_ccw_01", "orr_ccw_02", "orr_ccw_03", "orr_ccw_04", "orr_iblur", "orr_bellandur", "orr_ccw_07", "orr_doddanekundi"]),
    ("ORR westbound (KR Puram to Silk Board)", ["orr_mahadevapura", "orr_marathahalli", "orr_cw_03", "orr_cw_04", "orr_cw_05", "orr_cw_06", "orr_cw_07", "orr_hsr", "orr_cw_09"]),
    ("Hosur Road", ["hosur_bommanahalli", "hosur_02"]),
    ("Old Airport Rd (inbound) and Varthur Rd (outbound)", ["old_airport_konena", "varthur_kundalahalli"]),
]
LABEL = {"orr_ccw_01": "Silk Board", "orr_ccw_02": "HSR Layout", "orr_ccw_03": "Agara", "orr_ccw_04": "Agara to Iblur", "orr_iblur": "Iblur",
         "orr_bellandur": "Bellandur", "orr_ccw_07": "Bellandur to Doddanekundi", "orr_doddanekundi": "Doddanekundi to KR Puram",
         "orr_mahadevapura": "KR Puram to Mahadevapura", "orr_marathahalli": "Marathahalli", "orr_cw_03": "Marathahalli to Bellandur", "orr_cw_04": "Bellandur",
         "orr_cw_05": "Bellandur to Iblur", "orr_cw_06": "Iblur to Agara", "orr_cw_07": "Agara", "orr_hsr": "HSR Layout", "orr_cw_09": "Silk Board",
         "hosur_bommanahalli": "Bommanahalli", "hosur_02": "Silk Board to Lalbagh", "old_airport_konena": "Old Airport Rd (inbound)", "varthur_kundalahalli": "Varthur Rd (outbound)"}


def r1(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 1)


def build(pkl, out):
    D = pd.read_pickle(pkl)
    F, grid, ref, T = D["F"], D["grid"], D["ref"], D["T"]
    seg = pd.read_csv(prepare.SEGMENTS_CSV).set_index("segment_id")
    moments = []
    for d in F[15].index:
        if d.day_of_week >= 5 or prepare.day_type(pd.DatetimeIndex([d]))[0] != "weekday":
            continue
        core = [r for r in grid.columns if r.startswith("orr")]
        if grid.loc[d, core].notna().sum() < 14:
            continue
        m = {"t": d.strftime("%a %d %b %H:%M"), "roads": {}, "trips": {}}
        for r in grid.columns:
            row = {"now": r1(grid.at[d, r])}
            for h in (15, 30, 60):
                row[f"f{h}"] = r1(F[h].at[d, r])
                tt = d + pd.Timedelta(minutes=h)
                row[f"a{h}"] = r1(grid.at[tt, r]) if tt in grid.index else None
            m["roads"][r] = row
        for _, x in T[T.depart == d].iterrows():
            m["trips"][x["trip"]] = {k: r1(x[k]) for k in ("actual", "current", "historical", "forecast")}
        moments.append(m)
    data = dict(moments=moments, ref={k: r1(v) for k, v in ref.items()}, length={k: float(v) for k, v in seg["length_km"].items()},
                chains=CHAINS, label=LABEL, mae={"15": 2.98, "30": 3.38, "60": 3.51}, base={"15": 3.16, "30": 3.91, "60": 4.42})
    html = TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")))
    open(out, "w", encoding="utf-8").write(html)
    return len(moments)


TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Traffic Forecast Replay</title>
<style>
:root{--bg:#f4f6f9;--card:#fff;--ink:#1b1f2a;--mut:#5a6275;--line:#dfe3ea;--g:#2bb673;--a:#f5a623;--r:#e5484d;--na:#c9cfda;--acc:#3b82f6}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--card:#1b2030;--ink:#eef1f6;--mut:#a3adc2;--line:#2c3348;--na:#3a4258}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Calibri,Arial,sans-serif}
header{padding:18px 24px 6px}h1{margin:0;font:700 26px Cambria,Georgia,serif}.sub{color:var(--mut);margin-top:2px}
.bar{display:flex;flex-wrap:wrap;gap:14px;align-items:center;padding:10px 24px}
select,button{font:inherit;padding:7px 12px;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;cursor:pointer}
button.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}.grp{display:flex;gap:6px;align-items:center}.grp b{color:var(--mut);font-weight:600;margin-right:2px}
main{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:16px;padding:6px 24px 24px}
@media (max-width:900px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card h2{margin:0 0 8px;font:700 17px Cambria,Georgia,serif}
.chain{margin:12px 0 4px}.chain .t{font-weight:600;margin-bottom:5px}
.strip{display:flex;gap:3px;height:54px}.seg{border-radius:6px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:13px;min-width:30px;cursor:default;text-shadow:0 1px 2px rgba(0,0,0,.35)}
.names{display:flex;gap:3px;margin-top:3px}.names span{font-size:11px;color:var(--mut);overflow:hidden;white-space:nowrap;text-overflow:ellipsis;text-align:center;min-width:30px}
.leg{display:flex;gap:14px;flex-wrap:wrap;color:var(--mut);font-size:13px;margin-top:10px}.leg i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:5px;vertical-align:-1px}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:6px 4px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--mut);font-weight:600}
td.n,th.n{text-align:right}.best{color:var(--g);font-weight:700}.warn{color:var(--r);font-weight:700}
ul{margin:6px 0 0 18px;padding:0}.note{color:var(--mut);font-size:13px;margin-top:8px}
</style></head><body>
<header><h1>Traffic Forecast Replay: Bengaluru Outer Ring Road</h1>
<div class="sub">21 road stretches, speeds from TomTom. Replays real moments from the test week (25 to 31 October 2026): the forecast made at that moment next to what actually happened.</div></header>
<div class="bar">
<div class="grp"><b>Moment</b><select id="mom"></select></div>
<div class="grp"><b>Show</b><button data-k="now">Now</button><button data-k="f15">Forecast +15</button><button data-k="f30">Forecast +30</button><button data-k="f60">Forecast +60</button></div>
<div class="grp"><b>Compare with</b><button data-c="a">Actual later</button></div>
</div>
<main><section class="card" id="map"></section>
<aside><div class="card"><h2>Early warnings</h2><div id="alerts"></div></div>
<div class="card" style="margin-top:16px"><h2>Trip time (minutes)</h2><div id="trip"></div></div>
<div class="card" style="margin-top:16px"><h2>Model error (test week, MAE km/h)</h2><div id="err"></div></div></aside></main>
<script>
const D=__DATA__;const $=s=>document.querySelector(s);
let cur=0,key="now",cmp=false;
const col=(v,r)=>{if(v==null)return"var(--na)";const q=v/r;return q>=.85?"var(--g)":q>=.6?"var(--a)":"var(--r)"};
const sel=$("#mom");D.moments.forEach((m,i)=>{const o=document.createElement("option");o.value=i;o.textContent=m.t;sel.appendChild(o)});
sel.onchange=()=>{cur=+sel.value;draw()};
document.querySelectorAll("button[data-k]").forEach(b=>b.onclick=()=>{key=b.dataset.k;cmp=false;draw()});
document.querySelector("button[data-c]").onclick=()=>{if(key!="now"){cmp=!cmp;draw()}};
function value(r,m){const x=m.roads[r];if(cmp&&key!="now")return x["a"+key.slice(1)];return x[key]}
function draw(){const m=D.moments[cur];
document.querySelectorAll("button[data-k]").forEach(b=>b.classList.toggle("on",b.dataset.k==key&&!cmp));
document.querySelector("button[data-c]").classList.toggle("on",cmp);
let h=`<h2>${cmp?"What actually happened":key=="now"?"Speeds now":"Forecast "+key.replace("f","+")+" min"} <span style="font-weight:400;color:var(--mut)">(${m.t})</span></h2>`;
D.chains.forEach(([t,ids])=>{const tot=ids.reduce((s,r)=>s+Math.sqrt(D.length[r]),0);
h+=`<div class="chain"><div class="t">${t}</div><div class="strip">`+ids.map(r=>{const v=value(r,m);return `<div class="seg" title="${D.label[r]||r}: ${v==null?"no reading":v+" km/h (normal "+D.ref[r]+")"}" style="flex:${Math.sqrt(D.length[r])/tot*ids.length};background:${col(v,D.ref[r])}">${v==null?"":Math.round(v)}</div>`}).join("")+`</div><div class="names">`+ids.map(r=>`<span style="flex:${Math.sqrt(D.length[r])/tot*ids.length}" title="${D.label[r]||r}">${D.label[r]||r}</span>`).join("")+`</div></div>`});
h+=`<div class="leg"><span><i style="background:var(--g)"></i>flowing (85% of normal or more)</span><span><i style="background:var(--a)"></i>slow (60 to 85%)</span><span><i style="background:var(--r)"></i>congested (below 60%)</span><span><i style="background:var(--na)"></i>no reading</span></div><div class="note">Numbers are km/h. Segment width grows with road length (square-root scale). Normal = night-time speed of that road.</div>`;
$("#map").innerHTML=h;
const al=[];D.chains.forEach(([t,ids])=>ids.forEach(r=>{const x=m.roads[r];[30,60].forEach(hh=>{const f=x["f"+hh],a=x["a"+hh];if(f!=null&&x.now!=null&&f/D.ref[r]<.6&&x.now/D.ref[r]>=.6){al.push({r,hh,f,a})}})}));
const seen={};const uniq=al.filter(a=>{const k=a.r+a.hh;if(seen[k])return false;seen[k]=1;return true});
$("#alerts").innerHTML=uniq.length?"<ul>"+uniq.map(a=>`<li><b>${D.label[a.r]||a.r}</b>: predicted ${Math.round(a.f)} km/h in ${a.hh} min (normal ${Math.round(D.ref[a.r])})${a.a!=null?`; actual ${Math.round(a.a)} km/h`+(a.a/D.ref[a.r]<.6?" <span class=\"warn\">congested</span>":" (no jam)"):""}</li>`).join("")+"</ul>":"<div class='note'>No stretch that is flowing now is predicted to become congested within the hour.</div>";
const tr=Object.entries(m.trips);$("#trip").innerHTML=tr.length?tr.map(([n,x])=>{const rows=[["Live map (current speeds held)",x.current],["Historical average",x.historical],["Graph forecast",x.forecast],["Actual",x.actual]];const best=Math.min(Math.abs(x.current-x.actual),Math.abs(x.forecast-x.actual));
return `<div style="margin-bottom:10px"><b style="font-size:13px">${n}</b><table>`+rows.map(([l,v])=>`<tr><td>${l}</td><td class="n ${l=="Actual"?"best":""}">${v==null?"-":v.toFixed(1)}</td></tr>`).join("")+`</table></div>`}).join(""):"<div class='note'>No complete trip data at this moment.</div>";
$("#err").innerHTML=`<table><tr><th>Horizon</th><th class="n">Repeat speed</th><th class="n">Graph model</th></tr>`+["15","30","60"].map(k=>`<tr><td>+${k} min</td><td class="n">${D.base[k].toFixed(2)}</td><td class="n best">${D.mae[k].toFixed(2)}</td></tr>`).join("")+`</table><div class="note">Lower is better. 5 seeds, 7 test days.</div>`}
draw();
</script></body></html>
"""

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(build(a.demo, a.out), "moments")
