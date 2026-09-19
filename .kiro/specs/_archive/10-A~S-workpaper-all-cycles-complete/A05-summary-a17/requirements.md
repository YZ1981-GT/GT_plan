# A17 重大事项概要底稿（上市公司 A 类业务）

## 背景

A17 是审计完成阶段最核心的综合性底稿——"重大事项概要"是整个审计项目的执行摘要，仅 A 类业务（上市公司/IPO/重大资产重组等）强制编制。涵盖 14 个子底稿，按功能分为：

- A17 程序表（xlsx，已有 a-program-console）
- A17-1 重大事项概要汇总（docx，核心文档，14 表+目录）
- A17-2-1 关键审计事项 KAM（docx，5 表结构化）
- A17-3/3-1 业务咨询记录（docx，弹窗）
- A17-4 重大专业分歧事项记录（docx，弹窗）
- A17-5-1~5-5 审计工作完成核对表（xlsx，5 个，共 770 行）
- A17-6 总结会会议纪要（docx，弹窗）
- A17-7/7A 独立性声明书（doc，已有 independence-signing）

## audit-xlsx（A17 专用）

> 产出 `backend/data/a17_xlsx_audit.json`；任务 **PRE-4-0 / X-A17** 在 [infra/tasks.md](../completion-phase-infra/tasks.md) **✅ 已完成**。

| 文件 | 说明 |
|------|------|
| A17 重大事项概要程序表.xlsx | 程序表步骤扩充来源 |
| A17-5-1 ~ A17-5-5 | 核对表 ×5（~770 行）；PRE-4 列映射权威源 |

**未完成前**：~~A17-5 parser 不得标绿~~（PRE-4-1 ✅ 已完成）。

## 前置依赖（阻塞项，须先于本 spec P0）

> **权威定义**：[completion-phase-infra](../completion-phase-infra/requirements.md)（PRE-1~3；PRE-2 阻塞 core/plus 导出）。

| 依赖 | 阻塞范围 |
|------|----------|
| PRE-1 | A17-3/4/6 弹窗下载 |
| PRE-2 | A17-core/plus Word 导出 |
| PRE-3 | 弹窗 chip + ref_index 三处同步 |
| PRE-4 阶段 1~2 | A17-5 核对表（lite） |

## 适用条件

- 程序表步骤使用 `applicable_categories: ["A"]`（与现有 `ProcedureTableService._check_applicable` + `business_category_service.get_category_prefix` **同一套机制**）
- **A 类业务**（`business_category` 前缀 `A`）：A17 程序表及各子底稿**强制适用**
- **B 类业务**：部分步骤/子底稿可选（程序表步骤级 `applicable_categories` 控制）
- **C 类业务**：默认不适用，可手动改回适用
- ⚠️ 不使用 `template_type == 'listed'` 判定 A17 适用性（该字段仅用于附注/报表模板，与 A/B/C 业务分类不同）

## 交付分期（避免一次性 27 任务绑死）

| 分期 | 范围 | 验收标准（DoD） |
|------|------|----------------|
| **A17-lite** | 弹窗 3/4/6 + A17-5 核对表路由 + 程序表适用性 | 弹窗能下载 docx；A17-5-1 能打开核对表并保存 |
| **A17-core** | A17-1 章节编辑器 + 章节取数 + Word 导出 | 写 1 章→刷新不丢→导出 Word 该章有内容、蓝色提示已删 |
| **A17-plus** | KAM 组件 + LLM + 报告 push + 完整性检查 | KAM 新增→导出；底稿→报告单向 sync 可用 |

**Out of scope（独立 spec，不纳入本 spec 任务计数）**：
- A17-7/7A 逐人确认弹窗 + B3 联动预警（已有 `independence-signing` 基础，增强面大）

---

## 需求

### 1. A17-3/3-1/4/6 — 弹窗模式

