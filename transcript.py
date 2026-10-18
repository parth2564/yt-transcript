"""Download YouTube transcripts as clean text files.

Usage:
    python transcript.py <url> [<url> ...]
    python transcript.py -f links.txt        (one URL per line)

Output goes to ./transcripts/<title> [<id>].txt (plain text)
and ./transcripts/<title> [<id>].timestamped.txt
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

OUT_DIR = Path(__file__).parent / "transcripts"
PREFERRED_LANGS = ["en", "en-US", "en-GB", "hi"]


def video_id(url: str) -> str:
    url = url.strip()
    if re.fullmatch(r"[\w-]{11}", url):
        return url
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname and "youtu.be" in parsed.hostname:
        return parsed.path.lstrip("/")[:11]
    qs = urllib.parse.parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]
    m = re.search(r"/(?:shorts|embed|live)/([\w-]{11})", parsed.path)
    if m:
        return m.group(1)
    raise ValueError(f"Could not find a video ID in: {url}")


def video_title(vid: str) -> str:
    try:
        url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
            f"https://www.youtube.com/watch?v={vid}"
        )
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r)["title"]
    except Exception:
        return vid


ENGLISH = ["en", "en-US", "en-GB", "en-IN"]


def fetch(vid: str, lang: str = "auto"):
    """lang: "auto" | "hi" | "en" | "hi-to-en" (Hindi/other translated to English by YouTube)."""
    transcripts = YouTubeTranscriptApi().list(vid)
    available = ", ".join(sorted({t.language for t in transcripts})) or "none"

    def find(codes):
        try:
            return transcripts.find_transcript(codes)
        except Exception:
            return None

    if lang == "hi":
        t = find(["hi"])
        if not t:
            raise LookupError(f"No Hindi transcript for this video. Available: {available}")
    elif lang == "en":
        t = find(ENGLISH)
        if not t:
            raise LookupError(f"No English transcript for this video. Try 'Translate to English'. Available: {available}")
    elif lang == "hi-to-en":
        # YouTube often already has an (auto) English track; otherwise ask it to translate.
        t = find(ENGLISH)
        if not t:
            src = find(["hi"]) or next(iter(transcripts))
            if not any(l.language_code == "en" for l in src.translation_languages):
                raise LookupError(f"YouTube doesn't offer an English translation for this video. Available: {available}")
            t = src.translate("en")
    else:
        t = find(PREFERRED_LANGS) or next(iter(transcripts))  # fall back to whatever language exists
    return t.language, t.fetch()


def to_paragraphs(snippets, gap=2.0, max_len=600) -> str:
    """Join caption fragments into readable paragraphs (break on pauses)."""
    paras, cur, last_end = [], [], 0.0
    for s in snippets:
        text = re.sub(r"\s*\[[^\]]*\]\s*", " ", s.text.replace("\n", " ")).strip()
        if not text:
            continue
        if cur and (s.start - last_end > gap or sum(map(len, cur)) > max_len):
            paras.append(" ".join(cur))
            cur = []
        cur.append(text)
        last_end = s.start + s.duration
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras)


def stamp(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


def process(url: str) -> None:
    vid = video_id(url)
    title = video_title(vid)
    lang, snippets = fetch(vid)
    safe = re.sub(r'[<>:"/\\|?*]', "", title)[:80].strip()
    base = OUT_DIR / f"{safe} [{vid}]"
    header = f"{title}\nhttps://youtu.be/{vid}\nLanguage: {lang}\n\n"

    OUT_DIR.mkdir(exist_ok=True)
    base.with_suffix(".txt").write_text(header + to_paragraphs(snippets), encoding="utf-8")
    base.with_suffix(".timestamped.txt").write_text(
        header + "\n".join(f"[{stamp(s.start)}] {s.text.strip()}" for s in snippets),
        encoding="utf-8",
    )
    print(f"OK   {title}  ->  {base.with_suffix('.txt').name}")
    return base.with_suffix(".txt")


def main(argv):
    if not argv:
        argv = [input("Paste YouTube link(s), space-separated: ")]
    urls = []
    if argv[0] == "-f":
        urls = [l for l in Path(argv[1]).read_text().splitlines() if l.strip()]
    else:
        for a in argv:
            urls += a.split()
    for u in urls:
        try:
            process(u)
        except Exception as e:
            print(f"FAIL {u}: {type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}")


if __name__ == "__main__":
    main(sys.argv[1:])
