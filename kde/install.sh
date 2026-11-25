#!/bin/bash
# install.sh -- install the ModelDeck KDE tray icon for the current user and start it.
#
#   kde/install.sh                      this machine's own Claude Code / Codex logins
#   kde/install.sh --from <host> <dir>  show <host>'s logins: status is read over ssh from the checkout at <dir> there
#
# Installs ~/.local/share/modeldeck-kde/modeldeck-tray.py, ~/.config/modeldeck-kde/config.json (kept if present,
# unless --from is given) and the user service modeldeck-tray.service. Needs python3 with PySide6.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
APP="$HOME/.local/share/modeldeck-kde"
CONF="$HOME/.config/modeldeck-kde"
UNIT="$HOME/.config/systemd/user/modeldeck-tray.service"
mkdir -p "$APP" "$CONF" "$(dirname "$UNIT")"
install -m 0755 "$HERE/modeldeck-tray.py" "$APP/modeldeck-tray.py"
if [ "${1:-}" = "--from" ]; then
  host=${2:?host}; dir=${3:?checkout directory on that host}
  cmd="ssh -o BatchMode=yes -o ConnectTimeout=8 $host node $dir/kde/modeldeck-status.mjs"
  python3 - "$CONF/config.json" "$cmd" <<'PY'
import json, sys
json.dump({'command': sys.argv[2], 'interval_seconds': 300, 'warn': 25, 'critical': 10}, open(sys.argv[1], 'w'), indent=1)
PY
elif [ ! -f "$CONF/config.json" ]; then
  python3 - "$CONF/config.json" "node $HERE/modeldeck-status.mjs" <<'PY'
import json, sys
json.dump({'command': sys.argv[2], 'interval_seconds': 300, 'warn': 25, 'critical': 10}, open(sys.argv[1], 'w'), indent=1)
PY
fi
cat > "$UNIT" <<UNITEOF
[Unit]
Description=ModelDeck KDE tray icon (Claude Code and Codex capacity left)
PartOf=graphical-session.target
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 $APP/modeldeck-tray.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=graphical-session.target
UNITEOF
systemctl --user daemon-reload
systemctl --user enable modeldeck-tray.service >/dev/null 2>&1 || true
systemctl --user restart modeldeck-tray.service
sleep 3
systemctl --user is-active modeldeck-tray.service
