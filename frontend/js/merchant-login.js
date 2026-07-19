import { login, logout } from './auth.js';


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
    errorElement.textContent = '请输入运营台管理员账号和密码。';
    return;
  }

  button.disabled = true;
  errorElement.textContent = '';
  try {
    const user = await login(username, passwordInput.value);
    passwordInput.value = '';
    if (user.role !== 'admin') {
      logout();
      errorElement.textContent = '该入口仅供商户授权的运营台管理员使用。';
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
