import clsx from "clsx";
import { Loader2, X } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { useEffect } from "react";
import type { Level, Status } from "../lib/api";

// ---------------------------------------------------------------- buttons
type Variant = "primary" | "secondary" | "ghost" | "danger";
const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-500 shadow-sm shadow-brand-600/20 disabled:hover:bg-brand-600",
  secondary: "bg-surface text-slate-700 ring-1 ring-slate-200 hover:bg-slate-50 hover:ring-slate-300 shadow-sm disabled:text-slate-400",
  ghost: "text-slate-600 hover:bg-slate-100 hover:text-slate-900 disabled:text-slate-300",
  danger: "bg-surface text-rose-600 ring-1 ring-rose-200 hover:bg-rose-50 disabled:text-rose-300",
};

export function Button({
  variant = "secondary",
  size = "md",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md"; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none",
        size === "sm" ? "h-8 px-3 text-[13px]" : "h-9 px-4 text-sm",
        variants[variant],
        className,
      )}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

// ---------------------------------------------------------------- layout
export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("rounded-xl border border-slate-200/80 bg-surface shadow-[0_1px_2px_rgba(15,23,42,0.04)]", className)}>{children}</div>;
}

export function CardHeader({ title, description, action }: { title: ReactNode; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 py-4">
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
        {description && <p className="mt-0.5 text-[13px] text-slate-500">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  );
}

export function PageHeader({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-[22px] font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-slate-500">{description}</p>}
      </div>
      {action && <div className="flex flex-wrap items-center gap-2">{action}</div>}
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 grid size-11 place-items-center rounded-xl bg-slate-100 text-slate-400">{icon}</div>
      <p className="text-sm font-medium text-slate-700">{title}</p>
      {children && <div className="mt-1 max-w-sm text-[13px] text-slate-500">{children}</div>}
    </div>
  );
}

// ---------------------------------------------------------------- form
export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="mb-1.5 block text-[13px] font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

const inputBase =
  "w-full rounded-lg border border-slate-200 bg-surface px-3 text-sm text-slate-800 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-3 focus:ring-brand-500/15 disabled:bg-slate-50";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={clsx(inputBase, "h-9", className)} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...rest} className={clsx(inputBase, "py-2 leading-relaxed", className)} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={clsx(inputBase, "h-9 pr-8", className)}>
      {children}
    </select>
  );
}

export function Toggle({ checked, onChange, label, description }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string }) {
  return (
    <button type="button" onClick={() => onChange(!checked)} className="flex items-start gap-3 text-left">
      <span className={clsx("mt-0.5 flex h-5 w-9 shrink-0 items-center rounded-full p-0.5 transition-colors", checked ? "bg-brand-600" : "bg-slate-300")}>
        <span className={clsx("size-4 rounded-full bg-[#fff] shadow transition-transform", checked && "translate-x-4")} />
      </span>
      <span>
        <span className="block text-sm font-medium text-slate-700">{label}</span>
        {description && <span className="block text-xs text-slate-500">{description}</span>}
      </span>
    </button>
  );
}

export function Checkbox({ checked, onChange, indeterminate }: { checked: boolean; onChange: (v: boolean) => void; indeterminate?: boolean }) {
  return (
    <input
      type="checkbox"
      checked={checked}
      ref={(el) => {
        if (el) el.indeterminate = !!indeterminate;
      }}
      onChange={(e) => onChange(e.target.checked)}
      onClick={(e) => e.stopPropagation()}
      className="size-4 cursor-pointer rounded border-slate-300 accent-brand-600"
    />
  );
}

// ---------------------------------------------------------------- badges
const tones = {
  slate: "bg-slate-100 text-slate-600 ring-slate-500/10",
  brand: "bg-brand-50 text-brand-700 ring-brand-600/15",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/15",
  amber: "bg-amber-50 text-amber-700 ring-amber-600/20",
  red: "bg-rose-50 text-rose-700 ring-rose-600/15",
  blue: "bg-sky-50 text-sky-700 ring-sky-600/15",
  violet: "bg-violet-50 text-violet-700 ring-violet-600/15",
};
export type Tone = keyof typeof tones;

export function Badge({ tone = "slate", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset", tones[tone], className)}>
      {children}
    </span>
  );
}

