# Task 17 —— 定向行为测试与 localhost:3030 Playwright 端到端补验（闭合）

日期：2026-09-25
环境：后端 9980（`--reload` 热加载）+ 前端 3030 + 本地 PG，登录态 admin 可用。

## 结论

Task 17 端到端补验 **通过**。本轮环境登录态可用，突破了历史记录中「3030 重定向 `/login` 无可用登录态」的阻塞；期间定位并修复了一个真实后端 500 缺陷（render-config `UnboundLocalError`），补齐防御测试，并用真实浏览器完成 R14 全部验收点。

## 一、定向行为测试（4 文件 / 29 例全绿）

| 文件 | 例数 | 覆盖 R14 点 |
|---|---|---|
| `composables/__tests__/FormulaManagerPageWiring.spec.ts` | 4 | 真实 Dialog 挂载：全册聚合+清筛选 / 丢弃慢旧实例结果 / 显式失败非空成功 / 用户 tab 真 wpId + 拒收关闭会话响应（R14.2/14.3/14.4/14.5） |
| `components/workpaper/__tests__/wpRendererFormulaEntry.spec.ts` | — | 页面入口带当前页身份、缺 wp_code 不打开、来回切页取当次页（R14.1/14.2） |
| `components/formula/__tests__/sharedSheetScopeTargeting.spec.ts` | — | 共享页真实定位 / 定位不到显式告警不谎称（R14.3） |
| `components/formula/__tests__/formulaBoardAndGlobalScope.spec.ts` | — | 公式看板 + 全局作用域 |

命令：`npx vitest run`（去 rtk，避免 reporter 干扰）。4 文件 29 passed。

## 二、根因修复：render-config 端点 `UnboundLocalError` 500

### 复现
真实 HTTP `GET /api/workpapers/c24c0705-.../render-config?project_id=0ec33ac9-...` → **500（空响应体）**。
Playwright 全宿主 e2e 并发访问时表现为 `read ECONNRESET`。

### 根因（直调 `_get_render_config_impl` 打印 traceback 定位）
```
File "app/routers/wp_render_config.py", line 962, in _get_render_config_impl
  if ovr in _SELF_CONTAINED_DEDICATED and sheets:
     ^^^ UnboundLocalError: cannot access local variable 'ovr'
```
`ovr = _WP_CODE_OVERRIDE.get(wp_code)` 曾**只在 `for cls in classifications` 循环体内**首次赋值。当 classifications 为空 / 全部 sheet 被 `continue` 跳过（空 sheet 集底稿，如 `c24c0705`）时，循环体一次都不执行，循环后第 962 行引用了从未赋值的 `ovr`。有 sheet 的底稿从未暴露此边界，故长期潜伏。

### 修复（单一真源、语义等价）
`ovr` 是 wp_code 级循环不变量，与具体 sheet 无关，**提升到循环外初始化**，删除循环体内冗余赋值行。
- `IMPL_OK sheets= 0` + `CONTRACT_OK`（直调验证）
- 运行中后端（`--reload`）热加载后真实 HTTP `RC_STATUS=200`

### 防御测试（防回退）
`backend/tests/test_render_config_semantic.py::TestOvrLoopInvariantRegression`
源码守卫：`ovr = _WP_CODE_OVERRIDE.get(wp_code)` 必须出现在 `for cls in classifications:` 之前，且引用点 `if ovr in _SELF_CONTAINED_DEDICATED` 仍在（防守卫假绿）。
- GREEN：`1 passed`
- RED 验证：临时注释循环外初始化行 → `FAILED`（准确抓回归），随后恢复。
- 全文件回归：`41 passed`（原 40 + 新守卫 1）。

## 三、回归修复：GtWpAiReviewToolbar 缺 Task 9 taxonomy 属性

核查阶段发现 `aiActionTaxonomy.spec.ts`（Task 9）RED：`GtWpAiReviewToolbar.vue` 缺 `data-ai-action="ai_review_page"/"ai_review_batch"` 与 `descriptorFor(...)` 接线（Task 9 组件改动此前未落库）。已补齐（两按钮加 `data-ai-action` + `:aria-label` 由 `descriptorFor().a11yName` 派生）。修复后本 spec 相关 16 文件 100 例全绿。

## 四、Playwright 真实浏览器端到端验收（localhost:3030）