- 加入 `WpPopupDocxEditor` 配置（`wpPopupDocxConfigs.ts` 单一数据源）
- 弹窗：使用说明 + 预填充下载 + OnlyOffice 在线编辑（可用时）
- 程序表 chip 点击时弹窗展示（`INLINE_POPUP_WP_CODES` + `preventNavigate`）
- **适用性联动**（与 `ProcedureTableService` 契约）：
  - 步骤 `applicable=false` → chip **灰显不可点**，不弹窗
  - 步骤 `applicable=true` 且子底稿未生成 → 弹窗内引导「下载模板编辑」
  - 子底稿已有 OnlyOffice 实例 → 弹窗内在线编辑
- A17 程序表步骤须补 `ref_index` 指向 A17-3/4/6（当前 JSON 仅 2 步，**实物 xlsx 是 5 步**，须按实物扩充）：

  | seq | 程序（实物） | ref_index |
  |-----|-------------|-----------|
  | 1 | 汇总重大职业判断及需合伙人关注事项 | `A17-1` |
  | 2 | 重大会计/审计事项咨询，确定咨询报告恰当 | `A17-3`（+A17-3-1） |
  | 3 | 项目组专业意见分歧已解决并记录 | `A17-4` |
  | 4 | 识别重大职业判断及需合伙人关注（KAM） | `A17-2`（KAM 底稿 A17-2-1） |
  | 5 | 召开项目组总结会并记录会议纪要 | `A17-6` |

  > ⚠️ **A17-5 核对表不在程序表 5 步内**（实物程序表无指向 A17-5 的步骤）。A17-5-1~5-5 是独立核对表底稿，通过底稿目录/索引打开，不靠程序表 chip。旧 spec/JSON 的 seq2「编制完成核对表 ref A17-5」与实物不符，扩充时替换为上述 5 步。
  > seq4 ref 实物为 `A17-2`（不带 -1）；KAM 结构化底稿实际是 `A17-2-1`。

### 2. A17-5-1~5-5 — 核对表模式

- 按 `business_category` 选择适用版本：
  - 财报审计（A17-5-1）：所有项目必做
  - 内控审计（A17-5-2）：整合审计项目
  - IPO 特别程序（A17-5-3）：IPO 项目
  - 新三板特别程序（A17-5-4）：新三板项目
  - 函证程序（A17-5-5）：所有项目推荐
- componentType = `checklist-table`（复用 `GtChecklistTable.vue`）
- ⚠️ 模板格式为 **xlsx**（非 A1-15/16 的 docx），须新建 `checklist_xlsx_parser.py`，不可复用 `checklist_docx_parser.py`
- 5 个版本合计约 770 行；每个版本独立解析 + 注册
- 支持搜索、批量标记、进度统计（复用已有 `GtChecklistTable` 能力）

### 3. A17-7/7A — 独立性签署（仅确认现有能力，增强另开 spec）

- 确认 `_WP_CODE_OVERRIDE['A17-7'] = 'independence-signing'` 已生效
- **本 spec 不包含**：逐人确认弹窗、B3 联动预警（建议独立 `a17-independence-enhancement` spec）

### 4. A17-1 重大事项概要汇总 — 章节导航式 HTML 组件（核心）

- componentType = `a17-summary`（HTML 组件，非 OnlyOffice Word 编辑）
- **设计原则：编辑时结构化 HTML，交付时生成 Word**（与 DisclosureEditor 同一思路）
- 与 A18-2 共用「结构化函件编辑」模式（见 design.md §共享抽象）
- 章节结构（**16 章 + 附件**，从实物模板 A17-1 目录提取，**以实物为准**）：
  1. 审计业务约定范围及执行情况
  2. 独立性
  3. 对审计计划的更新和修改
  4. 需合伙人关注事项
  5. 业务咨询记录及专业意见分歧解决情况
  6. 对重大错报风险的应对措施执行情况
  7. 利用专家的工作
  8. 已审财务报表分析
  9. 对关联方及关联方交易的结论
  10. 基于持续经营假设的考虑
  11. 对期后事项形成的结论
  12. 拟在审计报告中沟通的关键审计事项（引用 A17-2-1）
  13. 其他信息
  14. 财务报表审计结论
  15. 其他特殊考虑事项
  16. 提请下年度审计关注事项
  - 附件（如适用）

  > ⚠️ 旧 spec 写的「11 章」是简化臆测版，章节名/顺序/数量均与实物不符。`a17_chapter_definitions.json` 必须按上述 16 章实物目录生成（item_id `A17-1-ch01`~`A17-1-ch16`）。

