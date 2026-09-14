# Requirements Document

## Introduction

本 spec 源自 `docs/GLOBAL_REFINEMENT_PROPOSAL_v4.md`（全局深度复盘建议书 v4，已校准到 v4.2/main 基线）的 **M1「一致性收口」** 档，目标是消除前端真实存在的低接入短板与遗留死代码。范围**严格限定为 M1 的 4 条任务（T1～T4）**，明确排除 M2（联动闭环）、M3（运维收尾）、M4（决策可信度）、M5（功能补全）。

M1 的核心价值：让同一个金额在不同页面长得一样、让失败提示风格统一、清掉历史除法 bug 残骸、消除散落的状态字符串硬编码。这是 v4 文档自荐的起点——纯前端、无外部依赖、风险最低、价值最高。

四条任务：
- **T1**：GtAmountCell 全量化（展示金额的裸列/本地 fmtAmt → `<GtAmountCell>`）+ 组件接入 CI 卡点
- **T2**：ElMessage.error 分层治理（catch 块内裸用改 handleApiError，业务校验保留）
- **T3**：删除 AMOUNT_DIVISOR_KEY 死代码（3 文件残骸）
- **T4**：残留状态字符串硬编码替换为 statusEnum 常量

## 关键约束（所有需求共同遵循）

1. **基线数字以 main 分支实测为准，立项当天必须重测**。v4 文档的 v4.2 快照（GtAmountCell 8 文件 / 视图 112 / ElMessage.error 187 处 100 文件）是 2026-05-29 时刻值，仅作参考。v4 铁律：实测有效期 = 单次 grep 时刻，基线随分支演进失效。任何 CI 卡点基线不得建立在过时数字上。
2. **仅修改前端代码**：`audit-platform/frontend/src/`（仓库唯一前端路径）。禁止写 `frontend/src/`（仓库根空壳）。不改后端、不改 DB、不改 router。
3. **GtEditableTable 不强制全量化**：明确"可编辑表"白名单（调整分录 / 合并工作底稿 / 试算表），其余只读表保持 `GtAmountCell + el-table` 即可，避免为统一而统一。
4. **每条需求必须可验收**：grep 命中数 / CI 基线 / 测试通过 / 单位切换实测，拒绝"做了但说不清"。
5. **工程约定**：PBT 用 `max_examples=15`；Windows 用 `python` 非 `python3`，命令分隔用 `;` 非 `&&`；前端质量双卡点 = `vue-tsc` 0 errors + `vitest` 0 failed。

## Glossary

