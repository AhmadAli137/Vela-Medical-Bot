export type RecordData = Record<string, any>;
export type RoomObject = RecordData & { id: string; label: string; semantic_class: string; pose: {x: number; y: number; z: number}; dimensions: {x: number; y: number; z: number}; policy: string; confidence: number; reachable_by_patient?: boolean; state: RecordData };
export type Bootstrap = RecordData & {mode: string; room: RecordData & {id: string; name: string; version: number; objects: RoomObject[]}; tasks: RecordData[]; robots: RecordData[]; metrics: RecordData; templates: (string | RecordData)[]; skills: RecordData[]; opportunities: RecordData[]; images: RecordData[]; sessions: RecordData[]};

export async function api<T = RecordData>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 45000);
  const abort = () => controller.abort();
  signal?.addEventListener('abort', abort, {once: true});
  if (signal?.aborted) controller.abort();
  try {
    const response = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: body === undefined ? {} : {'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data.detail ?? data.message ?? `Request failed (${response.status})`;
      throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    }
    return data;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('The service took too long to respond. Refresh to check the latest state before trying again.');
    if (error instanceof TypeError) throw new Error('Vela cannot reach the service. Start the API on port 8000, then try again.');
    throw error;
  } finally {
    window.clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
  }
}

export const human = (value: unknown) => String(value ?? 'Not available').replaceAll('_', ' ').replaceAll('-', ' ');
export const display = (value: unknown) => value === null || value === undefined ? 'Not measured' : typeof value === 'object' ? JSON.stringify(value) : String(value);
export const when = (value: unknown) => {
  if (!value) return 'No observation';
  const d = new Date(String(value));
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
};
