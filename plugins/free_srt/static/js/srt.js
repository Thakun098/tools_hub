export function parseTime(value) {
  const match = /^(\d{1,3}):(\d{2}):(\d{2})[,.](\d{3})$/.exec(value.trim());
  if (!match) return null;
  const [, hours, minutes, seconds, milliseconds] = match;
  if (+minutes > 59 || +seconds > 59) return null;
  return (((+hours * 60) + +minutes) * 60 + +seconds) * 1000 + +milliseconds;
}

export function formatTime(value) {
  value = Math.max(0, Math.round(value));
  const hours = Math.floor(value / 3600000);
  value %= 3600000;
  const minutes = Math.floor(value / 60000);
  value %= 60000;
  const seconds = Math.floor(value / 1000);
  const milliseconds = value % 1000;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')},${String(milliseconds).padStart(3, '0')}`;
}

export function parseSrt(content) {
  const blocks = content.replace(/\r/g, '').trim().split(/\n\s*\n/).filter(Boolean);
  return blocks.map((block, index) => {
    const lines = block.split('\n');
    if (lines.length < 3) throw new Error(`บรรทัด SRT ชุดที่ ${index + 1} ไม่สมบูรณ์`);
    const times = lines[1].split(/\s+-->\s+/);
    const start = parseTime(times[0] || '');
    const end = parseTime(times[1] || '');
    if (start === null || end === null) throw new Error(`เวลาในชุดที่ ${index + 1} ไม่ถูกต้อง`);
    return {start_ms: start, end_ms: end, text: lines.slice(2).join('\n').trim()};
  });
}


export function displayUnits(text) {
  const source = String(text || '');
  if (globalThis.Intl?.Segmenter) {
    return [...new Intl.Segmenter(undefined, {granularity: 'grapheme'}).segment(source)]
      .map(item => item.segment);
  }
  return Array.from(source);
}

export function displayLength(text) {
  return displayUnits(String(text || '').replace(/\s/g, '')).length;
}

export function splitCueText(text, targetRatio = 0.5) {
  const source = String(text || '').replace(/\r\n/g, '\n').trim();
  const units = displayUnits(source);
  if (units.length < 2) return null;
  const ratio = Number.isFinite(targetRatio) ? Math.min(1, Math.max(0, targetRatio)) : 0.5;
  const target = Math.min(units.length - 1, Math.max(1, Math.round(units.length * ratio)));
  const punctuation = /[.!?\u3002\uFF01\uFF1F\u2026\uFF0C,;:\uFF1B\uFF1A\u3001\u2014-]/;
  const candidates = units.map((_, index) => index + 1).filter(index => index < units.length);
  const nearbyRadius = Math.max(1, Math.floor(units.length / 4));
  const nearby = candidates.filter(index => Math.abs(index - target) <= nearbyRadius);
  const natural = nearby.filter(index => /\s/.test(units[index - 1]) || punctuation.test(units[index - 1]));
  const pool = natural.length ? natural : nearby;
  const boundary = pool.reduce((best, index) => (
    Math.abs(index - target) < Math.abs(best - target) ? index : best
  ), pool[0]);
  const left = units.slice(0, boundary).join('').trim();
  const right = units.slice(boundary).join('').trim();
  return left && right ? {left, right, ratio: boundary / units.length} : null;
}
