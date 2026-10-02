import React, { useState, useEffect } from 'react';
import { analysisRequest, analysisStorageKey } from '../api';

const SUGGESTED_QUESTIONS = [
  'What are our top inventory risks?',
  'Give me a high-level business overview.',
  'How is Harbor Pen Set performing?',
  'Which products have declining demand?',
  'What is our total profit margin this month?'
];

export default function Ask() {
  const [analysisId, setAnalysisId] = useState(null);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const id = sessionStorage.getItem(analysisStorageKey);
    if (id) setAnalysisId(id);
  }, []);

  const handleAsk = async (qToSubmit) => {
    const q = (qToSubmit || question).trim();
    if (!q || !analysisId) return;

    setQuestion(q);
    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const data = await analysisRequest(`/${analysisId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      });
      setResponse(data);
    } catch (err) {
      setError(err.message || 'Failed to get answer. Please retry.');
    } finally {
      setLoading(false);
    }
  };

  if (!analysisId) {
    return (
      <section>
        <h2>Ask LegacyAI</h2>
        <p>No active analysis session found. Upload a dataset or load synthetic demo data to ask evidence-backed questions.</p>
        <a href="/data">Go to Data Workspace →</a>
      </section>
    );
  }

  return (
    <div>
      <section aria-labelledby="ask-heading">
        <h2 id="ask-heading">Ask LegacyAI</h2>
        <p>Ask natural language questions about your active dataset. LegacyAI uses Python analytics for facts and LLM reasoning strictly for evidence explanations.</p>

        {/* Question Form */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleAsk();
          }}
          style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', margin: '1.5rem 0' }}
        >
          <label htmlFor="question-input" style={{ fontWeight: 'bold' }}>
            Your Business Question:
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              id="question-input"
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. What are our top inventory risks?"
              disabled={loading}
              style={{ flex: 1, padding: '0.75rem', borderRadius: '6px', border: '1px solid #cbd5e1', fontSize: '1rem' }}
            />
            <button type="submit" disabled={loading || !question.trim()} style={{ background: '#246174', color: '#fff', padding: '0.75rem 1.5rem', borderRadius: '6px', border: 'none', fontWeight: 'bold', cursor: 'pointer' }}>
              {loading ? 'Analyzing…' : 'Ask LegacyAI'}
            </button>
          </div>
        </form>

        {/* Suggested Questions */}
        <div>
          <span style={{ fontSize: '0.9rem', color: '#64748b', fontWeight: 'bold', marginRight: '0.5rem' }}>
            Suggested Questions:
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.5rem' }}>
            {SUGGESTED_QUESTIONS.map((sq, i) => (
              <button
                key={i}
                type="button"
                className="secondary"
                disabled={loading}
                onClick={() => handleAsk(sq)}
                style={{ fontSize: '0.85rem', padding: '0.4rem 0.75rem', cursor: 'pointer' }}
              >
                {sq}
              </button>
            ))}
          </div>
        </div>
      </section>

      {error && <p role="alert" className="notice">{error}</p>}
      {loading && <p role="status" style={{ marginTop: '1.5rem' }}>Evaluating query with deterministic Python analytics & evidence engine…</p>}

      {response && (
        <section style={{ marginTop: '2rem' }}>
          {/* Header & Verification Badge */}
          <div style={{ background: '#f8fafc', padding: '1.25rem', borderRadius: '8px', border: '1px solid #cbd5e1', marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0 }}>Q: "{response.question}"</h3>
              <span className={`badge ${response.intent?.supported ? 'severity-low' : 'severity-high'}`} style={{ fontWeight: 'bold' }}>
                {response.intent?.intent_type} ({response.intent?.supported ? 'SUPPORTED' : 'UNSUPPORTED'})
              </span>
            </div>

            <div style={{ margin: '1rem 0 0 0', padding: '0.5rem 0.75rem', borderRadius: '4px', background: response.intent?.supported ? '#f0fdf4' : '#fef2f2', border: '1px solid', borderColor: response.intent?.supported ? '#86efac' : '#fca5a5', fontSize: '0.9rem' }}>
              <strong>Verification Status: </strong>
              {response.verification?.status === 'verified' ? (
                <span style={{ color: '#166534', fontWeight: 'bold' }}>✓ Verified against dataset evidence</span>
              ) : (
                <span style={{ color: '#991b1b', fontWeight: 'bold' }}>⚪ AI Explanation Unavailable — Showing Factual Finding</span>
              )}
            </div>
          </div>

          {/* Factual Finding Box */}
          <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1.25rem', marginBottom: '1.5rem' }}>
            <h4 style={{ marginTop: 0, color: '#0f172a' }}>Factual Finding (Deterministic Python Analytics)</h4>
            <p style={{ fontSize: '1.05rem', fontWeight: '600', color: '#1e293b' }}>{response.factual_finding?.finding}</p>
            <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9rem', color: '#475569' }}>
              <strong>Methodology / Context:</strong> {response.factual_finding?.why}
            </p>
          </div>

          {/* Explanation Box */}
          {response.explanation && response.explanation !== response.factual_finding?.finding && (
            <div style={{ background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '1.25rem', marginBottom: '1.5rem' }}>
              <h4 style={{ marginTop: 0 }}>Evidence Explanation</h4>
              <p>{response.explanation}</p>
            </div>
          )}

          {/* Recommended Action Card */}
          {response.recommendation && (
            <div style={{ background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '1.25rem', marginBottom: '1.5rem' }}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#1e40af' }}>Recommended Operational Action</h4>
              <p style={{ fontSize: '1.05rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>{response.recommendation.action}</p>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.9rem', color: '#1e3a8a' }}>
                  Target: <strong>{response.recommendation.target || 'General Scope'}</strong> | Timeframe: <strong>{response.recommendation.timeframe_days || 14} days</strong>
                </span>
                {response.recommendation.issue_id && (
                  <a href={`/decisions/${encodeURIComponent(response.recommendation.issue_id)}`} style={{ background: '#1e40af', color: '#fff', padding: '0.4rem 0.8rem', borderRadius: '4px', textDecoration: 'none', fontSize: '0.85rem', fontWeight: 'bold' }}>
                    Investigate in Decisions →
                  </a>
                )}
              </div>
            </div>
          )}

          {/* Verified Evidence Cards */}
          {response.evidence?.length > 0 && (
            <div>
              <h4>Verified Supporting Evidence ({response.evidence.length})</h4>
              <div style={{ display: 'grid', gap: '0.75rem' }}>
                {response.evidence.map((ev) => (
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
            </div>
          )}
        </section>
      )}
    </div>
  );
}
