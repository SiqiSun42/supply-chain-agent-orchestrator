export const MS_PER_UTC_DAY = 86400000;

export type Alarm = {
  id: string;
  triggerTimeMs: number;
  task: string;
  enabled: boolean;
  repeatDays: number;
};

export function normalizeRepeatDays(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return 0;
  return Math.floor(value);
}

const STORAGE_KEY = "orchestrator.alarms";

export const DEFAULT_ALARMS: Alarm[] = [
  {
    id: "alarm-sample-1",
    triggerTimeMs: Date.UTC(2026, 0, 1, 0, 1, 16),
    task:
      "What is the latest inventory for part HYD-08 at warehouse WH-1? Report units on hand, reorder point, units reserved, units in transit, and the snapshot date used.",
    enabled: true,
    repeatDays: 0,
  },
];

function isAlarm(value: unknown): value is Alarm {
  if (!value || typeof value !== "object") return false;
  const a = value as Alarm;
  return (
    typeof a.id === "string" &&
    typeof a.triggerTimeMs === "number" &&
    Number.isFinite(a.triggerTimeMs) &&
    typeof a.task === "string" &&
    typeof a.enabled === "boolean"
  );
}

function normalizeAlarm(value: unknown): Alarm | null {
  if (!isAlarm(value)) return null;
  return {
    ...value,
    repeatDays: normalizeRepeatDays(value.repeatDays),
  };
}

export function loadAlarms(): Alarm[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === null) return DEFAULT_ALARMS;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return DEFAULT_ALARMS;
    return parsed.map(normalizeAlarm).filter((a): a is Alarm => a !== null);
  } catch {
    return DEFAULT_ALARMS;
  }
}

export function saveAlarms(alarms: Alarm[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(alarms));
  } catch {
    /* storage unavailable */
  }
}
