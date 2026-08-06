import assert from 'node:assert/strict';
import test from 'node:test';
import { REG_PWD } from '../src/constants/reg.ts';

const generatedPassword = '0123456789abcdef'.repeat(4);

test('login and profile forms accept generated passwords through the shared rule', () => {
  assert.equal(REG_PWD.test('a'.repeat(8)), true);
  assert.equal(REG_PWD.test(generatedPassword), true);
  assert.equal(REG_PWD.test('z'.repeat(128)), true);
});

test('shared password rule rejects unsafe lengths and whitespace', () => {
  for (const password of ['', 'a'.repeat(7), 'a'.repeat(129), 'safe passphrase', ' '.repeat(8)]) {
    assert.equal(REG_PWD.test(password), false, JSON.stringify(password));
  }
});
