# 致同审计作业平台 — Spec 开发索引

**最后更新**：2026-07-30
**当前分支**：`work/2026-05-30-wp-specs`
**统计**：Active 11（`.kiro/specs/` 实测目录数；本表已列 6 条，余 5 条待补）/ Archived 470 = 总计 481
**最高迁移**：**V133**（以 `migration_status` 实测为准）
**技术栈**：FastAPI + PostgreSQL + Redis / Vue 3 + Element Plus + Univer

---

## 〇、如何使用本索引

每个 spec 是一个目录，包含三件套文档：

| 文件 | 用途 | 何时读 |
|------|------|--------|
| `requirements.md` | 需求（用户故事 + 验收准则） | "要解决什么问题" |
| `design.md` | 设计（架构、数据模型、接口） | "怎么实现的" |
| `tasks.md` | 任务清单（`[x]`=完成 / `[ ]`=未做 / `[ ]*`=可选） | "做到哪了" |

**定位路径**：
- Active spec：`.kiro/specs/{name}/`
- Archived spec：`.kiro/specs/_archive/{分类}/{name}/`

---

## 一、Active Specs

新建 spec 放 `.kiro/specs/{name}/`。

| Spec | 阶段 | 说明 |
|------|------|------|
| `d2-ar-disclosure-template-alignment` | ✅ 全部完成（31/31，含交互实测，已提交） | D2 应收账款上市披露三层（底稿 / 同步映射 / 附注模板 五、5）对齐致同源模板：分类披露与单项计提恢复双期 6/5 列、组合分表双期 6 值列、补终止确认与继续涉入两表、10 节说明文本、旧表名清理机制。**Task 10 交互实测已补**（chrome-devtools + postgres MCP）：上市 TAB 正确挂载证明 wp_code 后缀分发修复生效，落库 §五、5 共 12 表、分类披露与续表各 6 列两级表头、`text_content` 10 节说明齐备；实测顺带修掉 `D2DisclosureNoteBody.vue` 缺 `portfolio` 说明文本域（AI 已备上下文却没有文本域 → 同步永远只落 9 节） |
| `f2-inventory-disclosure-template-alignment` | ✅ 全部完成（已随分层批次提交） | F2 存货披露表（上市/国企）与附注 §五、9 / §八、10 对齐源模版：(3) 计提比例口径修正（`D/B` 而非占跌价合计）、(4) 借款费用资本化拆为独立小节 + 合同履约成本摊销说明、新增「确认为存货的数据资源」21 行三段式表（两版共用）、附注两级表头 `_column_groups`、seed 列元数据贯通 `_carry_seed_column_meta`。**Sprint 6 复盘改进**：数据资源表 4 条 F9 交叉勾稽、金额真源收归 `displayPrefs.fmtAmount` + 新建 `shared/WpAmountInput.vue`（`el-input` 承载千分符，实证 `el-input-number :formatter` 是空操作）、`ColumnDef.flat` 三态抑制凭空父表头、PBT 9 条、修掉 `note_word_exporter._build_two_level_header_rows` 子表头右移丢末列的真 bug、CI 加 `note-inventory-structure` job、`validate_note_template.py` → `validate_note_docx_placeholders.py`、两披露 Tab 接入 11 处 AI 辅助 + 复核 chip（并按源模板口径补详 5 条过于笼统的 prompt）。**多区块导入导出**（新建 `_f2_disclosure_import_export.py`：一区块一 sheet + 文本域集中「文本说明」sheet，上市 10 sheet / 国企 5 sheet；DR 表必须按 rowKey 匹配因三段标签重复；override/dr 为整表覆盖但全空表跳过防误清；前后端 4 组常量镜像由读 .ts 源码的契约测试守）。前端 95 + 后端 123 测试全绿，live HTTP 往返 + Playwright 实测 0 console error。**11.3 已收口**：按 spec 单独提交实测不成立（核心交付落在被 8 个在飞 spec 同时改的共享真源上）→ 按层 8 个 commit 覆盖全部 352 文件（`21cdd06a`/`f5debfa4`/`4678ec3b`/`02f122b8`/`9a9cf12e`/`a2a4feb2`/`1c3241af`/`030d2535`，未 push）。⚠️ 并发会话曾回退 `disclosure_engine.py` 与两个 `note_template_*.json` |
| `disclosure-columns-coverage-rollout` | ✅ Task 1~16 全部完成（已随分层批次提交） | 披露表 `columns` 覆盖与两级表头推广。**基础设施**：`ColumnDef.flat` 声明 + `defineColumns` 透传；后端 `_extract_column_groups` 三态（`None`=未声明回退前缀推断 / `[]`=任一列 `flat` 显式单级 / 非空=显式分组），调用侧守卫写 `if col_groups is None` 防 `[]` 被推断抢占；F2 房企 3 表 + 数据资源表标 `flat` 消除凭空「本期」父表头。**守卫**：`check_disclosure_columns_coverage.py --strict` + allowlist `reason` 必填（空白视为未登记、不豁免）+ 守卫自测 10 条；CI job `disclosure-columns-coverage`。**批 1~4**：L1/L3（范式样板）→ K4~K7 → J1（补 `flat` + 收敛到共享 `ColumnDef`）→ H4（复用 `buildH2ListedColumns` 子集，不各造一份）；全 Tab 契约测试 `disclosureColumnsCoverage.spec.ts`（P1 键一一对应 / P2 标签列唯一居首 / P3 group 相邻 / P6 禁英文键当列头）；Playwright + DB 实测 K6 两版真两级表头（父表头串上市「期末余额/上年年末余额」vs 国企「期末数/期初数」不串味）+ K7 单级对照 + F2 四表 1 行表头。**并入 3 项遗留**：R6 账龄标签披露口径单一真源 `disclosureAgingLabels.ts`（D2/F1/F4/K1/G5/D3 六循环收敛，国企首档字面收归 `DISCLOSURE_AGING_WITHIN1_SOE`，守卫 15/15 `--strict` exit 0；D3 合计行字面为「合计」故不套 `合 计`）/ R7 动态子表名孤儿清理 `disclosureSyncedTables.ts`（同步**成功后**才 `markSynced`）+ R7.5 基线播种（实测 13 表→11 表清掉上线前残留、再同步 11→11 稳态）/ R8 `sheet_name` 断言漂移 10 条全改引用 `X_DISCLOSURE_SHEET_NAME` 常量（不写字面量，8 种括号写法并存）+ 守卫 `disclosureSheetNameRegistry.spec.ts` 6/6。**顺带修掉 3 个实质缺陷**：D2 披露 sheet 分发被 wp_code 后缀抢占（`附注披露信息（国企）D2-1` 被 `/D2(?:-\d+)?[A-Z]?$/` 抢先命中 → 披露组件此前完全挂不上，vitest 与 `get_diagnostics` 均查不出）、D3 国企静默校对读错字段恒为 0、`（续：期初数）` 续表键双真源。**🔴 跨 spec 交接（2026-07-30 实测）**：`--strict` 现报 98 调用点 / 92 覆盖 / 0 豁免 / **6 未覆盖**、exit 1 → CI job 当前为**红**；6 条全部是 `disclosure-sync-path-buildout` 新接线的 G 循环 Tab（`G12TabDisclosure{Listed,SOE}` / `G5TabDisclosure{Listed,SOE}` / `G8TabDisclosureBase` / `G9TabDisclosureBase`，调用点总数由 92→98 恰好 +6），本 rollout 自己的 14 个 Tab 全覆盖（批 4 收口时为 92/92）→ 红灯归属该 spec，列头补齐随其批 1 收尾（其 Notes 已记「新 builder 必须登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`」）；该 spec 批 1 已收口、6 条全部补齐，`disclosureColumnsCoverage.spec.ts` 复测转绿。**12.3 已收口**：按 spec 单独提交不成立 → 随同一批 8 个分层 commit 提交（清单见 `f2-inventory` 行） |
| `j1-disclosure-template-alignment` | 进行中：Task 1/2/12~15 完成（wave 1~2），wave 3~6 待做 | J1 应付职工薪酬披露三层对齐源模板（`backend/wp_templates/J/J1 应付职工薪酬.xlsx` 逐格精读 + `consol_note_sections_*` 印证；`note_check_preset_formulas.json` 无 J1 条目故裁决者退为 consol）。**已完成**：①附注模板幂等脚本 `fix_note_j1_employee_comp_structure.py`（`--dry-run`/`--check`，三连验证幂等）—— soe 八、40 第 3 表消重名（原与第 2 张同名 `短期薪酬列示` 而前端推 `设定提存计划列示` → **孤儿子表，模板第 3 表永空**）、6 表补 `columns`（标签列 `flat` 抑制「本期增加/本期减少」共同前缀被反猜出凭空「本期」父表头）+ `guidance`、listed 表2 删 `……` 占位行、`text_sections` listed 4→11 段（补源 xlsx R37/R38/R50/R53 四段说明 + R54 现金流量注）/ soe 3→7 段（原状只有 3 个 `###` 表标题 → 文本区 seed 恒空；设定受益计划交叉引用由过时的 八、47 改指 八、54）；②后端守卫 30 测试 + CI job `note-j1-structure`。**复盘增补 P0/P1 已修**：③**P0 三张表合计行从未推给附注**（组件传入的三个数组都不含合计行，合计是 composable 的 computed → 同步后附注三表全缺合计）→ 抽零依赖 leaf `j1DisclosureRowModel.ts`（消循环依赖，composable re-export 保既有 import）+ 载荷层 `withTotalRow()` 统一补（与 UI 合计同源、幂等无双合计）+ `J1_NOTE_TOTAL_LABEL='合计'`（模板字面无空格，底稿 UI 仍用源模板「合 计」）；④**P1 明细两表缺「从 J1-2 带入」**（短期薪酬 12 行 + 设定提存 8 行原需手打，而源模板每行都引 J1-2）→ 新建纯函数 `j1DisclosureDetailPull.ts`（两趟匹配消行序依赖 / 包含聚合最短 3 字防「其他」误吸 / 队列配对 / 国企 `absorb` 别名对齐 `B28=J30+J31` / 未匹配「其中：」子项跳过防双算）；⑤**P1 两披露 Tab 不可复核**（主入口已 provide 圆点但组件无触发器）→ Tab 级 + 2 个 section 级 `GtReviewTrigger` + 3 个取数追溯 `GtIndexChip`（顺带让原死代码 `import GtIndexChip` 变为实际使用）；⑥契约守卫接共享 helper `j1NoteSubtableContract.spec.ts`（正是能拦住孤儿子表的那条 P1）。测试：后端 30 + 前端 167（12 文件）全绿，6 个改动文件 Vite transform 全 200。**待做**：勾稽引擎 + 面板（源模板 8 条 Excel 公式关系）/ 父行 = Σ 缩进子行派生 / 上市辞退福利 placeholder 自造内容纠偏 / 国企说明拆 3 段 / 6 条 AI prompt 注册（现全落通用兜底）/ 抽 `J1MovementTable.vue`（6 份重复表模板）/ 浏览器实测 |
| `k2-other-current-assets-disclosure-alignment` | ✅ 全部完成（6 波 22 项）+ 浏览器实测通过，待 commit | K2 其他流动资产披露三层（底稿上市/国企披露表 / 同步映射 / 附注 §五、13 与 §八、14）对齐源模板。**改造前是自造结构**：上市 7 列变动矩阵（期初/增加/减少/期末/占比/备注）、国企 6 列（含变动原因），行名也是自拟（`预付款项-待转`/`理财产品`/`待摊费用`），而源 xlsx 与附注模版都是三列明细列示表；上市侧附注要求的「合同取得成本变动」「碳排放配额变动」两张条件性表底稿完全缺失。**已做**：①幂等脚本 `fix_note_k2_structure.py`（`--dry-run`/`--check`）—— §五、13 表②名从段落文本泄漏值改为「合同取得成本」且补回 md 重建丢掉的标签列 `headers[0]='项目'`、表③名从表头首格 `项  目` 改为「碳排放配额变动情况」并删 `header_label` 假数据行、4 张表补 `columns`（显式 `flat`，源模板单行表头）+ `guidance`（模版提示原文 + F13-1/F13-1a/F13-2 勾稽 + 数据来源）；②`k2NoteSectionMap.ts` 重写 —— **`sheet_name` 半角括号→全角**（与源 xlsx tab 名逐字一致，原值让附注「打开同步底稿」匹配落空）、子表名/历史表名/固定行名常量化、`buildK2ListedColumns`/`buildK2SoeColumns`、载荷推 3 表/1 表 + `_note_texts` + `_removed_table_keys`；③纯函数引擎 `useK2DisclosureEngine.ts`（合计/转置矩阵公式/勾稽，容差 0.01 元，审定数缺失即跳过不造假阳性）；④两版组件重写（固定行 + 动态行 `ElMessageBox.prompt`、`WpAmountInput` 千分符、条件性区块开关、勾稽 bar、上市文本三段各带 AI 且 prompt 写明「不得虚构」）；⑤守卫：契约 34 + 引擎 15 + 后端结构 16（含反向自检）+ `P1_ROUTE` 登记 + CI job `note-k2-structure`。**实测**（chrome-devtools + postgres 只读）：两版落库表数/列元数据/`flat`/`_last_sync_sheet`/`text_content` 全对，②表期末余额 105,000 = 100,000+30,000−20,000−5,000，关闭③开关后子表由 3→2（`_removed_table_keys` 生效）再开启复原。**顺带发现（另立 spec）**：K8~K13 六个循环的 `X_DISCLOSURE_SHEET_NAME` 同为半角括号而源 xlsx 是全角；K1 上市源 tab 名实为前半角后全角 |
| `n1-deferred-tax-disclosure-template-alignment` | 实现完成 + 实测通过，剩 3 项遗留 | N1 递延所得税资产披露三层（底稿上市/国企披露表 / 同步映射 / 附注 §五、30 与 §八、31）对齐致同源模板。**根因**：两个披露 Tab 原是**自造结构**（源模板一张表都没对上——7 列「已确认明细」+ 源模板没有的「余额变动表」「与 N3 对应关系」，缺表（2）与负债段，且把 N1-2 的审计过程列当披露内容）；附注模板表 1 的 5 列两级表头被 `rebuild_note_from_md.py` 压扁成 3 列并残留 `header_label` 假数据行，国企表 2 同样被压扁且**整张缺失**源模板（2）B「互抵明细」。**产出**：幂等脚本 `fix_note_deferred_tax_structure.py`（listed 4 表 / soe 5 表，两级表头 + `flat` 三态 + 全表 guidance + text_sections `####` 前缀）；`n1NoteSectionMap` 重写（5 表 + 子列序单一真源 `n1UnoffsetSubOrder` —— 🔴 **两版子列序在源模板里是相反的**，上市暂时性差异在前、国企递延所得税资产/负债在前）；新建勾稽引擎 `n1DisclosureConsistency`（规则全取源模板公式，含跨表 `B40=B52`）+ 面板 + 共用分段两级表头表组件 `N1DisclosureSegmentTable`。**顺带修 3 个真缺陷**：`el-input` 只绑 `@change` 时 EP 会在 nextTick 把 DOM 值重置回 `modelValue` → 用户键入被抹掉（实测行名落库为空串）；附注 TAB 编制提示对已同步项目永久为空（`guidance` 只在 seed 路径生效 → 新建读时回填 `note_table_guidance.py`）；`n1-linkage-fixes.spec.ts` 5 条长期红（测试桩缺 `getField`、入参名 `auditYear` 写成 `currentYear`、亏损 fixture 仍是 N1-5 重建前形状）。后端 66 + 前端 111 测试全绿 + CI job `note-deferred-tax-structure`；chrome-devtools + postgres 双向实测（0 表 → 4/5 表、两级表头子列序不串味、公式行与勾稽正确、自动同步落库）。**遗留**：guidance 回填的 live 端点复验需重启后端（本机 `--reload` 实测未生效）/ 附注编辑页 UI 未肉眼复验（打印预览遮罩 + 共享 Chrome 被并发抢占，已用端点+DB 实证替代）/ `disclosure_notes.source_template` 与章节号变体不一致（上市章节号记录标 soe，须单独立 spec） |
| `n-cycle-tax-disclosure-alignment` | ✅ 实现 + 实测全部完成（Task 1~10.1），仅剩 10.2 commit | N 循环税务类披露三层对齐源模板：N2 应交税费（五、41 / 八、41）、N4 税金及附加（五、63，**国企不披露**）、N5 所得税费用（三、所得税费用 / 八、78）。**改造前六个披露 Tab 全部无同步链路**（数据只停在 `checklist_responses`，附注永远拿不到），且都是自造结构：N2 上市误用国企变动口径（两组件复制粘贴）、N4 上市多出自造的变动额/变动率/变动原因三列、N4 国企凭空造了一整套披露表（源模板此节内容是「附注披露信息：无」）。**模板侧 md 重建缺陷**：八、41 被压成 3 列（源模板 5 列变动表）、N5 两版各有两张**同名表**（上市都叫 `项  目`=表头首格泄漏 / 国企都叫 `所得税费用`）→ 表名是 `sub_table_data` 的键，同名互相覆盖**丢整张表**、八、78 表 2 被压成 2 列丢「上期发生额」。**产出**：幂等脚本 `fix_note_n_cycle_tax_structure.py`（`--dry-run`/`--check`）+ 共用件提升（`shared/disclosure/WpDisclosureSegmentTable.vue` 新增 `column.readonly` 公式列、`WpDisclosureConsistencyPanel.vue`、`composables/shared/{disclosureSegmentTypes,disclosureConsistency,cycleSheetRouting,wpAiText}.ts`，N1 侧 re-export）+ 三份 `n{2,4,5}NoteSectionMap.ts` + 两份编制模型 + 勾稽引擎 `nCycleTaxConsistency.ts`（规则全取源模板公式，含 N2 国企逐行 `E8=B8+C8-D8` 与 N5 跨表相等）+ 5 个 Tab 重建 + N4 国企「本版不适用」说明页。**守卫**：后端 147（结构 + 进程内 ASGI e2e）/ 前端 N 循环 229 + 平台守卫 48 + N1 回归 216；CI 加 `note-n-cycle-tax-frontend`（12 spec）。**实测顺带挖出 3 个宿主缺陷**：`GtN2TaxesPayable` 分发用繁体「國企」（国企 Tab 从未渲染过）、**N2/N4/N5 三个宿主全都漏传 `projectId`** → 同步含自动同步永久静默失败（控制台只有 `Missing required prop`，vitest 与 `get_diagnostics` 查不出）→ 已补平台守卫「宿主必须给披露 Tab 传 projectId」（现存 126 处使用点全合规）。`MISSING_SYNC_PATH` 47→42 |
| `f1-prepayment-disclosure-template-alignment` | 实现完成 + 实测通过，待 commit | F1 预付款项披露三层（底稿上市/国企披露表 / 同步映射 / 附注 §五、7 与 §八、7）对齐源模板：两版按账龄表恢复 5 列两级表头 + 小计/减：减值准备/合计 三行尾、上市超1年表列结构改为「账面余额/占比/减值准备」（原因移入行展开区 + 据此生成说明）、国企第 3 张表消重名（原与第 2 张同名 → 孤儿子表）、上市第 3 张表名从「单位名称」改为完整表名并上报 `_removed_table_keys`、6 张表补 `columns`/`guidance`/空白行骨架、国企逐段减值准备同步时聚合为一行。幂等脚本 `fix_note_prepayment_structure.py`（`--dry-run`/`--check`）+ 存量回填 `backfill_note_prepayment_snapshots.py`（4 条空骨架已回填、1 条有数据按安全门跳过）+ 后端 44 测试 + 前端 58 测试全绿 + 国企底稿与附注 §八、7 Playwright 实测通过 |

