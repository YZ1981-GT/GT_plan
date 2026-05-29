# V3 spec 已知缺口与技术债（gaps.md）

> 起草日期：2026-05-28
> 来源：spec 关闭前反向记录（conventions.md §⑥ gaps.md 反向记录铁律）
> 用途：作为下一个 spec 的 input，避免"标 [x] 但实际未到位"被遗忘

## A. 真正未做（外部依赖阻塞）

| 项 | tasks.md 标记 | 阻塞 | 解锁路径 |
|---|---|---|---|
| 14.4 真实项目 UAT（合伙人验收） | `[ ]` | 真合伙人 + 全流程项目数据 | 拆独立 spec `v3-partner-acceptance`，不阻塞主 spec 关闭 |
| 12.1.6 Playwright 全功能回归 | `[x]`（spec 已建占位）| dev server + 真实底稿 | spec `v3-playwright-uat` |
| 12.2.4 65 万行性能基准 | `[x]`（vitest 替代）| YG2101 真实数据 | spec `v3-large-data-perf` |
| 13.11 全平台中文化截图对比 | `[x]`（spec 已建占位）| dev server | 同上 v3-playwright-uat |

## B. 部分完成 / 妥协（标 [x] 但未到 baseline）

### B.1 GtAmountCell 覆盖率严重不足（Req 8.1）

| 维度 | 数据 |
|---|---|
| spec 描述 | "TrialBalance / ConsolidationIndex / CFSWorksheet / SamplingEnhanced / WorkpaperSummary 等 15+ 视图接入" |
| 实际接入 | 3 视图（TrialBalance / SamplingEnhanced / ConsolidationIndex）共减 17 处 |
| 实测 ratio（2026-05-28） | 380 处 `align="right"` 列 / 66 处 GtAmountCell ≈ **17%** |
| 目标 | 80%（304 处） |
| **下个 spec** | `gt-amount-cell-rollout`：分 4 批每批 20 视图，2-3 周 |

### B.2 WorkpaperEditor 瘦身仅完成 5%

| 维度 | 数据 |
|---|---|
| 起始 | 2625 行 |
| 当前 | 2555 行（-70 行净） |
| 目标 | ≤ 1000 行 |
| 完成度 | **70/1625 ≈ 4.3%** |
| 已建基础设施 | useEditorToolbar / useEditorCycles / useEditorMode / editorDialogConfig 4 composable + 删 44 处冗余别名 |
| 缺口 | 模板 v-for 渲染替代散落 if/else + onMounted dispatch 拆出 + SFC 子组件拆分（SaveBar / SidePanel / DialogHost）|
| **下个 spec** | `workpaper-editor-shrink-phase2`：3-5 天独立 Sprint |

### B.3 加载状态统一推进 ~0（Req 8.2）

| 维度 | 数据 |
|---|---|
| 起始 baseline | 10 视图 el-skeleton |
| 当前实测 | 11 视图 |
| 推进 | +1 视图（≈ 0%）|
| 标 [x] 依据 | "3 视图示范 + 余下一次性加载无需改动"（实质未达成 spec 描述的 10 视图 refetch 改 v-loading）|
| **下个 spec** | 触碰时做（按需）|

### B.4 错误处理统一仅 Top 15（Req 8.5）

| 维度 | 数据 |
|---|---|
| spec 描述 | "58 视图 catch 块 ElMessage.error → handleApiError 机械替换" |
| 实际替换 | Top 15 文件 ~30 处 |
| 完成度 | ≈ 26% |
| 标 [x] 依据 | "余下 6 处为特殊处理"（数据源 views 内）；剩余 ~28 处分散在 components/services 未触达 |
| **下个 spec** | 触碰时做 |

### B.5 console.log 治理只清"真实违规"

| 维度 | 数据 |
|---|---|
| spec 描述 | "74 处 console.log/error/warn 替换" |
| 实际处理 | 3 处真实 ESLint 违规 + Top 28 处 DEV 守卫 |
| 完成度（按总数）| 31/74 = 41%；按违规数 100% |
| 教训 | spec 起草混淆"grep 总数"和"违规数"（conventions §② 已固化）|

## C. 跳过的 case / 测试

### C.1 PrefillDiffPanel L-3 snapshot comparison column

- **状态**：4 测试 `describe.skip` + TODO 注释
- **原因**：组件中未实现 `with-snapshot-toggle` UI（"与上次快照对比" / "数据已变更"标签）
- **下个 spec**：`prefill-snapshot-comparison`（独立功能 spec）
- **位置**：`src/__tests__/PrefillDiffPanel.spec.ts:107`

### C.2 GtTableExtended formatter / toolbar-left slot 测试

