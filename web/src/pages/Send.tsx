import { FlaskConical, Inbox, RotateCcw, Rocket, ShieldCheck, Square } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Badge, Button, Callout, Card, CardHeader, Checkbox, Empty, PageHeader, Progress } from "../components/ui";
import { api, type Task } from "../lib/api";
import { useAction, useAppState, useCompanies } from "../lib/hooks";
import { useTasks } from "../lib/tasks";

export default function SendPage() {
  const { data: state } = useAppState();
  const { data: companies = [] } = useCompanies();
  const { latest, track, cancel } = useTasks();
  const task = latest("send");
  const sending = task?.state === "running";

  const approved = useMemo(() => companies.filter((c) => c.status === "approved"), [companies]);
  const failed = companies.filter((c) => c.status === "failed");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => setSelected(new Set(approved.map((c) => c.id))), [approved]);

  const test = useAction(() => api.post<{ sent_to: string }>("/send/test", { company_id: [...selected][0] ?? approved[0]?.id }), (r) => `Test sent to ${r.sent_to} - check your inbox`);
  const send = useAction(() => api.post<Task>("/send", { ids: approved.filter((c) => selected.has(c.id)).map((c) => c.id) }));
  const retry = useAction(() => Promise.all(failed.map((c) => api.patch(`/companies/${c.id}`, { status: "approved" }))), "Moved back to the queue");

  if (!state) return null;
  const blockers = [!state.checks.gmail && "connect Gmail", !state.checks.resume && "upload your resume"].filter(Boolean) as string[];
  const count = Math.min(selected.size, state.allowance);

  return (
    <>
      <PageHeader title="Send" description="Emails go out from your Gmail one at a time, with a random pause between each so your account isn't flagged as spam." />

      <div className="mb-6 grid grid-cols-3 gap-4">
        {[
          ["Approved & waiting", approved.length],
          ["Sent in the last 24 h", state.sent_24h],
          ["You can still send today", state.allowance],
        ].map(([label, value]) => (
          <Card key={label} className="p-5">
            <div className="text-[13px] font-medium text-slate-500">{label}</div>
            <div className="mt-1 text-3xl font-semibold tracking-tight text-slate-900">{value}</div>
          </Card>
        ))}
      </div>

      {blockers.length > 0 && (
        <div className="mb-6">
          <Callout tone="amber">
            Before sending: {blockers.join(" and ")} in <Link to="/settings" className="font-medium underline">Settings</Link>.
          </Callout>
        </div>
      )}

      {task && (task.state === "running" || Date.now() - new Date(task.started_at).getTime() < 15 * 60_000) && (
        <Card className="mb-6 p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold text-slate-900">{task.label}</div>
              <div className="mt-0.5 text-[13px] text-slate-500">{task.state === "error" ? task.error : task.message}</div>
            </div>
            {sending ? (
              <Button variant="danger" size="sm" icon={<Square className="size-3.5" />} onClick={() => cancel(task.id)}>
                Stop
              </Button>
            ) : (
              <Badge tone={task.state === "done" ? "green" : "amber"}>{task.state === "done" ? "Finished" : task.state}</Badge>
            )}
          </div>
          <Progress value={task.total ? (100 * task.done) / task.total : 5} className="mt-4" />
          <div className="mt-2 text-xs tabular-nums text-slate-400">
            {task.done} of {task.total} processed
          </div>
        </Card>
      )}

      <Card>
        <CardHeader
          title="Send queue"
          description="Untick anything you don't want to send yet."
          action={
            approved.length > 0 && (
              <Button size="sm" icon={<FlaskConical className="size-3.5" />} loading={test.isPending} disabled={blockers.length > 0} onClick={() => test.mutate(undefined)}>
                Send a test to myself
              </Button>
            )
          }
        />
        {approved.length === 0 ? (
          <Empty icon={<Inbox className="size-5" />} title="Nothing approved yet">
            Approve drafts on the <Link to="/compose" className="font-medium text-brand-600">Compose</Link> page.
          </Empty>
        ) : (
          <>
            <ul className="divide-y divide-slate-100">
              {approved.map((c) => (
                <li key={c.id} className="flex items-center gap-4 px-5 py-3">
                  <Checkbox checked={selected.has(c.id)} onChange={(v) => setSelected((s) => (v ? new Set(s.add(c.id)) : (s.delete(c.id), new Set(s))))} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-slate-900">{c.subject}</div>
                    <div className="truncate text-[13px] text-slate-500">
                      {c.name} → {c.email}
                    </div>
                  </div>
                  <Link to="/compose" className="text-xs font-medium text-slate-400 hover:text-brand-600">
                    Edit
                  </Link>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-4 border-t border-slate-100 bg-slate-50/60 px-5 py-4">
              <label className="flex cursor-pointer items-center gap-2.5 text-[13px] text-slate-700">
                <Checkbox checked={confirmed} onChange={setConfirmed} />
                I've reviewed these emails and want to send {count} now
              </label>
              <div className="flex-1" />
              <span className="flex items-center gap-1.5 text-xs text-slate-500">
                <ShieldCheck className="size-3.5" /> {state.profile.delay_min}-{state.profile.delay_max}s between emails · never emails an address twice
              </span>
              <Button
                variant="primary"
                icon={<Rocket className="size-4" />}
                disabled={!confirmed || !count || blockers.length > 0 || sending}
                loading={send.isPending}
                onClick={() =>
                  send.mutateAsync(undefined).then((t) => {
                    track(t);
                    setConfirmed(false);
                    toast(`Sending ${count} emails - you can leave this page`);
                  })
                }
              >
                Send {count}
              </Button>
            </div>
          </>
        )}
      </Card>

      {failed.length > 0 && (
        <Card className="mt-6">
          <CardHeader
            title={`${failed.length} failed`}
            action={
              <Button size="sm" icon={<RotateCcw className="size-3.5" />} loading={retry.isPending} onClick={() => retry.mutate(undefined)}>
                Retry all
              </Button>
            }
          />
          <ul className="divide-y divide-slate-100">
            {failed.map((c) => (
              <li key={c.id} className="px-5 py-3 text-[13px]">
                <span className="font-medium text-slate-800">{c.name}</span> <span className="text-slate-500">({c.email})</span>
                <div className="text-rose-600">{c.error}</div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