---

## 二、已归档 Spec（448个，15 分类）

```
_archive/
├── 01-phase-foundation/              24
├── 02-workpaper-cycles/              16
├── 03-refinement-rounds/              9
├── 04-infra/                          2
├── 04-infra-architecture/            36
├── 05-business-features/            234
├── 06-engineering-governance/        13
├── 07-workpaper-slimdown/            22
├── 08-disclosure-notes/              19
├── 09-consolidation-phases/           5
├── 10-A~S-workpaper-all-cycles-complete/ 31
├── 11-confirmation-d0-module/        11
├── 12-2026-06-23-batch/              12
├── 13-2026-06-29-batch/              33
└── 99-superseded/                     4
```

### 最近归档（2026-07-29，12个已完成 spec 归档）

**→ 05-business-features（+9）**

| Spec | 说明 |
|------|------|
| advanced-query-consolidation | 高级查询模块合并收敛（12/12 全绿） |
| attachment-workpaper-linkage-convergence | 附件↔底稿联动收敛（V133 唯一约束+ensure_wp_link 幂等+反查去重+解除关联+证据类型声明+OCR 双轨归一；23/23） |
| f2-adjudication-import-export | F2 审定表导入导出（9/9 + 3.3* live 可选留待） |
| f2-detail-ledger-pull | F2 明细表序时账取数（11/11） |
| f2-four-table-extraction-refresh | F2 四表取数刷新（22/22，含灰度+Tier A 预设+面板+render 委托） |
| hi-cycle-four-table-extraction | H/I 循环四表取数（14/14，含 H5/H6/H7/H9/I1-I6 全铺） |
| lmn-four-table-extraction | L/M/N 循环四表取数（12/12 + 13* Playwright 可选留待） |
| template-library-formula-preset-custom | 模板库公式预设通用/自定义（16/16，含隔离存储+覆盖策略+权限门控） |
| work-hours-auto-collect-and-edit | 工时自动采集与编辑（18/18） |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| d-cycle-disclosure-note-enhancement | D3-D7 审定↔披露差异告警+批量同步（据实判定 Req1/Req2 对 D3-D7 冗余=cross-sheet-cell 恒等不接入；Req4 由现有「全部刷新」满足；产出 useDisclosureAdjudicationReconcile 通用工具；13/13） |

