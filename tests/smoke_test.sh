#!/usr/bin/env bash
# Offline smoke test: no API keys, no network, no money.
# It makes fake pictures, voice lines and a talk clip with ffmpeg, then runs the free commands and a full build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
K="$ROOT/skills/katha-studio/scripts/katha.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
export KATHA_CONFIG_DIR="$WORK/config"   # never read the real config
unset FAL_KEY ELEVENLABS_API_KEY || true
F="$WORK/film"

python3 "$K" --version
python3 "$K" new "$F" --title "Smoke test" --language en

python3 - "$F" <<'PY'
import json, sys
p = sys.argv[1] + "/film.json"
f = json.load(open(p))
f["characters"] = {"hero": {"look": "a kind young farmer in a white kurta"}}
f["voices"] = {"narrator": {"voice_id": "test"}, "hero": {"voice_id": "test"}}
f["scenes"] = [
    {"id": 1, "speaker": "narrator", "kind": "still", "text": "Once upon a time, in a small village, there lived a farmer.",
     "image": "Wide shot of {hero} in a green field."},
    {"id": 2, "speaker": "hero", "kind": "talk", "text": "The rain will come. I know it will come!",
     "image": "Front-facing close-up of {hero} looking at the camera, mouth closed."},
    {"id": 3, "speaker": "narrator", "kind": "still", "text": "And that night, the rain came.",
     "image": "{hero} in the rain at night."},
]
f["captions"] = False
f["title_card"] = False
f["thumbnail"] = {"scene": 1, "text": "Smoke test"}
json.dump(f, open(p, "w"), indent=2)
PY

python3 "$K" validate "$F"
python3 "$K" cost "$F"

# fake assets in the places the paid steps write them
for i in 1 2 3; do
  n=$(printf %03d $i)
  ffmpeg -v error -y -f lavfi -i "testsrc2=s=2752x1536:d=1" -frames:v 1 "$F/img/s$n.png"
  ffmpeg -v error -y -f lavfi -i "sine=f=$((200 + i * 80)):d=2.5" -ac 1 "$F/audio/raw$n.mp3"
  ffmpeg -v error -y -i "$F/audio/raw$n.mp3" -af "adelay=250:all=1,apad=pad_dur=0.45" -ac 2 "$F/audio/p$n.mp3"
done
ffmpeg -v error -y -f lavfi -i "testsrc=s=1280x720:r=24:d=3" -pix_fmt yuv420p "$F/clips/s002.mp4"

# a paid step without --yes must stop at the price and spend nothing
python3 "$K" talk "$F" 2 --redo | grep -q "DRY RUN"
echo "ok dry run stops"

python3 "$K" build "$F"
python3 "$K" check "$F"

# captions need a browser; test them when one is installed
if python3 -c "import sys; sys.path.insert(0, '$ROOT/skills/katha-studio/scripts'); import katha; sys.exit(0 if katha.find_chrome() else 1)"; then
  python3 - "$F" <<'PY'
import json, sys
p = sys.argv[1] + "/film.json"
f = json.load(open(p)); f["captions"] = True; f["title_card"] = True
json.dump(f, open(p, "w"), indent=2)
PY
  python3 "$K" build "$F"
  python3 "$K" check "$F"
  ls "$F/build/cap/"*.png > /dev/null
  echo "ok captions"
else
  echo "skip captions: no Chrome on this machine"
fi

python3 "$K" frames "$F" --every 2
test -s "$F/out/thumbnail.jpg"
echo "SMOKE TEST PASSED"
