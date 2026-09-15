"use client";

import { useEffect, useState } from "react";

type SystemCheck = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
  severity: "required" | "warning" | "info";
};

type Preflight = {
  version: string;
  release: string;
  ready: boolean;
  checks: SystemCheck[];
  transcription_backend: string;
  ranking_backend: string;
  local_whisper_model: string;
  work_dir: string;
  project_count: number;
  project_storage_bytes: number;
  disk_free_bytes: number;
  disk_total_bytes: number;
  privacy_note: string;
};

type Cleanup = {
  removed_files: number;
  removed_bytes: number;
  startup_cleanup: number;
};

function humanBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return "0 MB";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export default function StatusPage() {
  const workerUrl = process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000";
  const [data, setData] = useState<Preflight | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [cleaning, setCleaning] = useState(false);
  const [cleanupMessage, setCleanupMessage] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${workerUrl}/system/preflight`, { cache: "no-store" });
      const payload: Preflight & { detail?: string } = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Could not run the system check");
      setData(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the Clip AI worker");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void refresh(); }, []);

  async function cleanTemporaryFiles() {
    setCleaning(true);
    setCleanupMessage("");
    try {
      const res = await fetch(`${workerUrl}/system/cleanup`, { method: "POST" });
      const payload: Cleanup & { detail?: string } = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Cleanup failed");
      setCleanupMessage(payload.removed_files > 0
        ? `Removed ${payload.removed_files} temporary item${payload.removed_files === 1 ? "" : "s"} and freed ${humanBytes(payload.removed_bytes)}.`
        : "No stale temporary files were found.");
      await refresh();
    } catch (err) {
      setCleanupMessage(err instanceof Error ? err.message : "Cleanup failed");
    } finally {
      setCleaning(false);
    }
  }

  function replayOnboarding() {
    window.localStorage.removeItem("clip-ai-v22-onboarding");
    window.localStorage.removeItem("clip-ai-v21-onboarding");
    window.localStorage.removeItem("clip-ai-v20-onboarding");
    window.location.href = "/";
  }

  return (
    <div className="shell">
      <nav className="nav">
        <a className="brand brandLink" href="/">Clip AI</a>
        <div className="navActions">
          <a className="navLink" href="/projects">Projects</a>
          <a className="navLink activeNav" href="/status">System</a>
          <a className="navLink" href="/">Create</a>
          <div className="badge">v23 · stable candidate</div>
        </div>
      </nav>

      <main className="main statusMain">
        <section className="statusHero">
          <div>
            <div className="eyebrow">Beta readiness</div>
            <h1>System check</h1>
            <p className="sub">A quick preflight for FFmpeg, transcription, storage and the local workspace. Green here means the core Clip AI pipeline is ready.</p>
          </div>
          <button className="statusRefresh" onClick={() => void refresh()} disabled={loading}>{loading ? "Checking…" : "Run check again"}</button>
        </section>

        {error && <div className="error">{error}</div>}

        {data && (
          <>
            <section className={`readinessBanner ${data.ready ? "ready" : "notReady"}`}>
              <div className="readinessIcon">{data.ready ? "✓" : "!"}</div>
              <div>
                <span>{data.release}</span>
                <h2>{data.ready ? "Ready to create Shorts" : "A required check needs attention"}</h2>
                <p>{data.privacy_note}</p>
              </div>
              <strong>{data.version}</strong>
            </section>

            <section className="statusGrid">
              {data.checks.map((check) => (
                <article className={`statusCheck ${check.ok ? "ok" : "bad"}`} key={check.id}>
                  <div className="statusCheckIcon">{check.ok ? "✓" : check.severity === "warning" ? "△" : "×"}</div>
                  <div>
                    <h3>{check.label}</h3>
                    <p>{check.detail}</p>
                  </div>
                  <span>{check.ok ? "Ready" : check.severity === "warning" ? "Optional" : "Fix"}</span>
                </article>
              ))}
            </section>

            <section className="betaStats">
              <article><span>AI mode</span><strong>{data.transcription_backend} + {data.ranking_backend}</strong><small>{data.local_whisper_model}</small></article>
              <article><span>Saved projects</span><strong>{data.project_count}</strong><small>{humanBytes(data.project_storage_bytes)} used by projects</small></article>
              <article><span>Free disk</span><strong>{humanBytes(data.disk_free_bytes)}</strong><small>of {humanBytes(data.disk_total_bytes)}</small></article>
            </section>

            <section className="betaTools">
              <div>
                <h2>Local beta tools</h2>
                <p>Cleanup only removes stale temporary render/audio leftovers. It does not delete saved projects or finished Shorts.</p>
              </div>
              <div className="betaToolActions">
                <button onClick={cleanTemporaryFiles} disabled={cleaning}>{cleaning ? "Cleaning…" : "Clean temporary files"}</button>
                <button onClick={replayOnboarding}>Replay welcome tour</button>
                <a className="diagnosticLink" href={`${workerUrl}/system/diagnostics`}>Export redacted diagnostics</a>
              </div>
              {cleanupMessage && <p className="cleanupMessage">{cleanupMessage}</p>}
            </section>

            <section className="betaNotice">
              <strong>What “beta” means here</strong>
              <p>v23 Stable Candidate keeps the classic anime cinematic window and adds stricter narrative completeness, stronger Best 3 diversity and regression hardening.</p>
              <code>{data.work_dir}</code>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