**→ 09-consolidation-phases（+1）**

| Spec | 说明 |
|------|------|
| consol-disclosure-note-persistence | 合并附注 V2 按项目灰度（note_formula_gray 镜像+wizard_state opt-in+灰度端点+P1-A(a) 删读端 schema 死字段；9/9） |

**→ 11-confirmation-d0-module（+1）**

| Spec | 说明 |
|------|------|
| confirmation-linkage-completion | 函证两价值孤儿正式做完（D0-4/D0-7 un-stub 从 D0-1 带入+dispatch_records 退役标 DEPRECATED+舞弊信号汇集 D0-8 真接线落 checklist_responses；19/19） |

### 最近归档（2026-07-27，本轮 8 个完成 spec 归档）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| disclosure-note-quality-completion | 附注模块质量完成：markdown 残留止血（前端 renderNoteTextToHtml + 生成侧 sanitize_note_narrative + 存量脚本 live 清 216 条）/ stale_source 诚实分级暴露 / linkage 诊断端点 + BS-002 示例 seed / consol V2 落库 SourceTemplate.consolidated AttributeError 修复；test_note_content_utils_sanitize 7 + test_note_readiness_and_stale 16 + test_consol_notes_v2_persist 24 全绿；灰度默认关零回归；已 commit+push `b57d713e` |

