import clsx from "clsx";
import { History, LayoutDashboard, Loader2, Mail, Monitor, Moon, PenLine, Radar, Send, Settings, Square, Sun, Users } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import type { AppState } from "../lib/api";
import { useTasks } from "../lib/tasks";
import type { ThemeMode } from "../lib/theme";
import { Progress } from "./ui";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/discover", label: "Discover", icon: Radar },
  { to: "/pipeline", label: "Pipeline", icon: Users },
  { to: "/compose", label: "Compose", icon: PenLine },
  { to: "/send", label: "Send", icon: Send },
  { to: "/history", label: "History", icon: History },
];

function count(state: AppState | undefined, key: string) {
  const c = state?.counts ?? {};
  if (key === "/pipeline") return (c.new ?? 0) + (c.portal ?? 0) + (c.ready ?? 0);
  if (key === "/compose") return c.drafted ?? 0;
  if (key === "/send") return c.approved ?? 0;
  return 0;
}

export function Layout({ state, theme }: { state?: AppState; theme: { mode: ThemeMode; setMode: (m: ThemeMode) => void } }) {
  const { tasks, cancel } = useTasks();
  const running = Object.values(tasks).filter((t) => t.state === "running");
  const setupDone = state ? Object.values(state.checks).filter(Boolean).length : 0;

  return (
    <div className="flex h-full">
      <aside className="theme-fixed flex w-60 shrink-0 flex-col border-r border-white/5 bg-slate-950 text-slate-300">
        <div className="flex items-center gap-2.5 px-5 pb-6 pt-5">
          <div className="grid size-8 place-items-center rounded-lg bg-brand-600 text-white shadow-lg shadow-brand-600/30">
            <Mail className="size-4" />
          </div>
          <div>
            <div className="text-[15px] font-semibold text-white">Job Dedo</div>
            <div className="text-[11px] text-slate-500">Outreach that gets replies</div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map(({ to, label, icon: Icon, end }) => {
            const n = count(state, to);
            return (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                    isActive ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
                  )
                }
              >
                <Icon className="size-4" />
                <span className="flex-1">{label}</span>
                {n > 0 && <span className="rounded-full bg-brand-600/90 px-1.5 text-[11px] font-semibold text-white">{n}</span>}
              </NavLink>
            );
          })}
        </nav>

        {running.length > 0 && (
          <div className="mx-3 mb-3 space-y-3 rounded-lg bg-white/5 p-3">
            {running.map((t) => (
              <div key={t.id}>
                <div className="flex items-center gap-2 text-xs font-medium text-slate-200">
                  <Loader2 className="size-3.5 animate-spin text-brand-500" />
                  <span className="flex-1 truncate">{t.label}</span>
                  {t.kind === "send" && (
                    <button onClick={() => cancel(t.id)} title="Stop sending" className="text-slate-400 hover:text-rose-400">
                      <Square className="size-3.5" />
                    </button>
                  )}
                </div>
                <div className="mt-1 truncate text-[11px] text-slate-500">{t.message}</div>
                {t.total > 0 && <Progress value={(100 * t.done) / t.total} className="mt-2 bg-white/10" />}
              </div>
            ))}
          </div>
        )}

        <div className="border-t border-white/5 p-3">
          <NavLink
            to="/settings"
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200",
              )
            }
          >
            <Settings className="size-4" />
            <span className="flex-1">Settings</span>
            {state && setupDone < 3 && <span className="rounded-full bg-amber-500/90 px-1.5 text-[11px] font-semibold text-white">{setupDone}/3</span>}
          </NavLink>
          <div className="mt-3 grid grid-cols-3 gap-1 rounded-lg bg-white/5 p-1" role="radiogroup" aria-label="Theme">
            {(
              [
                ["light", Sun, "Light"],
                ["dark", Moon, "Dark"],
                ["system", Monitor, "System"],
              ] as const
            ).map(([m, Icon, label]) => (
              <button
                key={m}
                role="radio"
                aria-checked={theme.mode === m}
                title={`${label} theme`}
                onClick={() => theme.setMode(m)}
                className={clsx(
                  "flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[11px] font-medium transition-colors",
                  theme.mode === m ? "bg-white/15 text-white" : "text-slate-500 hover:text-slate-300",
                )}
              >
                <Icon className="size-3.5" />
                {label}
              </button>
            ))}
          </div>
          {state && (
            <div className="mt-3 px-3 text-[11px] text-slate-500">
              {state.sent_24h} / {state.profile.daily_limit} emails sent today
              <Progress value={(100 * state.sent_24h) / Math.max(1, state.profile.daily_limit)} className="mt-1.5 bg-white/10" />
            </div>
          )}
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