- **状态**：5/5 passed（通过添加 GtEditableTable 自定义 stub 解决）
- **隐性缺**：测试只验证 stub 而非真实 Element Plus 渲染；真实组件 formatter 调用 / slot 渲染未在 vitest 端到端覆盖
- **建议**：下次添加 Storybook + visual regression 时补 e2e 验证

### C.3 PBT 跳过的边界

- property-form-validation 起初未涵盖 `year < 2000` 范围失败 → 修预测谓词后通过
- property-year-switching 5c 起初未排除 `targetYear === 2024` 初始值 → filter 后通过
- 教训已固化到 conventions（"PBT oracle 完整性 / PBT 边界值过滤"两条铁律）

## D. 可选项（spec 中标 `[ ]*`）

| 项 | tasks.md 编号 | 决策 |
|---|---|---|
| 8.6.2 其余列表视图分页 | `[ ]*` | 触碰时做，不立 spec |
| 11.9 6000 用户压测估算 | `[x]`（已写容量规划文档）| docs/operations/time-machine-capacity-planning.md |
| 12.6 用户行为热力图（PostHog） | `[ ]*` | 独立 spec `posthog-rollout`（3 天，按需）|
| 13.12 删除 _chinese_localize.py | 已完成（保留供后续 spec 复用）| 复用而非删 |

## E. 测试基线（CI 锁定值，2026-05-28）

防退化基线，写入 `.github/workflows/baselines.json._v3_coverage_guards`：

| 指标 | 当前值 | CI 卡点 |
|---|---|---|
| vue-tsc errors | 0 | 0 |
| vitest failed tests | 0 | 0 |
| vitest skipped tests | 7 | ≤ 7（PrefillDiffPanel 4 + 其他 3）|
| GtAmountCell uses | 66 | ≥ 66（只增不减）|
| el-form 含 :rules 视图 | 70 | ≥ 70（只增不减）|
| WorkpaperEditor.vue 行数 | 2555 | ≤ 2555（只减不增）|
| ESLint no-console 严格违规 | 0 | 0 |

## F. 元 - spec 流程改进（已沉淀到 conventions.md）

- **§① 3 分钟可行性探测铁律**：起草时强制最小可行性证据
- **§② baseline 总数 vs 违规数**：严格区分两类数字
- **§③ TS 类型预演**：design.md 必须含 5-10 行类型签名片段
- **§④ [~] 状态语义铁律**：拆 `[partial]` / `[blocked-env]` 不混用
- **§⑤ 真环境 UAT 拆独立 spec**：不阻塞主 spec 关闭
- **§⑥ gaps.md 反向记录铁律**（**本文件就是这条铁律的产物**）
- **§⑦ CI 双卡点**（vue-tsc 0 errors + vitest 0 failed，已 2026-05-28 落地）

## G. 下一步推荐 spec 清单（按 ROI 排序）

| 优先级 | spec 名 | 工时 | 触发条件 | 状态 |
|---|---|---|---|---|
| ✅ 完成 | `cycle-editor-generic`（K/L/M/N → useSimpleCycleEditor）| 0.5 天 | 直接修 | 2026-05-28 commit f8bedc32+ |
| ✅ 完成 | `html-renderer-registry`（11 类硬编码 → registry 模式） | 0.5 天 | 直接修 | 2026-05-28 commit f8bedc32+ |
| P0 | `v3-partner-acceptance` | 1-2 天 | 合伙人有空 | spec 未起 |
| P0 | `workpaper-list-shrink`（3238→拆 5 SFC + shell）| 1 周 | 触碰列表时 | **README stub** `.kiro/specs/workpaper-list-shrink/README.md` |
| P1 | `gt-amount-cell-rollout` | 2-3 周 | 当前 17% → 80% 覆盖 | spec 未起 |
| P1 | `workpaper-editor-shrink-phase2` | 3-5 天 | 2555 → ≤1000 行 | spec 未起 |
| P1 | `workpaper-fill-service-split`（1587→拆 4 service）| 2 天 | prefill 函数下次扩展时 | **README stub** `.kiro/specs/workpaper-fill-service-split/README.md` |
| P2 | `prefill-snapshot-comparison` | 2 天 | L-3 feature 实现 + 启用 4 测试 | spec 未起 |
| P2 | `vllm-httpx-bugfix` | 1 天 | 修 3 个明确方案的 bug（memory 已记）| spec 未起 |
| P2 | `gt-c-note-table-shrink`（1608+1125 → 拆 5+7） | 2-3 天 | 触碰附注/控制测试时 | **README stub** `.kiro/specs/gt-c-note-table-shrink/README.md` |
| P3 | `posthog-rollout` | 3 天（可选）| 用户行为可观测性 | spec 未起 |
