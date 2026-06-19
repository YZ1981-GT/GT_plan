# A7–A15 完成阶段底稿（关联交易→持续经营）

## 背景

A7–A15 是审计**完成阶段**核心程序组（A1 总程序表 seq 6–11），共 **26 个物理文件**（`_index.json` 已核对），含 **套娃 sheet**（A11 bundle 内 3 sheet、A13 单文件 8 sheet 等）。

> **audit-xlsx**：**26/26 完成** ✅ → 权威列映射见 `backend/data/a7_a15_xlsx_audit.json`；程序表步骤见 `procedure_table_templates.json`（**非**运行时解析 xlsx）。

本 spec 参照 **A17/A18**：先定实物格式 → 再定运行时 componentType → 再定交付分期。

**相关 spec**：

- **公共 PRE / 持久化 / 联动** → [completion-phase-infra](../completion-phase-infra/requirements.md)
- 子 spec（可选独立 PR）：[A13 套件](../a13-misstatement-workpaper/requirements.md)、[A14 缺陷族](../a14-control-deficiency/requirements.md)

---

## 前置依赖

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)（PRE-1~4、checkCompletion、issue_tickets）。  
> 本 spec 增量：**PRE-4 阶段 3~4**（A11-2/3、A14-1、A15-1）；**audit-xlsx ✅** 不阻塞 lite。

| 依赖 | 本 spec 阻塞范围 |
|------|------------------|
| PRE-1/3 | 7 个 docx 弹窗（lite smoke 三件套） |
| PRE-2 | A8 export-word（plus） |
| PRE-4 阶段 3~4 | A11-2/3、A14-1、A15-1 checklist（core） |
| audit-xlsx | ✅ 已完成 |

---

## 适用条件

- 程序表步骤 `applicable_categories: ["A","B"]` → 与 `ProcedureTableService._check_applicable` + `business_category_service` **同一套机制**
- **A10** I/J/K 列 = 综合性问题 / 组织架构 / 循环问题（适用标签，非 ref_index）
- **A13** seq2.x L 列 = 上市公司；**A15** seq13 非上市 / seq14 上市
- **A11** 程序 sheet 脚注：纯财报 1–17 / 纯内控 18–23 / 整合审计全做
- **A14-5/6**、**A11-3** = plus 或整合审计场景，lite 不阻塞

---

## 交付分期

| 分期 | 范围 | 验收标准（DoD） |
|------|------|----------------|
| **audit-xlsx** | 26 文件深读 + JSON diff | ✅ 已完成；audit JSON + procedure_table 对齐 |
| **lite** | 9× 程序表 HTML + 7 docx 弹窗 + ref_index + A14 适用性 | 程序表可操作；**smoke 三件套** docx 下载成功（见下）；A13-1 汇总有数据时非空 |
| **core** | A13 Tab、A11 分流、A10-2/A14-1~4/A15-1/A7-2 HTML | A13 ≥2 Tab 可保存；A15-1/A14-1 checklist 可保存；A11 双轨不串路由 |
| **plus** | A14-5/6、摘要 API、A8 export-word、跨模块联动 E2E | A8-1/2 导出无蓝【】残留；A14→A9 提示可用 |

**Out of scope**：程序表改回 Univer 编辑；A11-1 docx 与 xlsx 审定表共用同一路由。

**lite docx smoke 三件套**（最小 E2E，覆盖标准路径 + 边界）：

| wp_code | 验证点 |
|---------|--------|
| A8-1 | 标准路径：seq2 chip → prefilled-download；含 client_name/年度 |
| A9-1 | PRE-1 边界：文件名 **无空格** 前缀 fallback |
| A10-1 | 大文件：142 段 + 10 表可下载；guidance 按节锚点可见 |

---

## 已知陷阱（audit 结论，实施时勿踩）

