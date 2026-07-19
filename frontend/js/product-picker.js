import { apiFetch, readJson } from './api.js';


export function initProductPicker({ onSelect, onError }) {
  const dialog = document.getElementById('productPickerDialog');
  const content = document.getElementById('productPickerContent');
  let products = null;

  document.getElementById('openProductPicker').addEventListener('click', async () => {
    dialog.showModal();
    if (products) return;
    showState(content, '正在读取当前店铺商品…');
    try {
      const payload = await readJson(await apiFetch('/api/demo-store/products'));
      products = payload.data || [];
      renderProducts(content, products, (product) => {
        dialog.close();
        onSelect(product);
      });
    } catch (error) {
      showState(content, error.message || '商品加载失败。', true);
      onError(error.message || '商品加载失败。');
    }
  });
}


function renderProducts(container, products, onSelect) {
  if (!products.length) {
    showState(container, '当前店铺暂无可咨询商品。');
    return;
  }
  const grid = element('div', 'picker-grid product-picker-grid');
  products.forEach((product) => {
    const card = element('article', 'picker-card product-picker-card');
    const visual = element('div', `picker-product-visual product-tone-${((product.product_id || 1) - 1) % 7 + 1}`);
    const image = document.createElement('img');
    image.src = product.image_url || '/assets/products/product-card.svg';
    image.alt = '';
    image.addEventListener('error', () => image.remove());
    const category = element('span');
    category.textContent = product.category;
    visual.append(image, category);

    const body = element('div', 'picker-card-body');
    const title = document.createElement('h3');
    title.textContent = product.name;
    const price = element('strong', 'picker-price');
    price.textContent = formatMoney(product.price);
    const variants = document.createElement('p');
    variants.textContent = `${(product.colors || []).join(' / ')} · ${(product.sizes || []).join(' / ')}`;
    const footer = element('div', 'picker-card-footer');
    const stock = element('span', `stock-badge ${product.stock > 0 ? 'in-stock' : 'out-of-stock'}`);
    stock.textContent = product.stock > 0 ? `有库存 · ${product.stock}件` : '暂时缺货';
    const button = element('button', 'select-context-button');
    button.type = 'button';
    button.textContent = '发送商品卡片';
    button.addEventListener('click', () => onSelect(product));
    footer.append(stock, button);
    body.append(title, price, variants, footer);
    card.append(visual, body);
    grid.appendChild(card);
  });
  container.replaceChildren(grid);
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
