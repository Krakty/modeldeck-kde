#!/usr/bin/env python3
"""modeldeck-tray.py -- a KDE system tray icon showing how much Claude Code and Codex capacity is left.

The icon shows the lowest "% left" across every account and limit window (gold when low, red when
critical). Hover for one text bar per limit window with its reset time. Left-click opens a panel with a
large bar per window; the right-click menu refreshes or quits.

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
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QProgressBar, QSystemTrayIcon, QVBoxLayout, QWidget

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


def rows(status, now=None):
    """One row per limit window (left = percent left) or per problem (left = None)."""
    out = []
    for account in status.get('accounts', []):
        name = account.get('provider', '?')
        if account.get('plan'):
            name += f" ({account['plan']})"
        if account.get('error'):
            out.append({'name': name, 'left': None, 'note': account['error']})
        for window in account.get('windows', []):
            left = window.get('leftPercent')
            if not isinstance(left, (int, float)):
                continue
            out.append({'name': f"{name} {window.get('label', 'limit')}", 'left': int(left),
                        'note': reset_text(window.get('resetsAt'), now)})
        if not account.get('error') and not account.get('windows'):
            out.append({'name': name, 'left': None, 'note': 'no limit windows reported'})
    return out


def text_bar(left, cells=10):
    """'███░░░░░░░' with the filled part showing what is left."""
    filled = max(0, min(cells, round(left * cells / 100)))
    return '\u2588' * filled + '\u2591' * (cells - filled)


def hover_line(row):
    if row['left'] is None:
        return f"{row['name']}: {row['note']}"
    return f"{text_bar(row['left'])} {row['left']}%  {row['name']}" + (f" \u00b7 {row['note']}" if row['note'] else '')


def summarize(status, now=None):
    """-> (lowest percent left or None, list of plain text lines)."""
    lowest, lines = None, []
    for row in rows(status, now):
        if row['left'] is None:
            lines.append(f"{row['name']}: {row['note']}")
            continue
        lowest = row['left'] if lowest is None else min(lowest, row['left'])
        lines.append(f"{row['name']}: {row['left']}% left" + (f", {row['note']}" if row['note'] else ''))
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
    painter.drawRoundedRect(0, 0, 64, 64, 12, 12)
    font = QFont()
    font.setBold(True)
    font.setPixelSize(48 if len(text) <= 2 else 34)
    painter.setFont(font)
    painter.setPen(QColor('#1b1e20' if colour == GOLD else '#ffffff'))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
    painter.end()
    return QIcon(pixmap)


class Panel(QWidget):
    """The click panel: one large bar per limit window, percent left written inside it."""

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('ModelDeck')
        self.setMinimumWidth(460)
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(18, 16, 18, 16)
        self.layout_.setSpacing(6)

    def fill(self, row_list, footer, config):
        while self.layout_.count():
            item = self.layout_.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for row in row_list:
            title = QLabel(row['name'] + (f"  \u00b7  {row['note']}" if row['left'] is not None and row['note'] else ''))
            title.setStyleSheet('font-size: 13pt; font-weight: 600; margin-top: 8px;')
            self.layout_.addWidget(title)
            if row['left'] is None:
                problem = QLabel(row['note'])
                problem.setWordWrap(True)
                problem.setStyleSheet(f'font-size: 12pt; color: {RED};')
                self.layout_.addWidget(problem)
                continue
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(row['left'])
            bar.setFormat(f"{row['left']}% left")
            bar.setAlignment(Qt.AlignCenter)
            bar.setFixedHeight(34)
            colour = colour_for(row['left'], config)
            bar.setStyleSheet(
                'QProgressBar { border: 1px solid palette(mid); border-radius: 7px; font-size: 14pt; font-weight: 700; }'
                f'QProgressBar::chunk {{ background: {colour}; border-radius: 6px; }}')
            self.layout_.addWidget(bar)
        foot = QLabel(footer)
        foot.setStyleSheet('font-size: 10pt; color: palette(placeholder-text); margin-top: 10px;')
        self.layout_.addWidget(foot)
        self.adjustSize()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)


class Tray:
    def __init__(self, app):
        self.config = load_config()
        self.process = None
        self.last_ok = None
        self.tray = QSystemTrayIcon(make_icon('…', GREY))
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.panel = Panel()
        self.tray.activated.connect(lambda reason: self.toggle_panel() if reason == QSystemTrayIcon.Trigger else None)
        self.show(None, [{'name': 'ModelDeck', 'left': None, 'note': 'reading usage…'}], '')
        self.tray.show()
        self.kill_timer = QTimer(singleShot=True)
        self.kill_timer.timeout.connect(self.timed_out)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(max(60, int(self.config['interval_seconds'])) * 1000)
        self.app = app
        QTimer.singleShot(0, self.refresh)

    def show(self, lowest, row_list, footer, stale=False):
        colour = GREY if stale else colour_for(lowest, self.config)
        self.tray.setIcon(make_icon('?' if lowest is None else str(int(lowest)), colour))
        self.tray.setToolTip('\n'.join(['ModelDeck: percent left'] + [hover_line(r) for r in row_list] + ([footer] if footer else [])))
        self.panel.fill(row_list, footer, self.config)
        self.menu.clear()
        self.menu.addAction('Show bars', self.toggle_panel)
        self.menu.addAction('Refresh now', self.refresh)
        self.menu.addSeparator()
        self.menu.addAction('Quit', QApplication.quit)

    def toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.panel.show()
            self.panel.raise_()
            self.panel.activateWindow()

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
        lowest, row_list, footer = self.last_ok or (None, [], '')
        self.show(lowest, [{'name': 'Not updated', 'left': None, 'note': why}] + row_list, footer, stale=True)

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
        row_list = rows(status)
        lowest = min((r['left'] for r in row_list if r['left'] is not None), default=None)
        footer = 'Updated ' + datetime.now().strftime('%H:%M') + ' from ' + str(status.get('host', '?'))
        self.last_ok = (lowest, row_list, footer)
        self.show(lowest, row_list, footer)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('modeldeck-tray')
    app.setQuitOnLastWindowClosed(False)
    tray = Tray(app)  # noqa: F841 (keeps the tray alive)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
