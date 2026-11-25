#!/usr/bin/env node
// modeldeck-status.mjs -- print one JSON snapshot of how much Claude Code and Codex capacity is left
// for the logins on THIS machine. Read-only: it calls upstream's two usage readers and exits.
// No daemon, no data directory, nothing written. Used by kde/modeldeck-tray.py (run locally or over ssh).
//
//   node kde/modeldeck-status.mjs            # ~/.claude and ~/.codex
//   CLAUDE_CONFIG_DIR=... CODEX_HOME=... node kde/modeldeck-status.mjs
import os from 'node:os';
import path from 'node:path';
import { main as probeClaude } from '../src/adapters/claude-usage-probe.mjs';
import { parseClaudeUsage, readClaudePlanDisplayName, resolveClaudeCodeVersion } from '../src/adapters/claude.mjs';
import { fetchCodexRateLimits, readCodexPlan } from '../src/adapters/codex.mjs';

const home = os.homedir();
const claudeHome = process.env.CLAUDE_CONFIG_DIR || path.join(home, '.claude');
const codexHome = process.env.CODEX_HOME || path.join(home, '.codex');

function windows(snapshots) {
  return (snapshots || [])
    .filter((s) => s && s.scope !== 'spend' && Number.isFinite(Number(s.usedPercent)))
    .map((s) => {
      const used = Math.max(0, Math.min(100, Number(s.usedPercent)));
      return { label: String(s.scope || 'limit'), usedPercent: used, leftPercent: Math.round(100 - used), resetsAt: s.resetsAt || null };
    });
}
const short = (error) => String(error?.message || error).replace(/\s+/g, ' ').slice(0, 160);

async function claude() {
  const account = { provider: 'Claude Code', plan: null, windows: [], error: null };
  try {
    let version = null;
    try { version = await resolveClaudeCodeVersion(); } catch { /* fallback version is fine */ }
    let buffer = '';
    await probeClaude({
      env: { ...process.env, CLAUDE_CONFIG_DIR: claudeHome, ...(version ? { MODELDECK_CLAUDE_UA_VERSION: version } : {}) },
      stdout: { write: (chunk) => { buffer += chunk; return true; } },
    });
    const parsed = parseClaudeUsage(JSON.parse(buffer));
    account.windows = windows(Array.isArray(parsed) ? parsed : parsed?.snapshots || parsed?.windows);
  } catch (error) { account.error = short(error); }
  try {
    const plan = await readClaudePlanDisplayName({ claudeConfigDir: claudeHome });
    account.plan = typeof plan === 'string' ? plan : plan?.displayName || plan?.planDisplayName || null;
  } catch { /* display only */ }
  return account;
}

async function codex() {
  const account = { provider: 'Codex', plan: null, windows: [], error: null };
  try { account.windows = windows(await fetchCodexRateLimits({ codexHome })); } catch (error) { account.error = short(error); }
  try { account.plan = (await readCodexPlan({ codexHome })).planType; } catch { /* display only */ }
  return account;
}

const accounts = await Promise.all([claude(), codex()]);
process.stdout.write(`${JSON.stringify({ schema: 1, host: os.hostname(), generatedAt: new Date().toISOString(), accounts })}\n`);
