import clsx from "clsx";
import { Check, ChevronDown, ChevronRight, Download, ExternalLink, Globe, Plus, Search, Trash2, Users } from "lucide-react";
import { Fragment, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Button,
  Callout,
  Card,
  Checkbox,
  Empty,
  ExtLink,
  Field,
  Input,
  LevelBadge,
  Modal,
  PageHeader,
  Score,
  SkillChips,
  StatusBadge,
} from "../components/ui";
import { api, type Company, type Status, type Task } from "../lib/api";
import { useAction, useCompanies } from "../lib/hooks";
import { useTasks } from "../lib/tasks";

const FILTERS: { key: string; label: string; statuses: Status[] | null }[] = [
  { key: "all", label: "All", statuses: null },
  { key: "portal", label: "Apply on site", statuses: ["portal"] },
  { key: "email", label: "Needs email", statuses: ["new", "no_email"] },
  { key: "ready", label: "Ready to write", statuses: ["ready"] },
  { key: "drafted", label: "Drafts", statuses: ["drafted", "approved"] },
  { key: "sent", label: "Sent / applied", statuses: ["sent", "applied"] },
  { key: "other", label: "Skipped / failed", statuses: ["skipped", "failed"] },
];

export default function Pipeline() {
  const { data: companies = [], isLoading } = useCompanies();
  const { latest, track } = useTasks();
  const lookupTask = latest("contacts");
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [open, setOpen] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);

  const rows = useMemo(() => {
    const f = FILTERS.find((x) => x.key === filter)!;
    const needle = q.toLowerCase();
    return companies
      .filter((c) => !f.statuses || f.statuses.includes(c.status))
      .filter((c) => !needle || `${c.name} ${c.job_title} ${c.email}`.toLowerCase().includes(needle))
      .sort((a, b) => (b.match_score ?? -1) - (a.match_score ?? -1));
  }, [companies, filter, q]);

  const needEmail = companies.filter((c) => c.status === "new").length;
  const noEmail = companies.filter((c) => c.status === "no_email").length;
  const lookup = useAction((body: { ids?: number[]; include_no_email?: boolean }) => api.post<Task>("/contacts/lookup", body));
  const remove = useAction((ids: number[]) => api.post<{ deleted: number }>("/companies/delete", { ids }), (r) => `Removed ${r.deleted}`);
  const lookingUp = lookupTask?.state === "running";

  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id));
  const toggle = (id: number) => setSelected((s) => (s.has(id) ? (s.delete(id), new Set(s)) : new Set(s.add(id))));

  return (
    <>
      <PageHeader
        title="Pipeline"
        description="Every company you're tracking. Find each one's hiring email, check it, then move on to Compose."
        action={
          <>
            <a href="/api/export/companies.csv">
              <Button icon={<Download className="size-4" />}>Export</Button>
            </a>
            <Button icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>
              Add company
            </Button>
            <Button
              variant="primary"
              icon={<Globe className="size-4" />}
              loading={lookingUp || lookup.isPending}
              disabled={!needEmail && !noEmail}
              onClick={() => lookup.mutateAsync({ include_no_email: !needEmail }).then(track)}
            >
              {needEmail ? `Find emails for ${needEmail}` : noEmail ? `Retry ${noEmail} without email` : "Find emails"}
            </Button>
          </>
        }
      />

      {lookingUp && (
        <div className="mb-4">
          <Callout>
            {lookupTask.message} ({lookupTask.done}/{lookupTask.total}) - visiting each company's website for careers@, hiring@, jobs@ addresses…
          </Callout>
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3">
          <div className="flex flex-wrap gap-1">
            {FILTERS.map((f) => {
              const n = f.statuses ? companies.filter((c) => f.statuses!.includes(c.status)).length : companies.length;
              return (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={clsx(
                    "rounded-md px-2.5 py-1 text-[13px] font-medium transition",
                    filter === f.key ? "bg-brand-600 text-white" : "text-slate-500 hover:bg-slate-100 hover:text-slate-800",
                  )}
                >
                  {f.label} <span className={filter === f.key ? "text-white/60" : "text-slate-400"}>{n}</span>
                </button>
              );
            })}
          </div>
          <div className="flex-1" />
          {selected.size > 0 && (
            <Button size="sm" variant="danger" icon={<Trash2 className="size-3.5" />} onClick={() => remove.mutate([...selected], { onSuccess: () => setSelected(new Set()) })}>
              Remove {selected.size}
            </Button>
          )}
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-slate-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search" className="h-9 w-56 pl-8" />
          </div>
        </div>

        {isLoading ? null : rows.length === 0 ? (
          <Empty icon={<Users className="size-5" />} title={companies.length ? "Nothing in this view" : "Your pipeline is empty"}>
            {companies.length ? "Try another filter." : "Use Discover to find matching jobs, or add a company yourself."}
          </Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                  <th className="w-10 px-4 py-2.5">
                    <Checkbox
                      checked={allSelected}
                      indeterminate={!allSelected && rows.some((r) => selected.has(r.id))}
                      onChange={(v) => setSelected(v ? new Set(rows.map((r) => r.id)) : new Set())}
                    />
                  </th>
                  <th className="px-2 py-2.5 font-medium">Match</th>
                  <th className="px-3 py-2.5 font-medium">Company & role</th>
                  <th className="px-3 py-2.5 font-medium">How to apply</th>
                  <th className="px-3 py-2.5 font-medium">Status</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((c) => (
                  <Fragment key={c.id}>
                    <tr className={clsx("cursor-pointer hover:bg-slate-50/70", open === c.id && "bg-slate-50/70")} onClick={() => setOpen(open === c.id ? null : c.id)}>
                      <td className="px-4 py-3">
                        <Checkbox checked={selected.has(c.id)} onChange={() => toggle(c.id)} />
                      </td>
                      <td className="px-2 py-3">
                        <Score value={c.match_score} size={36} />
                      </td>
                      <td className="max-w-xs px-3 py-3">
                        <div className="truncate font-medium text-slate-900">{c.name}</div>
                        <div className="flex items-center gap-2 truncate text-[13px] text-slate-500">
                          <span className="truncate">{c.job_title || "General enquiry"}</span>
                          <LevelBadge level={c.match_level} />
                        </div>
                      </td>
                      <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                        <EmailCell company={c} />
                      </td>
                      <td className="px-3 py-3">
                        <StatusBadge status={c.status} />
                      </td>
                      <td className="pr-4 text-slate-400">{open === c.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}</td>
                    </tr>
                    {open === c.id && (
                      <tr className="bg-slate-50/70">
                        <td />
                        <td colSpan={5} className="px-3 pb-5 pt-1">
                          <Details company={c} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <AddCompany open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

function EmailCell({ company }: { company: Company }) {
  const [value, setValue] = useState(company.email ?? "");
  const [manual, setManual] = useState(false);
  const save = useAction((email: string) => api.patch(`/companies/${company.id}`, { email }), "Email saved");
  const mark = useAction(() => api.patch(`/companies/${company.id}`, { status: "applied" }), `${company.name} marked as applied`);
  const { track } = useTasks();
  const find = useAction(() => api.post<Task>("/contacts/lookup", { ids: [company.id] }));

  if ((company.status === "portal" || company.status === "applied") && !manual) {
    return (
      <div className="flex items-center gap-2">
        {company.job_url && (
          <a href={company.job_url} target="_blank" rel="noreferrer">
            <Button size="sm" variant={company.status === "portal" ? "primary" : "secondary"} icon={<ExternalLink className="size-3.5" />}>
              Apply on site
            </Button>
          </a>
        )}
        {company.status === "portal" && (
          <>
            <Button size="sm" icon={<Check className="size-3.5" />} loading={mark.isPending} onClick={() => mark.mutate(undefined)}>
              Mark applied
            </Button>
            <button
              className="text-xs text-slate-400 hover:text-brand-600"
              title="Small startups often read email - look up a hiring address or type one"
              onClick={() => (setManual(true), find.mutateAsync(undefined).then(track))}
            >
              or email
            </button>
          </>
        )}
      </div>
    );
  }
  const locked = company.status === "sent";
  const commit = () => value.trim() !== (company.email ?? "") && save.mutate(value.trim());
  const options = company.emails.filter((e) => e !== company.email);
  return (
    <div className="flex items-center gap-1.5">
      <input
        value={value}
        disabled={locked}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        placeholder={company.status === "new" ? "not looked up yet" : "add an email"}
        className="h-8 w-60 rounded-md border border-transparent bg-transparent px-2 text-[13px] text-slate-700 placeholder:text-slate-400 hover:border-slate-200 focus:border-brand-500 focus:bg-surface focus:outline-none disabled:hover:border-transparent"
      />
      {options.length > 0 && !locked && (
        <select
          value=""
          onChange={(e) => (setValue(e.target.value), save.mutate(e.target.value))}
          className="h-7 w-7 cursor-pointer appearance-none rounded border border-slate-200 bg-surface text-center text-[11px] text-slate-500"
          title={`${options.length} other addresses found`}
        >
          <option value="">+{options.length}</option>
          {options.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}

function Details({ company: c }: { company: Company }) {
  return (
    <div className="grid gap-5 rounded-lg border border-slate-200 bg-surface p-4 md:grid-cols-2">
      <div className="space-y-3">
        <div>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-400">Skills</div>
          {c.matched.length || c.missing.length ? (
            <SkillChips matched={c.matched} missing={c.missing} limit={12} />
          ) : (
            <span className="text-[13px] text-slate-400">No posting to compare against</span>
          )}
          {c.missing.length > 0 && (
            <p className="mt-2 text-xs text-slate-500">
              <span className="font-medium text-amber-700">+ amber</span> skills appear in the posting but not on your resume. If you have them, add them to your resume before applying.
            </p>
          )}
        </div>
        {c.error && <Callout tone="amber">{c.error}</Callout>}
      </div>
      <div className="space-y-1.5 text-[13px]">
        {[
          ["Job posting", c.job_url],
          ["Careers page", c.careers_url],
          ["Website", c.website],
        ].map(([label, url]) => (
          <div key={label} className="flex gap-3">
            <span className="w-24 shrink-0 text-slate-400">{label}</span>
            {url ? <ExtLink href={url}>{url.replace(/^https?:\/\//, "").slice(0, 60)}</ExtLink> : <span className="text-slate-300">–</span>}
          </div>
        ))}
        <div className="flex gap-3">
          <span className="w-24 shrink-0 text-slate-400">Location</span>
          <span className="text-slate-600">{c.location || "–"}</span>
        </div>
        <div className="flex gap-3">
          <span className="w-24 shrink-0 text-slate-400">Source</span>
          <span className="text-slate-600">{c.source || "–"}</span>
        </div>
        {c.status === "no_email" && (
          <p className="pt-2 text-xs text-slate-500">No public email found - apply through the job posting or careers page instead.</p>
        )}
      </div>
    </div>
  );
}

function AddCompany({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form, setForm] = useState({ name: "", website: "", email: "", job_title: "", job_url: "" });
  const add = useAction(() => api.post("/companies", form));
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  return (
    <Modal open={open} onClose={onClose} title="Add a company">
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(undefined, {
            onSuccess: () => {
              toast.success(`${form.name} added`);
              setForm({ name: "", website: "", email: "", job_title: "", job_url: "" });
              onClose();
            },
          });
        }}
      >
        <Field label="Company name">
          <Input value={form.name} onChange={set("name")} required autoFocus />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Website">
            <Input value={form.website} onChange={set("website")} placeholder="https://" />
          </Field>
          <Field label="Hiring email" hint="Leave empty to look it up">
            <Input value={form.email} onChange={set("email")} type="email" placeholder="careers@…" />
          </Field>
          <Field label="Role">
            <Input value={form.job_title} onChange={set("job_title")} placeholder="e.g. Frontend Intern" />
          </Field>
          <Field label="Job posting link">
            <Input value={form.job_url} onChange={set("job_url")} placeholder="https://" />
          </Field>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={add.isPending}>
            Add company
          </Button>
        </div>
      </form>
    </Modal>
  );
}
