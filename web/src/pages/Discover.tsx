import clsx from "clsx";
import { BellRing, Briefcase, Building2, ExternalLink, Eye, EyeOff, Globe2, Inbox, Plus, Radar, RefreshCw, Search, SlidersHorizontal, Sparkles, Telescope, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  Empty,
  Field,
  Input,
  LevelBadge,
  PageHeader,
  Progress,
  Score,
  Select,
  SkillChips,
  Toggle,
} from "../components/ui";
import { api, type DiscoveredBoard, type DiscoverResult, type JobResult, type Task } from "../lib/api";
import { timeAgo, useAction, useAppState, useSaveProfile, useWatchlist } from "../lib/hooks";
import { useTasks } from "../lib/tasks";

const ATS_LABEL = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workable: "Workable",
  smartrecruiters: "SmartRecruiters",
  workday: "Workday",
  recruitee: "Recruitee",
  personio: "Personio",
};
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString()} ${n === 1 ? one : many}`;

export default function Discover() {
  const [tab, setTab] = useState<"careers" | "boards" | "alerts">("careers");
  const { latest, track } = useTasks();
  const task = latest("discover");
  const running = task?.state === "running";

  return (
    <>
      <PageHeader
        title="Discover"
        description="Scan company career pages directly and score every opening against your resume. Only roles that fit get added to your pipeline."
      />

      <FilterBar />

      <div className="mb-4 inline-flex rounded-lg bg-slate-200/60 p-1">
        {(
          [
            ["careers", "Career pages", Building2],
            ["boards", "Job boards", Globe2],
            ["alerts", "Job alerts", BellRing],
          ] as const
        ).map(([key, label, Icon]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={clsx(
              "flex items-center gap-2 rounded-md px-4 py-1.5 text-sm font-medium transition",
              tab === key ? "bg-surface text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700",
            )}
          >
            <Icon className="size-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === "careers" && (
        <>
          <CareerPages running={running} onTask={track} />
          <WebFinder onTask={track} />
        </>
      )}
      {tab === "boards" && <JobBoards running={running} onTask={track} />}
      {tab === "alerts" && <JobAlerts running={running} onTask={track} />}

      {task && <Results task={task} />}
    </>
  );
}

// ---------------------------------------------------------------- filters
function FilterBar() {
  const { data: state } = useAppState();
  const save = useSaveProfile();
  const [keywords, setKeywords] = useState("");
  const [minMatch, setMinMatch] = useState(40);
  useEffect(() => {
    if (state) {
      setKeywords(state.profile.keywords);
      setMinMatch(state.profile.min_match);
    }
  }, [state]);
  if (!state) return null;
  const dirty = keywords !== state.profile.keywords || minMatch !== state.profile.min_match;

  return (
    <Card className="mb-6">
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <SlidersHorizontal className="size-4 text-slate-400" /> What counts as a match
          </span>
        }
        description="Used for every scan and search. A job must mention one of your keywords in its title (or several in its description)."
        action={
          dirty && (
            <Button size="sm" variant="primary" loading={save.isPending} onClick={() => save.mutate({ keywords, min_match: minMatch })}>
              Save filters
            </Button>
          )
        }
      />
      <div className="grid gap-5 px-5 py-4 md:grid-cols-[1fr_220px_260px]">
        <Field
          label="Role keywords"
          hint={
            state.suggested_keywords && keywords !== state.suggested_keywords ? (
              <>
                Suggested for “{state.profile.target_role}”:{" "}
                <button type="button" className="font-medium text-brand-600 hover:underline" onClick={() => setKeywords(state.suggested_keywords)}>
                  use {state.suggested_keywords.split(",").length} suggested keywords
                </button>
              </>
            ) : (
              "Comma separated job titles or topics, e.g. frontend, react, web developer"
            )
          }
        >
          <Input value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder="Set your target role in Settings to get suggestions" />
        </Field>
        <Field label={`Minimum match: ${minMatch}%`} hint="Share of the job's skills on your resume">
          <input type="range" min={0} max={90} step={5} value={minMatch} onChange={(e) => setMinMatch(+e.target.value)} className="mt-2 w-full accent-brand-600" />
        </Field>
        <div className="pt-6">
          <Toggle
            checked={state.profile.fresher_only}
            onChange={(v) => save.mutate({ fresher_only: v })}
            label="Fresher-friendly only"
            description="Hide mid-level and senior roles (2+ years)"
          />
        </div>
      </div>
      {state.resume.skills.length === 0 && (
        <div className="px-5 pb-4">
          <Callout tone="amber">Upload your resume in Settings - match scores are calculated from the skills on it.</Callout>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- career pages
function CareerPages({ running, onTask }: { running: boolean; onTask: (t: Task) => void }) {
  const { data: watch = [], isLoading } = useWatchlist();
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");

  const add = useAction(
    () => api.post<{ name: string; jobs: number; ats: keyof typeof ATS_LABEL }>("/watchlist", { url, name }),
    (r) => `${r.name} added - ${r.jobs} open jobs on ${ATS_LABEL[r.ats]}`,
  );
  const { data: appState } = useAppState();
  const starter = useAction((list: string) => api.post<{ added: number }>("/watchlist/starter", { list }), (r) => `Added ${r.added} companies`);
  const starterButtons = Object.entries(appState?.starter_lists ?? {}).map(([key, s]) => (
    <Button key={key} size="sm" icon={<Sparkles className="size-3.5" />} loading={starter.isPending && starter.variables === key} onClick={() => starter.mutate(key)}>
      {s.label} ({s.count})
    </Button>
  ));
  const remove = useAction((id: number) => api.del(`/watchlist/${id}`));
  const scan = useAction((ids: number[]) => api.post<Task>("/discover/scan", { ids }));

  const runScan = (ids: number[] = []) => scan.mutateAsync(ids).then(onTask);

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
      <Card>
        <CardHeader
          title="Watchlist"
          description="Companies whose career pages you track. Each scan reads every open job on their board."
          action={
            <Button variant="primary" icon={<Radar className="size-4" />} loading={running || scan.isPending} disabled={!watch.length} onClick={() => runScan()}>
              Scan all
            </Button>
          }
        />
        {isLoading ? null : watch.length === 0 ? (
          <Empty icon={<Building2 className="size-5" />} title="Your watchlist is empty">
            Add a company's careers page on the right, find companies with “Find more companies on the web” below, or start from a ready-made list. Scans keep only the jobs that match your keywords.
            <div className="mt-4 flex flex-wrap justify-center gap-2">{starterButtons}</div>
          </Empty>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                <th className="px-5 py-2.5 font-medium">Company</th>
                <th className="px-3 py-2.5 font-medium">Board</th>
                <th className="px-3 py-2.5 text-right font-medium">Open jobs</th>
                <th className="px-3 py-2.5 text-right font-medium">Matches</th>
                <th className="px-3 py-2.5 font-medium">Scanned</th>
                <th className="w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {watch.map((w) => (
                <tr key={w.id} className="group hover:bg-slate-50/60">
                  <td className="px-5 py-3">
                    <div className="font-medium text-slate-800">{w.name}</div>
                    {w.error && <div className="truncate text-xs text-rose-600">{w.error}</div>}
                  </td>
                  <td className="px-3 py-3">
                    <Badge>{ATS_LABEL[w.ats]}</Badge>
                  </td>
                  <td className="px-3 py-3 text-right tabular-nums text-slate-600">{w.jobs_total ?? "–"}</td>
                  <td className="px-3 py-3 text-right tabular-nums">
                    {w.jobs_matched == null ? (
                      <span className="text-slate-400">–</span>
                    ) : (
                      <span className={w.jobs_matched ? "font-semibold text-emerald-600" : "text-slate-400"}>{w.jobs_matched}</span>
                    )}
                  </td>
                  <td className="px-3 py-3 text-xs text-slate-500">{timeAgo(w.last_scanned)}</td>
                  <td className="px-3 py-3">
                    <div className="flex justify-end gap-1 opacity-0 transition group-hover:opacity-100">
                      <button title="Scan" disabled={running} onClick={() => runScan([w.id])} className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-brand-600">
                        <RefreshCw className="size-3.5" />
                      </button>
                      <button title="Remove" onClick={() => remove.mutate(w.id)} className="rounded p-1.5 text-slate-400 hover:bg-rose-50 hover:text-rose-600">
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card className="h-fit">
        <CardHeader title="Add a company" description="Paste its careers page or any job link." />
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            add.mutate(undefined, { onSuccess: () => (setUrl(""), setName("")) });
          }}
        >
          <Field label="Careers page or job link">
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://jobs.lever.co/company" required />
          </Field>
          <Field label="Company name" hint="Optional - detected from the board when left empty">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Acme AI" />
          </Field>
          <Button type="submit" variant="primary" className="w-full" icon={<Plus className="size-4" />} loading={add.isPending}>
            Add to watchlist
          </Button>
          {watch.length > 0 && (
            <div className="space-y-2 border-t border-slate-100 pt-4">
              <div className="text-xs font-medium text-slate-500">Or add a ready-made list</div>
              <div className="flex flex-wrap gap-2">{starterButtons}</div>
            </div>
          )}
          <p className="text-xs leading-relaxed text-slate-500">
            Works with Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Workday, Recruitee and Personio, which covers most startups and many large employers. If a careers page isn't detected, open any job on it and paste that link.
          </p>
        </form>
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------- job boards
function JobBoards({ running, onTask }: { running: boolean; onTask: (t: Task) => void }) {
  const { data: state } = useAppState();
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState("");
  const [country, setCountry] = useState("India");
  const [sources, setSources] = useState<string[] | null>(null);
  const search = useAction(() => api.post<Task>("/discover/boards", { query, location, country, sources: sources ?? state?.boards ?? [], limit: 100 }));
  useEffect(() => {
    if (state && !query) setQuery(state.profile.target_role);
  }, [state]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!state) return null;
  const active = sources ?? state.boards;
  const local = state.boards.includes("Adzuna") || state.boards.includes("Jooble");

  return (
    <Card>
      <CardHeader title="Search job boards" description="Results are scored and filtered the same way as career-page scans." />
      <form
        className="space-y-4 p-5"
        onSubmit={(e) => {
          e.preventDefault();
          search.mutateAsync(undefined).then(onTask);
        }}
      >
        <div className="grid gap-4 md:grid-cols-[2fr_1.5fr_1fr]">
          <Field label="Job title or keywords">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. frontend developer intern" required />
          </Field>
          <Field label="Location" hint={local ? undefined : "Needs an Adzuna or Jooble key"}>
            <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. Hyderabad" disabled={!local} />
          </Field>
          <Field label="Country">
            <Select value={country} onChange={(e) => setCountry(e.target.value)} disabled={!state.boards.includes("Adzuna")}>
              {state.countries.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </Select>
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {state.boards.map((b) => (
            <button
              type="button"
              key={b}
              onClick={() => setSources(active.includes(b) ? active.filter((x) => x !== b) : [...active, b])}
              className={clsx(
                "rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset transition",
                active.includes(b) ? "bg-brand-50 text-brand-700 ring-brand-200" : "bg-surface text-slate-500 ring-slate-200",
              )}
            >
              {b}
            </button>
          ))}
          <div className="flex-1" />
          <Button type="submit" variant="primary" icon={<Search className="size-4" />} loading={running || search.isPending} disabled={!active.length}>
            Search
          </Button>
        </div>
        {!local && (
          <Callout tone="amber">
            Remotive, RemoteOK and Arbeitnow only list remote jobs and have very few security roles. For jobs in Indian cities, add a free Adzuna or Jooble key in Settings - or use Career pages, which works best for niche roles.
          </Callout>
        )}
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------- results
function Results({ task }: { task: Task }) {
  const [showHidden, setShowHidden] = useState(false);
  const result = task.result as unknown as DiscoverResult;
  const jobs = useMemo(() => (result?.jobs ?? []).filter((j) => showHidden || j.passed), [result, showHidden]);

  if (task.state === "running") {
    return (
      <Card className="mt-6 p-6">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium text-slate-700">{task.message}</span>
          {task.total > 0 && (
            <span className="tabular-nums text-slate-400">
              {task.done}/{task.total}
            </span>
          )}
        </div>
        <Progress value={task.total ? (100 * task.done) / task.total : 10} className="mt-3" />
      </Card>
    );
  }
  if (task.state === "error") return <Callout tone="amber">{task.error}</Callout>;
  if (!result?.jobs) return null;

  return (
    <Card className="mt-6">
      <CardHeader
        title={`${plural(result.passed, "matching job")} at ${plural(result.companies, "company", "companies")}`}
        description={`${result.providers ? `Read ${plural(Object.values(result.providers).reduce((a, b) => a + b, 0), "alert email")} · ` : ""}Scanned ${plural(result.found, "opening")} · ${plural(result.added, "new company", "new companies")} added to your pipeline${result.updated ? ` · ${result.updated} updated with a better-fitting role` : ""}`}
        action={
          <Button size="sm" variant="ghost" icon={showHidden ? <EyeOff className="size-4" /> : <Eye className="size-4" />} onClick={() => setShowHidden(!showHidden)}>
            {showHidden ? "Hide filtered" : `Show ${result.found - result.passed > 300 ? "top" : ""} filtered`}
          </Button>
        }
      />
      {Object.keys(result.errors ?? {}).length > 0 && (
        <div className="px-5 pt-4">
          <Callout tone="amber">
            {Object.entries(result.errors).map(([k, v]) => (
              <div key={k}>
                <b>{k}:</b> {v}
              </div>
            ))}
          </Callout>
        </div>
      )}
      {jobs.length === 0 ? (
        <Empty icon={<Briefcase className="size-5" />} title="No jobs passed your filters">
          Try lowering the minimum match, adding keywords, or turning off "Fresher-friendly only".
        </Empty>
      ) : (
        <ul className="divide-y divide-slate-100">
          {jobs.map((j, i) => (
            <JobRow key={`${j.company}-${j.title}-${i}`} job={j} />
          ))}
        </ul>
      )}
    </Card>
  );
}

const OUTCOME: Record<JobResult["status"], { label: string; tone: "green" | "brand" | "slate" }> = {
  added: { label: "Added to pipeline", tone: "green" },
  updated: { label: "Updated in pipeline", tone: "brand" },
  kept: { label: "Already in pipeline", tone: "slate" },
  other: { label: "Better role at this company added", tone: "slate" },
  hidden: { label: "Filtered out", tone: "slate" },
};

function JobRow({ job }: { job: JobResult }) {
  const [added, setAdded] = useState(false);
  const addAnyway = useAction(() => api.post<{ status: string }>("/discover/add", job));
  const outcome = OUTCOME[job.status];
  return (
    <li className={clsx("flex gap-4 px-5 py-4", !job.passed && "bg-slate-50/50")}>
      <Score value={job.score} size={44} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <a href={job.url} target="_blank" rel="noreferrer" className="font-medium text-slate-900 hover:text-brand-600">
            {job.title}
          </a>
          <LevelBadge level={job.level} />
        </div>
        <div className="mt-0.5 text-[13px] text-slate-500">
          {job.company}
          {job.location ? ` · ${job.location}` : ""} · {job.source}
        </div>
        <div className="mt-2">
          <SkillChips matched={job.matched} missing={job.missing} />
        </div>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-2">
        {job.passed || added ? (
          <Badge tone={added ? "green" : outcome.tone}>{added ? "Added to pipeline" : outcome.label}</Badge>
        ) : (
          <Button
            size="sm"
            icon={<Plus className="size-3.5" />}
            loading={addAnyway.isPending}
            onClick={() =>
              addAnyway.mutate(undefined, {
                onSuccess: (r) => {
                  setAdded(true);
                  toast.success(r.status === "kept" ? `${job.company} is already in your pipeline` : `${job.company} added`);
                },
              })
            }
          >
            Add anyway
          </Button>
        )}
        <a href={job.url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-slate-400 hover:text-brand-600">
          View posting <ExternalLink className="size-3" />
        </a>
      </div>
    </li>
  );
}

// ---------------------------------------------------------------- web discovery
function WebFinder({ onTask }: { onTask: (t: Task) => void }) {
  const { latest, track } = useTasks();
  const task = latest("webfind");
  const [location, setLocation] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const key = (b: DiscoveredBoard) => `${b.ats}:${b.token}`;
  const boards = ((task?.result as { boards?: DiscoveredBoard[] } | undefined)?.boards ?? []) as DiscoveredBoard[];
  const fresh = boards.filter((b) => !b.known);
  const search = useAction(() => api.post<Task>("/discover/web", { location }));
  const add = useAction(
    (scan: boolean) =>
      api.post<{ added: number; task?: Task }>("/watchlist/bulk", {
        boards: boards.filter((b) => picked.has(key(b))).map(({ ats, token }) => ({ ats, token })),
        scan,
      }),
    (r) => `Added ${r.added} companies to your watchlist${r.task ? " - scanning them now" : ""}`,
  );
  useEffect(() => setPicked(new Set(fresh.map(key))), [task?.id, task?.state]); // eslint-disable-line react-hooks/exhaustive-deps
  const running = task?.state === "running";
  const toggle = (k: string, on: boolean) =>
    setPicked((s) => {
      const n = new Set(s);
      if (on) n.add(k);
      else n.delete(k);
      return n;
    });

  return (
    <Card className="mt-6">
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Telescope className="size-4 text-slate-400" /> Find more companies on the web
          </span>
        }
        description="Searches the web for job pages on all 8 hiring systems that match your role keywords, so you find companies you've never heard of. Takes about 2 minutes."
      />
      <form
        className="flex flex-wrap items-end gap-3 px-5 py-4"
        onSubmit={(e) => {
          e.preventDefault();
          search.mutateAsync(undefined).then(track);
        }}
      >
        <Field label="Location (optional)" className="w-64">
          <Input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="e.g. India, Bengaluru, remote" />
        </Field>
        <Button type="submit" icon={<Search className="size-4" />} loading={running || search.isPending}>
          Search the web
        </Button>
        {running && task && (
          <div className="min-w-64 flex-1">
            <div className="text-xs text-slate-500">{task.message}</div>
            <Progress value={task.total ? (100 * task.done) / task.total : 5} className="mt-1.5" />
          </div>
        )}
      </form>
      {task?.state === "error" && (
        <div className="px-5 pb-4">
          <Callout tone="amber">{task.error}</Callout>
        </div>
      )}
      {task?.state === "done" && (
        <>
          <div className="flex flex-wrap items-center gap-3 border-y border-slate-100 bg-slate-50/50 px-5 py-3">
            <span className="text-[13px] text-slate-600">
              Found <b>{boards.length}</b> company job boards · <b>{fresh.length}</b> not on your watchlist yet. Pick the ones worth scanning:
            </span>
            <div className="flex-1" />
            <Button size="sm" variant="ghost" onClick={() => setPicked(picked.size ? new Set() : new Set(fresh.map(key)))}>
              {picked.size ? "Clear selection" : "Select all new"}
            </Button>
            <Button size="sm" disabled={!picked.size} loading={add.isPending} onClick={() => add.mutate(false)}>
              Add {picked.size} to watchlist
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={<Radar className="size-3.5" />}
              disabled={!picked.size}
              loading={add.isPending}
              onClick={() => add.mutateAsync(true).then((r) => r.task && onTask(r.task))}
            >
              Add &amp; scan {picked.size}
            </Button>
          </div>
          {boards.length === 0 ? (
            <Empty icon={<Telescope className="size-5" />} title="Nothing found this time">
              Search engines sometimes rate-limit. Try again in a few minutes, or with different keywords.
            </Empty>
          ) : (
            <ul className="max-h-[420px] divide-y divide-slate-100 overflow-y-auto">
              {boards.map((b) => (
                <li key={key(b)} className={clsx("flex items-center gap-4 px-5 py-2.5", b.known && "opacity-50")}>
                  <input
                    type="checkbox"
                    disabled={b.known}
                    checked={picked.has(key(b))}
                    onChange={(e) => toggle(key(b), e.target.checked)}
                    className="size-4 accent-brand-600"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-slate-800">{b.token.split("/")[0]}</span>
                      <Badge>{ATS_LABEL[b.ats]}</Badge>
                      {b.known && <Badge tone="green">On watchlist</Badge>}
                    </div>
                    <div className="truncate text-xs text-slate-500">{b.samples.join(" · ") || b.url}</div>
                  </div>
                  <a href={b.url} target="_blank" rel="noreferrer" className="text-slate-400 hover:text-brand-600" title="Open the job page">
                    <ExternalLink className="size-3.5" />
                  </a>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- job alerts
const ALERT_SITES = [
  { name: "LinkedIn", how: "Jobs → search your role → turn on “Set alert”", url: "https://www.linkedin.com/jobs/" },
  { name: "Naukri", how: "Search → “Create job alert” on the results page", url: "https://www.naukri.com/" },
  { name: "Indeed", how: "Search → “Get new jobs for this search by email”", url: "https://in.indeed.com/" },
  { name: "Internshala", how: "Preferences → turn on internship alert emails", url: "https://internshala.com/" },
  { name: "Glassdoor", how: "Search → “Create job alert”", url: "https://www.glassdoor.co.in/" },
];

function JobAlerts({ running, onTask }: { running: boolean; onTask: (t: Task) => void }) {
  const { data: state } = useAppState();
  const [days, setDays] = useState(14);
  const run = useAction(() => api.post<Task>("/discover/alerts", { days }));
  if (!state) return null;
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Inbox className="size-4 text-slate-400" /> Import jobs from your alert emails
            </span>
          }
          description="LinkedIn, Naukri, Indeed and others email you new jobs. Job Dedo reads those emails from your Gmail (read-only, nothing is marked as read), pulls out every job and scores it against your resume. Their websites are never visited."
        />
        <div className="space-y-4 p-5">
          {!state.checks.gmail && <Callout tone="amber">Connect your Gmail in Settings first - alerts are read from your inbox with the same App Password.</Callout>}
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Look back" className="w-48">
              <Select value={days} onChange={(e) => setDays(+e.target.value)}>
                {[3, 7, 14, 30].map((d) => (
                  <option key={d} value={d}>
                    Last {d} days
                  </option>
                ))}
              </Select>
            </Field>
            <Button
              variant="primary"
              icon={<BellRing className="size-4" />}
              disabled={!state.checks.gmail}
              loading={running || run.isPending}
              onClick={() => run.mutateAsync(undefined).then(onTask)}
            >
              Import from Gmail
            </Button>
          </div>
          <p className="text-xs leading-relaxed text-slate-500">
            Alert emails carry only the title, company and place, so the match score is based on the title. The minimum-match filter is skipped for them (you chose those alerts), but keywords and fresher-friendly still apply. Imported jobs are marked <b>Apply on site</b>.
          </p>
        </div>
      </Card>
      <Card className="h-fit">
        <CardHeader title="Set up alerts once" description={`Search for your role${state.profile.target_role ? ` (“${state.profile.target_role}”)` : ""} and turn on email alerts.`} />
        <ul className="divide-y divide-slate-100">
          {ALERT_SITES.map((s) => (
            <li key={s.name} className="px-5 py-3">
              <a href={s.url} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-sm font-medium text-slate-800 hover:text-brand-600">
                {s.name} <ExternalLink className="size-3" />
              </a>
              <div className="text-xs text-slate-500">{s.how}</div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
