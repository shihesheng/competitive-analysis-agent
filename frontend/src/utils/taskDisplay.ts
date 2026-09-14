const TASK_DISPLAY_MAP_KEY = "taskDisplayIdMap";
const TASK_DISPLAY_COUNTER_KEY = "taskDisplayIdCounter";

function readDisplayMap(): Record<string, string> {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    return JSON.parse(
      window.sessionStorage.getItem(TASK_DISPLAY_MAP_KEY) ?? "{}",
    ) as Record<string, string>;
  } catch {
    return {};
  }
}

function writeDisplayMap(map: Record<string, string>) {
  window.sessionStorage.setItem(TASK_DISPLAY_MAP_KEY, JSON.stringify(map));
}

function readCounter() {
  const rawValue = window.sessionStorage.getItem(TASK_DISPLAY_COUNTER_KEY);
  const value = rawValue ? Number.parseInt(rawValue, 10) : 0;
  return Number.isFinite(value) ? value : 0;
}

export function getDisplayTaskId(taskId?: string | null): string | null {
  if (!taskId) {
    return null;
  }

  if (typeof window === "undefined") {
    return "TASK-001";
  }

  const displayMap = readDisplayMap();
  if (displayMap[taskId]) {
    return displayMap[taskId];
  }

  const nextCounter = readCounter() + 1;
  const displayTaskId = `TASK-${String(nextCounter).padStart(3, "0")}`;

  displayMap[taskId] = displayTaskId;
  writeDisplayMap(displayMap);
  window.sessionStorage.setItem(TASK_DISPLAY_COUNTER_KEY, String(nextCounter));

  return displayTaskId;
}
