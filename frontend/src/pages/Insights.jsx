import React, { useEffect, useRef, useState } from 'react';
import { analysisRequest, analysisStorageKey } from '../api';
import IssuePanel from './IssuePanel';

const reasons = {
  insufficient_history: 'Fewer than 14 calendar days of history are available.',
  product_missing_in_period: 'A product in the fixed dataset cohort has no observations in one or both windows.',
  incomplete_daily_coverage: 'At least one product is missing daily observations in these windows.',
  zero_previous_value: 'The previous recorded total is zero; percentage change is undefined.',
  no_observations: 'No observations in this window.',
  date_boundary: 'The dataset date is too early to represent both comparison windows.',
};

function value(metric) {
  if (!metric || metric.status !== 'supported') return 'Not supported';
  // Decimal strings and large integer strings stay exact; no money arithmetic in JS.
  return typeof metric.value === 'number' ? metric.value.toLocaleString() : metric.value;
}

function Range({ period }) {
  return period ? <>{period.start} to {period.end} ({period.calendar_days} days)</> : <>Unavailable</>;
}

function MetricTable({ caption, headings, rows, renderRow }) {
  const [page, setPage] = useState(0);
  const size = 20;
  const pages = Math.max(1, Math.ceil(rows.length / size));
  useEffect(() => setPage(0), [rows]);
  return <>
    <div className="table-scroll"><table>
      <caption>{caption}</caption>
      <thead><tr>{headings.map((heading) => <th key={heading} scope="col">{heading}</th>)}</tr></thead>
      <tbody>{rows.slice(page * size, (page + 1) * size).map(renderRow)}</tbody>
    </table></div>
    {pages > 1 && <div className="actions">
      <button className="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous {caption}</button>
      <span>Page {page + 1} of {pages} · {rows.length} entries</span>
      <button className="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next {caption}</button>
    </div>}
  </>;
}

function Changes({ comparison }) {
  return <section aria-labelledby="comparison-title">
    <h2 id="comparison-title">Period comparison</h2>
    <p>Current: <Range period={comparison.current_period} /></p>
    <p>Previous: <Range period={comparison.previous_period} /></p>
    <p>Equal seven-day calendar windows anchored to the dataset's latest date. Complete daily coverage is required for every product in the dataset cohort.</p>
    {comparison.status === 'unsupported' && <p className="notice">Comparison not supported: {reasons[comparison.reason]}</p>}
    <div className="table-scroll"><table>
      <caption>Observed totals and supported changes</caption>
      <thead><tr><th scope="col">Metric</th><th scope="col">Previous</th><th scope="col">Current</th><th scope="col">Absolute change</th><th scope="col">Percentage change</th></tr></thead>
      <tbody>{Object.values(comparison.metrics).map((item) => <tr key={item.name}>
        <th scope="row">{item.name === 'total_revenue' ? 'Revenue (currency)' : 'Units sold'}</th>
        <td>{value(item.previous)}</td><td>{value(item.current)}</td><td>{value(item.absolute_change)}</td>
        <td>{value(item.percentage_change)}{item.percentage_change.status === 'supported' ? '%' : ''}
          {item.percentage_change.reason === 'zero_previous_value' && <small> {reasons.zero_previous_value}</small>}</td>
      </tr>)}</tbody>
    </table></div>
    <p className="muted">Displayed period totals include observed records only. Missing observations are never assumed to be zero.</p>
  </section>;
}

