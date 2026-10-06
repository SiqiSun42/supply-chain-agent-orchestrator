import { createContext, useContext, useEffect, useRef, useState, type Dispatch, type ReactNode, type SetStateAction } from "react";

import { api } from "./api";
import { type Alarm, loadAlarms, MS_PER_UTC_DAY, saveAlarms } from "./alarmsStorage";
import { loadSimClock, saveSimClock } from "./simClockStorage";
import { useUser } from "./user";

type SimContextValue = {
  simTimeMs: number;
  setSimTimeMs: Dispatch<SetStateAction<number>>;
  running: boolean;
  setRunning: Dispatch<SetStateAction<boolean>>;
  clockEditing: boolean;
  setClockEditing: Dispatch<SetStateAction<boolean>>;
  alarms: Alarm[];
  setAlarms: Dispatch<SetStateAction<Alarm[]>>;
};

const SimContext = createContext<SimContextValue | null>(null);

function fireDueAlarms(simTimeMs: number, alarms: Alarm[], userId: string): Alarm[] | null {
  let next: Alarm[] | null = null;
  for (const alarm of alarms) {
    if (!alarm.enabled || alarm.triggerTimeMs !== simTimeMs) continue;
    const task = alarm.task.trim();
    if (!task) continue;
    void api.createRun(task, userId, null).catch(() => {});
    if (alarm.repeatDays > 0) {
      if (!next) next = [...alarms];
      const idx = next.findIndex((a) => a.id === alarm.id);
      if (idx >= 0) {
        next[idx] = {
          ...next[idx],
          triggerTimeMs: alarm.triggerTimeMs + alarm.repeatDays * MS_PER_UTC_DAY,
        };
      }
    }
  }
  return next;
}

export function SimProvider({ children }: { children: ReactNode }) {
  const { userId } = useUser();
  const [simTimeMs, setSimTimeMs] = useState(() => loadSimClock().simTimeMs);
  const [running, setRunning] = useState(() => loadSimClock().running);
  const [clockEditing, setClockEditing] = useState(false);
  const [alarms, setAlarms] = useState<Alarm[]>(() => loadAlarms());

  const alarmsRef = useRef(alarms);
  const userIdRef = useRef(userId);
  const simTimeRef = useRef(simTimeMs);

  useEffect(() => {
    alarmsRef.current = alarms;
  }, [alarms]);

  useEffect(() => {
    userIdRef.current = userId;
  }, [userId]);

  useEffect(() => {
    simTimeRef.current = simTimeMs;
  }, [simTimeMs]);

  useEffect(() => {
    saveSimClock({ simTimeMs, running });
  }, [simTimeMs, running]);

  useEffect(() => {
    saveAlarms(alarms);
  }, [alarms]);

  useEffect(() => {
    if (!running || clockEditing) return;
    const id = window.setInterval(() => {
      const next = simTimeRef.current + 1000;
      simTimeRef.current = next;
      setSimTimeMs(next);
      const rescheduled = fireDueAlarms(next, alarmsRef.current, userIdRef.current);
      if (rescheduled) setAlarms(rescheduled);
    }, 1000);
    return () => window.clearInterval(id);
  }, [running, clockEditing]);

  return (
    <SimContext.Provider
      value={{
        simTimeMs,
        setSimTimeMs,
        running,
        setRunning,
        clockEditing,
        setClockEditing,
        alarms,
        setAlarms,
      }}
    >
      {children}
    </SimContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSim() {
  const ctx = useContext(SimContext);
  if (!ctx) throw new Error("useSim must be used within SimProvider");
  return ctx;
}
