#!/usr/bin/env node
// PostToolUse hook: auto-log errors that Claude detects and fixes
// Triggers after Edit/Write tool uses when error patterns are found

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const LOGGER = path.join(__dirname, '..', 'error-logger.js');
const ERROR_PATTERNS = [
  /(?:Error|Exception|Traceback|FAILED|ERROR)[\s\S]{0,300}/i,
  /raise\s+\w+Error/,
  /File ".*", line \d+/,
];

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const toolName = data.tool_name || '';
    const toolInput = data.tool_input || {};
    const toolResult = data.tool_result || {};

    // Only act on Edit/Write tool uses
    if (!['Edit', 'Write', 'MultiEdit'].includes(toolName)) {
      process.exit(0);
    }

    const resultText = JSON.stringify(toolResult);
    const inputText = JSON.stringify(toolInput);

    // Detect if there was an error being fixed (old_string contains error pattern)
    const oldString = toolInput.old_string || '';
    const newString = toolInput.new_string || '';
    const filePath = toolInput.file_path || toolInput.path || '';

    const hasErrorInOld = ERROR_PATTERNS.some(p => p.test(oldString));
    const isFixing = oldString && newString && hasErrorInOld;

    if (!isFixing) {
      // Also check if result indicates a fix happened via error keywords in context
      const fixKeywords = ['fix', 'error', 'exception', 'bug', 'traceback', 'failed'];
      const contextHasFix = fixKeywords.some(k =>
        inputText.toLowerCase().includes(k) && newString.length > 0
      );
      if (!contextHasFix) process.exit(0);
    }

    const errorMatch = oldString.match(/(\w+Error|\w+Exception|FAILED.*)/i);
    const errorType = errorMatch ? errorMatch[1] : 'Bug';
    const errorMessage = oldString.slice(0, 300).trim() || 'Code error detected';

    const payload = {
      source: 'claude',
      error_type: errorType,
      error_message: errorMessage,
      solution: `Fixed in ${path.basename(filePath)}: replaced with corrected code`,
      files_changed: filePath ? [filePath] : [],
      tags: ['auto-logged', 'claude-fix']
    };

    execSync(`node "${LOGGER}" '${JSON.stringify(payload).replace(/'/g, "\\'")}'`);
  } catch (e) {
    // Silent fail — never block the tool
  }
  process.exit(0);
});
