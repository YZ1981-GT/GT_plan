# 任务 3.3 浏览器实测证据（写请求年度门控）

> 实测日期：2026-10-25。浏览器：Chrome DevTools page 2，`http://127.0.0.1:3030`，已登录 `admin`，隔离上下文 `pcfc-admin`。
> 本批聚焦**写请求**链路验证（任务 3.2 的写请求年度门控 + 程序表字段覆盖写入）。读请求链路验证见 `evidence/read-batch-4.2.md`（已通过）。
>
> 结论：**全部通过**。有年度项目写请求正确使用项目审计年度 2025（非日历年 2026）；缺年度项目空态门控完全阻止写操作 UI 挂载、零年度参数化请求。

## 验证数据

- 有年度项目：`0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49`，名称「重药控股安徽有限公司_2025」，`audit_year=2025`。
  - 底稿入口：`0898d6e5-3388-4371-b9cc-034fa7e8b593`，`wp_code=D2-1`；程序表子页 = 「应收账款实质性程序表D2A」（`componentType: d2-accounts-receivable`，但渲染为 `a-program-console` 壳）。
- 缺年度项目：`a070397b-34b7-4b57-b832-125c4bffceec`，名称 `proj_a6242abd`，`audit_year=null`。
  - 底稿入口：`24924bd1-9aef-483d-8016-11ae5feaef6b`，`wp_code=D2`。

## 测试步骤与结果

### A. 有年度项目 — 程序表步骤状态写入（通过）

1. 打开 D2-1 底稿编辑页：`/projects/0ec33ac9-.../workpapers/0898d6e5-.../edit`
2. 切到「💰 应收账款实质性程序表D2A」子页。
3. 页面显示 20 条程序步骤（全「待执行」），编制信息「索引号：D2A」「截止日：2025-12-31」。
4. 点击步骤 1 的状态下拉「待执行 ▸」→ 选择「执行中」。
5. UI 更新：步骤 1 从「待执行」变为「执行中」；摘要从「20 待执行」变为「1 进行中 / 19 待执行」。

**写请求网络证据**（`reqid=20788`）：

```
POST /api/workpapers/field-overrides → 200
Content-Type: application/json

请求体：
{
  "project_id": "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49",
  "year": 2025,                          ← 项目审计年度（非 2026 日历年）
  "scope": "procedure_table:D2A",        ← 表码（来自 render-config override_scope）
  "item_key": "1",
  "field": "status",
  "value": "in_progress"
}

响应体：
{
  "code": 200,
  "message": "success",
  "data": {
    "id": "41a9e872-aa34-401d-8a64-3218d383f5ff",
    "project_id": "0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49",
    "year": 2025,
    "scope": "procedure_table:D2A",
    "item_key": "1",
    "field": "status",
    "value": "in_progress"
  }
}
```

验证要点：
- `year: 2025` — 使用项目审计年度，非当前日历年（2026-10-25 执行时日历年为 2026）。
- `scope: "procedure_table:D2A"` — 使用表码，非表名（与 `_a_program.py` 的 `resolve_program_template_code` 一致）。
- 响应 200 且 data 回显完全一致。

**render-config 证据**（`reqid=20566`）：

- `data.audit_year = 2025`
- `sheets[1].html_data.project_context.audit_year = "2025"`
- `sheets[1].html_data.project_context.bs_date = "2025-12-31"`

### B. 缺年度项目 — 空态门控阻止写操作（通过）

1. 打开 D2 底稿编辑页：`/projects/a070397b-.../workpapers/24924bd1-.../edit`
2. 页面显示：
   - uid 47_32「未设置审计年度」
   - uid 47_33「请先在项目基本信息中填写审计年度，再打开底稿读取数据。」
3. **无工作台标签栏**（无「💰 审定表D2-1」「💰 应收账款实质性程序表D2A」等子页）；**无工具栏**（无「💾 保存」「📊 一键填充」「🔄 刷新取数」等按钮）；**无程序表行**（无「填写执行情况」输入框、无「待执行」下拉、无「委派」按钮）。
4. 空态门控使写操作入口完全不存在，用户**无法触发任何写请求**。

