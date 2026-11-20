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
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Dashboard canale</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#fff;--fg:#1a1a1a;--card:#f4f4f6;--mut:#666;--ac:#e5322d;--ac2:#2d6be5}
@media(prefers-color-scheme:dark){:root{--bg:#111;--fg:#eee;--card:#1c1c20;--mut:#999}}
*{box-sizing:border-box}body{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px system-ui,sans-serif;max-width:1000px;margin:auto}
h1{font-size:22px;margin:4px 0}h2{font-size:16px;margin:24px 0 8px}.mut{color:var(--mut);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-top:12px}
.k{background:var(--card);border-radius:10px;padding:12px}.k b{display:block;font-size:24px}
.card{background:var(--card);border-radius:10px;padding:12px;overflow-x:auto}
table{width:100%;border-collapse:collapse}td,th{padding:6px 8px;text-align:left;border-bottom:1px solid #8883;white-space:nowrap}
td.t{white-space:normal;min-width:180px}th{color:var(--mut);font-weight:500;font-size:13px}a{color:var(--ac2)}
.tag{background:var(--ac);color:#fff;border-radius:4px;padding:1px 6px;font-size:12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
</style></head><body>
<h1 id="n"></h1><div class="mut" id="u"></div><div class="kpis" id="k"></div>
<h2>Andamento</h2><div class="grid"><div class="card"><canvas id="c1"></canvas></div><div class="card"><canvas id="c2"></canvas></div></div>
<h2>Programmati</h2><div class="card"><table id="s"></table></div>
<h2>Tutti gli Short</h2><div class="card"><table id="a"></table></div>
<script>
const D=__DATA__;const f=n=>n.toLocaleString('it-IT');
const fmt=(s,tz)=>new Date(s).toLocaleString('it-IT',{timeZone:tz,day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
const pub=D.items.filter(v=>!v.scheduled&&v.privacy==='public'),sch=D.items.filter(v=>v.scheduled);
document.getElementById('n').textContent=D.name;
document.getElementById('u').textContent='Aggiornato '+fmt(D.updated,'Europe/Rome')+' (Roma)';
const tv=pub.reduce((a,v)=>a+v.views,0),tl=pub.reduce((a,v)=>a+v.likes,0);
const K=[['Iscritti',D.subs],['Views canale',D.views],['Short pubblici',pub.length],['Programmati',sch.length],
['Views medie',pub.length?Math.round(tv/pub.length):0],['Like/view %',tv?(100*tl/tv).toFixed(1):0],['Commenti',pub.reduce((a,v)=>a+v.comments,0)]];
document.getElementById('k').innerHTML=K.map(([a,b])=>`<div class="k"><b>${typeof b=='number'?f(b):b}</b><span class="mut">${a}</span></div>`).join('');
const lab=pub.map(v=>new Date(v.published).toLocaleDateString('it-IT',{day:'2-digit',month:'short'}));
if(window.Chart)new Chart(c1,{type:'bar',data:{labels:lab,datasets:[{label:'Views per Short',data:pub.map(v=>v.views),backgroundColor:'#e5322d'}]},options:{plugins:{legend:{display:true}}}});
let cum=0;if(window.Chart)new Chart(c2,{type:'line',data:{labels:lab,datasets:[{label:'Views cumulate',data:pub.map(v=>cum+=v.views),borderColor:'#2d6be5',tension:.3},
{label:'Like',data:pub.map(v=>v.likes),borderColor:'#e5a02d',tension:.3}]}});
const link=v=>`<a href="https://youtube.com/shorts/${v.id}" target="_blank">${v.title}</a>`;
s.innerHTML=sch.length?'<tr><th>Titolo<th>New York<th>Roma</tr>'+sch.map(v=>`<tr><td class="t">${link(v)}<td>${fmt(v.published,'America/New_York')}<td>${fmt(v.published,'Europe/Rome')}</tr>`).join(''):'<tr><td class="mut">Nessuno Short programmato</tr>';
a.innerHTML='<tr><th>Titolo<th>Data<th>Views<th>Like<th>Comm.<th>Durata</tr>'+[...D.items].reverse().map(v=>`<tr><td class="t">${link(v)}${v.scheduled?' <span class="tag">programmato</span>':''}<td>${fmt(v.published,'Europe/Rome')}<td>${f(v.views)}<td>${f(v.likes)}<td>${v.comments}<td>${v.sec}s</tr>`).join('');
</script></body></html>"""

if __name__ == "__main__":
    data = fetch(P.access_token())
    os.makedirs("output", exist_ok=True)
    open("output/dashboard.html", "w").write(HTML.replace("__DATA__", json.dumps(data)))
    print("output/dashboard.html", len(data["items"]), "video")
