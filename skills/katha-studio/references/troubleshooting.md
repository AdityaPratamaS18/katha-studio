# Troubleshooting

| Fault | Probable cause | Corrective action |
|---|---|---|
| `HTTP 403 ... Exhausted balance` from fal | The fal account has no credit | Add credit at https://fal.ai/dashboard/billing, then run the same command again. Finished files are kept. |
| `HTTP 401` | The key is wrong | Run `katha.py setup` again in a terminal. |
| A talk clip shows letters or subtitles | Kling adds them at random, more often when the prompt has the line or names text | Keep `talk_prompt` empty (default "."), make sure the picture has no text, then `talk <folder> <id> --yes --redo`. |
| The mouth does not follow the voice | Side view, small face, or a hand in front of the mouth | Make a new front-facing close-up picture (`images <id> --yes --redo`), then a new talk clip. |
| A face changes between scenes | The sheet is weak, or too many characters in one picture | Improve the `look`, remake the sheet, then remake the pictures of that character. |
| `Chrome did not write ...png` | Chrome is not installed, or another headless Chrome holds the screen | Install Chrome or set `CHROME_PATH`; close test windows; run build again. |
| Captions show boxes instead of letters | No font for the script on this computer | Install Noto Sans for the script (for example Noto Sans Devanagari) or set `caption_look.font`. |
| ffmpeg says "No such filter" | A small ffmpeg build | Install a full build (`brew install ffmpeg`, `sudo apt install ffmpeg`). |
| The film is too quiet or too loud | The music file is loud | Lower `music_volume`. The build sets the whole film to -14 LUFS. |
| The voice reads a word wrongly | The model does not know the word | Write the word as it sounds, or add vowel marks, then `voice <folder> <id>`. |
