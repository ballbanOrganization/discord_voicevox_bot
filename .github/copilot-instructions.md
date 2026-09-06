# Copilot instructions

## Project shape

This repository is a Python 3.10 Discord voice-reading bot:

- `main.py` is a thin executable entry point. It creates the bot and calls
  `client.run(...)` only inside `main()`.
- `app/bot.py` owns the Discord client lifecycle and wires the application
  services together.
- `app/commands.py` registers the existing slash commands and
  `app/events.py` handles message and voice-state events.
- `app/runtime.py` keeps independent text-channel and playback state for each
  guild. `app/playback.py` gives each guild one FIFO queue and worker.
- `app/text.py` contains pure message normalization and attachment
  announcements.
- `app/user_repository.py` persists `data/user_data.json` with the unchanged
  `user_id`, `sound`, `entry_audio`, and `exit_audio` schema.
- `app/voicevox.py` is an asynchronous VOICEVOX adapter. Speaker discovery is
  performed during bot startup, not during module import.
- `app/speech.py` combines the user repository, VOICEVOX adapter, and
  `app/audio_cache.py`. Cache files retain the layout
  `audio/<style name><speaker name>/<md5>.wav`.

## Build, run, and test

Run commands from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:discord_token = "<Discord bot token>"
python main.py
```

The process expects VOICEVOX at `http://127.0.0.1:50021/` and requires an
`ffmpeg` executable for Discord playback. `VOICEVOX_URL` can override the
engine URL. The token is read from the lowercase `discord_token` environment
variable; this repository does not load `.env`.

Run focused tests and the existing lint checks with:

```powershell
pytest -q
flake8 . --exclude=.venv --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --exclude=.venv --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics
```

CI runs on the existing Windows self-hosted runner, installs
`requirements.txt`, runs the two flake8 passes and pytest, then restarts the
`discord_voicevox_bot` NSSM service.

## Behavior and compatibility

- Do not start Discord, contact VOICEVOX, or require a live service while
  importing application modules.
- Keep the existing command names and user-facing Japanese responses.
- Ignore message prefixes `m!` and `/`; replace URLs and IP-like text; replace
  runs of four or more `w` characters with `わらわら`; cap normalized text at
  300 characters; process attachments as category announcements.
- Do not mutate Discord `Message` objects during normalization.
- Use `entry_audio` for joins and `exit_audio` for leaves.
- Preserve the JSON schema and the cache MD5, which is computed from the exact
  normalized text.
- Do not commit generated WAV files, credentials, `.env`, or local editor
  configuration.
