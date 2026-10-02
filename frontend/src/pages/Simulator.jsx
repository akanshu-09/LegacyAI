import React, { useEffect, useRef, useState } from 'react';
import { analysisRequest, analysisStorageKey } from '../api';

const labels = {
  assumed_receipt_quantity: 'Assumed receipt (units)', daily_demand: 'Demand rate (units/day)',
  projected_demand: 'Projected demand (units)', available_inventory: 'Available inventory (units)',
  projected_ending_inventory: 'Projected ending inventory (units)', unmet_demand: 'Unmet demand (units)',
  days_inventory_remaining: 'Days inventory remaining', potential_stockout: 'Potential stockout',
  potential_excess_stock: 'Potential excess stock (>30 remaining days)',
};
const reasons = {
  stale_inventory_snapshot: 'Inventory snapshot is older than the dataset end date.',
  incomplete_daily_coverage: 'Seven complete recent calendar days are required.',
  date_boundary: 'The latest seven-day window cannot be represented.',
  zero_scenario_demand: 'Undefined at zero demand; no infinity or excess classification is inferred.',
};

function Value({ metric }) {
  if (!metric || metric.status !== 'supported') return <span>Unsupported: {reasons[metric?.reason] || metric?.reason}</span>;
  return <>{typeof metric.value === 'boolean' ? (metric.value ? 'Yes' : 'No') : metric.value}</>;
}

