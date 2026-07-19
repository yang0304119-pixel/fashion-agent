import { apiFetch, getAccessToken, readJson } from './api.js';
import { logout, restoreUser } from './auth.js';


const PAGE_SIZE = 20;
const STATUSES = ['reviewing', 'approved', 'succeeded', 'rejected', 'failed'];
const STATUS_META = {
  reviewing: { label: '待审核', title: '待审核申请', description: '需要授权人员作出批准或拒绝决定。' },
  approved: { label: '已批准', title: '已批准退款', description: '审核已通过，等待退款渠道完成处理。' },
  succeeded: { label: '已成功', title: '退款成功', description: '退款渠道已返回成功并记录平台流水号。' },
  rejected: { label: '已拒绝', title: '已拒绝申请', description: '授权人员已拒绝的退款申请。' },
  failed: { label: '渠道失败', title: '渠道失败', description: '审核已通过，但退款渠道执行失败。' },
};
const state = {
  user: null,
  view: 'dashboard',
  status: 'reviewing',
  page: 1,
  ordersPage: 1,
  ticketsPage: 1,
  tracesPage: 1,
  selectedSessionId: '',
  selectedTraceId: null,
  casesPage: 1,
  selectedCaseId: null,
  knowledgePage: 1,
  knowledgeBuildsPage: 1,
  knowledgeBuilds: [],
  selectedKnowledgeDocumentId: null,
  selectedKnowledgeRevisionId: null,
  selectedRefund: null,
};


document.addEventListener('DOMContentLoaded', bootstrap);


async function bootstrap() {
  bindEvents();
  if (!getAccessToken()) {
    redirectToLogin();
    return;
  }
  try {
    state.user = await restoreUser();
    if (state.user?.role !== 'admin') {
      logout();
      redirectToLogin('当前账号没有管理员权限。');
      return;
    }
    document.getElementById('adminIdentity').textContent = `${state.user.username} · 管理员`;
    document.getElementById('adminGuard').classList.add('hidden');
    document.getElementById('adminPanel').classList.remove('hidden');
    await openCurrentView();
  } catch (error) {
    if (error.message !== '登录状态已过期') {
      logout();
      redirectToLogin(error.message || '管理员身份验证失败。');
    }
  }
}


function bindEvents() {
  document.getElementById('adminLogoutBtn').addEventListener('click', () => {
    logout();
    window.location.href = '/';
  });
  document.getElementById('refreshRefundsBtn').addEventListener('click', refreshWorkspace);
  window.addEventListener('hashchange', openCurrentView);
  document.getElementById('adminOrderStatusFilter').addEventListener('change', () => {
    state.ordersPage = 1;
    loadOrders();
  });
  document.getElementById('adminTicketStatusFilter').addEventListener('change', () => {
    state.ticketsPage = 1;
    loadTickets();
  });
  document.getElementById('adminTicketTypeFilter').addEventListener('change', () => {
    state.ticketsPage = 1;
    loadTickets();
  });
  document.getElementById('traceSearchForm').addEventListener('submit', (event) => {
    event.preventDefault();
    state.selectedSessionId = document.getElementById('traceSessionSearch').value.trim();
    state.tracesPage = 1;
    loadTraces();
  });
  document.getElementById('clearTraceSearchBtn').addEventListener('click', () => {
    document.getElementById('traceSessionSearch').value = '';
    state.selectedSessionId = '';
    state.tracesPage = 1;
    loadTraces();
  });
  document.getElementById('traceIntentFilter').addEventListener('change', () => {
    state.tracesPage = 1;
    loadTraces();
  });
  document.getElementById('traceStatusFilter').addEventListener('change', () => {
    state.tracesPage = 1;
    loadTraces();
  });
  ['caseResolvedFilter', 'caseIntentFilter', 'caseKnowledgeFilter'].forEach((id) => {
    document.getElementById(id).addEventListener('change', () => {
      state.casesPage = 1;
      loadCases();
    });
  });
  document.getElementById('caseAnnotationForm').addEventListener('submit', saveCaseAnnotation);
  document.getElementById('cancelCaseAnnotationBtn').addEventListener('click', () => {
    document.getElementById('caseDetailDialog').close();
  });
  document.getElementById('knowledgeSearchForm').addEventListener('submit', (event) => {
    event.preventDefault();
    state.knowledgePage = 1;
    loadKnowledgeDocuments();
  });
  ['knowledgeTypeFilter', 'knowledgeParseFilter', 'knowledgeReviewFilter'].forEach((id) => {
    document.getElementById(id).addEventListener('change', () => {
      state.knowledgePage = 1;
      loadKnowledgeDocuments();
    });
  });
  document.getElementById('clearKnowledgeFiltersBtn').addEventListener('click', () => {
    ['knowledgeSearchInput', 'knowledgeTypeFilter', 'knowledgeParseFilter', 'knowledgeReviewFilter'].forEach((id) => {
      document.getElementById(id).value = '';
    });
    state.knowledgePage = 1;
    loadKnowledgeDocuments();
  });
  document.getElementById('openKnowledgeUploadBtn').addEventListener('click', openKnowledgeUpload);
  document.getElementById('knowledgeUploadForm').addEventListener('submit', uploadKnowledgeDocument);
  document.getElementById('cancelKnowledgeUploadBtn').addEventListener('click', () => {
    document.getElementById('knowledgeUploadDialog').close();
  });
  document.getElementById('parseKnowledgeBtn').addEventListener('click', parseSelectedKnowledgeRevision);
  document.getElementById('saveKnowledgeContentBtn').addEventListener('click', saveSelectedKnowledgeContent);
  document.getElementById('approveKnowledgeBtn').addEventListener('click', approveSelectedKnowledgeRevision);
  document.getElementById('rejectKnowledgeBtn').addEventListener('click', rejectSelectedKnowledgeRevision);
  document.getElementById('knowledgeRevisionUploadForm').addEventListener('submit', uploadKnowledgeRevision);
  document.getElementById('createKnowledgeBuildBtn').addEventListener('click', createKnowledgeBuild);
  document.getElementById('rollbackKnowledgeBuildBtn').addEventListener('click', rollbackKnowledgeBuild);
  document.getElementById('knowledgeTestForm').addEventListener('submit', runKnowledgeTest);
  document.querySelectorAll('.metric-tab').forEach((tab) => {
    tab.addEventListener('click', () => selectStatus(tab.dataset.status));
  });
  document.querySelectorAll('[data-dashboard-refund-status]').forEach((card) => {
    card.addEventListener('click', () => {
      state.status = card.dataset.dashboardRefundStatus;
      state.page = 1;
    });
  });
  document.querySelectorAll('[data-close-dialog]').forEach((button) => {
    button.addEventListener('click', () => document.getElementById(button.dataset.closeDialog).close());
  });
  document.getElementById('confirmApproveBtn').addEventListener('click', approveSelectedRefund);
  document.getElementById('cancelRejectBtn').addEventListener('click', () => {
    document.getElementById('rejectDialog').close();
  });
  document.getElementById('rejectForm').addEventListener('submit', rejectSelectedRefund);
  bindBackdropClose('refundDetailDialog');
  bindBackdropClose('ticketDetailDialog');
  bindBackdropClose('adminOrderDialog');
  bindBackdropClose('approveDialog');
  bindBackdropClose('rejectDialog');
  bindBackdropClose('caseDetailDialog');
  bindBackdropClose('knowledgeUploadDialog');
  bindBackdropClose('knowledgeDetailDialog');
}


async function openCurrentView() {
  const requestedView = window.location.hash.replace('#', '');
  const availableViews = ['dashboard', 'knowledge', 'orders', 'refunds', 'tickets', 'traces', 'cases'];
  state.view = availableViews.includes(requestedView) ? requestedView : 'dashboard';
  document.querySelectorAll('[data-admin-view]').forEach((link) => {
    link.classList.toggle('active', link.dataset.adminView === state.view);
  });
  document.querySelectorAll('[data-admin-panel]').forEach((panel) => {
    panel.classList.toggle('hidden', panel.dataset.adminPanel !== state.view);
  });

  const heading = document.getElementById('adminPageHeading');
  const eyebrow = heading.querySelector('.eyebrow');
  const title = heading.querySelector('h1');
  const description = heading.querySelector('p:not(.eyebrow)');
  const refreshButton = document.getElementById('refreshRefundsBtn');
  if (state.view === 'dashboard') {
    eyebrow.textContent = 'OPERATIONS OVERVIEW';
    title.textContent = '运营总览';
    description.textContent = '查看当前租户的客服业务和待办事项。';
    refreshButton.textContent = '刷新总览';
    await loadDashboard();
  } else if (state.view === 'knowledge') {
    eyebrow.textContent = 'KNOWLEDGE LIFECYCLE';
    title.textContent = '知识文档';
    description.textContent = '上传、解析、修订和审核当前租户的商家知识。';
    refreshButton.textContent = '刷新文档';
    await Promise.all([loadKnowledgeDocuments(), loadKnowledgeBuilds()]);
  } else if (state.view === 'orders') {
    eyebrow.textContent = 'BUSINESS CONTEXT';
    title.textContent = '业务上下文';
    description.textContent = '只读查看外部业务系统提供的用户、商品、订单与关联售后信息。';
    refreshButton.textContent = '刷新上下文';
    await loadOrders();
  } else if (state.view === 'tickets') {
    eyebrow.textContent = 'SERVICE OPERATIONS';
    title.textContent = '人工接管与工单';
    description.textContent = '查看复杂问题的人工接管、关联业务数据和处理结果。';
    refreshButton.textContent = '刷新工单';
    await loadTickets();
  } else if (state.view === 'traces') {
    eyebrow.textContent = 'AGENT OBSERVABILITY';
    title.textContent = '执行轨迹';
    description.textContent = '按会话复盘意图识别、工作流、槽位、RAG来源和错误阶段。';
    refreshButton.textContent = '刷新轨迹';
    await loadTraces();
  } else if (state.view === 'cases') {
    eyebrow.textContent = 'QUALITY OPERATIONS';
    title.textContent = '未解决案例';
    description.textContent = '人工标注意图和答案，并维护知识库候选队列。';
    refreshButton.textContent = '刷新案例';
    await Promise.all([loadCaseStats(), loadCases()]);
  } else {
    applyRefundStatusUI();
    eyebrow.textContent = 'HIGH-RISK REVIEW';
    title.textContent = '高风险操作审核';
    description.textContent = '审核退款等高风险业务请求，并追踪外部渠道执行结果。';
    refreshButton.textContent = '刷新数据';
    await Promise.all([loadStatusCounts(), loadRefunds()]);
  }
}