function Analytics({ data }) {
  const { overview } = data;
  const snapshots = overview.inventory_snapshot_metadata;
  return <>
    <section aria-labelledby="overview-title">
      <h2 id="overview-title">Business overview</h2>
      <p>Observed dataset period: <Range period={data.period} /></p>
      <p className="muted">{data.coverage.observed_days} observed days · {data.coverage.row_count} validated rows. Missing days are not imputed.</p>
      <dl className="profile-grid">
        {[['Revenue (dataset currency)', overview.total_revenue], ['Units sold', overview.total_units_sold],
          ['Last-known inventory units', overview.current_inventory_units], ['Products', overview.product_count],
          ['Categories', overview.category_count]].map(([label, metric]) => <div key={label}><dt>{label}</dt><dd>{value(metric)}</dd></div>)}
      </dl>
      <p className={snapshots.mixed_snapshot_dates ? 'notice' : 'muted'}>
        Inventory uses each product's latest observed snapshot once. Snapshot dates: {snapshots.snapshot_date_range.start} to {snapshots.snapshot_date_range.end}.
        {snapshots.mixed_snapshot_dates ? ' Mixed dates: this is not a simultaneous stock balance.' : ''}
      </p>
      <p className="muted">Currency is not supplied in V1. No currency symbol or financial assumptions are inferred.</p>
    </section>
    <Changes comparison={data.period_comparison} />
    <section aria-labelledby="products-title">
      <h2 id="products-title">Product performance</h2>
      <p>Active-day averages use observed product days, including days with recorded zero sales.</p>
      <MetricTable caption="Products" headings={['Product', 'Revenue', 'Units sold', 'Inventory / date', 'Units / active day', 'Revenue / active day']}
        rows={data.products} renderRow={(product) => <tr key={product.product_id}>
          <th scope="row">{product.product_name}<small>{product.product_id} · {product.category}</small></th>
          <td>{value(product.total_revenue)}</td><td>{value(product.total_units_sold)}</td>
          <td>{value(product.current_inventory_units)}<small>{product.inventory_observation_date}</small></td>
          <td>{value(product.average_units_per_active_day)}</td><td>{value(product.average_revenue_per_active_day)}</td>
        </tr>} />
      <details><summary>Product period changes</summary>
        <MetricTable caption="Product comparisons" headings={['Product', 'Revenue absolute change', 'Revenue %', 'Units absolute change', 'Units %', 'Support']}
          rows={data.products} renderRow={(product) => {
            const comp = product.period_comparison;
            const { total_revenue: revenue, total_units_sold: units } = comp.metrics;
            return <tr key={product.product_id}><th scope="row">{product.product_name}</th>
              <td>{value(revenue.absolute_change)}</td><td>{value(revenue.percentage_change)}{revenue.percentage_change.status === 'supported' ? '%' : ''}</td>
              <td>{value(units.absolute_change)}</td><td>{value(units.percentage_change)}{units.percentage_change.status === 'supported' ? '%' : ''}</td>
              <td>{comp.status === 'supported' ? 'Supported' : reasons[comp.reason]}
                {comp.status === 'supported' && (revenue.percentage_change.reason || units.percentage_change.reason) && <small>{reasons.zero_previous_value}</small>}</td>
            </tr>;
          }} />
      </details>
    </section>
    <section aria-labelledby="categories-title">
      <h2 id="categories-title">Category performance</h2>
      <MetricTable caption="Categories" headings={['Category', 'Revenue', 'Units sold', 'Products', 'Last-known inventory']}
        rows={data.categories} renderRow={(category) => <tr key={category.category}><th scope="row">{category.category}</th>
          <td>{value(category.total_revenue)}</td><td>{value(category.total_units_sold)}</td><td>{value(category.product_count)}</td><td>{value(category.current_inventory_units)}</td></tr>} />
    </section>
    <section aria-labelledby="series-title">
      <h2 id="series-title">Daily sales</h2>
      <p>Recorded dates only, in chronological order. These totals cover the products observed on each date.</p>
      <MetricTable caption="Daily observations" headings={['Date', 'Revenue', 'Units sold', 'Observed products']}
        rows={data.daily_time_series} renderRow={(point) => <tr key={point.date}><th scope="row">{point.date}</th>
          <td>{value(point.total_revenue)}</td><td>{value(point.total_units_sold)}</td><td>{point.observed_product_count}</td></tr>} />
    </section>
    <p className="muted">Session expires at {new Date(data.expires_at).toLocaleString()}. Metrics are calculated by the backend from validated data.</p>
  </>;
}

export default function Insights() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const active = useRef(null);
  useEffect(() => {
    const id = sessionStorage.getItem(analysisStorageKey);
    if (!id) {
      setData(null);
      setError({ message: 'Load a validated CSV or demo business in Data to view analytics.' });
      return;
    }
    const controller = new AbortController();
    active.current = controller;
    const timeout = setTimeout(() => controller.abort(), 60000);
    setLoading(true);
    setError(null);
    setData(null);
    analysisRequest(`/${encodeURIComponent(id)}/analytics`, {}, controller.signal)
      .then((result) => { if (active.current === controller) setData(result); })
      .catch((failure) => {
        if (active.current !== controller) return;
        if (failure.code === 'analysis_unavailable') sessionStorage.removeItem(analysisStorageKey);
        setError({ message: failure.name === 'AbortError' ? 'Analytics request timed out. Please retry.'
          : failure.message || 'Could not reach the backend. Check the connection and retry.' });
      })
      .finally(() => {
        clearTimeout(timeout);
        if (active.current === controller) setLoading(false);
      });
    return () => { active.current = null; controller.abort(); clearTimeout(timeout); };
  }, [attempt]);
  useEffect(() => {
    if (!data) return;
    const timer = setTimeout(() => {
      setData(null);
      sessionStorage.removeItem(analysisStorageKey);
      setError({ message: 'This analysis session expired. Upload again or load the demo.' });
    }, Math.max(0, new Date(data.expires_at).getTime() - Date.now()));
    return () => clearTimeout(timer);
  }, [data]);
  return <>
    <h2>Business insights</h2>
    <p>Deterministic metrics from your validated analysis session.</p>
    <div className="actions"><a href="/data">Manage dataset</a><button className="secondary" disabled={loading} onClick={() => setAttempt(attempt + 1)}>Refresh analytics</button></div>
    {loading && <p role="status">Calculating analytics…</p>}
    {error && <p role="alert" className="notice">{error.message}</p>}
    {data && <><IssuePanel key={data.analysis_id} analysisId={data.analysis_id} /><Analytics data={data} /></>}
  </>;
}
