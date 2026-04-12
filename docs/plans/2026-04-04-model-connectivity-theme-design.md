# Marathon Core Model Connectivity And Theme Toggle Design

**Goal**

在 `Marathon Core` 的 operator UI 里补上模型连通性测试、完整模型参数保存复用，以及可见的明暗模式图标切换。

## Why

当前新建任务页已经能输入模型、Base URL 和 API Key，也有“保存当前配置”按钮，但仍然缺三件关键能力：

- 输入完模型后，不能在启动任务前直接测试联通性
- 保存的模型配置没有完整覆盖所有高级参数，也没有在页面上明确表现“后续会自动复用”
- 主题目前只跟随系统 `prefers-color-scheme`，没有显式的亮/暗切换图标

## Product Shape

本次改动只作用于 `Marathon Core` operator UI。

### 1. 模型连通性测试

在新建任务页模型配置卡片中增加“测试连通性”按钮。

行为：

- 读取当前表单中的模型配置，不要求先保存
- 直接向所填 `base_url` 发起一个最小化 chat completion 探针
- 返回：
  - 请求是否成功
  - 延迟
  - 响应模型名
  - 一个很短的响应预览
  - token usage（如果提供）

失败时返回清晰错误，而不是静默失败。

### 2. 模型配置保存复用

“保存当前配置”继续沿用现有 model profile 机制，但要覆盖完整高级参数：

- `reasoning_effort`
- `temperature`
- `top_p`
- `max_completion_tokens`
- `request_timeout_seconds`
- `request_max_attempts`
- `request_retry_delay_seconds`
- `extra_body`

页面重新打开时自动把已保存的默认配置回填到表单。

### 3. 明暗模式图标切换

增加一个全局主题切换按钮，显示在 operator UI 顶栏导航区域。

规则：

- 默认仍可从系统主题推导
- 用户点击后进入显式 `light` / `dark` 模式
- 选择持久化到 `localStorage`
- 图标和标签要明确反映“切到哪种模式”

## Boundaries

不做：

- 多 profile 管理器
- provider 专用健康检查
- public site 主题切换
- design-lab 页面主题统一