**→ 05-business-features（+7）**

| Spec | 说明 |
|------|------|
| confirmation-alternative-structure-alignment | 替代程序结构对齐九套（K0-5/K0-6/L0-5 渲染层拆借贷双表 + L0-5 期初一致性 + G0-6 区块对齐 + F05/F06 拆子组件 + L05 adapter passthrough 修复）；函证域 750 passed；Playwright 留待 |
| confirmation-hub-workbench-tabs | 函证枢纽底稿多 sheet 可达 + 台账双向导航 + E0 重建（B 方案）+ 路由与编码治理（sheet override 编码尾码优先解析）；前端 706+后端契约 35 passed；仅 8.2* Playwright 可选留待 |
| confirmation-shared-model-extension | 四张共享表行模型 additive 补列（ConfirmationRow/EntityVerifyRow/ReliabilityRow/DiffReconcileRow）+ 列配置驱动 + Master 简表回退/FullGrid 宽表分工修正；函证域 668+22 契约 passed；6.3 Playwright 留待 |
| e0-send-list-components | E0-3~E0-6 四张发函前清单审定 E0.yaml + 生成器 `_reviewed` 防覆盖 + 候选去重纯函数；54 passed；Playwright 留待 |
| g0-investment-diff-model | G0 证券差异表补 5 列 + 非证券三维差异专属组件（confirmation-diff-nonsecurities 全链注册）+ migrateAdjust 修复；g0 域 33+confirmation 691+注册 66+后端 29 passed+live round-trip PASS |
| g7-linkage-extraction-completion | G7 长投联动取数（底稿侧合并联动 + G7-2/G7-1 四表跨册取数 + 抽凭铺开 + 过期常驻提示 + G7-4 反向补录 + 主入口白屏 P0 修复）；26/26 全绿；灰度默认关 |
| trial-balance-version-timemachine | 试算表版本时光机（V128 snapshot 表 + TbSnapshotService create/list/restore/diff + SHA-256 dedup + 版本抽屉 + best-effort 快照不阻断 recalc）；8/8 全绿 + Property 1-8 PBT |

