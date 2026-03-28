(() => {
  const { api, post, queryParam, previewText, formatContainerState } = window.MarathonUi;

  let defaultTaskPrompt = '';
  let containersByName = new Map();
  let accountsByHandle = new Map();
  let keepRequestedHandle = false;

  function timestampSlug() {
    const now = new Date();
    const pad = (value) => String(value).padStart(2, '0');
    return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  }

  function suggestedName() {
    return `marathon-${timestampSlug()}`;
  }

  function setBanner(message, tone = '') {
    const node = document.getElementById('formBanner');
    node.className = `banner ${tone}`.trim();
    node.textContent = message;
  }

  function renderPreview() {
    const baseName = document.getElementById('baseName').value || '-';
    const containerName = document.getElementById('containerName').value.trim() || '(自动生成)';
    const mode = document.getElementById('modeSelect').value;
    const agentHandle = document.getElementById('agentHandle').value || '先不绑定公开账号';
    const prompt = mode === 'task'
      ? previewText(document.getElementById('taskPrompt').value, defaultTaskPrompt)
      : '自由探索会自动使用开放探索提示。';

    document.getElementById('runPreview').textContent =
      `来源容器：${baseName}\n新容器：${containerName}\n运行方式：${mode === 'freeplay' ? '自由探索' : '按任务执行'}\n公开账号：${agentHandle}\n任务说明：${prompt}`;
  }

  function syncMode() {
    const taskField = document.getElementById('taskField');
    taskField.classList.toggle('hidden', document.getElementById('modeSelect').value === 'freeplay');
    renderPreview();
  }

  function applyInheritedAgentHandle() {
    if (keepRequestedHandle) {
      renderPreview();
      return;
    }

    const baseName = document.getElementById('baseName').value;
    const accountSelect = document.getElementById('agentHandle');
    const inheritedHandle = containersByName.get(baseName)?.agent_handle || '';

    if (inheritedHandle && accountsByHandle.has(inheritedHandle)) {
      accountSelect.value = inheritedHandle;
    } else {
      accountSelect.value = '';
    }
    renderPreview();
  }

  async function loadPage() {
    const [overview, accountsPayload] = await Promise.all([
      api('/api/overview'),
      api('/api/agent-accounts').catch(() => ({ accounts: [] })),
    ]);
    document.getElementById('serverTime').textContent = overview.server_time || '-';
    defaultTaskPrompt = overview.config?.default_task_prompt || '';

    const baseSelect = document.getElementById('baseName');
    baseSelect.innerHTML = '';

    const containers = overview.containers || [];
    containersByName = new Map(containers.map((container) => [container.name, container]));
    containers.forEach((container) => {
      const option = document.createElement('option');
      option.value = container.name;
      option.textContent = `${container.name} · ${formatContainerState(container.state || 'UNKNOWN')}`;
      baseSelect.append(option);
    });

    const accountSelect = document.getElementById('agentHandle');
    const accounts = accountsPayload.accounts || [];
    accountsByHandle = new Map(accounts.map((account) => [account.agent_handle, account]));
    accountSelect.innerHTML = '<option value="">先不绑定公开账号</option>';
    accounts.forEach((account) => {
      const option = document.createElement('option');
      option.value = account.agent_handle;
      option.textContent = `@${account.agent_handle}${account.display_name ? ` · ${account.display_name}` : ''}`;
      accountSelect.append(option);
    });

    const requestedBase = queryParam('base').trim();
    if (requestedBase && containers.some((container) => container.name === requestedBase)) {
      baseSelect.value = requestedBase;
    }
    const requestedHandle = queryParam('agent_handle').trim();
    if (requestedHandle && accounts.some((account) => account.agent_handle === requestedHandle)) {
      accountSelect.value = requestedHandle;
      keepRequestedHandle = true;
    } else {
      keepRequestedHandle = false;
      applyInheritedAgentHandle();
    }

    if (!document.getElementById('taskPrompt').value.trim()) {
      document.getElementById('taskPrompt').value = defaultTaskPrompt;
    }

    if (!document.getElementById('containerName').value.trim()) {
      document.getElementById('containerName').value = suggestedName();
    }

    document.getElementById('submitBtn').disabled = containers.length === 0;
    if (containers.length === 0) {
      setBanner('当前没有可用的来源容器，先准备一个基础容器。', 'warn');
    } else {
      setBanner('来源容器已经就绪，可以直接创建。');
    }
    syncMode();
  }

  document.getElementById('baseName').addEventListener('change', applyInheritedAgentHandle);
  document.getElementById('containerName').addEventListener('input', renderPreview);
  document.getElementById('taskPrompt').addEventListener('input', renderPreview);
  document.getElementById('modeSelect').addEventListener('change', syncMode);
  document.getElementById('agentHandle').addEventListener('change', () => {
    keepRequestedHandle = false;
    renderPreview();
  });

  document.getElementById('fillNameBtn').addEventListener('click', () => {
    document.getElementById('containerName').value = suggestedName();
    renderPreview();
  });

  document.getElementById('launchForm').addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
      base_name: document.getElementById('baseName').value,
      container_name: document.getElementById('containerName').value.trim(),
      mode: document.getElementById('modeSelect').value,
      agent_handle: document.getElementById('agentHandle').value,
    };
    if (payload.mode === 'task') {
      payload.task_prompt = document.getElementById('taskPrompt').value;
    }

    try {
      setBanner('正在创建并启动新任务。', 'good');
      const result = await post('/api/runs/start', payload);
      if (!result.ok) {
        throw new Error(result.error || result.stderr || result.step || '创建失败');
      }
      const targetContainer = result.launch?.container || payload.container_name || '';
      setBanner(`创建完成，正在跳转到 ${targetContainer} 的详情页。`, 'good');
      window.location.href = `/container?container=${encodeURIComponent(targetContainer)}`;
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  loadPage().catch((error) => {
    setBanner(error.message, 'bad');
    document.getElementById('submitBtn').disabled = true;
  });
})();
