# ModelDeck for KDE

A small system tray icon for KDE Plasma (or any desktop with a StatusNotifier tray) that shows how
much Claude Code and Codex capacity is left. It is a Linux front end built on this fork's upstream
usage readers; the macOS app and the daemon are not used.

- The icon shows the lowest "% left" across every account and limit window: blue when healthy,
  gold at 25% or less, red at 10% or less, grey when the last read failed.
- Hover for one text bar per limit window, with the percent left and the reset time.
- Left-click opens a panel with a large bar per window and the percent left written inside it
  (Esc or another click closes it).
- Right-click to refresh now or quit. It otherwise refreshes every five minutes.

## Parts

| File | What it does |
| --- | --- |
| `modeldeck-status.mjs` | Prints one JSON snapshot for the logins on the machine it runs on. Read-only: it calls `src/adapters/claude-usage-probe.mjs` and `src/adapters/codex.mjs` and exits. Nothing is written. Runs on Node 20 or later. |
| `modeldeck-tray.py` | The tray icon (Python, PySide6). It runs the configured command and shows what it prints. |
| `install.sh` | Installs the tray as a systemd user service. |

## Install

```
kde/install.sh                       # show this machine's own logins
kde/install.sh --from <host> <dir>   # show <host>'s logins, read over ssh from this checkout at <dir> on <host>
```

The second form needs key-based ssh to `<host>`; only the tray file is installed locally.

Settings are in `~/.config/modeldeck-kde/config.json`: `command`, `interval_seconds`, `warn`,
`critical`. The tray rereads the file on every refresh.

## What it reads

- Claude Code: the OAuth token in `~/.claude/.credentials.json`, used for one request to the
  provider's usage endpoint (the same request upstream ModelDeck makes).
- Codex: `codex app-server --stdio`, method `account/rateLimits/read`, with `CODEX_HOME=~/.codex`.

No credential is copied, stored, printed or sent anywhere other than its own provider.

## Tests

```
python3 -m unittest discover kde/tests
```

## Licence

Same as upstream: PolyForm Noncommercial 1.0.0 (see `LICENSE.md`). Not for commercial use.
