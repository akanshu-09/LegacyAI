export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '');
export const analysisStorageKey = 'legacyai.analysis_id';
export const maxUploadBytes = 2 * 1024 * 1024;

export async function analysisRequest(path, options = {}, signal) {
  const response = await fetch(`${apiBaseUrl}/api/v1/analysis${path}`, {
    ...options, signal, cache: 'no-store',
  });
  if (response.status === 204) return null;
  let body;
  try {
    body = await response.json();
  } catch {
    throw { message: 'The backend returned an unreadable response. Check that the API URL is correct.' };
  }
  if (!response.ok) throw body.error || { message: 'The request failed. Please retry.' };
  return body;
}
