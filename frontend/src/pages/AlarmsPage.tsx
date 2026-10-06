import clsx from "clsx";
import { AlarmClock, Pause, Pencil, Play, Plus } from "lucide-react";
import { useRef, useState } from "react";

import { PageHeader } from "../components/PageHeader";
import { Button } from "../components/ui";
import {
  formatSimClock,
  parseDateInput,
  simTimeToUtcParts,
  utcPartsToDateInput,
  utcPartsToSimTimeMs,
  type UtcDateTimeParts,
} from "../lib/format";
import { type Alarm, normalizeRepeatDays } from "../lib/alarmsStorage";
import { useSim } from "../lib/simContext";

type Tab = "alarms" | "time";

const fieldClass =
  "rounded-lg border border-slate-300 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none";

const NEW_ALARM_DEFAULT_MS = Date.UTC(2026, 0, 2, 0, 0, 0);

function newAlarmId(): string {
  return crypto.randomUUID();
}

function defaultNewAlarmDraft(): { dateInput: string; draft: UtcDateTimeParts; content: string } {
  const draft = simTimeToUtcParts(NEW_ALARM_DEFAULT_MS);
  return {
    dateInput: utcPartsToDateInput(draft),
    draft,
    content: "",
  };
}

type UtcTimeFieldsProps = {
  dateInput: string;
  draft: UtcDateTimeParts;
  onDateChange: (value: string) => void;
  patchDraft: (patch: Partial<UtcDateTimeParts>) => void;
  repeatDays?: number;
  onRepeatDaysChange?: (value: number) => void;
};

function UtcTimeFields({
  dateInput,
  draft,
  onDateChange,
  patchDraft,
  repeatDays,
  onRepeatDaysChange,
}: UtcTimeFieldsProps) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Date</span>
        <input type="date" className={fieldClass} value={dateInput} onChange={(e) => onDateChange(e.target.value)} />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Hour</span>
        <input
          type="number"
          min={0}
          max={23}
          className={clsx(fieldClass, "w-20 tabular-nums")}
          value={draft.hour}
          onChange={(e) => patchDraft({ hour: Number(e.target.value) })}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Minute</span>
        <input
          type="number"
          min={0}
          max={59}
          className={clsx(fieldClass, "w-20 tabular-nums")}
          value={draft.minute}
          onChange={(e) => patchDraft({ minute: Number(e.target.value) })}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs text-slate-500">Second</span>
        <input
          type="number"
          min={0}
          max={59}
          className={clsx(fieldClass, "w-20 tabular-nums")}
          value={draft.second}
          onChange={(e) => patchDraft({ second: Number(e.target.value) })}
        />
      </label>
      {onRepeatDaysChange !== undefined && repeatDays !== undefined && (
        <label className="block">
          <span className="mb-1 block text-xs text-slate-500">Repeat</span>
          <div className="flex items-center gap-1.5 text-sm text-slate-700">
            <span>every</span>
            <input
              type="number"
              min={0}
              className={clsx(fieldClass, "w-16 tabular-nums")}
              value={repeatDays}
              onChange={(e) => onRepeatDaysChange(normalizeRepeatDays(Number(e.target.value)))}
            />
            <span>day(s)</span>
          </div>
        </label>
      )}
    </div>
  );
}

type AlarmEditorFormProps = {
  dateInput: string;
  draft: UtcDateTimeParts;
  repeatDays: number;
  content: string;
  error: string | null;
  onDateChange: (value: string) => void;
  patchDraft: (patch: Partial<UtcDateTimeParts>) => void;
  onRepeatDaysChange: (value: number) => void;
  onContentChange: (value: string) => void;
  onApply: () => void;
  onCancel: () => void;
  onDelete?: () => void;
};

function AlarmEditorForm({
  dateInput,
  draft,
  repeatDays,
  content,
  error,
  onDateChange,
  patchDraft,
  onRepeatDaysChange,
  onContentChange,
  onApply,
  onCancel,
  onDelete,
}: AlarmEditorFormProps) {
  return (
    <div className="mt-4 space-y-6 border-t border-slate-100 pt-6">
      <div>
        <p className="mb-3 text-sm font-medium text-slate-700">Set alarm time (UTC)</p>
        <UtcTimeFields
          dateInput={dateInput}
          draft={draft}
          onDateChange={onDateChange}
          patchDraft={patchDraft}
          repeatDays={repeatDays}
          onRepeatDaysChange={onRepeatDaysChange}
        />
      </div>
      <div>
        <p className="mb-3 text-sm font-medium text-slate-700">Set alarm content</p>
        <textarea
          className={clsx(fieldClass, "min-h-[140px] w-full resize-y font-normal leading-relaxed")}
          value={content}
          onChange={(e) => onContentChange(e.target.value)}
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" onClick={onApply}>
          Apply
        </Button>
        {onDelete && (
          <Button type="button" variant="danger" size="sm" onClick={onDelete}>
            Delete
          </Button>
        )}
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </div>
  );
}