- **每章节功能（A17-core MVP）**：
  - 左侧目录导航（点击跳转）
  - **提示栏**（折叠面板）：编制说明/准则要求——**不导出**
  - 正文编辑区（textarea，纯文本+换行）
  - **「从关联模块拉取」**按钮（P1，仅已就绪数据源）
  - 引用标记（显示数据来源 wp_code）
- **每章节功能（A17-plus，后做）**：
  - 「AI 辅助生成」按钮（LLM + RAG）

- **文字内容分类规则**（致同模板通用，与 A18 一致）：
  | 类型 | 识别方式 | 编辑时展示 | 导出处理 |
  |------|----------|------------|----------|
  | 提示性/说明性 | 蓝色字体 / 【注：...】 | 提示栏（折叠） | **不导出** |
  | 需用户修改的 | 红色字体 / XX/201X | 正文区高亮 | 替换后导出 |
  | 固定正文 | 黑色字体 | 只读参考 | 原样导出 |
  | 用户填写的 | textarea | 正文编辑区 | 导出 |

- **章节数据来源映射 + 就绪状态**（按 16 章实物，仅列有自动取数的章节；未列出章节为纯手工填写）：
  | 章节 | 自动取数来源 | P1 就绪 | 备注 |
  |------|-------------|---------|------|
  | 1 约定范围及执行 | 项目信息 + B1/B5 约定书 | ✅ 项目信息可用 | 约定书摘要待 API |
  | 2 独立性 | A17-7 签署 + A10-1 沟通 | ⚠️ 部分 | 仅签署完成状态，无逐人明细 |
  | 3 计划更新 | B40~B60 变更 | ❌ | 需 risk 底稿摘要 API |
  | 4 需合伙人关注事项 | 各循环 + A17 程序表 seq1 | ❌ | 科目底稿未完成 |
  | 5 业务咨询及分歧 | A17-3/3-1 + A17-4 | ⚠️ | 弹窗 docx 有，摘要 API 待建 |
  | 6 重大错报风险应对 | B40 风险评估 | ❌ | 需格式化输出 API |
  | 7 利用专家的工作 | （手工） | — | 无自动源 |
  | 8 已审财务报表分析 | A1-13/A1-14 分析性复核 | ⚠️ | 依赖 analytical-review spec |
  | 9 关联方及交易结论 | A7 / A7-1 | ⚠️ | 计数可用，结论手工 |
  | 10 持续经营 | A15 / A15-1 | ⚠️ | 程序表有，结构化结论 API 待建 |
  | 11 期后事项结论 | A11 / A11-1 | ⚠️ | 弹窗 docx 有，摘要 API 待建 |
  | 12 KAM | A17-2-1 | ❌ | 依赖 A17-plus |
  | 13 其他信息 | A8 / A8-2 | ⚠️ | 弹窗 docx 有 |
  | 14 财务报表审计结论 | 审计意见 | ⚠️ | 报告意见类型可用 |
  | 15 其他特殊考虑 | A13 + A14 + issue_tickets（舞弊线索） | ⚠️ | issue_tickets 无 fraud 枚举，见 design |
  | 16 提请下年度关注 | （手工） | — | 无自动源 |

  > P1「拉取」仅实现 ✅/⚠️ 行；❌ 行保留按钮但 toast「数据源未就绪」。  
  > 完整联动矩阵：[linkage.md](../completion-phase-infra/linkage.md)（注：linkage 表内「ch07 舞弊/ch08 KAM/ch09 持续经营/ch10 沟通」的章节号是旧 11 章编号，须按本 16 章表重映射——舞弊→ch15、KAM→ch12、持续经营→ch10、其他信息→ch13）

### 5. A17-2-1 关键审计事项(KAM) — 结构化表单（A17-plus）