### 上一轮归档（2026-07-27，disclosure-note-linkage-completion 完成归档）

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| disclosure-note-linkage-completion | 附注模块联动链完成收口：①披露表保存后自动同步到附注（`useDisclosureAutoSync` 单一封装+全循环 24+ tab 铺开）②同步端点 URL 收敛为单一 canonical（H3/H4/H5/J1/D6 迁移+契约守卫）③合并附注 V2 落库激活穿透（`_persist_consol_sections_v2` provenance-only+灰度默认关）④stale_source 历史回填（221 行 report_fallback）⑤公式灰度按项目启用（`note_formula_gray_service`+就绪度看板暴露）；13 属性 P1-P13 全覆盖+live 端到端三流程验证 PASS |

### 最近归档（2026-07-26，13个已完成 spec 归档）

**→ 05-business-features（+11）**

| Spec | 说明 |
|------|------|
| adjustment-import-export-contract | 调整分录导入导出契约收敛（中央 overwrite by-key 幂等+示例行全等+汇总导出补类型列+7张底稿三重对齐 item_id/storage_field/field_keys+K12-3 JSON 迁移+双侧契约守卫；后端 265+前端 52 测试+live round-trip K3-3/中央三段 RESTORED_IDENTICAL）；已 commit `fb7921fc` |
| adjustment-detail-account-code | 调整分录明细行 `detail_account_code` 可空列（V127 迁移+前端 effectiveCode 优先匹配+导入保留明细码+recalc 零影响契约；后端 68+前端 16 测试+HTTP round-trip 100101 落库）；已 commit `fb7921fc` |
| h2-disclosure-linkage-and-prefill | H2 在建工程 P1 增强：披露表→附注结构化推送（buildH2SyncPayload 6/4 子表逐字对齐模板+12 vitest）+ 审定表从集中登记带入调整（1604 已接入+AdjudicationBringInDialog）+ H2-2 明细四表取数自动种子（后端 _build_h2_detail_prefill TB 叶子+Persist_First）+ H4 工程物资跨底稿勾稽（h2H4MaterialPull 纯函数）+ P0 四修（TB 叶子防双算+双模式 config 预拉+useNoteRefresh 1604+L1 JSON 键优先） |
| n1-loss-check-source-alignment | N1-5 按源模板重建（到期年度行+本期数三列+确认/不确认拆分+依据+来源三选+索引）+ 附注五、30/八、31 未确认一节数据源打通（deriveUnrecognizedLossPayload）+ IE 新列对齐 + N1-4/N1-1 跨表带入；7波全绿含 7.3* live round-trip |
| confirmation-attachment-ocr-linkage | 函证台账回函证据链（发函件/回函件上传+OCR识别比对+自动匹配+人工确认回填+状态撤回+一步退到底）；28/28 任务全绿 |
| f4-aging-enum-unification | F4 应付账款账龄接入平台枚举单一真源（3年段/5年段/自定义）：F4-2 扁平→nested keyed+F4-1段驱动+残差行+后端动态列头；23/24（仅7.3* Playwright留待） |
| h1-four-table-extraction | H1 固定资产四表取数扩展：H1-2 分类级 TB 叶子取数+明细增减↔序时账核对+折旧取数+related_parties注入+试算核对走规则映射；30/30 全绿 |
| h3-cross-workpaper-reconciliation | H3 投资性房地产跨底稿勾稽增强；9/9 全绿 |
| h4-four-table-extraction | H4 工程物资四表取数；10/10 全绿 |
| h5-disclosure-note-linkage | H5 生产性生物资产/油气资产披露↔附注联动（五、xx/八、xx）；7/8（仅8* live留待） |
| j1-disclosure-note-linkage | J1 应付职工薪酬披露表↔附注（五、40/八、40）结构化推送+正反向跳转+2211刷新+覆盖率守卫；12/12 全绿 |