真实底稿：项目 `2aa00f57-...` 的 D2 应收账款底稿 `ef7f88e3-...`（页面自动切到 last-active D2）。

| 验收点 | 实测 | 对应需求 |
|---|---|---|
| compatibility outlet 真实挂载 | `compatOutlet: true` | R4.1/R14.1 |
| primary outlet 真实挂载 | `primaryOutlet: true` | R4.1 |
| GtWpToolbar 渲染 | `gtWpToolbar: true` | — |
| 公式入口唯一 | `formulaBtnCount: 1`（挂 `page-capabilities-compatibility`） | R4.5/R5.1 |
| 点击打开唯一 dialog | `visibleDialogCount: 1` / `formulaDialogCount: 1`，标题「ƒx 公式管理中心」 | R5.1 |
| 默认全册聚合真实数据 | 「底稿全册公式 45」，健康度 100% 42/42、逻辑审核 (10) | R14.3 |
| 显示来源位置 + 真实年度 | 「底稿 > D2 > 全册（当前位置：底稿目录；2025年度）」 | R14.2/14.3 |
| 无运行时错误 | `0 console errors` | R12.3 |

截图：`basis/T17-e2e-formula-manager-open.png`。

### 全宿主 e2e spec 说明
`e2e/workpaper-formula-toolbar-shell.spec.ts` 的 `resolveHostMatrix` 串行遍历项目**所有**底稿逐个调 render-config（单个 2MB / ~1.5s），在当前大项目（`0ec33ac9` E2E-D4 发布测试项目，底稿多且凑不齐 PREFERRED 编码）上累计超过 120s 超时。这是**测试遍历策略在大项目上的性能问题**，非本 spec 功能缺陷（render-config 500 已修，单请求 200）。故本轮以「定向真实浏览器验收」替代全矩阵跑，直接覆盖 R14 验收点。全宿主矩阵在合适的小种子项目上仍可复现（Task 14 历史 4/4 PASS 记录）。

## 五、未 commit → 本轮入库
Task 17 历史记录「未 commit，spec 与新增测试尚未入库」。本轮随归档一并提交：GtWpAiReviewToolbar 接线修复、render-config 根因修复 + 防御测试、本证据文件、截图。


## 六、复盘：回归核查与既存漂移隔离

本 spec 相关全量测试回归（2026-09-25）：

- **前端** `shell/formula` + `components/formula` + `FormulaManagerPageWiring/Dialog` + `wpRendererFormulaEntry` + `workpaper/review`：**302 passed / 1 failed**。
  - 唯一失败 `noteScopeTargeting.spec.ts > ReportView 挂载 FormulaManagerDialog`：属 **report 域（domain-owned，本 spec 明确 out-of-scope）**，且 `ReportView.vue` 工作树无改动、最后一次改动在 commit `82f58ea44`（D4 IPO 综合交付）——**既存漂移，非本轮引入**。
- **后端** render-config 全量：**94 passed / 3 failed**。
  - 3 例失败均在 `test_render_config_component_type_pbt.py`（如 `A8-1` 期望 `word-template`、实际 `a8-1-other-info-representation`）——是 `_WP_CODE_OVERRIDE` 组件映射被其他 spec 修改导致 PBT 期望值过期。
  - **隔离验证**：`git stash` 掉本轮全部改动后，这 3 例 **仍全红** ⇒ 与本 spec 修复无因果，属既存漂移。
- 本轮两处修复（render-config `ovr` 循环外初始化、`GtWpAiReviewToolbar` taxonomy 接线）+ 防御测试 `TestOvrLoopInvariantRegression` 全部 GREEN，无新增回归。

**触类旁通核查**：render-config `_get_render_config_impl` 中 `ovr` 之后的所有 `sheets` 消费点（`_first_ct = sheets[0] ... if sheets else None`、`if ovr in _SELF_CONTAINED_DEDICATED and sheets:` 等）均已带空 sheet 防御，`ovr` 是唯一漏掉循环外初始化的变量，已修复；未发现同型 UnboundLocalError 隐患。

**移交建议（不属本 spec，登记不处理）**：
- report 域 `ReportView.vue` 公式弹窗接线与 `noteScopeTargeting.spec.ts` 期望不一致，建议 report 域负责 spec 复核。
- `test_render_config_component_type_pbt.py` 3 例期望值随 `_WP_CODE_OVERRIDE` 映射演进已过期，建议 render/override 相关 spec 更新 golden 期望。