| 陷阱 | 影响 | 处理 |
|------|------|------|
| A11-1 编号冲突 | docx 问询函 vs xlsx 审定表同名 | 双轨路由，见 §7 / design §sheet 路由 |
| A8 列偏移 | K=索引号（非 H） | JSON ref_index 为准；diff 脚本 ● 仅 A8 |
| A14-2 首 sheet 误标 | 物理文件内 sheet 名写 A14-4 | 以 audit JSON sheet 顺序为准 |
| A14 seq2 xlsx 乱码 | 程序表 H 列预填损坏 | ref 以 JSON 为准 |
| A14-1/2/4/5 示例 sheet | `example-skip` | 不注册 runtime |
| A10-1 / A8-2 | 不宜做 A17-1 章节 HTML | 弹窗 + Word 自由编辑 + export（PRE-2） |

---

## 底稿清单（26 物理文件 + 套娃 sheet）

| 索引 | 实物 | 格式 | sheet | 规划 runtime | 分期 |
|------|------|------|-------|--------------|------|
| A7 | 关联交易程序表 | xlsx | 1 | a-program-console | lite |
| A7-1 | 汇总关联方交易及关联往来 | xlsx | 1 | univer → HTML 表格 | lite/core |
| A7-2 | 关联方交易附注披露信息 | xlsx | 2 | c-note-table | core |
| A8 | 其他信息程序表 | xlsx | 1 | a-program-console | lite |
| A8-1 | 管理层书面声明 | docx | — | wp-popup-docx | lite |
| A8-2 | 其他信息比对记录 | docx | — | wp-popup-docx | lite |
| A9 | 内部控制建议程序表 | xlsx | 1 | a-program-console | lite |
| A9-1 | 致管理层沟通函 | docx | — | wp-popup-docx | lite |
| A9-2 | 致治理层沟通函 | docx | — | wp-popup-docx | lite |
| A10 | 与治理层沟通程序表 | xlsx | 1 | a-program-console | lite |
| A10-1 | 与治理层沟通函 | docx | — | wp-popup-docx | lite |
| A10-2 | 与治理层的沟通记录 | xlsx | 2 | d-form-confirmation | core |
| A11 | 期后事项程序表 | xlsx | **6** | a11-bundle | lite/core |
| A11-1 | 期后事项问询函 | docx | — | wp-popup-docx | lite |
| A12 | 律师回复程序表 | xlsx | 1 | a-program-console | lite |
| A12-1 | 法律事务确认函及律师回复函 | docx | — | wp-popup-docx | lite |
| A13 | 错报（程序表及底稿） | xlsx | **8** | a13-bundle / Tab 套件 | lite/core |
| A14 | 内部控制缺陷程序表 | xlsx | 1 | a-program-console | lite |
| A14-1 | 内部控制缺陷汇总表 | xlsx | 2 | checklist-table | core |
| A14-2 | 企业层面控制缺陷评价 | xlsx | 3 | d-form-table | core |
| A14-3 | IT缺陷汇总及评价 | xlsx | 6 | **a14-3-workbook** | core |
| A14-4 | 业务流程层面控制缺陷评价 | xlsx | 8 | d-form-table | core |
| A14-5 | 与其他缺陷一同进行评价 | xlsx | 4 | d-form-table | plus |
| A14-6 | 非财务报告内部控制缺陷评价 | xlsx | 1 | e-control-test | plus |
| A15 | 持续经营程序表 | xlsx | **3** | a15-bundle | lite |
| A15-1 | 持续经营调查表 | xlsx | 2 | checklist-table | core |

**套娃 sheet 明细**（单文件多 sheet，runtime 路由见 design.md）：

| 父文件 | sheet | componentType |
|--------|-------|---------------|
| A11 | 底稿目录 | b-index |
| A11 | 审计程序A11（财报+内控） | a-program-console |
| A11 | 期后事项审定表A11-1 | d-form-table → **`A11-WP-1`** |
| A11 | 期后事项调查问卷A11-2 | checklist-table |
| A11 | 期后内控事项调查问卷A11-3 | checklist-table |
| A13 | 底稿目录 / A13错报程序表 / A13-1~5 | 见 §5 |
| A15 | 持续经营能力对审计报告影响决策图 | guidance-reference（不持久化） |

