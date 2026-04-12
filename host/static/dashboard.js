(() => {
  const {
    api,
    preferredRunForContainer,
    previewText,
    blogSections,
    blogPreview,
    formatMode,
    formatRunState,
    formatContainerState,
    formatTime,
    stateTone,
    containerStateTone,
  } = window.MarathonUi;

  let refreshTimer = null;
  let lastKnownLiveState = false;
  let loading = false;
  let currentFilter = 'all';
  let cachedOverview = null;

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = value;
    }
  }

  function chip(text, tone = '') {
    const node = document.createElement('span');
    node.className = `status-chip ${tone}`.trim();
    node.textContent = text;
    return node;
  }

  function metaItem(label, value) {
    const wrap = document.createElement('div');
    wrap.className = 'meta-item';

    const dt = document.createElement('dt');
    dt.textContent = label;

    const dd = document.createElement('dd');
    dd.textContent = value;

    wrap.append(dt, dd);
    return wrap;
  }

  function emptyState(text) {
    const node = document.createElement('div');
    node.className = 'empty-state';
    node.textContent = text;
    return node;
  }

  function roundValue(run) {
    const value = Number(run?.completed_rounds);
    return Number.isFinite(value) && value >= 0 ? String(value) : '-';
  }

  function runIsLive(run) {
    return Boolean(run?.supervisor_running || String(run?.state || '').toLowerCase() === 'running');
  }

  function containerIsRunning(container) {
    return String(container?.state || '').toUpperCase() === 'RUNNING';
  }

  function clearRefreshTimer() {
    if (refreshTimer) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function scheduleAutoRefresh(isLive) {
    lastKnownLiveState = isLive;
    clearRefreshTimer();
    const delay = document.hidden ? 15000 : isLive ? 4000 : 12000;
    refreshTimer = window.setTimeout(() => {
      void loadPage({ silent: true });
    }, delay);
  }

  function hasLiveRun(overview) {
    return (overview.runs || []).some((run) => runIsLive(run));
  }

  function refreshLabel(isLive) {
    return isLive ? '自动 4 秒' : '自动 12 秒';
  }

  function latestPost(item) {
    return item?.container?.latest_blog_post || null;
  }

  function postField(item, key, ...fallbacks) {
    const sections = blogSections(latestPost(item));
    const fromPost = sections[key] || '';
    if (fromPost) return fromPost;
    return previewText(...fallbacks);
  }

  function runIntent(item) {
    return postField(
      item,
      'next',
      item?.run?.latest_action_next,
      item?.run?.last_next,
      item?.run?.task_prompt,
    );
  }

  function runMotion(item) {
    return postField(
      item,
      'done',
      item?.run?.latest_action_done,
      item?.run?.last_done,
      item?.run?.latest_action_summary,
      item?.run?.last_summary,
    );
  }

  function runThought(item) {
    return postField(
      item,
      'thought',
      item?.run?.latest_action_thought,
      item?.run?.last_thought,
      item?.run?.latest_response_preview,
    );
  }

  function truncateText(text, limit = 160) {
    const compact = String(text || '')
      .trim()
      .replace(/\s+/g, ' ');
    if (!compact) return '还没有最近输出。';
    if (compact.length <= limit) return compact;
    return `${compact.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
  }

  function latestRoundLabel(item) {
    const runRound = Number(item?.run?.completed_rounds);
    if (Number.isFinite(runRound) && runRound > 0) {
      return `第 ${runRound} 轮`;
    }
    const postRound = Number(latestPost(item)?.round);
    if (Number.isFinite(postRound) && postRound > 0) {
      return `第 ${postRound} 轮`;
    }
    return '还没有轮次';
  }

  function updatedAt(item) {
    return item?.container?.latest_blog_updated_at || item?.run?.updated_at || '';
  }

  function renderTease(label, text, className = 'featured-card-block') {
    const block = document.createElement('div');
    block.className = className;

    const blockLabel = document.createElement('strong');
    blockLabel.textContent = label;

    const blockText = document.createElement('p');
    blockText.textContent = text;

    block.append(blockLabel, blockText);
    return block;
  }

  function makeCardNavigable(node, href, label) {
    node.classList.add('card-shell');
    node.tabIndex = 0;
    node.setAttribute('role', 'link');
    node.setAttribute('aria-label', label);

    node.addEventListener('click', (event) => {
      if (event.target.closest('a, button, input, select, textarea, summary')) {
        return;
      }
      window.location.href = href;
    });

    node.addEventListener('keydown', (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') {
        return;
      }
      event.preventDefault();
      window.location.href = href;
    });
  }

  function decorateContainers(overview) {
    const recencyIndexByContainer = new Map();
    (overview.runs || []).forEach((run, index) => {
      const containerName = String(run?.container || '').trim();
      if (containerName && !recencyIndexByContainer.has(containerName)) {
        recencyIndexByContainer.set(containerName, index);
      }
    });

    return [...(overview.containers || [])]
      .map((container) => {
        const run = preferredRunForContainer(overview, container.name);
        const isLive = runIsLive(run);
        const isRunning = containerIsRunning(container);
        const hasRun = Boolean(run);
        const recentIndex = recencyIndexByContainer.has(container.name)
          ? Number(recencyIndexByContainer.get(container.name))
          : 999;
        const rounds = Number(run?.completed_rounds);

        let score = 0;
        if (isLive) score += 40;
        if (isRunning) score += 15;
        if (hasRun) score += 10;
        if (recentIndex !== 999) score += Math.max(0, 12 - recentIndex);
        if (Number.isFinite(rounds) && rounds > 0) score += Math.min(5, rounds);
        if (String(run?.mode || '').toLowerCase() === 'freeplay') score += 1;

        return {
          container,
          run,
          isLive,
          isRunning,
          hasRun,
          recentIndex,
          score,
        };
      })
      .sort((left, right) => {
        if (right.score !== left.score) return right.score - left.score;
        if (left.recentIndex !== right.recentIndex) return left.recentIndex - right.recentIndex;
        return String(left.container?.name || '').localeCompare(String(right.container?.name || ''), 'zh-CN');
      });
  }

  function matchesFilter(item) {
    if (currentFilter === 'running') {
      return item.isLive || item.isRunning;
    }
    if (currentFilter === 'recent') {
      return item.hasRun;
    }
    return true;
  }

  function detailHref(containerName) {
    return `/container?container=${encodeURIComponent(containerName)}`;
  }

  function newHref(containerName) {
    return containerName ? `/new?base=${encodeURIComponent(containerName)}` : '/new';
  }

  function actionLink(href, text, className = 'nav-link') {
    const link = document.createElement('a');
    link.className = className;
    link.href = href;
    link.textContent = text;
    return link;
  }

  function renderTabs() {
    document.querySelectorAll('#filterTabs [data-filter]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.filter === currentFilter));
    });
  }

  function renderFilterSummary(allItems, matchedItems) {
    const liveCount = allItems.filter((item) => item.isLive || item.isRunning).length;
    const recentCount = allItems.filter((item) => item.hasRun).length;

    if (!allItems.length) {
      setText('filterSubtitle', '现在还没有容器。先新建一个任务，首页就会开始长内容。');
      return;
    }

    if (currentFilter === 'running') {
      setText('filterSubtitle', `只显示正在运行或仍有活动任务的容器，共 ${matchedItems.length} 个。`);
      return;
    }

    if (currentFilter === 'recent') {
      setText('filterSubtitle', `只显示留下运行记录的容器，共 ${matchedItems.length} 个；当前共有 ${recentCount} 个有历史。`);
      return;
    }

    setText('filterSubtitle', `正在显示全部 ${allItems.length} 个容器，其中 ${liveCount} 个正在运行，${recentCount} 个留有任务记录。`);
  }

  function renderFeaturedSummary(allItems, featuredItems, remainingItems) {
    if (!allItems.length) {
      setText('featuredSubtitle', '还没有重点容器，先让系统跑出第一个实例。');
      setText('gridSubtitle', '下面会保留新建入口，等第一页数据长出来。');
      return;
    }

    if (!featuredItems.length) {
      setText('featuredSubtitle', '当前筛选下没有重点容器。');
      setText('gridSubtitle', `当前筛选下还剩 ${remainingItems.length} 个容器。`);
      return;
    }

    setText('featuredSubtitle', `按当前活跃度先挑出 ${featuredItems.length} 个重点容器，优先看最值得点开的。`);

    if (!remainingItems.length) {
      setText('gridSubtitle', '当前重点里已经包含全部符合条件的容器。');
      return;
    }

    setText('gridSubtitle', `下方还有 ${remainingItems.length} 个符合当前筛选的容器，继续用浏览方式往下扫。`);
  }

  function featuredEmptyCard(text) {
    const article = document.createElement('article');
    article.className = 'featured-card';
    article.append(emptyState(text));
    return article;
  }

  function browserEmptyCard(text) {
    const article = document.createElement('article');
    article.className = 'browser-card';
    article.append(emptyState(text));
    return article;
  }

  function renderFeaturedCard(item) {
    const href = detailHref(item.container.name);
    const article = document.createElement('article');
    article.className = 'featured-card';
    makeCardNavigable(article, href, `打开容器 ${item.container?.name || ''} 的详情页`);

    const head = document.createElement('div');
    head.className = 'featured-card-head';

    const eyebrow = document.createElement('p');
    eyebrow.className = 'card-eyebrow';
    eyebrow.textContent = item.isLive ? '当前重点' : item.hasRun ? '重点回看' : '待启动容器';

    const titleWrap = document.createElement('div');
    titleWrap.className = 'featured-card-title';

    const title = document.createElement('h3');
    title.textContent = item.container?.name || '未命名容器';

    const subtitle = document.createElement('p');
    subtitle.textContent = item.run
      ? `${latestRoundLabel(item)} · ${item.isLive ? '正在推进' : '最近更新'} · ${item.run.run_id || '-'}`
      : '这个容器还没有任务记录';

    const statusRow = document.createElement('div');
    statusRow.className = 'status-row';
    statusRow.append(chip(`容器：${formatContainerState(item.container?.state)}`, containerStateTone(item.container?.state)));
    if (item.run) {
      statusRow.append(chip(`任务：${formatRunState(item.run.state)}`, stateTone(item.run.state)));
      statusRow.append(chip(formatMode(item.run.mode)));
    } else {
      statusRow.append(chip('任务未启动', 'warn'));
    }
    statusRow.append(chip(latestRoundLabel(item)));

    titleWrap.append(title, subtitle);
    head.append(eyebrow, titleWrap, statusRow);

    const copy = document.createElement('div');
    copy.className = 'featured-card-copy';

    copy.append(
      renderTease(
        '刚刚完成',
        item.run || latestPost(item) ? truncateText(runMotion(item), 120) : '还没有任务记录。',
      ),
      renderTease(
        '接下来',
        item.run || latestPost(item) ? truncateText(runIntent(item), 100) : '等它跑起来后会显示。',
        'featured-card-block featured-card-block-accent',
      ),
    );

    const foot = document.createElement('div');
    foot.className = 'featured-card-foot';

    const meta = document.createElement('dl');
    meta.className = 'featured-meta';
    meta.append(
      metaItem('更新', updatedAt(item) ? formatTime(updatedAt(item)) : '-'),
      metaItem('轮次', latestRoundLabel(item)),
      metaItem('模型', item.run?.model || '-'),
    );

    const actions = document.createElement('div');
    actions.className = 'featured-actions';
    actions.append(actionLink(newHref(item.container.name), '基于此新建', 'nav-link'));

    foot.append(meta, actions);
    article.append(head, copy, foot);
    return article;
  }

  function renderBrowserCard(item) {
    const href = detailHref(item.container.name);
    const article = document.createElement('article');
    article.className = 'browser-card';
    makeCardNavigable(article, href, `打开容器 ${item.container?.name || ''} 的详情页`);

    const titleWrap = document.createElement('div');
    titleWrap.className = 'browser-card-title';

    const title = document.createElement('h3');
    title.textContent = item.container?.name || '未命名容器';

    const subtitle = document.createElement('p');
    subtitle.textContent = item.run
      ? `${latestRoundLabel(item)} · ${updatedAt(item) ? formatTime(updatedAt(item)) : '最近有更新'}`
      : '这个容器还没有运行记录';

    titleWrap.append(title, subtitle);

    const statusRow = document.createElement('div');
    statusRow.className = 'status-row';
    statusRow.append(chip(formatContainerState(item.container?.state), containerStateTone(item.container?.state)));
    if (item.run) {
      statusRow.append(chip(formatRunState(item.run.state), stateTone(item.run.state)));
      statusRow.append(chip(formatMode(item.run.mode)));
    } else {
      statusRow.append(chip('未启动', 'warn'));
    }

    const summary = document.createElement('div');
    summary.className = 'card-summary';

    const summaryLead = document.createElement('p');
    summaryLead.className = 'card-summary-main';
    summaryLead.textContent = item.run || latestPost(item)
      ? truncateText(runMotion(item), 100)
      : '还没有任务记录。';

    summary.append(summaryLead);

    const foot = document.createElement('div');
    foot.className = 'browser-card-foot';

    const meta = document.createElement('div');
    meta.className = 'browser-card-meta';
    meta.textContent = updatedAt(item)
      ? `${formatTime(updatedAt(item))}`
      : item.isRunning ? '已启动' : '-';

    const actions = document.createElement('div');
    actions.className = 'card-actions';
    actions.append(actionLink(newHref(item.container.name), '基于此新建', 'nav-link'));

    foot.append(meta, actions);
    article.append(titleWrap, statusRow, summary, foot);
    return article;
  }

  function renderCreateCard() {
    const article = document.createElement('a');
    article.className = 'browser-card create-browser-card';
    article.href = '/new';

    const title = document.createElement('strong');
    title.textContent = '新建任务';

    const note = document.createElement('p');
    note.textContent = '开一个新的容器，或者从现有容器复制出新的实验分支。';

    article.append(title, note);
    return article;
  }

  function renderFeatured(items, hasContainers) {
    const root = document.getElementById('featuredRow');
    root.replaceChildren();

    if (!items.length) {
      root.append(featuredEmptyCard(hasContainers ? '当前筛选下没有重点容器。' : '还没有容器。先去新建页创建一个任务。'));
      return;
    }

    root.replaceChildren(...items.map((item) => renderFeaturedCard(item)));
  }

  function renderGrid(items, hasContainers) {
    const root = document.getElementById('containerGrid');
    const children = [renderCreateCard()];

    if (!items.length) {
      children.push(
        browserEmptyCard(hasContainers ? '当前筛选下没有更多容器了。' : '还没有容器。先去新建页创建一个任务。'),
      );
      root.replaceChildren(...children);
      return;
    }

    root.replaceChildren(...children, ...items.map((item) => renderBrowserCard(item)));
  }

  function renderDashboard(overview) {
    cachedOverview = overview;
    const allItems = decorateContainers(overview);
    const matchedItems = allItems.filter((item) => matchesFilter(item));
    const featuredItems = matchedItems.slice(0, Math.min(4, matchedItems.length));
    const remainingItems = matchedItems.slice(featuredItems.length);

    renderTabs();
    renderFilterSummary(allItems, matchedItems);
    renderFeaturedSummary(allItems, featuredItems, remainingItems);
    renderFeatured(featuredItems, Boolean(allItems.length));
    renderGrid(remainingItems, Boolean(allItems.length));
  }

  function renderDashboardError(message) {
    setText('filterSubtitle', message);
    setText('featuredSubtitle', '当前无法加载重点容器。');
    setText('gridSubtitle', '稍后可以点刷新重试。');
    document.getElementById('featuredRow').replaceChildren(featuredEmptyCard(message));
    document.getElementById('containerGrid').replaceChildren(renderCreateCard(), browserEmptyCard(message));
  }

  async function loadPage(options = {}) {
    const silent = Boolean(options.silent);
    if (loading) return;
    loading = true;

    try {
      const overview = await api('/api/overview');
      document.getElementById('serverTime').textContent = overview.server_time || '-';
      renderDashboard(overview);
      scheduleAutoRefresh(hasLiveRun(overview));
    } catch (error) {
      clearRefreshTimer();
      if (silent) {
        scheduleAutoRefresh(lastKnownLiveState);
      } else {
        renderDashboardError(error.message);
      }
    } finally {
      loading = false;
    }
  }

  document.getElementById('filterTabs').addEventListener('click', (event) => {
    const button = event.target.closest('[data-filter]');
    if (!button) return;
    const nextFilter = button.dataset.filter || 'all';
    if (nextFilter === currentFilter) return;
    currentFilter = nextFilter;
    if (cachedOverview) {
      renderDashboard(cachedOverview);
    }
  });

  document.getElementById('refreshBtn').addEventListener('click', async () => {
    try {
      await loadPage();
    } catch (error) {
      renderDashboardError(error.message);
    }
  });

  document.addEventListener('visibilitychange', () => {
    scheduleAutoRefresh(lastKnownLiveState);
  });

  loadPage().catch((error) => {
    renderDashboardError(error.message);
  });
})();
