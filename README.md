# katha-studio

A Claude Code skill that makes animated mythology and devotional story films for YouTube.
You tell Claude the story. Claude writes the script, makes the characters, the voices, the talking
shots and the captions, and gives you a finished 1080p film, a thumbnail and the YouTube text.

The characters talk: their mouths move with the voice (lip-sync). The look is a warm, Pixar-like
3D animation style, and it works for any language that ElevenLabs speaks (Hindi, Tamil, Telugu,
Bengali, Marathi, English and more).

## What one film costs

| Film | Pictures | Talking shots | Total (first takes) |
|---|---|---|---|
| 30 s, 6 scenes, 4 talking | US$1.20 | about US$1.40 | about US$2.60 |
| 5 min, 40 scenes, 24 talking | US$6.50 | about US$9 | about US$16 |
| 20 min, 140 scenes, 90 talking | US$22 | about US$33 | about US$55 |

Plan 30% more for shots that you make again. The voice uses your ElevenLabs plan
(Starter is enough for 2 or 3 films of 20 minutes each month). Assembly, captions and music are free.
`katha.py cost <folder>` gives the exact estimate for your script before you spend anything.

## What you need

- [Claude Code](https://claude.com/claude-code)
- Python 3.9 or newer (no pip packages)
- ffmpeg (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on Linux)
- Google Chrome, Chromium, Edge or Brave (for the captions)
- A [fal](https://fal.ai) account with credit (pictures and talking shots)
- An [ElevenLabs](https://elevenlabs.io) account (voices). The free plan does not allow commercial use.

macOS is tested (Intel and Apple Silicon). Linux should work. On Windows, use WSL.

The build runs on your computer. A 20 minute film takes about 40 minutes to build.

## Install

In Claude Code:

```
/plugin marketplace add <your-github-user>/katha-studio
/plugin install katha-studio@katha-studio
```

Or copy the skill by hand:

```bash
git clone https://github.com/<your-github-user>/katha-studio
mkdir -p ~/.claude/skills && cp -R katha-studio/skills/katha-studio ~/.claude/skills/
```

Then start Claude Code in an empty folder and type:

```
/katha-studio setup
```

Claude checks your computer, tells you what to install, and asks you to save your 2 API keys
with `katha.py setup` in your own terminal. Your keys stay on your computer
(`~/.config/katha-studio/config.json`, readable only by you). Claude never sees them.

## Make a film

```
/katha-studio new the story of Sudama and Krishna, Hindi, 1 minute
```

Claude guides you through 3 approvals:

1. **The script.** A table of every scene: who speaks, the line, the picture. Plus the cost.
2. **The characters.** One reference sheet for each character. Every picture in the film uses it, so the faces stay the same.
3. **The film.** You watch it with sound and ask for changes. Only the scene you change is made again.

Everything that costs money shows its price first and runs only after you say yes.

## The steps inside

| Step | Tool | Command |
|---|---|---|
| Check the computer | ffmpeg, Chrome, keys | `katha.py doctor` |
| Script | Claude | `film.json` |
| Character sheets | Nano Banana Pro on fal | `katha.py sheets` |
| Scene pictures | Nano Banana Pro on fal, with the sheets as references | `katha.py images` |
| Voices | ElevenLabs, one voice for each character | `katha.py voice` |
| Talking shots | Kling AI Avatar on fal | `katha.py talk` |
| Moving shots (optional) | Kling 2.5 on fal | `katha.py move` |
| Captions, crossfades, music, -14 LUFS, thumbnail | ffmpeg and Chrome | `katha.py build` |
| Final check | ffprobe | `katha.py check`, `katha.py frames` |

## Before you start a channel

- YouTube can stop monetisation for "inauthentic content": many films from one template with no
  human work. Tell each story in a different way, and add your own intro or moral in your own voice.
- In YouTube Studio, answer the "altered or synthetic content" question honestly.
- The old stories are free to tell. The scripts, characters and thumbnails of other channels are not. Do not copy them.
- Treat the stories with respect. Many viewers watch them as devotion.

## Licence

MIT. See `LICENSE`.