**网络证据**：

全部 API 请求（过滤 Kaspersky 安全扫描后）：
- `GET /api/projects/a070397b-…` → 200（项目上下文，无年度参数）
- `GET /api/projects/a070397b-…/ledger/years` → 200（年度探测，`years=[]`）
- `GET /api/workpapers/24924bd1-…/render-config` → 200（`data.audit_year = null`）
- `POST /api/editing-locks/workpaper/24924bd1-…` → 200（编辑锁，无年度参数）
- `GET /api/…/event-cascade/health`、`role-context/…`、`ledger-import/active-job`、`formula-settings/pending`、`consolidation/…/lock-status`、`stale-summary`、`notifications`、`review-inbox` — 均为项目上下文读取，无年度参数。

**零年度参数化业务请求**（`performance.getEntriesByType('resource')` 过滤确认）：
- `trial-balance?year=…` — 0 次
- `adjustments?year=…` — 0 次
- `guidance` — 0 次（唯一匹配是 Vite 源文件 HMR）
- `field-overrides` — 0 次
- `procedure-tables` — 0 次
- `save` — 0 次

4.2 证据中记录的旧缺陷（`adjustments?year=2025` 静默请求）**已修复不再复现**。

### C. 对照：4.2 证据中旧缺陷的修复确认

4.2 首次实测时缺年度项目仍按 2025 发出 `adjustments?year=2025`，根因是 `GtWpRenderer.preparationYear` 在 `render-config.audit_year=null` 时回退到 `useProjectStore().year`（store 年度是可切换 UI 状态，初始化为当前年减一 = 2025）。

修复后：`GtWpRenderer.preparationYear` 只认 render-config 的 `audit_year`，配置缺省时才回退父 Shell 传入的同项目年度；年度缺失时不挂载注册表 HTML 子组件。`WorkpaperEditor.vue` 以 `projectYear != null` 为挂载门，确认缺失后显示中文空态。

本次 3.3 实测**与 4.2 修复后复测结果一致**：缺年度页面显示空态、零业务请求。

## 控制台证据

- 有年度 D2A 实测期间：无 error（仅既有 Element Plus/Vue warning）。
- 缺年度 D2 实测期间：1 条 `DataCloneError: Failed to execute 'postMessage' on 'BroadcastChannel'`（BroadcastChannel 序列化问题，与年度无关）；无年度相关 error 或 warning。

## 修改文件与数据变更

- 修改文件：仅新增本证据文件 `evidence/write-batch-3.3.md`；未修改生产代码、测试代码或任务清单。
- 数据变更：重药安徽项目 D2A 程序表步骤 1 状态从「待执行」改为「执行中」（`field_overrides` 记录 `41a9e872-…`，`value="in_progress"`）。该变更为实测写入证据，可由用户在程序表 UI 中恢复。

## 任务结论

任务 3.3 浏览器实测**全部通过**：

| 链路 | 验证要点 | 结果 |
|---|---|---|
| 有年度 — 写请求年度 | `field-overrides` POST 的 `year` = 项目审计年度 2025，非日历年 2026 | ✅ 通过 |
| 有年度 — 写请求 scope | `scope` = `procedure_table:D2A`（表码），非表名 | ✅ 通过 |
| 有年度 — 读请求年度 | render-config `audit_year=2025`，`project_context.bs_date=2025-12-31` | ✅ 通过（同 4.2） |
| 缺年度 — 空态文案 | 「未设置审计年度」+「请先在项目基本信息中填写审计年度」 | ✅ 通过（同 4.2） |
| 缺年度 — 写 UI 不可达 | 无工作台标签、无工具栏、无程序表行、无输入/下拉 | ✅ 通过 |
| 缺年度 — 零业务请求 | performance API 确认 0 次 trial-balance/adjustments/guidance/field-overrides/procedure-tables 请求 | ✅ 通过 |
| 缺年度 — 旧缺陷不复现 | 4.2 记录的 `adjustments?year=2025` 已消除 | ✅ 通过 |
