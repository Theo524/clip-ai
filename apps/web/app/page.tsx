"use client";

import { FormEvent, useEffect, useState } from "react";

type Clip = {
  start: number;
  end: number;
  title: string;
  hook: string;
  score: number;
  reasons: string[];
  social_caption?: string | null;
  score_breakdown?: Record<string, number>;
  editor_note?: string | null;
};

type AnalyzeResponse = {
  source_url: string;
  mock: boolean;
  clips: Clip[];
  job_id?: string | null;
};

type YouTubeInfo = {
  source_url: string;
  title: string;
  author_name?: string | null;
  thumbnail_url?: string | null;
  provider_name: string;
};

type SavedRender = {
  filename: string;
  kind: "short" | "original";
  media_url: string;
  download_url: string;
  size_bytes: number;
  created_at: string;
};

type ProjectDetail = {
  job_id: string;
  title: string;
  source_type: "upload" | "youtube";
  source_url?: string | null;
  author_name?: string | null;
  thumbnail_url?: string | null;
  created_at: string;
  updated_at: string;
  clip_count: number;
  render_count: number;
  storage_bytes: number;
  clips: Clip[];
  renders: SavedRender[];
};

type LayoutMode = "auto" | "fill" | "focus" | "backdrop" | "preserve";
type CaptionStyle = "auto" | "viral" | "cinematic" | "clean" | "meme";
type FrameSize = "auto" | "compact" | "balanced" | "immersive";
type Platform = "auto" | "shorts" | "tiktok" | "reels";
type CopyStyle = "auto" | "viral" | "clean" | "cinematic";

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
  framing_mode?: "speaker" | "face" | "motion" | "center" | "portrait" | null;
  layout_mode?: "fill" | "focus" | "backdrop" | "preserve" | null;
  caption_style?: "viral" | "cinematic" | "clean" | "meme" | null;
  frame_size?: "compact" | "balanced" | "immersive" | null;
  tracking_samples?: number | null;
  face_samples?: number | null;
  motion_samples?: number | null;
  active_speaker_samples?: number | null;
  active_speaker_switches?: number | null;
  group_fallback_samples?: number | null;
  caption_offset_ms?: number | null;
  word_timed_captions?: boolean | null;
  caption_zone?: "upper" | "middle" | "lower" | null;
  platform?: Platform | null;
  cover_url?: string | null;
  auto_profile?: string | null;
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
  if (mode === "speaker") return "active-speaker aware";
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

function platformLabel(platform?: Platform | null) {
  if (platform === "tiktok") return "TikTok";
  if (platform === "reels") return "Instagram Reels";
  if (platform === "shorts") return "YouTube Shorts";
  return "Auto platform safe-zone";
}

function captionZoneLabel(zone?: RenderResponse["caption_zone"]) {
  if (zone === "upper") return "upper caption-safe zone";
  if (zone === "middle") return "middle caption-safe zone";
  return "lower caption-safe zone";
}

function exportFilename(title: string) {
  const clean = title
    .normalize("NFKD")
    .replace(/[^\w\s-]/g, "")
    .trim()
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 72);
  return `${clean || "clip-ai-short"}.mp4`;
}

function namedDownloadUrl(url: string, title: string) {
  const separator = url.includes("?") ? "&" : "?";
  return `${url}${separator}name=${encodeURIComponent(exportFilename(title))}`;
}

function topClipIndices(clips: Clip[], limit = 3) {
  return clips
    .map((clip, index) => ({ index, score: clip.score }))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((item) => item.index);
}

function scoreTone(score: number) {
  if (score >= 85) return "excellent";
  if (score >= 72) return "strong";
  return "solid";
}

