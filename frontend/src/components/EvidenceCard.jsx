import React from 'react';

export default function EvidenceCard({ evidence }) {
  const ev = evidence;
  return <article className="evidence-panel">
    <h4>{ev.metric.replaceAll('_', ' ')}</h4>
    <p className="evidence-value"><strong>{String(ev.value)}</strong> {ev.unit}</p>
    <p>Source: {ev.source?.name?.replaceAll('_', ' ')} ({ev.source?.kind})</p>
    <p>Method: {ev.method}</p>
    <details><summary>Traceability and calculation details</summary>
      <dl>
        <dt>Evidence ID</dt><dd className="column-list">{ev.evidence_id}</dd>
        <dt>Period</dt><dd>{ev.period ? `${ev.period.start} to ${ev.period.end}` : 'Not applicable'}</dd>
        {ev.comparison_period && <><dt>Comparison period</dt><dd>{ev.comparison_period.start} to {ev.comparison_period.end}</dd></>}
        {ev.observation_date && <><dt>Observation date</dt><dd>{ev.observation_date}</dd></>}
        {ev.exact && <><dt>Exact value</dt><dd>{ev.exact.numerator} / {ev.exact.denominator}</dd></>}
        {ev.detector_version && <><dt>Detector version</dt><dd>{ev.detector_version}</dd></>}
      </dl>
      <pre>{JSON.stringify(ev.inputs || {}, null, 2)}</pre>
    </details>
  </article>;
}