export const STATUS: Record<Status, { label: string; tone: Tone; dot: string }> = {
  new: { label: "Needs email", tone: "slate", dot: "bg-slate-400" },
  portal: { label: "Apply on site", tone: "blue", dot: "bg-sky-400" },
  applied: { label: "Applied on site", tone: "green", dot: "bg-emerald-400" },
  no_email: { label: "No email found", tone: "amber", dot: "bg-amber-500" },
  ready: { label: "Ready to write", tone: "blue", dot: "bg-sky-500" },
  drafted: { label: "Draft", tone: "violet", dot: "bg-violet-500" },
  approved: { label: "Approved", tone: "brand", dot: "bg-brand-500" },
  sent: { label: "Sent", tone: "green", dot: "bg-emerald-500" },
  failed: { label: "Failed", tone: "red", dot: "bg-rose-500" },
  skipped: { label: "Skipped", tone: "slate", dot: "bg-slate-300" },
};

export function StatusBadge({ status }: { status: Status }) {
  const s = STATUS[status];
  return (
    <Badge tone={s.tone}>
      <span className={clsx("size-1.5 rounded-full", s.dot)} />
      {s.label}
    </Badge>
  );
}

const LEVELS: Record<Level, { label: string; tone: Tone }> = {
  intern: { label: "Internship", tone: "green" },
  entry: { label: "Entry level", tone: "green" },
  open: { label: "Level not stated", tone: "slate" },
  mid: { label: "Mid level", tone: "amber" },
  senior: { label: "Senior", tone: "red" },
};

export function LevelBadge({ level }: { level: Level | null }) {
  if (!level) return null;
  return <Badge tone={LEVELS[level].tone}>{LEVELS[level].label}</Badge>;
}

export function Score({ value, size = 40 }: { value: number | null; size?: number }) {
  if (value === null || value === undefined) return <span className="text-xs text-slate-400">–</span>;
  const r = size / 2 - 3.5;
  const c = 2 * Math.PI * r;
  const color = value >= 70 ? "#059669" : value >= 50 ? "#4f46e5" : value >= 35 ? "#d97706" : "#94a3b8";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} title={`${value}% match with your resume`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-slate-200)" strokeWidth={3.5} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={3.5}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - value / 100)}
        />
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[11px] font-semibold text-slate-700">{value}</span>
    </div>
  );
}

export function SkillChips({ matched, missing, limit = 6 }: { matched: string[]; missing: string[]; limit?: number }) {
  return (
    <div className="flex flex-wrap gap-1">
      {matched.slice(0, limit).map((s) => (
        <span key={s} className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">
          ✓ {s}
        </span>
      ))}
      {missing.slice(0, Math.max(2, limit - matched.length)).map((s) => (
        <span key={s} className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-700">
          + {s}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- progress & modal
export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={clsx("h-1.5 overflow-hidden rounded-full bg-slate-100", className)}>
      <div className="h-full rounded-full bg-brand-600 transition-all duration-500" style={{ width: `${Math.min(100, Math.max(3, value))}%` }} />
    </div>
  );
}

export function Modal({ open, onClose, title, children, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/50 p-4 pt-[8vh] backdrop-blur-[2px]" onMouseDown={onClose}>
      <div className={clsx("w-full rounded-xl bg-surface shadow-2xl", wide ? "max-w-4xl" : "max-w-lg")} onMouseDown={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
          <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600">
            <X className="size-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

export function Callout({ tone = "brand", icon, children }: { tone?: "brand" | "amber" | "green"; icon?: ReactNode; children: ReactNode }) {
  const styles = {
    brand: "border-brand-200 bg-brand-50/60 text-brand-900",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    green: "border-emerald-200 bg-emerald-50 text-emerald-900",
  };
  return (
    <div className={clsx("flex gap-3 rounded-lg border px-4 py-3 text-[13px] leading-relaxed", styles[tone])}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function ExtLink({ href, children }: { href: string | null | undefined; children: ReactNode }) {
  if (!href) return null;
  return (
    <a href={href} target="_blank" rel="noreferrer" className="text-brand-600 hover:text-brand-700 hover:underline" onClick={(e) => e.stopPropagation()}>
      {children}
    </a>
  );
}
