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
};

function fmt(seconds: number) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

export default function Home() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AnalyzeResponse | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    setResult(null);

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

  return (
    <div className="shell">
      <nav className="nav">
        <div className="brand">Clip AI</div>
        <div className="badge">Milestone 1</div>
      </nav>

      <main className="main">
        <section className="hero">
          <div className="eyebrow">Long video → short-form gold</div>
          <h1>Find the clips worth posting.</h1>
          <p className="sub">
            Paste a YouTube link. AI scans the content, identifies self-contained moments with strong hooks,
            and ranks the best candidates for Shorts, Reels and TikTok.
          </p>

          <form className="inputCard" onSubmit={submit}>
            <input
              className="urlInput"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://www.youtube.com/watch?v=..."
              type="url"
              required
            />
            <button className="primary" disabled={loading || !url}>
              {loading ? "Finding moments…" : "Generate clips"}
            </button>
          </form>
          {error && <div className="error">{error}</div>}
        </section>

        {result && (
          <section className="results">
            <div className="resultsHead">
              <div>
                <h2>Your strongest moments</h2>
                <p>{result.clips.length} candidates ranked by short-form potential.</p>
              </div>
              {result.mock && <div className="badge">Demo analysis</div>}
            </div>

            <div className="clipGrid">
              {result.clips.map((clip, index) => (
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
                </article>
              ))}
            </div>
            <div className="footNote">Next: cut these timestamps automatically, smart-crop to 9:16 and burn animated captions.</div>
          </section>
        )}
      </main>
    </div>
  );
}
