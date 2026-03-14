#!/usr/bin/env node
// Initialize the error-solutions SQLite database
// Run once: node .claude/init-error-log.js

const Database = require('better-sqlite3');
const path = require('path');
const fs = require('fs');

const DB_PATH = path.join(__dirname, 'error-solutions.db');
const db = new Database(DB_PATH);

db.exec(`
  CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,          -- 'claude', 'django', 'bash', 'manual'
    module TEXT,                   -- e.g. 'porter_invoice', 'gmail_leads'
    error_type TEXT,               -- e.g. 'KeyError', 'MigrationError', '500'
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    solution TEXT,
    files_changed TEXT,            -- JSON array of files touched in fix
    tags TEXT,                     -- JSON array e.g. ['migration','gmail','billing']
    resolved INTEGER DEFAULT 0     -- 0=unresolved, 1=resolved
  );

  CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern TEXT NOT NULL,         -- recurring error pattern/keyword
    occurrences INTEGER DEFAULT 1,
    last_seen TEXT,
    best_solution TEXT
  );
`);

console.log('Error-solutions DB initialized at:', DB_PATH);
db.close();