**→ 08-disclosure-notes（+2）**

| Spec | 说明 |
|------|------|
| n1-disclosure-note-linkage | N1 递延所得税资产披露表↔附注（五、30/八、31）结构化推送+正反向跳转+2211 定向刷新+覆盖率守卫；N3 共用章节子表所有权方案 A（N1 独占四张表）；前端 288+后端 63 测试+live round-trip RESTORED_IDENTICAL |
| disclosure-note-formula-data-population | 附注表内公式数据补全（formula binding 119 条+合计标注 393 行+预设 995 条+附注侧 logic_check 61 条+只读诊断 linkage 缺口+契约守卫）；371 测试+真实项目 round-trip PASS；灰度默认 False |

**→ 05-business-features（+1，2026-07-27）**

| Spec | 说明 |
|------|------|
| trial-balance-cross-comparison | 试算表跨年度/跨项目对比（`useTbComparison` 外连接+差异高亮+SheetJS 导出，复用 GET /trial-balance 无新端点）；全 6 任务完成——Task 5 PBT+vitest 15 测绿（P1-P7，fast-check numRuns=20，含 zero-division/403 隔离/max5/零回归），Task 6* Playwright e2e 2 测 live 通过（真实栈 9980+3030/项目 0ec33ac9） |

### 上次归档（2026-07-25，活跃 spec 全部收尾归档）

