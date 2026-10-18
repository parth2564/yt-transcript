"""Tiny local page: paste a YouTube link, get the full transcript, download it.

Run:  python app.py   (then open http://localhost:8765)
"""
import json
import os
import re
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from transcript import fetch, to_paragraphs, video_id, video_title

PORT = 8765

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>YouTube Transcript</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 860px; margin: 40px auto; padding: 0 16px; color: #222; }
  form { display: flex; gap: 8px; }
  input { flex: 1; padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 6px; }
  select { padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 6px; }
  #langinfo { color: #666; font-weight: normal; font-size: 14px; }
  button { padding: 10px 18px; font-size: 16px; border: 0; border-radius: 6px; background: #c00; color: #fff; cursor: pointer; }
  button:disabled { opacity: .5; }
  #bar { display: none; justify-content: space-between; align-items: center; margin: 20px 0 8px; }
  #out { white-space: pre-wrap; line-height: 1.6; }
  #err { color: #c00; margin-top: 16px; }
</style></head>
<body>
  <h2>YouTube Transcript</h2>
  <form id="f">
    <input id="url" placeholder="Paste YouTube link" autofocus>
    <select id="lang">
      <option value="auto">Auto</option>
      <option value="hi">Hindi</option>
      <option value="en">English</option>
      <option value="hi-to-en">Translate to English</option>
    </select>
    <button id="go">Get transcript</button>
  </form>
  <div id="err"></div>
  <div id="bar"><div><strong id="title"></strong><div id="langinfo"></div></div><button id="dl">Download .txt</button></div>
  <div id="out"></div>
<script>
let current = null;
f.onsubmit = async (e) => {
  e.preventDefault();
  err.textContent = ""; out.textContent = ""; bar.style.display = "none"; go.disabled = true; go.textContent = "Loading...";
  try {
    const r = await fetch("/api/transcript?lang=" + lang.value + "&url=" + encodeURIComponent(url.value));
    const d = await r.json();
    if (!r.ok) throw new Error(d.error);
    current = d;
    title.textContent = d.title; langinfo.textContent = "Language: " + d.language;
    out.textContent = d.text; bar.style.display = "flex";
  } catch (x) { err.textContent = x.message; }
  go.disabled = false; go.textContent = "Get transcript";
};
dl.onclick = () => {
  const blob = new Blob([current.title + "\\n" + current.link + "\\n\\n" + current.text], { type: "text/plain" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = current.title.replace(/[<>:"/\\\\|?*]/g, "").slice(0, 80) + ".txt";
  a.click();
};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, ctype):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            return self.send(200, PAGE, "text/html; charset=utf-8")
        if parsed.path == "/api/transcript":
            qs = urllib.parse.parse_qs(parsed.query)
            url = qs.get("url", [""])[0]
            lang = qs.get("lang", ["auto"])[0]
            try:
                vid = video_id(url)
                language, snippets = fetch(vid, lang)
                body = {
                    "title": video_title(vid),
                    "link": f"https://youtu.be/{vid}",
                    "language": language,
                    "text": to_paragraphs(snippets),
                }
                return self.send(200, json.dumps(body), "application/json")
            except Exception as e:
                msg = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
                if isinstance(e, LookupError):
                    pass
                elif type(e).__name__ in ("IpBlocked", "RequestBlocked", "YouTubeRequestFailed") or "429" in str(e):
                    if os.environ.get("PORT"):
                        msg = ("YouTube is blocking transcript requests from this hosting server (YouTube blocks "
                               "cloud servers). Use the PC version instead. The link itself is fine.")
                    else:
                        msg = ("YouTube has temporarily blocked transcript requests from your internet connection "
                               "(too many requests). Wait 30-60 minutes and try again, or switch network "
                               "(e.g. mobile hotspot). The link itself is fine.")
                elif "disabled" in msg.lower() or "No transcripts" in msg:
                    msg = "This video has no captions/transcript available."
                return self.send(400, json.dumps({"error": msg}), "application/json")
        self.send(404, "Not found", "text/plain")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if os.environ.get("PORT"):  # running on a cloud host
        server = ThreadingHTTPServer(("0.0.0.0", int(os.environ["PORT"])), Handler)
        print(f"Listening on port {os.environ['PORT']}", flush=True)
    else:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        print(f"Open http://localhost:{PORT}  (Ctrl+C to stop)")
        webbrowser.open(f"http://localhost:{PORT}")
    server.serve_forever()
