"""Offline tests for the tray's text and colour decisions: python3 -m unittest discover kde/tests"""
import importlib.util
import os
import unittest
from datetime import datetime, timezone

spec = importlib.util.spec_from_file_location('tray', os.path.join(os.path.dirname(__file__), '..', 'modeldeck-tray.py'))
tray = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tray)
NOW = datetime(2026, 11, 25, 4, 0, tzinfo=timezone.utc)
STATUS = {'host': 'h', 'accounts': [
    {'provider': 'Claude Code', 'plan': None, 'error': None, 'windows': [
        {'label': 'weekly', 'leftPercent': 23, 'resetsAt': '2026-11-25T10:00:00.606Z'},
        {'label': 'Fable weekly', 'leftPercent': 69, 'resetsAt': None}]},
    {'provider': 'Codex', 'plan': 'pro', 'error': None, 'windows': [
        {'label': 'weekly', 'leftPercent': 12, 'resetsAt': '2026-11-28T23:17:34.000Z'}]},
    {'provider': 'Other', 'plan': None, 'error': 'sign in again', 'windows': []}]}


class TrayText(unittest.TestCase):
    def test_lowest_is_the_worst_window(self):
        lowest, lines = tray.summarize(STATUS, NOW)
        self.assertEqual(lowest, 12)
        self.assertEqual(len(lines), 4)
        self.assertIn('Codex (pro) weekly: 12% left', lines[2])
        self.assertIn('(in 3d 19h)', lines[2])
        self.assertEqual(lines[1], 'Claude Code Fable weekly: 69% left')
        self.assertEqual(lines[3], 'Other: sign in again')

    def test_reset_text(self):
        self.assertIn('(in 6h 0m)', tray.reset_text('2026-11-25T10:00:00.606Z', NOW))
        self.assertEqual(tray.reset_text('2026-11-25T03:00:00Z', NOW), 'resetting now')
        self.assertEqual(tray.reset_text(None, NOW), '')
        self.assertEqual(tray.reset_text('garbage', NOW), '')

    def test_colours(self):
        config = {'warn': 25, 'critical': 10}
        self.assertEqual(tray.colour_for(None, config), tray.GREY)
        self.assertEqual(tray.colour_for(60, config), tray.NEUTRAL)
        self.assertEqual(tray.colour_for(25, config), tray.GOLD)
        self.assertEqual(tray.colour_for(10, config), tray.RED)

    def test_hover_bars(self):
        self.assertEqual(tray.text_bar(0), '\u2591' * 10)
        self.assertEqual(tray.text_bar(100), '\u2588' * 10)
        self.assertEqual(tray.text_bar(23), '\u2588' * 2 + '\u2591' * 8)
        line = tray.hover_line(tray.rows(STATUS, NOW)[2])
        self.assertTrue(line.startswith('\u2588' + '\u2591' * 9 + ' 12%  Codex (pro) weekly'))
        self.assertEqual(tray.hover_line(tray.rows(STATUS, NOW)[3]), 'Other: sign in again')

    def test_no_windows_is_said(self):
        _, lines = tray.summarize({'accounts': [{'provider': 'Codex', 'windows': [], 'error': None}]}, NOW)
        self.assertEqual(lines, ['Codex: no limit windows reported'])


if __name__ == '__main__':
    unittest.main()
