(() => {
  const {
    api,
    queryParam,
    latestRunForContainer,
    activeRunForContainer,
    formatMode,
    blogSections,
    formatTime,
  } = window.MarathonUi;

  function cell(mainText, subText) {
    const cell = document.createElement('td');

    const main = document.createElement('div');
    main.className = 'table-main';
    main.textContent = mainText;

    const sub = document.createElement('div');
    sub.className = 'table-sub';
    sub.textContent = subText;

    cell.append(main, sub);
    return cell;
  }

  function blogCell(container, active, latest) {
    const cell = document.createElement('td');
    const post = container?.latest_blog_post || null;
    const sections = blogSections(post);

    const time = document.createElement('div');
    time.className = 'table-main';
    time.textContent = formatTime(container?.latest_blog_updated_at || active?.updated_at || latest?.updated_at);

    const stack = document.createElement('div');
    stack.className = 'table-blog';

    [
      { label: 'Done', text: sections.done || active?.latest_action_done || latest?.latest_action_done || '还没有博客记录。' },
      { label: 'Next', text: sections.next || active?.latest_action_next || latest?.latest_action_next || '下一步还没有写出来。' },
      { label: 'Thought', text: sections.thought || active?.latest_action_thought || latest?.latest_action_thought || '这一轮的思路还没有写出来。' },
    ].forEach((item) => {
      const block = document.createElement('div');
      block.className = 'table-blog-block';

      const label = document.createElement('strong');
      label.textContent = item.label;

      const text = document.createElement('div');
      text.className = 'table-blog-copy';
      text.textContent = item.text;

      block.append(label, text);
      stack.append(block);
    });

    cell.append(time, stack);
    return cell;
  }

  function renderRows(overview) {
    const root = document.getElementById('sandboxesTableBody');
    const current = queryParam('container').trim();
    const containers = overview.containers || [];
    const runningContainers = containers.filter((container) => String(container.state || '').toUpperCase() === 'RUNNING').length;
    const runningAgents = (overview.runs || []).filter(
      (run) => run.supervisor_running || String(run.state || '').toLowerCase() === 'running',
    ).length;

    document.getElementById('serverTime').textContent = overview.server_time || '-';
    document.getElementById('pageNote').textContent =
      `共 ${containers.length} 个容器，${runningContainers} 个容器在运行，${runningAgents} 个任务在执行。`;

    root.innerHTML = '';
    if (!containers.length) {
      const row = document.createElement('tr');
      const cell = document.createElement('td');
      cell.colSpan = 5;
      cell.textContent = '还没有容器。';
      row.append(cell);
      root.append(row);
      return;
    }

    containers.forEach((container) => {
      const latest = latestRunForContainer(overview, container.name);
      const active = activeRunForContainer(overview, container.name);

      const row = document.createElement('tr');
      if (current === container.name) {
        row.style.background = 'var(--surface-muted)';
      }

      const sandboxCell = cell(
        container.name,
        current === container.name ? '当前选中' : '去看这个容器的详情',
      );

      const containerCell = cell(
        window.MarathonUi.formatContainerState(container.state || 'UNKNOWN'),
        (container.ips || [])[0] || '没有地址',
      );

      const aiCell = cell(
        active ? `执行中 · ${formatMode(active.mode)}` : latest ? `空闲 · ${formatMode(latest.mode)}` : '未启动',
        active?.run_id || latest?.run_id || '还没有任务记录',
      );

      const recordCell = blogCell(container, active, latest);

      const actionCell = document.createElement('td');
      const actionWrap = document.createElement('div');
      actionWrap.className = 'card-actions';

      const detailLink = document.createElement('a');
      detailLink.className = 'nav-link button-primary';
      detailLink.href = `/container?container=${encodeURIComponent(container.name)}`;
      detailLink.textContent = '看详情';

      const newLink = document.createElement('a');
      newLink.className = 'nav-link';
      newLink.href = `/new?base=${encodeURIComponent(container.name)}`;
      newLink.textContent = '基于此新建';

      actionWrap.append(detailLink, newLink);
      actionCell.append(actionWrap);

      row.append(sandboxCell, containerCell, aiCell, recordCell, actionCell);
      root.append(row);
    });
  }

  async function loadPage() {
    const overview = await api('/api/overview');
    renderRows(overview);
  }

  document.getElementById('refreshBtn').addEventListener('click', async () => {
    try {
      await loadPage();
    } catch (error) {
      document.getElementById('pageNote').textContent = error.message;
    }
  });

  loadPage().catch((error) => {
    const root = document.getElementById('sandboxesTableBody');
    root.innerHTML = '';
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.textContent = error.message;
    row.append(cell);
    root.append(row);
    document.getElementById('pageNote').textContent = '读取容器列表失败。';
  });
})();
