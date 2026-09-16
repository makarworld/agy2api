import assert from 'node:assert/strict';
import test from 'node:test';

import { buildThoughtTemplate, parseThoughtTemplate } from './thought-template.ts';

test('builds escaped template around protected marker', () => {
  assert.equal(buildThoughtTemplate('<think>\n', '\n</think>\n\n'), '<think>\\n{...}\\n</think>\\n\\n');
});

test('splits valid template and restores newlines', () => {
  assert.deepEqual(parseThoughtTemplate('[think]\\n{...}\\n[/think]'), {
    prefix: '[think]\n',
    suffix: '\n[/think]',
  });
});

test('rejects missing or duplicate marker', () => {
  assert.equal(parseThoughtTemplate('<think>text</think>'), null);
  assert.equal(parseThoughtTemplate('{...}{...}'), null);
});