**→ 05-business-features（+7）**

| Spec | 说明 |
|------|------|
| d-cycle-four-table-extraction-formulas | 四表库→D1-D7 底稿自动提取填充 + 公式管理可查可编（Tier B 复用 `_build_adjudication_prefill` / Tier A 可编辑标量；灰度默认关；160 测试绿+7 契约守卫；D6 真 seed 其余宁缺勿造） |
| d-cycle-tier-a-writeback-detail-seed | 前置 spec P0 增量：Tier A 编辑真生效（保存跳 parsed_data+返回 evaluated_value 不落库 + GET value + render transient TB核对行 seed 主机制，D1-D7 全铺）+ P0-2 明细维度归集 render transient seed（子开关 D6-2 试点）；332 测试绿+G6/G7/G8 守卫 |
| adjustment-collaboration-and-propagation | 调整分录多人协作接力（V125 两表+协作锁+复用 NotificationService）+ 明细表联动带入（Part B 无新表读时匹配，K8-2/K9-2 试点）；64 后端+18 前端测试绿 |
| deliverable-lineage-content-control | 交付 docx 章节内容控件化（Block Content Control Tag=`sec_xxx`）+ OnlyOffice 连接器真·光标跟随溯源；灰度+auto-follow 默认关；26 后端+32 前端测试绿（6* 连接器 live 验证 env-gated 留待） |
| balance-import-annual-column-semantics | 余额表导入年度优先+月度兜底（识别层区分年初/期初+本年累计 / 分类层年度=key月度=recommended / 转换层 `_first_decimal` 年度优先）；711 测试绿含 Property 1-15 PBT+三源契约守卫 |
| audit-check-review-gate-hardening | 「审计检查」升级为复核收口 gate（双通道写单一缓存 S1-S5 后端算+S6 前端上报 / 聚合运行时校验源复用口径不新造 / 通过率区分已判定vs未覆盖 / V126 签认只提示不阻断 / 零回归）；后端 475+前端 31 测试+P1-P14 全覆盖；**Playwright E2E 6 流程全绿（0ec33ac9）** |
| ledger-raw-extra-column-display | 账套导入非关键列进 `raw_extra` 后凭证/序时账/辅助明细查询作额外列显示（后端单一 helper `_attach_extra_fields`+前端动态列 el-table/v2/凭证明细）；复制 [object Object] 修复+列显隐⚙；后端 31+前端 29 测试绿+Playwright 真实数据通过 |

**→ 08-disclosure-notes（+1）**

| Spec | 说明 |
|------|------|
| disclosure-notes-selective-generation | 「生成附注」弹窗按附注实时树勾选章节+一键预设（只勾有数据科目）；唯一后端改动=树节点加 `has_data`（与 `_has_content` 收敛共享 `note_content_utils` helper）；导出零改动；后端 15+前端 8 测试绿+live 契约验证 |

### 最近归档（2026-07-24，全循环复盘收尾 + 基础设施加固）

**→ 05-business-features（+3）**

| Spec | 说明 |
|------|------|
| confirmation-coverage-single-source | 函证覆盖率口径修正（TB population 为分母+单一真源+死端点移除+孤儿组件清理） |
| workpaper-adjustment-centralization | 底稿调整→集中登记汇聚（V124+AdjustmentSyncService+全81循环接入+origin过滤防TB双计+a13死事件修复） |
| voucher-sampling-hardening | 抽凭引擎加固（DB级全量抽样框+方法学单一真源+批次状态机+服务端授权+LIKE转义，已push独立分支） |

