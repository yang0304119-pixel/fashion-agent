import { login, logout } from './auth.js';
import { permissionSet } from './admin-permissions.js';


document.addEventListener('DOMContentLoaded', () => {
  logout();
  document.getElementById('merchantLoginForm').addEventListener('submit', submitLogin);
});


async function submitLogin(event) {
  event.preventDefault();
  const username = document.getElementById('username').value.trim();
  const passwordInput = document.getElementById('password');
  const errorElement = document.getElementById('loginError');
  const button = document.getElementById('loginBtn');

  if (!username || !passwordInput.value) {
    errorElement.textContent = '请输入商家员工账号和密码。';
    return;
  }

  button.disabled = true;
  errorElement.textContent = '';
  try {
    const user = await login(username, passwordInput.value);
    passwordInput.value = '';
    if (!permissionSet(user).size) {
      logout();
      errorElement.textContent = '该入口仅供商户授权的员工账号使用。';
      return;
    }
    window.location.href = '/admin.html';
  } catch (error) {
    passwordInput.value = '';
    errorElement.textContent = error.message || '登录失败。';
  } finally {
    button.disabled = false;
  }
}
