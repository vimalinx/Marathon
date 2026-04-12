(() => {
  const { api, post, queryParam, previewText, formatContainerState } = window.MarathonUi;

  let defaultTaskPrompt = '';
  let containersByName = new Map();

  function setValue(id, value) {
    const node = document.getElementById(id);
    if (!node) return;
    node.value = value == null ? '' : String(value);
  }

  function secondsToMinutesValue(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return '';
    const minutes = number / 60;
    return Number.isInteger(minutes) ? String(minutes) : String(minutes.toFixed(2));
  }

  function minutesInputToSeconds(id) {
    const raw = document.getElementById(id).value.trim();
    if (!raw) return '';
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < 0) {
      throw new Error('任务时长上限必须是非负数字。');
    }
    return String(Math.round(parsed * 60));
  }

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

  function setConfigBanner(message, tone = '') {
    const node = document.getElementById('configBanner');
    node.className = `banner ${tone}`.trim();
    node.textContent = message;
    node.classList.remove('hidden');
    setTimeout(() => node.classList.add('hidden'), 4000);
  }

  function containerDisplayName(name) {
    if (name === 'marathon-base') return '默认模板（空容器）';
    return name;
  }

  function renderPreview() {
    const baseName = document.getElementById('baseName').value || '-';
    const containerName = document.getElementById('containerName').value.trim() || '(自动生成)';
    const mode = document.getElementById('modeSelect').value;
    const customModel = document.getElementById('modelInput').value.trim() || '(未填)';
    const customBaseUrl = document.getElementById('baseUrlInput').value.trim() || '(未填)';
    const customApiKey = document.getElementById('apiKeyInput').value.trim() ? '已填写' : '(未填)';
    const maxRounds = document.getElementById('maxRoundsInput').value.trim() || '0';
    const sleepSeconds = document.getElementById('sleepSecondsInput').value.trim() || '1';
    const maxRuntime = document.getElementById('maxRuntimeMinutesInput').value.trim() || '不限制';
    const maxTotalTokens = document.getElementById('maxTotalTokensInput').value.trim() || '不限制';
    const prompt = mode === 'task'
      ? previewText(document.getElementById('taskPrompt').value, defaultTaskPrompt)
      : '自由探索提示';

    document.getElementById('runPreview').textContent =
      `来源：${containerDisplayName(baseName)}\n新容器：${containerName}\n方式：${mode === 'freeplay' ? '自由探索' : '按任务执行'}\nModel：${customModel}\nBase URL：${customBaseUrl}\nAPI Key：${customApiKey}\n最大轮次：${maxRounds}\n轮次间隔：${sleepSeconds}s\n时长上限：${maxRuntime === '不限制' ? maxRuntime : `${maxRuntime} 分钟`}\n总 token 预算：${maxTotalTokens}\n任务：${prompt}`;
  }

  function nonEmptyValue(id) {
    return document.getElementById(id).value.trim();
  }

  function collectModelPayload() {
    const payload = {};
    const mappings = [
      ['modelInput', 'model'],
      ['baseUrlInput', 'base_url'],
      ['apiKeyInput', 'api_key'],
      ['reasoningEffort', 'reasoning_effort'],
      ['temperatureInput', 'temperature'],
      ['topPInput', 'top_p'],
      ['maxCompletionTokensInput', 'max_completion_tokens'],
      ['requestTimeoutSecondsInput', 'request_timeout_seconds'],
      ['requestMaxAttemptsInput', 'request_max_attempts'],
      ['requestRetryDelaySecondsInput', 'request_retry_delay_seconds'],
    ];

    mappings.forEach(([id, key]) => {
      const value = nonEmptyValue(id);
      if (value) {
        payload[key] = value;
      }
    });

    const extraBody = nonEmptyValue('extraBodyInput');
    if (extraBody) {
      const parsed = JSON.parse(extraBody);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Extra Body JSON 必须是一个对象。');
      }
      payload.extra_body = extraBody;
    }

    return payload;
  }

  function collectRunControlPayload() {
    const payload = {};
    const maxRounds = nonEmptyValue('maxRoundsInput');
    const sleepSeconds = nonEmptyValue('sleepSecondsInput');
    const maxTotalTokens = nonEmptyValue('maxTotalTokensInput');
    const maxRuntimeSeconds = minutesInputToSeconds('maxRuntimeMinutesInput');

    if (maxRounds) payload.max_rounds = maxRounds;
    if (sleepSeconds) payload.sleep_seconds = sleepSeconds;
    if (maxRuntimeSeconds) payload.max_runtime_seconds = maxRuntimeSeconds;
    if (maxTotalTokens) payload.max_total_tokens = maxTotalTokens;
    return payload;
  }

  function applyContainerSettings(settings = {}) {
    setValue('modeSelect', settings.mode || 'task');
    setValue('taskPrompt', settings.task_prompt || defaultTaskPrompt);
    setValue('modelInput', settings.model || document.getElementById('modelInput').value);
    setValue('baseUrlInput', settings.base_url || document.getElementById('baseUrlInput').value);
    setValue('reasoningEffort', settings.reasoning_effort || '');
    setValue('temperatureInput', settings.temperature ?? '');
    setValue('topPInput', settings.top_p ?? '');
    setValue('maxCompletionTokensInput', settings.max_completion_tokens ?? '');
    setValue('requestTimeoutSecondsInput', settings.request_timeout_seconds ?? document.getElementById('requestTimeoutSecondsInput').value);
    setValue('maxRoundsInput', settings.max_rounds ?? '0');
    setValue('sleepSecondsInput', settings.sleep_seconds ?? '1');
    setValue('maxRuntimeMinutesInput', secondsToMinutesValue(settings.max_runtime_seconds));
    setValue('maxTotalTokensInput', settings.max_total_tokens ?? '');
    syncMode();
  }

  async function loadBaseContainerDefaults() {
    const baseName = document.getElementById('baseName').value;
    if (!baseName || !containersByName.has(baseName)) {
      renderPreview();
      return;
    }
    const detail = await api(`/api/containers/${encodeURIComponent(baseName)}`);
    applyContainerSettings(detail.saved_agent_settings || {});
    renderPreview();
  }

  function syncMode() {
    const taskField = document.getElementById('taskField');
    taskField.classList.toggle('hidden', document.getElementById('modeSelect').value === 'freeplay');
    renderPreview();
  }

  async function loadPage() {
    const [overview, profilesPayload] = await Promise.all([
      api('/api/overview'),
      api('/api/model-profiles').catch(() => ({ profiles: [], default_profile_id: '' })),
    ]);
    document.getElementById('serverTime').textContent = overview.server_time || '-';
    defaultTaskPrompt = overview.config?.default_task_prompt || '';

    const baseSelect = document.getElementById('baseName');
    baseSelect.innerHTML = '';

    const containers = overview.containers || [];
    containers.sort((a, b) => {
      if (a.name === 'marathon-base') return -1;
      if (b.name === 'marathon-base') return 1;
      return a.name.localeCompare(b.name);
    });
    containersByName = new Map(containers.map((container) => [container.name, container]));
    containers.forEach((container) => {
      const option = document.createElement('option');
      option.value = container.name;
      option.textContent = container.name === 'marathon-base'
        ? `默认模板 · ${formatContainerState(container.state || 'UNKNOWN')}`
        : `${container.name} · ${formatContainerState(container.state || 'UNKNOWN')}`;
      baseSelect.append(option);
    });
    if (containersByName.has('marathon-base') && !queryParam('base').trim()) {
      baseSelect.value = 'marathon-base';
    }

    // Pre-fill model fields from the default profile if available
    const profiles = profilesPayload.profiles || [];
    const defaultProfileId = profilesPayload.default_profile_id || '';
    const defaultProfile = profiles.find((p) => p.id === defaultProfileId) || profiles[0];
    if (defaultProfile) {
      if (defaultProfile.model && !document.getElementById('modelInput').value) {
        document.getElementById('modelInput').value = defaultProfile.model;
      }
      if (defaultProfile.base_url && !document.getElementById('baseUrlInput').value) {
        document.getElementById('baseUrlInput').value = defaultProfile.base_url;
      }
      if (defaultProfile.api_key && !document.getElementById('apiKeyInput').value) {
        document.getElementById('apiKeyInput').value = defaultProfile.api_key;
      }
      if (defaultProfile.reasoning_effort && !document.getElementById('reasoningEffort').value) {
        document.getElementById('reasoningEffort').value = defaultProfile.reasoning_effort;
      }
      if (defaultProfile.temperature != null && !document.getElementById('temperatureInput').value) {
        document.getElementById('temperatureInput').value = String(defaultProfile.temperature);
      }
      if (defaultProfile.top_p != null && !document.getElementById('topPInput').value) {
        document.getElementById('topPInput').value = String(defaultProfile.top_p);
      }
      if (defaultProfile.max_completion_tokens != null && !document.getElementById('maxCompletionTokensInput').value) {
        document.getElementById('maxCompletionTokensInput').value = String(defaultProfile.max_completion_tokens);
      }
      if (defaultProfile.request_timeout_seconds != null && !document.getElementById('requestTimeoutSecondsInput').value) {
        document.getElementById('requestTimeoutSecondsInput').value = String(defaultProfile.request_timeout_seconds);
      }
      if (defaultProfile.request_max_attempts != null && !document.getElementById('requestMaxAttemptsInput').value) {
        document.getElementById('requestMaxAttemptsInput').value = String(defaultProfile.request_max_attempts);
      }
      if (defaultProfile.request_retry_delay_seconds != null && !document.getElementById('requestRetryDelaySecondsInput').value) {
        document.getElementById('requestRetryDelaySecondsInput').value = String(defaultProfile.request_retry_delay_seconds);
      }
      if (defaultProfile.extra_body && Object.keys(defaultProfile.extra_body).length && !document.getElementById('extraBodyInput').value) {
        document.getElementById('extraBodyInput').value = JSON.stringify(defaultProfile.extra_body, null, 2);
      }
    }

    const requestedBase = queryParam('base').trim();
    if (requestedBase && containers.some((container) => container.name === requestedBase)) {
      baseSelect.value = requestedBase;
    }

    if (!document.getElementById('containerName').value.trim()) {
      document.getElementById('containerName').value = suggestedName();
    }

    if (!document.getElementById('maxRoundsInput').value.trim()) {
      document.getElementById('maxRoundsInput').value = '0';
    }
    if (!document.getElementById('sleepSecondsInput').value.trim()) {
      document.getElementById('sleepSecondsInput').value = '1';
    }

    document.getElementById('submitBtn').disabled = containers.length === 0;
    if (containers.length === 0) {
      setBanner('当前没有可用的来源容器，先准备一个基础容器。', 'warn');
    } else {
      setBanner('来源容器已就绪，可以直接创建。');
      await loadBaseContainerDefaults();
    }
    if (!document.getElementById('taskPrompt').value.trim()) {
      document.getElementById('taskPrompt').value = defaultTaskPrompt;
    }
    syncMode();
  }

  // Event listeners
  document.getElementById('baseName').addEventListener('change', () => {
    void loadBaseContainerDefaults().catch((error) => setBanner(error.message, 'bad'));
  });
  document.getElementById('containerName').addEventListener('input', renderPreview);
  document.getElementById('taskPrompt').addEventListener('input', renderPreview);
  document.getElementById('modeSelect').addEventListener('change', syncMode);
  [
    'maxRoundsInput',
    'sleepSecondsInput',
    'maxRuntimeMinutesInput',
    'maxTotalTokensInput',
    'modelInput',
    'baseUrlInput',
    'apiKeyInput',
    'reasoningEffort',
    'temperatureInput',
    'topPInput',
    'maxCompletionTokensInput',
    'requestTimeoutSecondsInput',
    'requestMaxAttemptsInput',
    'requestRetryDelaySecondsInput',
    'extraBodyInput',
  ].forEach((id) => {
    document.getElementById(id).addEventListener('input', renderPreview);
    document.getElementById(id).addEventListener('change', renderPreview);
  });

  document.getElementById('fillNameBtn').addEventListener('click', () => {
    document.getElementById('containerName').value = suggestedName();
    renderPreview();
  });

  // Save config button
  document.getElementById('testConfigBtn').addEventListener('click', async () => {
    try {
      const payload = collectModelPayload();
      if (!payload.model) {
        throw new Error('先填 Model。');
      }
      if (!payload.base_url) {
        throw new Error('先填 Base URL。');
      }
      if (!payload.api_key) {
        throw new Error('先填 API Key。');
      }
      setConfigBanner('正在测试模型连通性…', 'good');
      const result = await post('/api/model-connectivity-test', payload);
      const usage = result.usage?.total_tokens != null ? ` · total_tokens ${result.usage.total_tokens}` : '';
      setConfigBanner(
        `连通成功 · ${result.response_model || result.model} · ${result.latency_ms}ms${usage} · ${result.preview}`,
        'good',
      );
    } catch (error) {
      setConfigBanner(error.message, 'bad');
    }
  });

  document.getElementById('saveConfigBtn').addEventListener('click', async () => {
    try {
      const model = nonEmptyValue('modelInput');
      const baseUrl = nonEmptyValue('baseUrlInput');
      const apiKey = nonEmptyValue('apiKeyInput');
      if (!model && !baseUrl) {
        setConfigBanner('至少填 Model 或 Base URL 才能保存。', 'warn');
        return;
      }

      const profile = {
        id: 'default',
        label: '默认配置',
        model: model,
        base_url: baseUrl,
        api_key: apiKey,
        reasoning_effort: nonEmptyValue('reasoningEffort'),
        temperature: nonEmptyValue('temperatureInput') ? parseFloat(nonEmptyValue('temperatureInput')) : null,
        top_p: nonEmptyValue('topPInput') ? parseFloat(nonEmptyValue('topPInput')) : null,
        max_completion_tokens: nonEmptyValue('maxCompletionTokensInput') ? parseInt(nonEmptyValue('maxCompletionTokensInput'), 10) : null,
        request_timeout_seconds: nonEmptyValue('requestTimeoutSecondsInput') ? parseFloat(nonEmptyValue('requestTimeoutSecondsInput')) : 120,
        request_max_attempts: nonEmptyValue('requestMaxAttemptsInput') ? parseInt(nonEmptyValue('requestMaxAttemptsInput'), 10) : null,
        request_retry_delay_seconds: nonEmptyValue('requestRetryDelaySecondsInput') ? parseFloat(nonEmptyValue('requestRetryDelaySecondsInput')) : null,
        extra_body: {},
      };

      const extraBody = nonEmptyValue('extraBodyInput');
      if (extraBody) {
        profile.extra_body = JSON.parse(extraBody);
      }

      await post('/api/model-profiles', {
        default_profile_id: 'default',
        profiles: [profile],
      });
      setConfigBanner('配置已保存；后续打开新建任务页会自动复用。', 'good');
    } catch (error) {
      setConfigBanner(error.message, 'bad');
    }
  });

  // Submit form
  document.getElementById('launchForm').addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
      base_name: document.getElementById('baseName').value,
      container_name: document.getElementById('containerName').value.trim(),
      mode: document.getElementById('modeSelect').value,
    };
    Object.assign(payload, collectModelPayload());
    Object.assign(payload, collectRunControlPayload());
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