function parseAlarmDraft(
  dateInput: string,
  draft: UtcDateTimeParts,
): { ok: true; ms: number } | { ok: false; error: string } {
  const date = parseDateInput(dateInput);
  if (!date) {
    return { ok: false, error: "Enter a valid UTC date." };
  }
  const ms = utcPartsToSimTimeMs({
    ...date,
    hour: draft.hour,
    minute: draft.minute,
    second: draft.second,
  });
  if (ms === null) {
    return { ok: false, error: "Enter a valid UTC date and time." };
  }
  return { ok: true, ms };
}

type AlarmCardProps = {
  alarm: Alarm;
  editing: boolean;
  editorLocked: boolean;
  dateInput: string;
  draft: UtcDateTimeParts;
  contentDraft: string;
  repeatDaysDraft: number;
  editError: string | null;
  onOpenEdit: () => void;
  onCancelEdit: () => void;
  onApplyEdit: () => void;
  onDeleteEdit: () => void;
  onToggleEnabled: () => void;
  onDateChange: (value: string) => void;
  patchDraft: (patch: Partial<UtcDateTimeParts>) => void;
  onRepeatDaysChange: (value: number) => void;
  onContentChange: (value: string) => void;
};

function AlarmCard({
  alarm,
  editing,
  editorLocked,
  dateInput,
  draft,
  contentDraft,
  repeatDaysDraft,
  editError,
  onOpenEdit,
  onCancelEdit,
  onApplyEdit,
  onDeleteEdit,
  onToggleEnabled,
  onDateChange,
  patchDraft,
  onRepeatDaysChange,
  onContentChange,
}: AlarmCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
      <p className="text-lg text-slate-900">
        <span className="font-medium text-slate-600">Alarm: </span>
        <span className="font-mono tabular-nums">{formatSimClock(alarm.triggerTimeMs)}</span>
        <span className="ml-2 text-sm font-normal text-slate-400">UTC</span>
      </p>
      {!editing && <p className="mt-4 text-sm leading-relaxed text-slate-700">{alarm.task}</p>}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant={editing ? "primary" : "secondary"}
          size="sm"
          disabled={editorLocked && !editing}
          aria-label={editing ? "Close alarm editor" : "Edit alarm"}
          aria-pressed={editing}
          onClick={() => (editing ? onCancelEdit() : onOpenEdit())}
        >
          <Pencil className="h-4 w-4" />
          {editing ? "Close" : "Edit"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={editing || editorLocked}
          aria-label={alarm.enabled ? "Disable alarm" : "Enable alarm"}
          aria-pressed={alarm.enabled}
          onClick={onToggleEnabled}
        >
          <AlarmClock className="h-4 w-4" />
          {alarm.enabled ? "Disable" : "Enable"}
        </Button>
        <span className="text-sm text-slate-500">
          {editing
            ? "Editing alarm — this alarm is disabled."
            : alarm.enabled
              ? "This alarm is enabled."
              : "This alarm is disabled."}
        </span>
      </div>
      {editing && (
        <AlarmEditorForm
          dateInput={dateInput}
          draft={draft}
          repeatDays={repeatDaysDraft}
          content={contentDraft}
          error={editError}
          onDateChange={onDateChange}
          patchDraft={patchDraft}
          onRepeatDaysChange={onRepeatDaysChange}
          onContentChange={onContentChange}
          onApply={onApplyEdit}
          onDelete={onDeleteEdit}
          onCancel={onCancelEdit}
        />
      )}
    </div>
  );
}

