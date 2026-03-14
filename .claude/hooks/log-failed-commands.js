#!/usr/bin/env node
// PostToolUseFailure hook: log failed bash commands with their error output

const path = require('path');
const { execSync } = require('child_process');

const LOGGER = path.join(__dirname, '..', 'error-logger.js');

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => { input += chunk; });
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const toolName = data.tool_name || '';

    if (toolName !== 'Bash') {
      process.exit(0);
    }

    const command = (data.tool_input || {}).command || '';
    const errorOutput = (data.tool_result || {}).stderr ||
                        (data.tool_result || {}).error ||
                        JSON.stringify(data.tool_result || {});

    // Skip trivial/noisy failures
    const skipPatterns = ['grep', 'ls ', 'cat ', 'echo '];
    if (skipPatterns.some(p => command.startsWith(p))) process.exit(0);

    const errorType = command.startsWith('python manage.py migrate') ? 'MigrationError'
      : command.startsWith('pip install') ? 'InstallError'
      : command.startsWith('python manage.py') ? 'DjangoManagementError'
      : 'BashCommandError';

    const payload = {
      source: 'bash',
      error_type: errorType,
      error_message: `Command failed: ${command.slice(0, 150)}`,
      stack_trace: errorOutput ? String(errorOutput).slice(0, 1000) : null,
      tags: ['bash', 'auto-logged', errorType.toLowerCase()]
    };

    execSync(`node "${LOGGER}" '${JSON.stringify(payload).replace(/'/g, "\\'")}'`);
  } catch (e) {
    // Silent fail
  }
  process.exit(0);
});
