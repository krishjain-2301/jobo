import clsx from "clsx";
import { Bot, CheckCheck, ExternalLink, FileText, PenLine, Save, SkipForward, ThumbsUp } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Button, Callout, Card, Empty, Field, Input, LevelBadge, Modal, PageHeader, Score, SkillChips, STATUS, Textarea } from "../components/ui";
import { api, type Company, type Task } from "../lib/api";
import { useAction, useAppState, useCompanies } from "../lib/hooks";
import { useTasks } from "../lib/tasks";

export default function Compose() {
  const { data: companies = [] } = useCompanies();
  const { data: state } = useAppState();
  const { latest, track } = useTasks();
  const items = useMemo(
    () =>
      companies
        .filter((c) => ["ready", "drafted", "approved", "failed"].includes(c.status))
        .sort((a, b) => order(a) - order(b) || (b.match_score ?? -1) - (a.match_score ?? -1)),
    [companies],
  );
  const [activeId, setActiveId] = useState<number | null>(null);
  const [templateOpen, setTemplateOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const active = items.find((c) => c.id === activeId) ?? items.find((c) => c.status === "drafted") ?? items[0];

  const ready = items.filter((c) => c.status === "ready");
  const drafted = items.filter((c) => c.status === "drafted");
  const approveAll = useAction(() => api.post<{ approved: number }>("/companies/approve", { ids: drafted.map((c) => c.id) }), (r) => `Approved ${r.approved} drafts`);
  const aiRunning = latest("compose")?.state === "running";

  return (
    <>
      <PageHeader
        title="Compose"
        description="Every company gets its own email. Start from a template or the AI writer, then tailor each one - mention their product and the skills the role asks for."
        action={
          <>
            <Button icon={<FileText className="size-4" />} onClick={() => setTemplateOpen(true)} disabled={!ready.length}>
              Draft {ready.length || ""} from template
            </Button>
            <Button icon={<Bot className="size-4" />} onClick={() => setAiOpen(true)} disabled={!ready.length} loading={aiRunning}>
              Write with AI
            </Button>
            <Button variant="primary" icon={<CheckCheck className="size-4" />} disabled={!drafted.length} loading={approveAll.isPending} onClick={() => approveAll.mutate(undefined)}>
              {drafted.length === 1 ? "Approve 1 draft" : `Approve ${drafted.length || ""} drafts`}
            </Button>
          </>
        }
      />

      {items.length === 0 ? (
        <Card>
          <Empty icon={<PenLine className="size-5" />} title="Nothing to write yet">
            Companies show up here once they have a hiring email. Find emails on the <Link to="/pipeline" className="font-medium text-brand-600">Pipeline</Link> page.
          </Empty>
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[300px_1fr]">
          <Card className="h-fit overflow-hidden">
            <ul className="max-h-[70vh] divide-y divide-slate-100 overflow-y-auto">
              {items.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setActiveId(c.id)}
                    className={clsx(
                      "flex w-full items-center gap-3 px-4 py-3 text-left transition",
                      active?.id === c.id ? "bg-brand-50/70 shadow-[inset_3px_0_0] shadow-brand-600" : "hover:bg-slate-50",
                    )}
                  >
                    <span className={clsx("size-2 shrink-0 rounded-full", STATUS[c.status].dot)} title={STATUS[c.status].label} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-slate-800">{c.name}</div>
                      <div className="truncate text-xs text-slate-500">{c.job_title || "General enquiry"}</div>
                    </div>
                    {c.match_score != null && <span className="text-xs font-semibold tabular-nums text-slate-400">{c.match_score}</span>}
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          {active && <Editor key={active.id} company={active} pitchMissing={!state?.profile.pitch} />}
        </div>
      )}

      <TemplateModal open={templateOpen} onClose={() => setTemplateOpen(false)} ids={ready.map((c) => c.id)} sampleId={ready[0]?.id} />
      <AiModal
        open={aiOpen}
        onClose={() => setAiOpen(false)}
        ids={ready.map((c) => c.id)}
        onTask={(t) => {
          track(t);
          setAiOpen(false);
        }}
      />
    </>
  );
}

const order = (c: Company) => ({ drafted: 0, failed: 1, ready: 2, approved: 3 })[c.status as "drafted"] ?? 4;

function Editor({ company: c, pitchMissing }: { company: Company; pitchMissing: boolean }) {
  const [subject, setSubject] = useState(c.subject ?? "");
  const [body, setBody] = useState(c.body ?? "");
  useEffect(() => {
    setSubject(c.subject ?? "");
    setBody(c.body ?? "");
  }, [c.subject, c.body]);
  const save = useAction((status: string | undefined) => api.patch(`/companies/${c.id}`, { subject, body, ...(status ? { status } : {}) }));
  const words = body.trim() ? body.trim().split(/\s+/).length : 0;
  const dirty = subject !== (c.subject ?? "") || body !== (c.body ?? "");

  const act = (status: string | undefined, msg: string) => save.mutate(status, { onSuccess: () => toast.success(msg) });

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-start gap-4 border-b border-slate-100 px-5 py-4">
          <Score value={c.match_score} size={44} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[15px] font-semibold text-slate-900">{c.name}</h2>
              <LevelBadge level={c.match_level} />
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[13px] text-slate-500">
              <span>{c.job_title || "General enquiry"}</span>
              <span>→ {c.email}</span>
              {c.job_url && (
                <a href={c.job_url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-brand-600 hover:underline">
                  Posting <ExternalLink className="size-3" />
                </a>
              )}
            </div>
            {(c.matched.length > 0 || c.missing.length > 0) && (
              <div className="mt-2.5">
                <SkillChips matched={c.matched} missing={c.missing} limit={10} />
              </div>
            )}
          </div>
        </div>

        <div className="space-y-4 p-5">
          {c.status === "ready" && !c.body && (
            <Callout>
              No draft yet. Write it here, or use <b>Draft from template</b> / <b>Write with AI</b> above for all ready companies at once.
              {pitchMissing && " Tip: add a short pitch in Settings - templates use it."}
            </Callout>
          )}
          {c.error && <Callout tone="amber">{c.error}</Callout>}
          <Field label="Subject">
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Frontend Developer Internship - Your Name" />
          </Field>
          <Field label="Email" hint={`${words} words · aim for 120-200. Your resume is attached automatically.`}>
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={18} className="font-[450]" />
          </Field>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" icon={<ThumbsUp className="size-4" />} loading={save.isPending} disabled={!subject.trim() || !body.trim()} onClick={() => act("approved", "Approved - it's in the Send queue")}>
              {c.status === "approved" ? "Save" : "Save & approve"}
            </Button>
            <Button icon={<Save className="size-4" />} disabled={!dirty || !body.trim()} onClick={() => act(c.status === "ready" ? "drafted" : c.status === "approved" ? "drafted" : undefined, "Draft saved")}>
              Save draft
            </Button>
            <div className="flex-1" />
            <Button variant="ghost" icon={<SkipForward className="size-4" />} onClick={() => act("skipped", `${c.name} skipped`)}>
              Skip company
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function TemplateModal({ open, onClose, ids, sampleId }: { open: boolean; onClose: () => void; ids: number[]; sampleId?: number }) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [placeholders, setPlaceholders] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(null);
  useEffect(() => {
    if (open)
      api.get<{ subject: string; body: string; placeholders: Record<string, string> }>("/compose/template").then((t) => {
        setSubject(t.subject);
        setBody(t.body);
        setPlaceholders(t.placeholders);
      });
  }, [open]);
  useEffect(() => {
    if (!open || !body) return;
    const t = setTimeout(() => {
      api
        .post<{ subject: string; body: string }>("/compose/preview", { subject, body, company_id: sampleId })
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 300);
    return () => clearTimeout(t);
  }, [open, subject, body, sampleId]);
  const create = useAction(() => api.post<{ drafted: number }>("/compose/template", { subject, body, ids }), (r) => `Created ${r.drafted} drafts - now tailor each one`);

  return (
    <Modal open={open} onClose={onClose} title={`Draft ${ids.length === 1 ? "1 email" : `${ids.length} emails`} from a template`} wide>
      <div className="grid gap-5 md:grid-cols-2">
        <div className="space-y-4">
          <Field label="Subject">
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </Field>
          <Field label="Body">
            <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14} className="font-mono text-[13px]" />
          </Field>
          <div className="flex flex-wrap gap-1">
            {Object.entries(placeholders).map(([k, v]) => (
              <button key={k} type="button" title={v} onClick={() => setBody(body + k)} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600 hover:bg-brand-50 hover:text-brand-700">
                {k}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="mb-1.5 text-[13px] font-medium text-slate-700">Preview</div>
          <div className="h-[calc(100%-1.75rem)] rounded-lg border border-slate-200 bg-slate-50 p-4">
            {preview ? (
              <>
                <div className="mb-3 border-b border-slate-200 pb-3 text-sm font-semibold text-slate-900">{preview.subject}</div>
                <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed text-slate-700">{preview.body}</pre>
              </>
            ) : (
              <span className="text-[13px] text-slate-400">Check the template for typos in {"{placeholders}"}.</span>
            )}
          </div>
        </div>
      </div>
      <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-4">
        <p className="text-xs text-slate-500">Drafts are a starting point - edit each one before approving.</p>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={create.isPending} disabled={!preview} onClick={() => create.mutate(undefined, { onSuccess: onClose })}>
            Create {ids.length === 1 ? "draft" : `${ids.length} drafts`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function AiModal({ open, onClose, ids, onTask }: { open: boolean; onClose: () => void; ids: number[]; onTask: (t: Task) => void }) {
  const { data: state } = useAppState();
  const [instructions, setInstructions] = useState("");
  const run = useAction(() => api.post<Task>("/compose/ai", { ids, instructions }));
  if (!state) return null;
  const provider = state.profile.provider;
  const keyEnv = { "Claude (Anthropic)": "ANTHROPIC_API_KEY", OpenAI: "OPENAI_API_KEY", "Google Gemini": "GEMINI_API_KEY" }[provider] ?? "OPENAI_COMPAT_API_KEY";
  const hasKey = state.secrets[keyEnv] || state.providers[provider]?.needs_base_url;
  return (
    <Modal open={open} onClose={onClose} title={`Write ${ids.length === 1 ? "1 email" : `${ids.length} emails`} with AI`}>
      <div className="space-y-4">
        {!hasKey ? (
          <Callout tone="amber">
            Add your {provider} API key in <Link to="/settings" className="font-medium underline">Settings</Link> to use the AI writer. Gemini and Groq have free tiers.
          </Callout>
        ) : (
          <p className="text-[13px] text-slate-600">
            Using <b>{provider}</b> · {state.profile.model}. Each email is written from your resume and that company's job posting, using only facts from your resume.
          </p>
        )}
        <Field label="Extra instructions (optional)">
          <Textarea value={instructions} onChange={(e) => setInstructions(e.target.value)} rows={3} placeholder="e.g. mention I'm available for a 6-month remote internship; keep it under 150 words" />
        </Field>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" icon={<Bot className="size-4" />} loading={run.isPending} disabled={!hasKey} onClick={() => run.mutateAsync(undefined).then(onTask)}>
            Write {ids.length === 1 ? "draft" : `${ids.length} drafts`}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
