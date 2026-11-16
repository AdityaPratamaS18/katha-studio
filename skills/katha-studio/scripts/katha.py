#!/usr/bin/env python3
"""
katha: make an animated story film (16:9, 1080p) from one film.json.

    python3 katha.py doctor                      check tools, keys and balances
    python3 katha.py setup                       save your API keys (run it yourself, in a terminal)
    python3 katha.py new <folder> --title "..."  start a film folder with an example film.json
    python3 katha.py validate <folder>           check film.json before you spend money
    python3 katha.py cost <folder>               estimate what the paid steps cost
    python3 katha.py voices --language hi        list library voices for a language (with preview links)
    python3 katha.py voices --add <voice_id> --owner <public_owner_id> --name "Narrator"
    python3 katha.py sheets <folder> [ids] [--yes]     one reference sheet for each character
    python3 katha.py images <folder> [ids] [--yes]     one picture for each scene
    python3 katha.py voice  <folder> [ids]             one ElevenLabs read for each scene (uses your quota)
    python3 katha.py talk   <folder> [ids] [--yes]     lip-synced clip for each "talk" scene (Kling AI Avatar)
    python3 katha.py move   <folder> [ids] [--yes]     moving clip for each "move" scene (Kling image-to-video)
    python3 katha.py build  <folder>                   captions, assembly, music, loudness, thumbnail
    python3 katha.py check  <folder>                   size, length, loudness of the finished film
    python3 katha.py frames <folder> [--every 20]      contact sheet of the finished film, to look at

Nothing that costs money runs without --yes. Without it you get the price.
Keys: environment FAL_KEY and ELEVENLABS_API_KEY, or ~/.config/katha-studio/config.json (from `setup`).
Needs: Python 3.9+, ffmpeg + ffprobe, and Google Chrome (or Chromium, Edge, Brave) for the captions.
No pip packages.
"""

import argparse
import base64
import concurrent.futures as cf
import getpass
import hashlib
import json
import math
import mimetypes
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
CONFIG_DIR = Path(os.environ.get("KATHA_CONFIG_DIR", Path.home() / ".config" / "katha-studio"))
CONFIG = CONFIG_DIR / "config.json"

W, H, FPS = 1920, 1080, 30
LEAD = 0.25        # silence before each line
TAIL = 0.45        # silence after each line
XF = 0.4           # crossfade between scenes (inside the silences)
LAST_HOLD = 1.5    # extra hold on the last scene

FAL_QUEUE = "https://queue.fal.run"
FAL_UPLOAD = "https://rest.alpha.fal.ai/storage/upload/initiate"
FAL_PRICING = "https://api.fal.ai/v1/models/pricing"
EL_API = "https://api.elevenlabs.io/v1"

MODELS = {
    # images
    "nano-banana-pro": {"t2i": "fal-ai/nano-banana-pro", "edit": "fal-ai/nano-banana-pro/edit", "usd": 0.15},
    "nano-banana-2": {"t2i": "fal-ai/nano-banana-2", "edit": "fal-ai/nano-banana-2/edit", "usd": 0.08},
    # talking shots (image + audio -> lip-synced video), price per second of output
    "kling-avatar": {"app": "fal-ai/kling-video/ai-avatar/v2/standard", "usd_s": 0.0562},
    "kling-avatar-pro": {"app": "fal-ai/kling-video/ai-avatar/v2/pro", "usd_s": 0.115},
    # moving shots (image -> video), price per second
    "kling-2.5": {"app": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video", "usd_s": 0.07},
}
DEFAULTS = {
    "sheet_model": "nano-banana-pro",
    "image_model": "nano-banana-pro",
    "image_resolution": "2K",
    "avatar_model": "kling-avatar",
    "move_model": "kling-2.5",
    "tts_model": "eleven_multilingual_v2",
    "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True},
    "currency": {"code": "USD", "per_usd": 1.0},
    "caption_font": "'Kohinoor Devanagari','Noto Sans Devanagari','Nirmala UI','Mangal','Noto Sans',sans-serif",
}
# Kling AI Avatar has no negative prompt. In tests, a prompt that named "subtitles" or held the spoken line
# made Kling draw fake subtitle text on some clips; its own default "." did not. Keep it.
AVATAR_PROMPT = "."
CHARS_PER_SECOND = 13.0   # rough speech rate, for estimates only


class Fail(SystemExit):
    pass


def die(msg):
    raise Fail(f"ERROR: {msg}")


def say(msg=""):
    print(msg, flush=True)


# ------------------------------------------------------------------ config and keys

def load_config():
    cfg = {}
    if CONFIG.exists():
        try:
            cfg = json.loads(CONFIG.read_text())
        except json.JSONDecodeError:
            die(f"{CONFIG} is not valid JSON")
    return cfg


def secret(name):
    env = {"fal": "FAL_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}[name]
    if os.environ.get(env):
        return os.environ[env].strip()
    v = load_config().get(f"{name}_key")
    if v:
        return v.strip()
    die(f"No {name} key. Run `python3 {Path(__file__).name} setup` in a terminal, or set ${env}.")


def has_secret(name):
    try:
        secret(name)
        return True
    except Fail:
        return False


def settings(film=None):
    s = json.loads(json.dumps(DEFAULTS))
    s.update({k: v for k, v in load_config().items() if not k.endswith("_key")})
    if film:
        s.update(film.get("settings", {}))
    return s


def money(usd, s):
    c = s.get("currency") or DEFAULTS["currency"]
    us = f"US${usd:,.4f}" if 0 < usd < 0.1 else f"US${usd:,.2f}"
    if c.get("code", "USD") == "USD":
        return us
    return f"{us} (about {c['code']} {usd * float(c['per_usd']):,.2f})"


# ------------------------------------------------------------------ http

def http(url, method="GET", payload=None, headers=None, timeout=120, raw=False):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "katha-studio/0.1")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            if raw:
                return body
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:700]
        hint = ""
        if e.code in (401, 403) and "balance" in detail.lower():
            hint = "\nHINT: your fal balance is empty. Add credit at https://fal.ai/dashboard/billing"
        elif e.code == 401:
            hint = "\nHINT: the API key is wrong or expired. Run setup again."
        die(f"HTTP {e.code} from {url.split('?')[0]}: {detail}{hint}")
    except urllib.error.URLError as e:
        die(f"Could not reach {url.split('?')[0]}: {e.reason}")


# ------------------------------------------------------------------ fal

def fal_headers():
    return {"Authorization": f"Key {secret('fal')}"}


