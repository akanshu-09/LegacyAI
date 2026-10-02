import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import Data from './pages/Data';
import Insights from './pages/Insights';
import Decisions from './pages/Decisions';
import Ask from './pages/Ask';
import { apiBaseUrl } from './api';

function Health() {
  const [status, setStatus] = useState('checking');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeout = setTimeout(() => controller.abort(), 5000);
    setStatus('checking');

    async function checkHealth() {
      try {
        const response = await fetch(`${apiBaseUrl}/health`, { signal: controller.signal });
        if (!response.ok) throw new Error('Health request failed');
        const body = await response.json();
        if (body.status !== 'ok' || body.service !== 'legacyai-backend') {
          throw new Error('Unexpected health response');
        }
        if (active) setStatus('connected');
      } catch {
        if (active) setStatus('disconnected');
      } finally {
        clearTimeout(timeout);
      }
    }
    checkHealth();
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [attempt]);

  return (
      <section aria-labelledby="connection-title">
        <h2 id="connection-title">Backend connection</h2>
        <p role="status" className={status}>
          {status === 'checking' ? 'Checking backend…' : status === 'connected' ? 'Backend connected' : 'Backend disconnected'}
        </p>
        {status === 'disconnected' && <p>Start the backend and check your local API URL and CORS configuration, then retry.</p>}
        <button disabled={status === 'checking'} onClick={() => setAttempt((value) => value + 1)}>Check again</button>
      </section>
  );
}

function App() {
  const pathname = window.location.pathname;
  const isData = pathname === '/data';
  const isInsights = pathname === '/insights';
  const isDecisions = pathname.startsWith('/decisions');
  const isAsk = pathname === '/ask';

  return (
    <main>
      <header>
        <p className="eyebrow">Verified data. Traceable decisions.</p>
        <h1>LegacyAI</h1>
        <p>AI reasons about verified data — it does not replace the data.</p>
        <nav aria-label="Main navigation">
          <a href="/" aria-current={!isData && !isInsights && !isDecisions && !isAsk ? 'page' : undefined}>Overview</a>
          <a href="/data" aria-current={isData ? 'page' : undefined}>Data</a>
          <a href="/insights" aria-current={isInsights ? 'page' : undefined}>Insights</a>
          <a href="/ask" aria-current={isAsk ? 'page' : undefined}>Ask AI</a>
          <a href="/decisions" aria-current={isDecisions ? 'page' : undefined}>Decisions</a>
        </nav>
      </header>
      {isAsk ? <Ask /> : isDecisions ? <Decisions /> : isInsights ? <Insights /> : isData ? <Data /> : <>
        <Health />
        <section><h2>Start with trustworthy data</h2><p>Validate a CSV and inspect its dataset profile in a temporary analysis session.</p><a href="/data">Open data workspace →</a></section>
      </>}
    </main>
  );
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
