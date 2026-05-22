# Design Document — Phase 3 系统性增强

## 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0 | 2026-05-21 | 初始设计 |

---

## Overview

Phase 3 包含五项系统性增强：双向穿透、LLM 规则类引擎接入、压力测试、暗色模式、Storybook。这些功能跨度较大，建议按独立子项目并行推进（F1/F2 有后端依赖需串行，F3/F4/F5 可并行）。

---

## F1 双向穿透 — 架构设计

### 穿透方向定义

```
当前已有（↓ 下钻）：
  TB → AUX → Ledger → AuxLedger → 底稿

新增（↑ 上钻）：
  附注 cell → 报表行 → TB 科目 → (可继续 ↓ 下钻到明细账)
```

### 后端 API

```python
# GET /api/projects/{pid}/notes/trace-source?cell_id={cell_id}
# 追溯附注 cell 的数据来源
# Response:
{
  "source_type": "report_line",  # report_line | tb_account | formula
  "report_line": {"line_code": "BS-001", "item_name": "货币资金", "amount": 5000000},
  "tb_accounts": [
    {"code": "1001", "name": "库存现金", "closing_balance": 50000},
    {"code": "1002", "name": "银行存款", "closing_balance": 4950000}
  ]
}

# GET /api/projects/{pid}/reports/line-composition?line_code={line_code}
# 查询报表行的构成科目
# Response:
{
  "line_code": "BS-001",
  "item_name": "货币资金",
  "total_amount": 5000000,
  "accounts": [
    {"code": "1001", "name": "库存现金", "closing_balance": 50000, "pct": 1.0},
    {"code": "1002", "name": "银行存款", "closing_balance": 4950000, "pct": 99.0}
  ]
}
```

### 前端交互

```
┌─────────────────────────────────────────────────┐
│ DisclosureEditor.vue                             │
│   cell (auto mode) → @click → TraceSourcePopover│
│     ├─ 来源报表行：货币资金 ¥5,000,000          │
│     ├─ 构成科目：                                │
│     │   1001 库存现金      ¥50,000    (1%)      │
│     │   1002 银行存款      ¥4,950,000 (99%)     │
│     └─ [跳转到试算表 →]                          │
└─────────────────────────────────────────────────┘
```

### ADR-F1: Popover vs Dialog

**决策**：使用 el-popover（轻量弹出层），不用 el-dialog。

**理由**：追溯信息量小（1 个报表行 + 2-5 个科目），popover 更轻量且不遮挡编辑器内容。

---

## F2 LLM 接入 — 架构设计

### 统一 LLM 调用封装

```python
# backend/app/services/llm_service.py
class LLMService:
    """统一 LLM 调用封装，所有 stub 引擎通过此服务调用 vLLM"""

    BASE_URL = settings.VLLM_BASE_URL  # http://localhost:8100/v1
    MODEL = settings.VLLM_MODEL_NAME   # Qwen3.5-27B-NVFP4

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: float = 30.0,
    ) -> LLMResponse:
        """调用 vLLM OpenAI 兼容 API"""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self.BASE_URL}/chat/completions", json={
                    "model": self.MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                })
                resp.raise_for_status()
                data = resp.json()
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    tokens_used=data["usage"]["total_tokens"],
                    is_stub=False,
                )
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
            return LLMResponse(content=None, tokens_used=0, is_stub=True, error=str(e))
```

### K 费用异常分析接入

```python
# wp_k_expense_analysis.py 改造
async def analyze_expense_anomaly(db, wp_id, project_id):
    # 1. 规则引擎执行（已有逻辑，不变）
    rule_result = _execute_yoy_analysis(...)

    # 2. LLM 生成解释（新增）
    if settings.WP_AI_SERVICE_ENABLED:
        llm = LLMService()
        prompt = _build_expense_prompt(rule_result)
        llm_response = await llm.generate(
            system_prompt="你是一位资深审计师，请基于以下费用异常分析数据，给出专业的审计判断。",
            user_prompt=prompt,
        )
        if not llm_response.is_stub:
            rule_result["ai_explanation"] = llm_response.content
            rule_result["is_llm_stub"] = False
            return rule_result

    # 3. 降级：返回规则结果 + stub 标记
    rule_result["is_llm_stub"] = True
    rule_result["ai_explanation"] = "AI 分析功能待接入，当前显示规则引擎结果。"
    return rule_result
```

---

## F3 压力测试 — 架构设计

### 压测工具选型

**决策**：使用 Locust（Python 生态，与后端技术栈一致）。