**→ 06-engineering-governance（+1）**

| Spec | 说明 |
|------|------|
| attachment-ocr-ai-evidence-governance-hardening | 附件/OCR/AI/证据治理加固（65/66 任务；发布门 9 绿 + capacity 6000VU 待专用环境） |

**→ 08-disclosure-notes（+4）**

| Spec | 说明 |
|------|------|
| disclosure-table-sync-convergence | 披露表列头随 `_columns` 携带 + 后端单点投影（43/43 覆盖守卫 --strict 绿，全迁移 F2/F3/H9/H10/G/H/I/K/F1+GtCNoteTable） |
| d7-contract-liabilities-enhancement | D7 合同负债动态账龄全链路 + 调整分录按性质/账龄路由（13/13，复用 D3 机制零平行实现） |
| disclosure-note-formula-and-report-sync | 附注公式求值+报表→附注真同步+校验preset加载修复（20/20，灰度默认关零回归） |
| disclosure-note-validation-completion | 附注校验6 executor落地+ValidationContext数据装配（11类型全实现，Skip优于误报） |
| disclosure-note-knowledge-ai-enrichment | 附注RAG知识库接入AI正文生成（10/11，Task11前置不满足如实未做） |

### 最近归档（2026-07-19，工时模块重构）

**→ 05-business-features（+2）**

| Spec | 任务 | 说明 |
|------|------|------|
| workhour-entry-frontend | 6/6 | Phase7 细粒度工时填报前端入口（Dialog+List+ProjectView+路由） |
| workhour-table-unification | 8/8 | 两套工时表统一迁移（V117 数据迁移+审批改造+兼容层+WeeklyTimesheet 改写） |

### 上次归档（2026-07-18，26个 spec）

**→ 04-infra-architecture（+5）**

| Spec | 任务 | 说明 |
|------|------|------|
| acnr | 76/76 | ACNR 地址坐标名称库（五层模型+resolver+grammar） |
| acnr-consumer-wiring | 100/100 | ACNR 消费者接入（P1-P15全实现） |
| acnr-runtime-convergence | 25/25 | ACNR 运行时闭环修复（Phase1+2，509测试） |
| formula-runtime-convergence | 18/18 | 公式运行时真实写入/回滚/并发收敛 |
| platform-global-hardening | 79/79 | 全局工程治理（displayPrefs/GtWorkpaperShell/CI守卫） |

**→ 05-business-features（+5）**

| Spec | 任务 | 说明 |
|------|------|------|
| confirmation-alternative-factory-convergence | 13/13 | 函证 alternative 八套收敛为工厂（-47%代码） |
| d5-enhancement-polish | 15/15 | D5 应收账款底稿精美化打磨 |
| d6-enhancement-polish | 17/17 | D6 合同资产底稿增强打磨（列设置/勾稽/AI/结论模板） |
| d7-enhancement-polish | 15/15 | D7 合同负债底稿增强打磨（列设置/TB勾稽/公允判断） |
| procedure-delegation-notification | 17/17 | 程序委派通知机制 |

**→ 06-engineering-governance（+6）**

| Spec | 任务 | 说明 |
|------|------|------|
| procedure-delegation-visibility-isolation | 18/18 | 服务端 fail-closed 底稿可见性隔离（V113） |
| visibility-isolation-go-live-hardening | 8/8 | 可见性隔离上线加固（Go_Live_Gate=LIVE） |
| workpaper-maintainability-convergence | 37/37 | 底稿可维护性收敛（GtWpRenderer 465能力槽位） |
| workpaper-maintainability-convergence-followup | 36/36 | 可维护性收敛后续（FormData工厂化） |
| version-trail-full-coverage | 38/38 | 版本链全覆盖（89个D~N主入口+CI守卫） |
| ui-pattern-unification | 18/18 | UI模式统一（抽凭dialog-mode+版本链Toolbar） |

---

## 三、运维命令速查

| 需求 | 命令 |
|------|------|
| 代码规模 | `codegraph status` |
| 超标文件 | `python backend/scripts/check/check_file_size.py` |
| 最高迁移 | `ls backend/migrations/V*.sql \| sort \| tail -1` |
| 三件套完整性 | 扫描 `_archive/` 各 spec 目录是否含 requirements.md + design.md + tasks.md |

---

## 四、索引规约

1. 新建 spec 放 `.kiro/specs/{name}/`（扁平，不可嵌套）
2. 完成 spec 归档移到 `_archive/{分类}/`，同步更新本文件
3. 分类：01地基 / 02循环 / 03打磨 / 04架构 / 05业务 / 06工程 / 07底稿瘦身 / 08附注 / 09合并 / 10全循环 / 11函证 / 12 2023-06-23批 / 13 2026-06-29批 / 99取代
4. **凭印象禁令**：完成度必须实证
5. 迁移系统 = `backend/migrations/V*.sql`（MigrationRunner），新加必须 `IF NOT EXISTS` 幂等
