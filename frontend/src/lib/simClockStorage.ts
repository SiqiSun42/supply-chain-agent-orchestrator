import { DEFAULT_SIM_TIME_MS } from "./format";

const TIME_KEY = "orchestrator.simClock.timeMs";
const RUNNING_KEY = "orchestrator.simClock.running";

export type SimClockSnapshot = {
  simTimeMs: number;
  running: boolean;
};

function readNumber(key: string): number | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

function readBoolean(key: string): boolean | null {
  try {
    const raw = localStorage.getItem(key);
    if (raw === "1") return true;
    if (raw === "0") return false;
    return null;
  } catch {
    return null;
  }
}

export function loadSimClock(): SimClockSnapshot {
  const simTimeMs = readNumber(TIME_KEY) ?? DEFAULT_SIM_TIME_MS;
  const running = readBoolean(RUNNING_KEY) ?? false;
  return { simTimeMs, running };
}

export function saveSimClock(snapshot: SimClockSnapshot): void {
  try {
    localStorage.setItem(TIME_KEY, String(snapshot.simTimeMs));
    localStorage.setItem(RUNNING_KEY, snapshot.running ? "1" : "0");
  } catch {
    /* storage unavailable */
  }
}