def fal_upload(path, film_dir=None):
    """Upload a local file to fal storage. Cached by path, size and mtime."""
    p = Path(path)
    cache_file = (Path(film_dir) / ".cache" / "uploads.json") if film_dir else None
    cache = json.loads(cache_file.read_text()) if cache_file and cache_file.exists() else {}
    st = p.stat()
    ck = f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    if ck in cache:
        return cache[ck]
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    init = http(FAL_UPLOAD, "POST", {"content_type": ctype, "file_name": p.name}, fal_headers())
    req = urllib.request.Request(init["upload_url"], data=p.read_bytes(), method="PUT")
    req.add_header("Content-Type", ctype)
    urllib.request.urlopen(req, timeout=600)
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache[ck] = init["file_url"]
        cache_file.write_text(json.dumps(cache, indent=1))
    return init["file_url"]


def fal_run(app, payload, label="", poll=6, timeout=1800):
    job = http(f"{FAL_QUEUE}/{app}", "POST", payload, fal_headers())
    t0, last = time.time(), None
    while True:
        if time.time() - t0 > timeout:
            die(f"{label}: timed out after {timeout}s (request {job.get('request_id')})")
        st = http(job["status_url"], headers=fal_headers())
        if st.get("status") != last:
            last = st.get("status")
            say(f"  {label} {int(time.time() - t0):>4}s {last}")
        if last == "COMPLETED":
            return http(job["response_url"], headers=fal_headers())
        if last in ("FAILED", "ERROR", "CANCELLED"):
            die(f"{label}: job {last}: {json.dumps(st)[:500]}")
        time.sleep(poll)


def media_url(result):
    for k in ("images", "image", "video", "videos", "output"):
        v = result.get(k)
        if isinstance(v, list) and v:
            v = v[0]
        if isinstance(v, dict) and v.get("url"):
            return v["url"]
        if isinstance(v, str) and v.startswith("http"):
            return v
    die("the job finished but returned no media URL: " + json.dumps(result)[:500])


def download(url, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    with urllib.request.urlopen(url, timeout=900) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(out)
    return out


# ------------------------------------------------------------------ ffmpeg helpers

def ff(args, quiet=True):
    cmd = ["ffmpeg", "-hide_banner", "-y"] + (["-v", "error"] if quiet else []) + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        die("ffmpeg failed:\n" + " ".join(cmd)[:1500] + "\n" + r.stderr[-1500:])
    return r


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        die(f"cannot read the length of {path}")


def to_image(src, dst, width=None):
    """Any image (png, jpg, webp) to dst; optional width. Keeps 16:9 shots honest."""
    vf = [f"scale={width}:-2:flags=lanczos"] if width else []
    ff(["-i", src] + (["-vf", ",".join(vf)] if vf else []) + ["-q:v", "2", "-frames:v", "1", dst])


# ------------------------------------------------------------------ chrome (captions and thumbnail text)

def find_chrome():
    if os.environ.get("CHROME_PATH") and Path(os.environ["CHROME_PATH"]).exists():
        return os.environ["CHROME_PATH"]
    mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
    for p in mac:
        if Path(p).exists():
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge",
                 "brave-browser", "chrome", "msedge"):
        p = shutil.which(name)
        if p:
            return p
    win = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
    for p in win:
        if Path(p).exists():
            return p
    return None


def apple_silicon():
    if platform.system() != "Darwin":
        return False
    r = subprocess.run(["sysctl", "-n", "hw.optional.arm64"], capture_output=True, text=True)
    return r.stdout.strip() == "1"


