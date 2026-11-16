---
name: katha-studio
description: Make animated mythology, devotional and folk story films for YouTube (16:9, 1080p) with talking characters. Guides first-time setup (ffmpeg, Chrome, fal and ElevenLabs keys), then writes the story script, makes consistent characters, voices, lip-synced talking shots, captions, music and the final film plus thumbnail and YouTube text. Use when the user wants to start or run a story or katha YouTube channel, make an animated story video, "make a video like <a mythology channel>", set up katha-studio, or continue a film made with it.
argument-hint: "[setup | new <story> | continue <folder>]"
---

# katha-studio

You make a finished animated story film with the user. One film is one folder with one `film.json`.
The tool is `python3 "${CLAUDE_SKILL_DIR}/scripts/katha.py"` (call it KATHA below). It needs no pip packages.

Paid steps (sheets, images, talk, move) print the price and stop. They spend money only with `--yes`.
Run `--yes` only after the user agreed to that price in chat. The voice step uses the user's ElevenLabs quota.

Read these when you need them:
- `references/film-format.md`: every field of film.json.
- `references/story-craft.md`: how to write a katha script that holds viewers, and the shot rules.
- `references/troubleshooting.md`: known faults and fixes.

## 0. First run: guided setup

Do this when the user is new, or when any later step fails with a missing tool or key.

1. Run `KATHA doctor`. It prints OK or MISS for each item, with the fix.
2. For each MISS, give the user the exact fix command for their system, one at a time. Wait until they say it is done.
3. Keys: tell the user to make a fal key (https://fal.ai/dashboard/keys) and an ElevenLabs key (https://elevenlabs.io/app/settings/api-keys), and to add credit to fal (US$10 is enough for a first short film).
4. Tell the user to run `python3 "${CLAUDE_SKILL_DIR}/scripts/katha.py" setup` in their own terminal. Never ask them to paste a key into the chat, and never type a key yourself.
5. Run `KATHA doctor` again. Continue only on READY.

NOTE: The ElevenLabs free plan does not allow commercial use. A monetised channel needs Starter or above.

## 1. The story (gate 1: the user approves the script)

1. Ask, one question at a time: the story, the language, the length (start with 1 to 3 minutes for a first film), and the channel name.
2. Run `KATHA new <folder> --title "<title>" --language <code>`.
3. Write `film.json`: style, characters with a full `look` each, voices (narrator plus one for each speaking character), and the scenes. Follow `references/story-craft.md`.
4. Run `KATHA validate <folder>` and fix every FAIL.
5. Show the user the script as a table (id, speaker, kind, line, picture in a few words) and `KATHA cost <folder>`. Change it until they approve it.

## 2. Voices

1. Run `KATHA voices --language <code>` (add `--gender male`, `--accent standard` or `--search "old"` to narrow it). Give the user 3 choices for each role with the preview links.
2. When they pick, put the voice_id into `film.json` `voices`. A library voice works without adding it to the account.
3. Only if the voice step then fails with "voice not found", run `KATHA voices --add <voice_id> --owner <owner> --name "<role>"`. This uses one of the account's voice slots.
4. Run `KATHA voice <folder> <2 or 3 ids>` and ask the user to listen to `audio/raw<id>.mp3` before you voice the full film.

## 3. Characters (gate 2: the user approves each sheet)

1. Run `KATHA sheets <folder>`, tell the user the price, then run it with `--yes` after they agree.
2. Look at every `img/char_<id>.png` yourself with the Read tool. Check age, face, costume, colours and the number of people.
3. Show the sheets to the user. If a sheet is wrong, change that character's `look` and run `KATHA sheets <folder> <id> --yes`.

The sheets are the identity of the film. Never make scene pictures before the user approves the sheets.

## 4. Pictures, voice, motion

1. `KATHA images <folder>` (price), then with `--yes`. It makes only the missing pictures.
2. Look at `img/contact.jpg`, then open each picture that looks wrong. Check: the right characters, no extra people, no text, no wrong crown or costume, and for every talk scene a clear front-facing face with the mouth closed.
3. Remake a bad picture: improve its `image` prompt, then `KATHA images <folder> <id> --yes --redo`.
4. `KATHA voice <folder>`. It caches each line, so a second run is free. Remake one line after a text change with `KATHA voice <folder> <id>`.
5. `KATHA talk <folder>` (price), then with `--yes`. Only after the pictures and the voice of those scenes are final: a new picture or a new voice needs a new clip.
6. Look at every `clips/s<id>_check.jpg` yourself. Remake a clip that shows letters, fake subtitles or a face that changed: `KATHA talk <folder> <id> --yes --redo`.
7. If the film has `move` scenes: `KATHA move <folder>` (price), then with `--yes`.

## 5. Build and check (gate 3: the user watches the film)

1. `KATHA build <folder>`. Output: `out/<slug>.mp4` and `out/thumbnail.jpg`.
2. `KATHA check <folder>` must print PASS.
3. `KATHA frames <folder>`, then look at `out/frames.jpg` and the thumbnail yourself.
4. Write `out/youtube.md`: 3 title options (under 70 characters, the story name plus an emotional hook), a description (2 lines of summary, the moral, the source text of the story, chapters with timestamps from the scene lengths), 10 tags, and the line "Made with AI tools" for the altered-content question in YouTube Studio.
5. Ask the user to watch the full film with sound. Make each fix they ask for at its own step, then build again.

## Rules that came from real faults

- Every talk scene needs a front-facing close-up, head and shoulders, mouth closed. A side view or a bowed head gives poor lip-sync.
- Leave the talk prompt as the default ".". A prompt with the spoken line, or with words such as "no subtitles", made Kling draw fake subtitle text in tests. Kling has no negative prompt.
- Write "an adult man about 30 years old (not a child)" for adult gods. Without it, the model often draws Krishna and others as children.
- Write what a character must NOT wear when a scene risks it ("no crown, no jewellery" for a poor Brahmin), because the model copies the costume of the other character in the frame.
- Keep each line under about 250 characters. Split a long speech into 2 scenes with 2 pictures.
- Do not copy the script, characters or thumbnails of another channel. The old stories are free to tell; another channel's telling is not.
- YouTube can stop monetisation for "inauthentic content" (mass-made films with no human work). Tell the user to vary the stories and structure, and to add their own intro or moral in their own voice.