- componentType = `kam-workpaper`
- 5 个结构化区域（识别过程 / KAM 列表 / 3 要素描述 / 措辞审核 / 治理层确认）
- **与审计报告联动（分阶段）**：
  - **P3 MVP**：底稿 → 报告**单向 push**（底稿为权威源）
  - **P4+（可选）**：报告修订 → 底稿 stale 标记（不做双向实时 sync）
- **LLM 辅助（A17-plus，非 MVP）**：KAM 描述初稿生成
- remark JSON schema 见 design.md（前后端校验必选）

### 6. Word 导出（A17-core / A17-plus）

- 调用共享引擎 `docx_template_filler.py`（与 A18 共用，**不在本 spec 内实现**）
- A17-1：按章节组装 Word
- A17-2-1：动态 KAM 表格行
- 通用规则：蓝色删除、红色替换、注释表格删除、导出前未完成项检测

## LLM 集成要求（A17-plus，非 lite/core 阻塞项）

- 使用 `llm_client.chat_completion()`（httpx + 熔断器）
- RAG：知识库检索同行业 KAM 案例、概要范例
- Prompt：`backend/data/wp_llm_prompts/a17/`
- 生成结果为「建议稿」，用户编辑后采纳

## 关联模块

- B40~B50 风险评估（重大错报风险来源）
- A10 与治理层沟通（沟通记录来源）
- A13 错报汇总（舞弊线索）
- A14 内控缺陷（缺陷汇总）
- A15 持续经营（评估结论）
- A17-7 独立性声明（签署状态）
- issue_tickets（问题单，category 枚举见 design 映射）
- 知识库（A17-plus）
- 审计报告正文（KAM 段落，P3 单向 push）

---

## 现状与差距

> **2026-06-18 codegraph 实证**：core 基本闭合；plus 大部分落地；3 项前端缺口见下表「待做」。

| 能力 | 目标 | 代码现状 | 分期 |
|------|------|----------|------|
| A17 程序表 | 7 步 + applicable A | ✅ `procedure_table_templates.json` A17 7 步 | lite |
| A17-5 audit | a17_xlsx_audit.json | ✅ PRE-4-0 | lite |
| A17-3/4/6 弹窗 | wpPopupDocxConfigs | ✅ 配置 + `a17-lite.spec.ts` **E10** | lite |
| A17-5 checklist | PRE-4 + override | ✅ parser + `_WP_CODE_OVERRIDE` A17-5-1~5 | lite |
| 程序表 chip 灰显 | applicable=false → disabled | ✅ `GtAProgramConsole.isRowChipDisabled` | lite |
| A17-1 章节 HTML | a17-summary | ✅ `GtA17Summary.vue` 16 章 + debounce 保存 | core |
| 章节定义 JSON | a17_chapter_definitions.json | ✅ 16 章 | core |
| 章节拉取 | pull API + 按钮 | ✅ `a17_summary_service.py`（ch01 等 MVP；其余提示未就绪） | core |
| export-word | a17_word_exporter | ✅ `/api/a17/export-word` + `test_a17_word_exporter.py` | core |
| A17-2-1 KAM | kam-workpaper | ✅ `GtKamWorkpaper.vue` + registry | plus |
| KAM Word 导出 | A17-2-1 template | ✅ `A17WordExporter.export_kam` | plus |
| KAM→报告 push | 单向 sync | ✅ `a17_kam_push_service.py` + 单测 | plus |
| LLM 辅助 | ai-generate 端点 | ✅ `a17_llm_service.py` + GtA17Summary AI 弹窗 | plus |
| issue_hints UI | ch15 等提示栏 | ✅ `GtA17Summary` + issue-hints API | plus |
| A17-5 自动选版 | business_category | ✅ API + `GtAProgramConsole` 必做/推荐 badge | plus |
| E2E | E10/E11/E12 | ✅ spec 已写（`RUN_FULL_E2E=1` 待环境跑绿） | lite/core |

上游就绪度见 requirements §4 章节表及 [linkage.md](../completion-phase-infra/linkage.md)。