---

## 程序表列布局变体（audit 结论）

| 程序表 | header R5 索引列 | 适用列 | 额外列 | 步数 |
|--------|-------------------|--------|--------|------|
| A7/A9/A11/A12/A14 | **H**=索引号 | E | I=开机启动项（A7） | 见 JSON |
| A8 | **K**=索引号 | H | — | 10 + ●/5.x |
| A10 | **H**=索引号 | E | I/J/K 适用标签 | 11 + 子项 |
| A13 | **K**=索引号 | H | L=开机启动项 | 5 + 13 子项 |
| A15 | **H**=索引号 | E | — | 14 |

> xlsx H/K 列 ref 常为空；**chip ref_index 以 JSON 为准**。diff 脚本已处理 ●（仅 A8 展开）、（n）归一化（A11）、xlsx 乱码（A14 seq2）。

---

## 需求

### 1. 程序表（A7–A15）— `GtAProgramConsole`

- 步骤权威源：`procedure_table_templates.json`（**已全部对齐** A8–A15；A8 含 ●/内联子项规则）
- 打开 wp_code=A7~A15 程序表 xlsx → 运行时 **HTML**，不解析 live xlsx
- 各表 `ref_index` 见下表；`applicable=false` → chip 灰显

| 程序表 | 关键 ref_index | auto_data_source |
|--------|----------------|------------------|
| A7 | seq1→A7-1, seq6→A7-2 | — |
| A8 | seq2→A8-1, seq3→A8-2 | `reference_note` 20 项 |
| A9 | seq1→A14, seq2/4→A9-1,A9-2 | — |
| A10 | seq6→A10-2, seq7/4.8→A10-1 | — |
| A11 | seq1→A11-1 docx, seq2→A11-2 | — |
| A12 | seq1→A12-1 | — |
| A13 | seq3→A13-1; 3.1→A13-3,A13-5; 4/5→A13-4 | seq3 `misstatement_summary` |
| A14 | seq2→A14-2,3,4; 3→A14-5; 4→A14-1; 1→CX; 6→A14-6 | seq4 `control_deficiency_count` |
| A15 | seq1/4→A15-1 | — |

### 2. docx 弹窗（7 个）— `WpPopupDocxEditor`

加入 `wpPopupDocxConfigs.ts`（单一数据源）+ `INLINE_POPUP_WP_CODES` + 程序表 `ref_index` 三处同步（PRE-3）。

**适用性联动**（与 `ProcedureTableService` 契约，对标 A17 §1）：

- 步骤 `applicable=false` → chip **灰显不可点**，不弹窗
- 步骤 `applicable=true` 且子底稿未生成 → 弹窗内「下载模板编辑」
- 子底稿已有 OnlyOffice 实例 → 弹窗内在线编辑（当前 7 个均无实例，lite 走 prefilled-download）

| wp_code | chip 来源 | 结构要点 | 占位 / 颜色 | export 残留检测（plus/PRE-2） |
|---------|-----------|----------|-------------|------------------------------|
| A8-1 | A8 seq2（**条件适用**：其他信息审计报告日后取得） | 6 条声明 + 注释表 | 红=公司/年度；【审计报告日】 | 无蓝【】/注释表/201X |
| A8-2 | A8 seq3 | 5 章 + 封面表 + 文件清单 | guidance 引用 A8 `reference_note`（静态 JSON 20 项） | 无蓝提示/XX 日期 |
| A9-1 | A9 seq2 | 3 节沟通函 + 回签；文件名 **无空格** | 蓝【列明具体缺陷…】 | 无蓝【】残留 |
| A9-2 | A9 seq4 | 同 A9-1 结构 | 同上 | 同上 |
| A10-1 | A10 seq7, 4.8 | 1151 超大信函；142 段 + 10 表 | 蓝【请描述…】/【不适用的删除】 | 无蓝【】；guidance **按节锚点**导航 |
| A11-1 | A11 seq1 | 1332 问询函；38 段 + 1 表 | 红=ABC/202X；蓝【财务报表批准报出日】 | 无蓝【】/20X 残留 |
| A12-1 | A12 seq1 | 确认函 + 复函合一；23 段 + 5 表 | 红=201X；蓝=标准措辞（无【】） | 无 201X 残留 |

