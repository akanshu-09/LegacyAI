import React, { useEffect, useState } from 'react';
import { analysisRequest, analysisStorageKey } from '../api';

export default function Decisions() {
  const [analysisId, setAnalysisId] = useState(null);
  const [issuesData, setIssuesData] = useState(null);
  const [selectedIssueId, setSelectedIssueId] = useState(null);
  const [decision, setDecision] = useState(null);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [loadingDecision, setLoadingDecision] = useState(false);
  const [error, setError] = useState(null);
  const [decisionError, setDecisionError] = useState(null);

  useEffect(() => {
    const id = sessionStorage.getItem(analysisStorageKey);
    if (!id) return;
    setAnalysisId(id);

    // Extract path issueId if navigating directly to /decisions/:issueId
    const pathname = window.location.pathname;
    const match = pathname.match(/\/decisions\/(.+)/);
    const pathIssueId = match ? decodeURIComponent(match[1]) : null;

    setLoadingIssues(true);
    const controller = new AbortController();

    analysisRequest(`/${id}/issues`, {}, controller.signal)
      .then((data) => {
        setIssuesData(data);
        if (pathIssueId && data.issues?.some((i) => i.issue_id === pathIssueId)) {
          setSelectedIssueId(pathIssueId);
        } else if (data.issues && data.issues.length > 0) {
          setSelectedIssueId(data.issues[0].issue_id);
        }
      })
      .catch((err) => setError(err.message || 'Failed to load issues.'))
      .finally(() => setLoadingIssues(false));

    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!analysisId || !selectedIssueId) return;

    setLoadingDecision(true);
    setDecisionError(null);
    const controller = new AbortController();

    analysisRequest(`/${analysisId}/decisions/${encodeURIComponent(selectedIssueId)}`, { method: 'POST' }, controller.signal)
      .then((data) => {
        setDecision(data);
      })
      .catch((err) => {
        setDecisionError(err.message || 'Failed to generate AI decision.');
      })
      .finally(() => setLoadingDecision(false));

    return () => controller.abort();
  }, [analysisId, selectedIssueId]);

  if (!analysisId) {
    return (
      <section>
        <h2>Decision Workspace</h2>
        <p>No active session found. Upload a dataset or load synthetic demo data to explore evidence-backed AI decisions.</p>
        <a href="/data">Go to Data Workspace →</a>
      </section>
    );
  }

  const issues = issuesData?.issues || [];
  const currentIssue = issues.find((i) => i.issue_id === selectedIssueId) || decision?.issue;

  return (
    <div>
      <section aria-labelledby="decisions-heading">
        <h2 id="decisions-heading">AI Decision Engine</h2>
        <p>Ground AI reasoning strictly in verified dataset evidence. Human makes final operational decisions.</p>

        {loadingIssues && <p role="status">Loading detected issues…</p>}
        {error && <p role="alert" className="notice">{error}</p>}

        {issues.length > 0 && (
          <div style={{ marginBottom: '1.5rem' }}>
            <label htmlFor="issue-select" style={{ fontWeight: 'bold', display: 'block', marginBottom: '0.5rem' }}>
              Select Detected Issue to Investigate:
            </label>
            <select
              id="issue-select"
              value={selectedIssueId || ''}
              onChange={(e) => {
                const newId = e.target.value;
                setSelectedIssueId(newId);
                window.history.replaceState(null, '', `/decisions/${encodeURIComponent(newId)}`);
              }}
              style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid #ccc', minWidth: '300px' }}
            >
              {issues.map((i) => (
                <option key={i.issue_id} value={i.issue_id}>
                  [{i.severity}] {i.entity_name} - {i.title}
                </option>
              ))}
            </select>
          </div>
        )}
      </section>

      {selectedIssueId && (
        <section aria-labelledby="issue-detail-heading">
          {currentIssue && (
            <div style={{ background: '#f8fafc', padding: '1.25rem', borderRadius: '8px', border: '1px solid #cbd5e1', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 id="issue-detail-heading" style={{ margin: 0 }}>
                  {currentIssue.title}: {currentIssue.entity_name}
                </h3>
                <span className={`badge severity-${(currentIssue.severity || 'LOW').toLowerCase()}`} style={{ fontWeight: 'bold' }}>
                  {currentIssue.severity} SEVERITY
                </span>
              </div>
              <p style={{ marginTop: '0.5rem', color: '#475569' }}>{currentIssue.summary}</p>
              <a href={`/simulator?product_id=${encodeURIComponent(currentIssue.entity_id)}`}>Simulate this product with your own assumptions →</a>
            </div>
          )}

          {loadingDecision && <p role="status">Generating AI decision reasoning & verifying claims…</p>}
          {decisionError && <p role="alert" className="notice">{decisionError}</p>}

          {decision && (
            <div>
              {/* Verification Status Badge */}
              <div style={{ margin: '1rem 0', padding: '0.75rem 1rem', borderRadius: '6px', border: '1px solid', backgroundColor: decision.verification?.status === 'verified' ? '#f0fdf4' : decision.verification?.status === 'partially_verified' ? '#fefce8' : decision.ai_available ? '#fef2f2' : '#f1f5f9', borderColor: decision.verification?.status === 'verified' ? '#86efac' : decision.verification?.status === 'partially_verified' ? '#fde047' : decision.ai_available ? '#fca5a5' : '#cbd5e1' }}>
                <strong>Claim Verification Status: </strong>
                {decision.verification?.status === 'verified' ? (
                  <span style={{ color: '#166534', fontWeight: 'bold' }}>✓ Verified against dataset evidence</span>
                ) : decision.verification?.status === 'partially_verified' ? (
                  <span style={{ color: '#854d0e', fontWeight: 'bold' }}>⚠️ Partially verified (some ungrounded citations)</span>
                ) : decision.ai_available ? (
                  <span style={{ color: '#991b1b', fontWeight: 'bold' }}>✗ Claims unverified or rejected</span>
                ) : (
                  <span style={{ color: '#475569', fontWeight: 'bold' }}>⚪ AI reasoning unavailable</span>
                )}
                <ul style={{ margin: '0.5rem 0 0 1.25rem', fontSize: '0.9rem' }}>
                  {decision.verification?.details?.map((d, idx) => (
                    <li key={idx}>{d}</li>
                  ))}
                </ul>
              </div>

              {!decision.ai_available && (
                <div className="notice" style={{ background: '#f8fafc', borderColor: '#94a3b8' }}>
                  <p><strong>AI Provider Status:</strong> {decision.ai_error || 'AI provider unavailable.'}</p>
                  <p style={{ fontSize: '0.9rem' }}>Deterministic analytics, issue detection, and verified evidence remain fully operational below.</p>
                </div>
              )}

              {decision.ai_available && decision.reasoning && (
                <div style={{ display: 'grid', gap: '1.5rem', marginTop: '1.5rem' }}>
                  {/* Recommended Action Card */}
                  <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '1.25rem' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', color: '#1e40af' }}>Recommended Operational Action</h4>
                    <p style={{ fontSize: '1.1rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>
                      {decision.reasoning.recommendation?.action}
                    </p>
                    <p style={{ margin: 0, fontSize: '0.95rem', color: '#1e3a8a' }}>
                      Target: <strong>{decision.reasoning.recommendation?.target}</strong> | Timeframe: <strong>{decision.reasoning.recommendation?.timeframe_days} days</strong>
                    </p>
                  </div>

                  {/* Summary */}
                  <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1.25rem' }}>
                    <h4 style={{ marginTop: 0 }}>Reasoning Summary</h4>
                    <p>{decision.reasoning.summary}</p>
                  </div>

                  {/* Root Cause Explanations */}
                  {decision.reasoning.root_causes?.length > 0 && (
                    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1.25rem' }}>
                      <h4 style={{ marginTop: 0 }}>Plausible Root Cause Analysis</h4>
                      <ul>
                        {decision.reasoning.root_causes.map((rc, idx) => (
                          <li key={idx} style={{ marginBottom: '0.5rem' }}>
                            {rc.explanation}
                            {rc.evidence_ids?.length > 0 && (
                              <span style={{ fontSize: '0.85rem', color: '#64748b', marginLeft: '0.5rem' }}>
                                (Cites: {rc.evidence_ids.join(', ')})
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Assumptions & Uncertainties Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1rem' }}>
                      <h5 style={{ marginTop: 0 }}>Explicit Assumptions</h5>
                      <ul style={{ paddingLeft: '1.25rem', fontSize: '0.9rem' }}>
                        {decision.reasoning.assumptions?.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1rem' }}>
                      <h5 style={{ marginTop: 0 }}>Uncertainties & Absent Context</h5>
                      <ul style={{ paddingLeft: '1.25rem', fontSize: '0.9rem' }}>
                        {decision.reasoning.uncertainties?.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  {/* What Would Change This Decision */}
                  {decision.reasoning.what_would_change_this_decision?.length > 0 && (
                    <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1rem' }}>
                      <h5 style={{ marginTop: 0 }}>What Would Change This Decision</h5>
                      <ul style={{ paddingLeft: '1.25rem', fontSize: '0.9rem' }}>
                        {decision.reasoning.what_would_change_this_decision.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Verified Evidence Details */}
              <div style={{ marginTop: '2rem' }}>
                <h4>Underlying Verified Evidence</h4>
                {decision.cited_evidence?.length === 0 ? (
                  <p>No cited evidence objects available.</p>
                ) : (
                  <div style={{ display: 'grid', gap: '1rem' }}>
                    {decision.cited_evidence?.map((ev) => (
                      <div key={ev.evidence_id} className="evidence-panel">
                        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                          <strong>{ev.metric}</strong>
                          <span style={{ fontSize: '0.85rem', color: '#64748b' }}>{ev.evidence_id}</span>
                        </div>
                        <p style={{ margin: '0.25rem 0' }}>
                          Value: <strong>{ev.value?.display_string || String(ev.value)}</strong> {ev.unit}
                        </p>
                        <p style={{ margin: '0.25rem 0', fontSize: '0.85rem', color: '#475569' }}>
                          Source: {ev.source?.name} ({ev.source?.kind}) | Method: {ev.method}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  );
}
