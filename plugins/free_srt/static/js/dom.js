export const $ = id => document.getElementById(id);

export function escapeHtml(value) {
  const element = document.createElement('span');
  element.textContent = String(value ?? '');
  return element.innerHTML;
}

export function formatEta(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(Number(seconds))) {
    return 'กำลังประเมินเวลา...';
  }
  seconds = Math.max(0, Math.round(Number(seconds)));
  if (seconds < 5) return 'ใกล้เสร็จแล้ว';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  const remainingSeconds = seconds % 60;
  return `เหลือประมาณ ${hours ? `${hours} ชม. ` : ''}${minutes ? `${minutes} นาที ` : ''}${!hours && remainingSeconds ? `${remainingSeconds} วินาที` : ''}`.trim();
}

