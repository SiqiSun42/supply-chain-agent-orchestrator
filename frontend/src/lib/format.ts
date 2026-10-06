export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return new Date(iso).toLocaleDateString();
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

export function compact(value: number): string {
  return new Intl.NumberFormat("en", { notation: "compact" }).format(value);
}

export function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const SIM_CLOCK_TZ = "UTC";

export function formatSimClock(epochMs: number): string {
  const d = new Date(epochMs);
  const date = d.toLocaleDateString("en-CA", { timeZone: SIM_CLOCK_TZ });
  const time = d.toLocaleTimeString("en-US", {
    timeZone: SIM_CLOCK_TZ,
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
  return `${date}, ${time}`;
}

export const DEFAULT_SIM_TIME_MS = Date.UTC(2026, 0, 1, 0, 0, 0);

export type UtcDateTimeParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
};

export function simTimeToUtcParts(epochMs: number): UtcDateTimeParts {
  const d = new Date(epochMs);
  return {
    year: d.getUTCFullYear(),
    month: d.getUTCMonth() + 1,
    day: d.getUTCDate(),
    hour: d.getUTCHours(),
    minute: d.getUTCMinutes(),
    second: d.getUTCSeconds(),
  };
}

export function utcPartsToDateInput(parts: Pick<UtcDateTimeParts, "year" | "month" | "day">): string {
  const y = parts.year;
  const m = String(parts.month).padStart(2, "0");
  const d = String(parts.day).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function parseDateInput(value: string): Pick<UtcDateTimeParts, "year" | "month" | "day"> | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  const ms = Date.UTC(year, month - 1, day);
  const check = new Date(ms);
  if (check.getUTCFullYear() !== year || check.getUTCMonth() + 1 !== month || check.getUTCDate() !== day) {
    return null;
  }
  return { year, month, day };
}

export function utcPartsToSimTimeMs(parts: UtcDateTimeParts): number | null {
  if (
    parts.hour < 0 ||
    parts.hour > 23 ||
    parts.minute < 0 ||
    parts.minute > 59 ||
    parts.second < 0 ||
    parts.second > 59
  ) {
    return null;
  }
  const date = parseDateInput(utcPartsToDateInput(parts));
  if (!date) return null;
  const ms = Date.UTC(date.year, date.month - 1, date.day, parts.hour, parts.minute, parts.second);
  return Number.isFinite(ms) ? ms : null;
}
