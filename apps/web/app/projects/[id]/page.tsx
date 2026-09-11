"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";

type Project = {
  id: string;
  name: string;
  status: string;
  timezone: string;
  target_date: string | null;
  row_version: number;
};

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [name, setName] = useState("");
  const [targetDate, setTargetDate] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    api<Project>(`/api/v1/projects/${id}`)
      .then((nextProject) => {
        if (!active) return;
        setProject(nextProject); setName(nextProject.name); setTargetDate(nextProject.target_date ?? "");
      })
      .catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "Unable to load project"); });
    return () => { active = false; };
  }, [id]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!project) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const updated = await api<Project>(`/api/v1/projects/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ expected_row_version: project.row_version, name, target_date: targetDate || null }),
      });
      setProject(updated); setName(updated.name); setTargetDate(updated.target_date ?? "");
      setMessage("Project updated.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update project");
    } finally { setBusy(false); }
  }

  async function disable() {
    if (!project) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await api<Project>(`/api/v1/projects/${id}?expected_row_version=${project.row_version}`, { method: "DELETE" });
      router.push("/projects");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to disable project");
      setBusy(false);
    }
  }

  return <>
    <p><Link href="/projects">← Back to projects</Link></p>
    <p className="eyebrow muted">Project boundary</p><h1>{project?.name ?? "Project"}</h1>
    {project && <p className="notice">{project.status.replaceAll("_", " ")} · {project.timezone} · row version {project.row_version}</p>}
    <p className="lede">Projects remain paused until a later contract-confirmation phase. Disabling a project prevents it from becoming eligible for new work.</p>
    {error && <p className="error">{error}</p>}
    {message && <p className="success">{message}</p>}
    <div className="row"><Link className="button" href={`/projects/${id}/contract`}>Contract documents</Link><Link className="button" href={`/projects/${id}/scope`}>Review scope</Link><Link className="button" href={`/projects/${id}/routing`}>Routing diagnostics</Link></div>\n    <form className="card stack" onSubmit={save}>
      <div className="row">
        <label>Name<input value={name} onChange={(event) => setName(event.target.value)} required /></label>
        <label>Target date<input type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} /></label>
      </div>
      <div className="row"><button disabled={busy || !project}>Save project</button><button className="danger" type="button" disabled={busy || !project || project.status === "DELETION_PENDING"} onClick={disable}>Disable project</button></div>
    </form>
  </>;
}
