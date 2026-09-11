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
  caption_offset_ms?: number | null;
  word_timed_captions?: boolean | null;
  caption_zone?: "upper" | "middle" | "lower" | null;
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

function captionZoneLabel(zone?: RenderResponse["caption_zone"]) {
  if (zone === "upper") return "upper caption-safe zone";
  if (zone === "middle") return "middle caption-safe zone";
  return "lower caption-safe zone";
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
  const [captionOffsets, setCaptionOffsets] = useState<Record<number, number>>({});

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
    setCaptionOffsets({});

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
        body.caption_offset_ms = captionOffsets[index] || 0;
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
        <div className="badge">Milestone 11 · simpler controls</div>
      </nav>

      <main className="main">
        <section className="hero">
          <div className="eyebrow">Long video → short-form gold</div>
          <h1>Turn a long video into a Short without learning video editing.</h1>
          <p className="sub">
            Upload a video, pick a moment, and press Create Short. Auto handles framing and captions; the detailed controls are there only when you want them.
          </p>

          <div className="modeTabs">
            <button className={mode === "upload" ? "tab active" : "tab"} onClick={() => switchMode("upload")}>
              Your video
            </button>
            <button className={mode === "youtube" ? "tab active" : "tab"} onClick={() => switchMode("youtube")}>
              YouTube link
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
                {loading ? "Finding moments…" : "Try link demo"}
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

            <details className="formatGuide">
              <summary>
                <span>
                  <strong>New to video settings?</strong>
                  <small>Open the 60-second guide to framing, sizes and captions.</small>
                </span>
                <span className="guideChevron">⌄</span>
              </summary>
              <div className="guideBody">
                <div className="guideIntro">
                  <strong>The final Short is always 9:16</strong>
                  <p>That is the normal vertical phone format (720×1280 in this local build). The choices below change how your original video sits inside that vertical canvas.</p>
                </div>
                <div className="guideGrid">
                  <div className="guideGroup">
                    <h4>Framing</h4>
                    <p><b>Auto</b> — recommended. Clip AI chooses for you.</p>
                    <p><b>Fill</b> — fills the phone screen; best for one-person talking videos.</p>
                    <p><b>Focus</b> — a large central video window with dark space around it; useful for films and wider scenes.</p>
                    <p><b>Backdrop</b> — like Focus, but the spare area uses a blurred version of the video.</p>
                    <p><b>Preserve</b> — keeps footage that is already vertical mostly unchanged.</p>
                  </div>
                  <div className="guideGroup">
                    <h4>Video size</h4>
                    <p>This mainly affects Focus and Backdrop.</p>
                    <p><b>Compact</b> — more breathing room around the picture.</p>
                    <p><b>Balanced</b> — recommended; roughly a 4:5-style picture inside the 9:16 Short.</p>
                    <p><b>Immersive</b> — makes the picture larger and uses more of the screen.</p>
                  </div>
                  <div className="guideGroup">
                    <h4>Caption style</h4>
                    <p><b>Viral Pop</b> — energetic word highlighting for podcasts and social clips.</p>
                    <p><b>Cinematic</b> — quieter subtitles on the lower part of the actual picture.</p>
                    <p><b>Clean</b> — simple and readable with little distraction.</p>
                    <p><b>Meme</b> — bold, playful text for reactions, gameplay and humorous clips.</p>
                  </div>
                </div>
                <div className="guideTip"><b>Not sure?</b> Leave everything on Auto and press Create Short. You can always regenerate with different settings.</div>
              </div>
            </details>

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
                const selectedOffset = captionOffsets[index] || 0;

                return (
                  <article className="clipCard" key={`${clip.start}-${index}`}>
                    <div className="clipTop">
                      <span className="score">{clip.score}/100</span>
                      <span className="time">{fmt(clip.start)} → {fmt(clip.end)}</span>
                    </div>
                    <h3>{clip.title}</h3>
                    <div className="clipPreview">
                      <span>Starts with</span>
                      <p>“{clip.hook}”</p>
                    </div>
                    <details className="whyPicked">
                      <summary>Why Clip AI picked this moment</summary>
                      <div className="reasons">
                        {clip.reasons.map((reason) => <span className="reason" key={reason}>{reason}</span>)}
                      </div>
                    </details>

                    {!result.mock && result.job_id && (
                      <>
                        <div className="renderActions simpleActions">
                          <button
                            className="renderButton shortButton"
                            onClick={() => renderMedia(clip, index, "short")}
                            disabled={rendering !== null}
                          >
                            {isShortRendering ? "Creating Short…" : "Create Short"}
                          </button>
                          <button
                            className="renderButton secondaryButton"
                            onClick={() => renderMedia(clip, index, "original")}
                            disabled={rendering !== null}
                          >
                            {isOriginalRendering ? "Cutting original…" : "Original clip"}
                          </button>
                        </div>

                        <details className="customizePanel">
                          <summary>
                            <span>Customize</span>
                            <small>Optional · Auto is recommended</small>
                          </summary>
                          <div className="customizeBody">
                            <div className="renderOptions">
                              <label>
                                <span>Framing <i>How the picture fits</i></span>
                                <select
                                  value={selectedLayout}
                                  onChange={(e) => setLayouts((current) => ({ ...current, [index]: e.target.value as LayoutMode }))}
                                  disabled={rendering !== null}
                                >
                                  <option value="auto">Auto · recommended</option>
                                  <option value="fill">Fill · full vertical crop</option>
                                  <option value="focus">Focus · central window</option>
                                  <option value="backdrop">Backdrop · central + blur</option>
                                  <option value="preserve">Preserve · already vertical</option>
                                </select>
                              </label>
                              <label>
                                <span>Video size <i>Focus/Backdrop only</i></span>
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
                                <span>Captions <i>Text personality</i></span>
                                <select
                                  value={selectedCaption}
                                  onChange={(e) => setCaptions((current) => ({ ...current, [index]: e.target.value as CaptionStyle }))}
                                  disabled={rendering !== null}
                                >
                                  <option value="auto">Auto · recommended</option>
                                  <option value="viral">Viral Pop</option>
                                  <option value="cinematic">Cinematic</option>
                                  <option value="clean">Clean</option>
                                  <option value="meme">Meme</option>
                                </select>
                              </label>
                            </div>
                            <details className="advancedPanel">
                              <summary>Advanced timing</summary>
                              <div className="syncControl">
                                <div className="syncHead">
                                  <span>Caption sync</span>
                                  <strong>{selectedOffset > 0 ? `+${selectedOffset}` : selectedOffset} ms</strong>
                                </div>
                                <input
                                  type="range"
                                  min="-500"
                                  max="500"
                                  step="50"
                                  value={selectedOffset}
                                  disabled={rendering !== null}
                                  onChange={(e) => setCaptionOffsets((current) => ({ ...current, [index]: Number(e.target.value) }))}
                                />
                                <div className="syncLegend"><span>Earlier</span><span>Whisper timing</span><span>Later</span></div>
                              </div>
                            </details>
                          </div>
                        </details>
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
                              ? `${layoutLabel(renderedClip.layout_mode)} · ${frameSizeLabel(renderedClip.frame_size)} · ${captionLabel(renderedClip.caption_style)} · ${renderedClip.word_timed_captions ? "word-synced" : "legacy timing"} · ${captionZoneLabel(renderedClip.caption_zone)} · ${framingLabel(renderedClip.framing_mode)}`
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
            <div className="footNote">Milestone 11 keeps Auto simple, moves expert controls out of the way, explains every format in plain English, and removes the doubled-text effect from Viral/Meme word pops.</div>
          </section>
        )}
      </main>
    </div>
  );
}
