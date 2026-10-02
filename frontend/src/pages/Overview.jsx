import React, { useEffect, useState } from 'react';
import { analysisRequest, analysisStorageKey } from '../api';
import { runCancellableRequest, requestErrorMessage } from '../requestLifecycle';
import HeroArt from '../components/HeroArt';
import Icon from '../components/Icon';

export default function Overview() {
  const [workspace, setWorkspace] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const id = sessionStorage.getItem(analysisStorageKey);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    setLoading(true); setError(null);
    runCancellableRequest(async () => {
      const [profile, analytics, detection] = await Promise.all([
        analysisRequest(`/${id}`, {}, controller.signal),
        analysisRequest(`/${id}/analytics`, {}, controller.signal),
        analysisRequest(`/${id}/issues`, {}, controller.signal),
      ]);
      return { profile, analytics, detection };
    }, controller.signal, {
      success: data => { setWorkspace(data); setError(null); },
      failure: failure => { setWorkspace(null); setError(requestErrorMessage(failure, 'Unable to load your workspace. Check your connection and retry.')); },
      settled: () => setLoading(false),
    });
    return () => controller.abort();
  }, [id, attempt]);
  useEffect(() => {
    if (!workspace) return;
    const timer = setTimeout(() => { setWorkspace(null); setError('This analysis expired. Load data to continue.'); }, Math.max(0, Date.parse(workspace.profile.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [workspace]);

  return <>
    <section className="overview-hero">
      <div className="hero-copy"><p className="eyebrow">Business workspace</p>
      <h2>Welcome Judges</h2>
      <p>Your business decision workspace is ready.</p>
      <p className="muted">Explore verified insights, investigate risks, and simulate your next move.</p>
      {workspace && <p className="hero-status">Business data loaded · {workspace.profile.profile.row_count} observations · {workspace.detection.issues.length} issues detected</p>}
      <div className="actions"><a className="button hero-primary" href="/data">{workspace ? 'Manage business data' : 'Load demo or upload data'} →</a><a className="button hero-secondary" href="/simulator">Test a decision →</a></div></div>
      <HeroArt />
    </section>
    {loading && <p role="status">Loading your business workspace…</p>}
    {error && <section><p role="alert" className="notice">{error}</p><button onClick={() => setAttempt(value => value + 1)}>Retry workspace</button><p><a href="/data">Manage data</a></p></section>}
    {!id && <section><h3>Start with your business data</h3><p>Load the synthetic demo or upload a validated dataset to see actual business results and detected issues.</p><a href="/data">Open data workspace →</a></section>}
    <div className="section-heading"><h3>Your next move</h3><span>From evidence to action</span></div>
    <div className="workflow-grid">{[
      ['insights', '01 / UNDERSTAND', 'Explore your insights', 'See what changed, with verified metrics and traceable evidence.', '/insights'],
      ['decisions', '02 / INVESTIGATE', 'Consider a decision', 'Review detected issues, reasoning and the evidence behind each action.', '/decisions'],
      ['simulator', '03 / TEST', 'Test before you act', 'Compare a hypothetical scenario with the baseline. You make the call.', '/simulator'],
    ].map(([icon, step, title, copy, href]) => <a className={`workflow-card workflow-${icon}`} key={href} href={href}><div className="workflow-top"><span>{step}</span><Icon name={icon} /></div><h3>{title}</h3><p>{copy}</p><span className="workflow-link">Open workspace <span aria-hidden="true">↗</span></span></a>)}</div>
    {workspace && <>
      <section className="dataset-summary"><div className="section-heading"><h3>Business snapshot</h3><span className="badge status-good">Business data loaded</span></div><p className="muted">{workspace.profile.source === 'demo' ? 'Synthetic demo business' : 'Validated business dataset'} · {workspace.profile.profile.row_count} observations · {workspace.analytics.period.start} to {workspace.analytics.period.end}</p>
        <dl className="profile-grid overview-metrics">{[['Reported revenue', workspace.analytics.overview.total_revenue], ['Units sold', workspace.analytics.overview.total_units_sold], ['Latest inventory', workspace.analytics.overview.current_inventory_units]].map(([label, metric]) => <div key={label}><dt>{label}</dt><dd>{metric.status === 'supported' ? metric.value : 'Unsupported'}<small> {metric.unit}</small></dd></div>)}</dl>
        <a href="/insights">Explore business insights →</a>
      </section>
      <section><div className="section-heading"><h3>Issues to investigate</h3><span className="badge">{workspace.detection.issues.length} detected issues</span></div><p className="muted">Review evidence and unsupported evaluations before acting.</p>
        <div className="priority-grid">{workspace.detection.issues.slice(0, 3).map(issue => <article className="priority-card" key={issue.issue_id}><span className={`badge severity-${issue.severity.toLowerCase()}`}>{issue.severity}</span><h4>{issue.entity_name}</h4><p className="issue-type">{issue.title}</p><p>{issue.summary}</p><div className="actions"><a href={`/decisions/${encodeURIComponent(issue.issue_id)}`}>Investigate decision →</a><a href={`/simulator?product_id=${encodeURIComponent(issue.entity_id)}`}>Simulate an action →</a></div></article>)}</div>
        <a href="/insights">View all issues and evidence →</a>
      </section>
    </>}
  </>;
}
