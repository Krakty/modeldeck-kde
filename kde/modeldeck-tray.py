#!/usr/bin/env python3
"""modeldeck-tray.py -- a KDE system tray icon showing how much Claude Code and Codex capacity is left.

The icon shows the lowest "% left" across every account and limit window (gold when low, red when
critical). Hover for one line per window with its reset time; the menu shows the same lines.

It only runs the command in ~/.config/modeldeck-kde/config.json and reads the JSON that prints:
  {"command": "node /path/to/kde/modeldeck-status.mjs", "interval_seconds": 300, "warn": 25, "critical": 10}
To show another machine's accounts, make the command an ssh call to that machine.
"""
import json
import os
import shlex
import sys
from datetime import datetime, timezone

from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.expanduser('~/.config/modeldeck-kde/config.json')
DEFAULTS = {'command': 'node ' + shlex.quote(os.path.join(HERE, 'modeldeck-status.mjs')),
            'interval_seconds': 300, 'warn': 25, 'critical': 10, 'timeout_seconds': 60}
NEUTRAL, GOLD, RED, GREY = '#3daee9', '#f5c211', '#e01b24', '#7f8c8d'


def load_config():
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, encoding='utf-8') as handle:
            config.update({k: v for k, v in json.load(handle).items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return config


def reset_text(iso, now=None):
    """'resets Wed 10:00 (in 6h 4m)' in local time, or '' when the window has no reset."""
    if not iso:
        return ''
    try:
        when = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
    except ValueError:
        return ''
    now = now or datetime.now(timezone.utc)
    minutes = int((when - now).total_seconds() // 60)
    if minutes <= 0:
        return 'resetting now'
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    span = f'{days}d {hours}h' if days else (f'{hours}h {mins}m' if hours else f'{mins}m')
    return f"resets {when.astimezone().strftime('%a %H:%M')} (in {span})"


def summarize(status, now=None):
    """-> (lowest percent left or None, list of text lines)."""
    lowest, lines = None, []
    for account in status.get('accounts', []):
        name = account.get('provider', '?')
        if account.get('plan'):
            name += f" ({account['plan']})"
        if account.get('error'):
            lines.append(f"{name}: {account['error']}")
        for window in account.get('windows', []):
            left = window.get('leftPercent')
            if not isinstance(left, (int, float)):
                continue
            lowest = left if lowest is None else min(lowest, left)
            reset = reset_text(window.get('resetsAt'), now)
            lines.append(f"{name} {window.get('label', 'limit')}: {int(left)}% left" + (f", {reset}" if reset else ''))
        if not account.get('error') and not account.get('windows'):
            lines.append(f'{name}: no limit windows reported')
    return lowest, lines


def colour_for(lowest, config):
    if lowest is None:
        return GREY
    if lowest <= config['critical']:
        return RED
    if lowest <= config['warn']:
        return GOLD
    return NEUTRAL


def make_icon(text, colour):
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(colour))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 14, 14)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(38 if len(text) <= 2 else 28)
    painter.setFont(font)
    painter.setPen(QColor('#1b1e20' if colour == GOLD else '#ffffff'))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


class Tray:
    def __init__(self, app):
        self.config = load_config()
        self.process = None
        self.last_ok = None
        self.tray = QSystemTrayIcon(make_icon('…', GREY))
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.refresh() if reason == QSystemTrayIcon.Trigger else None)
        self.show(None, ['Reading usage…'])
        self.tray.show()
        self.kill_timer = QTimer(singleShot=True)
        self.kill_timer.timeout.connect(self.timed_out)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(max(60, int(self.config['interval_seconds'])) * 1000)
        self.app = app
        QTimer.singleShot(0, self.refresh)

    def show(self, lowest, lines, stale=False):
        colour = GREY if stale else colour_for(lowest, self.config)
        self.tray.setIcon(make_icon('?' if lowest is None else str(int(lowest)), colour))
        self.tray.setToolTip('ModelDeck\n' + '\n'.join(lines))
        self.menu.clear()
        for line in lines:
            self.menu.addAction(line).setEnabled(False)
        self.menu.addSeparator()
        self.menu.addAction('Refresh now', self.refresh)
        self.menu.addAction('Quit', QApplication.quit)

    def refresh(self):
        if self.process is not None:
            return
        self.config = load_config()
        self.process = QProcess()
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(lambda _error: self.failed('could not start the status command'))
        self.process.startCommand(self.config['command'])
        self.kill_timer.start(int(self.config['timeout_seconds']) * 1000)

    def timed_out(self):
        if self.process is not None:
            self.process.kill()

    def failed(self, why):
        self.kill_timer.stop()
        self.process = None
        lowest, lines = self.last_ok or (None, [])
        note = f'Not updated: {why}'
        self.show(lowest, [note] + lines, stale=True)

    def finished(self, code, _status):
        if self.process is None:
            return
        output = bytes(self.process.readAllStandardOutput()).decode('utf-8', 'replace')
        try:
            status = json.loads(output.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return self.failed(f'status command gave no usable answer (exit {code})')
        self.kill_timer.stop()
        self.process = None
        lowest, lines = summarize(status)
        lines.append('Updated ' + datetime.now().strftime('%H:%M') + ' from ' + str(status.get('host', '?')))
        self.last_ok = (lowest, lines)
        self.show(lowest, lines)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('modeldeck-tray')
    app.setQuitOnLastWindowClosed(False)
    tray = Tray(app)  # noqa: F841 (keeps the tray alive)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
