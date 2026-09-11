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

type LayoutMode = "auto" | "fill" | "focus" | "backdrop" | "preserve";
type CaptionStyle = "auto" | "viral" | "cinematic" | "clean" | "meme";
type FrameSize = "compact" | "balanced" | "immersive";

type RenderResponse = {
  job_id: string;
  filename: string;
  start: number;
  end: number;
  duration: number;
  media_url: string;
  download_url: string;
  kind?: "original" | "short";
  width?: number | null;
  height?: number | null;
  framing_mode?: "face" | "motion" | "center" | "portrait" | null;
  layout_mode?: "fill" | "focus" | "backdrop" | "preserve" | null;
  caption_style?: "viral" | "cinematic" | "clean" | "meme" | null;
  frame_size?: "compact" | "balanced" | "immersive" | null;
  tracking_samples?: number | null;
  face_samples?: number | null;
  motion_samples?: number | null;
};

type Mode = "upload" | "youtube";
type RenderKind = "original" | "short";

function fmt(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return h > 0 ? `${h}:${m.toString().padStart(2, "0")}:${s}` : `${m}:${s}`;
}

function framingLabel(mode?: RenderResponse["framing_mode"]) {
  if (mode === "face") return "face-aware";
  if (mode === "motion") return "motion-aware";
  if (mode === "portrait") return "portrait-preserved";
  return "safe-center";
}

function layoutLabel(mode?: RenderResponse["layout_mode"]) {
  if (mode === "fill") return "full vertical fill";
  if (mode === "focus") return "central focus window";
  if (mode === "backdrop") return "focus + blurred backdrop";
  if (mode === "preserve") return "portrait preserve";
  return "adaptive layout";
}

function frameSizeLabel(size?: RenderResponse["frame_size"]) {
  if (size === "compact") return "compact";
  if (size === "immersive") return "immersive";
  return "balanced";
}

