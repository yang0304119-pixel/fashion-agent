import { readJson, saveSession } from './api.js';
import { fillChatMessage, initChat } from './chat.js';
import { renderLoading, renderMessage } from './message-renderer.js';
import { initProductPicker } from './product-picker.js';
import { initOrderPicker } from './order-picker.js';


const state = {
  user: null,
  context: null,
  loadingMessage: null,
};


document.addEventListener('DOMContentLoaded', bootstrap);


async function bootstrap() {
  bindDialogs();
  bindPromptButtons();
  bindClearContext();
  renderWelcome();
  setControlsDisabled(true);

  try {
    state.user = await createDemoSession();
    renderIdentity(state.user);
    initProductPicker({ onSelect: selectProduct, onError: showToast });
    initOrderPicker({ onSelect: selectOrder, onError: showToast });
    initChat({
      getContext: () => state.context,
      onMessage: appendMessage,
      onBusy: setChatBusy,
      onError: appendError,
    });
    setControlsDisabled(false);
  } catch (error) {
    showToast(error.message || '模拟消费者会话初始化失败。');
    appendMessage(systemModel('模拟消费者会话初始化失败，请检查 Mock 外部电商系统数据。'));
  }
}


async function createDemoSession() {
  const response = await fetch('/api/demo-store/session', { method: 'POST' });
  const payload = await readJson(response);
  saveSession(payload.access_token, payload.user);
  return payload.user;
}


function renderWelcome() {
  appendMessage(systemModel('会话已进入 Sandbox。商品、订单与身份数据均会由服务端重新校验。'));
  appendMessage({
    id: messageId('welcome'),
    sender: 'agent',
    type: 'text',
    content: '您好，我是云裳 AI 客服。先从下方选择一件商品或一个订单，我可以继续回答商品知识、推荐尺码、查询库存与订单，也能演示高风险操作的安全审核闭环。',
    payload: { intent: 'welcome', confidence: 1, sources: [] },
    created_at: new Date().toISOString(),
  });
}


function selectProduct(product) {
  state.context = { type: 'product', ...product };
  appendMessage({
    id: messageId('product'),
    sender: 'user',
    type: 'product_card',
    content: '',
    payload: product,
    created_at: new Date().toISOString(),
  });
  appendMessage(systemModel(`已将“${product.name}”设为当前商品。下一条消息会自动携带 product_id=${product.product_id}。`));
  renderContext();
  fillChatMessage('');
}


function selectOrder(order) {
  state.context = { type: 'order', ...order };
  appendMessage({
    id: messageId('order'),
    sender: 'user',
    type: 'order_card',
    content: '',
    payload: order,
    created_at: new Date().toISOString(),
  });
  appendMessage(systemModel(`已将订单 ${order.order_id} 设为当前订单。下一条消息会自动携带 order_id=${order.order_id}。`));
  renderContext();
  fillChatMessage('');
}


function renderContext() {
  const productSlot = document.getElementById('currentProductSlot');
  const orderSlot = document.getElementById('currentOrderSlot');
  const mobile = document.getElementById('mobileContext');
  const clear = document.getElementById('clearContextBtn');
  clear.disabled = !state.context;

  renderEmptySlot(productSlot, 'product');
  renderEmptySlot(orderSlot, 'order');
  mobile.replaceChildren();
  mobile.classList.toggle('hidden', !state.context);

  if (!state.context) {
    document.getElementById('chatInput').placeholder = '先选择商品或订单，再输入你的问题…';
    return;
  }

  if (state.context.type === 'product') {
    renderProductSlot(productSlot, state.context);
    document.getElementById('chatInput').placeholder = '询问这件商品的尺码、库存、材质或洗护…';
    mobile.appendChild(contextChip('商品', state.context.name));
  } else {
    renderOrderSlot(orderSlot, state.context);
    document.getElementById('chatInput').placeholder = '询问这个订单的物流、状态或申请退款…';
    mobile.appendChild(contextChip(`订单 ${state.context.order_id}`, state.context.product_name));
  }
}


