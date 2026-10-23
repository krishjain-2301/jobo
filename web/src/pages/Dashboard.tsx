import clsx from "clsx";
import { ArrowRight, CheckCircle2, Circle, Inbox, Radar, Send, Sparkles, Target } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, Card, CardHeader, Empty, LevelBadge, PageHeader, Score, STATUS, StatusBadge } from "../components/ui";
import type { Status } from "../lib/api";
import { daysSince, timeAgo, useAppState, useCompanies, useHistory } from "../lib/hooks";

const FUNNEL: Status[] = ["portal", "new", "no_email", "ready", "drafted", "approved", "sent", "applied"];

export default function Dashboard() {
  const { data: state } = useAppState();
  const { data: companies = [] } = useCompanies();
  const { data: history = [] } = useHistory();
  if (!state) return null;

  const firstName = state.profile.name.split(" ")[0];
  const checks = [
    { ok: state.checks.profile, label: "Add your name and target role", to: "/settings" },
    { ok: state.checks.resume, label: "Upload your resume", to: "/settings" },
    { ok: state.checks.gmail, label: "Connect Gmail with an App Password", to: "/settings" },
  ];
  const setupDone = checks.every((c) => c.ok);
  const active = companies.filter((c) => !["sent", "applied", "skipped"].includes(c.status));
  const topMatches = [...active].sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1)).slice(0, 5);
  const followUps = history.filter((h) => daysSince(h.sent_at) >= 7).length;
  const total = companies.length || 1;

  const next = !setupDone
    ? { text: "Finish setting up your account", to: "/settings" }
    : (state.counts.approved ?? 0) > 0
      ? { text: `Send ${state.counts.approved} approved emails`, to: "/send" }
      : (state.counts.drafted ?? 0) > 0
        ? { text: `Review ${state.counts.drafted} drafts`, to: "/compose" }
        : (state.counts.ready ?? 0) > 0
          ? { text: `Write emails for ${state.counts.ready} companies`, to: "/compose" }
          : (state.counts.new ?? 0) > 0
            ? { text: `Find hiring emails for ${state.counts.new} companies`, to: "/pipeline" }
            : (state.counts.portal ?? 0) > 0
              ? { text: `Apply to ${state.counts.portal} roles on their company sites`, to: "/pipeline" }
              : { text: "Discover new matching jobs", to: "/discover" };

  const stats = [
    { label: "In pipeline", value: active.length, icon: Target, hint: "companies you're tracking" },
    { label: "Ready to send", value: state.counts.approved ?? 0, icon: Sparkles, hint: "approved emails" },
    { label: "Applications", value: state.sent_total + (state.counts.applied ?? 0), icon: Send, hint: `${state.sent_total} by email · ${state.counts.applied ?? 0} on company sites` },
    { label: "Left today", value: state.allowance, icon: Inbox, hint: `daily limit ${state.profile.daily_limit}` },
  ];

  return (
    <>
      <PageHeader
        title={firstName ? `Welcome back, ${firstName}` : "Welcome"}
        description="Find roles that fit your resume, reach the right inbox, and keep every application on track."
      />

      <Link
        to={next.to}
        className="group mb-6 flex items-center justify-between rounded-xl bg-gradient-to-r from-brand-600 to-indigo-500 px-6 py-5 text-white shadow-lg shadow-brand-600/20"
      >
        <div>
          <div className="text-xs font-medium uppercase tracking-wider text-white/70">Next step</div>
          <div className="mt-1 text-lg font-semibold">{next.text}</div>
        </div>
        <ArrowRight className="size-5 transition-transform group-hover:translate-x-1" />
      </Link>

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map(({ label, value, icon: Icon, hint }) => (
          <Card key={label} className="p-5">
            <div className="flex items-center justify-between">
              <span className="text-[13px] font-medium text-slate-500">{label}</span>
              <Icon className="size-4 text-slate-400" />
            </div>
            <div className="mt-2 text-3xl font-semibold tracking-tight text-slate-900">{value}</div>
            <div className="mt-1 text-xs text-slate-400">{hint}</div>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="Best matches in your pipeline"
              description="Scored against your resume - higher means more of the job's skills are on your resume."
              action={
                <Link to="/pipeline" className="text-[13px] font-medium text-brand-600 hover:text-brand-700">
                  View all
                </Link>
              }
            />
            {topMatches.length === 0 ? (
              <Empty icon={<Radar className="size-5" />} title="No companies yet">
                Head to <Link to="/discover" className="font-medium text-brand-600">Discover</Link> to scan career pages for roles that fit you.
              </Empty>
            ) : (
              <ul className="divide-y divide-slate-100">
                {topMatches.map((c) => (
                  <li key={c.id} className="flex items-center gap-4 px-5 py-3.5">
                    <Score value={c.match_score} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-slate-900">{c.job_title || "General enquiry"}</div>
                      <div className="truncate text-[13px] text-slate-500">
                        {c.name}
                        {c.location ? ` · ${c.location}` : ""}
                      </div>
                    </div>
                    <LevelBadge level={c.match_level} />
                    <StatusBadge status={c.status} />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <CardHeader title="Pipeline" description="Where each company is in the process." />
            <div className="space-y-3 px-5 py-4">
              {FUNNEL.map((s) => {
                const n = state.counts[s] ?? 0;
                return (
                  <div key={s} className="flex items-center gap-3">
                    <span className="w-32 text-[13px] text-slate-600">{STATUS[s].label}</span>
                    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <div className={clsx("h-full rounded-full", STATUS[s].dot)} style={{ width: `${(100 * n) / total}%` }} />
                    </div>
                    <span className="w-8 text-right text-[13px] font-medium tabular-nums text-slate-700">{n}</span>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          {!setupDone && (
            <Card>
              <CardHeader title="Get set up" description="One-time setup before your first send." />
              <ul className="space-y-1 p-3">
                {checks.map((c) => (
                  <li key={c.label}>
                    <Link to={c.to} className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-slate-50">
                      {c.ok ? <CheckCircle2 className="size-4 text-emerald-500" /> : <Circle className="size-4 text-slate-300" />}
                      <span className={c.ok ? "text-slate-400 line-through" : "text-slate-700"}>{c.label}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHeader
              title="Recent applications"
              action={followUps > 0 && <Badge tone="amber">{followUps} to follow up</Badge>}
            />
            {history.length === 0 ? (
              <Empty icon={<Send className="size-5" />} title="Nothing sent yet" />
            ) : (
              <ul className="divide-y divide-slate-100">
                {history.slice(0, 6).map((h) => (
                  <li key={h.id} className="px-5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-medium text-slate-800">{h.company}</span>
                      <span className="shrink-0 text-xs text-slate-400">{timeAgo(h.sent_at)}</span>
                    </div>
                    <div className="truncate text-xs text-slate-500">{h.email}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {state.resume.skills.length > 0 && (
            <Card>
              <CardHeader title="Skills found in your resume" description="These drive the match scores." />
              <div className="flex flex-wrap gap-1.5 p-5">
                {state.resume.skills.map((s) => (
                  <Badge key={s}>{s}</Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
