# Spec B (R10) — Linkage & Tokens

**编制人**：合伙人（平台治理）
**起草日期**：2026-05-16
**状态**：🟡 占位（立项规划完成，待启动条件满足后起草三件套）
**关联**：v3 §7（联动闭环）+ §8（显示治理三条线）+ §9（组件铺设）
**预计启动**：2026-06-上旬（v3 P0 全部清完 + Spec A 上线观察 ≥ 7 天稳定后）

---

## 立项背景

v3 P0 + Spec A 落地后剩余的 4 个核心治理面：

1. **显示治理三条线**：字号 1565 处 / 颜色 1611 处 / 背景 712 处 inline 硬编码（v3 §8）
2. **GtEditableTable 接入率治理**：当前仅 3 处使用（Adjustments + 2 个合并工作表组件），需职责瘦身（v3 §9）
3. **报表/附注/错报右键穿透补完**：ReportView/DisclosureEditor 已有，TrialBalance "查看关联底稿" 已有；缺 Misstatements/Adjustments 右键菜单（v3 §7.6）
4. **stylelint 卡点 + CI 基线**：3888 处硬编码迁移过程必须有 grep 卡点防回退（v3 §8.1 验收）

**不重复 Spec A 已交付内容**：useStaleStatus 推 6 视图 / PartnerSignDecision stale 摘要 / AJE→错报转换前端入口 — 这些已经在 commit `b4cda44` 完成，本 spec 不重做。

---

## 范围（3 周工时）

### Sprint 1（1 周）— 字号变量化 4 批 + stylelint 卡点

按 v3 §8.1 规约：

| 批次 | 视图清单 | 工时 | 验收 |
|------|---------|------|------|
| 批 1 | WorkpaperEditor / WorkpaperList / WorkpaperWorkbench / DisclosureEditor / AuditReportEditor | 1.5 天 | 编辑器 5 视图 inline `font-size:` = 0 |
| 批 2 | TrialBalance / ReportView / Adjustments / Misstatements / Materiality / LedgerPenetration | 1.5 天 | 表格类 6 视图 inline `font-size:` = 0 |
| 批 3 | ProjectDashboard / ManagerDashboard / PartnerDashboard / QCDashboard / EqcrMetrics / Dashboard | 1 天 | Dashboard 系列 inline `font-size:` = 0 |
| 批 4 | 剩余 ~30 视图 | 1 天 | 全量 inline `font-size:\s*\d+px` = 0 |

**强制卡点**：
- `gt-tokens.css` 7 级字号变量（`--gt-font-size-xs/sm/md/lg/xl/2xl/3xl`）已就绪，仅扩充 metric 文档
- 安装 `stylelint-vue` + 自定义规则禁止 `font-size: \d+px` 内联
- CI 加 `npm run stylelint` step（如未装则 Sprint 1 第一天先装）
- baseline 1565 → 0，每批 PR 后 CI 强制 grep 数减少

### Sprint 2（1 周）— 颜色 + 背景变量化

按 v3 §8.2 / §8.3：

#### 颜色（1611 处）
- 补完 `gt-tokens.css` 5 个语义色 + 灰度 9 阶
- 4 批走（同 Sprint 1 视图分组）
- 验收：`grep -rE 'color:\s*#[0-9a-fA-F]{3,6}' src --include='*.vue' | wc -l < 50`

#### 背景（712 处）
- 定义 6 级背景：`--gt-bg-default/subtle/info/warning/success/danger`
- 4 批走
- 验收：`grep -rE 'background(-color)?:\s*#[0-9a-fA-F]{3,6}' src --include='*.vue' | wc -l < 30`

### Sprint 3（1 周）— GtEditableTable 瘦身 + 穿透菜单补完

#### A. GtEditableTable 职责瘦身（v3 §9.1）

**当前现状**（grep 实测 2026-05-16）：
- 仅 3 个文件使用：Adjustments.vue / InternalTradeSheet.vue / InternalCashFlowSheet.vue
- 组件本身 ~500 行，承担"列表展示+行内编辑+撤销+校验+全屏"多重职责

**拆分方案**：
- `GtTableExtended.vue`：基于 el-table + 紫色表头 + 字号 class + 千分位 + 空状态 + 复制粘贴右键菜单（**所有列表型表格走这个**，约 200 行）
- `GtFormTable.vue`：行内编辑型表格（dirty 标记 + 校验 + 撤销，约 250 行）—— 仅 Adjustments / InternalTradeSheet / InternalCashFlowSheet 用
- `GtEditableTable.vue` 改为兼容 wrapper（内部根据 prop `mode='display'|'edit'` 路由到上面两个），**不立即删除**避免 breaking 改动

#### B. CI baseline 卡点

- `<el-table` 直接使用 baseline = 当前实测值（grep 后填入）
- 新视图必须用 `GtTableExtended` 或 `GtFormTable`，禁止裸 `<el-table` 起新表

#### C. 右键穿透菜单补完（v3 §7.6）

**已就绪**（无需改）：
- `TrialBalance` 右键 "查看关联底稿" ✅
- `ReportView` `relatedWorkpapers` API ✅
- `DisclosureEditor` 右键 "查看相关底稿" ✅

