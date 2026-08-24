const fs = require('fs');
const path = require('path');
const os = require('os');

const homeDir = os.homedir();
const srcPath = path.join(homeDir, '.claude', 'settings.json');
const destPath = path.join(__dirname, 'gclaude-settings.json');

let settings = {};

if (fs.existsSync(srcPath)) {
  try {
    const raw = fs.readFileSync(srcPath, 'utf8');
    settings = JSON.parse(raw);
  } catch (err) {
    console.error(`[gclaude] Warning: Failed to parse ${srcPath}:`, err.message);
  }
}

if (!settings || typeof settings !== 'object' || Array.isArray(settings)) {
  settings = {};
}

if (!settings.env || typeof settings.env !== 'object' || Array.isArray(settings.env)) {
  settings.env = {};
}

// Set custom environment variables
settings.env.ANTHROPIC_BASE_URL = 'http://127.0.0.1:26767/anthropic';
settings.env.ANTHROPIC_API_KEY = 'sk-my-super-secret-key-123';
settings.env.ANTHROPIC_MODEL = 'max-gem';

// Remove ANTHROPIC_AUTH_TOKEN if present to ensure API key is used
delete settings.env.ANTHROPIC_AUTH_TOKEN;

try {
  fs.writeFileSync(destPath, JSON.stringify(settings, null, 2) + '\n', 'utf8');
} catch (err) {
  console.error(`[gclaude] Error writing to ${destPath}:`, err.message);
  process.exit(1);
}