function bindBackdropClose(dialogId) {
  const dialog = document.getElementById(dialogId);
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog.close();
  });
}


function redirectToLogin(message = '') {
  if (message) sessionStorage.setItem('login_notice', message);
  window.location.href = '/';
}


async function refreshWorkspace() {
  const button = document.getElementById('refreshRefundsBtn');
  button.disabled = true;
  try {
    if (state.view === 'dashboard') {
      await loadDashboard();
      showToast('运营总览已刷新。');
    } else if (state.view === 'knowledge') {
      await Promise.all([loadKnowledgeDocuments(), loadKnowledgeBuilds()]);
      showToast('知识文档已刷新。');
    } else if (state.view === 'orders') {
      await loadOrders();
      showToast('订单数据已刷新。');
    } else if (state.view === 'tickets') {
      await loadTickets();
      showToast('工单数据已刷新。');
    } else if (state.view === 'traces') {
      await loadTraces();
      showToast('执行轨迹已刷新。');
    } else if (state.view === 'cases') {
      await Promise.all([loadCaseStats(), loadCases()]);
      showToast('未解决案例已刷新。');
    } else {
      await Promise.all([loadStatusCounts(), loadRefunds()]);
      showToast('退款数据已刷新。');
    }
  } finally {
    button.disabled = false;
  }
}


async function loadKnowledgeDocuments() {
  const container = document.getElementById('adminKnowledgeContent');
  showLoadingState(container, '正在读取知识文档…');
  const params = new URLSearchParams({
    page: state.knowledgePage,
    page_size: PAGE_SIZE,
  });
  const search = document.getElementById('knowledgeSearchInput').value.trim();
  const knowledgeType = document.getElementById('knowledgeTypeFilter').value;
  const parseStatus = document.getElementById('knowledgeParseFilter').value;
  const reviewStatus = document.getElementById('knowledgeReviewFilter').value;
  if (search) params.set('search', search);
  if (knowledgeType) params.set('knowledge_type', knowledgeType);
  if (parseStatus) params.set('parse_status', parseStatus);
  if (reviewStatus) params.set('review_status', reviewStatus);

  try {
    const payload = await requestJson(`/api/admin/knowledge/documents?${params}`);
    renderKnowledgeDocuments(container, payload.data);
    renderKnowledgePagination(payload);
  } catch (error) {
    showErrorState(container, error.message);
    document.getElementById('adminKnowledgePagination').replaceChildren();
  }
}


async function loadKnowledgeBuilds() {
  const container = document.getElementById('knowledgeBuildsContent');
  showLoadingState(container, '正在读取知识库版本…');
  const params = new URLSearchParams({
    page: state.knowledgeBuildsPage,
    page_size: 10,
  });
  try {
    const [payload, activePayload, readyPayload] = await Promise.all([
      requestJson(`/api/admin/knowledge/index-builds?${params}`),
      requestJson('/api/admin/knowledge/index-builds?status=active&page=1&page_size=1'),
      requestJson('/api/admin/knowledge/index-builds?status=ready&page=1&page_size=100'),
    ]);
    const testableBuilds = [...readyPayload.data, ...activePayload.data];
    state.knowledgeBuilds = testableBuilds;
    renderKnowledgeBuildSummary(payload.data, activePayload.data[0], readyPayload.data[0]);
    renderKnowledgeBuilds(container, payload.data);
    renderKnowledgeBuildsPagination(payload);
    renderKnowledgeTestBuildOptions(testableBuilds);
  } catch (error) {
    showErrorState(container, error.message);
    document.getElementById('knowledgeBuildSummary').replaceChildren();
    document.getElementById('knowledgeBuildsPagination').replaceChildren();
    renderKnowledgeTestBuildOptions([]);
  }
}


function renderKnowledgeBuildSummary(builds, activeBuild = null, readyBuild = null) {
  const summary = document.getElementById('knowledgeBuildSummary');
  const active = activeBuild || builds.find((build) => build.status === 'active');
  const ready = readyBuild || builds.find((build) => build.status === 'ready');
  const latest = builds[0];
  summary.replaceChildren(
    knowledgeBuildMetric('当前线上版本', active ? `Build #${active.id}` : '尚未上线'),
    knowledgeBuildMetric('最新候选版本', ready ? `Build #${ready.id}` : '暂无候选'),
    knowledgeBuildMetric('最近构建结果', latest ? knowledgeBuildStatusLabel(latest.status) : '尚未构建'),
  );
  document.getElementById('rollbackKnowledgeBuildBtn').disabled = !active?.previous_active_build_id;
}


function knowledgeBuildMetric(label, value) {
  const card = document.createElement('article');
  const labelNode = document.createElement('span');
  labelNode.textContent = label;
  const valueNode = document.createElement('strong');
  valueNode.textContent = value;
  card.append(labelNode, valueNode);
  return card;
}


function renderKnowledgeBuilds(container, builds) {
  if (!builds.length) {
    showEmptyState(container, '尚无知识库版本', '审核知识文档后，可以创建第一个候选知识库。');
    return;
  }
  const wrapper = element('div', 'table-wrap');
  const table = element('table', 'data-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['版本', '状态', '文档/Chunk', '构建时间', '上线时间', '错误', '操作'].forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);
  const body = document.createElement('tbody');
  builds.forEach((build) => {
    const row = document.createElement('tr');
    const actions = element('div', 'knowledge-actions-cell');
    if (build.status === 'ready') {
      actions.appendChild(actionButton('上线', 'primary', () => activateKnowledgeBuild(build.id)));
    } else {
      actions.appendChild(textCell(build.status === 'active' ? '消费者使用中' : '—'));
    }
    [
      itemCell(`Build #${build.id}`, build.collection_name || '集合尚未创建'),
      knowledgeBuildStatusCell(build.status),
      textCell(`${build.document_count} / ${build.chunk_count}`),
      textCell(formatDate(build.finished_at || build.started_at)),
      textCell(formatDate(build.activated_at)),
      textCell(build.error_message || '—'),
      actions,
    ].forEach((cell) => {
      const td = document.createElement('td');
      td.appendChild(cell);
      row.appendChild(td);
    });
    body.appendChild(row);
  });
  table.append(head, body);
  wrapper.appendChild(table);
  container.replaceChildren(wrapper);
}


function renderKnowledgeTestBuildOptions(builds) {
  const select = document.getElementById('knowledgeTestBuild');
  const previous = select.value;
  select.replaceChildren();
  const testable = builds.filter((build) => ['active', 'ready', 'superseded'].includes(build.status));
  testable.forEach((build) => {
    const option = document.createElement('option');
    option.value = String(build.id);
    const role = build.status === 'active'
      ? '当前线上'
      : build.status === 'ready'
        ? '候选版本'
        : '历史版本';
    option.textContent = `${role} · Build #${build.id} · ${build.chunk_count} chunks`;
    select.appendChild(option);
  });
  if (testable.some((build) => String(build.id) === previous)) {
    select.value = previous;
  } else {
    const candidate = testable.find((build) => build.status === 'ready');
    const active = testable.find((build) => build.status === 'active');
    select.value = String(candidate?.id || active?.id || testable[0]?.id || '');
  }
  select.disabled = !testable.length;
  document.getElementById('runKnowledgeTestBtn').disabled = !testable.length;
  if (!testable.length) {
    showEmptyState(
      document.getElementById('knowledgeTestResult'),
      '暂无可测试知识库版本',
      '请先构建候选知识库，或上线一个成功版本。',
    );
  }
}


async function runKnowledgeTest(event) {
  event.preventDefault();
  const question = document.getElementById('knowledgeTestQuestion').value.trim();
  const buildId = Number(document.getElementById('knowledgeTestBuild').value);
  const topK = Number(document.getElementById('knowledgeTestTopK').value);
  const result = document.getElementById('knowledgeTestResult');
  const button = document.getElementById('runKnowledgeTestBtn');
  if (!question || !buildId) return;
  button.disabled = true;
  showLoadingState(result, '正在生成回答并分析混合检索结果…');
  try {
    const payload = await requestJson('/api/admin/knowledge/question-tests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, build_id: buildId, top_k: topK }),
    });
    renderKnowledgeTestResult(payload.data);
  } catch (error) {
    showErrorState(result, error.message || '知识库测试失败。');
  } finally {
    button.disabled = !document.getElementById('knowledgeTestBuild').value;
  }
}


