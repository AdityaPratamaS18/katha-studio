# Security

## Report a problem

Report security problems in private: https://github.com/AdityaPratamaS18/katha-studio/security/advisories/new

Do not open a public issue for a security problem. The maintainer aims to answer within 7 days.

## What katha-studio does with your keys

| Item | Behaviour |
|---|---|
| Where keys are kept | `~/.config/katha-studio/config.json`, mode 600 in a folder with mode 700. Or the environment variables `FAL_KEY` and `ELEVENLABS_API_KEY`. |
| Who types the keys | You, in your own terminal, with `katha.py setup`. The input is hidden. The skill tells Claude never to ask for a key in the chat. |
| Where keys are sent | Only to the service they belong to: the fal key to the fal API (`queue.fal.run`, `rest.alpha.fal.ai`, `api.fal.ai`); the ElevenLabs key to `api.elevenlabs.io`. |
| What is printed | Keys are never printed or written to logs. `doctor` shows only OK or MISS. |
| Telemetry | None. The tool sends nothing to the author. |

## What leaves your computer

| Data | Sent to | Note |
|---|---|---|
| Picture prompts, character sheets, scene pictures | fal | Reference files are uploaded to fal storage. fal storage links are long random URLs, but anyone with a link can open it. |
| Voice lines (the text of your script) | ElevenLabs | |
| Talk pictures and voice files | fal | For the lip-sync step. |

Do not put private photos of real people into `refs` unless you have their permission.

## Safe use

1. Use a separate fal key for this tool, and set a spending limit in the fal dashboard.
2. Never commit `config.json`, a `.env` file or a film folder that holds a key. The `.gitignore` of this repo excludes film folders.
3. If a key leaks, revoke it at once in the fal or ElevenLabs dashboard, then run `katha.py setup` with a new key.
4. Every paid step prints its price and stops. It spends money only with `--yes`.

## Supply chain

- The tool uses only the Python standard library, ffmpeg and a Chromium browser. There are no pip packages to install.
- The GitHub Actions in this repo are pinned to commit SHAs and run with read-only permissions.
