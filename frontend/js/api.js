const ACCESS_TOKEN_KEY = 'access_token';
const CURRENT_USER_KEY = 'current_user';


export function getAccessToken() {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY) || '';
}


export function saveSession(accessToken, user) {
  sessionStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  sessionStorage.setItem(CURRENT_USER_KEY, JSON.stringify(user));
}


export function getStoredUser() {
  const rawUser = sessionStorage.getItem(CURRENT_USER_KEY);
  if (!rawUser) return null;
  try {
    return JSON.parse(rawUser);
  } catch {
    sessionStorage.removeItem(CURRENT_USER_KEY);
    return null;
  }
}


export function clearSession() {
  sessionStorage.clear();
}


export async function apiFetch(url, options = {}) {
  const token = getAccessToken();
  const headers = new Headers(options.headers || {});
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    clearSession();
    window.location.href = document.body.dataset.sessionRecovery || '/';
    throw new Error('登录状态已过期');
  }

  return response;
}


export async function readJson(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw new Error(payload?.detail || `请求失败（${response.status}）`);
  }
  return payload;
}
