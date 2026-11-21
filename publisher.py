#!/usr/bin/env python3
"""Publisher agent: takes Shorts made by agent.py and publishes them on YouTube.

  python publisher.py --auth                      # once: get the YouTube refresh token
  python publisher.py output/barings              # publish one Short
  python publisher.py --all                       # publish every Short not yet published
  python publisher.py output/barings --dry-run    # only write/print title, description, tags
  python publisher.py output/barings --privacy private --at 2026-11-18T17:00:00Z
  python publisher.py output/barings --slot auto  # next free slot: 14:00 or 18:00 New York time

Needs YT_CLIENT_ID, YT_CLIENT_SECRET and (after --auth) YT_REFRESH_TOKEN.
Writes output/<slug>/youtube.json with the video id, so a Short is never uploaded twice.
"""
import argparse
import datetime as dt
import glob
import http.server
import json
import os
import re
import sys
import urllib.parse
import webbrowser

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
# upload + comments (engager.py). Changing scopes needs a new --auth.
SCOPE = ("https://www.googleapis.com/auth/youtube.upload "
         "https://www.googleapis.com/auth/youtube.force-ssl")
TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
CATEGORY_EDUCATION = "27"
TOKEN_FILE = os.path.join(HERE, "youtube_token.json")
# Daily publishing slots (local time). Shorts are uploaded as scheduled and go public then.
SLOTS = ["14:00", "18:00"]
SLOT_TZ = "America/New_York"  # US Eastern time
MIN_LEAD = dt.timedelta(minutes=20)  # YouTube needs publishAt a bit in the future

# Channel-wide hashtags: always present, after the story-specific ones.
BASE_TAGS = ["shorts", "finance", "money", "business", "truestory", "investing"]
CTA = "Follow for more true stories of fortunes made and lost."
DISCLAIMER = ("Images are AI-generated illustrations, not real photos. "
              "Story based on public reporting; not financial advice.")


def log(msg):
    print(f"[publisher] {msg}", flush=True)


# ---------- description & hashtags ----------

def _clean_tag(t):
    return re.sub(r"[^0-9A-Za-z]", "", t.lstrip("#")).lower()


def build_hashtags(script, limit=12):
    """Story hashtags first (they show above the title), then channel ones. No duplicates.
    YouTube ignores all hashtags if there are more than 15."""
    out = []
    for t in list(script.get("hashtags", [])) + BASE_TAGS:
        t = _clean_tag(t)
        if t and t not in out:
            out.append(t)
    # keep #shorts in the first three so YouTube files it as a Short
    out.remove("shorts")
    out.insert(0, "shorts")
    return out[:limit]


def build_metadata(script):
    tags = build_hashtags(script)
    title = script["title"].strip()
    if "#shorts" not in title.lower() and len(title) + 8 <= 100:
        title += " #shorts"
    desc = script["description"].strip()
    if "follow" not in desc.lower():
        desc += "\n\n" + CTA
    hashtag_line = " ".join("#" + t for t in tags)
    description = f"{desc}\n\n{DISCLAIMER}\n\n{hashtag_line}"
    # "tags" field: hidden keywords (max 500 chars total)
    keywords = tags + [w for w in script["slug"].split("_") if len(w) > 2]
    keywords, total = list(dict.fromkeys(keywords)), 0
    kept = []
    for k in keywords:
        total += len(k) + 1
        if total > 480:
            break
        kept.append(k)
    return {"title": title[:100], "description": description[:5000], "tags": kept}


# ---------- OAuth ----------

def _from_files(name):
    """Fallback for running on a PC: client_secret*.json downloaded from Google Cloud,
    and youtube_token.json written by --auth (both git-ignored)."""
    if name in ("YT_CLIENT_ID", "YT_CLIENT_SECRET"):
        files = sorted(glob.glob(os.path.join(HERE, "client_secret*.json")))
        if files:
            c = json.load(open(files[0]))
            c = c.get("installed") or c.get("web") or {}
            return c.get("client_id" if name == "YT_CLIENT_ID" else "client_secret")
    if name == "YT_REFRESH_TOKEN" and os.path.exists(TOKEN_FILE):
        return json.load(open(TOKEN_FILE)).get("refresh_token")