**文字颜色语义**（与 A17/A18 一致）：红=填写；蓝+【】=编制提示（export 删除）；黑=保留；注释表=export 删除。

**反例（明确不做）**：

- ❌ A8-2 / A10-1 做成 A17-1 / A18-2 式 structured HTML 章节编辑器
- ✅ 弹窗 guidance + Word 自由编辑 + export-word（PRE-2）

### 3. 核对表 — `checklist-table` + PRE-4

| wp_code | sheet | 结构 | 项数 |
|---------|-------|------|------|
| A11-2 | 期后事项调查问卷 | 序号/调查内容/适用情况/简要说明 | 13 + 签章区 |
| A11-3 | 期后内控事项调查问卷 | 同上 | 10 |
| A14-1 | A14-1控制缺陷汇总表 | R5+R6 双行表头；认定 6 列矩阵 | 动态行 + 注1/2 |
| A15-1 | 持续经营调查问卷 | 三章节问卷 + 调查结论 | 11+6+4 |

列映射以 audit JSON 为准；示例 sheet（A14-1/2/4/5）标记 `example-skip`，不注册 runtime。

**持久化契约**：见 [persistence.md](../completion-phase-infra/persistence.md)（A11-2/3、A15-1 固定问卷；A14-1 动态行 `A14-1-row-{NNN}` + remark JSON）。

### 4. 表单 — `d-form-table` / `d-form-confirmation`

| wp_code | 要点 |
|---------|------|
| A10-2 | 模板1：参与人+议题；模板2：5 列风险表（R9/R10 header） |
| A13-2 | 序号/错报说明/索引号/披露要求/金额/错报性质/不更正原因（18 行） |
| A13-3 | 错报合计矩阵（资产±…损益±）+ 重要性评价 + 前期错报节 |
| A13-4 | 错误/舞弊缺陷表 + 舞弊对审计影响 |
| A13-5 | 与管理层/治理层沟通记录 |
| A14-2 | 企业层面 Step1–4 + 初步结论（⚠️ 文件内首 sheet 误标业务流程/A14-4） |
| A14-3 | IT 缺陷汇总 + IT 评价 Step1–6 + 沟通纪要（**a14-3-workbook**） |
| A14-4 | 业务流程 Step1–7 + 结论 |
| A14-5 | T3 汇总评价（plus） |
| A11-WP-1 | 审定表：类别/期后事项/审计过程及结论/索引/备注 |

> A14 全族详设见 [a14-control-deficiency](../a14-control-deficiency/requirements.md)

### A13 Tab 套件

> 详设见 [a13-misstatement-workpaper](../a13-misstatement-workpaper/requirements.md)

- `wp_code=A13` → Tab：**程序表 | A13-1 汇总 | A13-2~5 表单**
- A13-1：`misstatement-summary`（三大错报块 + 底部合计表；借/贷双行表头）
- 非仅 `misstatement-summary` 单页（当前 override 待扩展）

### 6. 专用组件

| wp_code | componentType | 说明 |
|---------|---------------|------|
| A7-2 | c-note-table | 多 section 附注披露；需 section-aware parser |
| A7-1 | univer → HTML | 关联交易/往来汇总矩阵 |
| A14-6 | e-control-test | T4 非财报告 Step1–7 |
| A15 | guidance-reference | 决策图 sheet，仅 guidance 引用 |

### 7. A11-1 编号冲突（core 必做）

