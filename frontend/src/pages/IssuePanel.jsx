import React, { useEffect, useMemo, useState } from 'react';
import { analysisRequest } from '../api';

const groups = {
  All: null,
  Demand: ['demand_decline', 'demand_spike'],
  Inventory: ['stockout_risk', 'excess_inventory'],
  Anomalies: ['sales_anomaly'],
};
const reasons = {
  date_boundary: 'Dates cannot represent the required history window.',
  insufficient_history: 'Not enough history for both comparison windows.',
  incomplete_daily_coverage: 'Required daily observations are missing.',
  product_missing_in_period: 'Product observations are absent from a comparison window.',
  zero_previous_demand: 'Previous demand is zero; percentage change is undefined.',
  zero_recent_demand: 'Recent demand is zero; depletion coverage cannot be calculated.',
  stale_inventory_snapshot: 'Inventory was not observed on the dataset’s latest date.',
  insufficient_anomaly_samples: 'Too few observed baseline days for the anomaly rule.',
  zero_iqr: 'Baseline IQR is zero; the anomaly rule cannot distinguish outliers reliably.',
};
const statuses = { issue_detected: 'Issue detected', evaluated_no_issue: 'Evaluated — no issue', unsupported: 'Unsupported' };
const range = (period) => period ? `${period.start} to ${period.end}` : 'Not applicable';

function Pages({ page, count, onChange, label }) {
  const pages = Math.ceil(count / 20);
  return pages > 1 && <div className="actions">
    <button className="secondary" disabled={page === 0} onClick={() => onChange(page - 1)}>Previous {label}</button>
    <span>Page {page + 1} of {pages}</span>
    <button className="secondary" disabled={page + 1 >= pages} onClick={() => onChange(page + 1)}>Next {label}</button>
  </div>;
}

export default function IssuePanel({ analysisId }) {
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const [filter, setFilter] = useState('All');
  const [page, setPage] = useState(0);
  const [supportPage, setSupportPage] = useState(0);
  const [selected, setSelected] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => controller.abort(), 60000);
    setResult(null); setError(null); setSelected(null); setPage(0); setSupportPage(0);
    analysisRequest(`/${encodeURIComponent(analysisId)}/issues`, {}, controller.signal)
      .then((data) => { if (active) setResult(data); })
      .catch((failure) => { if (active) setError(failure.name === 'AbortError'
        ? 'Issue detection timed out. Please retry.' : failure.message || 'Could not load issues. Please retry.'); })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; controller.abort(); clearTimeout(timeout); };
  }, [analysisId, attempt]);
  const evidenceById = useMemo(() => new Map((result?.evidence || []).map((item) => [item.evidence_id, item])), [result]);
  const matches = (item) => !groups[filter] || groups[filter].includes(item.issue_type);
  const issues = result?.issues.filter(matches) || [];
  const evaluations = result?.evaluations.filter(matches) || [];
  return <section aria-labelledby="issues-title">
    <h2 id="issues-title">Issues and evidence</h2>
    <p>Deterministic conditions from observed data. Severity comes from documented backend rules; these are not recommendations.</p>
    {!result && !error && <p role="status">Checking supported detector rules…</p>}
    {error && <><p role="alert" className="notice">{error}</p><button onClick={() => setAttempt(attempt + 1)}>Retry issue detection</button></>}
    {result && <>
      <p>Detection period: {range(result.detection_period)}. Dates refer to the dataset, not today.</p>
      <div className="actions" aria-label="Issue filters">{Object.keys(groups).map((name) =>
        <button className="secondary" key={name} aria-pressed={filter === name} onClick={() => {
          setFilter(name); setPage(0); setSupportPage(0); setSelected(null);
        }}>{name}</button>)}</div>
      {!issues.length && <p>No detected issues in this filter. Check unsupported evaluations below before drawing conclusions.</p>}
      {issues.slice(page * 20, (page + 1) * 20).map((issue) => <article className="issue-card" key={issue.issue_id}>
        <h3>{issue.title} · {issue.entity_name}</h3>
        <p><strong>{issue.severity}</strong> · Product {issue.entity_id}
          {issue.observation_date && <> · Observation {issue.observation_date}</>}</p>
        <p>{issue.summary}</p>
        <button className="secondary" onClick={() => setSelected(issue)}>View evidence: {issue.title} · {issue.entity_name}{issue.observation_date ? ` · ${issue.observation_date}` : ''}</button>
      </article>)}
      <Pages page={page} count={issues.length} onChange={setPage} label="issues" />
      {selected && <section className="evidence-panel" aria-labelledby="evidence-title">
        <h3 id="evidence-title">Evidence: {selected.title} · {selected.entity_name}</h3>
        <button className="secondary" onClick={() => setSelected(null)}>Close evidence</button>
        <p>Dataset as-of date: {selected.detected_at} · Detector: {selected.detector_version}</p>
        <p className="column-list">Issue ID: {selected.issue_id}</p>
        <p>Ratios are rounded for display. Exact fractions and inputs below preserve the values used by the detector.</p>
        {selected.evidence_ids.map((id) => {
          const item = evidenceById.get(id);
          return item ? <article className="evidence-item" key={id}>
            <h4>{item.metric}: {item.value} {item.unit}</h4>
            <p>Period: {range(item.period)} · Comparison/baseline: {range(item.comparison_period)}</p>
            {item.observation_date && <p>Observed on: {item.observation_date}</p>}
            <p>Source: {item.source.name} ({item.source.kind})</p>
            <p>Method: {item.method}</p>
            <p>Exact value: {item.exact.numerator} / {item.exact.denominator}</p>
            <details><summary>Calculation inputs and evidence ID</summary>
              <pre>{JSON.stringify(item.inputs, null, 2)}</pre><p className="column-list">{id}</p>
            </details>
          </article> : <p role="alert" key={id}>Referenced evidence is unavailable. Do not rely on this issue.</p>;
        })}
      </section>}
      <h3>Detector evaluations</h3>
      <p>“Evaluated — no issue” applies only to that rule. “Unsupported” means the data could not support evaluation.</p>
      <div className="table-scroll"><table><caption>Support and abstention</caption>
        <thead><tr><th scope="col">Product</th><th scope="col">Detector</th><th scope="col">Status</th><th scope="col">Reason</th></tr></thead>
        <tbody>{evaluations.slice(supportPage * 20, (supportPage + 1) * 20).map((item) =>
          <tr key={`${item.entity_id}:${item.detector_version}`}><th scope="row">{item.entity_name}</th>
            <td>{item.detector_version}</td><td>{statuses[item.status]}</td><td>{reasons[item.reason] || item.reason || '—'}</td></tr>)}</tbody>
      </table></div>
      <Pages page={supportPage} count={evaluations.length} onChange={setSupportPage} label="evaluations" />
    </>}
  </section>;
}
