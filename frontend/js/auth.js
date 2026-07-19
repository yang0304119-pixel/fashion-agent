import {
  apiFetch,
  clearSession,
  getAccessToken,
  getStoredUser,
  readJson,
  saveSession,
} from './api.js';


export async function login(username, password) {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const payload = await readJson(response);
  saveSession(payload.access_token, payload.user);
  return payload.user;
}


export async function restoreUser() {
  if (!getAccessToken()) return null;
  const storedUser = getStoredUser();
  const response = await apiFetch('/api/auth/me');
  const user = await readJson(response);
  saveSession(getAccessToken(), user);
  return user || storedUser;
}


export function logout() {
  clearSession();
}