**待补**：
- `Misstatements` 右键菜单 "查看关联底稿"（按 standard_account_code 反查）
- `Adjustments` 右键菜单 "查看关联底稿"（按 line_items.standard_account_code 反查）
- 后端补端点（如缺）：`GET /api/projects/{pid}/misstatements/{id}/related-workpapers`

---

## 启动条件（Sprint 0 强制核验）

进入 Sprint 1 前必须完成以下 grep 核验，输出对比报告：

| 核验项 | 命令 | 当前快照 | 启动门槛 |
|--------|------|---------|---------|
| v3 P0 全部完成 | 看 docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md §6 表 | 13/13 ✅ | 必须 13/13 |
| Spec A 上线 ≥ 7 天 | `git log --since='7 days ago' v3-linkage-stale-propagation/` | 2026-05-16 完成 | ≥ 2026-05-23 |
| stylelint 装机 | `npm ls stylelint stylelint-vue` | 待装 | 必装 |
| `gt-tokens.css` 字号变量已就绪 | grep `--gt-font-size-` | ✅ 7 级齐 | 已满足 |
| `gt-tokens.css` 颜色变量补完 | grep `--gt-color-` | 部分齐 | Sprint 0 第一天补完 |
| inline `font-size:` 总数 | `rg "font-size:\s*\d+px" src/**/*.vue \| wc -l` | 1565（v3 §1 引用） | Sprint 1 baseline |
| inline `color: #xxx` 总数 | `rg "color:\s*#[0-9a-fA-F]" src/**/*.vue \| wc -l` | 1611 | Sprint 2 baseline |
| inline `background: #xxx` 总数 | `rg "background(-color)?:\s*#" src/**/*.vue \| wc -l` | 712 | Sprint 2 baseline |
| `<el-table` 裸用总数 | `rg "<el-table" src/**/*.vue \| wc -l` | 待 grep | Sprint 3 baseline |

**关键铁律**（v3 沉淀）：
- spec 创建前必须做"现状核验"，避免 Spec A 已落地的内容被重做（如 Spec A 已推 useStaleStatus 6 视图，本 spec 不重做）
- baseline 数字必须实测填入，不能凭 v3 文档引用
- 每 Sprint 结束后必须再跑一次 grep 核验，CI 卡点确保只减不增

---

## 风险与冲突

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| stylelint 规则太严导致 CI 红一周 | 高 | 低 | Sprint 0 第一天先把规则调到 warning 级，不阻断 PR；Sprint 1 末尾才转 error |
| 字号统一后视觉差异引入 review 工作量 | 中 | 中 | 每批 PR 配截图对比；token 命名遵循已有约定不动用户视觉记忆 |
| GtEditableTable 拆分破坏 Adjustments 行为 | 中 | 高 | wrapper 兼容 + 老组件保留 60 天观察期 + Adjustments 单测扩展（粘贴/撤销/dirty） |
| 字号迁移触碰 1500+ 处文件冲突 | 高 | 低 | 4 批小 PR + 严禁多人并行同视图；每 PR ≤ 50 视图 |
| Misstatements/Adjustments 关联底稿端点不存在 | 高 | 中 | Sprint 3 第一天先 grep 后端是否有 `related-workpapers`，缺则补 1 个端点（半天工时） |

---

## 不做清单（明确排除）

按 v3 §13：
- ❌ 暗色模式（先把 token 打实，Spec D 评估）
- ❌ 全局 Ctrl+K 搜索（用户实际诉求弱）
- ❌ 给 GtEditableTable 加新功能（先做接入率治理 + 拆分，新功能 Spec D 评估）
- 🟡 客户主数据 + 项目标签（R11 评估，业务诉求弱）

---

## 预期交付

- **代码**：Sprint 1 字号 token 化 + Sprint 2 颜色背景 token 化 + Sprint 3 GtEditableTable 拆分
- **CI**：3 个 grep 卡点（font-size / color / background）+ 1 个 stylelint job + 1 个 `<el-table` baseline
- **文档**：`docs/UI_TOKEN_MIGRATION_GUIDE.md` + `docs/COMPONENT_USAGE_GUIDE.md`（GtTableExtended vs GtFormTable 选择树）
- **回归**：截图对比 ≥ 30 个视图 + 全量 vue-tsc + getDiagnostics 0 错误
- **三件套补齐**：Sprint 0 末尾产出 requirements.md + design.md + tasks.md（届时再做）

---

## 与 Spec C 的并行关系

依赖面不重叠（Spec B 改样式 + 组件，Spec C 改后端聚合 + 前端容灾），可并行；建议同周启动同周结束便于 release 节奏管理。

冲突点：GtEditableTable 拆分影响范围与 Spec C 的"危险操作二次确认补漏"在 Adjustments 视图重叠；Sprint 3 启动前与 Spec C 团队对齐改动顺序（建议 Spec C 先合）。

---

**预期工时**：起草三件套 1 天 + 实施 3 周 = **22 个工作日**（不含上线前 UAT）。

下一步：v3 P0 全清 + Spec A 观察期满后，本 README 升级为完整三件套（requirements / design / tasks）。
