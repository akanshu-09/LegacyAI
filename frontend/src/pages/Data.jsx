import React, { useEffect, useRef, useState } from 'react';
import { analysisRequest, analysisStorageKey, maxUploadBytes } from '../api';

function ValidationError({ error }) {
  return (
    <div role="alert" className="error-panel">
      <h3>Dataset could not be loaded</h3>
      <p>{error.message}</p>
      {error.schema?.missing_required_columns?.length > 0 && <p>Missing columns: {error.schema.missing_required_columns.join(', ')}</p>}
      {error.schema?.unknown_columns?.length > 0 && <p>Unrecognized columns: {error.schema.unknown_columns.join(', ')}</p>}
      {error.schema?.duplicate_columns?.length > 0 && <p>Repeated columns: {error.schema.duplicate_columns.join(', ')}</p>}
      {error.data_quality && <p>{error.data_quality.error_count} validation issues · {error.data_quality.duplicate_rows} duplicate rows</p>}
      {error.errors?.length > 0 && <ul>{error.errors.map((issue, index) => (
        <li key={index}>Row {issue.row}{issue.column ? ` · ${issue.column}` : ''}: {issue.message}</li>
      ))}</ul>}
      {error.errors_truncated && <p>Showing the first 100 issues. Correct them and upload again to check remaining rows.</p>}
    </div>
  );
}

function DatasetProfile({ analysis }) {
  const { profile } = analysis;
  const quality = profile.data_quality;
  return (
    <section aria-labelledby="profile-title">
      <h2 id="profile-title">Dataset profile</h2>
      <p className="connected">Validated · {analysis.source === 'demo' ? 'Synthetic demo business' : 'Uploaded CSV'}</p>
      <dl className="profile-grid">
        <div><dt>Rows</dt><dd>{profile.row_count.toLocaleString()}</dd></div>
        <div><dt>Products</dt><dd>{profile.product_count.toLocaleString()}</dd></div>
        <div><dt>Categories</dt><dd>{profile.category_count.toLocaleString()}</dd></div>
        <div><dt>Date range</dt><dd>{profile.date_range.start} to {profile.date_range.end}</dd></div>
      </dl>
      <h3>Data quality</h3>
      <p>{quality.duplicate_rows} duplicate rows · {quality.error_count} validation errors</p>
      {quality.warnings.map((warning) => <p key={warning} className="notice">{warning}</p>)}
      <table>
        <caption>Missing values by field</caption>
        <thead><tr><th scope="col">Field</th><th scope="col">Missing values</th></tr></thead>
        <tbody>{Object.entries(quality.missing_values).map(([field, count]) => <tr key={field}><th scope="row">{field}</th><td>{count}</td></tr>)}</tbody>
      </table>
      <h3>Recognized schema · {profile.schema.version}</h3>
      <p className="column-list">{profile.schema.recognized_columns.join(', ')}</p>
      {profile.schema.absent_optional_columns.length > 0 && <p>Optional columns not supplied: {profile.schema.absent_optional_columns.join(', ')}</p>}
      <p>Session expires at <time dateTime={analysis.expires_at}>{new Date(analysis.expires_at).toLocaleString()}</time>. Reloading does not extend its lifetime.</p>
      <p className="muted">This is a structural dataset profile. <a href="/insights">View deterministic business analytics →</a></p>
    </section>
  );
}