def env(name):
    v = os.environ.get(name) or _from_files(name)
    if not v:
        sys.exit(f"missing environment variable {name} (see README, section YouTube)")
    return v


def auth_flow():
    """Desktop OAuth flow on localhost: prints the refresh token to save as YT_REFRESH_TOKEN."""
    cid, secret = env("YT_CLIENT_ID"), env("YT_CLIENT_SECRET")
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": "REDIRECT", "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent"})
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in q or "error" in q:  # ignore e.g. /favicon.ico
                got["code"] = (q.get("code") or [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK, you can close this tab.")

        def log_message(self, *a):
            pass

    # free port picked by the OS on 127.0.0.1, so it never clashes with other local apps
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_address[1]}"
    url = url.replace("REDIRECT", urllib.parse.quote(redirect, safe=""))
    print("Open this link and allow access (choose your YouTube channel):\n" + url)
    webbrowser.open(url)
    while "code" not in got:
        srv.handle_request()
    if not got["code"]:
        sys.exit("authorization denied")
    r = requests.post(TOKEN_URL, data={
        "code": got["code"], "client_id": cid, "client_secret": secret,
        "redirect_uri": redirect, "grant_type": "authorization_code"}, timeout=30)
    r.raise_for_status()
    tok = r.json()["refresh_token"]
    json.dump({"refresh_token": tok}, open(TOKEN_FILE, "w"))
    print(f"\nSaved to {TOKEN_FILE}: publisher.py on this PC is ready.")
    print("For the cloud environment, add this as YT_REFRESH_TOKEN:\n" + tok)


def access_token():
    r = requests.post(TOKEN_URL, data={
        "client_id": env("YT_CLIENT_ID"), "client_secret": env("YT_CLIENT_SECRET"),
        "refresh_token": env("YT_REFRESH_TOKEN"), "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"token refresh failed: {r.status_code} {r.text}")
    return r.json()["access_token"]


# ---------- slots ----------

def _utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def taken_times(token):
    """Times (UTC) of the channel's recent uploads: scheduled publishAt or actual publish time.
    Covers Shorts made from other accounts too, since it reads the channel itself."""
    h = {"Authorization": f"Bearer {token}"}
    api = "https://www.googleapis.com/youtube/v3"
    r = requests.get(f"{api}/channels", params={"part": "contentDetails", "mine": "true"},
                     headers=h, timeout=30)
    r.raise_for_status()
    uploads = r.json()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    r = requests.get(f"{api}/playlistItems", params={
        "part": "contentDetails", "playlistId": uploads, "maxResults": 20}, headers=h, timeout=30)
    r.raise_for_status()
    ids = [i["contentDetails"]["videoId"] for i in r.json()["items"]]
    if not ids:
        return []
    r = requests.get(f"{api}/videos", params={"part": "status,snippet", "id": ",".join(ids)},
                     headers=h, timeout=30)
    r.raise_for_status()
    out = []
    for v in r.json()["items"]:
        st = v["status"]
        if st.get("publishAt"):
            out.append(_utc(st["publishAt"]))
        elif st.get("privacyStatus") == "public":
            out.append(_utc(v["snippet"]["publishedAt"]))
    return out


def local_scheduled(output_dir):
    """publish_at of uploads made from this machine (output/*/youtube.json). The channel's upload
    playlist can take minutes to list a new video, so two uploads in a row could get the same slot."""
    import glob
    out = []
    for f in glob.glob(os.path.join(output_dir, "*", "youtube.json")):
        try:
            at = json.load(open(f)).get("publish_at")
        except (OSError, ValueError):
            continue
        if at:
            out.append(_utc(at))
    return out


def next_slot(taken, now=None):
    """First slot (UTC, RFC3339) at least MIN_LEAD from now with no video within 90 min of it."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(SLOT_TZ)
    now = now or dt.datetime.now(dt.timezone.utc)
    day = now.astimezone(tz).date()
    for d in range(14):
        for s in SLOTS:
            hh, mm = map(int, s.split(":"))
            t = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz) + dt.timedelta(days=d)
            t = t.astimezone(dt.timezone.utc)
            if t - now < MIN_LEAD:
                continue
            if all(abs(t - x) > dt.timedelta(minutes=90) for x in taken):
                return t.strftime("%Y-%m-%dT%H:%M:%SZ")
    sys.exit("no free slot in the next 14 days")


# ---------- upload ----------

def upload(video, meta, privacy, publish_at, token):
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
              "containsSyntheticMedia": True}  # realistic AI images -> must be disclosed
    if publish_at:
        status["privacyStatus"] = "private"  # required by the API for scheduled videos
        status["publishAt"] = publish_at
    body = {"snippet": {**meta, "categoryId": CATEGORY_EDUCATION,
                        "defaultLanguage": "en", "defaultAudioLanguage": "en"},
            "status": status}
    size = os.path.getsize(video)
    h = {"Authorization": f"Bearer {token}"}
    r = requests.post(UPLOAD_URL, params={"uploadType": "resumable", "part": "snippet,status"},
                      headers={**h, "Content-Type": "application/json; charset=UTF-8",
                               "X-Upload-Content-Type": "video/mp4",
                               "X-Upload-Content-Length": str(size)},
                      data=json.dumps(body), timeout=60)
    if r.status_code != 200:
        sys.exit(f"upload init failed: {r.status_code} {r.text}")
    session = r.headers["Location"]
    with open(video, "rb") as f:
        r = requests.put(session, headers={**h, "Content-Type": "video/mp4"}, data=f, timeout=600)
    if r.status_code not in (200, 201):
        sys.exit(f"upload failed: {r.status_code} {r.text}")
    return r.json()["id"]


def publish(d, a, token=None):
    d = os.path.abspath(d)
    script = json.load(open(os.path.join(d, "script.json")))
    slug = script["slug"]
    video = os.path.join(d, f"short_{slug}.mp4")
    done = os.path.join(d, "youtube.json")
    if not os.path.exists(video):
        log(f"skip {slug}: no video")
        return
    if os.path.exists(done) and not a.dry_run:
        log(f"skip {slug}: already published ({json.load(open(done))['url']})")
        return
    meta = build_metadata(script)
    with open(os.path.join(d, "youtube_metadata.json"), "w") as f:
        json.dump(meta, f, indent=1, ensure_ascii=False)
    if a.dry_run:
        print(f"\nTITLE: {meta['title']}\n\n{meta['description']}\n\nTAGS: {', '.join(meta['tags'])}\n")
        return
    token = token or access_token()
    if a.slot == "auto" and not a.at:
        a.at = next_slot(taken_times(token) + local_scheduled(os.path.dirname(d)))
        log(f"slot: {a.at}")
    log(f"uploading {slug} ({os.path.getsize(video) / 1e6:.1f} MB, "
        f"{'scheduled ' + a.at if a.at else a.privacy})")
    vid = upload(video, meta, a.privacy, a.at, token)
    url = f"https://youtube.com/shorts/{vid}"
    json.dump({"id": vid, "url": url, "privacy": a.privacy, "publish_at": a.at,
               "title": meta["title"]}, open(done, "w"), indent=1)
    log(f"scheduled for {a.at}: {url}" if a.at else f"published: {url}")
    return url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", nargs="?", help="output/<slug> folder made by agent.py")
    ap.add_argument("--all", action="store_true", help="publish every unpublished Short in output/")
    ap.add_argument("--auth", action="store_true", help="one-time login, prints YT_REFRESH_TOKEN")
    ap.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])
    ap.add_argument("--at", help="schedule, RFC3339 UTC e.g. 2026-11-18T17:00:00Z")
    ap.add_argument("--slot", choices=["auto"],
                    help="schedule at the next free daily slot (SLOTS, New York time)")
    ap.add_argument("--dry-run", action="store_true", help="only build title/description/tags")
    a = ap.parse_args()

    if a.auth:
        return auth_flow()
    if a.all:
        folders = sorted(glob.glob(os.path.join(HERE, "output", "*", "script.json")))
        token = None if a.dry_run else access_token()
        for s in folders:
            publish(os.path.dirname(s), a, token)
            if a.slot:
                a.at = None  # each Short gets its own slot
    elif a.folder:
        publish(a.folder, a)
    else:
        ap.error("give a folder, --all or --auth")


if __name__ == "__main__":
    main()