export default function Simulator() {
  const [options, setOptions] = useState(null);
  const [inputs, setInputs] = useState({ product_id: '', baseline_reorder_quantity: '0', reorder_adjustment_percent: 0, demand_change_percent: 0, horizon_days: 14 });
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);
  const [id, setId] = useState(() => sessionStorage.getItem(analysisStorageKey));
  const running = useRef(null);
  useEffect(() => () => running.current?.abort(), []);

  function expire() {
    running.current?.abort();
    setOptions(null); setResult(null); setId(null); setLoading(false);
    setInputs({ product_id: '', baseline_reorder_quantity: '0', reorder_adjustment_percent: 0, demand_change_percent: 0, horizon_days: 14 });
    if (sessionStorage.getItem(analysisStorageKey) === id) sessionStorage.removeItem(analysisStorageKey);
    setError('Analysis session is unavailable. Upload again or load the demo.');
  }

  useEffect(() => {
    if (!id) { setLoading(false); return; }
    const controller = new AbortController();
    running.current = controller;
    setLoading(true); setError(null);
    analysisRequest(`/${id}/simulation`, {}, controller.signal).then((data) => {
      if (controller.signal.aborted) return;
      setOptions(data);
      const preferred = new URLSearchParams(window.location.search).get('product_id');
      const selected = data.products.find(p => p.product_id === preferred) || data.products.find(p => p.status === 'supported') || data.products[0];
      setInputs(previous => ({ ...previous, product_id: selected?.product_id || '' }));
    }).catch(err => {
      if (controller.signal.aborted) return;
      if (err.code === 'analysis_unavailable') expire();
      else setError(err.message || 'Unable to load simulation inputs. Retry.');
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, attempt]);

  useEffect(() => {
    if (!options) return;
    const timer = setTimeout(expire, Math.max(0, Date.parse(options.expires_at) - Date.now()));
    return () => clearTimeout(timer);
  }, [options]);

  const product = options?.products.find(p => p.product_id === inputs.product_id);
  function change(key, value) { setInputs(previous => ({ ...previous, [key]: value })); setResult(null); setError(null); }
  async function run(event) {
    event.preventDefault();
    const controller = new AbortController(); running.current = controller;
    setLoading(true); setResult(null); setError(null);
    try {
      const data = await analysisRequest(`/${id}/simulate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...inputs, baseline_reorder_quantity: Number(inputs.baseline_reorder_quantity) }),
      }, controller.signal);
      if (!controller.signal.aborted) setResult(data);
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err.code === 'analysis_unavailable') expire();
      else setError(err.message || 'Scenario was rejected. Check input ranges and retry.');
    } finally { if (!controller.signal.aborted) setLoading(false); }
  }

  return <section aria-labelledby="simulator-heading">
    <h2 id="simulator-heading">Before you act, test it.</h2>
    <p>Deterministic what-if simulator. Hypothetical outcomes, not forecasts or purchasing instructions.</p>
    {error && <p role="alert" className="notice">{error}</p>}
    {!id && <p>No active analysis. <a href="/data">Load data to simulate a decision →</a></p>}
    {loading && <p role="status">Loading simulation…</p>}
    {id && !options && !loading && <button onClick={() => setAttempt(value => value + 1)}>Retry loading simulator</button>}
    {options && <>
      <p>Dataset as of {options.dataset_as_of}. Session ends {options.expires_at}.</p>
      <form onSubmit={run}>
        <label htmlFor="simulation-product">Product</label>
        <select id="simulation-product" value={inputs.product_id} disabled={loading} onChange={e => change('product_id', e.target.value)}>
          {options.products.map(p => <option key={p.product_id} value={p.product_id}>{p.product_name} ({p.product_id}){p.status === 'unsupported' ? ' — unsupported' : ''}</option>)}
        </select>
        {product && <p>Observed inventory: {product.source.inventory_units} units on {product.source.inventory_observation_date}. Recent demand: {product.source.recent_units} units across {product.source.observed_days} observed days ({product.source.demand_period?.start || 'unavailable'} to {product.source.demand_period?.end || 'unavailable'}).</p>}
        {product?.reason && <p className="notice">Simulation unsupported: {reasons[product.reason]}</p>}
        <label htmlFor="baseline-reorder">Baseline reorder quantity (assumed immediate receipt, units)</label>
        <input id="baseline-reorder" type="number" min="0" max="1000000000000" step="1" required value={inputs.baseline_reorder_quantity} disabled={loading} onChange={e => change('baseline_reorder_quantity', e.target.value)} />
        <p>Enter your own assumed quantity. Zero means no receipt; adjusting zero still gives zero.</p>
        <label htmlFor="reorder-adjustment">Reorder adjustment: {inputs.reorder_adjustment_percent}% (−50% to +50%)</label>
        <input id="reorder-adjustment" type="range" min="-50" max="50" step="1" value={inputs.reorder_adjustment_percent} disabled={loading} onChange={e => change('reorder_adjustment_percent', Number(e.target.value))} />
        <label htmlFor="demand-scenario">Demand scenario: {inputs.demand_change_percent}% (−30% to +30%)</label>
        <input id="demand-scenario" type="range" min="-30" max="30" step="1" value={inputs.demand_change_percent} disabled={loading} onChange={e => change('demand_change_percent', Number(e.target.value))} />
        <label htmlFor="simulation-horizon">Horizon (days after dataset snapshot)</label>
        <select id="simulation-horizon" value={inputs.horizon_days} disabled={loading} onChange={e => change('horizon_days', Number(e.target.value))}>
          {[7, 14, 30].map(days => <option key={days} value={days}>{days} days</option>)}
        </select>
        <div className="actions"><button type="submit" disabled={loading || product?.status !== 'supported'}>Run hypothetical scenario</button></div>
      </form>
      {result && <>
        <h3>Hypothetical outcome — {result.product.product_name}</h3>
        <p>Baseline uses the same horizon and your assumed reorder, with no adjustments. Differences are scenario minus baseline.</p>
        <div className="table-scroll"><table>
          <caption>Baseline and scenario comparison</caption>
          <thead><tr><th scope="col">Metric</th><th scope="col">Baseline</th><th scope="col">Scenario</th><th scope="col">Difference</th></tr></thead>
          <tbody>{Object.entries(labels).map(([key, label]) => <tr key={key}><th scope="row">{label}</th><td><Value metric={result.baseline[key]} /></td><td><Value metric={result.scenario[key]} /></td><td>{result.comparison[key] ? <Value metric={result.comparison[key]} /> : '—'}</td></tr>)}</tbody>
        </table></div>
        <details><summary>Exact calculations and inputs</summary><pre>{JSON.stringify({ source: result.source, inputs: result.inputs, baseline: result.baseline, scenario: result.scenario, comparison: result.comparison }, null, 2)}</pre></details>
      </>}
      <h3>Explicit assumptions and limits</h3>
      <ul>{options.assumptions.map(item => <li key={item}>{item}</li>)}</ul>
      <p>Displayed quantities round to two decimal places. Exact fractions remain available above.</p>
    </>}
  </section>;
}
