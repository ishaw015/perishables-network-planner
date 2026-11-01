const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export function getToken(): string | null {
  try { return window.localStorage.getItem("token"); } catch { return null; }
}
export function setToken(t: string | null) {
  try { t ? window.localStorage.setItem("token", t) : window.localStorage.removeItem("token"); } catch {}
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try { res = await fetch(`${BASE}${path}`, { ...init, headers }); }
  catch { throw new ApiError(0, "Cannot reach the server. Is the API running?"); }
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : "Please check the values you entered.";
    } catch {}
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export async function login(email: string, password: string) {
  const body = new URLSearchParams({ username: email, password });
  let res: Response;
  try {
    res = await fetch(`${BASE}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
  } catch { throw new ApiError(0, "Cannot reach the server. Is the API running?"); }
  if (!res.ok) throw new ApiError(res.status, res.status === 401 ? "Incorrect email or password" : "Login failed");
  setToken((await res.json()).access_token);
}