const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function authHeaders(token?: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiGet<T>(path: string, token?: string | null): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    cache: "no-store",
    headers: authHeaders(token)
  });
  if (!response.ok) throw new Error(await responseMessage(response));
  return response.json();
}

export async function apiPost<T>(path: string, body: unknown, token?: string | null): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await responseMessage(response));
  return response.json();
}

export async function apiDelete<T>(path: string, token?: string | null): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "DELETE",
    headers: authHeaders(token)
  });
  if (!response.ok) throw new Error(await responseMessage(response));
  return response.json();
}

export async function apiUpload<T>(path: string, file: File, token?: string | null): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: authHeaders(token),
    body: form
  });
  if (!response.ok) throw new Error(await responseMessage(response));
  return response.json();
}

async function responseMessage(response: Response) {
  const text = await response.text();
  try {
    const parsed = JSON.parse(text);
    return parsed.detail || text || response.statusText;
  } catch {
    return text || response.statusText;
  }
}
