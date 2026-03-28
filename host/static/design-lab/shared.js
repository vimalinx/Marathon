(function () {
  "use strict";

  const EMPTY_MESSAGES = Object.freeze({
    noContext: "还没有选中实验",
    noSelfModification: "未观察到自我修改",
    noOutput: "还没有最近输出",
  });

  const ERROR_MESSAGES = Object.freeze({
    modelFailure: "读取模型信息失败",
    actionFailure: "操作失败",
  });

  async function fetchJson(url) {
    const response = await fetch(url, {
      headers: {
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error("请求失败：" + response.status);
    }
    return response.json();
  }

  function formatCategory(category) {
    if (category === "prompt_source") {
      return "提示词";
    }
    if (category === "tool_source") {
      return "工具";
    }
    if (category === "loop_source") {
      return "循环逻辑";
    }
    return category || "无";
  }

  function formatState(state) {
    const value = String(state || "").trim();
    const lower = value.toLowerCase();
    const upper = value.toUpperCase();
    if (lower === "running" || upper === "RUNNING") return "运行中";
    if (lower === "completed") return "已完成";
    if (lower === "stopped" || upper === "STOPPED") return "已停止";
    if (lower === "failed") return "失败";
    if (lower === "interrupted") return "已中断";
    if (upper === "FROZEN") return "已冻结";
    if (upper === "ABORTING") return "停止中";
    if (lower === "unknown" || upper === "UNKNOWN" || !value) return "未知";
    return value;
  }

  function formatRoundOutcome(round) {
    return round && round.failed ? "失败" : "完成";
  }

  function getSelectedContext() {
    const searchParams = new URLSearchParams(window.location.search);
    const runIdInput = document.querySelector("[data-context-run-id]");
    const containerInput = document.querySelector("[data-context-container]");
    const runId = (runIdInput && runIdInput.value.trim()) || searchParams.get("run_id") || "";
    const container = (containerInput && containerInput.value.trim()) || searchParams.get("container") || "";
    return { runId, container };
  }

  function buildVariantHref(page, context) {
    const params = new URLSearchParams();
    if (context.runId) {
      params.set("run_id", context.runId);
    }
    if (context.container) {
      params.set("container", context.container);
    }
    const query = params.toString();
    return query ? page + "?" + query : page;
  }

  async function fetchOverview() {
    return fetchJson("/api/overview");
  }

  async function fetchRunDetail(runId) {
    return fetchJson("/api/runs/" + encodeURIComponent(runId));
  }

  async function fetchContainerDetail(container) {
    return fetchJson("/api/containers/" + encodeURIComponent(container));
  }

  function buildStateBlock(title, copy) {
    const wrapper = document.createElement("div");
    const heading = document.createElement("strong");
    const detail = document.createElement("p");
    wrapper.className = "state-block";
    heading.textContent = title;
    detail.className = "muted";
    detail.textContent = copy;
    wrapper.append(heading, detail);
    return wrapper;
  }

  function renderEmptyState(target, title, copy) {
    if (!target) {
      return;
    }
    target.replaceChildren(buildStateBlock(title, copy));
  }

  function renderErrorState(target, title, error) {
    const message = error instanceof Error ? error.message : String(error || "Unknown error");
    renderEmptyState(target, title, message);
  }

  function updateVariantLinks() {
    const context = getSelectedContext();
    const links = document.querySelectorAll("[data-variant-page]");
    links.forEach(function (link) {
      const page = link.getAttribute("data-variant-page");
      if (!page) {
        return;
      }
      link.setAttribute("href", buildVariantHref(page, context));
    });
  }

  function syncContextInputs() {
    const searchParams = new URLSearchParams(window.location.search);
    const runIdInput = document.querySelector("[data-context-run-id]");
    const containerInput = document.querySelector("[data-context-container]");
    if (runIdInput && !runIdInput.value) {
      runIdInput.value = searchParams.get("run_id") || "";
    }
    if (containerInput && !containerInput.value) {
      containerInput.value = searchParams.get("container") || "";
    }
  }

  async function hydrateOverview() {
    const summaryNode = document.querySelector("[data-overview-summary]");
    if (!summaryNode) {
      return;
    }

    try {
      const overview = await fetchOverview();
      const context = getSelectedContext();
      const bits = [];
      if (context.runId) {
        try {
          const detail = await fetchRunDetail(context.runId);
          const state = detail.status && detail.status.state ? formatState(detail.status.state) : "未知";
          bits.push("运行 " + context.runId + " · " + state);
        } catch (error) {
          bits.push("运行 " + context.runId + " · 暂不可用");
        }
      }
      if (context.container) {
        try {
          const detail = await fetchContainerDetail(context.container);
          const runtime = detail.container_runtime || detail.runtime || {};
          const state = runtime.state ? formatState(runtime.state) : "未知";
          bits.push("容器 " + context.container + " · " + state);
        } catch (error) {
          bits.push("容器 " + context.container + " · 暂不可用");
        }
      }
      if (!bits.length) {
        const runCount = Array.isArray(overview.runs) ? overview.runs.length : 0;
        bits.push(EMPTY_MESSAGES.noContext + "。当前有 " + runCount + " 条运行记录。");
      }
      summaryNode.textContent = bits.join(" ");
    } catch (error) {
      renderErrorState(summaryNode, ERROR_MESSAGES.modelFailure, error);
    }
  }

  function renderNoContextState(target, copy) {
    renderEmptyState(
      target,
      EMPTY_MESSAGES.noContext,
      copy || "先在首页选一个运行或容器。"
    );
  }

  function renderNoSelfModificationState(target, copy) {
    renderEmptyState(
      target,
      EMPTY_MESSAGES.noSelfModification,
      copy || "当前还没有受追踪的变化。"
    );
  }

  function renderModelFailureState(target, error) {
    renderErrorState(target, ERROR_MESSAGES.modelFailure, error);
  }

  function renderActionFailureState(target, error) {
    renderErrorState(target, ERROR_MESSAGES.actionFailure, error);
  }

  function wireContextForm() {
    const form = document.querySelector("[data-context-form]");
    if (!form) {
      return;
    }
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const context = getSelectedContext();
      const nextSearch = new URLSearchParams();
      if (context.runId) {
        nextSearch.set("run_id", context.runId);
      }
      if (context.container) {
        nextSearch.set("container", context.container);
      }
      const nextUrl = nextSearch.toString() ? window.location.pathname + "?" + nextSearch.toString() : window.location.pathname;
      window.history.replaceState({}, "", nextUrl);
      updateVariantLinks();
      hydrateOverview();
    });
  }

  function initDesignLabShared() {
    syncContextInputs();
    updateVariantLinks();
    wireContextForm();
    hydrateOverview();
  }

  window.DesignLabShared = {
    EMPTY_MESSAGES: EMPTY_MESSAGES,
    ERROR_MESSAGES: ERROR_MESSAGES,
    buildStateBlock: buildStateBlock,
    getSelectedContext: getSelectedContext,
    buildVariantHref: buildVariantHref,
    fetchOverview: fetchOverview,
    fetchRunDetail: fetchRunDetail,
    fetchContainerDetail: fetchContainerDetail,
    renderEmptyState: renderEmptyState,
    renderErrorState: renderErrorState,
    renderNoContextState: renderNoContextState,
    renderNoSelfModificationState: renderNoSelfModificationState,
    renderModelFailureState: renderModelFailureState,
    renderActionFailureState: renderActionFailureState,
    formatCategory: formatCategory,
    formatState: formatState,
    formatRoundOutcome: formatRoundOutcome,
    initDesignLabShared: initDesignLabShared,
  };

  document.addEventListener("DOMContentLoaded", initDesignLabShared);
})();
