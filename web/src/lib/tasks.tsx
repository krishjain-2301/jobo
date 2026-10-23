import { useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { api, type Task } from "./api";

/** Background tasks (search, lookup, sending) keep running while you move between pages. */
interface TaskCenter {
  tasks: Record<string, Task>;
  track: (task: Task) => void;
  latest: (kind: Task["kind"]) => Task | undefined;
  cancel: (id: string) => Promise<void>;
}

const Ctx = createContext<TaskCenter | null>(null);

export function TaskProvider({ children, initial }: { children: ReactNode; initial: Task[] }) {
  const [tasks, setTasks] = useState<Record<string, Task>>({});
  const qc = useQueryClient();
  const seeded = useRef(false);

  const track = useCallback((task: Task) => setTasks((t) => ({ ...t, [task.id]: task })), []);

  useEffect(() => {
    if (!seeded.current && initial.length) {
      seeded.current = true;
      initial.forEach(track);
    }
  }, [initial, track]);

  const running = Object.values(tasks).filter((t) => t.state === "running");
  const runningKey = running.map((t) => t.id).join(",");

  useEffect(() => {
    if (!runningKey) return;
    const timer = setInterval(async () => {
      for (const id of runningKey.split(",")) {
        try {
          const next = await api.get<Task>(`/tasks/${id}`);
          setTasks((t) => ({ ...t, [id]: next }));
          if (next.state !== "running") {
            qc.invalidateQueries();
            if (next.state === "done") toast.success(next.message || `${next.label} finished`);
            if (next.state === "error") toast.error(next.error || `${next.label} failed`);
            if (next.state === "cancelled") toast(`${next.label} stopped`);
          } else if (next.kind === "send" || next.kind === "contacts") {
            qc.invalidateQueries({ queryKey: ["companies"] });
          }
        } catch {
          /* server restarting - try again next tick */
        }
      }
    }, 1000);
    return () => clearInterval(timer);
  }, [runningKey, qc]);

  const latest = useCallback(
    (kind: Task["kind"]) =>
      Object.values(tasks)
        .filter((t) => t.kind === kind)
        .sort((a, b) => (a.started_at < b.started_at ? 1 : -1))[0],
    [tasks],
  );

  const cancel = useCallback(
    async (id: string) => {
      track(await api.post<Task>(`/tasks/${id}/cancel`));
    },
    [track],
  );

  return <Ctx.Provider value={{ tasks, track, latest, cancel }}>{children}</Ctx.Provider>;
}

export function useTasks() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useTasks outside TaskProvider");
  return ctx;
}
