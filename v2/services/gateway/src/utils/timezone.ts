/**
 * IST Timezone Helper for ChampIQ V2
 * Provides consistent IST (Indian Standard Time, UTC+5:30) formatting.
 */

const IST_OFFSET_MS = 5.5 * 60 * 60 * 1000;

/**
 * Get the current date/time in IST as a Date object.
 */
export function nowIST(): Date {
  const now = new Date();
  return new Date(now.getTime() + IST_OFFSET_MS);
}

/**
 * Format a Date to an IST string: "YYYY-MM-DD HH:mm:ss IST"
 */
export function formatIST(date?: Date): string {
  const d = date ? new Date(date.getTime() + IST_OFFSET_MS) : nowIST();
  const year = d.getUTCFullYear();
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hours = String(d.getUTCHours()).padStart(2, '0');
  const minutes = String(d.getUTCMinutes()).padStart(2, '0');
  const seconds = String(d.getUTCSeconds()).padStart(2, '0');
  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} IST`;
}

/**
 * Get IST date string: "YYYY-MM-DD"
 */
export function todayIST(): string {
  const d = nowIST();
  const year = d.getUTCFullYear();
  const month = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

/**
 * Get IST time string: "HH:mm:ss"
 */
export function timeIST(): string {
  const d = nowIST();
  const hours = String(d.getUTCHours()).padStart(2, '0');
  const minutes = String(d.getUTCMinutes()).padStart(2, '0');
  const seconds = String(d.getUTCSeconds()).padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

/**
 * Check if current IST time is within business hours (9 AM - 6 PM).
 */
export function isBusinessHoursIST(): boolean {
  const d = nowIST();
  const hour = d.getUTCHours();
  return hour >= 9 && hour < 18;
}
