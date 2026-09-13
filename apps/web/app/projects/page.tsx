"use client";

import { useEffect, useState } from "react";

type ProjectSummary = {
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
  status?: string;
  processing_profile?: string;
  content_type?: string;
  resolved_content_type?: string;
  content_structure?: string;
  resolved_content_structure?: string;
  subject_hint?: string | null;
};

function humanBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function dateLabel(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Saved project" : date.toLocaleString();
}

export default function ProjectsPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [resuming, setResuming] = useState<string | null>(null);
  const workerUrl = process.env.NEXT_PUBLIC_WORKER_URL || "http://127.0.0.1:8000";

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const res = await fetch(`${workerUrl}/projects`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not load projects");
      setProjects(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load projects");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, []);

  async function removeProject(project: ProjectSummary) {
    if (!window.confirm(`Delete “${project.title}” and its local video files? This cannot be undone.`)) return;
    try {
      const res = await fetch(`${workerUrl}/projects/${project.job_id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not delete project");
      setProjects((items) => items.filter((item) => item.job_id !== project.job_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete project");
    }
  }

  async function resumeProject(project: ProjectSummary) {
    setResuming(project.job_id); setError("");
    try {
      const res = await fetch(`${workerUrl}/projects/${project.job_id}/resume`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Could not resume project");
      window.location.href = `/?project=${project.job_id}`;
    } catch (err) { setError(err instanceof Error ? err.message : "Could not resume project"); }
    finally { setResuming(null); }
  }

  const visibleProjects = projects.filter((project) => {
    const matchesQuery = !query.trim() || `${project.title} ${project.author_name || ""}`.toLowerCase().includes(query.trim().toLowerCase());
    const status = project.status || "ready";
    const matchesFilter = filter === "all" || (filter === "ready" ? status === "ready" : (filter === "needs-attention" ? status !== "ready" : project.source_type === filter));
    return matchesQuery && matchesFilter;
  });

  return (
    <div className="shell">
      <nav className="nav">
        <a className="brand brandLink" href="/">Clip AI</a>
        <div className="navActions">
          <a className="navLink activeNav" href="/projects">Projects</a>
          <a className="navLink" href="/status">System</a>
          <a className="navLink" href="/">Create</a>
          <div className="badge">v22 · M2 smarter clips</div>
        </div>
      </nav>

      <main className="main projectsMain">
        <section className="projectsHead">
          <div>
            <div className="eyebrow">Your local workspace</div>
            <h1>Projects</h1>
            <p className="sub">Reopen previous analyses and rendered Shorts. Everything here lives on this PC for now.</p>
          </div>
          <a className="primary projectsNew" href="/">+ New project</a>
        </section>

        {error && <div className="error">{error}</div>}
        {!loading && projects.length > 0 && (
          <div className="projectToolbar">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search projects…" aria-label="Search projects" />
            <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label="Filter projects">
              <option value="all">All projects</option>
              <option value="ready">Ready</option>
              <option value="needs-attention">Needs attention / resumable</option>
              <option value="upload">Uploads</option>
              <option value="youtube">YouTube</option>
            </select>
          </div>
        )}
        {loading ? (
          <div className="projectsEmpty">Loading projects…</div>
        ) : projects.length === 0 ? (
          <div className="projectsEmpty">
            <strong>No saved projects yet</strong>
            <p>Analyse a video once and it will appear here automatically.</p>
            <a className="primary" href="/">Create your first project</a>
          </div>
        ) : (
          <div className="projectsGrid">
            {visibleProjects.map((project) => (
              <article className="projectCard" key={project.job_id}>
                <div className="projectThumb">
                  {project.thumbnail_url ? (
                    <img src={project.thumbnail_url} alt="" />
                  ) : (
                    <div className="projectPlaceholder">{project.source_type === "youtube" ? "▶" : "↑"}</div>
                  )}
                  <span>{project.source_type === "youtube" ? "YouTube" : "Upload"}</span>
                </div>
                <div className="projectBody">
                  <div style={{display:"flex",justifyContent:"space-between",gap:8,alignItems:"flex-start"}}><h2>{project.title}</h2><span className={`projectStatus ${project.status || "ready"}`}>{project.status || "ready"}</span></div>
                  {project.author_name && <p className="projectAuthor">{project.author_name}</p>}
                  <p className="projectDate">Updated {dateLabel(project.updated_at)}</p>
                  <div className="projectStats">
                    <span>{project.clip_count} suggestions</span>
                    <span>{project.render_count} renders</span>
                    <span>{humanBytes(project.storage_bytes)}</span>
                    <span>{project.processing_profile || "balanced"}</span>
                    <span>{(project.resolved_content_type || project.content_type || "other").replace("film-tv", "film / TV").replace("meme-comedy", "meme / comedy")}</span>
                    <span>{(project.resolved_content_structure || project.content_structure || "single-story").replace("single-story", "single story")}</span>
                  </div>
                  <div className="projectActions">
                    <a className="projectOpen" href={`/?project=${project.job_id}`}>Open project</a>
                    {(project.status && project.status !== "ready") && <button className="resumeButton" onClick={() => resumeProject(project)} disabled={resuming === project.job_id}>{resuming === project.job_id ? "Resuming…" : "Resume"}</button>}
                    <button onClick={() => removeProject(project)}>Delete</button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