def render_html(html_path, png_path, width=W, height=H, timeout=60):
    """Screenshot one HTML page with a transparent background.
    Chrome sometimes does not exit after a headless screenshot, so we wait for the file and then stop it."""
    chrome = find_chrome() or die("Chrome, Chromium, Edge or Brave is needed for captions. See `doctor`.")
    png_path = Path(png_path)
    if png_path.exists():
        png_path.unlink()
    profile = tempfile.mkdtemp(prefix="katha-chrome-")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--no-default-browser-check", "--disable-extensions", "--mute-audio",
           f"--user-data-dir={profile}", "--default-background-color=00000000",
           f"--window-size={width},{height}", f"--screenshot={png_path}", Path(html_path).resolve().as_uri()]
    if apple_silicon():
        # An Intel Python (Anaconda, old installers) runs under Rosetta, and its children start as Intel too.
        # Headless Chrome under Rosetta hangs, so ask for the native arm64 slice.
        cmd = ["/usr/bin/arch", "-arm64"] + cmd
    kw = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "posix":
        kw["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kw)
    t0, size = time.time(), -1
    try:
        while time.time() - t0 < timeout:
            if png_path.exists():
                s = png_path.stat().st_size
                if s > 0 and s == size:
                    break
                size = s
            if proc.poll() is not None and png_path.exists():
                break
            time.sleep(0.4)
    finally:
        if proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(proc.pid, signal.SIGKILL)
                else:
                    proc.kill()
            except (ProcessLookupError, PermissionError):
                pass
        shutil.rmtree(profile, ignore_errors=True)
    if not png_path.exists() or png_path.stat().st_size == 0:
        die(f"Chrome did not write {png_path.name}. Close other Chrome test windows and try again.")
    return png_path


CAPTION_CSS = """html,body{{margin:0;width:{W}px;height:{H}px;background:transparent;overflow:hidden}}
.c{{position:absolute;left:0;right:0;bottom:70px;text-align:center}}
.c span{{font-family:{font};font-weight:600;font-size:{size}px;color:{color};padding:6px 26px;
 background:rgba(0,0,0,.55);border-radius:14px;text-shadow:0 2px 4px #000;line-height:1.5;
 display:inline-block;max-width:1640px}}
.t{{position:absolute;left:60px;right:60px;top:{top}px;text-align:center;font-family:{font};font-weight:800;
 font-size:{tsize}px;color:{tcolor};line-height:1.25;text-shadow:0 0 30px rgba(255,140,0,.85),0 6px 12px #000}}"""


def page(body, s, look=None):
    look = look or {}
    css = CAPTION_CSS.format(W=W, H=H, font=look.get("font", s["caption_font"]), size=look.get("size", 54),
                             color=look.get("color", "#FFE27A"), top=look.get("title_top", 110),
                             tsize=look.get("title_size", 118), tcolor=look.get("title_color", "#FFD54A"))
    return f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>'


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------ film.json

def film_dir(arg):
    d = Path(arg).expanduser().resolve()
    if not (d / "film.json").exists():
        die(f"no film.json in {d}. Start one with `new`.")
    return d


def load_film(d):
    try:
        return json.loads((d / "film.json").read_text())
    except json.JSONDecodeError as e:
        die(f"film.json is not valid JSON: {e}")


def sid(sc):
    return f"{int(sc['id']):03d}"


def pick(scenes, ids, kind=None):
    want = {int(i) for i in ids} if ids else None
    return [sc for sc in scenes if (want is None or int(sc["id"]) in want) and (kind is None or sc.get("kind", "still") == kind)]


PLACE = re.compile(r"\{([a-z0-9_]+)\}")
TAG = re.compile(r"\[[^\]]*\]")


def validate(film, quiet=False):
    errs, warns = [], []
    chars = film.get("characters", {})
    voices = film.get("voices", {})
    if not film.get("title"):
        errs.append("title is empty")
    if not film.get("style"):
        errs.append("style is empty (one paragraph that every image prompt starts with)")
    ids = set()
    for sc in film.get("scenes", []):
        n = sc.get("id")
        if n in ids:
            errs.append(f"scene {n}: duplicate id")
        ids.add(n)
        k = sc.get("kind", "still")
        if k not in ("still", "talk", "move"):
            errs.append(f"scene {n}: kind must be still, talk or move")
        spk = sc.get("speaker")
        if not sc.get("text", "").strip():
            errs.append(f"scene {n}: text is empty")
        if spk not in voices:
            errs.append(f"scene {n}: speaker '{spk}' has no entry in voices")
        elif not voices[spk].get("voice_id"):
            warns.append(f"voice '{spk}' has no voice_id yet (pick one with `voices`)")
        for ph in PLACE.findall(sc.get("image", "")):
            if ph not in chars:
                errs.append(f"scene {n}: image names {{{ph}}} but there is no such character")
        if not sc.get("image") and not sc.get("image_from"):
            errs.append(f"scene {n}: image prompt is empty")
        if k == "talk":
            if spk not in chars:
                errs.append(f"scene {n}: a talk scene needs a speaker who is a character (not '{spk}')")
            elif f"{{{spk}}}" not in sc.get("image", "") and not sc.get("image_from"):
                errs.append(f"scene {n}: the speaker {{{spk}}} must be in the picture of a talk scene")
            img = sc.get("image", "").lower()
            if sc.get("image") and not any(w in img for w in ("front", "facing the camera", "looking at the camera")):
                warns.append(f"scene {n}: talk shots lip-sync best as a front-facing close-up; say so in the prompt")
        if len(TAG.sub("", sc.get("text", ""))) > 400:
            warns.append(f"scene {n}: a long line ({len(sc['text'])} characters); split it into 2 scenes")
    for v in sorted(set(warns)):
        if not quiet:
            say("WARN  " + v)
    for e in errs:
        say("FAIL  " + e)
    if errs:
        die(f"film.json has {len(errs)} problem(s)")
    return warns


def image_prompt(film, sc):
    chars = film.get("characters", {})
    body = PLACE.sub(lambda m: chars[m.group(1)]["look"], sc["image"])
    return f"{film['style'].strip()} {body.strip()}"


def scene_chars(sc):
    return list(dict.fromkeys(PLACE.findall(sc.get("image", ""))))


# ------------------------------------------------------------------ cost

def estimate(film, s, ids=None, step=None):
    scenes = film["scenes"] if not ids else pick(film["scenes"], ids)
    img = MODELS[s["image_model"]]["usd"]
    sheet = MODELS[s["sheet_model"]]["usd"]
    av = MODELS[s["avatar_model"]]["usd_s"]
    mv = MODELS[s["move_model"]]["usd_s"]
    rows = []
    n_chars = len(film.get("characters", {}))
    talk_s = sum(math.ceil(len(TAG.sub("", sc["text"])) / CHARS_PER_SECOND + LEAD + TAIL + 1) for sc in scenes
                 if sc.get("kind") == "talk")
    move_n = sum(1 for sc in scenes if sc.get("kind") == "move")
    tts_chars = sum(len(sc["text"]) for sc in scenes)
    rows.append(("sheets", f"{n_chars} character sheets x {money(sheet, s)}", n_chars * sheet))
    rows.append(("images", f"{len(scenes)} scene pictures x {money(img, s)}", len(scenes) * img))
    rows.append(("talk", f"about {talk_s} s of lip-synced video x {money(av, s)}/s", talk_s * av))
    rows.append(("move", f"{move_n} moving shots x 5 s x {money(mv, s)}/s", move_n * 5 * mv))
    rows.append(("voice", f"{tts_chars:,} characters of your ElevenLabs quota", 0.0))
    if step:
        rows = [r for r in rows if r[0] == step]
    return rows


# ------------------------------------------------------------------ commands: doctor and setup

def cmd_doctor(a):
    ok = True

    def line(good, what, fix=""):
        nonlocal ok
        ok &= bool(good)
        say(f"{'OK  ' if good else 'MISS'}  {what}" + ("" if good or not fix else f"\n      fix: {fix}"))

    sysname = platform.system()
    line(sys.version_info >= (3, 9), f"Python {platform.python_version()}", "install Python 3.9 or newer")
    brew = "brew install ffmpeg" if sysname == "Darwin" else (
        "sudo apt install ffmpeg" if sysname == "Linux" else "winget install ffmpeg")
    has_ff = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
    line(has_ff, "ffmpeg and ffprobe", brew)
    if has_ff:
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        need = ["xfade", "zoompan", "loudnorm", "overlay", "tpad", "acrossfade"]
        miss = [f for f in need if f" {f} " not in filters]
        line(not miss, "ffmpeg filters " + ", ".join(need), f"your ffmpeg lacks {miss}; install a full build ({brew})")
    chrome = find_chrome()
    line(chrome, f"Chrome for captions ({chrome or 'not found'})",
         "install Google Chrome, or set CHROME_PATH to Chromium, Edge or Brave")
    for name, url in (("fal", "https://fal.ai/dashboard/keys"), ("elevenlabs", "https://elevenlabs.io/app/settings/api-keys")):
        line(has_secret(name), f"{name} key", f"make a key at {url}, then run `python3 {Path(__file__).name} setup`")
    if has_secret("elevenlabs"):
        try:
            sub = http(f"{EL_API}/user/subscription", headers={"xi-api-key": secret("elevenlabs")})
            left = sub.get("character_limit", 0) - sub.get("character_count", 0)
            say(f"      ElevenLabs plan '{sub.get('tier')}': {left:,} characters left this month")
            if sub.get("tier") == "free":
                say("      NOTE: the free plan does not allow commercial use. Use Starter or above for a monetised channel.")
        except Fail as e:
            line(False, "ElevenLabs key works", str(e))
    if has_secret("fal"):
        try:
            http(f"{FAL_PRICING}?endpoint_id={MODELS['kling-avatar']['app']}", headers=fal_headers())
            say("      fal key accepted. fal does not show the balance here: see https://fal.ai/dashboard/billing")
        except Fail as e:
            line(False, "fal key works", str(e))
    say("\nREADY" if ok else "\nNOT READY: fix the MISS lines, then run doctor again.")
    if not ok:
        raise SystemExit(1)


def cmd_setup(a):
    if not sys.stdin.isatty():
        die("setup asks for your keys. Run it yourself in a terminal (not through Claude), "
            f"or set FAL_KEY and ELEVENLABS_API_KEY.\n  python3 {Path(__file__).resolve()} setup")
    cfg = load_config()
    say("katha-studio setup. Keys are saved to " + str(CONFIG) + " (only your user can read it).")
    say("Press Enter to keep a saved key.\n")
    for name, url in (("fal", "https://fal.ai/dashboard/keys"), ("elevenlabs", "https://elevenlabs.io/app/settings/api-keys")):
        have = " (saved)" if cfg.get(f"{name}_key") else ""
        v = getpass.getpass(f"{name} API key{have}. Get one at {url}\n> ").strip()
        if v:
            cfg[f"{name}_key"] = v
    cur = input("\nYour currency code for estimates (USD, INR, EUR...) [USD]: ").strip().upper() or "USD"
    rate = 1.0
    if cur != "USD":
        rate = float(input(f"How many {cur} is 1 US$? ").strip() or "1")
    cfg["currency"] = {"code": cur, "per_usd": rate}
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(cfg, indent=2))
    os.chmod(CONFIG, 0o600)
    say(f"\nSaved. Now run: python3 {Path(__file__).resolve()} doctor")


