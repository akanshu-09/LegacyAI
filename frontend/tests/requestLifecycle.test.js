import test from 'node:test';
import assert from 'node:assert/strict';
import { runCancellableRequest, requestErrorMessage } from '../src/requestLifecycle.js';

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function recorder(events, label) {
  return { success: value => events.push([label, 'success', value]), failure: value => events.push([label, 'failure', value]), settled: () => events.push([label, 'settled']) };
}

test('StrictMode cleanup abort is silent, including finally', async () => {
  const controller = new AbortController(), result = deferred(), events = [];
  const running = runCancellableRequest(() => result.promise, controller.signal, recorder(events, 'old'));
  controller.abort();
  result.reject(new DOMException('signal is aborted without reason', 'AbortError'));
  await running;
  assert.deepEqual(events, []);
});

test('transport resolving after cancellation cannot overwrite newer decision or loading state', async () => {
  const old = new AbortController(), fresh = new AbortController(), stale = deferred(), latest = deferred(), events = [];
  const first = runCancellableRequest(() => stale.promise, old.signal, recorder(events, 'old'));
  old.abort();
  const second = runCancellableRequest(() => latest.promise, fresh.signal, recorder(events, 'new'));
  latest.resolve({ issue_id: 'new' }); await second;
  stale.resolve({ issue_id: 'old' }); await first;
  assert.deepEqual(events, [['new', 'success', { issue_id: 'new' }], ['new', 'settled']]);
});

test('stale network rejection is ignored even if error is not named AbortError', async () => {
  const controller = new AbortController(), result = deferred(), events = [];
  const running = runCancellableRequest(() => result.promise, controller.signal, recorder(events, 'old'));
  controller.abort(); result.reject(new TypeError('Failed to fetch')); await running;
  assert.deepEqual(events, []);
});

test('AbortError is ignored even before signal records cancellation', async () => {
  const events = [];
  await runCancellableRequest(() => Promise.reject(new DOMException('signal is aborted without reason', 'AbortError')), new AbortController().signal, recorder(events, 'request'));
  assert.deepEqual(events, [['request', 'settled']]);
});

test('genuine API failures remain visible, then a successful retry clears error', async () => {
  let error = null, value = null;
  const apiError = { code: 'analysis_unavailable', message: 'Reload your dataset.' };
  const handlers = { failure: failure => { error = requestErrorMessage(failure, 'Retry.'); }, success: result => { error = null; value = result; }, settled: () => {} };
  await runCancellableRequest(() => Promise.reject(apiError), new AbortController().signal, handlers);
  assert.equal(error, apiError.message);
  await runCancellableRequest(() => Promise.resolve({ ai_available: false, ai_error: 'Groq unavailable' }), new AbortController().signal, handlers);
  assert.equal(error, null);
  assert.equal(value.ai_error, 'Groq unavailable');
});

test('browser implementation error text is replaced by clean product copy', () => {
  assert.equal(requestErrorMessage(new TypeError('Failed to fetch'), 'Check your connection and retry.'), 'Check your connection and retry.');
  assert.equal(requestErrorMessage(new Error('signal is aborted without reason'), 'Retry.'), 'Retry.');
});
