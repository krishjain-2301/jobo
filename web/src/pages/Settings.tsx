import { CheckCircle2, ExternalLink, FileUp, KeyRound, Lock } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, CardHeader, Field, Input, PageHeader, Select, Textarea, Toggle } from "../components/ui";
import { api, type AppState, type Profile } from "../lib/api";
import { useAction, useAppState } from "../lib/hooks";

const KEY_ENV: Record<string, string> = {
  "Claude (Anthropic)": "ANTHROPIC_API_KEY",
  OpenAI: "OPENAI_API_KEY",
  "Google Gemini": "GEMINI_API_KEY",
};

export default function SettingsPage() {
  const { data: state } = useAppState();
  const [p, setP] = useState<Profile | null>(null);
  useEffect(() => {
    if (state && !p) setP(state.profile);
  }, [state, p]);
  const saveProfile = useAction((fields: Partial<Profile>) => api.put<AppState>("/profile", fields), "Settings saved");
  if (!state || !p) return null;

  const set = <K extends keyof Profile>(k: K) => (v: Profile[K]) => setP({ ...p, [k]: v });
  const text = (k: keyof Profile) => ({ value: String(p[k] ?? ""), onChange: (e: { target: { value: string } }) => setP({ ...p, [k]: e.target.value }) });
  const save = (...keys: (keyof Profile)[]) => saveProfile.mutate(Object.fromEntries(keys.map((k) => [k, p[k]])));

  return (
    <>
      <PageHeader title="Settings" description="Everything is stored on this computer only - your profile in data/, passwords and keys in .env (never committed to git)." />

      <div className="space-y-6">
        <Section
          title="About you"
          description="Used in every email signature and as context for the AI writer."
          done={state.checks.profile}
          footer={<SaveBtn onClick={() => save("name", "target_role", "phone", "linkedin", "pitch")} loading={saveProfile.isPending} />}
        >
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Full name">
              <Input {...text("name")} />
            </Field>
            <Field label="Role you're looking for" hint="Drives the suggested job keywords on Discover.">
              <Input {...text("target_role")} placeholder="e.g. Frontend Developer Intern, Data Analyst" />
            </Field>
            <Field label="Phone">
              <Input {...text("phone")} />
            </Field>
            <Field label="LinkedIn or portfolio">
              <Input {...text("linkedin")} />
            </Field>
            <Field label="Short pitch" hint="1-2 specific sentences: projects, numbers, tools. Templates insert it as {pitch}." className="md:col-span-2">
              <Textarea {...text("pitch")} rows={3} />
            </Field>
          </div>
        </Section>

        <ResumeSection state={state} />

        <GmailSection state={state} />

        <Section
          title="Sending limits"
          description="Gmail allows ~500 a day, but cold-email bursts get accounts flagged. 30-50 a day with pauses is a safe pace."
          footer={<SaveBtn onClick={() => save("daily_limit", "delay_min", "delay_max")} loading={saveProfile.isPending} />}
        >
          <div className="grid gap-4 md:grid-cols-3">
            <Field label="Max emails per 24 h">
              <Input type="number" min={1} max={200} value={p.daily_limit} onChange={(e) => set("daily_limit")(+e.target.value)} />
            </Field>
            <Field label="Min seconds between emails">
              <Input type="number" min={10} value={p.delay_min} onChange={(e) => set("delay_min")(+e.target.value)} />
            </Field>
            <Field label="Max seconds between emails">
              <Input type="number" min={10} value={p.delay_max} onChange={(e) => set("delay_max")(+e.target.value)} />
            </Field>
          </div>
        </Section>

        <AiSection state={state} p={p} setP={setP} onSave={() => save("provider", "model", "base_url")} saving={saveProfile.isPending} />

        <KeysSection state={state} />
      </div>
    </>
  );
}