- **GtAmountCell**：全局金额单元格组件（`src/components/common/GtAmountCell.vue`），统一万元/千元/元单位换算、千分位、tabular-nums 等宽数字、负数红字、可点击穿透。props = `value`(number|string|null) / `clickable`(bool) / `comment`(CellComment|null) / `priorValue`，emit `click`。内部 Decimal.js 计算，跟随 `displayPrefs` store 单位切换。
- **fmtAmt / 本地金额格式化**：各视图自行实现的 `{{ fmtAmt(row.xxx) }}` 等局部金额渲染，不跟随全局单位切换，是 T1 要消除的反模式。
- **displayPrefs store**：全局显示偏好单一真源（`src/stores/displayPrefs.ts`），管理金额单位/小数位/负数红字/零值显示/高亮阈值，localStorage 持久化。
- **handleApiError**：统一 API 错误处理工具（`src/utils/errorHandler.ts`），签名 `handleApiError(e, context)`，按 HTTP 状态码分级（网络/401静默/403/404/409/423/422/5xx），解析后端 `detail` 弹中文提示。
- **ElMessage.error catch 裸用**：`try { ... } catch (e) { ElMessage.error('xxx失败') }` 形式，未解析后端 detail，是 T2 要替换的子集。
- **ElMessage.error 业务校验提示**：文件大小超限 / 表单必填 / 登录失败等**主动**校验提示，不在 catch 块内，合理保留，**不得**误改。
- **AMOUNT_DIVISOR_KEY**：历史双重除法 bug 残骸（`src/constants/amountDivisor.ts` 定义的 Symbol），GtAmountCell 内 `injectedDivisor` inject 后 `_divisor` computed 已 no-op（标 `eslint-disable @typescript-eslint/no-unused-vars`），LedgerPenetration.vue 仅 import 未 provide（死 import）。是 T3 要删除的死代码。
- **statusEnum**：状态枚举常量 + 中文 label 单一真源（`src/constants/statusEnum.ts`），提供 WP_STATUS / ISSUE_STATUS / QC_INSPECTION_VERDICT / ARCHIVE_JOB_STATUS / REPORT_STATUS / PDF_TASK_STATUS 等常量及 `getStatusLabel` / `getStatusColor`。T4 要把散落的 `=== 'draft'` 等字符串硬编码替换为此处常量。
- **核心数据视图（六大）**：四表（资产负债/利润/现金流/所有者权益）、报表（ReportView）、底稿（WorkpaperList/Editor/Workbench/Summary）、调整（Adjustments）、错报（Misstatements）、附注（DisclosureEditor）——金额密集、最需统一呈现的页面。
- **CI 基线（baselines.json）**：`.github/workflows/baselines.json`，frontend-build job 读取做"只减不增/只增不减"卡点。现有相关字段：`no-bare-amount-cell-tables`(92) / `GtAmountCell-uses`(66) / `el-table-naked-vue-files`(176) / `align-right-cols`(380) / `GtAmountCell-coverage-ratio`("17%") / `GtAmountCell-target-ratio`("80%")。
- **双口径说明**：v4 用**文件数口径**（GtAmountCell 接入 8 文件 / 112 视图）；既有 baselines.json + memory 的 `gt-amount-cell-rollout` 用**用量/列数口径**（GtAmountCell-uses 66 / align-right-cols 380 / 覆盖率 17%→80%）。两者并存，本 spec 验收以**列数口径**对齐既有 CI 卡点（避免新建第三套基线），文件数口径仅作进度参考。

## Requirements

### Requirement 1：立项当天基线重测（前置守门）

**User Story:** 作为开发者，我希望在立项当天对 main 分支重新实测所有 M1 相关基线数字，以便 CI 卡点和验收目标建立在真实当前值而非过时快照上。

#### Acceptance Criteria

1. WHEN 本 spec 进入实施（tasks 执行）阶段, THE 实施者 SHALL 在 main 分支用 PowerShell `Select-String -List | Measure-Object` 重新精确计数以下指标：GtAmountCell 接入文件数、`GtAmountCell-uses` 用量、`align-right-cols` 列数、`el-table-naked-vue-files`、catch 块内 ElMessage.error 数、AMOUNT_DIVISOR_KEY 引用文件数、状态硬编码命中数。
2. WHERE grep 结果返回 `[truncated: too many matches]`, THE 实施者 SHALL 禁止数可见行下结论，必须用 `-List | Measure-Object` 精确计数。
3. THE 重测结果 SHALL 写入本 spec 的 tasks.md 或独立 baseline 记录，作为后续所有 CI 卡点和验收阈值的唯一依据。
4. IF 重测值与 v4.2 快照（GtAmountCell 8 文件 / 112 视图 / ElMessage 187 处）存在差异, THEN THE 实施者 SHALL 以重测值为准并记录差异原因。

### Requirement 2：T1 — GtAmountCell 全量化

**User Story:** 作为审计助理，我希望所有展示金额的页面都用统一的金额单元格呈现（同样的单位、千分位、对齐、负数红字、可穿透），以便同一个数字在序时账穿透页、底稿汇总页、底稿工作台之间长得一样，减少认知负担和看错数的风险。

**User Story:** 作为项目经理 / 合伙人，我希望切换金额单位（元/万元/千元）后所有金额页同步变化，以便全局口径一致，不会一个页面显示万元、另一个还显示元。

#### Acceptance Criteria

