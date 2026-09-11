"use client";

import { FormEvent, useState } from "react";

type Clip = {
  start: number;
  end: number;
  title: string;
  hook: string;
  score: number;
  reasons: string[];
};

type AnalyzeResponse = {
  source_url: string;
  mock: boolean;
  clips: Clip[];
  job_id?: string | null;
};

type RenderResponse = {
  job_id: string;
  filename: string;
  start: number;
  end: number;
  duration: number;
  media_url: string;
  download_url: string;
};

type Mode = "upload" | "youtube";

function fmt(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${s}` : `${m}:${s}`;
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("upload");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [renderingIndex, setRenderingIndex] = useState<number | null>(null);
  const [rendered, setRendered] = useState<Record<number, RenderResponse>>({});

  const workerUrl = process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000";

  async function submitUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError("");
    setLoading(true);
    setResult(null);
    setRendered({});

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("max_clips", "6");
      const res = await fetch(`${workerUrl}/analyze-upload`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Analysis failed");
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function submitYoutube(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    setResult(null);
    setRendered({});

    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ source_url: url, max_clips: 6 }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Analysis failed");
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function renderClip(clip: Clip, index: number) {
    if (!result?.job_id) {
      setError("This result does not have a real uploaded source attached.");
      return;
    }

    setError("");
    setRenderingIndex(index);
    try {
      const res = await fetch(`${workerUrl}/render-clip`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          job_id: result.job_id,
          start: clip.start,
          end: clip.end,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Clip render failed");
      setRendered((current) => ({ ...current, [index]: data }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong while rendering");
    } finally {
      setRenderingIndex(null);
    }
  }

  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">Clip AI</div>
        <div className="badge">Milestone 3 · real MP4 cuts</div>
      </nav>

      <main className="main">
        <section className="hero">
          <div className="eyebrow">Long video → short-form gold</div>
          <h1>Find it. Cut it. Play it.</h1>
          <p className="sub">
            Upload a video you own or are authorised to use. Local Whisper finds candidate moments, then Clip AI can cut any chosen timestamp into a real browser-ready MP4.
          </p>

          <div className="modeTabs">
            <button className={mode === "upload" ? "tab active" : "tab"} onClick={() => { setMode("upload"); setError(""); setResult(null); setRendered({}); }}>
              Upload video · real
            </button>
            <button className={mode === "youtube" ? "tab active" : "tab"} onClick={() => { setMode("youtube"); setError(""); setResult(null); setRendered({}); }}>
              YouTube URL · demo
            </button>
          </div>

          {mode === "upload" ? (
            <form className="uploadCard" onSubmit={submitUpload}>
              <label className="filePicker">
                <span className="fileIcon">↑</span>
                <span className="fileTitle">{file ? file.name : "Choose a video file"}</span>
                <span className="fileHelp">MP4, MOV, MKV, WEBM, M4V or AVI</span>
                <input
                  type="file"
                  accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.m4v,.avi"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
              <button className="primary wide" disabled={loading || !file}>
                {loading ? "Running local Whisper…" : "Analyze real video"}
              </button>
              <p className="localNote">The source and rendered clips stay in the worker&apos;s local work folder on your PC.</p>
            </form>
          ) : (
            <form className="inputCard" onSubmit={submitYoutube}>
              <input
                className="urlInput"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://www.youtube.com/watch?v=..."
                type="url"
                required
              />
              <button className="primary" disabled={loading || !url}>
                {loading ? "Finding moments…" : "Generate demo clips"}
              </button>
            </form>
          )}
          {error && <div className="error">{error}</div>}
        </section>

        {result && (
          <section className="results">
            <div className="resultsHead">
              <div>
                <h2>Your strongest moments</h2>
                <p>{result.clips.length} candidates ranked by short-form potential.</p>
              </div>
              <div className="badge">{result.mock ? "Demo analysis" : "Real local transcript"}</div>
            </div>

            <div className="clipGrid">
              {result.clips.map((clip, index) => {
                const renderedClip = rendered[index];
                const isRendering = renderingIndex === index;
                const playableUrl = renderedClip ? `${workerUrl}${renderedClip.media_url}` : "";
                const downloadUrl = renderedClip ? `${workerUrl}${renderedClip.download_url}` : "";

                return (
                  <article className="clipCard" key={`${clip.start}-${index}`}>
                    <div className="clipTop">
                      <span className="score">{clip.score}/100</span>
                      <span className="time">{fmt(clip.start)} → {fmt(clip.end)}</span>
                    </div>
                    <h3>{clip.title}</h3>
                    <p className="hook">“{clip.hook}”</p>
                    <div className="reasons">
                      {clip.reasons.map((reason) => <span className="reason" key={reason}>{reason}</span>)}
                    </div>

                    {!result.mock && result.job_id && (
                      <button
                        className="renderButton"
                        onClick={() => renderClip(clip, index)}
                        disabled={renderingIndex !== null}
                      >
                        {isRendering ? "Cutting MP4…" : renderedClip ? "Re-render clip" : "Generate MP4"}
                      </button>
                    )}

                    {renderedClip && (
                      <div className="renderedClip">
                        <video className="clipVideo" controls preload="metadata" src={playableUrl} />
                        <div className="renderMeta">
                          <span>{Math.round(renderedClip.duration)} sec MP4</span>
                          <a className="downloadLink" href={downloadUrl}>Download MP4</a>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
            <div className="footNote">Next milestone: transform the cut into 9:16, add animated captions, then move toward speaker/face-aware reframing.</div>
          </section>
        )}
      </main>
    </div>
  );
}