export default function Data() {
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState('');
  const [selection, setSelection] = useState('');
  const [notice, setNotice] = useState('');
  const fileInput = useRef(null);
  const activeRequest = useRef(null);

  function clearLocalSession() {
    sessionStorage.removeItem(analysisStorageKey);
    setAnalysis(null);
  }

  async function load(path, options, label, restoring = false) {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    const timeout = setTimeout(() => controller.abort(), 60000);
    setLoading(label);
    setError(null);
    setNotice('');
    try {
      const result = await analysisRequest(path, options, controller.signal);
      if (activeRequest.current !== controller) return;
      if (result) {
        sessionStorage.setItem(analysisStorageKey, result.analysis_id);
        setAnalysis(result);
      } else {
        clearLocalSession();
        setNotice('Session released. Choose a CSV or load the demo to begin again.');
      }
    } catch (failure) {
      if (activeRequest.current !== controller) return;
      if (failure.code === 'analysis_unavailable') clearLocalSession();
      setError(failure.name === 'AbortError'
        ? { message: 'The request timed out. Check the backend connection and retry.' }
        : { ...failure, message: failure.message || 'Could not reach the backend. Check the connection and retry.' });
      if (restoring && failure.code !== 'analysis_unavailable') {
        setNotice('Your session ID is retained. Reload the page after the backend connection is restored.');
      }
    } finally {
      clearTimeout(timeout);
      if (activeRequest.current === controller) setLoading('');
    }
  }

  useEffect(() => {
    const id = sessionStorage.getItem(analysisStorageKey);
    if (id) load(`/${encodeURIComponent(id)}`, {}, 'Restoring analysis session…', true);
    return () => {
      activeRequest.current?.abort();
      activeRequest.current = null;
    };
  }, []);

  useEffect(() => {
    if (!analysis) return;
    const remaining = Math.max(0, new Date(analysis.expires_at).getTime() - Date.now());
    const timer = setTimeout(() => {
      clearLocalSession();
      setNotice('Your temporary session expired. Upload again or load the demo.');
    }, remaining);
    return () => clearTimeout(timer);
  }, [analysis]);

  async function upload(event) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) {
      setError({ message: 'Choose a CSV file first.' });
      return;
    }
    if (!file.name.toLowerCase().endsWith('.csv') || file.size > maxUploadBytes) {
      setError({ message: 'Choose a .csv file no larger than 2 MiB.' });
      return;
    }
    const pending = load('/upload', { method: 'POST', headers: { 'Content-Type': 'text/csv' }, body: file }, 'Uploading and validating CSV…');
    // Do not retain a selected file after sending it. Only the opaque ID is persisted.
    fileInput.current.value = '';
    setSelection('');
    await pending;
  }

  return (
    <>
      <section aria-labelledby="data-title">
        <h2 id="data-title">Load business data</h2>
        <p>Upload a supported sales and inventory CSV, or explore a synthetic business. Validation runs before a session is created.</p>
        <form onSubmit={upload}>
          <label htmlFor="dataset-file">Sales / inventory CSV</label>
          <input ref={fileInput} id="dataset-file" type="file" accept=".csv,text/csv" disabled={Boolean(loading)}
            onChange={(event) => setSelection(event.target.files?.[0]?.name || '')} />
          <p className="muted">UTF-8 · exact V1 headers · up to 2 MiB and 10,000 rows</p>
          <div className="actions">
            <button type="submit" disabled={Boolean(loading) || !selection}>Upload CSV</button>
            <button type="button" className="secondary" disabled={Boolean(loading)}
              onClick={() => load('/demo', { method: 'POST' }, 'Loading demo business…')}>Load Demo Business</button>
          </div>
        </form>
        <details>
          <summary>CSV contract and validation policies</summary>
          <p className="column-list">Required: date, product_id, product_name, category, units_sold, revenue, inventory, unit_price</p>
          <p>Optional: supplier, lead_time_days. Dates use YYYY-MM-DD. Quantities and lead times are nonnegative integers; revenue and unit price use nonnegative decimals with at most two decimal places.</p>
          <p>Required blanks, duplicate rows and unknown columns are rejected. Optional blanks remain null. No missing values are inferred.</p>
        </details>
        <p className="muted">Data stays in temporary backend memory for 30 minutes. The browser retains only the analysis ID. Server restarts clear all sessions.</p>
        <p role="status">{loading || notice}</p>
        {error && <ValidationError error={error} />}
      </section>
      {analysis && <>
        {error && <p className="notice">The existing validated session remains active; the new request did not replace it.</p>}
        <DatasetProfile analysis={analysis} />
        <button type="button" className="secondary" disabled={Boolean(loading)}
          onClick={() => load(`/${encodeURIComponent(analysis.analysis_id)}`, { method: 'DELETE' }, 'Releasing session…')}>Release analysis session</button>
      </>}
    </>
  );
}
