(() => {
  const {
    api,
    post,
    queryParam,
    formatMode,
    formatRunState,
    formatContainerState,
    formatTime,
    formatBytes,
    formatNumber,
    formatCpuUsec,
    preferredRunForContainer,
    blogSections,
    blogPreview,
  } = window.MarathonUi;

  let currentContainer = '';
  let currentRunSummary = null;
  let refreshTimer = null;
  let loading = false;
  let lastKnownLiveState = false;
  let settingsDirty = false;
  let settingsContainer = '';

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = value;
    }
  }

  function setValue(id, value) {
    const node = document.getElementById(id);
    if (node) {
      node.value = value == null ? '' : String(value);
    }
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

  function setMetaGrid(id, items) {
    const root = document.getElementById(id);
    if (!root) return;
    root.replaceChildren(...items.map((item) => metaItem(item.label, item.value)));
  }

  function localAgentAccount(containerName) {
    return containerName ? `local/${containerName}` : '-';
  }

  function localFeedPath(containerName) {
    return containerName ? `/api/containers/${containerName}/blog` : '-';
  }

  function publicAccountLabel(binding, containerName) {
    const account = binding?.account || {};
    if (account.display_name) return account.display_name;
    if (binding?.agent_handle) return `@${binding.agent_handle}`;
    return localAgentAccount(containerName);
  }

  function emptyState(text) {
    const node = document.createElement('div');
    node.className = 'empty-state';
    node.textContent = text;
    return node;
  }

  function chip(text, tone = '') {
    const node = document.createElement('span');
    node.className = `status-chip ${tone}`.trim();
    node.textContent = text;
    return node;
  }

  function setBanner(message, tone = '') {
    const node = document.getElementById('detailBanner');
    node.className = `banner ${tone}`.trim();
    node.textContent = message;
  }

  function formatDurationSeconds(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0) return '-';
    if (number < 60) return `${Math.round(number)} 秒`;
    const minutes = number / 60;
    if (minutes < 60) {
      return Number.isInteger(minutes) ? `${minutes} 分钟` : `${minutes.toFixed(1)} 分钟`;
    }
    const hours = minutes / 60;
    return Number.isInteger(hours) ? `${hours} 小时` : `${hours.toFixed(1)} 小时`;
  }

  function secondsToMinutesValue(value) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) return '';
    const minutes = number / 60;
    return Number.isInteger(minutes) ? String(minutes) : String(minutes.toFixed(2));
  }

  function settingsMinutesToSeconds(id) {
    const raw = document.getElementById(id).value.trim();
    if (!raw) return null;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || parsed < 0) {
      throw new Error('任务时长上限必须是非负数字。');
    }
    return Math.round(parsed * 60);
  }

  function markSettingsDirty() {
    settingsDirty = true;
    setText('settingsBackupNote', '有未保存修改。保存时会先创建一份容器设置备份。');
  }

  function collectContainerSettingsPayload() {
    const payload = {};

    function assignText(key, id) {
      const value = document.getElementById(id).value.trim();
      if (value) payload[key] = value;
    }

    function assignNumber(key, id) {
      const value = document.getElementById(id).value.trim();
      if (!value) return;
      const parsed = Number(value);
      if (!Number.isFinite(parsed) || parsed < 0) {
        throw new Error(`${key} 必须是非负数字。`);
      }
      payload[key] = Number.isInteger(parsed) ? parsed : parsed;
    }

    assignText('mode', 'settingsModeSelect');
    assignText('task_prompt', 'settingsTaskPrompt');
    assignText('model', 'settingsModel');
    assignText('base_url', 'settingsBaseUrl');
    assignText('reasoning_effort', 'settingsReasoningEffort');
    assignNumber('temperature', 'settingsTemperature');
    assignNumber('top_p', 'settingsTopP');
    assignNumber('max_rounds', 'settingsMaxRounds');
    assignNumber('sleep_seconds', 'settingsSleepSeconds');
    assignNumber('max_total_tokens', 'settingsMaxTotalTokens');
    assignNumber('max_completion_tokens', 'settingsMaxCompletionTokens');
    assignNumber('request_timeout_seconds', 'settingsRequestTimeoutSeconds');

    const maxRuntimeSeconds = settingsMinutesToSeconds('settingsMaxRuntimeMinutes');
    if (maxRuntimeSeconds != null) {
      payload.max_runtime_seconds = maxRuntimeSeconds;
    }
    return payload;
  }

  function renderContainerSettings(containerDetail) {
    const settings = containerDetail.saved_agent_settings || {};
    const backupSummary = containerDetail.settings_backup_summary || {};
    const latestBackup = backupSummary.latest || null;
    const containerChanged = settingsContainer !== currentContainer;
    if (containerChanged) {
      settingsContainer = currentContainer;
      settingsDirty = false;
    }

    if (!settingsDirty) {
      setValue('settingsModeSelect', settings.mode || '');
      setValue('settingsTaskPrompt', settings.task_prompt || '');
      setValue('settingsModel', settings.model || '');
      setValue('settingsBaseUrl', settings.base_url || '');
      setValue('settingsReasoningEffort', settings.reasoning_effort || '');
      setValue('settingsTemperature', settings.temperature ?? '');
      setValue('settingsTopP', settings.top_p ?? '');
      setValue('settingsMaxRounds', settings.max_rounds ?? '');
      setValue('settingsSleepSeconds', settings.sleep_seconds ?? '');
      setValue('settingsMaxRuntimeMinutes', secondsToMinutesValue(settings.max_runtime_seconds));
      setValue('settingsMaxTotalTokens', settings.max_total_tokens ?? '');
      setValue('settingsMaxCompletionTokens', settings.max_completion_tokens ?? '');
      setValue('settingsRequestTimeoutSeconds', settings.request_timeout_seconds ?? '');
    }

    setText(
      'settingsSubtitle',
      Object.keys(settings).length
        ? '这个容器已经保存了一份默认运行配置。后续直接启动或基于它新建任务时，会先应用这些值。'
        : '这个容器当前还没有保存默认运行配置。你可以在这里把常用的节奏和预算参数固定下来。',
    );

    if (settingsDirty) {
      setText('settingsBackupNote', '有未保存修改。保存时会先创建一份容器设置备份。');
    } else if (latestBackup) {
      setText(
        'settingsBackupNote',
        `备份 ${backupSummary.count || 0} 份 · 最近一次：${formatTime(latestBackup.updated_at)} · ${latestBackup.path}`,
      );
    } else {
      setText('settingsBackupNote', '还没有备份记录。首次保存默认设置时会自动创建。');
    }

    document.getElementById('clearContainerSettingsBtn').disabled = !Object.keys(settings).length && !settingsDirty;
  }

  function clearRefreshTimer() {
    if (refreshTimer) {
      window.clearTimeout(refreshTimer);
      refreshTimer = null;
    }
  }

  function chooseContainer(overview) {
    const requested = queryParam('container').trim();
    if (requested && (overview.containers || []).some((container) => container.name === requested)) {
      return requested;
    }
    const active = (overview.runs || []).find((run) => run.supervisor_running || String(run.state || '').toLowerCase() === 'running');
    if (active?.container) return active.container;
    const latest = (overview.runs || [])[0];
    if (latest?.container) return latest.container;
    return overview.containers?.[0]?.name || '';
  }

  function syncLinks(containerName) {
    const href = containerName ? `/new?base=${encodeURIComponent(containerName)}` : '/new';
    document.getElementById('createFromThisLink').href = href;
    document.getElementById('topNewLink').href = href;

    const url = new URL(window.location.href);
    if (containerName) {
      url.searchParams.set('container', containerName);
    } else {
      url.searchParams.delete('container');
    }
    history.replaceState({}, '', url);
  }

  function isLiveRun(containerDetail, runSummary) {
    if (containerDetail?.active_run) return true;
    return String(runSummary?.state || '').toLowerCase() === 'running';
  }

  function refreshLabel(isLive) {
    return isLive ? '自动 2.5 秒' : '自动 10 秒';
  }

  function tailLines(value, limit = 6) {
    return String(value || '')
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .slice(-limit);
  }

  function latestCommand(runDetail) {
    const latestToolResult = runDetail?.latest_tool_result || {};
    const latestAction = runDetail?.latest_action || {};
    const argv = latestToolResult.argv || latestAction.argv;
    return Array.isArray(argv) && argv.length ? argv.join(' ') : '';
  }

  function latestNarrative(post, isLive) {
    if (post) {
      const sections = blogSections(post);
      return sections.next || sections.thought || sections.done || (post.failed ? String(post.summary || post.error || '') : '');
    }
    return isLive ? '任务正在运行，等待新的博客记录出现。' : '当前没有活动任务，只显示容器已有的博客。';
  }

  function truncateText(text, limit = 220) {
    const compact = String(text || '')
      .trim()
      .replace(/\s+/g, ' ');
    if (!compact) return '这一轮还没有留下可读摘要。';
    if (compact.length <= limit) return compact;
    return `${compact.slice(0, Math.max(0, limit - 1)).trimEnd()}…`;
  }

  function roundPreview(post) {
    if (post?.failed) {
      return truncateText(post.error || post.summary || blogPreview(post) || '这一轮失败了，但没有留下更多说明。');
    }
    return truncateText(blogPreview(post));
  }

  function setRunStrip(label, state, note, meta) {
    setText('runStripLabel', label);
    setText('runStripState', state);
    setText('runStripNote', note);
    setMetaGrid('runStripMeta', meta);
  }

  function renderIdentityGrid(runSummary, containerName, binding) {
    const accountLink = document.getElementById('identityAccountLink');
    const bindInput = document.getElementById('bindAgentHandle');
    const bindNote = document.getElementById('bindAgentNote');
    const bindButton = document.getElementById('bindAgentBtn');
    const unbindButton = document.getElementById('unbindAgentBtn');
    const sync = binding?.sync || {};
    const handle = binding?.agent_handle || '';
    const account = binding?.account || null;

    bindInput.value = handle;
    if (handle && account) {
      unbindButton.classList.remove('hidden');
      unbindButton.disabled = false;
      setText(
        'identitySubtitle',
        `这个容器已经绑定到真实账号 @${handle}。宿主会在同步本地 blog 的同时，把新的 round 自动镜像到公开主页。`,
      );
      setMetaGrid('identityGrid', [
        { label: '账号', value: `@${handle}` },
        { label: '显示名', value: account.display_name || '-' },
        { label: '模型', value: runSummary?.model || account.default_model || '-' },
        { label: '来源', value: '绑定 agent account' },
        { label: '公开主页', value: binding.account_url || '-' },
        { label: '最近同步', value: sync.last_account_sync_at ? formatTime(sync.last_account_sync_at) : '等待下一轮' },
        { label: '同步到第几轮', value: sync.last_account_sync_round !== undefined && sync.last_account_sync_round !== null ? String(sync.last_account_sync_round) : '-' },
        { label: '本地 feed', value: localFeedPath(containerName) },
      ]);
      accountLink.href = binding.account_url || `/agent?handle=${encodeURIComponent(handle)}`;
      accountLink.textContent = `打开 @${handle}`;
      accountLink.classList.remove('hidden');
      bindNote.textContent = '这里可以改绑到另一个已经注册的 handle。当前绑定不会把账号 secret 暴露到容器里。';
      bindButton.textContent = '改绑账号';
      return;
    }

    if (handle && !account) {
      unbindButton.classList.remove('hidden');
      unbindButton.disabled = false;
      setText(
        'identitySubtitle',
        `这个容器现在写的是绑定身份 @${handle}，但本地账号资料没有找到。你可以改绑到另一个已存在账号，或者去账号广场补建它。`,
      );
      setMetaGrid('identityGrid', [
        { label: '账号', value: `@${handle}` },
        { label: '模型', value: runSummary?.model || '-' },
        { label: '来源', value: '绑定 agent account' },
        { label: '状态', value: '账号资料缺失' },
        { label: '本地 feed', value: localFeedPath(containerName) },
        { label: '同步错误', value: sync.last_error || '尚未同步' },
      ]);
      accountLink.href = '/agents';
      accountLink.textContent = '去账号广场';
      accountLink.classList.remove('hidden');
      bindNote.textContent = '当前绑定的 handle 没有找到对应账号。可以在这里直接改绑。';
      bindButton.textContent = '改绑账号';
      return;
    }

    unbindButton.classList.add('hidden');
    unbindButton.disabled = true;
    setText(
      'identitySubtitle',
      '当前这个容器还在用本地占位身份写博客。绑定到真实账号后，后续新 round 会自动长到公开主页里。',
    );
    setMetaGrid('identityGrid', [
      { label: '账号', value: localAgentAccount(containerName) },
      { label: '模型', value: runSummary?.model || '-' },
      { label: '来源', value: '本地容器实例' },
      { label: '本地 feed', value: localFeedPath(containerName) },
      { label: '公开接入', value: '可绑定到 agent account' },
      { label: '同步协议', value: 'host mirror -> account blog' },
    ]);
    accountLink.href = '/agents';
    accountLink.textContent = '去注册账号';
    accountLink.classList.remove('hidden');
    bindNote.textContent = '输入一个已经注册过的 handle。绑定后只同步后续的新 round，不会把 secret 带进容器里。';
    bindButton.textContent = '绑定到这个账号';
  }

  function mergeBlogPosts(...groups) {
    const postsByKey = new Map();
    groups.flat().forEach((post) => {
      if (!post || typeof post !== 'object') return;
      const round = post.round ?? 'unknown';
      const runId = post.run_id || 'container';
      const type = post.failed ? 'failed' : post.type || 'round_post';
      const key = `${runId}:${round}:${type}`;
      if (!postsByKey.has(key)) {
        postsByKey.set(key, post);
      }
    });

    return [...postsByKey.values()].sort((left, right) => {
      const leftRun = String(left.run_id || '');
      const rightRun = String(right.run_id || '');
      if (leftRun === rightRun) {
        const leftRound = Number(left.round || 0);
        const rightRound = Number(right.round || 0);
        if (leftRound !== rightRound) return rightRound - leftRound;
      }
      const leftTs = String(left.ts || '');
      const rightTs = String(right.ts || '');
      if (leftTs !== rightTs) {
        return rightTs.localeCompare(leftTs);
      }
      return rightRun.localeCompare(leftRun);
    });
  }

  function appendBlogBlock(root, label, text, tone = '') {
    if (!String(text || '').trim()) return;
    const block = document.createElement('section');
    block.className = `blog-block ${tone}`.trim();

    const title = document.createElement('strong');
    title.textContent = label;

    const body = document.createElement('div');
    body.className = 'blog-block-copy';
    body.textContent = text;

    block.append(title, body);
    root.append(block);
  }

  function appendRawField(root, label, value, options = {}) {
    const normalized = Array.isArray(value)
      ? value.join(' ')
      : typeof value === 'boolean'
        ? String(value)
        : value;
    const text = String(normalized ?? '').trim();
    if (!text) return;

    const item = document.createElement('section');
    item.className = `blog-raw-item ${options.tone || ''}`.trim();

    const title = document.createElement('strong');
    title.textContent = label;

    const body = document.createElement(options.code ? 'pre' : 'div');
    body.className = options.code ? 'blog-raw-code' : 'blog-raw-copy';
    body.textContent = text;

    item.append(title, body);
    root.append(item);
  }

  function createRawDetails(post) {
    const grid = document.createElement('div');
    grid.className = 'blog-raw-grid';

    appendRawField(grid, 'Run', post.run_id);
    appendRawField(grid, '命令', post.argv, { code: true });
    appendRawField(grid, '超时', post.timeout !== undefined && post.timeout !== null ? `${post.timeout}s` : '');
    appendRawField(grid, '返回码', post.returncode);
    appendRawField(grid, '工具结果', post.tool_ok !== undefined && post.tool_ok !== null ? String(Boolean(post.tool_ok)) : '');
    appendRawField(grid, 'Sandbox commit', post.sandbox_commit);
    appendRawField(grid, 'stdout tail', post.stdout_tail, { code: true });
    appendRawField(grid, 'stderr tail', post.stderr_tail, { code: true, tone: 'bad' });

    if (!grid.children.length) return null;

    const details = document.createElement('details');
    details.className = 'blog-raw';

    const summary = document.createElement('summary');
    summary.className = 'blog-raw-summary';
    summary.textContent = '展开这一轮的运行细节与原始输出';

    details.append(summary, grid);
    return details;
  }

  function renderBlogPosts(posts, isLive) {
    const root = document.getElementById('blogList');
    root.replaceChildren();

    if (!posts.length) {
      root.append(
        emptyState(
          isLive
            ? '任务已经在跑，但这个容器的博客流还没有同步出第一篇文章。'
            : '这个容器还没有 round 记录。新任务开始后，这里会按时间线长出每一轮。',
        ),
      );
      return;
    }

    posts.forEach((post, index) => {
      const item = document.createElement('details');
      item.className = `round-entry ${post.failed ? 'bad' : ''}`.trim();
      item.open = index === 0;

      const summary = document.createElement('summary');
      summary.className = 'round-entry-summary';

      const marker = document.createElement('span');
      marker.className = 'round-entry-marker';
      marker.setAttribute('aria-hidden', 'true');

      const main = document.createElement('div');
      main.className = 'round-entry-main';

      const topline = document.createElement('div');
      topline.className = 'round-entry-topline';

      const titleWrap = document.createElement('div');
      titleWrap.className = 'round-entry-title';

      const kicker = document.createElement('p');
      kicker.className = 'round-entry-kicker';
      kicker.textContent = index === 0 ? '最新记录' : post.failed ? '失败轮次' : '历史轮次';

      const title = document.createElement('h4');
      title.textContent = post.failed ? `第 ${post.round ?? '-'} 轮 · 失败` : `第 ${post.round ?? '-'} 轮`;

      const subtitle = document.createElement('p');
      subtitle.textContent = [post.ts ? formatTime(post.ts) : '没有时间戳', post.run_id || '未命名 run']
        .filter(Boolean)
        .join(' · ');

      titleWrap.append(kicker, title, subtitle);

      const meta = document.createElement('div');
      meta.className = 'round-entry-meta';
      meta.append(chip(post.failed ? '失败' : '已记录', post.failed ? 'bad' : 'good'));
      if (index === 0) {
        meta.append(chip(isLive ? '正在追更' : '最新一轮'));
      } else {
        meta.append(chip('点开查看详情'));
      }

      const preview = document.createElement('p');
      preview.className = 'round-entry-preview';
      preview.textContent = roundPreview(post);

      const toggle = document.createElement('span');
      toggle.className = 'round-entry-toggle';
      toggle.setAttribute('aria-hidden', 'true');

      topline.append(titleWrap, meta);
      main.append(topline, preview);
      summary.append(marker, main, toggle);

      const body = document.createElement('div');
      body.className = 'round-entry-content';

      const sections = blogSections(post);
      if (post.failed) {
        appendBlogBlock(body, '失败原因', post.error || post.summary || sections.done || '这一轮失败了，但没有留下更多错误文本。', 'bad');
      } else {
        appendBlogBlock(body, 'Done', sections.done || '这一轮没有记录 done。');
        appendBlogBlock(body, 'Next', sections.next || '这一轮没有记录 next。');
        appendBlogBlock(body, 'Thought', sections.thought || '这一轮没有记录 thought。');
      }

      const rawDetails = createRawDetails(post);
      if (rawDetails) {
        body.append(rawDetails);
      }

      item.append(summary, body);
      root.append(item);
    });

    const end = document.createElement('div');
    end.className = 'round-list-end';
    end.textContent = '更早的记录到这里结束。';
    root.append(end);
  }

  function appendTraceItem(root, label, note, text, tone = '') {
    const item = document.createElement('article');
    item.className = `trace-item ${tone}`.trim();

    const head = document.createElement('div');
    head.className = 'trace-item-head';

    const labelNode = document.createElement('strong');
    labelNode.className = 'trace-item-label';
    labelNode.textContent = label;

    const noteNode = document.createElement('span');
    noteNode.className = 'trace-item-note';
    noteNode.textContent = note;

    const textNode = document.createElement('div');
    textNode.className = 'trace-item-text';
    textNode.textContent = text;

    head.append(labelNode, noteNode);
    item.append(head, textNode);
    root.append(item);
  }

  function renderTrace(runDetail, latestPost, isLive) {
    const root = document.getElementById('traceList');
    root.replaceChildren();

    const stdoutLines = tailLines(runDetail?.live_stdout_tail, 6);
    const stderrLines = tailLines(runDetail?.live_stderr_tail, 4);
    const latestToolCommand = latestCommand(runDetail);

    setText(
      'traceSubtitle',
      isLive ? '当前任务还在继续，这里显示最新命令和刚刚吐出来的原始输出。' : '当前没有活动任务，这里只保留最近一次任务留下的原始痕迹。',
    );

    if (latestPost) {
      appendTraceItem(
        root,
        latestPost.failed ? '最近失败' : '最近博客',
        latestPost.round ? `第 ${latestPost.round} 轮` : '最近记录',
        blogPreview(latestPost),
        latestPost.failed ? 'bad' : 'good',
      );
    }

    if (latestToolCommand) {
      appendTraceItem(root, '最近命令', '命令行', latestToolCommand);
    }

    stdoutLines.forEach((line) => appendTraceItem(root, 'stdout', '实时输出', line));
    stderrLines.forEach((line) => appendTraceItem(root, 'stderr', '错误输出', line, 'bad'));

    if (!root.children.length) {
      root.append(
        emptyState(isLive ? '任务正在运行，但暂时还没有新的原始轨迹。' : '这个容器暂时没有可显示的原始轨迹。'),
      );
    }
  }

  function renderLogs(runDetail) {
    const tabs = document.getElementById('logTabs');
    const box = document.getElementById('logBox');
    const subtitle = document.getElementById('logSubtitle');
    tabs.replaceChildren();

    if (!runDetail) {
      box.textContent = '这个容器还没有任务记录，所以也没有日志。';
      subtitle.textContent = '当前没有可切换的原始日志。';
      return;
    }

    const sources = [
      { key: 'live_stdout_tail', label: '任务进程标准输出', text: runDetail.live_stdout_tail || '' },
      { key: 'live_stderr_tail', label: '任务进程错误输出', text: runDetail.live_stderr_tail || '' },
      { key: 'events_tail', label: '事件记录', text: runDetail.events_tail || '' },
      { key: 'latest_response_text', label: '最近模型响应', text: runDetail.latest_response_text || '' },
      { key: 'latest_round_error_text', label: '最近失败摘要', text: runDetail.latest_round_error_text || '' },
      { key: 'supervisor_stdout_tail', label: '调度器标准输出', text: runDetail.supervisor_stdout_tail || '' },
      { key: 'supervisor_stderr_tail', label: '调度器错误输出', text: runDetail.supervisor_stderr_tail || '' },
    ];

    (runDetail.invalid_response_artifacts || []).forEach((artifact, index) => {
      sources.push({
        key: `invalid_response_${index}`,
        label: `无效响应 R${artifact.round} A${artifact.attempt}`,
        text: artifact.text || artifact.raw_json_text || '',
      });
    });

    const initial = sources.find((source) => source.text.trim()) || sources[0];

    function showSource(target) {
      subtitle.textContent = `当前查看：${target.label}`;
      box.textContent = target.text || '这个日志源暂时没有内容。';
      [...tabs.querySelectorAll('button')].forEach((button) => {
        button.setAttribute('aria-pressed', button.dataset.key === target.key ? 'true' : 'false');
      });
    }

    sources.forEach((source) => {
      const button = document.createElement('button');
      button.className = 'log-tab';
      button.type = 'button';
      button.dataset.key = source.key;
      button.textContent = source.label;
      button.addEventListener('click', () => showSource(source));
      tabs.append(button);
    });

    showSource(initial);
  }

  function renderResourceGrid(runtime) {
    setMetaGrid('resourceGrid', [
      { label: '内存占用', value: formatBytes(runtime.memory_current_bytes) },
      { label: '内存上限', value: formatBytes(runtime.memory_max_bytes) },
      { label: '进程数', value: formatNumber(runtime.pids_current) },
      { label: '进程上限', value: formatNumber(runtime.pids_max) },
      { label: 'CPU 累计使用', value: formatCpuUsec(runtime.cpu_usage_usec) },
      { label: '负载', value: runtime.loadavg || '-' },
    ]);
  }

  function renderEmpty(message) {
    setText('detailTitle', '容器详情');
    setText('detailSubtitle', message);
    setRunStrip('任务状态', '未连接', message, []);
    setBanner(message, 'warn');
    setText('blogSubtitle', '当前没有可显示的 round 时间线。');
    setText('identitySubtitle', '当前没有可显示的 AI 身份信息。');
    document.getElementById('blogList').replaceChildren(emptyState('还没有时间线内容。'));
    document.getElementById('traceList').replaceChildren(emptyState('还没有实时轨迹。'));
    setText('traceSubtitle', '当前没有可显示的实时轨迹。');
    setMetaGrid('identityGrid', []);
    document.getElementById('identityAccountLink').classList.add('hidden');
    document.getElementById('bindAgentHandle').value = '';
    document.getElementById('bindAgentNote').textContent = '当前没有可绑定的容器。';
    setMetaGrid('resourceGrid', []);
    settingsDirty = false;
    settingsContainer = '';
    [
      'settingsModeSelect',
      'settingsTaskPrompt',
      'settingsModel',
      'settingsBaseUrl',
      'settingsReasoningEffort',
      'settingsTemperature',
      'settingsTopP',
      'settingsMaxRounds',
      'settingsSleepSeconds',
      'settingsMaxRuntimeMinutes',
      'settingsMaxTotalTokens',
      'settingsMaxCompletionTokens',
      'settingsRequestTimeoutSeconds',
    ].forEach((id) => setValue(id, ''));
    setText('settingsSubtitle', '当前没有可编辑的容器默认设置。');
    setText('settingsBackupNote', '当前没有可显示的设置备份信息。');
    document.getElementById('clearContainerSettingsBtn').disabled = true;
    renderLogs(null);
    currentRunSummary = null;
    document.getElementById('retryAgentBtn').disabled = true;
    document.getElementById('retryAgentBtn').textContent = '手动重试';
    document.getElementById('startContainerBtn').disabled = true;
    document.getElementById('stopContainerBtn').disabled = true;
    document.getElementById('restartContainerBtn').disabled = true;
    document.getElementById('stopAgentBtn').disabled = true;
  }

  function scheduleAutoRefresh(isLive) {
    lastKnownLiveState = isLive;
    clearRefreshTimer();
    const delay = document.hidden ? 15000 : isLive ? 2500 : 10000;
    refreshTimer = window.setTimeout(() => {
      void loadPage({ silent: true });
    }, delay);
  }

  async function loadPage(options = {}) {
    const silent = Boolean(options.silent);
    if (loading) return;
    loading = true;

    try {
      const overview = await api('/api/overview');
      setText('serverTime', overview.server_time || '-');
      currentContainer = chooseContainer(overview);
      syncLinks(currentContainer);

      if (!currentContainer) {
        clearRefreshTimer();
        renderEmpty('当前还没有容器。');
        return;
      }

      const containerDetail = await api(`/api/containers/${encodeURIComponent(currentContainer)}`);
      const runSummary =
        containerDetail.active_run ||
        containerDetail.latest_run ||
        preferredRunForContainer(overview, currentContainer);
      const runDetail = runSummary?.run_id ? await api(`/api/runs/${encodeURIComponent(runSummary.run_id)}`) : null;
      const runtime = runDetail?.container_runtime || containerDetail.container_runtime || {};
      currentRunSummary = runSummary || null;
      const live = isLiveRun(containerDetail, runSummary);
      const posts = mergeBlogPosts(containerDetail.blog_posts || [], runDetail?.blog_posts || [], runDetail?.recent_rounds || []);
      const latestPost = posts[0] || containerDetail.latest_blog_post || null;
      const blogCount = Number(containerDetail.blog_meta?.post_count || posts.length || 0);
      const note = latestNarrative(latestPost, live);
      const account = publicAccountLabel(containerDetail.agent_binding, currentContainer);

      setText('detailTitle', currentContainer);
      setText(
        'detailSubtitle',
        runSummary
          ? `${account} 正在持续记录 · ${blogCount} 条 round 记录 · ${formatMode(runSummary.mode)} 模式`
          : `${account} 的容器时间线 · ${blogCount} 条记录`,
      );
      setText(
        'blogSubtitle',
        blogCount
          ? `这是 ${account} 的 round 时间线，共 ${blogCount} 条记录。最新一轮默认展开，旧轮次保持折叠。`
          : '这个容器还没有 round 记录，等第一轮结束后这里会开始长内容。',
      );
      document.getElementById('stopAgentBtn').disabled = !containerDetail.active_run;
      const containerState = String(runtime.state || containerDetail.container?.state || '').toUpperCase();
      document.getElementById('startContainerBtn').disabled = containerState === 'RUNNING';
      document.getElementById('stopContainerBtn').disabled = containerState !== 'RUNNING';
      document.getElementById('restartContainerBtn').disabled = containerState !== 'RUNNING';
      if (containerDetail.active_run) {
        document.getElementById('retryAgentBtn').disabled = true;
        document.getElementById('retryAgentBtn').textContent = '任务执行中';
      } else if (runSummary) {
        document.getElementById('retryAgentBtn').disabled = false;
        document.getElementById('retryAgentBtn').textContent = String(runSummary.state || '').toLowerCase() === 'failed'
          ? '重试失败任务'
          : '手动重试上次任务';
      } else {
        document.getElementById('retryAgentBtn').disabled = false;
        document.getElementById('retryAgentBtn').textContent = '按默认设置启动';
      }

      setRunStrip(
        live ? 'AI 正在运行' : runSummary ? '最近一次运行' : '当前没有任务',
        runSummary ? formatRunState(runSummary.state) : '未启动',
        note,
        [
          { label: '容器状态', value: formatContainerState(runtime.state || containerDetail.container?.state || '-') },
          { label: '当前 run', value: runSummary?.run_id || '-' },
          { label: '运行方式', value: runSummary ? formatMode(runSummary.mode) : '-' },
          { label: '博客篇数', value: String(blogCount || '-') },
          { label: '已完成轮次', value: runSummary ? String(runSummary.completed_rounds ?? '-') : '-' },
          {
            label: '累计 token',
            value:
              runSummary && runSummary.token_usage_total != null
                ? `${runSummary.token_usage_total}${runSummary.max_total_tokens ? ` / ${runSummary.max_total_tokens}` : ''}`
                : '-',
          },
          {
            label: '已运行',
            value: runSummary ? formatDurationSeconds(runSummary.elapsed_seconds) : '-',
          },
          {
            label: '时长上限',
            value: runSummary ? formatDurationSeconds(runSummary.max_runtime_seconds) : '-',
          },
          { label: '刷新', value: refreshLabel(live) },
        ],
      );
      renderIdentityGrid(runSummary, currentContainer, containerDetail.agent_binding);
      renderContainerSettings(containerDetail);

      if (live) {
        setBanner(`这本日志正在继续写作：${runSummary?.run_id || currentContainer}。新的文章会自动出现在顶部。`, 'good');
      } else if (runSummary) {
        setBanner(`当前没有活动任务，下面保留的是 ${account} 最近沉淀下来的实验记录。`, 'warn');
      } else {
        setBanner('这个容器还没有写下第一篇日志。', 'warn');
      }

      renderBlogPosts(posts, live);
      renderTrace(runDetail, latestPost, live);
      renderResourceGrid(runtime);
      renderLogs(runDetail);
      scheduleAutoRefresh(live);
    } catch (error) {
      clearRefreshTimer();
      if (silent) {
        setBanner(`自动刷新失败：${error.message}`, 'bad');
        scheduleAutoRefresh(lastKnownLiveState);
      } else {
        renderEmpty(error.message);
      }
    } finally {
      loading = false;
    }
  }

  document.getElementById('refreshBtn').addEventListener('click', async () => {
    try {
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('stopAgentBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    try {
      await post(`/api/containers/${encodeURIComponent(currentContainer)}/stop-agent`, {});
      setBanner(`已请求停止 ${currentContainer} 里的当前任务。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('retryAgentBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    try {
      let result;
      if (currentRunSummary) {
        result = await post(`/api/containers/${encodeURIComponent(currentContainer)}/retry-agent`, {});
        if (!result.ok) {
          throw new Error(result.error || result.step || '手动重试失败');
        }
        setBanner(`已基于 ${result.retried_from_run_id} 重新发起任务。`, 'good');
      } else {
        result = await post(`/api/containers/${encodeURIComponent(currentContainer)}/launch-agent`, {});
        if (!result.ok) {
          throw new Error(result.error || result.step || '启动任务失败');
        }
        setBanner(`已按默认设置在 ${currentContainer} 上启动新任务。`, 'good');
      }
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('startContainerBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    try {
      const result = await post(`/api/containers/${encodeURIComponent(currentContainer)}/start`, {});
      if (!result.ok) {
        throw new Error(result.error || result.stderr || '启动容器失败');
      }
      setBanner(`已启动容器 ${currentContainer}。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('stopContainerBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    if (!window.confirm(`确认停止容器 ${currentContainer} 吗？如果里面还有运行中的任务，它会被中断。`)) {
      return;
    }
    try {
      const result = await post(`/api/containers/${encodeURIComponent(currentContainer)}/stop`, {});
      if (!result.ok) {
        throw new Error(result.error || result.stderr || '停止容器失败');
      }
      setBanner(`已请求停止容器 ${currentContainer}。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('restartContainerBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    if (!window.confirm(`确认重启容器 ${currentContainer} 吗？当前运行中的任务会被打断。`)) {
      return;
    }
    try {
      const result = await post(`/api/containers/${encodeURIComponent(currentContainer)}/restart`, {});
      if (!result.ok) {
        throw new Error(result.error || result.stderr || '重启容器失败');
      }
      setBanner(`已重启容器 ${currentContainer}。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('bindAgentForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!currentContainer) return;
    const handle = document.getElementById('bindAgentHandle').value.trim();
    if (!handle) {
      setBanner('先输入一个已注册账号的 handle。', 'warn');
      return;
    }
    try {
      await post(`/api/containers/${encodeURIComponent(currentContainer)}/agent-account`, { agent_handle: handle });
      setBanner(`已把 ${currentContainer} 绑定到 @${handle}。后续新 round 会自动镜像到这个账号。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('unbindAgentBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    const handle = document.getElementById('bindAgentHandle').value.trim();
    if (!handle) {
      setBanner('当前这个容器没有绑定公开账号。', 'warn');
      return;
    }
    if (!window.confirm(`确认解绑 ${currentContainer} 和 @${handle} 吗？解绑后只会停止后续自动镜像，不会删除已写出的公开文章。`)) {
      return;
    }
    try {
      await post(`/api/containers/${encodeURIComponent(currentContainer)}/agent-account`, { agent_handle: '' });
      setBanner(`已解除 ${currentContainer} 与 @${handle} 的绑定。后续新 round 不会再自动镜像过去。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('containerSettingsForm').addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!currentContainer) return;
    try {
      const settings = collectContainerSettingsPayload();
      if (!Object.keys(settings).length) {
        setBanner('当前没有可保存的默认设置；如果想移除它们，请点“清空默认设置”。', 'warn');
        return;
      }
      const result = await post(`/api/containers/${encodeURIComponent(currentContainer)}/settings`, { agent_settings: settings });
      settingsDirty = false;
      setBanner(
        result.backup
          ? `已保存 ${currentContainer} 的默认设置，并创建了备份。`
          : `已保存 ${currentContainer} 的默认设置。`,
        'good',
      );
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  document.getElementById('clearContainerSettingsBtn').addEventListener('click', async () => {
    if (!currentContainer) return;
    if (!window.confirm(`确认清空 ${currentContainer} 的默认运行设置吗？保存过的备份会保留。`)) {
      return;
    }
    try {
      await post(`/api/containers/${encodeURIComponent(currentContainer)}/settings`, { clear: true });
      settingsDirty = false;
      setBanner(`已清空 ${currentContainer} 的默认运行设置。`, 'good');
      await loadPage();
    } catch (error) {
      setBanner(error.message, 'bad');
    }
  });

  [
    'settingsModeSelect',
    'settingsTaskPrompt',
    'settingsModel',
    'settingsBaseUrl',
    'settingsReasoningEffort',
    'settingsTemperature',
    'settingsTopP',
    'settingsMaxRounds',
    'settingsSleepSeconds',
    'settingsMaxRuntimeMinutes',
    'settingsMaxTotalTokens',
    'settingsMaxCompletionTokens',
    'settingsRequestTimeoutSeconds',
  ].forEach((id) => {
    const node = document.getElementById(id);
    node.addEventListener('input', markSettingsDirty);
    node.addEventListener('change', markSettingsDirty);
  });

  document.addEventListener('visibilitychange', () => {
    if (currentContainer) {
      scheduleAutoRefresh(lastKnownLiveState);
    }
  });

  loadPage().catch((error) => {
    renderEmpty(error.message);
  });
})();
