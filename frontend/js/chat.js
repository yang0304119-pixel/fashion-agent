import { apiFetch, readJson } from './api.js';


const CHAT_SESSION_KEY = 'demo_chat_session_id';


function createSessionId() {
  if (window.crypto?.randomUUID) return crypto.randomUUID();
  return `session_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}


function getSessionId() {
  let sessionId = sessionStorage.getItem(CHAT_SESSION_KEY);
  if (!sessionId) {
    sessionId = createSessionId();
    sessionStorage.setItem(CHAT_SESSION_KEY, sessionId);
  }
  return sessionId;
}


function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}


function compactContext(context) {
  if (!context) return null;
  if (context.type === 'product') {
    return { type: 'product', product_id: context.product_id };
  }
  return { type: 'order', order_id: context.order_id };
}


export function initChat({ getContext, onMessage, onBusy, onError }) {
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const content = input.value.trim();
    if (!content) return;

    const context = compactContext(getContext());
    input.value = '';
    resizeTextarea(input);
    onMessage({
      id: messageId('user'),
      sender: 'user',
      type: 'text',
      content,
      payload: null,
      created_at: new Date().toISOString(),
    });
    onBusy(true);

    try {
      const response = await apiFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: getSessionId(),
          message: content,
          context,
        }),
      });
      const payload = await readJson(response);
      sessionStorage.setItem(CHAT_SESSION_KEY, payload.session_id);
      onMessage({
        id: messageId('agent'),
        sender: 'agent',
        type: payload.message_type || 'text',
        content: payload.answer || '暂时没有可用回复。',
        payload: {
          ...(payload.payload || {}),
          intent: payload.intent,
          confidence: payload.confidence,
          sources: payload.sources || [],
        },
        created_at: new Date().toISOString(),
      });
    } catch (error) {
      if (error.message !== '登录状态已过期') {
        onError(error.message || '请求失败，请稍后重试。');
      }
    } finally {
      onBusy(false);
      input.focus();
    }
  });

  input.addEventListener('input', () => resizeTextarea(input));
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });
}


export function fillChatMessage(message) {
  const input = document.getElementById('chatInput');
  input.value = message;
  resizeTextarea(input);
  input.focus();
}


function resizeTextarea(input) {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 132)}px`;
}
