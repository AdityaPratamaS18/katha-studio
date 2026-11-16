# Contributing

Thank you for helping. Small, tested changes are the easiest to accept.

## Rules

1. Keep the tool on the Python standard library. No pip dependencies.
2. A step that costs money must print its price and stop without `--yes`.
3. Never print, log or commit an API key.
4. Run the offline test before a pull request: `bash tests/smoke_test.sh` (needs ffmpeg; Chrome tests the captions).
5. When a change touches a paid step, test it with a dry run first and write the real cost in the pull request.
6. Do not use em-dashes or en-dashes in docs or code. CI checks this.
7. Update `CHANGELOG.md` and, for a release, the `version` in `.claude-plugin/plugin.json` and `__version__` in `katha.py`.

## Faults and ideas

Open an issue with the output of `katha.py doctor`. Remove every key from what you paste.