function renderKnowledgeTestResult(data) {
  const container = document.getElementById('knowledgeTestResult');
  const summary = element('div', 'knowledge-test-summary');
  summary.append(
    knowledgeBuildMetric('测试版本', `Build #${data.build.id} · ${knowledgeBuildStatusLabel(data.build.status)}`),
    knowledgeBuildMetric('召回数量', `${data.hits.length} 条`),
    knowledgeBuildMetric('知识类型过滤', data.knowledge_type_filter || '未限定'),
  );
  const queryPanel = element('section', 'knowledge-query-panel');
  const queryTitle = document.createElement('strong');
  queryTitle.textContent = '查询改写';
  const queryText = document.createElement('p');
  queryText.textContent = data.original_query === data.rewritten_query
    ? `未改写：${data.original_query}`
    : `原问题：${data.original_query}\n改写后：${data.rewritten_query}`;
  queryPanel.append(queryTitle, queryText);
  const answer = element('section', 'knowledge-answer-card');
  const answerTitle = document.createElement('strong');
  answerTitle.textContent = '候选回答';
  const answerText = document.createElement('pre');
  answerText.textContent = data.answer;
  answer.append(answerTitle, answerText);
  const hits = element('div', 'knowledge-hit-list');
  if (!data.hits.length) {
    showEmptyState(hits, '没有召回结果', '当前版本无法为该问题找到达到阈值的知识段落。');
  } else {
    data.hits.forEach((hit) => hits.appendChild(knowledgeHitCard(hit)));
  }
  container.replaceChildren(summary, queryPanel, answer, hits);
}


function knowledgeHitCard(hit) {
  const card = element('article', 'knowledge-hit-card');
  const header = element('div', 'knowledge-hit-header');
  const title = document.createElement('strong');
  title.textContent = `#${hit.rank} [${hit.source_id}] ${hit.title || '未命名来源'}`;
  const version = document.createElement('span');
  version.textContent = `文档 #${hit.document_id || '—'} · v${hit.version_no || '—'} · Revision #${hit.revision_id || '—'}`;
  header.append(title, version);
  const scores = element('div', 'knowledge-score-grid');
  [
    ['Dense', hit.dense_score, hit.dense_rank],
    ['BM25', hit.bm25_score, hit.bm25_rank],
    ['融合', hit.fusion_score, hit.fusion_rank],
  ].forEach(([label, score, rank]) => {
    const item = document.createElement('span');
    item.textContent = `${label} ${formatScore(score)} · rank ${rank || '—'}`;
    scores.appendChild(item);
  });
  const meta = document.createElement('p');
  meta.className = 'knowledge-hit-meta';
  meta.textContent = `${knowledgeTypeLabel(hit.knowledge_type)} · ${hit.category || '未分类'} · ${hit.relative_source || '安全来源标识不可用'} · Chunk ${hit.chunk_id}`;
  const preview = document.createElement('pre');
  preview.className = 'knowledge-hit-preview';
  preview.textContent = hit.preview;
  card.append(header, scores, meta, preview);
  return card;
}


function formatScore(value) {
  return Number(value || 0).toFixed(4);
}