| 用户入口 | 实际底稿 | 路由 |
|----------|----------|------|
| 程序表 chip `A11-1` | 期后事项问询函.docx | INLINE_POPUP |
| 底稿目录 F=`A11-1` | xlsx 内「期后事项审定表A11-1」 | `{ sheet: 'A11-WP-1' }` |
| chip `A11-2` | xlsx 问卷 sheet | checklist-table / sheet 路由 |

### 8. 跨模块联动（plus）

完整矩阵见 [linkage.md](../completion-phase-infra/linkage.md)。本 spec 作为**数据源**的关键行：

| 下游消费方 | 数据来源 | P1 就绪 | 方式 / 备注 |
|------------|----------|---------|-------------|
| A17 持续经营章 | A15-1 调查结论 | ⚠️ | 程序表有；结构化结论 API 待建 |
| A17 舞弊章 | A13-4 + A14-1 | ❌ | 依赖 core 表单 + checklist |
| A17 沟通章 | A10-1 / A10-2 | ⚠️ | 弹窗 docx 有；摘要 API 待建 |
| A9 弹窗 guidance | A14-1 缺陷计数/等级 | ❌ | 依赖 core A14-1 checklist |
| A16 书面声明 | A8-1 / A13-5 索引 | ⚠️ | A8-1 弹窗有；A13-5 表单未落地 |
| A16-7 关联方 | A7-1 / A7-2 | ❌ | 依赖 core c-note / 摘要 |
| EQCR | A15-1 调查结论 | ✅ | EQCR going_concern Tab 只读引用 + A15-1 提示栏 |
| A18 议题3 | A8-2 完成状态 | ⚠️ | **手动提示**，无 auto sync |

---

## 关联模块

- A1 总程序表 seq 6–11（完成阶段入口）
- A16 管理层声明书（A8-1 可整合；A13-5 书面声明索引）
- A17 重大事项概要（A15 持续经营章节引用）
- A18 书面声明（A8 其他信息 vs A18 议题3）
- [completion-phase-infra](../completion-phase-infra/requirements.md) / [linkage](../completion-phase-infra/linkage.md)

---

## 现状与差距 — 已闭合（2026-06-18）

> tasks.md 51/51 全绿。下表记录实施结论，仅供追溯参考。

| 能力 | 代码现状 | 落地证据 |
|------|----------|----------|
| 26 文件 audit JSON | ✅ | `a7_a15_xlsx_audit.json` |
| procedure_table A7–A15 | ✅ | JSON 已对齐 + CI `--diff-only` 门禁 |
| 9× 程序表 HTML | ✅ | `_WP_CODE_OVERRIDE` + htmlRendererRegistry |
| 7 docx 弹窗 | ✅ | `wpPopupDocxConfigs.ts` + Playwright `docx-popup-e2e.spec.ts` |
| ref_index 全表 | ✅ | A9 seq2→A9-1/seq4→A9-2 修正；全部验证通过 |
| A14 applicable_categories | ✅ | seq3/seq6 加 `["A","B"]` + PBT 测试 |
| A13-1 misstatement-summary | ✅ | `MisstatementSummaryView.vue` + vitest |
| checklist_xlsx_parser | ✅ | `checklist_xlsx_parser.py` 783 行 + 单测 |
| A13 Tab 套件 | ✅ | `GtMisstatementWorkpaper.vue` + A13.yaml schema |
| A11 双轨路由 | ✅ | `GtA11Bundle.vue` tab=A11-WP-1 + `BUNDLE_SHEET_ALIASES` |
| A14-3 workbook | ✅ | `_WP_CODE_OVERRIDE["A14-3"] = "a14-3-workbook"` |
| d-form A10-2/A13-2~5/A14-2~5 | ✅ | override 注册 + schema YAML |
| export-word | ✅ | `docx_template_filler.py` + `wp_export_word` 端点 |
| 跨模块摘要 API | ✅ | `workpaper_summaries_service.py` + 3 key handler |
| CI audit diff 门禁 | ✅ | `.github/workflows/ci.yml` + `KNOWN_DIFF_ALLOWLIST` |
