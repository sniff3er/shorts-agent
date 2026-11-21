"""Dashboard HTML del canale: statistiche, andamento e Short programmati.
Uso: python dashboard.py  -> output/dashboard.html (dati letti da YouTube, serve YT_*)."""
import datetime as dt
import json
import os
import re
import requests
import publisher as P

API = "https://www.googleapis.com/youtube/v3"


def fetch(token):
    h = {"Authorization": f"Bearer {token}"}
    g = lambda path, **p: requests.get(f"{API}/{path}", params=p, headers=h, timeout=30)
    r = g("channels", part="contentDetails,statistics,snippet", mine="true")
    r.raise_for_status()
    ch = r.json()["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, tok = [], None
    while len(ids) < 200:
        p = dict(part="contentDetails", playlistId=up, maxResults=50)
        if tok:
            p["pageToken"] = tok
        r = g("playlistItems", **p)
        r.raise_for_status()
        j = r.json()
        ids += [i["contentDetails"]["videoId"] for i in j["items"]]
        tok = j.get("nextPageToken")
        if not tok:
            break
    vids = []
    for i in range(0, len(ids), 50):
        r = g("videos", part="snippet,statistics,status,contentDetails", id=",".join(ids[i:i + 50]))
        r.raise_for_status()
        for v in r.json()["items"]:
            s, st = v.get("statistics", {}), v["status"]
            sec = 0
            m = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", v["contentDetails"]["duration"])
            if m:
                sec = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
            vids.append(dict(
                id=v["id"], title=v["snippet"]["title"],
                published=st.get("publishAt") or v["snippet"]["publishedAt"],
                scheduled=bool(st.get("publishAt")) and st.get("privacyStatus") == "private",
                privacy=st.get("privacyStatus"), sec=sec,
                views=int(s.get("viewCount", 0)), likes=int(s.get("likeCount", 0)),
                comments=int(s.get("commentCount", 0))))
    cs = ch["statistics"]
    return dict(name=ch["snippet"]["title"], subs=int(cs.get("subscriberCount", 0)),
                views=int(cs.get("viewCount", 0)), videos=int(cs.get("videoCount", 0)),
                items=sorted(vids, key=lambda x: x["published"]),
                updated=dt.datetime.now(dt.timezone.utc).isoformat())


HTML = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Finance Commm Dashboard</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700&family=Share+Tech+Mono&display=swap">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#02080f;--panel:#06172466;--ln:#19e3ff55;--cy:#19e3ff;--or:#ff9d2e;--fg:#cdf6ff;--mut:#5fa0b3;--ok:#3dffb0;color-scheme:dark;
--hd:Orbitron,system-ui,sans-serif;--mo:'Share Tech Mono',ui-monospace,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px var(--mo);
background-image:radial-gradient(ellipse at 50% -10%,#0a3a52 0,transparent 60%),linear-gradient(#19e3ff0d 1px,transparent 1px),linear-gradient(90deg,#19e3ff0d 1px,transparent 1px);background-size:100% 100%,32px 32px,32px 32px;
padding-block:20px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
.w{max-width:1040px;margin:auto}
header{display:flex;align-items:center;gap:16px;flex-wrap:wrap;border-bottom:1px solid var(--ln);padding-bottom:14px}
.ring{width:72px;height:72px;flex:none}
.ring .r1{transform-origin:50% 50%;animation:sp 12s linear infinite}.ring .r2{transform-origin:50% 50%;animation:sp 7s linear infinite reverse}
@keyframes sp{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.ring *,.dot{animation:none!important}}
h1{font:700 22px var(--hd);letter-spacing:.14em;margin:0;color:var(--cy);text-shadow:0 0 12px #19e3ff88;text-transform:uppercase}
.sub{color:var(--mut);font-size:13px;letter-spacing:.08em;margin-top:4px}
.clk{margin-left:auto;text-align:right;font-size:13px;color:var(--mut);line-height:1.6}.clk b{color:var(--cy);font:500 18px var(--hd)}
h2{font:500 13px var(--hd);letter-spacing:.2em;color:var(--cy);margin:26px 0 10px;text-transform:uppercase;display:flex;gap:10px;align-items:center}
h2:after{content:"";flex:1;height:1px;background:linear-gradient(90deg,var(--ln),transparent)}
.p{position:relative;background:var(--panel);border:1px solid var(--ln);padding:14px;min-width:0;backdrop-filter:blur(4px)}
.p:before,.p:after{content:"";position:absolute;width:12px;height:12px;border:2px solid var(--cy)}
.p:before{top:-1px;left:-1px;border-right:0;border-bottom:0}.p:after{bottom:-1px;right:-1px;border-left:0;border-top:0}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-top:18px}
.k b{display:block;font:700 28px var(--hd);color:#fff;text-shadow:0 0 14px #19e3ffaa;font-variant-numeric:tabular-nums}
.k span{color:var(--mut);font-size:12px;letter-spacing:.12em;text-transform:uppercase}
.k.o b{color:var(--or);text-shadow:0 0 14px #ff9d2eaa}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:12px}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse}
td,th{padding:8px;text-align:left;border-bottom:1px solid #19e3ff22;white-space:nowrap}td.t{white-space:normal;min-width:200px}
th{color:var(--mut);font-weight:400;font-size:12px;letter-spacing:.14em;text-transform:uppercase}
td.n{font-variant-numeric:tabular-nums;color:#fff}
a{color:var(--cy);text-decoration:none}a:hover{text-shadow:0 0 8px var(--cy)}a:focus-visible{outline:1px solid var(--or);outline-offset:2px}
.tag{border:1px solid var(--or);color:var(--or);padding:1px 6px;font-size:11px;letter-spacing:.1em;text-transform:uppercase}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok);margin-right:6px;animation:pl 2s infinite}
@keyframes pl{50%{opacity:.3}}
.cd{color:var(--or)}.empty{color:var(--mut);letter-spacing:.1em}
</style></head><body><div class="w">
<header>
<svg class="ring" viewBox="0 0 72 72" fill="none" aria-hidden="true"><circle cx="36" cy="36" r="33" stroke="#19e3ff44"/>
<g class="r1"><circle cx="36" cy="36" r="29" stroke="#19e3ff" stroke-width="3" stroke-dasharray="30 16 6 16"/></g>
<g class="r2"><circle cx="36" cy="36" r="21" stroke="#ff9d2e" stroke-width="2" stroke-dasharray="4 8"/></g>
<circle cx="36" cy="36" r="10" fill="#19e3ff22" stroke="#19e3ff"/><circle cx="36" cy="36" r="4" fill="#fff"/></svg>
<div><h1 id="n"></h1><div class="sub"><span class="dot"></span>SISTEMA ONLINE · <span id="u"></span></div></div>
<div class="clk"><div>ROMA <b id="cr"></b></div><div>NEW YORK <b id="cn"></b></div></div>
</header>
<div class="kpis" id="k"></div>
<h2>Telemetria</h2><div class="grid"><div class="p"><canvas id="c1"></canvas></div><div class="p"><canvas id="c2"></canvas></div></div>
<h2>Coda di lancio</h2><div class="p tw"><table id="s"></table></div>
<h2>Archivio Short</h2><div class="p tw"><table id="a"></table></div>
</div>
<script>
const D=__DATA__;const f=n=>n.toLocaleString('it-IT');
const fmt=(s,tz)=>new Date(s).toLocaleString('it-IT',{timeZone:tz,day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const pub=D.items.filter(v=>!v.scheduled&&v.privacy==='public'),sch=D.items.filter(v=>v.scheduled);
n.textContent=D.name;u.textContent='AGG. '+fmt(D.updated,'Europe/Rome').toUpperCase();
const tick=()=>{const t=z=>new Date().toLocaleTimeString('it-IT',{timeZone:z,hour:'2-digit',minute:'2-digit',second:'2-digit'});cr.textContent=t('Europe/Rome');cn.textContent=t('America/New_York');
document.querySelectorAll('[data-t]').forEach(e=>{let d=new Date(e.dataset.t)-new Date();if(d<0){e.textContent='IMMINENTE';return}let h=Math.floor(d/36e5),m=Math.floor(d%36e5/6e4),s=Math.floor(d%6e4/1e3);e.textContent=`T-${h}h ${String(m).padStart(2,'0')}m ${String(s).padStart(2,'0')}s`})};
setInterval(tick,1000);
const tv=pub.reduce((a,v)=>a+v.views,0),tl=pub.reduce((a,v)=>a+v.likes,0);
const K=[['Iscritti',D.subs],['Views canale',D.views],['Short online',pub.length],['In coda',sch.length,1],['Views medie',pub.length?Math.round(tv/pub.length):0],['Like / view %',tv?(100*tl/tv).toFixed(1):0],['Commenti',pub.reduce((a,v)=>a+v.comments,0)]];
k.innerHTML=K.map(([a,b,o])=>`<div class="p k${o?' o':''}"><b>${typeof b=='number'?f(b):b}</b><span>${a}</span></div>`).join('');
const lab=pub.map(v=>new Date(v.published).toLocaleDateString('it-IT',{day:'2-digit',month:'short'}));
if(window.Chart){Chart.defaults.color='#5fa0b3';Chart.defaults.font.family="'Share Tech Mono',monospace";Chart.defaults.borderColor='#19e3ff22';
new Chart(c1,{type:'bar',data:{labels:lab,datasets:[{label:'VIEWS / SHORT',data:pub.map(v=>v.views),backgroundColor:'#19e3ff88',borderColor:'#19e3ff',borderWidth:1}]}});
let cum=0;new Chart(c2,{type:'line',data:{labels:lab,datasets:[{label:'VIEWS CUMULATE',data:pub.map(v=>cum+=v.views),borderColor:'#19e3ff',backgroundColor:'#19e3ff22',fill:true,tension:.3,pointBackgroundColor:'#fff'},
{label:'LIKE',data:pub.map(v=>v.likes),borderColor:'#ff9d2e',tension:.3,pointBackgroundColor:'#ff9d2e'}]}})}
const link=v=>`<a href="https://youtube.com/shorts/${v.id}" target="_blank" rel="noopener">${v.title}</a>`;
s.innerHTML=sch.length?'<tr><th>Titolo<th>New York<th>Roma<th>Conto alla rovescia</tr>'+sch.map(v=>`<tr><td class="t">${link(v)}<td class="n">${fmt(v.published,'America/New_York')}<td class="n">${fmt(v.published,'Europe/Rome')}<td class="cd" data-t="${v.published}"></tr>`).join(''):'<tr><td class="empty">// NESSUNO SHORT IN CODA</tr>';
a.innerHTML='<tr><th>Titolo<th>Data<th>Views<th>Like<th>Comm.<th>Durata</tr>'+[...D.items].reverse().map(v=>`<tr><td class="t">${link(v)}${v.scheduled?' <span class="tag">in coda</span>':''}<td class="n">${fmt(v.published,'Europe/Rome')}<td class="n">${f(v.views)}<td class="n">${f(v.likes)}<td class="n">${v.comments}<td class="n">${v.sec}s</tr>`).join('');
tick();
</script></body></html>"""

if __name__ == "__main__":
    data = fetch(P.access_token())
    os.makedirs("output", exist_ok=True)
    html = HTML.replace("__DATA__", json.dumps(data))
    open("output/dashboard.html", "w").write(html)
    # versione per Artifact (senza doctype/head)
    page = re.sub(r'<!doctype html><html lang="it"><head><meta charset="utf-8">\s*<meta name="viewport"[^>]*>', "", html)
    page = page.replace("</head><body>", "").replace("</body></html>", "")
    open("output/dashboard_artifact.html", "w").write(page)
    print("output/dashboard.html", len(data["items"]), "video")
