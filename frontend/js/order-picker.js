import { apiFetch, readJson } from './api.js';


const ORDER_LABELS = {
  pending: '待发货',
  shipped: '已发货',
  delivered: '已签收',
  refunded: '已退款',
  cancelled: '已取消',
};


export function initOrderPicker({ onSelect, onError }) {
  const dialog = document.getElementById('orderPickerDialog');
  const content = document.getElementById('orderPickerContent');

  document.getElementById('openOrderPicker').addEventListener('click', async () => {
    dialog.showModal();
    showState(content, '正在读取模拟消费者订单…');
    try {
      const payload = await readJson(await apiFetch('/api/orders?page=1&page_size=100'));
      renderOrders(content, payload.data || [], (order) => {
        dialog.close();
        onSelect({
          order_id: order.id,
          product_name: order.product_name,
          amount: order.total_price,
          status: order.status,
          quantity: order.quantity,
        });
      });
    } catch (error) {
      showState(content, error.message || '订单加载失败。', true);
      onError(error.message || '订单加载失败。');
    }
  });
}


function renderOrders(container, orders, onSelect) {
  if (!orders.length) {
    showState(container, '模拟消费者暂无订单。');
    return;
  }
  const list = element('div', 'picker-grid order-picker-grid');
  orders.forEach((order) => {
    const card = element('article', 'picker-card order-picker-card');
    const orderMark = element('div', 'picker-order-mark');
    orderMark.innerHTML = '<span>ORDER</span><strong>订单</strong>';
    const body = element('div', 'picker-card-body');
    const top = element('div', 'order-picker-top');
    const number = element('span', 'rich-card-label');
    number.textContent = `订单 ${order.id}`;
    const status = element('span', `order-status status-${order.status}`);
    status.textContent = ORDER_LABELS[order.status] || order.status;
    top.append(number, status);
    const title = document.createElement('h3');
    title.textContent = order.product_name;
    const meta = document.createElement('p');
    meta.textContent = `数量 ${order.quantity} · 实付 ${formatMoney(order.total_price)}`;
    const button = element('button', 'select-context-button');
    button.type = 'button';
    button.textContent = '发送订单卡片';
    button.addEventListener('click', () => onSelect(order));
    body.append(top, title, meta, button);
    card.append(orderMark, body);
    list.appendChild(card);
  });
  container.replaceChildren(list);
}


function showState(container, message, isError = false) {
  const state = element('div', `picker-state ${isError ? 'error' : ''}`);
  state.textContent = message;
  container.replaceChildren(state);
}


function formatMoney(value) {
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value || 0));
}


function element(tagName, className = '') {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  return node;
}
