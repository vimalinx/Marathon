(function () {
  const AGENT_CREDENTIAL_PREFIX = 'marathon.agent.credentials:';
  const THEME_PREFERENCE_KEY = 'marathon.ui.theme';

  function getStoredThemePreference() {
    if (!window.localStorage) return '';
    return String(window.localStorage.getItem(THEME_PREFERENCE_KEY) || '').trim();
  }

  function preferredSystemTheme() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function activeTheme() {
    const stored = getStoredThemePreference();
    if (stored === 'light' || stored === 'dark') return stored;
    return preferredSystemTheme();
  }

  function applyTheme(theme, { persist = true } = {}) {
    const resolved = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = resolved;
    if (persist && window.localStorage) {
      window.localStorage.setItem(THEME_PREFERENCE_KEY, resolved);
    }
    return resolved;
  }

  function toggleTheme() {
    const nextTheme = activeTheme() === 'dark' ? 'light' : 'dark';
    return applyTheme(nextTheme);
  }

  function themeButtonLabel(theme) {
    if (theme === 'dark') {
      return { icon: '☀', label: '浅色' };
    }
    return { icon: '☾', label: '深色' };
  }

  function updateThemeToggleButton(button) {
    if (!button) return;
    const theme = activeTheme();
    const next = themeButtonLabel(theme);
    button.textContent = `${next.icon} ${next.label}`;
    button.setAttribute('aria-label', `切换到${next.label}模式`);
    button.dataset.theme = theme;
  }

  function ensureThemeToggle() {
    const nav = document.querySelector('.container-blog-nav, .topbar-links');
    if (!nav) return;
    let button = document.getElementById('themeToggleBtn');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.id = 'themeToggleBtn';
      button.className = 'nav-link theme-toggle';
      button.addEventListener('click', () => {
        toggleTheme();
        updateThemeToggleButton(button);
      });
      nav.append(button);
    }
    updateThemeToggleButton(button);
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;');
  }

  async function api(path, options = {}) {
    const { headers: optionHeaders = {}, ...restOptions } = options;
    const headers = {
      'Content-Type': 'application/json',
      ...optionHeaders,
    };
    const response = await fetch(path, {
      ...restOptions,
      headers,
    });
    const data = await response.json().catch(() => ({ ok: false, error: 'Invalid JSON response' }));
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  async function post(path, payload, options = {}) {
    return api(path, {
      method: 'POST',
      body: JSON.stringify(payload || {}),
      ...options,
    });
  }

  function queryParam(name) {
    return new URLSearchParams(window.location.search).get(name) || '';
  }

  function formatMode(mode) {
    return String(mode || '').toLowerCase() === 'freeplay' ? '自由探索' : '按任务执行';
  }

  function formatRunState(state) {
    const value = String(state || '').toLowerCase();
    if (value === 'running') return '运行中';
    if (value === 'completed') return '已完成';
    if (value === 'stopped') return '已停止';
    if (value === 'failed') return '失败';
    if (value === 'interrupted') return '已中断';
    if (value === 'unknown' || !value) return '未知';
    return String(state);
  }

  function formatContainerState(state) {
    const value = String(state || '').toUpperCase();
    if (value === 'RUNNING') return '运行中';
    if (value === 'STOPPED') return '已停止';
    if (value === 'FROZEN') return '已冻结';
    if (value === 'ABORTING') return '停止中';
    if (value === 'UNKNOWN' || !value) return '未知';
    return String(state);
  }

  function stateTone(state) {
    const value = String(state || '').toLowerCase();
    if (value === 'running') return 'good';
    if (value === 'completed' || value === 'stopped') return 'warn';
    if (value === 'failed' || value === 'interrupted' || value === 'unknown') return 'bad';
    return '';
  }

  function containerStateTone(state) {
    const value = String(state || '').toUpperCase();
    if (value === 'RUNNING') return 'good';
    if (value === 'STOPPED' || value === 'FROZEN') return 'warn';
    if (value === 'ABORTING' || value === 'ERROR' || value === 'UNKNOWN') return 'bad';
    return '';
  }

  function latestRunForContainer(overview, containerName) {
    return (overview?.runs || []).find((run) => run.container === containerName) || null;
  }

  function activeRunForContainer(overview, containerName) {
    return (overview?.runs || []).find(
      (run) => run.container === containerName && (run.supervisor_running || String(run.state || '').toLowerCase() === 'running'),
    ) || null;
  }

  function preferredRunForContainer(overview, containerName) {
    return activeRunForContainer(overview, containerName) || latestRunForContainer(overview, containerName);
  }

  function previewText(...candidates) {
    for (const candidate of candidates) {
      const compact =
        candidate && typeof candidate === 'object' && !Array.isArray(candidate)
          ? String(
              candidate.done ||
                candidate.next ||
                candidate.thought ||
                candidate.summary ||
                candidate.error ||
                '',
            )
              .trim()
              .replace(/\s+/g, ' ')
          : String(candidate || '').trim().replace(/\s+/g, ' ');
      if (compact) {
        return compact;
      }
    }
    return '还没有最近输出。';
  }

  function blogSections(post) {
    const value = post && typeof post === 'object' && !Array.isArray(post) ? post : {};
    return {
      done: String(value.done || value.summary || '').trim(),
      next: String(value.next || '').trim(),
      thought: String(value.thought || '').trim(),
      error: String(value.error || '').trim(),
    };
  }

  function blogPreview(post) {
    const sections = blogSections(post);
    return previewText(sections.done, sections.next, sections.thought, sections.error);
  }

  function formatTime(value) {
    const text = String(value || '').trim();
    if (!text) return '-';
    return text
      .replace('T', ' ')
      .replace(/([+-]\d{2})(\d{2})$/, '$1:$2');
  }

  function formatBytes(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
      return '-';
    }
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let current = value;
    let index = 0;
    while (current >= 1024 && index < units.length - 1) {
      current /= 1024;
      index += 1;
    }
    const digits = current >= 100 || index === 0 ? 0 : current >= 10 ? 1 : 2;
    return `${current.toFixed(digits)} ${units[index]}`;
  }

  function formatNumber(value) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      return '-';
    }
    return String(value);
  }

  function formatCpuUsec(value) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) {
      return '-';
    }
    if (value >= 1000000) {
      return `${(value / 1000000).toFixed(1)} s`;
    }
    if (value >= 1000) {
      return `${(value / 1000).toFixed(1)} ms`;
    }
    return `${value} µs`;
  }

  function agentCredentialKey(handle) {
    return `${AGENT_CREDENTIAL_PREFIX}${String(handle || '').trim()}`;
  }

  function getStoredAgentCredentials(handle) {
    const key = agentCredentialKey(handle);
    if (!String(handle || '').trim() || !window.localStorage) {
      return { authToken: '', instanceId: '' };
    }
    try {
      const payload = JSON.parse(window.localStorage.getItem(key) || '{}');
      return {
        authToken: String(payload.authToken || '').trim(),
        instanceId: String(payload.instanceId || '').trim(),
      };
    } catch (error) {
      return { authToken: '', instanceId: '' };
    }
  }

  function setStoredAgentCredentials(handle, credentials) {
    const trimmedHandle = String(handle || '').trim();
    if (!trimmedHandle || !window.localStorage) {
      return;
    }
    const authToken = String(credentials?.authToken || '').trim();
    const instanceId = String(credentials?.instanceId || '').trim();
    window.localStorage.setItem(
      agentCredentialKey(trimmedHandle),
      JSON.stringify({ authToken, instanceId, savedAt: new Date().toISOString() }),
    );
  }

  window.MarathonUi = {
    api,
    post,
    escapeHtml,
    queryParam,
    formatMode,
    formatRunState,
    formatContainerState,
    stateTone,
    containerStateTone,
    latestRunForContainer,
    activeRunForContainer,
    preferredRunForContainer,
    previewText,
    blogSections,
    blogPreview,
    formatTime,
    formatBytes,
    formatNumber,
    formatCpuUsec,
    getStoredAgentCredentials,
    setStoredAgentCredentials,
    applyTheme,
    activeTheme,
  };

  applyTheme(activeTheme(), { persist: false });
  ensureThemeToggle();
})();