### 压测脚本结构

```python
# tests/load/locustfile.py
class AuditUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """登录获取 token"""
        resp = self.client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
        self.token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def view_trial_balance(self):
        self.client.get(f"/api/projects/{PID}/trial-balance", headers=self.headers)

    @task(2)
    def edit_workpaper(self):
        self.client.get(f"/api/projects/{PID}/workpapers/{WP_ID}", headers=self.headers)

    @task(1)
    def save_workpaper(self):
        self.client.put(f"/api/projects/{PID}/workpapers/{WP_ID}", headers=self.headers, json={...})

    @task(2)
    def drilldown(self):
        self.client.get(f"/api/projects/{PID}/drilldown?account_code=1001", headers=self.headers)
```

### 性能优化方向（预判）

| 瓶颈 | 优化方案 |
|------|---------|
| DB 连接池耗尽 | pool_size=50, max_overflow=100 |
| TB 查询慢（大科目表） | 添加 GIN 索引 + 查询缓存（Redis 60s TTL） |
| prefill 计算慢 | 结果缓存（Redis，key=wp_id+tb_version） |
| 大 JSON 序列化 | orjson 替代 json（已在用） |
| SSE 连接数过多 | 限制每用户 1 个 SSE 连接 + 心跳 30s |

---

## F4 暗色模式 — 架构设计

### CSS 变量方案

```css
/* gt-design-tokens.css */
:root {
  --gt-bg-primary: #ffffff;
  --gt-bg-secondary: #f8f9fa;
  --gt-text-primary: #1a1a1a;
  --gt-text-secondary: #666666;
  --gt-border-color: #e4e7ed;
  --gt-table-header-bg: #f5f7fa;
  --gt-table-row-hover: #f5f8fc;
  --gt-table-row-selected: #e8f4fd;
  /* ... 更多变量 */
}

html.dark {
  --gt-bg-primary: #1a1a2e;
  --gt-bg-secondary: #16213e;
  --gt-text-primary: #e0e0e0;
  --gt-text-secondary: #a0a0a0;
  --gt-border-color: #2a2a4a;
  --gt-table-header-bg: #1f1f3a;
  --gt-table-row-hover: #252545;
  --gt-table-row-selected: #1a3a5c;
}

@media print {
  html.dark { /* 强制 light 主题打印 */ }
}
```

### Element Plus 暗色集成

```typescript
// main.ts
import 'element-plus/theme-chalk/dark/css-vars.css'

// App.vue
<el-config-provider :namespace="isDark ? 'dark' : ''">
  <router-view />
</el-config-provider>
```

### 主题切换 composable

```typescript
// useTheme.ts
export function useTheme() {
  const isDark = ref(localStorage.getItem('gt_theme') === 'dark')

  function toggle() {
    isDark.value = !isDark.value
    document.documentElement.classList.toggle('dark', isDark.value)
    localStorage.setItem('gt_theme', isDark.value ? 'dark' : 'light')
  }

  // 初始化
  onMounted(() => {
    document.documentElement.classList.toggle('dark', isDark.value)
  })

  return { isDark, toggle }
}
```

---

## F5 Storybook — 架构设计

### 技术选型

- Storybook 7.x + @storybook/vue3-vite
- 与现有 Vite 配置共享（tsconfig/alias/plugins）
- 部署：本地 `npm run storybook`（端口 6006）

### Stories 组织结构

```
frontend/src/stories/
├── common/
│   ├── GtEditableTable.stories.ts
│   ├── GtToolbar.stories.ts
│   ├── GtPageHeader.stories.ts
│   ├── GtAmountCell.stories.ts
│   ├── CellContextMenu.stories.ts
│   └── ... (28 个 common 组件)
├── business/
│   ├── SignGateChecklist.stories.ts
│   ├── VRHeatmap.stories.ts
│   ├── PrefillDiffPanel.stories.ts
│   ├── BatchActionBar.stories.ts
│   └── ConflictDialog.stories.ts
└── docs/
    └── ComponentGuide.mdx
```

---

## 测试策略

| 功能 | 测试方式 |
|------|---------|
| F1 双向穿透 | 后端 API 单测 + 前端 Playwright E2E |
| F2 LLM 接入 | 后端单测（mock vLLM）+ 集成测试（真实 vLLM） |
| F3 压力测试 | Locust 报告 + 性能基线对比 |
| F4 暗色模式 | vitest snapshot + 视觉回归（Chromatic） |
| F5 Storybook | Storybook build 成功 + 所有 stories 无报错 |
