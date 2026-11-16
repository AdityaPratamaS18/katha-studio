# film.json: every field

One film is one folder. The tool writes these subfolders: `img/`, `audio/`, `clips/`, `build/`, `out/`, `.cache/`.

| Field | Required | Meaning |
|---|---|---|
| `title` | yes | Shown as the title card for the first 3.5 s and on the thumbnail. |
| `slug` | no | File name of the film (`out/<slug>.mp4`). Default: the folder name. |
| `language` | no | Language code of the lines (`hi`, `ta`, `te`, `bn`, `mr`, `en`...). Used to search voices. |
| `style` | yes | One paragraph at the start of every picture prompt. Keep it the same for the whole channel. |
| `characters` | yes | `{id: {"look": "...", "refs": ["optional/photo.png"]}}`. `look` is the full description. Write age, body, face, hair, skin, costume, jewellery and what the character never wears. |
| `voices` | yes | `{speaker: {"voice_id": "...", "model": "eleven_v3"?, "speed": 0.95?, "settings": {...}?}}`. One entry for the narrator and one for each character that speaks. |
| `scenes` | yes | The list of scenes, in order. See below. |
| `thumbnail` | no | `{"scene": 4, "text": "..."}`. The picture of that scene with the text on it. |
| `music` | no | A file in the film folder (for example `music.mp3` from the YouTube Audio Library). `null` gives a soft free drone. `false` gives no music. |
| `music_volume` | no | Default 0.12. |
| `captions` | no | `true` (default) burns the lines into the picture. |
| `title_card` | no | `false` removes the title at the start. |
| `caption_look` | no | `font`, `size`, `color`, `title_size`, `title_color`, `title_top`. |
| `settings` | no | Overrides for this film: `image_model` (`nano-banana-pro` or `nano-banana-2`), `sheet_model`, `image_resolution` (`1K`, `2K`, `4K`), `avatar_model` (`kling-avatar` or `kling-avatar-pro`), `move_model`, `tts_model` (`eleven_multilingual_v2` or `eleven_v3`), `voice_settings`. |

## A scene

```json
{"id": 2, "speaker": "sudama", "kind": "talk",
 "text": "मैं कृष्ण का बचपन का मित्र हूँ। क्या वो मुझे पहचानेंगे?",
 "image": "Front-facing medium close-up portrait of {sudama} looking at the camera, ... mouth closed."}
```

| Field | Meaning |
|---|---|
| `id` | A unique number. Files use it: `img/s002.png`, `audio/p002.mp3`, `clips/s002.mp4`. |
| `speaker` | A key of `voices`. |
| `kind` | `still`: a slow zoom on the picture (free). `talk`: the speaker's mouth moves with the line (Kling AI Avatar, paid). `move`: a 5 s moving shot (Kling image-to-video, paid). |
| `text` | The spoken line. With `eleven_v3` you can add direction tags such as `[whispers]` or `[crying]`; they are not shown in the captions. |
| `image` | The picture prompt. `{character_id}` is replaced by that character's `look`, and the character sheet is sent as a reference. |
| `image_from` | Use the picture of another scene id (no new picture is made). |
| `refs` | More reference images (paths in the film folder), for example a place you want to keep the same. |
| `motion` | For `move` scenes: what moves ("the lamp flame flickers, slow push in"). |
| `talk_prompt` | Replaces the default talk prompt ("."). Never put the spoken line in it, and do not name text or subtitles in it. |

## Prices the tool uses (fal, November 2026)

| Model | Price |
|---|---|
| Nano Banana Pro (sheets, pictures) | US$0.15 an image |
| Nano Banana 2 (cheaper pictures) | US$0.08 an image |
| Kling AI Avatar v2 Standard (talk) | US$0.0562 a second |
| Kling AI Avatar v2 Pro (talk) | US$0.115 a second |
| Kling 2.5 Turbo Pro (move) | US$0.07 a second |

Check https://fal.ai/pricing before a big film. Prices change.