1. THE 实施者 SHALL 盘点六大核心数据视图（四表 / 报表 / 底稿 / 调整 / 错报 / 附注）中所有展示金额的 `<el-table-column>` 与本地 `fmtAmt` 渲染。
2. WHEN 一个金额列属于纯展示（非可编辑表白名单内）, THE 实施者 SHALL 将其替换为 `<GtAmountCell>`。
3. WHERE 表格属于"可编辑表"白名单（调整分录 / 合并工作底稿 / 试算表）, THE 实施者 SHALL 保留其编辑能力，不强制改为只读 GtAmountCell。
4. WHEN 替换完成, THE GtAmountCell 接入文件数 SHALL 从立项重测基线（v4.2 参考值 8）提升至 ≥ 30 个核心数据视图。
5. WHEN 用户在 displayPrefs 切换金额单位, THE 所有已接入 GtAmountCell 的金额 SHALL 同步换算显示。
6. THE 金额列裸用数（`no-bare-amount-cell-tables` / `align-right-cols` 中未走 GtAmountCell 的部分）SHALL 较立项基线下降 ≥ 80%。
7. THE 替换 SHALL NOT 改变任何金额的数值精度（沿用 Decimal，不引入浮点误差）。
8. WHEN 替换完成, THE `vue-tsc` SHALL 报 0 errors AND `vitest` SHALL 0 failed。

### Requirement 3：T1 — 组件接入 CI 卡点

**User Story:** 作为质控 / 开发者，我希望有 CI 卡点持续守护金额组件接入率，以便"做一轮停一轮"的漂移被自动拦截，接入率只增不减。

#### Acceptance Criteria

1. THE 实施者 SHALL 复用既有 `no-bare-amount-cell.cjs` ESLint 规则 + `.github/workflows/baselines.json` 基础设施，不新建并行的第三套基线体系。
2. THE CI 卡点 SHALL 以立项重测值更新 `baselines.json` 中 `no-bare-amount-cell-tables` / `GtAmountCell-uses` / `align-right-cols` 字段。
3. WHEN PR 使金额列裸用数增加（`no-bare-amount-cell-tables` 上升）, THE CI frontend-build job SHALL 失败。
4. WHEN PR 使 `GtAmountCell-uses` 减少, THE CI SHALL 失败（只增不减）。
5. THE 卡点脚本 SHALL 在本地可复现（提供 PowerShell 或 node 命令），与 CI 读取同一份 baselines.json。

### Requirement 4：T2 — ElMessage.error 分层识别

**User Story:** 作为开发者，我希望先把全库 ElMessage.error 按"是否在 catch 块内"分成两类，以便只治理该改的 catch 裸用，而不误伤合理的业务主动校验提示。

#### Acceptance Criteria

1. THE 实施者 SHALL 提供一种可复现的方法（脚本或 ESLint 规则或人工 review 清单）区分两类 ElMessage.error：(a) catch 块内裸用；(b) 业务主动校验提示（文件大小 / 表单必填 / 登录失败等）。
2. THE 实施者 SHALL NOT 将全库 ElMessage.error 总数（v4.2 参考 187 处）直接当作"待清零债务"，避免误伤第二类。
3. THE 分层结果 SHALL 输出 catch 块内裸用的精确命中数与文件清单，作为 T2 治理范围与 CI 基线依据。
4. WHERE 一处 ElMessage.error 难以静态判定归属, THE 实施者 SHALL 人工 review 确认归类，记录判定理由。

### Requirement 5：T2 — catch 裸用替换为 handleApiError

**User Story:** 作为审计助理，我希望操作失败时所有页面都告诉我"为什么失败"（解析后端 detail），而不是有的页面只说"失败了"，以便我能据此判断如何处理。

#### Acceptance Criteria

1. WHEN 一处 ElMessage.error 被判定为 catch 块内裸用, THE 实施者 SHALL 将其替换为 `handleApiError(e, '操作名')`，传入有意义的中文操作名。
2. THE catch 块内 ElMessage.error 命中数 SHALL 降至 0。
3. THE 业务主动校验提示（第二类）SHALL 保持不变，不被替换。
4. THE CI 卡点 SHALL 以分层后的 catch 残留数（治理后为 0）作为基线，而非 187 总数。
5. WHEN 替换完成, THE `vue-tsc` SHALL 报 0 errors AND `vitest` SHALL 0 failed。
6. WHEN 后端返回带 detail 的错误响应, THE 替换后的页面 SHALL 显示后端 detail 中文消息而非原始裸文案。

### Requirement 6：T3 — 删除 AMOUNT_DIVISOR_KEY 死代码

