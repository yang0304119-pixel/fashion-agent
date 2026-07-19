const ORDER_LABELS = {
  pending: '待发货',
  shipped: '已发货',
  delivered: '已签收',
  refunded: '已退款',
  cancelled: '已取消',
};

const REFUND_LABELS = {
  reviewing: '人工审核中',
  approved: '已批准，渠道处理中',
  succeeded: '模拟退款成功',
  rejected: '审核未通过',
  failed: '渠道处理失败',
};


export function renderMessage(container, message) {
  const row = element('article', `message-row ${message.sender} message-${message.type}`);
  row.dataset.messageId = message.id;

  if (message.sender === 'agent') row.appendChild(agentAvatar());

  const stack = element('div', 'message-stack');
  if (message.type === 'product_card') {
    stack.appendChild(productCard(message.payload));
  } else if (message.type === 'order_card') {
    stack.appendChild(orderCard(message.payload));
  } else if (message.type === 'refund_status') {
    stack.appendChild(refundCard(message));
  } else if (message.type === 'system') {
    stack.appendChild(systemMessage(message.content));
  } else {
    stack.appendChild(textBubble(message));
  }

  if (message.type !== 'system') {
    const time = element('time', 'message-time');
    time.dateTime = message.created_at;
    time.textContent = formatTime(message.created_at);
    stack.appendChild(time);
  }
  row.appendChild(stack);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return row;
}


export function renderLoading(container) {
  const row = element('article', 'message-row agent loading-row');
  row.appendChild(agentAvatar());
  const bubble = element('div', 'typing-bubble');
  bubble.setAttribute('aria-label', 'AI 客服正在思考');
  bubble.append(element('span'), element('span'), element('span'));
  row.appendChild(bubble);
  container.appendChild(row);
  container.scrollTop = container.scrollHeight;
  return row;
}


function textBubble(message) {
  const bubble = element('div', 'message-bubble');
  const text = element('p');
  text.textContent = message.content;
  bubble.appendChild(text);

  const sources = message.payload?.sources || [];
  if (sources.length) {
    const sourceBlock = element('div', 'source-block');
    const label = element('strong');
    label.textContent = '知识来源';
    const list = element('div', 'source-list');
    sources.forEach((source) => {
      const item = element('span', 'source-chip');
      item.textContent = `${source.id} · ${source.title || source.relative_source}`;
      list.appendChild(item);
    });
    sourceBlock.append(label, list);
    bubble.appendChild(sourceBlock);
  }
  return bubble;
}


function productCard(product) {
  const card = element('div', 'rich-card product-message-card');
  const visual = productVisual(product);
  const body = element('div', 'rich-card-body');
  const label = element('span', 'rich-card-label');
  label.textContent = '已发送商品';
  const title = element('strong', 'rich-card-title');
  title.textContent = product.name;
  const price = element('span', 'rich-card-price');
  price.textContent = formatMoney(product.price);
  const variants = element('span', 'rich-card-meta');
  variants.textContent = `${(product.colors || []).join('/')} · ${sizeRange(product.sizes)}`;
  body.append(label, title, price, variants);
  card.append(visual, body);
  return card;
}


function orderCard(order) {
  const card = element('div', 'rich-card order-message-card');
  const icon = element('div', 'order-card-icon');
  icon.textContent = '订单';
  const body = element('div', 'rich-card-body');
  const label = element('span', 'rich-card-label');
  label.textContent = `订单 ${order.order_id}`;
  const title = element('strong', 'rich-card-title');
  title.textContent = order.product_name;
  const meta = element('span', 'rich-card-meta');
  meta.textContent = `实付 ${formatMoney(order.amount)} · ${ORDER_LABELS[order.status] || order.status}`;
  body.append(label, title, meta);
  card.append(icon, body);
  return card;
}


function refundCard(message) {
  const payload = message.payload || {};
  const card = element('div', 'refund-card');
  const header = element('div', 'refund-card-header');
  const icon = element('span', 'refund-icon');
  icon.textContent = payload.status === 'succeeded' ? '✓' : '↻';
  const heading = element('div');
  const kicker = element('span', 'rich-card-label');
  kicker.textContent = `退款单 ${payload.refund_request_id || '处理中'}`;
  const title = element('strong');
  title.textContent = REFUND_LABELS[payload.status] || '退款进度已更新';
  heading.append(kicker, title);
  header.append(icon, heading);

  const summary = element('p');
  summary.textContent = message.content;
  const facts = element('div', 'refund-facts');
  facts.append(
    refundFact('关联订单', payload.order_id ? String(payload.order_id) : '—'),
    refundFact('退款金额', payload.amount != null ? formatMoney(payload.amount) : '—'),
    refundFact('处理方式', payload.human_required ? '人工审核' : '自动处理'),
  );
  card.append(header, summary, refundProgress(payload.status), facts);
  return card;
}


function refundProgress(status) {
  const stages = [
    ['submitted', '已提交'],
    ['reviewing', '审核'],
    ['processing', '渠道处理'],
    ['succeeded', '完成'],
  ];
  const rank = { reviewing: 1, approved: 2, succeeded: 3, rejected: 1, failed: 2 }[status] ?? 0;
  const wrapper = element('div', 'refund-progress');
  stages.forEach(([key, label], index) => {
    const step = element('div', `refund-step ${index <= rank ? 'active' : ''}`);
    if ((status === 'rejected' && key === 'reviewing') || (status === 'failed' && key === 'processing')) {
      step.classList.add('failed');
    }
    step.append(element('i'), textNode(label));
    wrapper.appendChild(step);
  });
  return wrapper;
}


function refundFact(label, value) {
  const item = element('div');
  const key = element('span');
  key.textContent = label;
  const content = element('strong');
  content.textContent = value;
  item.append(key, content);
  return item;
}


function systemMessage(content) {
  const message = element('div', 'system-message');
  const dot = element('span');
  const text = element('p');
  text.textContent = content;
  message.append(dot, text);
  return message;
}


function productVisual(product) {
  const visual = element('div', `product-message-visual product-tone-${((product.product_id || 1) - 1) % 7 + 1}`);
  const image = document.createElement('img');
  image.src = product.image_url || '/assets/products/product-card.svg';
  image.alt = '';
  image.addEventListener('error', () => image.remove());
  const mark = element('span');
  mark.textContent = (product.category || '服装').slice(0, 2);
  visual.append(image, mark);
  return visual;
}


function agentAvatar() {
  const avatar = element('div', 'agent-avatar');
  avatar.textContent = '云';
  return avatar;
}


function sizeRange(sizes = []) {
  if (!sizes.length) return '尺码以详情为准';
  if (sizes.length === 1) return sizes[0];
  return `${sizes[0]}–${sizes[sizes.length - 1]}`;
}


function formatMoney(value) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}


function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit' }).format(date);
}


function textNode(value) {
  const span = element('span');
  span.textContent = value;
  return span;
}


function element(tagName, className = '') {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  return node;
}