export function AlarmsPage() {
  const {
    simTimeMs,
    setSimTimeMs,
    running,
    setRunning,
    clockEditing,
    setClockEditing,
    alarms,
    setAlarms,
  } = useSim();
  const [tab, setTab] = useState<Tab>("alarms");
  const [addingNew, setAddingNew] = useState(false);
  const [editingAlarmId, setEditingAlarmId] = useState<string | null>(null);
  const [formDateInput, setFormDateInput] = useState("");
  const [formDraft, setFormDraft] = useState<UtcDateTimeParts>(() => simTimeToUtcParts(NEW_ALARM_DEFAULT_MS));
  const [formContent, setFormContent] = useState("");
  const [formRepeatDays, setFormRepeatDays] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const enabledBeforeEditRef = useRef<boolean | null>(null);

  const [clockDraft, setClockDraft] = useState<UtcDateTimeParts>(() => simTimeToUtcParts(simTimeMs));
  const [clockDateInput, setClockDateInput] = useState(() => utcPartsToDateInput(simTimeToUtcParts(simTimeMs)));
  const [clockEditError, setClockEditError] = useState<string | null>(null);
  const runningBeforeClockEditRef = useRef<boolean | null>(null);

  const editorBusy = addingNew || editingAlarmId !== null;

  const finishClockEdit = () => {
    const restoreRunning = runningBeforeClockEditRef.current;
    runningBeforeClockEditRef.current = null;
    setClockEditError(null);
    setClockEditing(false);
    if (restoreRunning !== null) {
      setRunning(restoreRunning);
    }
  };

  const openClockEdit = () => {
    runningBeforeClockEditRef.current = running;
    setRunning(false);
    const parts = simTimeToUtcParts(simTimeMs);
    setClockDraft(parts);
    setClockDateInput(utcPartsToDateInput(parts));
    setClockEditError(null);
    setClockEditing(true);
  };

  const cancelClockEdit = () => {
    finishClockEdit();
  };

  const applyClockEdit = () => {
    const parsed = parseAlarmDraft(clockDateInput, clockDraft);
    if (!parsed.ok) {
      setClockEditError(parsed.error);
      return;
    }
    setSimTimeMs(parsed.ms);
    finishClockEdit();
  };

  const patchClockDraft = (patch: Partial<UtcDateTimeParts>) => {
    setClockDraft((d) => ({ ...d, ...patch }));
  };

  const onClockDateChange = (value: string) => {
    setClockDateInput(value);
    const date = parseDateInput(value);
    if (date) setClockDraft((d) => ({ ...d, ...date }));
  };

  const resetFormToNewDefaults = () => {
    const defaults = defaultNewAlarmDraft();
    setFormDateInput(defaults.dateInput);
    setFormDraft(defaults.draft);
    setFormContent(defaults.content);
    setFormRepeatDays(0);
    setFormError(null);
  };

  const finishAlarmEdit = () => {
    const restoreEnabled = enabledBeforeEditRef.current;
    const editId = editingAlarmId;
    enabledBeforeEditRef.current = null;
    setFormError(null);
    setEditingAlarmId(null);
    if (editId !== null && restoreEnabled !== null) {
      setAlarms((list) => list.map((a) => (a.id === editId ? { ...a, enabled: restoreEnabled } : a)));
    }
  };

  const openAddNew = () => {
    finishAlarmEdit();
    resetFormToNewDefaults();
    setAddingNew(true);
  };

  const cancelAddNew = () => {
    setFormError(null);
    setAddingNew(false);
  };

  const applyAddNew = () => {
    const parsed = parseAlarmDraft(formDateInput, formDraft);
    if (!parsed.ok) {
      setFormError(parsed.error);
      return;
    }
    const alarm: Alarm = {
      id: newAlarmId(),
      triggerTimeMs: parsed.ms,
      task: formContent,
      enabled: true,
      repeatDays: normalizeRepeatDays(formRepeatDays),
    };
    setAlarms((list) => [...list, alarm]);
    setAddingNew(false);
    setFormError(null);
  };

  const openAlarmEdit = (alarm: Alarm) => {
    if (addingNew) {
      setAddingNew(false);
      setFormError(null);
    }
    finishAlarmEdit();
    enabledBeforeEditRef.current = alarm.enabled;
    setAlarms((list) => list.map((a) => (a.id === alarm.id ? { ...a, enabled: false } : a)));
    const parts = simTimeToUtcParts(alarm.triggerTimeMs);
    setFormDateInput(utcPartsToDateInput(parts));
    setFormDraft(parts);
    setFormContent(alarm.task);
    setFormRepeatDays(alarm.repeatDays);
    setFormError(null);
    setEditingAlarmId(alarm.id);
  };

  const cancelAlarmEdit = () => {
    finishAlarmEdit();
  };

  const applyAlarmEdit = () => {
    const editId = editingAlarmId;
    if (!editId) return;
    const parsed = parseAlarmDraft(formDateInput, formDraft);
    if (!parsed.ok) {
      setFormError(parsed.error);
      return;
    }
    setAlarms((list) =>
      list.map((a) =>
        a.id === editId
          ? {
              ...a,
              triggerTimeMs: parsed.ms,
              task: formContent,
              repeatDays: normalizeRepeatDays(formRepeatDays),
            }
          : a,
      ),
    );
    finishAlarmEdit();
  };

  const deleteAlarmEdit = () => {
    const editId = editingAlarmId;
    if (!editId) return;
    if (!window.confirm("Are you sure you want to delete this alarm?")) return;
    enabledBeforeEditRef.current = null;
    setAlarms((list) => list.filter((a) => a.id !== editId));
    setFormError(null);
    setEditingAlarmId(null);
  };

  const patchFormDraft = (patch: Partial<UtcDateTimeParts>) => {
    setFormDraft((d) => ({ ...d, ...patch }));
  };

  const onFormDateChange = (value: string) => {
    setFormDateInput(value);
    const date = parseDateInput(value);
    if (date) setFormDraft((d) => ({ ...d, ...date }));
  };

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Alarms"
        subtitle="Simulated clock and scheduled tasks."
        tabs={
          <div className="inline-flex rounded-lg bg-slate-100 p-1 text-sm">
            {(
              [
                ["alarms", "Alarms"],
                ["time", "Time"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={clsx(
                  "rounded-md px-3 py-1 font-medium",
                  tab === id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500",
                )}
              >
                {label}
              </button>
            ))}
          </div>
        }
      />
      <div className="scrollbar-thin flex-1 overflow-y-auto px-8 py-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {tab === "alarms" && (
            <>
              <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
                <Button
                  type="button"
                  variant={addingNew ? "primary" : "secondary"}
                  size="sm"
                  disabled={editingAlarmId !== null}
                  aria-expanded={addingNew}
                  onClick={() => (addingNew ? cancelAddNew() : openAddNew())}
                >
                  <Plus className="h-4 w-4" />
                  {addingNew ? "Close" : "Add new alarm"}
                </Button>
                {addingNew && (
                  <AlarmEditorForm
                    dateInput={formDateInput}
                    draft={formDraft}
                    repeatDays={formRepeatDays}
                    content={formContent}
                    error={formError}
                    onDateChange={onFormDateChange}
                    patchDraft={patchFormDraft}
                    onRepeatDaysChange={setFormRepeatDays}
                    onContentChange={setFormContent}
                    onApply={applyAddNew}
                    onCancel={cancelAddNew}
                  />
                )}
              </div>
              {alarms.map((alarm) => (
                <AlarmCard
                  key={alarm.id}
                  alarm={alarm}
                  editing={editingAlarmId === alarm.id}
                  editorLocked={editorBusy && editingAlarmId !== alarm.id}
                  dateInput={formDateInput}
                  draft={formDraft}
                  contentDraft={formContent}
                  repeatDaysDraft={formRepeatDays}
                  editError={formError}
                  onOpenEdit={() => openAlarmEdit(alarm)}
                  onCancelEdit={cancelAlarmEdit}
                  onApplyEdit={applyAlarmEdit}
                  onDeleteEdit={deleteAlarmEdit}
                  onToggleEnabled={() =>
                    setAlarms((list) => list.map((a) => (a.id === alarm.id ? { ...a, enabled: !a.enabled } : a)))
                  }
                  onDateChange={onFormDateChange}
                  patchDraft={patchFormDraft}
                  onRepeatDaysChange={setFormRepeatDays}
                  onContentChange={setFormContent}
                />
              ))}
            </>
          )}
          {tab === "time" && (
            <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
              <p className="text-lg text-slate-900">
                <span className="font-medium text-slate-600">Current time: </span>
                <span className="font-mono tabular-nums">{formatSimClock(simTimeMs)}</span>
                <span className="ml-2 text-sm font-normal text-slate-400">UTC</span>
              </p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  variant={clockEditing ? "primary" : "secondary"}
                  size="sm"
                  aria-label={clockEditing ? "Close time editor" : "Edit simulated time"}
                  aria-pressed={clockEditing}
                  onClick={() => (clockEditing ? cancelClockEdit() : openClockEdit())}
                >
                  <Pencil className="h-4 w-4" />
                  {clockEditing ? "Close" : "Edit"}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={clockEditing}
                  aria-label={running ? "Pause simulated clock" : "Run simulated clock"}
                  onClick={() => setRunning((r) => !r)}
                >
                  {running ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                  {running ? "Pause" : "Run"}
                </Button>
                <span className="text-sm text-slate-500">
                  {clockEditing
                    ? "Editing time — the clock is paused."
                    : running
                      ? "The simulated clock is running and the alarms are enabled."
                      : "The simulated clock is paused and the alarms are disabled."}
                </span>
              </div>
              {clockEditing && (
                <div className="mt-6 border-t border-slate-100 pt-6">
                  <p className="mb-3 text-sm font-medium text-slate-700">Set simulated time (UTC)</p>
                  <UtcTimeFields
                    dateInput={clockDateInput}
                    draft={clockDraft}
                    onDateChange={onClockDateChange}
                    patchDraft={patchClockDraft}
                  />
                  <div className="mt-4 flex gap-2">
                    <Button type="button" size="sm" onClick={applyClockEdit}>
                      Apply
                    </Button>
                    <Button type="button" variant="secondary" size="sm" onClick={cancelClockEdit}>
                      Cancel
                    </Button>
                  </div>
                  {clockEditError && <p className="mt-2 text-sm text-red-600">{clockEditError}</p>}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
