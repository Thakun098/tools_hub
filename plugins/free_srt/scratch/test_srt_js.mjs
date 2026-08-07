import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';

const sourceCode = readFileSync(new URL('../static/js/srt.js', import.meta.url), 'utf8');
const moduleUrl = 'data:text/javascript;base64,' + Buffer.from(sourceCode).toString('base64');
const {displayLength, displayUnits, splitCueText} = await import(moduleUrl);

test('manual split preserves Thai text and never invents ellipsis', () => {
  const source = '\u0e01\u0e33\u0e25\u0e31\u0e07\u0e17\u0e14\u0e2a\u0e2d\u0e1a\u0e01\u0e32\u0e23\u0e41\u0e1a\u0e48\u0e07\u0e04\u0e33\u0e1a\u0e23\u0e23\u0e22\u0e32\u0e22';
  const result = splitCueText(source, 0.4);
  assert.ok(result);
  assert.equal(result.left + result.right, source);
  assert.equal(result.left.includes('...') || result.right.includes('...'), false);
});

test('manual split follows a requested caret or media ratio', () => {
  const source = 'one two three four five six seven eight';
  const early = splitCueText(source, 0.25);
  const late = splitCueText(source, 0.75);
  assert.ok(early.ratio < late.ratio);
  assert.equal(early.left + ' ' + early.right, source);
  assert.equal(late.left + ' ' + late.right, source);
});

test('display units keep Thai spacing marks attached', () => {
  const saraAm = '\u0e01\u0e33';
  assert.equal(displayLength(saraAm), 1);
  assert.equal(displayUnits(saraAm).length, 1);
});