function renderKnowledgeBuildsPagination(payload) {
  const container = document.getElementById('knowledgeBuildsPagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const summary = document.createElement('span');
  summary.textContent = `共 ${payload.total} 个版本 · 第 ${payload.page}/${totalPages} 页`;
  const previous = actionButton('上一页', 'secondary', () => changeKnowledgeBuildPage(payload.page - 1));
  const next = actionButton('下一页', 'secondary', () => changeKnowledgeBuildPage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(summary, previous, next);
}


function changeKnowledgeBuildPage(page) {
  state.knowledgeBuildsPage = page;
  loadKnowledgeBuilds();
}


async function createKnowledgeBuild() {
  const button = document.getElementById('createKnowledgeBuildBtn');
  button.disabled = true;
  try {
    const payload = await requestJson('/api/admin/knowledge/index-builds', {
      method: 'POST',
    });
    showToast(`候选知识库 Build #${payload.data.id} 构建成功，尚未影响消费者。`);
    state.knowledgeBuildsPage = 1;
    await loadKnowledgeBuilds();
  } catch (error) {
    showToast(error.message || '候选知识库构建失败，当前线上版本未受影响。', true);
    await loadKnowledgeBuilds();
  } finally {
    button.disabled = false;
  }
}


async function activateKnowledgeBuild(buildId) {
  try {
    const payload = await requestJson(`/api/admin/knowledge/index-builds/${buildId}/activate`, {
      method: 'POST',
    });
    showToast(`Build #${payload.data.id} 已上线，消费者开始使用新知识。`);
    await loadKnowledgeBuilds();
  } catch (error) {
    showToast(error.message || '候选知识库上线失败。', true);
  }
}


async function rollbackKnowledgeBuild() {
  const button = document.getElementById('rollbackKnowledgeBuildBtn');
  button.disabled = true;
  try {
    const payload = await requestJson('/api/admin/knowledge/index-builds/rollback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_build_id: null }),
    });
    showToast(`已回滚到 Build #${payload.data.id}。`);
    await loadKnowledgeBuilds();
  } catch (error) {
    showToast(error.message || '知识库回滚失败。', true);
  } finally {
    button.disabled = false;
  }
}


function renderKnowledgeDocuments(container, documents) {
  if (!documents.length) {
    showEmptyState(container, '暂无知识文档', '上传商家资料后可进行解析和人工审核。');
    return;
  }
  const card = element('div', 'data-card');
  const wrapper = element('div', 'table-wrap');
  const table = element('table', 'data-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['文档', '知识类型', '当前版本', '解析状态', '审核状态', '质量', '更新时间', '操作'].forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);
  const body = document.createElement('tbody');
  documents.forEach((documentItem) => {
    const revision = documentItem.latest_revision;
    const row = document.createElement('tr');
    const actions = element('div', 'knowledge-actions-cell');
    actions.appendChild(actionButton('查看与审核', 'primary', () => openKnowledgeDetail(documentItem.id)));
    const cells = [
      itemCell(documentItem.title, documentItem.category),
      textCell(knowledgeTypeLabel(documentItem.knowledge_type)),
      itemCell(`v${revision.version_no}`, revision.original_filename),
      knowledgeStatusCell(revision.parse_status, 'parse'),
      knowledgeStatusCell(revision.review_status, 'review'),
      textCell(knowledgeQualityLabel(revision.quality_status)),
      textCell(formatDate(documentItem.updated_at)),
      actions,
    ];
    cells.forEach((cell) => {
      const td = document.createElement('td');
      td.appendChild(cell);
      row.appendChild(td);
    });
    body.appendChild(row);
  });
  table.append(head, body);
  wrapper.appendChild(table);
  card.appendChild(wrapper);
  container.replaceChildren(card);
}


function renderKnowledgePagination(payload) {
  const container = document.getElementById('adminKnowledgePagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const summary = document.createElement('span');
  summary.textContent = `共 ${payload.total} 份 · 第 ${payload.page}/${totalPages} 页`;
  const previous = actionButton('上一页', 'secondary', () => changeKnowledgePage(payload.page - 1));
  const next = actionButton('下一页', 'secondary', () => changeKnowledgePage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(summary, previous, next);
}


function changeKnowledgePage(page) {
  state.knowledgePage = page;
  loadKnowledgeDocuments();
}


function openKnowledgeUpload() {
  document.getElementById('knowledgeUploadForm').reset();
  document.getElementById('knowledgeUploadCategory').value = '通用';
  document.getElementById('knowledgeUploadType').value = 'after_sales_policy';
  document.getElementById('knowledgeUploadError').textContent = '';
  document.getElementById('knowledgeUploadDialog').showModal();
}


async function uploadKnowledgeDocument(event) {
  event.preventDefault();
  const file = document.getElementById('knowledgeUploadFile').files[0];
  const errorElement = document.getElementById('knowledgeUploadError');
  if (!file) {
    errorElement.textContent = '请选择需要上传的商家资料。';
    return;
  }
  const form = new FormData();
  form.append('title', document.getElementById('knowledgeUploadTitle').value.trim());
  form.append('knowledge_type', document.getElementById('knowledgeUploadType').value);
  form.append('category', document.getElementById('knowledgeUploadCategory').value.trim() || '通用');
  form.append('file', file, file.name);
  const button = document.getElementById('submitKnowledgeUploadBtn');
  button.disabled = true;
  errorElement.textContent = '';
  try {
    const payload = await requestJson('/api/admin/knowledge/documents', {
      method: 'POST',
      body: form,
    });
    document.getElementById('knowledgeUploadDialog').close();
    showToast(`知识文档“${payload.data.title}”已上传，等待解析。`);
    await loadKnowledgeDocuments();
    await openKnowledgeDetail(payload.data.id);
  } catch (error) {
    errorElement.textContent = error.message || '知识文档上传失败。';
  } finally {
    button.disabled = false;
  }
}


async function openKnowledgeDetail(documentId) {
  state.selectedKnowledgeDocumentId = documentId;
  const dialog = document.getElementById('knowledgeDetailDialog');
  showLoadingState(document.getElementById('knowledgeDetailSummary'), '正在读取知识文档…');
  document.getElementById('knowledgeQualityPanel').replaceChildren();
  document.getElementById('knowledgeContentEditor').value = '';
  document.getElementById('knowledgeContentEditor').disabled = true;
  document.getElementById('knowledgeDetailError').textContent = '';
  document.getElementById('knowledgeRejectReason').value = '';
  if (!dialog.open) dialog.showModal();
  try {
    const payload = await requestJson(`/api/admin/knowledge/documents/${documentId}`);
    await renderKnowledgeDetail(payload.data);
  } catch (error) {
    showErrorState(document.getElementById('knowledgeDetailSummary'), error.message);
  }
}


async function renderKnowledgeDetail(documentItem) {
  const revision = documentItem.latest_revision;
  state.selectedKnowledgeDocumentId = documentItem.id;
  state.selectedKnowledgeRevisionId = revision.id;
  document.getElementById('knowledgeDetailTitle').textContent = documentItem.title;
  const summary = element('div', 'knowledge-summary-grid');
  [
    ['知识类型', knowledgeTypeLabel(documentItem.knowledge_type)],
    ['分类', documentItem.category],
    ['当前版本', `v${revision.version_no} · ${revision.original_filename}`],
    ['创建时间', formatDate(documentItem.created_at)],
    ['解析状态', knowledgeParseLabel(revision.parse_status)],
    ['审核状态', knowledgeReviewLabel(revision.review_status)],
    ['内容哈希', revision.processed_sha256 ? revision.processed_sha256.slice(0, 16) : '尚未生成'],
    ['审核记录', revision.reviewed_at ? `${revision.reviewed_by || '管理员'} · ${formatDate(revision.reviewed_at)}` : '尚未审核'],
  ].forEach(([label, value]) => {
    const item = element('div', 'knowledge-summary-item');
    const labelNode = document.createElement('span');
    labelNode.textContent = label;
    const valueNode = document.createElement('strong');
    valueNode.textContent = value;
    item.append(labelNode, valueNode);
    summary.appendChild(item);
  });
  document.getElementById('knowledgeDetailSummary').replaceChildren(summary);
  renderKnowledgeQuality(revision);

  const canReview = revision.parse_status === 'succeeded';
  document.getElementById('parseKnowledgeBtn').disabled = revision.parse_status === 'running';
  document.getElementById('parseKnowledgeBtn').textContent = revision.parse_status === 'failed' ? '重新解析' : '开始解析';
  document.getElementById('saveKnowledgeContentBtn').disabled = !canReview;
  document.getElementById('approveKnowledgeBtn').disabled = !canReview;
  document.getElementById('rejectKnowledgeBtn').disabled = !canReview;
  document.getElementById('knowledgeContentEditor').disabled = !canReview;

  if (canReview) {
    try {
      const payload = await requestJson(`/api/admin/knowledge/revisions/${revision.id}/content`);
      document.getElementById('knowledgeContentEditor').value = payload.data.content;
    } catch (error) {
      document.getElementById('knowledgeDetailError').textContent = error.message;
    }
  } else if (revision.parse_error_message) {
    document.getElementById('knowledgeDetailError').textContent = revision.parse_error_message;
  }
}


function renderKnowledgeQuality(revision) {
  const panel = document.getElementById('knowledgeQualityPanel');
  panel.replaceChildren();
  if (!revision.quality_report) {
    panel.textContent = revision.parse_status === 'failed'
      ? `解析失败：${revision.parse_error_message || '请检查文件后重试。'}`
      : '解析完成后将在这里展示字符数、标题数、表格数和质量警告。';
    return;
  }
  const metrics = revision.quality_report.metrics || {};
  const summary = document.createElement('div');
  summary.innerHTML = `<strong>质量检测：</strong>${knowledgeQualityLabel(revision.quality_status)} · ${metrics.character_count || 0} 字符 · ${metrics.heading_count || 0} 个标题 · ${metrics.table_row_count || 0} 行表格`;
  panel.appendChild(summary);
  const warnings = revision.quality_report.warnings || [];
  if (warnings.length) {
    const list = element('ul', 'knowledge-warning-list');
    warnings.forEach((warning) => {
      const item = document.createElement('li');
      item.textContent = knowledgeWarningLabel(warning);
      list.appendChild(item);
    });
    panel.appendChild(list);
  }
  if (revision.review_reason) {
    const reason = document.createElement('p');
    reason.textContent = `审核意见：${revision.review_reason}`;
    panel.appendChild(reason);
  }
}


async function parseSelectedKnowledgeRevision() {
  if (!state.selectedKnowledgeRevisionId) return;
  await runKnowledgeAction(
    'parseKnowledgeBtn',
    `/api/admin/knowledge/revisions/${state.selectedKnowledgeRevisionId}/parse`,
    { method: 'POST' },
    '文档解析完成。',
  );
}


async function saveSelectedKnowledgeContent() {
  if (!state.selectedKnowledgeRevisionId) return;
  const content = document.getElementById('knowledgeContentEditor').value;
  if (!content.trim()) {
    document.getElementById('knowledgeDetailError').textContent = '解析内容不能为空。';
    return;
  }
  await runKnowledgeAction(
    'saveKnowledgeContentBtn',
    `/api/admin/knowledge/revisions/${state.selectedKnowledgeRevisionId}/content`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    },
    '解析内容已保存，审核状态已重置为待审核。',
  );
}


async function approveSelectedKnowledgeRevision() {
  if (!state.selectedKnowledgeRevisionId) return;
  await runKnowledgeAction(
    'approveKnowledgeBtn',
    `/api/admin/knowledge/revisions/${state.selectedKnowledgeRevisionId}/approve`,
    { method: 'POST' },
    '知识版本已审核通过；本阶段不会自动修改线上 Chroma。',
  );
}


async function rejectSelectedKnowledgeRevision() {
  if (!state.selectedKnowledgeRevisionId) return;
  const reason = document.getElementById('knowledgeRejectReason').value.trim();
  if (!reason) {
    document.getElementById('knowledgeDetailError').textContent = '拒绝时必须填写审核原因。';
    document.getElementById('knowledgeRejectReason').focus();
    return;
  }
  await runKnowledgeAction(
    'rejectKnowledgeBtn',
    `/api/admin/knowledge/revisions/${state.selectedKnowledgeRevisionId}/reject`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    },
    '知识版本已拒绝。',
  );
}


async function runKnowledgeAction(buttonId, url, options, successMessage) {
  const button = document.getElementById(buttonId);
  const errorElement = document.getElementById('knowledgeDetailError');
  button.disabled = true;
  errorElement.textContent = '';
  try {
    await requestJson(url, options);
    showToast(successMessage);
    await loadKnowledgeDocuments();
    await openKnowledgeDetail(state.selectedKnowledgeDocumentId);
  } catch (error) {
    errorElement.textContent = error.message || '知识文档操作失败。';
    showToast(errorElement.textContent, true);
  } finally {
    button.disabled = false;
  }
}


async function uploadKnowledgeRevision(event) {
  event.preventDefault();
  if (!state.selectedKnowledgeDocumentId) return;
  const fileInput = document.getElementById('knowledgeRevisionFile');
  const file = fileInput.files[0];
  if (!file) {
    document.getElementById('knowledgeDetailError').textContent = '请选择新版本文件。';
    return;
  }
  const form = new FormData();
  form.append('file', file, file.name);
  const button = document.getElementById('submitKnowledgeRevisionBtn');
  button.disabled = true;
  try {
    await requestJson(`/api/admin/knowledge/documents/${state.selectedKnowledgeDocumentId}/revisions`, {
      method: 'POST',
      body: form,
    });
    fileInput.value = '';
    showToast('新知识版本已上传，等待解析。');
    await loadKnowledgeDocuments();
    await openKnowledgeDetail(state.selectedKnowledgeDocumentId);
  } catch (error) {
    document.getElementById('knowledgeDetailError').textContent = error.message || '新版本上传失败。';
  } finally {
    button.disabled = false;
  }
}


async function loadDashboard() {
  const metricIds = {
    orders_total: 'dashboardOrdersTotal',
    pending_refunds: 'dashboardPendingRefunds',
    failed_refunds: 'dashboardFailedRefunds',
    pending_tickets: 'dashboardPendingTickets',
    unresolved_cases: 'dashboardUnresolvedCases',
    today_sessions: 'dashboardTodaySessions',
  };
  Object.values(metricIds).forEach((id) => {
    document.getElementById(id).textContent = '…';
  });
  try {
    const payload = await requestJson('/api/admin/dashboard');
    Object.entries(metricIds).forEach(([field, id]) => {
      document.getElementById(id).textContent = String(payload.data[field]);
    });
  } catch (error) {
    Object.values(metricIds).forEach((id) => {
      document.getElementById(id).textContent = '—';
    });
    showToast(error.message || '总览数据加载失败。');
  }
}


async function loadOrders() {
  const container = document.getElementById('adminOrdersContent');
  showLoadingState(container, '正在读取订单…');
  const params = new URLSearchParams({
    page: state.ordersPage,
    page_size: PAGE_SIZE,
  });
  const status = document.getElementById('adminOrderStatusFilter').value;
  if (status) params.set('status', status);
  try {
    const payload = await requestJson(`/api/admin/orders?${params}`);
    renderOrders(container, payload.data);
    renderOrderPagination(payload);
  } catch (error) {
    showErrorState(container, error.message);
    document.getElementById('adminOrdersPagination').replaceChildren();
  }
}


async function selectStatus(status) {
  if (!STATUSES.includes(status)) return;
  state.status = status;
  state.page = 1;
  applyRefundStatusUI();
  await loadRefunds();
}


function applyRefundStatusUI() {
  document.querySelectorAll('.metric-tab').forEach((tab) => {
    tab.classList.toggle('active', tab.dataset.status === state.status);
  });
  document.getElementById('currentStatusTitle').textContent = STATUS_META[state.status].title;
  document.getElementById('currentStatusDescription').textContent = STATUS_META[state.status].description;
}


async function loadStatusCounts() {
  await Promise.all(STATUSES.map(async (status) => {
    try {
      const payload = await requestJson(`/api/admin/refunds?status=${status}&page=1&page_size=1`);
      document.getElementById(`count-${status}`).textContent = String(payload.total);
    } catch (error) {
      document.getElementById(`count-${status}`).textContent = '—';
      throw error;
    }
  }));
}


async function loadRefunds() {
  const container = document.getElementById('adminRefundsContent');
  showLoadingState(container, `正在读取${STATUS_META[state.status].label}退款…`);
  try {
    const params = new URLSearchParams({
      status: state.status,
      page: state.page,
      page_size: PAGE_SIZE,
    });
    const payload = await requestJson(`/api/admin/refunds?${params}`);
    renderRefunds(container, payload.data);
    renderPagination(payload);
  } catch (error) {
    showErrorState(container, error.message);
    document.getElementById('adminRefundsPagination').replaceChildren();
  }
}


async function loadTickets() {
  const container = document.getElementById('adminTicketsContent');
  showLoadingState(container, '正在读取工单…');
  const status = document.getElementById('adminTicketStatusFilter').value;
  const type = document.getElementById('adminTicketTypeFilter').value;
  try {
    const params = new URLSearchParams({
      page: state.ticketsPage,
      page_size: PAGE_SIZE,
    });
    if (status) params.set('status', status);
    if (type) params.set('type', type);
    const payload = await requestJson(`/api/admin/tickets?${params}`);
    renderTickets(container, payload.data);
    renderTicketPagination(payload);
  } catch (error) {
    showErrorState(container, error.message);
    document.getElementById('adminTicketsPagination').replaceChildren();
  }
}


async function loadTraces() {
  const timeline = document.getElementById('traceTimeline');
  showLoadingState(timeline, '正在读取执行轨迹…');
  const params = new URLSearchParams({
    page: state.tracesPage,
    page_size: PAGE_SIZE,
  });
  if (state.selectedSessionId) params.set('session_id', state.selectedSessionId);
  const intent = document.getElementById('traceIntentFilter').value;
  const status = document.getElementById('traceStatusFilter').value;
  if (intent) params.set('intent', intent);
  if (status) params.set('status', status);

  try {
    const payload = await requestJson(`/api/admin/traces?${params}`);
    renderTraceSessions(payload.data);
    renderTraceTimeline(payload.data);
    renderTracePagination(payload);
    if (payload.data.length) {
      const selected = payload.data.find((trace) => trace.id === state.selectedTraceId) || payload.data[0];
      state.selectedTraceId = selected.id;
      await loadTraceDetail(selected.id);
    } else {
      state.selectedTraceId = null;
      showEmptyState(document.getElementById('traceDetail'), '暂无详情', '请调整查询条件。');
    }
  } catch (error) {
    showErrorState(timeline, error.message);
    showErrorState(document.getElementById('traceDetail'), error.message);
  }
}


async function loadCaseStats() {
  try {
    const payload = await requestJson('/api/admin/unresolved-cases/stats');
    document.getElementById('caseCountPending').textContent = String(payload.data.pending);
    document.getElementById('caseCountResolved').textContent = String(payload.data.resolved);
    document.getElementById('caseCountKnowledge').textContent = String(payload.data.knowledge_candidates);
  } catch (error) {
    ['caseCountPending', 'caseCountResolved', 'caseCountKnowledge'].forEach((id) => {
      document.getElementById(id).textContent = '—';
    });
    throw error;
  }
}


async function loadCases() {
  const container = document.getElementById('adminCasesContent');
  showLoadingState(container, '正在读取未解决案例…');
  const params = new URLSearchParams({
    page: state.casesPage,
    page_size: PAGE_SIZE,
  });
  const resolved = document.getElementById('caseResolvedFilter').value;
  const intent = document.getElementById('caseIntentFilter').value;
  const knowledge = document.getElementById('caseKnowledgeFilter').value;
  if (resolved) params.set('is_resolved', resolved);
  if (intent) params.set('predicted_intent', intent);
  if (knowledge) params.set('should_add_to_kb', knowledge);

  try {
    const payload = await requestJson(`/api/admin/unresolved-cases?${params}`);
    renderCases(container, payload.data);
    renderCasePagination(payload);
  } catch (error) {
    showErrorState(container, error.message);
    document.getElementById('adminCasesPagination').replaceChildren();
  }
}


function renderCases(container, cases) {
  if (!cases.length) {
    showEmptyState(container, '暂无案例', '当前筛选条件下没有未解决案例。');
    return;
  }
  const card = element('div', 'data-card');
  const wrapper = element('div', 'table-wrap');
  const table = element('table', 'data-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['用户原问题', '预测意图', '置信度', '系统回答', '处理状态', '知识库候选', '创建时间', '操作'].forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);
  const body = document.createElement('tbody');
  cases.forEach((caseItem) => {
    const row = document.createElement('tr');
    const cells = [
      itemCell(caseItem.user_message, `案例 #${caseItem.id}`),
      textCell(intentLabel(caseItem.predicted_intent)),
      textCell(formatConfidence(caseItem.confidence)),
      textCell(caseItem.final_answer || '—', 'answer-preview'),
      caseStatusCell(caseItem.is_resolved),
      textCell(caseItem.should_add_to_kb ? '是' : '否'),
      textCell(formatDate(caseItem.created_at)),
      actionButton(caseItem.is_resolved ? '查看标注' : '人工标注', caseItem.is_resolved ? 'secondary' : 'primary', () => openCaseDetail(caseItem.id)),
    ];
    cells.forEach((cell) => {
      const td = document.createElement('td');
      td.appendChild(cell);
      row.appendChild(td);
    });
    body.appendChild(row);
  });
  table.append(head, body);
  wrapper.appendChild(table);
  card.appendChild(wrapper);
  container.replaceChildren(card);
}


async function openCaseDetail(caseId) {
  state.selectedCaseId = caseId;
  const dialog = document.getElementById('caseDetailDialog');
  const readonly = document.getElementById('caseReadonlyDetail');
  showLoadingState(readonly, '正在读取案例详情…');
  document.getElementById('caseFormError').textContent = '';
  dialog.showModal();
  try {
    const payload = await requestJson(`/api/admin/unresolved-cases/${caseId}`);
    renderCaseAnnotation(payload.data);
  } catch (error) {
    showErrorState(readonly, error.message);
  }
}


function renderCaseAnnotation(caseItem) {
  const readonly = element('div', 'case-readonly');
  readonly.append(
    caseReadonlyItem('用户原问题', caseItem.user_message),
    caseReadonlyItem('系统预测', `${intentLabel(caseItem.predicted_intent)} · ${formatConfidence(caseItem.confidence)}`),
    caseReadonlyItem('系统最终回答', caseItem.final_answer || '—'),
    caseReadonlyItem('审核记录', caseItem.reviewer_username ? `${caseItem.reviewer_username} · ${formatDate(caseItem.reviewed_at)}` : '尚未人工标注'),
  );
  document.getElementById('caseReadonlyDetail').replaceChildren(readonly);
  document.getElementById('caseHumanIntent').value = caseItem.human_label_intent || '';
  document.getElementById('caseHumanAnswer').value = caseItem.human_label_answer || '';
  document.getElementById('caseShouldAddToKb').checked = Boolean(caseItem.should_add_to_kb);
  document.getElementById('caseIsResolved').checked = Boolean(caseItem.is_resolved);
}


function caseReadonlyItem(label, value) {
  const item = element('div', 'case-readonly-item');
  const heading = document.createElement('span');
  heading.textContent = label;
  const content = document.createElement('p');
  content.textContent = value;
  item.append(heading, content);
  return item;
}


async function saveCaseAnnotation(event) {
  event.preventDefault();
  if (!state.selectedCaseId) return;
  const intent = document.getElementById('caseHumanIntent').value || null;
  const answer = document.getElementById('caseHumanAnswer').value.trim() || null;
  const shouldAdd = document.getElementById('caseShouldAddToKb').checked;
  const isResolved = document.getElementById('caseIsResolved').checked;
  const errorElement = document.getElementById('caseFormError');
  if ((isResolved || shouldAdd) && !answer) {
    errorElement.textContent = isResolved
      ? '标记已处理时必须填写人工答案。'
      : '标记知识库候选时必须填写人工答案。';
    document.getElementById('caseHumanAnswer').focus();
    return;
  }

  const button = document.getElementById('saveCaseAnnotationBtn');
  button.disabled = true;
  errorElement.textContent = '';
  try {
    await requestJson(`/api/admin/unresolved-cases/${state.selectedCaseId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        is_resolved: isResolved,
        human_label_intent: intent,
        human_label_answer: answer,
        should_add_to_kb: shouldAdd,
      }),
    });
    document.getElementById('caseDetailDialog').close();
    showToast(`案例 #${state.selectedCaseId} 标注已保存。`);
    await Promise.all([loadCaseStats(), loadCases()]);
  } catch (error) {
    errorElement.textContent = error.message || '保存标注失败。';
  } finally {
    button.disabled = false;
  }
}


function renderCasePagination(payload) {
  const container = document.getElementById('adminCasesPagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const summary = document.createElement('span');
  summary.textContent = `共 ${payload.total} 条 · 第 ${payload.page}/${totalPages} 页`;
  const previous = actionButton('上一页', 'secondary', () => changeCasePage(payload.page - 1));
  const next = actionButton('下一页', 'secondary', () => changeCasePage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(summary, previous, next);
}


function changeCasePage(page) {
  state.casesPage = page;
  loadCases();
}


function renderTraceSessions(traces) {
  const container = document.getElementById('traceSessions');
  const sessions = new Map();
  traces.forEach((trace) => {
    if (!sessions.has(trace.session_id)) sessions.set(trace.session_id, []);
    sessions.get(trace.session_id).push(trace);
  });
  document.getElementById('traceSessionCount').textContent = String(sessions.size);
  const list = element('div', 'trace-list');
  sessions.forEach((items, sessionId) => {
    const button = element('button', `trace-list-button${state.selectedSessionId === sessionId ? ' active' : ''}`);
    button.type = 'button';
    const title = document.createElement('strong');
    title.textContent = sessionId;
    const meta = document.createElement('span');
    meta.textContent = `${items.length} 条请求 · ${formatDate(items[items.length - 1].created_at)}`;
    button.append(title, meta);
    button.addEventListener('click', () => selectTraceSession(sessionId));
    list.appendChild(button);
  });
  container.replaceChildren(list);
}


async function selectTraceSession(sessionId) {
  state.selectedSessionId = sessionId;
  state.tracesPage = 1;
  document.getElementById('traceSessionSearch').value = sessionId;
  await loadTraceSession(sessionId);
}


async function loadTraceSession(sessionId) {
  const timeline = document.getElementById('traceTimeline');
  showLoadingState(timeline, '正在读取会话时间线…');
  try {
    const payload = await requestJson(`/api/admin/trace-sessions/${encodeURIComponent(sessionId)}`);
    renderTraceTimeline(payload.data);
    renderTraceSessions(payload.data);
    document.getElementById('tracesPagination').replaceChildren();
    if (payload.data.length) {
      state.selectedTraceId = payload.data[0].id;
      await loadTraceDetail(state.selectedTraceId);
    }
  } catch (error) {
    showErrorState(timeline, error.message);
  }
}


function renderTraceTimeline(traces) {
  const container = document.getElementById('traceTimeline');
  if (!traces.length) {
    showEmptyState(container, '暂无轨迹', '当前条件下没有请求记录。');
    document.getElementById('selectedSessionLabel').textContent = '无结果';
    return;
  }
  const sessionIds = [...new Set(traces.map((trace) => trace.session_id))];
  document.getElementById('selectedSessionLabel').textContent = sessionIds.length === 1 ? sessionIds[0] : `${sessionIds.length} 个会话`;
  const list = element('div', 'trace-list');
  traces.forEach((trace) => {
    const wrapper = element('div', `trace-request ${trace.status || ''}`);
    const button = element('button', `trace-list-button${trace.id === state.selectedTraceId ? ' active' : ''}`);
    button.type = 'button';
    const title = document.createElement('strong');
    title.textContent = trace.message || `请求 #${trace.id}`;
    const meta = document.createElement('span');
    meta.textContent = `${intentLabel(trace.intent)} · ${workflowLabel(trace.workflow_name)} · ${traceStatusLabel(trace.status)}`;
    button.append(title, meta);
    button.addEventListener('click', () => loadTraceDetail(trace.id));
    wrapper.appendChild(button);
    list.appendChild(wrapper);
  });
  container.replaceChildren(list);
}


async function loadTraceDetail(traceId) {
  state.selectedTraceId = traceId;
  const container = document.getElementById('traceDetail');
  showLoadingState(container, '正在读取节点详情…');
  try {
    const payload = await requestJson(`/api/admin/traces/${traceId}`);
    renderTraceDetail(container, payload.data);
    document.getElementById('selectedTraceLabel').textContent = `Trace #${traceId}`;
    document.querySelectorAll('.timeline-pane .trace-list-button').forEach((button) => button.classList.remove('active'));
  } catch (error) {
    showErrorState(container, error.message);
  }
}


function renderTraceDetail(container, trace) {
  const root = document.createElement('div');
  root.append(
    traceDetailSection('请求摘要', traceSummary(trace)),
    traceDetailSection('缺失槽位', trace.missing_slots.length ? trace.missing_slots.join('、') : '无'),
    traceStepsSection(trace.steps),
    traceSourcesSection(trace.rag_sources),
    traceDetailSection('最终回答', trace.final_answer || '—'),
    traceErrorSection(trace.error),
  );
  container.replaceChildren(root);
}


function traceSummary(trace) {
  return [
    `用户消息：${trace.message || '—'}`,
    `识别意图：${intentLabel(trace.intent)}（${formatConfidence(trace.confidence)}）`,
    `实际工作流：${workflowLabel(trace.workflow_name)}`,
    `执行状态：${traceStatusLabel(trace.status)}`,
  ].join('\n');
}


function traceDetailSection(title, content) {
  const section = element('section', 'trace-detail-section');
  const heading = document.createElement('h3');
  heading.textContent = title;
  const paragraph = document.createElement('p');
  paragraph.textContent = content;
  section.append(heading, paragraph);
  return section;
}


function traceStepsSection(steps) {
  const section = element('section', 'trace-detail-section');
  const heading = document.createElement('h3');
  heading.textContent = '实际节点步骤';
  const list = element('div', 'trace-step-list');
  if (!steps.length) {
    list.textContent = '旧数据没有节点级步骤。';
  } else {
    steps.forEach((step) => {
      const card = element('div', `trace-step ${step.status}`);
      const title = document.createElement('strong');
      title.textContent = `${step.sequence}. ${step.node_name} · ${traceStatusLabel(step.status)}`;
      const meta = document.createElement('small');
      const parts = [`${step.duration_ms ?? 0} ms`];
      if (step.tool_name) parts.push(`工具：${step.tool_name}`);
      if (step.missing_slots.length) parts.push(`缺失：${step.missing_slots.join('、')}`);
      if (step.error) parts.push(`错误阶段：${step.error.stage || 'unknown'}`);
      meta.textContent = parts.join(' · ');
      card.append(title, meta);
      list.appendChild(card);
    });
  }
  section.append(heading, list);
  return section;
}


function traceSourcesSection(sources) {
  const section = element('section', 'trace-detail-section');
  const heading = document.createElement('h3');
  heading.textContent = 'RAG 来源';
  const list = element('div', 'trace-step-list');
  if (!sources.length) {
    list.textContent = '本次请求未使用 RAG 来源。';
  } else {
    sources.forEach((source) => {
      const card = element('div', 'source-card');
      card.textContent = source.title || source.relative_source || source.id || '未知来源';
      list.appendChild(card);
    });
  }
  section.append(heading, list);
  return section;
}


function traceErrorSection(error) {
  if (!error) return traceDetailSection('错误阶段', '无错误');
  return traceDetailSection(
    '错误阶段',
    `阶段：${error.stage || 'unknown'}\n代码：${error.code || '—'}\n类型：${error.type || '—'}\n信息：${error.message || '—'}`,
  );
}


function renderTracePagination(payload) {
  const container = document.getElementById('tracesPagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const previous = actionButton('上一页', 'secondary', () => changeTracePage(payload.page - 1));
  const summary = document.createElement('span');
  summary.textContent = `${payload.page}/${totalPages}`;
  const next = actionButton('下一页', 'secondary', () => changeTracePage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(previous, summary, next);
}


function changeTracePage(page) {
  state.tracesPage = page;
  loadTraces();
}


function renderOrders(container, orders) {
  if (!orders.length) {
    showEmptyState(container, '暂无订单', '当前筛选条件下没有订单记录。');
    return;
  }

  const card = element('div', 'data-card');
  const wrapper = element('div', 'table-wrap');
  const table = element('table', 'data-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['订单', '客户', '商品', '金额', '状态', '关联退款', '工单', '操作'].forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);

  const body = document.createElement('tbody');
  orders.forEach((order) => {
    const row = document.createElement('tr');
    const refundCell = order.refund_id
      ? actionButton(
        `#${order.refund_id} · ${refundStatusLabel(order.refund_status)}`,
        'secondary',
        () => openRefundDetailById(order.refund_id, order.refund_status),
      )
      : textCell('—');
    const cells = [
      itemCell(`#${order.id}`, formatDate(order.created_at)),
      itemCell(order.username, `用户ID ${order.user_id}`),
      itemCell(order.product_name, `数量 ${order.quantity}`),
      textCell(formatMoney(order.total_price), 'money'),
      orderStatusCell(order.status),
      refundCell,
      textCell(`${order.ticket_count} 个`),
      actionButton('查看详情', 'secondary', () => openOrderDetail(order.id)),
    ];
    cells.forEach((cell) => {
      const td = document.createElement('td');
      td.appendChild(cell);
      row.appendChild(td);
    });
    body.appendChild(row);
  });
  table.append(head, body);
  wrapper.appendChild(table);
  card.appendChild(wrapper);
  container.replaceChildren(card);
}


function renderTickets(container, tickets) {
  if (!tickets.length) {
    showEmptyState(container, '暂无工单', '当前筛选条件下没有工单记录。');
    return;
  }

  const card = element('div', 'data-card');
  const wrapper = element('div', 'table-wrap');
  const table = element('table', 'data-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['工单', '用户', '类型', '关联订单', '关联退款', '审核状态', '审核结果', '操作'].forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);

  const body = document.createElement('tbody');
  tickets.forEach((ticket) => {
    const row = document.createElement('tr');
    const cells = [
      itemCell(`#${ticket.id}`, formatDate(ticket.created_at)),
      itemCell(ticket.username, `用户ID ${ticket.user_id}`),
      textCell(ticketTypeLabel(ticket.type)),
      ticketOrderCell(ticket),
      ticketRefundCell(ticket),
      ticketStatusCell(ticket.status),
      itemCell(ticket.reviewer_username || '尚未审核', ticket.review_reason || '—'),
      actionButton('查看详情', 'secondary', () => openTicketDetail(ticket.id)),
    ];
    cells.forEach((cell) => {
      const td = document.createElement('td');
      td.appendChild(cell);
      row.appendChild(td);
    });
    body.appendChild(row);
  });
  table.append(head, body);
  wrapper.appendChild(table);
  card.appendChild(wrapper);
  container.replaceChildren(card);
}


function ticketOrderCell(ticket) {
  const wrapper = document.createElement('div');
  wrapper.append(
    itemCell(ticket.product_name, `订单 ${ticket.order_id}`),
    actionButton('查看订单', 'secondary', () => openOrderDetail(ticket.order_id)),
  );
  return wrapper;
}


function ticketRefundCell(ticket) {
  if (!ticket.refund_id) return textCell('—');
  const wrapper = document.createElement('div');
  wrapper.append(
    itemCell(`退款单 #${ticket.refund_id}`, refundStatusLabel(ticket.refund_status)),
    actionButton(
      '查看退款',
      'secondary',
      () => openRefundDetailById(ticket.refund_id, ticket.refund_status),
    ),
  );
  return wrapper;
}


async function openTicketDetail(ticketId) {
  const dialog = document.getElementById('ticketDetailDialog');
  const detail = document.getElementById('adminTicketDetail');
  showLoadingState(detail, '正在读取工单详情…');
  dialog.showModal();
  try {
    const payload = await requestJson(`/api/admin/tickets/${ticketId}`);
    renderTicketDetail(detail, payload.data);
  } catch (error) {
    showErrorState(detail, error.message);
  }
}


function renderTicketDetail(container, ticket) {
  const grid = element('div', 'detail-grid');
  grid.append(
    detailRow('工单号', String(ticket.id)),
    detailRow('用户', `${ticket.username}（${ticket.user_id}）`),
    detailRow('工单类型', ticketTypeLabel(ticket.type)),
    detailRow('工单状态', ticketStatusLabel(ticket.status)),
    detailRow('关联订单', String(ticket.order_id)),
    detailRow('商品', ticket.product_name),
    detailRow('关联退款', ticket.refund_id ? `退款单 #${ticket.refund_id} · ${refundStatusLabel(ticket.refund_status)}` : '—', true),
    detailRow('申请原因', ticket.reason, true),
    detailRow('审核管理员', ticket.reviewer_username || '—'),
    detailRow('审核时间', formatDate(ticket.reviewed_at)),
    detailRow('审核结果', ticket.review_reason || '尚未审核', true),
  );
  const actions = element('div', 'detail-actions');
  actions.appendChild(actionButton('关闭', 'secondary', () => document.getElementById('ticketDetailDialog').close()));
  actions.appendChild(actionButton('查看关联订单', 'secondary', () => openOrderDetail(ticket.order_id)));
  if (ticket.refund_id) {
    actions.appendChild(actionButton('查看关联退款', 'primary', () => {
      document.getElementById('ticketDetailDialog').close();
      openRefundDetailById(ticket.refund_id, ticket.refund_status);
    }));
  }
  grid.appendChild(actions);
  container.replaceChildren(grid);
}


async function openOrderDetail(orderId) {
  const dialog = document.getElementById('adminOrderDialog');
  const detail = document.getElementById('adminOrderDetail');
  showLoadingState(detail, '正在读取订单详情…');
  dialog.showModal();
  try {
    const payload = await requestJson(`/api/admin/orders/${orderId}`);
    const order = payload.data;
    const body = element('div', 'detail-body');
    body.append(
      detailRow('订单号', String(order.id)),
      detailRow('用户', `${order.user.username}（${order.user.id}）`),
      detailRow('商品', order.product.name),
      detailRow('商品分类', order.product.category),
      detailRow('购买数量', String(order.quantity)),
      detailRow('订单金额', formatMoney(order.total_price)),
      detailRow('订单状态', orderStatusLabel(order.status)),
      detailRow(
        '关联退款',
        order.refund ? `退款单 #${order.refund.id} · ${refundStatusLabel(order.refund.status)}` : '—',
      ),
      detailRow('关联工单', order.tickets.length ? `${order.tickets.length} 个` : '—'),
      detailRow('下单时间', formatDate(order.created_at)),
    );
    const actions = element('div', 'detail-actions');
    actions.appendChild(actionButton('关闭', 'secondary', () => dialog.close()));
    order.tickets.forEach((ticket) => {
      actions.appendChild(actionButton(
        `查看${ticketTypeLabel(ticket.type)}工单 #${ticket.id}`,
        'secondary',
        () => {
          dialog.close();
          openTicketDetailById(ticket.id);
        },
      ));
    });
    if (order.refund) {
      actions.appendChild(actionButton('查看关联退款', 'primary', () => {
        dialog.close();
        openRefundDetailById(order.refund.id, order.refund.status);
      }));
    }
    body.appendChild(actions);
    detail.replaceChildren(body);
  } catch (error) {
    showErrorState(detail, error.message);
  }
}


async function openRefundDetailById(refundId, refundStatus) {
  if (!refundId) return;
  state.status = STATUSES.includes(refundStatus) ? refundStatus : 'reviewing';
  window.location.hash = 'refunds';
  await openRefundDetail(refundId);
}


async function openTicketDetailById(ticketId) {
  if (!ticketId) return;
  window.location.hash = 'tickets';
  await openTicketDetail(ticketId);
}


function renderRefunds(container, refunds) {
  if (!refunds.length) {
    showEmptyState(container, `暂无${STATUS_META[state.status].label}退款`, '当前状态下没有退款申请。');
    return;
  }

  const card = element('div', 'data-card');
  const wrapper = element('div', 'table-wrap');
  const table = element('table', 'data-table');
  const head = document.createElement('thead');
  const headRow = document.createElement('tr');
  ['退款单', '客户', '商品与订单', '金额', '风险', '网关', '状态', '操作'].forEach((label) => {
    const th = document.createElement('th');
    th.textContent = label;
    headRow.appendChild(th);
  });
  head.appendChild(headRow);

  const body = document.createElement('tbody');
  refunds.forEach((refund) => {
    const row = document.createElement('tr');
    const cells = [
      itemCell(`#${refund.id}`, formatDate(refund.created_at)),
      itemCell(refund.username || `用户 ${refund.user_id}`, `用户ID ${refund.user_id}`),
      itemCell(refund.product_name || '未知商品', `订单 ${refund.order_id}`),
      textCell(formatMoney(refund.amount), 'money'),
      riskCell(refund.risk_level),
      textCell(gatewayLabel(refund.gateway_mode)),
      statusCell(refund.status),
      refundActions(refund),
    ];
    cells.forEach((cell) => {
      const td = document.createElement('td');
      td.appendChild(cell);
      row.appendChild(td);
    });
    body.appendChild(row);
  });
  table.append(head, body);
  wrapper.appendChild(table);
  card.appendChild(wrapper);
  container.replaceChildren(card);
}


function refundActions(refund) {
  const actions = element('div', 'action-row');
  actions.appendChild(actionButton('查看详情', 'secondary', () => openRefundDetail(refund.id)));
  if (refund.status === 'reviewing') {
    actions.appendChild(actionButton('批准', 'primary', () => openApproveDialog(refund)));
    actions.appendChild(actionButton('拒绝', 'danger', () => openRejectDialog(refund)));
  }
  return actions;
}


async function openRefundDetail(refundId) {
  const dialog = document.getElementById('refundDetailDialog');
  const detail = document.getElementById('adminRefundDetail');
  showLoadingState(detail, '正在读取退款详情…');
  dialog.showModal();
  try {
    const payload = await requestJson(`/api/admin/refunds/${refundId}`);
    state.selectedRefund = payload.data;
    renderRefundDetail(detail, payload.data);
  } catch (error) {
    showErrorState(detail, error.message);
  }
}


function renderRefundDetail(container, refund) {
  const grid = element('div', 'detail-grid');
  grid.append(
    detailRow('退款单号', String(refund.id)),
    detailRow('用户', `${refund.username || '未知用户'}（${refund.user_id}）`),
    detailRow('订单', String(refund.order_id)),
    detailRow('商品', refund.product_name || '未知商品'),
    detailRow('退款金额', formatMoney(refund.amount)),
    detailRow('风险等级', riskLabel(refund.risk_level)),
    detailRow('工单号', refund.ticket_id ? String(refund.ticket_id) : '—'),
    detailRow('网关模式', gatewayLabel(refund.gateway_mode)),
    detailRow('平台流水号', refund.provider_refund_id || '—', true),
    detailRow('退款原因', refund.reason, true),
    detailRow('失败原因', refund.failure_reason || '—', true),
  );

  const actions = element('div', 'detail-actions');
  actions.appendChild(actionButton('关闭', 'secondary', () => document.getElementById('refundDetailDialog').close()));
  if (refund.status === 'reviewing') {
    actions.appendChild(actionButton('拒绝退款', 'danger', () => {
      document.getElementById('refundDetailDialog').close();
      openRejectDialog(refund);
    }));
    actions.appendChild(actionButton('批准退款', 'primary', () => {
      document.getElementById('refundDetailDialog').close();
      openApproveDialog(refund);
    }));
  }
  grid.appendChild(actions);
  container.replaceChildren(grid);
}


function openApproveDialog(refund) {
  state.selectedRefund = refund;
  document.getElementById('approveWarning').textContent = refund.gateway_mode === 'mock'
    ? '当前为Mock演示环境，本操作不会产生真实资金变动。'
    : '当前为Manual演示环境，批准后只会记录审核结果，仍需外部渠道完成真实退款。';
  document.getElementById('approveSummary').textContent = `退款单 #${refund.id} · 订单 ${refund.order_id} · ${formatMoney(refund.amount)}`;
  document.getElementById('approveDialog').showModal();
}


async function approveSelectedRefund() {
  if (!state.selectedRefund) return;
  const button = document.getElementById('confirmApproveBtn');
  button.disabled = true;
  try {
    const payload = await requestJson(
      `/api/admin/refunds/${state.selectedRefund.id}/approve`,
      { method: 'POST' },
    );
    document.getElementById('approveDialog').close();
    showToast(`退款单 #${payload.data.id} 已批准。`);
    await Promise.all([loadStatusCounts(), loadRefunds()]);
  } catch (error) {
    showToast(error.message || '批准退款失败。', true);
  } finally {
    button.disabled = false;
  }
}


function openRejectDialog(refund) {
  state.selectedRefund = refund;
  document.getElementById('rejectReason').value = '';
  document.getElementById('rejectError').textContent = '';
  document.getElementById('rejectDialog').showModal();
  document.getElementById('rejectReason').focus();
}


async function rejectSelectedRefund(event) {
  event.preventDefault();
  if (!state.selectedRefund) return;
  const reasonInput = document.getElementById('rejectReason');
  const errorElement = document.getElementById('rejectError');
  const reason = reasonInput.value.trim();
  if (!reason) {
    errorElement.textContent = '请填写拒绝原因。';
    reasonInput.focus();
    return;
  }

  const button = document.getElementById('confirmRejectBtn');
  button.disabled = true;
  errorElement.textContent = '';
  try {
    const payload = await requestJson(
      `/api/admin/refunds/${state.selectedRefund.id}/reject`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      },
    );
    document.getElementById('rejectDialog').close();
    showToast(`退款单 #${payload.data.id} 已拒绝。`);
    await Promise.all([loadStatusCounts(), loadRefunds()]);
  } catch (error) {
    errorElement.textContent = error.message || '拒绝退款失败。';
  } finally {
    button.disabled = false;
  }
}


function renderPagination(payload) {
  const container = document.getElementById('adminRefundsPagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const summary = document.createElement('span');
  summary.textContent = `共 ${payload.total} 条 · 第 ${payload.page}/${totalPages} 页`;
  const previous = actionButton('上一页', 'secondary', () => changePage(payload.page - 1));
  const next = actionButton('下一页', 'secondary', () => changePage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(summary, previous, next);
}


function renderTicketPagination(payload) {
  const container = document.getElementById('adminTicketsPagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const summary = document.createElement('span');
  summary.textContent = `共 ${payload.total} 条 · 第 ${payload.page}/${totalPages} 页`;
  const previous = actionButton('上一页', 'secondary', () => changeTicketPage(payload.page - 1));
  const next = actionButton('下一页', 'secondary', () => changeTicketPage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(summary, previous, next);
}


function renderOrderPagination(payload) {
  const container = document.getElementById('adminOrdersPagination');
  container.replaceChildren();
  const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
  if (payload.total === 0 || totalPages === 1) return;
  const summary = document.createElement('span');
  summary.textContent = `共 ${payload.total} 条 · 第 ${payload.page}/${totalPages} 页`;
  const previous = actionButton('上一页', 'secondary', () => changeOrderPage(payload.page - 1));
  const next = actionButton('下一页', 'secondary', () => changeOrderPage(payload.page + 1));
  previous.disabled = payload.page <= 1;
  next.disabled = payload.page >= totalPages;
  container.append(summary, previous, next);
}


function changePage(page) {
  state.page = page;
  loadRefunds();
}


function changeOrderPage(page) {
  state.ordersPage = page;
  loadOrders();
}


function changeTicketPage(page) {
  state.ticketsPage = page;
  loadTickets();
}


async function requestJson(url, options = {}) {
  return readJson(await apiFetch(url, options));
}


function itemCell(title, subtitle) {
  const wrapper = document.createElement('div');
  const titleElement = element('span', 'item-title');
  titleElement.textContent = title;
  const subtitleElement = element('span', 'item-subtitle');
  subtitleElement.textContent = subtitle;
  wrapper.append(titleElement, subtitleElement);
  return wrapper;
}


function textCell(value, className = '') {
  const span = element('span', className);
  span.textContent = value;
  return span;
}


function riskCell(risk) {
  const badge = element('span', `status ${risk === 'high' ? 'failed' : 'succeeded'}`);
  badge.textContent = riskLabel(risk);
  return badge;
}


function statusCell(status) {
  const badge = element('span', `status ${status}`);
  badge.textContent = STATUS_META[status]?.label || status;
  return badge;
}


function orderStatusCell(status) {
  const badge = element('span', `status ${status}`);
  badge.textContent = orderStatusLabel(status);
  return badge;
}


function ticketStatusCell(status) {
  const badge = element('span', `status ${status}`);
  badge.textContent = ticketStatusLabel(status);
  return badge;
}


function caseStatusCell(isResolved) {
  const status = isResolved ? 'succeeded' : 'pending';
  const badge = element('span', `status ${status}`);
  badge.textContent = isResolved ? '已处理' : '待处理';
  return badge;
}


function knowledgeStatusCell(status, kind) {
  const visualStatus = status === 'running'
    ? 'processing'
    : status === 'approved'
      ? 'succeeded'
      : status;
  const badge = element('span', `status ${visualStatus}`);
  badge.textContent = kind === 'parse'
    ? knowledgeParseLabel(status)
    : knowledgeReviewLabel(status);
  return badge;
}


function knowledgeBuildStatusCell(status) {
  const visualStatus = {
    building: 'processing',
    ready: 'approved',
    active: 'succeeded',
    superseded: 'shipped',
    failed: 'failed',
  }[status] || status;
  const badge = element('span', `status ${visualStatus}`);
  badge.textContent = knowledgeBuildStatusLabel(status);
  return badge;
}


function actionButton(label, style, handler) {
  const button = element('button', `button ${style} small`);
  button.type = 'button';
  button.textContent = label;
  button.addEventListener('click', handler);
  return button;
}


function detailRow(label, value, full = false) {
  const row = element('div', `detail-row${full ? ' full' : ''}`);
  const labelElement = document.createElement('span');
  labelElement.textContent = label;
  const valueElement = document.createElement('strong');
  valueElement.textContent = value;
  row.append(labelElement, valueElement);
  return row;
}


function showLoadingState(container, message) {
  const wrapper = element('div', 'loading-state');
  wrapper.textContent = message;
  container.replaceChildren(wrapper);
}


function showEmptyState(container, title, message) {
  const wrapper = element('div', 'empty-state');
  const content = document.createElement('div');
  const heading = document.createElement('strong');
  heading.textContent = title;
  const description = document.createElement('span');
  description.textContent = message;
  content.append(heading, description);
  wrapper.appendChild(content);
  container.replaceChildren(wrapper);
}


function showErrorState(container, message) {
  const wrapper = element('div', 'error-state');
  const content = document.createElement('div');
  const heading = document.createElement('strong');
  heading.textContent = '加载失败';
  const description = document.createElement('span');
  description.textContent = message || '请稍后重试。';
  content.append(heading, description);
  wrapper.appendChild(content);
  container.replaceChildren(wrapper);
}


function showToast(message, isError = false) {
  const toast = document.getElementById('adminToast');
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.remove('hidden');
  window.clearTimeout(showToast.timeoutId);
  showToast.timeoutId = window.setTimeout(() => toast.classList.add('hidden'), 3500);
}


function gatewayLabel(mode) {
  return mode === 'mock' ? 'Mock 模拟' : 'Manual 人工';
}


function ticketTypeLabel(type) {
  return type === 'refund' ? '退款' : type === 'exchange' ? '换货' : type;
}


function ticketStatusLabel(status) {
  return { pending: '待处理', approved: '已通过', rejected: '已拒绝' }[status] || status;
}


function refundStatusLabel(status) {
  return STATUS_META[status]?.label || status || '未知状态';
}


function orderStatusLabel(status) {
  return {
    pending: '待发货',
    shipped: '已发货',
    delivered: '已签收',
    refunded: '已退款',
    cancelled: '已取消',
  }[status] || status;
}


function intentLabel(intent) {
  return {
    knowledge_query: '知识咨询',
    order_query: '订单查询',
    inventory_query: '库存查询',
    size_recommend: '尺码推荐',
    refund_request: '退款申请',
    composite_query: '组合查询',
    fallback: 'Fallback',
  }[intent] || intent || '未识别';
}


function knowledgeTypeLabel(type) {
  return {
    product_knowledge: '商品知识',
    size_guide: '尺码指南',
    after_sales_policy: '售后政策',
    logistics_policy: '物流规则',
    store_rule: '店铺规则',
    faq: 'FAQ',
  }[type] || type || '未分类';
}


function knowledgeParseLabel(status) {
  return {
    pending: '待解析',
    running: '解析中',
    succeeded: '解析成功',
    failed: '解析失败',
  }[status] || status || '未知';
}


function knowledgeReviewLabel(status) {
  return {
    pending: '待审核',
    approved: '已通过',
    rejected: '已拒绝',
  }[status] || status || '未知';
}


function knowledgeQualityLabel(status) {
  return {
    passed: '质量检查通过',
    warning: '存在质量提醒',
  }[status] || '尚未检查';
}


function knowledgeBuildStatusLabel(status) {
  return {
    building: '构建中',
    ready: '候选就绪',
    active: '当前线上',
    failed: '构建失败',
    superseded: '历史成功版本',
  }[status] || status || '未知';
}


function knowledgeWarningLabel(warning) {
  return {
    extracted_text_too_short: '解析文本较短，请确认内容是否完整',
    replacement_characters_detected: '检测到 Unicode 替换字符，可能存在乱码',
    possible_mojibake_detected: '检测到可能的乱码模式',
    very_long_lines_detected: '存在超长行，建议人工检查排版',
    high_repeated_line_ratio: '重复行比例较高，可能包含页眉页脚噪声',
  }[warning] || warning;
}


function workflowLabel(workflow) {
  return workflow || '尚未进入业务工作流';
}


function traceStatusLabel(status) {
  return {
    running: '运行中',
    succeeded: '成功',
    pending: '待补参数',
    failed: '失败',
  }[status] || status || '未知';
}


function formatConfidence(value) {
  if (value === null || value === undefined) return '—';
  return `${Math.round(Number(value) * 100)}%`;
}


function riskLabel(risk) {
  return risk === 'high' ? '高风险' : '低风险';
}


function formatMoney(value) {
  return new Intl.NumberFormat('zh-CN', {
    style: 'currency',
    currency: 'CNY',
    minimumFractionDigits: 2,
  }).format(Number(value || 0));
}


function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}


function element(tagName, className = '') {
  const node = document.createElement(tagName);
  if (className) node.className = className;
  return node;
}
