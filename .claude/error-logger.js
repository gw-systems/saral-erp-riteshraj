#!/usr/bin/env node
// Core error logger — used by all hooks and middleware
// Usage: node error-logger.js <json-payload>

const path = require('path');
const fs = require('fs');

const DB_PATH = path.join(__dirname, 'error-solutions.db');
const MD_PATH = path.join(__dirname, 'error-solutions.md');

function getDB() {
  const Database = require('better-sqlite3');
  return new Database(DB_PATH);
}

function initDB(db) {
  db.exec(`
    CREATE TABLE IF NOT EXISTS errors (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      timestamp TEXT NOT NULL,
      source TEXT NOT NULL,
      module TEXT,
      error_type TEXT,
      error_message TEXT NOT NULL,
      stack_trace TEXT,
      solution TEXT,
      files_changed TEXT,
      tags TEXT,
      resolved INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS patterns (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pattern TEXT NOT NULL,
      occurrences INTEGER DEFAULT 1,
      last_seen TEXT,
      best_solution TEXT
    );
  `);
}

function detectModule(errorMessage, stackTrace) {
  const text = (errorMessage + ' ' + (stackTrace || '')).toLowerCase();
  const modules = [
    'porter_invoice', 'gmail_leads', 'google_ads', 'billing',
    'quotation', 'migration', 'auth', 'settings'
  ];
  return modules.find(m => text.includes(m.replace('_', ' ')) || text.includes(m)) || 'general';
}

function appendMarkdown(entry) {
  const resolved = entry.resolved ? '✅' : '🔴';
  const section = `
## ${resolved} [${entry.source.toUpperCase()}] ${entry.error_type || 'Error'} — ${entry.timestamp}

**Module:** \`${entry.module || 'general'}\`
**Tags:** ${entry.tags ? JSON.parse(entry.tags).map(t => `\`${t}\``).join(', ') : '—'}

### Error
\`\`\`
${entry.error_message}
\`\`\`
${entry.stack_trace ? `\n### Stack Trace\n\`\`\`\n${entry.stack_trace.slice(0, 800)}\n\`\`\`\n` : ''}
### Solution
${entry.solution || '_Not yet resolved_'}
${entry.files_changed ? `\n**Files changed:** ${JSON.parse(entry.files_changed).map(f => `\`${f}\``).join(', ')}` : ''}

---
`;

  if (!fs.existsSync(MD_PATH)) {
    fs.writeFileSync(MD_PATH, '# ERP Error Solutions Log\n\nAuto-generated. Updated by Claude Code hooks and Django middleware.\n\n---\n');
  }
  fs.appendFileSync(MD_PATH, section);
}

function logError(payload) {
  const db = getDB();
  initDB(db);

  const timestamp = new Date().toISOString();
  const module = payload.module || detectModule(payload.error_message, payload.stack_trace);

  const entry = {
    timestamp,
    source: payload.source || 'manual',
    module,
    error_type: payload.error_type || null,
    error_message: payload.error_message,
    stack_trace: payload.stack_trace || null,
    solution: payload.solution || null,
    files_changed: payload.files_changed ? JSON.stringify(payload.files_changed) : null,
    tags: payload.tags ? JSON.stringify(payload.tags) : JSON.stringify([module]),
    resolved: payload.solution ? 1 : 0
  };

  const insert = db.prepare(`
    INSERT INTO errors (timestamp, source, module, error_type, error_message, stack_trace, solution, files_changed, tags, resolved)
    VALUES (@timestamp, @source, @module, @error_type, @error_message, @stack_trace, @solution, @files_changed, @tags, @resolved)
  `);
  const result = insert.run(entry);

  // Update patterns table
  const patternKey = (entry.error_type || '') + ':' + entry.error_message.slice(0, 60);
  const existing = db.prepare('SELECT id, occurrences FROM patterns WHERE pattern = ?').get(patternKey);
  if (existing) {
    db.prepare('UPDATE patterns SET occurrences = ?, last_seen = ?, best_solution = ? WHERE id = ?')
      .run(existing.occurrences + 1, timestamp, entry.solution || existing.best_solution, existing.id);
  } else {
    db.prepare('INSERT INTO patterns (pattern, occurrences, last_seen, best_solution) VALUES (?, 1, ?, ?)')
      .run(patternKey, timestamp, entry.solution);
  }

  appendMarkdown(entry);
  db.close();

  console.log(`[error-logger] Logged #${result.lastInsertRowid}: ${entry.error_type || 'Error'} in ${module}`);
  return result.lastInsertRowid;
}

function updateSolution(id, solution, filesChanged) {
  const db = getDB();
  initDB(db);
  db.prepare('UPDATE errors SET solution = ?, resolved = 1, files_changed = ? WHERE id = ?')
    .run(solution, filesChanged ? JSON.stringify(filesChanged) : null, id);
  db.close();
  console.log(`[error-logger] Updated solution for error #${id}`);
}

// CLI usage
const args = process.argv.slice(2);
if (args[0]) {
  try {
    const payload = JSON.parse(args[0]);
    if (payload.update_id) {
      updateSolution(payload.update_id, payload.solution, payload.files_changed);
    } else {
      logError(payload);
    }
  } catch (e) {
    console.error('[error-logger] Invalid JSON payload:', e.message);
    process.exit(1);
  }
}

module.exports = { logError, updateSolution };
