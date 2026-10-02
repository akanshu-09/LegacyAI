import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');

function App() {
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
    <main>
      <p>Phase 0 · Engineering foundation</p>
      <h1>LegacyAI</h1>
      <p>AI reasons about verified data — it does not replace the data.</p>
      <section aria-labelledby="connection-title">
        <h2 id="connection-title">Backend connection</h2>
        <p role="status" className={status}>
          {status === 'checking' ? 'Checking backend…' : status === 'connected' ? 'Backend connected' : 'Backend disconnected'}
        </p>
        {status === 'disconnected' && <p>Start the backend and check your local API URL and CORS configuration, then retry.</p>}
        <button disabled={status === 'checking'} onClick={() => setAttempt((value) => value + 1)}>Check again</button>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