function Section({ title, description, done, children, footer }: { title: string; description: string; done?: boolean; children: ReactNode; footer?: ReactNode }) {
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            {title}
            {done && <CheckCircle2 className="size-4 text-emerald-500" />}
          </span>
        }
        description={description}
      />
      <div className="p-5">{children}</div>
      {footer && <div className="flex justify-end border-t border-slate-100 bg-slate-50/50 px-5 py-3">{footer}</div>}
    </Card>
  );
}

const SaveBtn = ({ onClick, loading, label = "Save" }: { onClick: () => void; loading?: boolean; label?: string }) => (
  <Button variant="primary" size="sm" onClick={onClick} loading={loading}>
    {label}
  </Button>
);

function ResumeSection({ state }: { state: AppState }) {
  const input = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const upload = useAction((file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.post<AppState>("/resume", form);
  }, "Resume uploaded");
  const pick = (f?: File) => f && upload.mutate(f);

  return (
    <Section title="Resume" description="Attached to every email. Its skills drive the match scores on Discover." done={state.checks.resume}>
      <div
        onDragOver={(e) => (e.preventDefault(), setDrag(true))}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => (e.preventDefault(), setDrag(false), pick(e.dataTransfer.files[0]))}
        onClick={() => input.current?.click()}
        className={`flex cursor-pointer items-center gap-4 rounded-lg border-2 border-dashed px-5 py-5 transition ${drag ? "border-brand-500 bg-brand-50" : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"}`}
      >
        <div className="grid size-10 place-items-center rounded-lg bg-brand-50 text-brand-600">
          <FileUp className="size-5" />
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-slate-800">{state.resume.name ?? "Upload your resume"}</div>
          <div className="text-xs text-slate-500">{state.resume.name ? "Click or drop a file to replace it" : "PDF or DOCX - click or drag it here"}</div>
        </div>
        {upload.isPending && <span className="text-xs text-slate-500">Uploading…</span>}
        <input ref={input} type="file" accept=".pdf,.docx" hidden onChange={(e) => pick(e.target.files?.[0])} />
      </div>
      {state.resume.skills.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-400">{state.resume.skills.length} skills detected</div>
          <div className="flex flex-wrap gap-1.5">
            {state.resume.skills.map((s) => (
              <Badge key={s}>{s}</Badge>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}

function GmailSection({ state }: { state: AppState }) {
  const [address, setAddress] = useState(state.gmail_address);
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const save = useAction(
    () => api.put<AppState>("/secrets", { values: { GMAIL_ADDRESS: address, GMAIL_APP_PASSWORD: password }, remember }),
    "Gmail saved",
  );
  return (
    <Section
      title="Gmail"
      description="Emails are sent from your own Gmail account."
      done={state.checks.gmail}
      footer={<SaveBtn onClick={() => save.mutate(undefined, { onSuccess: () => setPassword("") })} loading={save.isPending} />}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Gmail address">
          <Input type="email" value={address} onChange={(e) => setAddress(e.target.value)} />
        </Field>
        <Field
          label="App Password"
          hint={
            <>
              Not your normal password - a 16-letter code from{" "}
              <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-brand-600 hover:underline">
                Google App Passwords <ExternalLink className="size-3" />
              </a>{" "}
              (needs 2-Step Verification).
            </>
          }
        >
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={state.secrets.GMAIL_APP_PASSWORD ? "•••• saved - type to replace" : "xxxx xxxx xxxx xxxx"} autoComplete="new-password" />
        </Field>
      </div>
      <div className="mt-4">
        <Toggle checked={remember} onChange={setRemember} label="Remember on this computer" description="Saves to .env so you don't re-enter it next time" />
      </div>
    </Section>
  );
}

function AiSection({ state, p, setP, onSave, saving }: { state: AppState; p: Profile; setP: (p: Profile) => void; onSave: () => void; saving: boolean }) {
  const [key, setKey] = useState("");
  const keyEnv = KEY_ENV[p.provider] ?? "OPENAI_COMPAT_API_KEY";
  const saveKey = useAction(() => api.put<AppState>("/secrets", { values: { [keyEnv]: key }, remember: true }), "API key saved");
  const info = state.providers[p.provider];
  return (
    <Section
      title="AI writer (optional)"
      description="Writes a first draft for each company from your resume and its job posting. Without a key, use templates."
      done={state.secrets[keyEnv]}
      footer={
        <SaveBtn
          onClick={() => {
            onSave();
            if (key) saveKey.mutate(undefined, { onSuccess: () => setKey("") });
          }}
          loading={saving || saveKey.isPending}
        />
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <Field label="Provider">
          <Select value={p.provider} onChange={(e) => setP({ ...p, provider: e.target.value, model: state.providers[e.target.value].models[0] })}>
            {Object.keys(state.providers).map((name) => (
              <option key={name}>{name}</option>
            ))}
          </Select>
        </Field>
        <Field label="Model">
          <Input list="models" value={p.model} onChange={(e) => setP({ ...p, model: e.target.value })} />
          <datalist id="models">
            {info?.models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </Field>
        <Field label="API key">
          <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={state.secrets[keyEnv] ? "•••• saved" : "Paste key"} autoComplete="off" />
        </Field>
        {info?.needs_base_url && (
          <Field label="Base URL" className="md:col-span-3">
            <Input value={p.base_url} onChange={(e) => setP({ ...p, base_url: e.target.value })} placeholder="https://api.groq.com/openai/v1" />
          </Field>
        )}
      </div>
    </Section>
  );
}

function KeysSection({ state }: { state: AppState }) {
  const [vals, setVals] = useState({ ADZUNA_APP_ID: "", ADZUNA_APP_KEY: "", JOOBLE_API_KEY: "", JSEARCH_API_KEY: "" });
  const save = useAction(() => api.put<AppState>("/secrets", { values: vals, remember: true }), "Keys saved");
  const field = (k: keyof typeof vals, label: string) => (
    <Field label={label}>
      <Input type="password" value={vals[k]} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} placeholder={state.secrets[k] ? "•••• saved" : ""} autoComplete="off" />
    </Field>
  );
  return (
    <Section
      title="Job board keys (optional)"
      description="Free keys. Adzuna and Jooble search Indian cities (they collect many Indeed- and Naukri-type listings); JSearch returns Google for Jobs results, which include LinkedIn, Indeed and Glassdoor postings."
      footer={
        <div className="flex w-full items-center justify-between">
          <span className="flex items-center gap-1.5 text-xs text-slate-500">
            <KeyRound className="size-3.5" />
            Free:{" "}
            <a className="text-brand-600 hover:underline" href="https://developer.adzuna.com/" target="_blank" rel="noreferrer">
              Adzuna
            </a>{" "}
            ·{" "}
            <a className="text-brand-600 hover:underline" href="https://jooble.org/api/about" target="_blank" rel="noreferrer">
              Jooble
            </a>{" "}
            ·{" "}
            <a className="text-brand-600 hover:underline" href="https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch" target="_blank" rel="noreferrer">
              JSearch
            </a>
          </span>
          <SaveBtn onClick={() => save.mutate(undefined, { onSuccess: () => (setVals({ ADZUNA_APP_ID: "", ADZUNA_APP_KEY: "", JOOBLE_API_KEY: "", JSEARCH_API_KEY: "" }), toast.success("Job boards updated")) })} loading={save.isPending} />
        </div>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        {field("ADZUNA_APP_ID", "Adzuna app ID")}
        {field("ADZUNA_APP_KEY", "Adzuna app key")}
        {field("JOOBLE_API_KEY", "Jooble API key")}
        {field("JSEARCH_API_KEY", "JSearch (RapidAPI) key")}
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
        <Lock className="size-3" /> Keys stay in .env on this computer.
      </p>
    </Section>
  );
}