function renderEmptySlot(slot, type) {
  const copy = type === 'product'
    ? ['当前商品', '尚未选择商品', '从输入区添加商品卡片']
    : ['当前订单', '尚未选择订单', '仅展示模拟消费者订单'];
  slot.classList.remove('selected');
  const icon = slot.querySelector('.slot-icon');
  slot.replaceChildren(icon);
  const text = document.createElement('div');
  text.append(label('small', copy[0]), label('strong', copy[1]), label('span', copy[2]));
  slot.appendChild(text);
}


function renderProductSlot(slot, product) {
  slot.classList.add('selected');
  const icon = slot.querySelector('.slot-icon');
  slot.replaceChildren(icon);
  const text = document.createElement('div');
  text.append(label('small', '当前商品'), label('strong', product.name), label('span', `${formatMoney(product.price)} · 库存 ${product.stock}`));
  slot.appendChild(text);
}


function renderOrderSlot(slot, order) {
  slot.classList.add('selected');
  const icon = slot.querySelector('.slot-icon');
  slot.replaceChildren(icon);
  const text = document.createElement('div');
  text.append(label('small', `当前订单 ${order.order_id}`), label('strong', order.product_name), label('span', `${formatMoney(order.amount)} · ${order.status}`));
  slot.appendChild(text);
}


function contextChip(kicker, title) {
  const chip = document.createElement('div');
  const text = document.createElement('div');
  text.append(label('small', kicker), label('strong', title));
  const button = label('button', '清除');
  button.type = 'button';
  button.addEventListener('click', clearContext);
  chip.append(text, button);
  return chip;
}


function bindClearContext() {
  document.getElementById('clearContextBtn').addEventListener('click', clearContext);
}


function clearContext() {
  if (!state.context) return;
  state.context = null;
  renderContext();
  appendMessage(systemModel('已清除当前卡片上下文。你可以重新选择商品或订单。'));
}


function appendMessage(message) {
  if (state.loadingMessage) {
    state.loadingMessage.remove();
    state.loadingMessage = null;
  }
  renderMessage(document.getElementById('messages'), message);
}


function appendError(message) {
  appendMessage({
    id: messageId('error'),
    sender: 'agent',
    type: 'text',
    content: message,
    payload: { intent: 'error', confidence: 0, sources: [] },
    created_at: new Date().toISOString(),
  });
}


function setChatBusy(isBusy) {
  document.getElementById('sendBtn').disabled = isBusy;
  document.getElementById('chatInput').disabled = isBusy;
  document.getElementById('openProductPicker').disabled = isBusy;
  document.getElementById('openOrderPicker').disabled = isBusy;
  document.getElementById('clearContextBtn').disabled = isBusy || !state.context;
  if (isBusy) state.loadingMessage = renderLoading(document.getElementById('messages'));
}


function setControlsDisabled(disabled) {
  ['openProductPicker', 'openOrderPicker', 'chatInput', 'sendBtn'].forEach((id) => {
    document.getElementById(id).disabled = disabled;
  });
}


function bindPromptButtons() {
  document.querySelectorAll('[data-prompt]').forEach((button) => {
    button.addEventListener('click', () => fillChatMessage(button.dataset.prompt));
  });
}


function bindDialogs() {
  document.querySelectorAll('[data-close-dialog]').forEach((button) => {
    button.addEventListener('click', () => document.getElementById(button.dataset.closeDialog).close());
  });
  document.querySelectorAll('dialog').forEach((dialog) => {
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
}


function renderIdentity(user) {
  document.getElementById('demoIdentity').textContent = user.username;
  document.getElementById('memberAvatar').textContent = user.username.slice(0, 1);
}


function showToast(message) {
  const toast = document.getElementById('pageToast');
  toast.textContent = message;
  toast.classList.remove('hidden');
  window.setTimeout(() => toast.classList.add('hidden'), 3200);
}


function systemModel(content) {
  return {
    id: messageId('system'),
    sender: 'system',
    type: 'system',
    content,
    payload: null,
    created_at: new Date().toISOString(),
  };
}


function messageId(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}


function formatMoney(value) {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value || 0));
}


function label(tagName, text) {
  const node = document.createElement(tagName);
  node.textContent = text;
  return node;
}