# ------------------------------------------------------------------ commands: new, validate, cost

def cmd_new(a):
    d = Path(a.folder).expanduser().resolve()
    if (d / "film.json").exists():
        die(f"{d}/film.json exists already")
    d.mkdir(parents=True, exist_ok=True)
    film = json.loads((TEMPLATES / "film.example.json").read_text())
    if a.title:
        film["title"] = a.title
    if a.language:
        film["language"] = a.language
    (d / "film.json").write_text(json.dumps(film, ensure_ascii=False, indent=2))
    for sub in ("img", "audio", "clips", "out"):
        (d / sub).mkdir(exist_ok=True)
    say(f"made {d}/film.json from the example. Replace the example story with yours.")


def cmd_validate(a):
    d = film_dir(a.folder)
    film = load_film(d)
    validate(film)
    n = len(film["scenes"])
    talk = sum(1 for sc in film["scenes"] if sc.get("kind") == "talk")
    secs = sum(len(TAG.sub("", sc["text"])) / CHARS_PER_SECOND + LEAD + TAIL for sc in film["scenes"])
    say(f"OK  {n} scenes ({talk} talk), about {secs / 60:.1f} min of film")


def cmd_cost(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    validate(film, quiet=True)
    rows = estimate(film, s)
    total = sum(r[2] for r in rows)
    say(f"{'step':<8} {'what':<62} cost")
    for step, what, usd in rows:
        say(f"{step:<8} {what:<62} {money(usd, s)}")
    say(f"{'total':<8} {'(first takes only; plan 30% more for shots you make again)':<62} {money(total, s)}")
    say(f"         with 30% retakes: {money(total * 1.3, s)}")


# ------------------------------------------------------------------ commands: voices

def cmd_voices(a):
    hdr = {"xi-api-key": secret("elevenlabs")}
    if a.add:
        if not a.owner:
            die("--add needs --owner <public_owner_id> from the list")
        name = a.name or a.add
        r = http(f"{EL_API}/voices/add/{a.owner}/{a.add}", "POST", {"new_name": name}, hdr)
        say(f"added '{name}' to your voices. voice_id: {r.get('voice_id', a.add)}")
        return
    if a.mine:
        r = http(f"{EL_API}/voices", headers=hdr)
        for v in r.get("voices", []):
            say(f"{v['voice_id']}  {v['name']:<28} {v.get('category', '')}")
        return
    q = {"page_size": a.n, "language": a.language}
    if a.accent:
        q["accent"] = a.accent
    if a.gender:
        q["gender"] = a.gender
    if a.search:
        q["search"] = a.search
    r = http(f"{EL_API}/shared-voices?{urllib.parse.urlencode(q)}", headers=hdr)
    vs = r.get("voices", [])
    if not vs:
        say("no voices found; try fewer filters")
    for v in vs:
        say(f"{v.get('name', '')[:30]:<30} {v.get('gender', ''):<7} {v.get('age', ''):<12} {v.get('accent', '')[:14]:<14} "
            f"{v.get('use_case', '')[:18]:<18}\n   voice_id={v['voice_id']} owner={v.get('public_owner_id')}\n"
            f"   {(v.get('description') or '')[:110]}\n   preview: {v.get('preview_url')}")


# ------------------------------------------------------------------ commands: sheets and images

def gen_image(model, prompt, out, refs, s, d, label):
    m = MODELS[model]
    payload = {"prompt": prompt, "num_images": 1, "aspect_ratio": "16:9", "output_format": "png"}
    if s.get("image_resolution"):
        payload["resolution"] = s["image_resolution"]
    if refs:
        payload["image_urls"] = [fal_upload(r, d) for r in refs]
        app = m["edit"]
    else:
        app = m["t2i"]
    res = fal_run(app, payload, label)
    tmp = download(media_url(res), Path(out).with_suffix(".download"))
    to_image(tmp, out)            # whatever came back (jpg, webp), store a real png
    tmp.unlink()
    (d / ".cache").mkdir(exist_ok=True)
    (d / ".cache" / f"{Path(out).stem}.prompt.txt").write_text(prompt)
    return out


def gate(rows, s, yes):
    total = sum(r[2] for r in rows)
    for _, what, usd in rows:
        say(f"  {what}: {money(usd, s)}")
    if not yes:
        say(f"DRY RUN. This step costs about {money(total, s)}. Run again with --yes to spend it.")
        return False
    return True


def cmd_sheets(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    chars = film.get("characters", {})
    ids = a.ids or list(chars)
    for c in ids:
        if c not in chars:
            die(f"no character '{c}'")
    usd = MODELS[s["sheet_model"]]["usd"]
    if not gate([("sheets", f"{len(ids)} character sheets", usd * len(ids))], s, a.yes):
        return
    (d / "img").mkdir(exist_ok=True)

    def one(c):
        prompt = (f"{film['style'].strip()} Character reference sheet on a plain light background: "
                  f"{chars[c]['look']}. Show the same character 3 times side by side: front view facing the camera, "
                  f"three-quarter view, and full body. Same face, age, height, costume and colours in all 3. "
                  f"No text, no labels, no watermark.")
        return gen_image(s["sheet_model"], prompt, d / "img" / f"char_{c}.png", chars[c].get("refs"), s, d, f"sheet {c}")

    with cf.ThreadPoolExecutor(4) as ex:
        for c, out in zip(ids, ex.map(one, ids)):
            say(f"sheet {c} -> {out}")
    say("Look at every sheet now: age, face, costume. Fix the 'look' text and make it again before the scenes.")


def cmd_images(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    validate(film, quiet=True)
    scenes = pick(film["scenes"], a.ids)
    if not a.ids and not a.redo:
        scenes = [sc for sc in scenes if not (d / "img" / f"s{sid(sc)}.png").exists() and not sc.get("image_from")]
    missing = [c for sc in scenes for c in scene_chars(sc) if not (d / "img" / f"char_{c}.png").exists()]
    if missing:
        die(f"make the character sheets first: {sorted(set(missing))}")
    if not scenes:
        say("every scene has a picture. Name scene ids to make one again.")
        return
    usd = MODELS[s["image_model"]]["usd"]
    if not gate([("images", f"{len(scenes)} scene pictures", usd * len(scenes))], s, a.yes):
        return

    def one(sc):
        refs = [d / "img" / f"char_{c}.png" for c in scene_chars(sc)] + [d / r for r in sc.get("refs", [])]
        prompt = image_prompt(film, sc)
        if refs:
            prompt += (" Use the reference images only for the faces, bodies and costumes of the characters; "
                       "keep each character exactly as in the references. No text, no captions, no watermark.")
        return gen_image(s["image_model"], prompt, d / "img" / f"s{sid(sc)}.png", refs, s, d, f"scene {sc['id']}")

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for sc, out in zip(scenes, ex.map(one, scenes)):
            say(f"scene {sc['id']} -> {out}")
    contact_sheet(d, [d / "img" / f"s{sid(sc)}.png" for sc in film["scenes"]], d / "img" / "contact.jpg")
    say(f"contact sheet: {d / 'img' / 'contact.jpg'}")


def contact_sheet(d, paths, out, cols=4):
    paths = [p for p in paths if Path(p).exists()]
    if not paths:
        return
    ins = []
    for p in paths:
        ins += ["-i", p]
    rows = math.ceil(len(paths) / cols)
    fc = "".join(f"[{i}:v]scale=480:270,setsar=1[t{i}];" for i in range(len(paths)))
    pad = cols * rows - len(paths)
    for j in range(pad):
        fc += f"color=black:s=480x270:d=1[p{j}];"
    labels = "".join(f"[t{i}]" for i in range(len(paths))) + "".join(f"[p{j}]" for j in range(pad))
    layout = "|".join(f"{(k % cols) * 480}_{(k // cols) * 270}" for k in range(cols * rows))
    fc += f"{labels}xstack=inputs={cols * rows}:layout={layout}[o]"
    ff(ins + ["-filter_complex", fc, "-map", "[o]", "-frames:v", "1", "-q:v", "3", out])


# ------------------------------------------------------------------ commands: voice

def clean_text(t):
    return re.sub(r"\s+", " ", TAG.sub("", t)).strip()


def cmd_voice(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    validate(film, quiet=True)
    voices = film["voices"]
    scenes = film["scenes"]
    todo = pick(scenes, a.ids)
    (d / "audio").mkdir(exist_ok=True)
    cache = d / ".cache" / "voice"
    cache.mkdir(parents=True, exist_ok=True)
    hdr = {"xi-api-key": secret("elevenlabs")}
    billed = 0
    index = {int(sc["id"]): i for i, sc in enumerate(scenes)}
    for sc in todo:
        v = voices[sc["speaker"]]
        if not v.get("voice_id"):
            die(f"voice '{sc['speaker']}' has no voice_id. Pick one with `voices`.")
        model = v.get("model", s["tts_model"])
        vs = dict(s["voice_settings"])
        vs.update(v.get("settings", {}))
        body = {"text": sc["text"], "model_id": model, "voice_settings": vs}
        if v.get("speed"):
            body["voice_settings"]["speed"] = v["speed"]
        if model != "eleven_v3":   # v3 does not take the neighbouring text
            i = index[int(sc["id"])]
            if i > 0:
                body["previous_text"] = clean_text(scenes[i - 1]["text"])
            if i + 1 < len(scenes):
                body["next_text"] = clean_text(scenes[i + 1]["text"])
        key = hashlib.sha1(json.dumps([v["voice_id"], body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        mp3, js = cache / f"{key}.mp3", cache / f"{key}.json"
        if not (mp3.exists() and js.exists()):
            r = http(f"{EL_API}/text-to-speech/{v['voice_id']}/with-timestamps?output_format=mp3_44100_128",
                     "POST", body, hdr, timeout=300)
            mp3.write_bytes(base64.b64decode(r["audio_base64"]))
            js.write_text(json.dumps({"text": sc["text"], "alignment": r.get("alignment")}, ensure_ascii=False))
            billed += len(sc["text"])
            note = "new"
        else:
            note = "cache"
        n = sid(sc)
        shutil.copy(mp3, d / "audio" / f"raw{n}.mp3")
        shutil.copy(js, d / "audio" / f"raw{n}.json")
        # the padded line: LEAD silence + voice + TAIL silence. Kling gets this file, so the clip and the film agree.
        ff(["-i", mp3, "-af", f"adelay={int(LEAD * 1000)}:all=1,apad=pad_dur={TAIL}", "-ar", "44100", "-ac", "2",
            "-c:a", "libmp3lame", "-b:a", "192k", d / "audio" / f"p{n}.mp3"])
        say(f"scene {sc['id']:>3} {sc['speaker']:<10} {duration(d / 'audio' / f'raw{n}.mp3'):5.2f} s  ({note})")
    say(f"done. {billed:,} characters billed to ElevenLabs this run.")


# ------------------------------------------------------------------ commands: talk and move

def cmd_talk(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    scenes = pick(film["scenes"], a.ids, "talk")
    if not a.ids and not a.redo:
        scenes = [sc for sc in scenes if not (d / "clips" / f"s{sid(sc)}.mp4").exists()]
    if not scenes:
        say("every talk scene has a clip. Name scene ids to make one again.")
        return
    for sc in scenes:
        for f in (d / "img" / f"s{sid(sc)}.png", d / "audio" / f"p{sid(sc)}.mp3"):
            if not f.exists():
                die(f"scene {sc['id']}: {f.name} is missing. Run images and voice first.")
    m = MODELS[s["avatar_model"]]
    secs = sum(math.ceil(duration(d / "audio" / f"p{sid(sc)}.mp3")) + 1 for sc in scenes)
    if not gate([("talk", f"{len(scenes)} talking clips, about {secs} s", secs * m["usd_s"])], s, a.yes):
        return
    (d / "clips").mkdir(exist_ok=True)

    def one(sc):
        n = sid(sc)
        jpg = d / ".cache" / f"s{n}_1920.jpg"     # fal takes images up to 5 MB
        jpg.parent.mkdir(exist_ok=True)
        to_image(d / "img" / f"s{n}.png", jpg, width=1920)
        payload = {"image_url": fal_upload(jpg, d), "audio_url": fal_upload(d / "audio" / f"p{n}.mp3", d),
                   "prompt": sc.get("talk_prompt", AVATAR_PROMPT)}
        res = fal_run(m["app"], payload, f"talk {sc['id']}", poll=10)
        out = download(media_url(res), d / "clips" / f"s{n}.mp4")
        check_strip(out)
        return out

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for sc, out in zip(scenes, ex.map(one, scenes)):
            say(f"scene {sc['id']} -> {out}")
    say("Look at each clips/s<id>_check.jpg for letters or fake subtitles, then watch the clips with sound.\n"
        "Remake a bad one with: talk <folder> <id> --yes --redo")


def check_strip(clip):
    """6 frames of a clip side by side, to look for stray text and a frozen face."""
    out = Path(clip).with_name(Path(clip).stem + "_check.jpg")
    dur = max(duration(clip), 0.5)
    ff(["-i", clip, "-vf", f"fps=6/{dur:.2f},scale=480:-2,tile=6x1", "-frames:v", "1", "-q:v", "3", out])
    return out


def cmd_move(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    scenes = pick(film["scenes"], a.ids, "move")
    if not a.ids and not a.redo:
        scenes = [sc for sc in scenes if not (d / "clips" / f"s{sid(sc)}.mp4").exists()]
    if not scenes:
        say("every move scene has a clip.")
        return
    m = MODELS[s["move_model"]]
    if not gate([("move", f"{len(scenes)} moving shots x 5 s", len(scenes) * 5 * m["usd_s"])], s, a.yes):
        return

    def one(sc):
        n = sid(sc)
        jpg = d / ".cache" / f"s{n}_1920.jpg"
        jpg.parent.mkdir(exist_ok=True)
        to_image(d / "img" / f"s{n}.png", jpg, width=1920)
        payload = {"image_url": fal_upload(jpg, d), "duration": "5",
                   "prompt": sc.get("motion", "Gentle natural motion, slow cinematic camera push in.") +
                   " Keep the animated style. No text, no talking.",
                   "negative_prompt": "text, subtitles, letters, watermark, talking, distorted faces"}
        res = fal_run(m["app"], payload, f"move {sc['id']}", poll=10)
        return download(media_url(res), d / "clips" / f"s{n}.mp4")

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for sc, out in zip(scenes, ex.map(one, scenes)):
            say(f"scene {sc['id']} -> {out}")


# ------------------------------------------------------------------ commands: build

def caption_chunks(sc, d, max_chars=42):
    """Split the line into caption chunks and time them from the ElevenLabs character alignment."""
    text = sc["text"]
    al = None
    js = d / "audio" / f"raw{sid(sc)}.json"
    if js.exists():
        al = (json.loads(js.read_text()) or {}).get("alignment")
    vdur = duration(d / "audio" / f"raw{sid(sc)}.mp3")
    # visible characters and their index in the sent text (tags like [whispers] are not shown)
    vis, idx, inside = [], [], False
    for i, ch in enumerate(text):
        if ch == "[":
            inside = True
        if not inside:
            vis.append(ch)
            idx.append(i)
        if ch == "]":
            inside = False
    clean = "".join(vis)
    # 1. pieces that end on punctuation
    pieces, start = [], 0
    for m in re.finditer(r"[।॥.!?,;:]+\s*", clean):
        pieces.append((start, m.end()))
        start = m.end()
    if clean[start:].strip():
        pieces.append((start, len(clean)))
    # 2. split a long piece at spaces into near-equal parts
    parts = []
    for s0, e0 in pieces:
        k = math.ceil((e0 - s0) / max_chars)
        if k <= 1:
            parts.append((s0, e0))
            continue
        cuts, target = [s0], (e0 - s0) / k
        spaces = [s0 + m.end() for m in re.finditer(r"\s+", clean[s0:e0])]
        for j in range(1, k):
            want = s0 + target * j
            if spaces:
                cuts.append(min(spaces, key=lambda x: abs(x - want)))
        cuts = sorted(set(cuts)) + [e0]
        parts += [(cuts[j], cuts[j + 1]) for j in range(len(cuts) - 1) if cuts[j] < cuts[j + 1]]
    # 3. join a short piece to the next one when both fit on one line
    merged = []
    for s0, e0 in parts:
        if merged and (merged[-1][1] - merged[-1][0]) < 14 and (e0 - merged[-1][0]) <= max_chars:
            merged[-1] = (merged[-1][0], e0)
        else:
            merged.append((s0, e0))
    out = []
    starts = ends = None
    if al and len(al.get("characters", [])) == len(text):
        starts, ends = al["character_start_times_seconds"], al["character_end_times_seconds"]
    total = max(1, len(clean.strip()))
    for k, (s0, e0) in enumerate(merged):
        seg = clean[s0:e0].strip()
        if not seg:
            continue
        if starts:
            t0 = starts[idx[s0]]
            t1 = ends[idx[min(e0, len(idx)) - 1]]
        else:
            t0 = vdur * s0 / total
            t1 = vdur * e0 / total
        out.append([t0, t1, seg])
    for k in range(len(out) - 1):           # no gap flicker between chunks
        out[k][1] = max(out[k][1], out[k + 1][0])
    if out:
        out[-1][1] = max(out[-1][1], vdur)
    return out


def scene_length(d, sc, last):
    return duration(d / "audio" / f"p{sid(sc)}.mp3") + (LAST_HOLD if last else 0)


def build_segment(d, film, sc, i, L, s, look):
    """One scene -> build/segNNN.mp4 (1080p30 video with captions + its own voice track)."""
    n = sid(sc)
    seg = d / "build" / f"seg{n}.mov"   # PCM audio: AAC adds a delay at each encode
    kind = sc.get("kind", "still")
    img = d / "img" / f"s{n}.png"
    if sc.get("image_from"):
        img = d / "img" / f"s{int(sc['image_from']):03d}.png"
    clip = d / "clips" / f"s{n}.mp4"
    caps = caption_chunks(sc, d) if film.get("captions", True) else []
    inputs, frames = [], int(round(L * FPS))
    if kind in ("talk", "move") and clip.exists():
        inputs += ["-i", clip]
        base = (f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS},tpad=stop_mode=clone:stop_duration={L + 5:.2f},"
                f"trim=duration={L:.3f},setpts=PTS-STARTPTS[v0]")
    else:
        if kind != "still":
            say(f"  WARN scene {sc['id']}: no clip yet, a zoom on the picture stands in")
        if not img.exists():
            die(f"scene {sc['id']}: {img.name} is missing. Run images first.")
        inputs += ["-loop", "1", "-framerate", FPS, "-i", img]
        zin = i % 2 == 0
        z = f"min(1+0.10*on/{frames},1.10)" if zin else f"max(1.10-0.10*on/{frames},1.0)"
        base = (f"[0:v]scale=3840:-2,zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:"
                f"s={W}x{H}:fps={FPS},setsar=1,trim=duration={L:.3f},setpts=PTS-STARTPTS[v0]")
    fc = [base]
    prev = "[v0]"
    capdir = d / "build" / "cap"
    for k, (t0, t1, text) in enumerate(caps):
        png = capdir / f"c{n}_{k:02d}.png"
        inputs += ["-i", png]
        fc.append(f"{prev}[{k + 1}:v]overlay=0:0:enable='between(t,{LEAD + t0:.2f},{LEAD + t1:.2f})'[o{k}]")
        prev = f"[o{k}]"
    fc.append(f"{prev}format=yuv420p[vout]")
    a_idx = len(caps) + 1
    inputs += ["-i", d / "audio" / f"p{n}.mp3"]
    fc.append(f"[{a_idx}:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur={L:.3f}[aout]")
    ff(inputs + ["-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]", "-t", f"{L:.3f}",
                 "-r", FPS, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "pcm_s16le", seg])
    return seg, caps


def render_captions(d, film, s, look, scenes, jobs=4):
    capdir = d / "build" / "cap"
    capdir.mkdir(parents=True, exist_ok=True)
    work = []
    for sc in scenes:
        if not film.get("captions", True):
            break
        for k, (_, _, text) in enumerate(caption_chunks(sc, d)):
            html = capdir / f"c{sid(sc)}_{k:02d}.html"
            png = html.with_suffix(".png")
            doc = page(f'<div class="c"><span>{esc(text)}</span></div>', s, look)
            if html.exists() and html.read_text() == doc and png.exists():
                continue
            html.write_text(doc)
            work.append((html, png))
    if work:
        say(f"rendering {len(work)} caption images")
        with cf.ThreadPoolExecutor(jobs) as ex:
            list(ex.map(lambda hp: render_html(*hp), work))


def music_bed(d, film, total, out):
    m = film.get("music")
    if m and (d / m).exists():
        vol = film.get("music_volume", 0.12)
        ff(["-stream_loop", "-1", "-i", d / m, "-t", f"{total:.2f}", "-af",
            f"volume={vol},afade=t=in:d=2,afade=t=out:st={max(0, total - 3):.2f}:d=3,aresample=48000", "-ac", "2", out])
        return out
    if film.get("music") is False:
        return None
    # soft tanpura-like drone (free, no licence needed)
    ff(["-f", "lavfi", "-i", f"sine=f=146.83:d={total:.2f}", "-f", "lavfi", "-i", f"sine=f=220:d={total:.2f}",
        "-f", "lavfi", "-i", f"sine=f=293.66:d={total:.2f}", "-f", "lavfi", "-i", f"sine=f=73.42:d={total:.2f}",
        "-filter_complex",
        "[0]volume=0.5[a];[1]volume=0.3[b];[2]volume=0.25[c];[3]volume=0.35[e];[a][b][c][e]amix=inputs=4,"
        f"tremolo=f=0.25:d=0.35,lowpass=f=900,aecho=0.8:0.7:120|240:0.3|0.2,volume=0.06,afade=t=in:d=2,"
        f"afade=t=out:st={max(0, total - 3):.2f}:d=3,aresample=48000[m]", "-map", "[m]", "-ac", "2", out])
    return out


def cmd_build(a):
    d = film_dir(a.folder)
    film = load_film(d)
    s = settings(film)
    validate(film, quiet=True)
    scenes = film["scenes"]
    look = film.get("caption_look", {})
    for sc in scenes:
        if not (d / "audio" / f"p{sid(sc)}.mp3").exists():
            die(f"scene {sc['id']}: no voice yet. Run voice first.")
    (d / "build").mkdir(exist_ok=True)
    (d / "out").mkdir(exist_ok=True)
    render_captions(d, film, s, look, scenes, jobs=a.jobs)
    lens = [scene_length(d, sc, i == len(scenes) - 1) for i, sc in enumerate(scenes)]

    def seg(i):
        return build_segment(d, film, scenes[i], i, lens[i], s, look)[0]

    say(f"building {len(scenes)} scene segments")
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        segs = list(ex.map(seg, range(len(scenes))))
    # join with crossfades, in groups so long films stay light on memory
    joined = join_segments(d, segs, lens)
    total = duration(joined)
    title_png = None
    if film.get("title_card", True):
        th = d / "build" / "title.html"
        th.write_text(page(f'<div class="t">{esc(film["title"])}</div>', s, look))
        title_png = render_html(th, d / "build" / "title.png")
    bed = music_bed(d, film, total, d / "build" / "music.m4a")
    slug = re.sub(r"[^a-z0-9]+", "-", (film.get("slug") or d.name).lower()).strip("-") or "film"
    out = d / "out" / f"{slug}.mp4"
    inputs = ["-i", joined]
    fc_v = "[0:v]"
    vf = []
    if title_png:
        inputs += ["-i", title_png]
        vf.append(f"[0:v][1:v]overlay=0:0:enable='between(t,0.3,3.8)'[tv]")
        fc_v = "[tv]"
    vf.append(f"{fc_v}fade=t=in:st=0:d=0.6,fade=t=out:st={total - 1:.2f}:d=1,format=yuv420p[vout]")
    a_in = "[0:a]"
    af = [f"{a_in}volume=1.0[voice]"]
    if bed:
        inputs += ["-i", bed]
        mi = 2 if title_png else 1
        af.append(f"[voice][{mi}:a]amix=inputs=2:normalize=0:duration=first[mix]")
        last = "[mix]"
    else:
        last = "[voice]"
    af.append(f"{last}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    ff(inputs + ["-filter_complex", ";".join(vf + af), "-map", "[vout]", "-map", "[aout]",
                 "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", FPS,
                 "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out])
    # one-pass loudnorm misses on short films; measure and correct with a plain gain (video is copied)
    lufs = measure_lufs(out)
    if lufs is not None and abs(lufs + 14) > 0.5:
        fixed = out.with_name(out.stem + ".fix.mp4")
        ff(["-i", out, "-c:v", "copy", "-af", f"volume={-14 - lufs:.2f}dB", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", fixed])
        fixed.replace(out)
    thumbnail(d, film, s, look)
    say(f"done: {out} ({total / 60:.1f} min). Thumbnail: {d / 'out' / 'thumbnail.jpg'}")


def join_segments(d, segs, lens, group=12):
    """Crossfade-join the scene segments. Works in groups of `group` so a 150-scene film never opens 150 inputs."""
    def xjoin(paths, plens, out):
        if len(paths) == 1:
            shutil.copy(paths[0], out)
            return out, plens[0]
        ins, fv, fa = [], [], []
        for p in paths:
            ins += ["-i", p]
        pv, pa, off = "[0:v]", "[0:a]", 0.0
        for k in range(1, len(paths)):
            off += plens[k - 1] - XF
            fv.append(f"{pv}[{k}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[v{k}]")
            fa.append(f"{pa}[{k}:a]acrossfade=d={XF}:c1=tri:c2=tri[a{k}]")
            pv, pa = f"[v{k}]", f"[a{k}]"
        ff(ins + ["-filter_complex", ";".join(fv + fa), "-map", pv, "-map", pa, "-c:v", "libx264",
                  "-preset", "veryfast", "-crf", "17", "-c:a", "pcm_s16le", out])
        return out, sum(plens) - XF * (len(paths) - 1)

    level, paths, plens = 0, list(segs), list(lens)
    while len(paths) > 1:
        nxt, nlens = [], []
        for g in range(0, len(paths), group):
            out = d / "build" / f"join{level}_{g // group:03d}.mov"
            o, l = xjoin(paths[g:g + group], plens[g:g + group], out)
            nxt.append(o)
            nlens.append(l)
        paths, plens, level = nxt, nlens, level + 1
    final = d / "build" / "joined.mov"
    if Path(paths[0]) != final:
        shutil.copy(paths[0], final)
    return final


def thumbnail(d, film, s, look):
    t = film.get("thumbnail", {})
    sc_id = t.get("scene") or film["scenes"][0]["id"]
    img = d / "img" / f"s{int(sc_id):03d}.png"
    if not img.exists():
        return
    th = d / "build" / "thumb.html"
    tl = dict(look)
    tl.setdefault("title_size", 150)
    tl.setdefault("title_top", 60)
    th.write_text(page(f'<div class="t">{esc(t.get("text", film["title"]))}</div>', s, tl))
    png = render_html(th, d / "build" / "thumb.png")
    ff(["-i", img, "-i", png, "-filter_complex", f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H}[b];[b][1:v]overlay=0:0,scale=1280:720", "-frames:v", "1", "-q:v", "2",
        d / "out" / "thumbnail.jpg"])


# ------------------------------------------------------------------ commands: check and frames

def measure_lufs(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    return float(m[-1]) if m else None


def cmd_check(a):
    d = film_dir(a.folder)
    vids = sorted((d / "out").glob("*.mp4"))
    if not vids:
        die("no film in out/. Run build first.")
    v = vids[-1]
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(v)],
                                     capture_output=True, text=True).stdout)
    vs = next(x for x in info["streams"] if x["codec_type"] == "video")
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(v), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True).stderr
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r)
    lufs = float(m[-1]) if m else None
    dur = float(info["format"]["duration"])
    say(f"{v.name}: {vs['width']}x{vs['height']}, {dur / 60:.1f} min, loudness {lufs} LUFS")
    probs = []
    if (int(vs["width"]), int(vs["height"])) != (W, H):
        probs.append("size is not 1920x1080")
    if lufs is None or abs(lufs + 14) > 1.5:
        probs.append("loudness is not near -14 LUFS (YouTube's level)")
    say("PASS" if not probs else "FAIL: " + "; ".join(probs))


def cmd_frames(a):
    d = film_dir(a.folder)
    vids = sorted((d / "out").glob("*.mp4"))
    if not vids:
        die("no film in out/. Run build first.")
    tmp = d / "build" / "frames"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    ff(["-i", vids[-1], "-vf", f"fps=1/{a.every},scale=480:270", tmp / "f%04d.jpg"])
    frames = sorted(tmp.glob("f*.jpg"))
    out = d / "out" / "frames.jpg"
    contact_sheet(d, frames[:40], out, cols=5)
    say(f"contact sheet: {out} ({min(len(frames), 40)} frames, one each {a.every} s)")


# ------------------------------------------------------------------ main

def main(argv=None):
    p = argparse.ArgumentParser(prog="katha", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    n = sub.add_parser("new")
    n.add_argument("folder")
    n.add_argument("--title")
    n.add_argument("--language")
    n.set_defaults(fn=cmd_new)
    for name, fn in (("validate", cmd_validate), ("cost", cmd_cost), ("check", cmd_check)):
        x = sub.add_parser(name)
        x.add_argument("folder")
        x.set_defaults(fn=fn)
    v = sub.add_parser("voices")
    v.add_argument("--language", default="hi")
    v.add_argument("--gender")
    v.add_argument("--accent", help="for example: standard, hindi, tamil")
    v.add_argument("--search")
    v.add_argument("--n", type=int, default=20)
    v.add_argument("--mine", action="store_true")
    v.add_argument("--add")
    v.add_argument("--owner")
    v.add_argument("--name")
    v.set_defaults(fn=cmd_voices)
    for name, fn, paid in (("sheets", cmd_sheets, True), ("images", cmd_images, True), ("voice", cmd_voice, False),
                           ("talk", cmd_talk, True), ("move", cmd_move, True), ("build", cmd_build, False)):
        x = sub.add_parser(name)
        x.add_argument("folder")
        x.add_argument("ids", nargs="*")
        x.add_argument("--jobs", type=int, default=4)
        if paid:
            x.add_argument("--yes", action="store_true", help="spend the money")
            x.add_argument("--redo", action="store_true", help="make again even if the file exists")
        x.set_defaults(fn=fn)
    f = sub.add_parser("frames")
    f.add_argument("folder")
    f.add_argument("--every", type=int, default=20)
    f.set_defaults(fn=cmd_frames)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
