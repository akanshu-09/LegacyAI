// Cancellation is control flow, not a product error. Guard every callback,
// including finally, because a transport can resolve after being cancelled.
export async function runCancellableRequest(request, signal, handlers) {
  try {
    const result = await request();
    if (!signal.aborted) handlers.success(result);
  } catch (error) {
    if (!signal.aborted && error?.name !== 'AbortError') handlers.failure(error);
  } finally {
    if (!signal.aborted) handlers.settled();
  }
}

export function requestErrorMessage(error, fallback) {
  // Structured API errors are actionable. Browser transport exception text
  // (including cancellation implementation details) is not product copy.
  return error?.code && typeof error.message === 'string' ? error.message : fallback;
}