export default function Home() {
  const [mode, setMode] = useState<Mode>("upload");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [youtubeInfo, setYoutubeInfo] = useState<YouTubeInfo | null>(null);
  const [youtubeFile, setYoutubeFile] = useState<File | null>(null);
  const [rightsConfirmed, setRightsConfirmed] = useState(false);
  const [youtubeChecking, setYoutubeChecking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [rendering, setRendering] = useState<{ index: number; kind: RenderKind } | null>(null);
  const [rendered, setRendered] = useState<Record<number, RenderResponse>>({});
  const [layouts, setLayouts] = useState<Record<number, LayoutMode>>({});
  const [captions, setCaptions] = useState<Record<number, CaptionStyle>>({});
  const [frameSizes, setFrameSizes] = useState<Record<number, FrameSize>>({});
  const [captionOffsets, setCaptionOffsets] = useState<Record<number, number>>({});
  const [platforms, setPlatforms] = useState<Record<number, Platform>>({});
  const [openedProjectTitle, setOpenedProjectTitle] = useState<string | null>(null);
  const [savedRenders, setSavedRenders] = useState<SavedRender[]>([]);
  const [copyStyles, setCopyStyles] = useState<Record<number, CopyStyle>>({});
  const [copyBusy, setCopyBusy] = useState<number | null>(null);
  const [copySaved, setCopySaved] = useState<number | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [batchRendering, setBatchRendering] = useState<{ current: number; total: number } | null>(null);

  const workerUrl = process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000";

  useEffect(() => {
    const jobId = new URLSearchParams(window.location.search).get("project");
    if (jobId) loadProject(jobId);
  }, []);

  async function loadProject(jobId: string) {
    setError("");
    setLoading(true);
    try {
      const res = await fetch(`${workerUrl}/projects/${encodeURIComponent(jobId)}`);
      const data: ProjectDetail & { detail?: string } = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not open this project");
      setOpenedProjectTitle(data.title);
      setSavedRenders(data.renders || []);
      setResult({
        source_url: data.source_url || data.title,
        mock: false,
        clips: data.clips,
        job_id: data.job_id,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open this project");
    } finally {
      setLoading(false);
    }
  }

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
    setPlatforms({});
    setSavedRenders([]);
    setCopyStyles({});
    setCopySaved(null);
    setOpenedProjectTitle(null);

    try {
      const form = new FormData();
      form.append("file", file);
      form.append("max_clips", "6");
      const res = await fetch(`${workerUrl}/analyze-upload`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Analysis failed");
      setResult(data);
      setOpenedProjectTitle(file.name);
      if (data.job_id) window.history.replaceState({}, "", `/?project=${data.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  async function submitYoutube(e: FormEvent) {
    e.preventDefault();
    setError("");
    setYoutubeChecking(true);
    setYoutubeInfo(null);
    setResult(null);
    setRendered({});
    setSavedRenders([]);
    setCopyStyles({});
    setCopySaved(null);
    setOpenedProjectTitle(null);

    try {
      const res = await fetch(`${workerUrl}/youtube-info?url=${encodeURIComponent(url)}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Could not read this YouTube link");
      setYoutubeInfo(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setYoutubeChecking(false);
    }
  }

  async function submitYoutubeOwned(e: FormEvent) {
    e.preventDefault();
    if (!youtubeInfo || !youtubeFile || !rightsConfirmed) return;
    setError("");
    setLoading(true);
    setResult(null);
    setRendered({});
    setLayouts({});
    setCaptions({});
    setFrameSizes({});
    setCaptionOffsets({});
    setPlatforms({});

    try {
      const form = new FormData();
      form.append("source_url", youtubeInfo.source_url);
      form.append("rights_confirmed", "true");
      form.append("file", youtubeFile);
      form.append("max_clips", "6");
      form.append("title", youtubeInfo.title);
      if (youtubeInfo.author_name) form.append("author_name", youtubeInfo.author_name);
      if (youtubeInfo.thumbnail_url) form.append("thumbnail_url", youtubeInfo.thumbnail_url);
      const res = await fetch(`${workerUrl}/analyze-youtube-owned`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "YouTube project analysis failed");
      setResult(data);
      setOpenedProjectTitle(youtubeInfo.title);
      if (data.job_id) window.history.replaceState({}, "", `/?project=${data.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }

  function updateClipLocal(index: number, patch: Partial<Clip>) {
    setResult((current) => {
      if (!current) return current;
      const clips = [...current.clips];
      clips[index] = { ...clips[index], ...patch };
      return { ...current, clips };
    });
    setCopySaved(null);
  }

  async function regenerateCopy(index: number) {
    if (!result?.job_id) return;
    setError("");
    setCopyBusy(index);
    setCopySaved(null);
    try {
      const res = await fetch(`${workerUrl}/projects/${result.job_id}/clips/${index}/generate-copy`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ style: copyStyles[index] || "auto" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not regenerate title");
      updateClipLocal(index, { title: data.title, social_caption: data.social_caption });
      setCopySaved(index);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not regenerate clip copy");
    } finally {
      setCopyBusy(null);
    }
  }

  async function saveCopy(index: number) {
    if (!result?.job_id) return;
    const clip = result.clips[index];
    if (!clip) return;
    setError("");
    setCopyBusy(index);
    setCopySaved(null);
    try {
      const res = await fetch(`${workerUrl}/projects/${result.job_id}/clips/${index}/copy`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ title: clip.title, social_caption: clip.social_caption || "" }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not save title");
      updateClipLocal(index, { title: data.title, social_caption: data.social_caption });
      setCopySaved(index);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save clip copy");
    } finally {
      setCopyBusy(null);
    }
  }

  async function copyToClipboard(key: string, text: string) {
    if (!text.trim()) return;
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      window.setTimeout(() => setCopied((current) => current === key ? null : current), 1600);
    } catch {
      setError("Could not copy to the clipboard. Select the text and copy it manually.");
    }
  }

  async function renderMedia(clip: Clip, index: number, kind: RenderKind, quiet = false): Promise<boolean> {
    if (!result?.job_id) {
      setError("This result does not have a real uploaded source attached.");
      return false;
    }

    if (!quiet) setError("");
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
        body.frame_size = frameSizes[index] || "auto";
        body.caption_offset_ms = captionOffsets[index] || 0;
        body.platform = platforms[index] || "auto";
      }

      const res = await fetch(`${workerUrl}${endpoint}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || data.error || "Render failed");
      setRendered((current) => ({ ...current, [index]: data }));
      const projectRes = await fetch(`${workerUrl}/projects/${result.job_id}`);
      if (projectRes.ok) {
        const projectData: ProjectDetail = await projectRes.json();
        setSavedRenders(projectData.renders || []);
      }
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong while rendering");
      return false;
    } finally {
      setRendering(null);
    }
  }

  async function renderBestThree() {
    if (!result?.job_id || batchRendering) return;
    const indices = topClipIndices(result.clips, 3);
    if (!indices.length) return;
    setError("");
    setBatchRendering({ current: 0, total: indices.length });
    for (let step = 0; step < indices.length; step += 1) {
      const index = indices[step];
      setBatchRendering({ current: step + 1, total: indices.length });
      const ok = await renderMedia(result.clips[index], index, "short", true);
      if (!ok) break;
    }
    setBatchRendering(null);
  }

  function switchMode(nextMode: Mode) {
    setMode(nextMode);
    setError("");
    setResult(null);
    setRendered({});
    setSavedRenders([]);
    setCopyStyles({});
    setCopySaved(null);
    setOpenedProjectTitle(null);
    window.history.replaceState({}, "", "/");
    if (nextMode !== "youtube") {
      setYoutubeInfo(null);
      setYoutubeFile(null);
      setRightsConfirmed(false);
    }
  }

  const bestIndices = result ? topClipIndices(result.clips, 3) : [];

  return (
    <div className="shell">
      <nav className="nav">
        <a className="brand brandLink" href="/">Clip AI</a>
        <div className="navActions">
          <a className="navLink" href="/projects">Projects</a>
          <div className="badge">v18 · active-speaker framing</div>
        </div>
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
            <div className="youtubeFlow">
              <form className="inputCard" onSubmit={submitYoutube}>
                <input
                  className="urlInput"
                  value={url}
                  onChange={(e) => {
                    setUrl(e.target.value);
                    setYoutubeInfo(null);
                    setYoutubeFile(null);
                    setRightsConfirmed(false);
                  }}
                  placeholder="https://www.youtube.com/watch?v=..."
                  type="url"
                  required
                />
                <button className="primary" disabled={youtubeChecking || !url}>
                  {youtubeChecking ? "Checking link…" : "Check YouTube link"}
                </button>
              </form>

              {youtubeInfo && (
                <form className="youtubeImportCard" onSubmit={submitYoutubeOwned}>
                  <div className="youtubeMeta">
                    {youtubeInfo.thumbnail_url && (
                      <img src={youtubeInfo.thumbnail_url} alt="YouTube video thumbnail" />
                    )}
                    <div>
                      <span className="youtubeKicker">YouTube video recognised</span>
                      <strong>{youtubeInfo.title}</strong>
                      {youtubeInfo.author_name && <small>{youtubeInfo.author_name}</small>}
                    </div>
                  </div>

                  <div className="youtubeSourceHelp">
                    <strong>Add the source video</strong>
                    <p>For now, Clip AI uses the YouTube link for the project identity and a video file you own for the actual processing. This keeps the workflow reliable instead of depending on an unofficial downloader.</p>
                  </div>

                  <label className="compactFilePicker">
                    <span>{youtubeFile ? youtubeFile.name : "Choose matching source video"}</span>
                    <small>MP4, MOV, MKV, WEBM, M4V or AVI</small>
                    <input
                      type="file"
                      accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.m4v,.avi"
                      onChange={(e) => setYoutubeFile(e.target.files?.[0] || null)}
                    />
                  </label>

                  <label className="rightsCheck">
                    <input
                      type="checkbox"
                      checked={rightsConfirmed}
                      onChange={(e) => setRightsConfirmed(e.target.checked)}
                    />
                    <span>I own this video or have permission to process and repurpose it.</span>
                  </label>

                  <button className="primary wide" disabled={loading || !youtubeFile || !rightsConfirmed}>
                    {loading ? "Analyzing YouTube project…" : "Analyze YouTube project"}
                  </button>
                </form>
              )}
            </div>
          )}
          {error && <div className="error">{error}</div>}
        </section>

        {result && (
          <section className="results">
            <div className="resultsHead">
              <div>
                <h2>{openedProjectTitle ? openedProjectTitle : "Your strongest moments"}</h2>
                <p>{result.clips.length} candidates ranked by short-form potential.{openedProjectTitle ? " This project is saved automatically." : ""}</p>
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
                    <p><b>Auto</b> — recommended. Clip AI chooses for you and now follows the likely active speaker in multi-person dialogue when confidence is strong.</p>
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

            {savedRenders.length > 0 && (
              <details className="savedRendersPanel">
                <summary>
                  <span><strong>Saved renders</strong><small>{savedRenders.length} files already in this project</small></span>
                  <span className="guideChevron">⌄</span>
                </summary>
                <div className="savedRendersGrid">
                  {savedRenders.map((media) => (
                    <article className="savedRenderCard" key={media.filename}>
                      <video controls preload="metadata" src={`${workerUrl}${media.media_url}`} />
                      <div>
                        <span>{media.kind === "short" ? "Vertical Short" : "Original clip"}</span>
                        <a href={`${workerUrl}${media.download_url}`}>Download</a>
                      </div>
                    </article>
                  ))}
                </div>
              </details>
            )}

            {!result.mock && bestIndices.length > 0 && (
              <section className="bestPicksPanel">
                <div className="bestPicksHead">
                  <div>
                    <span className="bestEyebrow">AI EDITOR PICKS</span>
                    <h3>Best 3 moments</h3>
                    <p>These have the strongest mix of hook, standalone context, payoff and likely retention.</p>
                  </div>
                  <button
                    className="renderAllButton"
                    type="button"
                    onClick={renderBestThree}
                    disabled={rendering !== null || batchRendering !== null}
                  >
                    {batchRendering ? `Rendering ${batchRendering.current}/${batchRendering.total}…` : "Render all 3"}
                  </button>
                </div>
                <div className="bestPicksGrid">
                  {bestIndices.map((index, rank) => {
                    const clip = result.clips[index];
                    const breakdown = clip.score_breakdown || {};
                    const alreadyRendered = Boolean(rendered[index]?.kind === "short");
                    return (
                      <article className="bestPickCard" key={`best-${clip.start}-${index}`}>
                        <div className="bestPickTop">
                          <span className="bestRank">#{rank + 1}</span>
                          <span className={`bestScore ${scoreTone(clip.score)}`}>{clip.score}/100</span>
                        </div>
                        <h4>{clip.title}</h4>
                        <p className="editorNote">{clip.editor_note || clip.reasons.slice(0, 2).join(" · ")}</p>
                        {Object.keys(breakdown).length > 0 && (
                          <div className="scoreBreakdown">
                            {Object.entries(breakdown).map(([label, value]) => (
                              <div className="scoreMetric" key={label}>
                                <span>{label}</span>
                                <div><i style={{ width: `${Math.max(4, Math.min(100, value))}%` }} /></div>
                                <b>{value}</b>
                              </div>
                            ))}
                          </div>
                        )}
                        <div className="bestPickActions">
                          <span>{fmt(clip.start)} → {fmt(clip.end)}</span>
                          <button
                            type="button"
                            onClick={() => renderMedia(clip, index, "short")}
                            disabled={rendering !== null || batchRendering !== null}
                          >
                            {rendering?.index === index && rendering.kind === "short" ? "Creating…" : alreadyRendered ? "Render again" : "Create Short"}
                          </button>
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            )}

            <div className="allSuggestionsHead">
              <div>
                <span>ALL CLIP DETAILS</span>
                <h3>Fine-tune any suggestion</h3>
              </div>
              <p>Best picks are highlighted above; every candidate remains editable below.</p>
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
                const selectedFrameSize = frameSizes[index] || "auto";
                const selectedOffset = captionOffsets[index] || 0;
                const selectedPlatform = platforms[index] || "auto";

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

                    {!result.mock && result.job_id && (
                      <details className="copyPanel">
                        <summary>
                          <span>Title & post caption</span>
                          <small>Generated from the dialogue · editable</small>
                        </summary>
                        <div className="copyBody">
                          <label className="copyField">
                            <span>Clip title</span>
                            <input
                              value={clip.title}
                              maxLength={120}
                              onChange={(e) => updateClipLocal(index, { title: e.target.value })}
                              disabled={copyBusy === index}
                            />
                          </label>
                          <label className="copyField">
                            <span>Social post caption</span>
                            <textarea
                              value={clip.social_caption || ""}
                              maxLength={500}
                              rows={3}
                              placeholder="Clip AI can generate a short post caption from this dialogue."
                              onChange={(e) => updateClipLocal(index, { social_caption: e.target.value })}
                              disabled={copyBusy === index}
                            />
                          </label>
                          <div className="copyTools">
                            <label>
                              <span>Regenerate style</span>
                              <select
                                value={copyStyles[index] || "auto"}
                                onChange={(e) => setCopyStyles((current) => ({ ...current, [index]: e.target.value as CopyStyle }))}
                                disabled={copyBusy === index}
                              >
                                <option value="auto">Auto</option>
                                <option value="viral">Viral</option>
                                <option value="clean">Clean</option>
                                <option value="cinematic">Cinematic</option>
                              </select>
                            </label>
                            <button className="copyButton" type="button" onClick={() => regenerateCopy(index)} disabled={copyBusy !== null}>
                              {copyBusy === index ? "Working…" : "Regenerate"}
                            </button>
                            <button className="copyButton saveCopyButton" type="button" onClick={() => saveCopy(index)} disabled={copyBusy !== null || !clip.title.trim()}>
                              {copySaved === index ? "Saved ✓" : "Save edits"}
                            </button>
                          </div>
                          <p className="copyNote">Titles and post captions are based only on the words spoken in this selected moment. You can rewrite either before exporting.</p>
                        </div>
                      </details>
                    )}

                    <details className="whyPicked">
                      <summary>Why Clip AI picked this moment</summary>
                      {clip.score_breakdown && Object.keys(clip.score_breakdown).length > 0 && (
                        <div className="miniScoreGrid">
                          {Object.entries(clip.score_breakdown).map(([label, value]) => (
                            <span key={label}><b>{label}</b>{value}</span>
                          ))}
                        </div>
                      )}
                      {clip.editor_note && <p className="whyEditorNote">{clip.editor_note}</p>}
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
                            disabled={rendering !== null || batchRendering !== null}
                          >
                            {isShortRendering ? "Creating Short…" : "Create Short"}
                          </button>
                          <button
                            className="renderButton secondaryButton"
                            onClick={() => renderMedia(clip, index, "original")}
                            disabled={rendering !== null || batchRendering !== null}
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
                                <span>Posting to <i>Adjusts caption safe-zones</i></span>
                                <select
                                  value={selectedPlatform}
                                  onChange={(e) => setPlatforms((current) => ({ ...current, [index]: e.target.value as Platform }))}
                                  disabled={rendering !== null || batchRendering !== null}
                                >
                                  <option value="auto">Auto · recommended</option>
                                  <option value="shorts">YouTube Shorts</option>
                                  <option value="tiktok">TikTok</option>
                                  <option value="reels">Instagram Reels</option>
                                </select>
                              </label>
                              <label>
                                <span>Framing <i>How the picture fits</i></span>
                                <select
                                  value={selectedLayout}
                                  onChange={(e) => setLayouts((current) => ({ ...current, [index]: e.target.value as LayoutMode }))}
                                  disabled={rendering !== null || batchRendering !== null}
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
                                  disabled={rendering !== null || batchRendering !== null}
                                >
                                  <option value="auto">Auto · recommended</option>
                                  <option value="compact">Compact</option>
                                  <option value="balanced">Balanced</option>
                                  <option value="immersive">Immersive</option>
                                </select>
                              </label>
                              <label>
                                <span>Captions <i>Text personality</i></span>
                                <select
                                  value={selectedCaption}
                                  onChange={(e) => setCaptions((current) => ({ ...current, [index]: e.target.value as CaptionStyle }))}
                                  disabled={rendering !== null || batchRendering !== null}
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
                                  disabled={rendering !== null || batchRendering !== null}
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
                        {isVertical ? (
                          <section className="readyPost">
                            <div className="readyPostHead">
                              <div>
                                <span className="readyKicker">Ready to post</span>
                                <strong>Your video, title and post caption in one place.</strong>
                              </div>
                              <span className="readyCheck">✓</span>
                            </div>

                            <div className="readyPostGrid">
                              <div className="thumbnailPreview" aria-label="Suggested cover preview">
                                {renderedClip.cover_url ? (
                                  <img src={`${workerUrl}${renderedClip.cover_url}`} alt="Suggested cover frame" />
                                ) : (
                                  <video muted playsInline preload="metadata" src={playableUrl} />
                                )}
                                <div className="thumbnailShade" />
                                <div className="thumbnailTitle">{clip.title}</div>
                                <span>Suggested cover</span>
                              </div>

                              <div className="readyCopyStack">
                                <div className="readyField">
                                  <div>
                                    <span>Title</span>
                                    <p>{clip.title}</p>
                                  </div>
                                  <button type="button" onClick={() => copyToClipboard(`${index}-title`, clip.title)}>
                                    {copied === `${index}-title` ? "Copied ✓" : "Copy"}
                                  </button>
                                </div>

                                <div className="readyField">
                                  <div>
                                    <span>Post caption</span>
                                    <p className="postCaptionText">{clip.social_caption || "No post caption yet. Open Title & post caption to generate one."}</p>
                                  </div>
                                  <button
                                    type="button"
                                    disabled={!clip.social_caption}
                                    onClick={() => copyToClipboard(`${index}-caption`, clip.social_caption || "")}
                                  >
                                    {copied === `${index}-caption` ? "Copied ✓" : "Copy"}
                                  </button>
                                </div>

                                <button
                                  className="copyBundleButton"
                                  type="button"
                                  disabled={!clip.social_caption}
                                  onClick={() => copyToClipboard(`${index}-bundle`, `${clip.title}\n\n${clip.social_caption || ""}`)}
                                >
                                  {copied === `${index}-bundle` ? "Title + caption copied ✓" : "Copy title + caption"}
                                </button>
                              </div>
                            </div>

                            <div className="readyDownloadRow">
                              <div>
                                <span>Export filename</span>
                                <strong>{exportFilename(clip.title)}</strong>
                              </div>
                              <a className="readyDownload" href={namedDownloadUrl(downloadUrl, clip.title)}>Download Short</a>
                            </div>

                            <details className="exportDetails">
                              <summary>Technical details</summary>
                              <p>
                                {Math.round(renderedClip.duration)} sec · {renderedClip.auto_profile ? `${renderedClip.auto_profile} · ` : ""}{platformLabel(renderedClip.platform)} · {layoutLabel(renderedClip.layout_mode)} · {frameSizeLabel(renderedClip.frame_size)} · {captionLabel(renderedClip.caption_style)} · {renderedClip.word_timed_captions ? "word-synced" : "legacy timing"} · {captionZoneLabel(renderedClip.caption_zone)} · {framingLabel(renderedClip.framing_mode)}{renderedClip.active_speaker_switches ? ` · ${renderedClip.active_speaker_switches} speaker switch${renderedClip.active_speaker_switches === 1 ? "" : "es"}` : ""}
                              </p>
                            </details>
                          </section>
                        ) : (
                          <div className="renderMeta">
                            <span>{Math.round(renderedClip.duration)} sec · original frame</span>
                            <a className="downloadLink" href={namedDownloadUrl(downloadUrl, clip.title)}>Download MP4</a>
                          </div>
                        )}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
            <div className="footNote">v18 adds conservative active-speaker framing for multi-person dialogue while falling back to group framing when confidence is weak.</div>
          </section>
        )}
      </main>
    </div>
  );
}
