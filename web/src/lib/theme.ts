import { useEffect, useState } from "react";

export type ThemeMode = "light" | "dark" | "system";
const KEY = "job-dedo-theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");

function readMode(): ThemeMode {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark" || saved === "system") return saved;
  } catch {
    /* storage blocked - fall back to the system setting */
  }
  return "system";
}

const resolve = (mode: ThemeMode) => (mode === "system" ? (media.matches ? "dark" : "light") : mode);

/** Light / dark / follow-the-OS, remembered per browser. index.html applies it before first paint. */
export function useTheme() {
  const [mode, setMode] = useState<ThemeMode>(readMode);
  const [resolved, setResolved] = useState<"light" | "dark">(() => resolve(readMode()));

  useEffect(() => {
    const apply = () => {
      const r = resolve(mode);
      setResolved(r);
      document.documentElement.classList.toggle("dark", r === "dark");
    };
    apply();
    try {
      localStorage.setItem(KEY, mode);
    } catch {
      /* not persisted this session */
    }
    if (mode !== "system") return;
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode]);

  return { mode, setMode, resolved };
}
