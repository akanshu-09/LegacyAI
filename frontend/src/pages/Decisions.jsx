import React, { useEffect, useState } from 'react';
import { analysisRequest, analysisStorageKey } from '../api';
import { runCancellableRequest, requestErrorMessage } from '../requestLifecycle';
import EvidenceCard from '../components/EvidenceCard';

export default function Decisions() {
  const [analysisId, setAnalysisId] = useState(null);
  const [issuesData, setIssuesData] = useState(null);
  const [selectedIssueId, setSelectedIssueId] = useState(null);
  const [decision, setDecision] = useState(null);
  const [loadingIssues, setLoadingIssues] = useState(false);
  const [loadingDecision, setLoadingDecision] = useState(false);
  const [error, setError] = useState(null);
  const [decisionError, setDecisionError] = useState(null);
  const [issueAttempt, setIssueAttempt] = useState(0);
  const [decisionAttempt, setDecisionAttempt] = useState(0);

  useEffect(() => {
    const id = sessionStorage.getItem(analysisStorageKey);
    if (!id) return;
    setAnalysisId(id);

    // Extract path issueId if navigating directly to /decisions/:issueId
    const pathname = window.location.pathname;
    const match = pathname.match(/\/decisions\/(.+)/);
    const pathIssueId = match ? decodeURIComponent(match[1]) : null;

    setLoadingIssues(true);
    setError(null);
    const controller = new AbortController();

    runCancellableRequest(() => analysisRequest(`/${id}/issues`, {}, controller.signal), controller.signal, {
      success: (data) => {
        setError(null);
        setIssuesData(data);
        if (pathIssueId && data.issues?.some((i) => i.issue_id === pathIssueId)) {
          setSelectedIssueId(pathIssueId);
        } else if (data.issues && data.issues.length > 0) {
          setSelectedIssueId(data.issues[0].issue_id);
        }
      },
      failure: (err) => setError(requestErrorMessage(err, 'Unable to load issues. Check your connection and retry.')),
      settled: () => setLoadingIssues(false),
    });

    return () => controller.abort();
  }, [issueAttempt]);

  useEffect(() => {
    if (!analysisId || !selectedIssueId) return;

    setLoadingDecision(true);
    setDecisionError(null);
    setDecision(null);
    const controller = new AbortController();

    runCancellableRequest(() => analysisRequest(`/${analysisId}/decisions/${encodeURIComponent(selectedIssueId)}`, { method: 'POST' }, controller.signal), controller.signal, {
      success: (data) => {
        setDecisionError(null);
        setDecision(data);
      },
      failure: (err) => setDecisionError(requestErrorMessage(err, 'Unable to load this decision. Check your connection and retry.')),
      settled: () => setLoadingDecision(false),
    });

    return () => controller.abort();
  }, [analysisId, selectedIssueId, decisionAttempt]);

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
        <h2 id="decisions-heading">Decision workspace</h2>
        <p>Investigate a detected issue, review its evidence, and consider your next action.</p>

        {loadingIssues && <p role="status">Loading detected issues…</p>}
        {error && <><p role="alert" className="notice">{error}</p><button onClick={() => setIssueAttempt(value => value + 1)}>Retry loading issues</button></>}

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
                setDecision(null);
                setDecisionError(null);
                window.history.replaceState(null, '', `/decisions/${encodeURIComponent(newId)}`);
              }}
              style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border)', width: 'min(100%, 500px)' }}
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
            <div style={{ background: 'var(--surface-soft)', padding: '1.25rem', borderRadius: '8px', border: '1px solid var(--border)', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 id="issue-detail-heading" style={{ margin: 0 }}>
                  {currentIssue.title}: {currentIssue.entity_name}
                </h3>
                <span className={`badge severity-${(currentIssue.severity || 'LOW').toLowerCase()}`} style={{ fontWeight: 'bold' }}>
                  {currentIssue.severity} SEVERITY
                </span>
              </div>
              <p style={{ marginTop: '0.5rem', color: 'var(--muted)' }}>{currentIssue.summary}</p>
              <a href={`/simulator?product_id=${encodeURIComponent(currentIssue.entity_id)}`}>Simulate this product with your own assumptions →</a>
            </div>
          )}

          {loadingDecision && <p role="status">Generating AI decision reasoning & verifying claims…</p>}
          {decisionError && <><p role="alert" className="notice">{decisionError}</p><button onClick={() => setDecisionAttempt(value => value + 1)}>Retry decision</button></>}

          {decision && decision.issue_id === selectedIssueId && (
            <div>
              {/* Verification Status Badge */}
              <div style={{ margin: '1rem 0', padding: '0.75rem 1rem', borderRadius: '6px', border: '1px solid', backgroundColor: decision.verification?.status === 'verified' ? 'var(--secondary-soft)' : decision.verification?.status === 'partially_verified' ? 'var(--warning-soft)' : decision.ai_available ? 'var(--accent-soft)' : 'var(--surface-soft)', borderColor: decision.verification?.status === 'verified' ? 'var(--border)' : decision.verification?.status === 'partially_verified' ? 'var(--gold)' : decision.ai_available ? 'var(--border)' : 'var(--border)' }}>
                <strong>Claim Verification Status: </strong>
                {decision.verification?.status === 'verified' ? (
                  <span style={{ color: 'var(--secondary)', fontWeight: 'bold' }}>Verified against dataset evidence</span>
                ) : decision.verification?.status === 'partially_verified' ? (
                  <span style={{ color: 'var(--warning)', fontWeight: 'bold' }}>Partially verified (some ungrounded citations)</span>
                ) : decision.ai_available ? (
                  <span style={{ color: 'var(--danger)', fontWeight: 'bold' }}>Claims unverified or rejected</span>
                ) : (
                  <span style={{ color: 'var(--muted)', fontWeight: 'bold' }}>AI reasoning unavailable</span>
                )}
                <details><summary>Verification details</summary><ul style={{ margin: '0.5rem 0 0 1.25rem', fontSize: '0.9rem' }}>
                  {decision.verification?.details?.map((d, idx) => (
                    <li key={idx}>{d}</li>
                  ))}
                </ul></details>
              </div>

              {!decision.ai_available && (
                <div className="notice" style={{ background: 'var(--surface-soft)', borderColor: 'var(--border)' }}>
                  <p><strong>AI Provider Status:</strong> {decision.ai_error || 'AI provider unavailable.'}</p>
                  <p style={{ fontSize: '0.9rem' }}>Deterministic analytics, issue detection, and verified evidence remain fully operational below.</p>
                </div>
              )}

              {decision.ai_available && decision.reasoning && (
                <div style={{ display: 'grid', gap: '1.5rem', marginTop: '1.5rem' }}>
                  {/* Recommended Action Card */}
                  <div style={{ background: 'var(--secondary-soft)', border: '1px solid var(--border)', borderRadius: '8px', padding: '1.25rem' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', color: 'var(--secondary)' }}>Recommended Operational Action</h4>
                    <p style={{ fontSize: '1.1rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>
                      {decision.reasoning.recommendation?.action}
                    </p>
                    <p style={{ margin: 0, fontSize: '0.95rem', color: 'var(--secondary)' }}>
                      Target: <strong>{decision.reasoning.recommendation?.target}</strong> | Timeframe: <strong>{decision.reasoning.recommendation?.timeframe_days} days</strong>
                    </p>
                  </div>

                  {/* Summary */}
                  <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '1.25rem' }}>
                    <h4 style={{ marginTop: 0 }}>Reasoning Summary</h4>
                    <p>{decision.reasoning.summary}</p>
                  </div>

                  {/* Root Cause Explanations */}
                  {decision.reasoning.root_causes?.length > 0 && (
                    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '1.25rem' }}>
                      <h4 style={{ marginTop: 0 }}>Plausible Root Cause Analysis</h4>
                      <ul>
                        {decision.reasoning.root_causes.map((rc, idx) => (
                          <li key={idx} style={{ marginBottom: '0.5rem' }}>
                            {rc.explanation}
                            {rc.evidence_ids?.length > 0 && (
                              <details><summary>Evidence references</summary><p className="column-list">{rc.evidence_ids.join(', ')}</p></details>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Assumptions & Uncertainties Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
                    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '1rem' }}>
                      <h5 style={{ marginTop: 0 }}>Explicit Assumptions</h5>
                      <ul style={{ paddingLeft: '1.25rem', fontSize: '0.9rem' }}>
                        {decision.reasoning.assumptions?.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '1rem' }}>
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
                    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '8px', padding: '1rem' }}>
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
                    {decision.cited_evidence?.map((ev) => <EvidenceCard key={ev.evidence_id} evidence={ev} />)}
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