**User Story:** 作为开发者，我希望清掉历史双重除法 bug 的 AMOUNT_DIVISOR_KEY 残骸，以便代码库不残留误导性的 no-op 死代码（符合"死代码立即删除，不留 fallback 注释"偏好）。

#### Acceptance Criteria

1. WHEN 确认 `AMOUNT_DIVISOR_KEY` 全仓仅 3 处引用（amountDivisor.ts 定义 + GtAmountCell.vue inject + LedgerPenetration.vue 死 import）, THE 实施者 SHALL 删除整个 `src/constants/amountDivisor.ts` 文件。
2. THE 实施者 SHALL 删除 `GtAmountCell.vue` 中 `AMOUNT_DIVISOR_KEY` 的 import、`inject`、`injectedDivisor`、no-op 的 `_divisor` computed 及相关 `eslint-disable` 注释。
3. THE 实施者 SHALL 删除 `LedgerPenetration.vue` 中 `AMOUNT_DIVISOR_KEY` 的 import。
4. WHEN 删除完成, THE grep `AMOUNT_DIVISOR_KEY`（范围 `src/**/*.vue,*.ts`）SHALL 返回 0 命中。
5. WHEN 删除完成, THE GtAmountCell 的金额显示行为 SHALL 与删除前完全一致（无功能回归，因其已 no-op）。
6. WHEN 删除完成, THE `vue-tsc` SHALL 报 0 errors AND `vitest` SHALL 0 failed。

### Requirement 7：T4 — 状态字符串硬编码替换为 statusEnum

**User Story:** 作为开发者，我希望散落在视图里的状态字符串硬编码（`=== 'draft'` 等）替换为 statusEnum 常量引用，以便状态枚举单一真源，新增/重命名状态时不会漏改某个页面。

#### Acceptance Criteria

1. THE 实施者 SHALL 在 QcInspectionWorkbench / ArchiveWizard / AuditReportEditor / IssueTicketList / PDFExportPanel 中定位所有状态字符串硬编码比较（如 `=== 'pending'` / `'completed'` / `'closed'` / `'rejected'` 等）。
2. WHEN 一处状态硬编码比较被定位, THE 实施者 SHALL 替换为 `statusEnum.ts` 中对应常量引用（如 `WP_STATUS.DRAFT` / `ISSUE_STATUS.CLOSED` / `QC_INSPECTION_VERDICT.PASS`）。
3. WHEN 替换完成, THE ESLint `no-status-string-literal` 规则在这 5 文件内命中数 SHALL 清零。
4. THE 替换 SHALL NOT 改变任何状态判断的业务逻辑（仅符号替换，行为等价）。
5. WHERE 某状态值在 statusEnum.ts 中尚无对应常量, THE 实施者 SHALL 补充该常量定义后再引用。
6. WHEN 替换完成, THE `vue-tsc` SHALL 报 0 errors AND `vitest` SHALL 0 failed。

## 验收目标汇总

| 任务 | 验收指标 | 目标 |
|------|---------|------|
| T1 | GtAmountCell 接入文件数 | 立项基线 → ≥ 30 核心数据视图 |
| T1 | 金额列裸用数（no-bare-amount-cell-tables） | 较立项基线下降 ≥ 80% |
| T1 | 单位切换联动 | 所有金额页同步变化 |
| T1 | CI 卡点 | baselines.json 接入率字段只增不减上线 |
| T2 | catch 块内 ElMessage.error | → 0 |
| T2 | 业务校验提示 | 保持不变（不误伤） |
| T3 | grep AMOUNT_DIVISOR_KEY | = 0 |
| T4 | 5 文件内状态硬编码 | = 0 |
| 全局 | vue-tsc / vitest | 0 errors / 0 failed |

## 范围边界（明确排除）

- ❌ M2 联动闭环（单元格右键溯源 / useProjectEvents / 通用编辑锁）
- ❌ M3 运维收尾（可选依赖文档 / 表膨胀监控 / 权限一致性测试）
- ❌ M4 决策可信度（PDF 预览 / 数据冻结提示 / EQCR verdict 透明化）
- ❌ M5 功能补全（函证模块 / 三码体系 / 虚拟滚动全量化）
- ❌ 后端代码、DB schema、router 任何改动
- ❌ GtEditableTable 强制全量化（仅明确可编辑表白名单）