function captionLabel(style?: RenderResponse["caption_style"]) {
  if (style === "viral") return "Viral Pop";
  if (style === "cinematic") return "Cinematic";
  if (style === "meme") return "Meme";
  return "Clean";
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("upload");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [rendering, setRendering] = useState<{ index: number; kind: RenderKind } | null>(null);
  const [rendered, setRendered] = useState<Record<number, RenderResponse>>({});
  const [layouts, setLayouts] = useState<Record<number, LayoutMode>>({});
  const [captions, setCaptions] = useState<Record<number, CaptionStyle>>({});
  const [frameSizes, setFrameSizes] = useState<Record<number, FrameSize>>({});

  const workerUrl = process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000";

  async function submitUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError("");
    setLoading(true);
    setResult(null);
    setRendered({});
    setLayouts({});
    setCaptions({});
    setFrameSizes({});

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

  async function renderMedia(clip: Clip, index: number, kind: RenderKind) {
    if (!result?.job_id) {
      setError("This result does not have a real uploaded source attached.");
      return;
    }

    setError("");
    setRendering({ index, kind });
    const endpoint = kind === "short" ? "/render-short" : "/render-clip";

    try {
      const body: Record<string, string | number> = {
        job_id: result.job_id,
        start: clip.start,
        end: clip.end,
      };
      if (kind === "short") {
        body.layout_mode = layouts[index] || "auto";
        body.caption_style = captions[index] || "auto";
        body.frame_size = frameSizes[index] || "balanced";
      }

      const res = await fetch(`${workerUrl}${endpoint}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Render failed");
      setRendered((current) => ({ ...current, [index]: data }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong while rendering");
    } finally {
      setRendering(null);
    }
  }

  function switchMode(nextMode: Mode) {
    setMode(nextMode);
    setError("");
    setResult(null);
    setRendered({});
  }

  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">Clip AI</div>
        <div className="badge">Milestone 7 · in-frame captions</div>
      </nav>

      <main className="main">
        <section className="hero">
          <div className="eyebrow">Long video → short-form gold</div>
          <h1>Vertical Shorts without destroying the scene.</h1>
          <p className="sub">
            Talking heads can fill 9:16. Movies and wider scenes use a large central portrait-friendly window instead of a tiny 16:9 letterbox. Captions always stay on the actual picture, never in the surrounding margins.
          </p>

          <div className="modeTabs">
            <button className={mode === "upload" ? "tab active" : "tab"} onClick={() => switchMode("upload")}>
              Upload video · real
            </button>
            <button className={mode === "youtube" ? "tab active" : "tab"} onClick={() => switchMode("youtube")}>
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
              <p className="localNote">Local Whisper + lightweight visual sampling. Short renders stay at 720×1280 so development remains practical on your PC.</p>
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
                const isThisRendering = rendering?.index === index;
                const isShortRendering = isThisRendering && rendering?.kind === "short";
                const isOriginalRendering = isThisRendering && rendering?.kind === "original";
                const playableUrl = renderedClip ? `${workerUrl}${renderedClip.media_url}` : "";
                const downloadUrl = renderedClip ? `${workerUrl}${renderedClip.download_url}` : "";
                const isVertical = renderedClip?.kind === "short";
                const selectedLayout = layouts[index] || "auto";
                const selectedCaption = captions[index] || "auto";
                const selectedFrameSize = frameSizes[index] || "balanced";

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
                      <>
                        <div className="renderOptions">
                          <label>
                            <span>Framing</span>
                            <select
                              value={selectedLayout}
                              onChange={(e) => setLayouts((current) => ({ ...current, [index]: e.target.value as LayoutMode }))}
                              disabled={rendering !== null}
                            >
                              <option value="auto">Auto</option>
                              <option value="fill">Fill · full 9:16 crop</option>
                              <option value="focus">Focus · central video window</option>
                              <option value="backdrop">Backdrop · focus + blur</option>
                              <option value="preserve">Preserve · vertical source</option>
                            </select>
                          </label>
                          <label>
                            <span>Video size</span>
                            <select
                              value={selectedFrameSize}
                              onChange={(e) => setFrameSizes((current) => ({ ...current, [index]: e.target.value as FrameSize }))}
                              disabled={rendering !== null}
                            >
                              <option value="compact">Compact</option>
                              <option value="balanced">Balanced · recommended</option>
                              <option value="immersive">Immersive</option>
                            </select>
                          </label>
                          <label>
                            <span>Captions</span>
                            <select
                              value={selectedCaption}
                              onChange={(e) => setCaptions((current) => ({ ...current, [index]: e.target.value as CaptionStyle }))}
                              disabled={rendering !== null}
                            >
                              <option value="auto">Auto</option>
                              <option value="viral">Viral Pop</option>
                              <option value="cinematic">Cinematic</option>
                              <option value="clean">Clean</option>
                              <option value="meme">Meme</option>
                            </select>
                          </label>
                        </div>
                        <p className="optionHint">Focus keeps a large central crop on a quiet dark canvas; Backdrop uses the same crop with blur. Captions are always placed inside the picture itself.</p>

                        <div className="renderActions">
                          <button
                            className="renderButton shortButton"
                            onClick={() => renderMedia(clip, index, "short")}
                            disabled={rendering !== null}
                          >
                            {isShortRendering ? "Building adaptive Short…" : "Generate Adaptive Short"}
                          </button>
                          <button
                            className="renderButton secondaryButton"
                            onClick={() => renderMedia(clip, index, "original")}
                            disabled={rendering !== null}
                          >
                            {isOriginalRendering ? "Cutting original…" : "Original MP4"}
                          </button>
                        </div>
                      </>
                    )}

                    {renderedClip && (
                      <div className={`renderedClip ${isVertical ? "verticalWrap" : ""}`}>
                        <video
                          className={`clipVideo ${isVertical ? "verticalVideo" : ""}`}
                          controls
                          preload="metadata"
                          src={playableUrl}
                        />
                        <div className="renderMeta">
                          <span>
                            {Math.round(renderedClip.duration)} sec · {isVertical
                              ? `${layoutLabel(renderedClip.layout_mode)} · ${frameSizeLabel(renderedClip.frame_size)} · ${captionLabel(renderedClip.caption_style)} · ${framingLabel(renderedClip.framing_mode)}`
                              : "original frame"}
                          </span>
                          <a className="downloadLink" href={downloadUrl}>Download MP4</a>
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
            <div className="footNote">Auto now prefers full Fill for stable single-person shots, Focus for movie/multi-person scenes, and Backdrop for motion-led content. Focus/Backdrop never use a tiny full-width 16:9 letterbox, and every caption stays on the actual video picture.</div>
          </section>
        )}
      </main>
    </div>
  );
}
