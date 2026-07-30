# Implementation Plan: F2 存货披露表与附注模块模板对齐

## Overview

5 个 Sprint：Sprint 1 修底稿披露表口径与切分（R1/R2）；Sprint 2 新增两版共用的数据资源表（R3）；Sprint 3 同步载荷 `ColumnDef.group` 化（R4 前置）；Sprint 4 后端贯通 + 附注模板幂等修订（R5/R4）；Sprint 5 回归与 Playwright 实测（R6）。

Sprint 1/2 只动前端披露表；Sprint 3 是 Sprint 4 附注渲染生效的前提（同步路径）；Sprint 4 的 seed 路径（7）与模板修订（8）互相独立但需一起验证。

## Task Dependency Graph

```
1 (R1 比例) ────────────────┐
2 (R2 切分) ────────────────┤
                            ├──> 10 (回归实测) ──> 11 (收尾)
3 (R3 纯函数) ──> 4 (上市)  ─┤
              └─> 5 (国企)  ─┤
                            │
6 (R3/R4 group 化) ─────────┤
                            │
7 (R5 seed 贯通) ───┐        │
8 (R4 模板修订) ────┴─> 9 ───┘
```

- `3` 阻塞 `4`、`5`（纯函数模型先行）
- `6` 依赖 `4`、`5`（数据资源子表列头随之加入）
- `9` 依赖 `7`、`8`（结构守卫需模板已修订、贯通已生效）
- `10` 依赖全部实现任务

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1", "2", "3", "7", "8"], "desc": "比例口径 / 小节切分 / 数据资源纯函数 / seed 贯通 / 模板修订（互不相干）" },
    { "wave": 1, "tasks": ["4", "5", "9"], "desc": "数据资源两版接入 + 附注结构守卫", "depends_on": [0] },
    { "wave": 2, "tasks": ["6"], "desc": "同步载荷 group 化（含数据资源列头）", "depends_on": [1] },
    { "wave": 3, "tasks": ["10"], "desc": "回归与 Playwright 实测", "depends_on": [2] },
    { "wave": 4, "tasks": ["12", "14", "15", "17"], "desc": "Sprint 6：勾稽 / 金额真源 / flat / 守卫（互不相干）", "depends_on": [3] },
    { "wave": 5, "tasks": ["13", "16"], "desc": "三件套接入 + 验证手段补齐", "depends_on": [4] },
    { "wave": 6, "tasks": ["11"], "desc": "收尾", "depends_on": [5] }
  ]
}
```

## Tasks

- [x] 1. R1 上市「按组合计提」比例口径修正
  - [x] 1.1 `useF2DisclosureListed.enrichS3`：`impairmentPct` 改 `safeRatio(r.impairment, r.balance)`
  - [x] 1.2 `s3EndTotal` / `s3PriorTotal`：`impairmentPct` 改 `safeRatio(impairment, balance)`，`balancePct` 保持 `balance ? 1 : 0`
  - [x] 1.3 UI 列 tooltip 标注「计提比例＝跌价准备÷本组合账面余额（源模板 F52=D52/B52）」；占比列同步加 tooltip
  - [x] 1.4 更新 `useF2DisclosureListed.spec.ts`：R1.1~R1.5 五条断言（12 tests 全绿）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. R2 上市小节切分与摊销说明
  - [x] 2.1 `useF2DisclosureListed` 新增 `s4AmortText` + item `F2-note-listed-note-amort`，纳入 `flushSave` keys 与 `persistNote`
  - [x] 2.2 `getSyncSnapshot` / `F2ListedSyncSnapshot` 增 `s4AmortText`
  - [x] 2.3 `buildF2ListedSubTableData._note_texts` 追加 `listed-note-amort`
  - [x] 2.4 `F2TabDisclosureListed.vue`：借款费用资本化从 (3) 卡片移出为独立 (4) 卡片，补源模板提示语；同卡片增「合同履约成本本期摊销金额的说明」文本框
  - [x] 2.5 更新编制提示 `details` 内容与小节编号（6 条）
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. R3 数据资源表纯函数模型
  - [x] 3.1 新建 `composables/f2DataResourceInventory.ts`：21 行模型 + `buildDataResourceRows` / `calcDrTotals` / `calcDrEnding` / `checkDrSubExcess` / `isDataResourceEmpty`
  - [x] 3.2 `variant` 区分第 12 行标题（上市「二、存货跌价准备」/ 国企「二、跌价准备」）
  - [x] 3.3 新建 `__tests__/f2DataResourceInventory.spec.ts`：P3~P5 + 空态 + 子项超额
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.9_

- [x] 4. R3 上市侧接入
  - [x] 4.1 `useF2DisclosureListed`：item `F2-note-listed-s8-data-resource`，读写 + `updateDrCell`
  - [x] 4.2 `F2TabDisclosureListed.vue`：新增「确认为存货的数据资源」卡片（段标题行加粗、`derived` 只读蓝字、子项超额黄字告警、空态 alert）
  - [x] 4.3 `getSyncSnapshot` + `buildF2ListedSubTableData` 增子表
  - _Requirements: 3.1, 3.4, 3.7, 3.8_

- [x] 5. R3 国企侧接入
  - [x] 5.1 `useF2DisclosureSoe`：item `F2-note-soe-s5-data-resource`，读写 + `updateDrCell`
  - [x] 5.2 `F2TabDisclosureSoe.vue`：新增同款卡片（编号 (5)，(3)(4) 之后）
  - [x] 5.3 `getSyncSnapshot` + `buildF2SoeSubTableData` 增子表
  - [x] 5.4 更新 `useF2DisclosureSoe.spec.ts`
  - _Requirements: 3.1, 3.2, 3.7_

- [x] 6. R4 同步载荷 ColumnDef.group 化
  - [x] 6.1 `buildF2ListedColumns`：存货分类 / 跌价变动 / 按组合计提（含续）改为 `group` + 子列 label；追加数据资源表列头
  - [x] 6.2 `buildF2SoeColumns`：存货分类（期末数/期初数）/ 跌价变动（本期增加 2 + 本期减少 3）；追加数据资源表列头
  - [x] 6.3 标签列 label 校准（分类表「项目」、国企变动表「存货种类」）
  - [x] 6.4 跑 `check_disclosure_columns_coverage.py` 与 `disclosureSyncUrlContract.spec.ts`
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 6.2_

- [x] 7. R5 seed 列元数据贯通
  - [x] 7.1 `disclosure_engine`：新增 `_carry_seed_column_meta`，在两处多表装配点（含降级分支）调用
  - [x] 7.2 新建 `tests/services/test_disclosure_engine_seed_column_meta.py`：透传 + 未声明零影响 + 不干扰 workpaper 投影
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 8. R4 附注模板幂等修订脚本
  - [x] 8.1 新建 `backend/scripts/fix/fix_note_inventory_structure.py`（`--dry-run` / `--check`）
  - [x] 8.2 上市 §五、9：9 张表 headers/columns/_column_groups、表名迁移、删 `header_label`、补空数据行、开发成本表头改「期末数/上年年末数」
  - [x] 8.3 国企 §八、10：2 张表列结构 + `text_sections` 追加
  - [x] 8.4 `--dry-run` 复核 diff 后正式执行，写 `_aligned_by` / `_aligned_at`
  - [x] 8.5 重复执行验证幂等（表数、`text_sections` 长度不变）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

- [x] 9. R4 结构守卫测试
  - [x] 9.1 新建 `tests/services/test_note_inventory_structure.py`：列数、`len(headers)-1 == len(values)`、无 `header_label`、表名唯一、`_column_groups` 区间不重叠且不越界
  - [x] 9.2 跑 `validate_note_template.py` + `test_note_template_row_type.py`
  - _Requirements: 4.6, 4.7, 4.8, 6.3, 6.4_

- [x] 10. R6 回归与实测
  - [x] 10.1 前端：`npx vitest --run` F2 披露相关 spec 全绿
  - [x] 10.2 后端：`python -m pytest backend/tests/services -k "note or disclosure"` 全绿
  - [x] 10.3 `npx tsc --noEmit` + Vite transform 200 校验两个 Tab 的 `.vue`
  - [x] 10.4 Playwright 实测：F2 上市 Tab 小节完整 + 数据资源表、国企 Tab；同步后附注存货章节两级表头与 TAB 页签
  - [x] 10.5 Word 导出抽验存货章节两行表头
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

## Sprint 6 — 复盘改进（A1~A5 / B1~B3 / C1~C2）

- [x] 12. R7 数据资源表 ↔ 分类表交叉勾稽（A1）
  - [x] 12.1 `f2DataResourceInventory.ts` 增纯函数 `buildDataResourceTieChecks(rows, classRow)`
        产出 4 条勾稽（原值期末/期初、跌价期末/期初），容差 0.01，全空则跳过
  - [x] 12.2 `useF2DisclosureListed` / `useF2DisclosureSoe` 暴露 `drTieChecks`（取 section1Rows 的 `data-resources` 行）
  - [x] 12.3 两个 Tab 的数据资源卡片顶部渲染差异告警（与 (2) `tieDiff` 同款 `el-alert` + `tie-warn` 风格）
  - [x] 12.4 `f2DataResourceInventory.spec.ts` 补 4 条勾稽 + 容差 + 空表跳过断言
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

- [x] 13. R8 三件套接入（A2 / B7）
  - [x] 13.1 核对 `F2SheetToolbar` 能否直接复用；不能则按其行为在两 Tab 内联实现
        （结论：`F2SheetToolbar` 面向单 sheet 表格，披露页是多区块 + 多文本域，
        故按其行为在两 Tab 内联实现 `useF2AiGenerate` + `AI_TARGETS` + `runAi`）
  - [x] 13.2 每个文本域 section 标题行右侧加「AI 辅助」（走 `useF2AiGenerate`，只读/不可用时禁用）
        上市 6 处 / 国企 5 处；后端 `_f2_inventory_main_ai._SUPPORTED_SECTIONS` 与
        `_SECTION_PROMPTS` 同步补齐 11 个披露 section（`soe-note-land` / `soe-note` 为新增），
        并把 5 条过于笼统的旧 prompt 按源模板与 15 号文口径补详（含「不得虚构」约束）
  - [x] 13.3 加 `F2ReviewChip`，`section-id` 用 `F2-note-listed` / `F2-note-soe`
        （实际取整 Tab 粒度而非 `-*` 逐 section：`F2ReviewChip` 按 section-id 拉复核线程，
        逐文本域会产生 11 条独立线程，复核人无法整页浏览）
  - [x] 13.4 加 `CycleImportExportDropdown`，多区块分 sheet
        新建后端 `_f2_disclosure_import_export.py`：**一区块一 sheet + 文本域集中
        「文本说明」sheet**，`F2-note-listed` 出 10 个 sheet（编制说明 / (1)分类只读 /
        (2)跌价准备变动 / (3)按组合计提×2 / (5)(6)(7)房企 3 表 / (8)数据资源 / 文本说明），
        `F2-note-soe` 出 5 个。三个区块形态：`rows`（数组）/ `override`（按类别名匹配的
        覆盖 map）/ `dr`（数据资源三来源列）。全部读写 `remark` 字段，与前端
        `useF2Disclosure{Listed,Soe}` 的 item_id 契约一致（测试逐条断言前端 PREFIX 存在）。
        三个 F2 路由分发到新模块（沿用 F2-1 的分发模式，不新建 router）。
        前端两 Tab 挂 `CycleImportExportDropdown` + `inject('reloadWorkpaperData')` 刷新。
  - [x] 13.5 补挂载测试断言三件套存在
        `__tests__/f2DisclosureAiReviewWiring.spec.ts`（13 tests）：AI 按钮数 == `runAi` 调用数、
        section 全在 `F2AiSection` 且有 `AI_TARGETS` 映射、`.ai-btn` 右对齐、`F2ReviewChip`
        section-id 正确、导入导出下拉 sheet/api-prefix/只读禁用 + `onImported` 重载接线、
        无残留 TODO；另有 `test_f2_disclosure_import_export.py` 44 条（前后端常量镜像 /
        workbook 结构 / 导出→导入往返 / 整表覆盖语义）；
        后端 `test_f2_ai_generate.py` 补 23 条（11 section × 支持性/端点 + 口径关键词）
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 14. R9 金额显示/录入回归单一真源（A5 / B1）
  - [x] 14.1 删除两个披露 Tab 的本地 `fmtAmount`，改用 `@/utils/formatters` + `displayPrefs`（或 `GtAmountCell`）
  - [x] 14.2 数据资源表可录入金额改 `el-input` + `wpAmountInput.ts` formatter/parser（千分符）
  - [x] 14.3 确认比例/计提标准/项目名称等非金额字段未被套用金额 formatter
  - [x] 14.4 核对 `F2FourTableSourcePanel.vue` 本地副本 → 记入遗留（超出本 spec，见「平台级发现」）
  - [x] 14.6 新建 `shared/WpAmountInput.vue`（`el-input` 承载千分符，替代无效的 `el-input-number :formatter`）
  - [x] 14.5 回归：数值断言与 Playwright 实测值不变
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 15. R10 房企单级表抑制凭空父表头（B2）
  - [x] 15.1 `ColumnDef` 增 `flat?: boolean` + `defineColumns` 透传
  - [x] 15.2 后端 `_extract_column_groups`：遇 `flat` 返回 `[]`（显式单级），无声明仍返回 `None`
  - [x] 15.3 F2 开发成本/开发产品/周转房 标签列加 `flat: true`
  - [x] 15.4 后端单测补三态；前端断言这 3 表 `_column_groups` 为空
  - [x] 15.5 🔴 **补 seed 路径（Sprint 7 纠正上一轮假绿）**：15.3 只改了**同步载荷**
        （`f2DisclosureSyncPayload.buildF2*Columns`），`note_template_*.json` 的 `columns`
        没加 flat → **seed 路径**（新建项目 / 重新生成附注）仍回退
        `_infer_groups_from_headers`。实测（无 flat 时）凭空造出：
        开发产品 `{本期,span2}+{期末,span2}` / 周转房 `{本期,span2}` /
        **开发成本 `{预计,span2}`**（把「预计竣工时间」与「预计总投资」凑成一组，上一轮未发现）。
        已在 `fix_note_inventory_structure.py` 给 5 张单级表的标签列补 `flat: true`，
        并把守卫从「只测同步载荷」扩到**直接跑 `_extract_column_groups(模板 columns)`**
        —— 上一轮的测试没覆盖 seed 路径才让它漏过去。
  - _Requirements: 10.1, 10.2, 10.3_
  - _Note: 与 `disclosure-columns-coverage-rollout` Task 1~3 同源，此处先行落地 F2 部分_

## Sprint 7 — 复盘二轮（用户："附注模块要跟着实际内容而变化"）

- [x] 18. R13 seed 路径与 guidance 补齐
  - [x] 18.1 5 张单级表标 `flat`（见 15.5）：开发成本 / 开发产品 / 周转房 /
        确认为存货的数据资源 / 存货跌价准备及合同履约成本减值准备（续）
  - [x] 18.2 14 张表全部补 `guidance`（此前 **guidance 全为 NO**，K1 已启用该范式存货漏了）；
        内容只取 15 号文条款 / 源 xlsx 红字括注 / 附注模版 md 的【】提示 / 证监会监管报告 /
        以「勾稽：」前缀标注的工具口径，并加测试断言每条 guidance 都有权威来源标记
  - [x] 18.3 **(3) 两组表的「或」互斥语义**：附注模版 md 行 2500「续：」/ **2511「或：」**
        表明按品类组合与按库龄组合是二选一（后者行标签为「1年以内」「1至2年」）。
        guidance 已写明互斥，并加断言守住。**底稿侧目前只有按品类组合的录入区块**，
        库龄组合两张表暂无数据来源 → 已记入 `disclosure-note-follow-actual-content` R4.5
  - [x] 18.4 headers 去 `<br/>`（「预计总<br/>投资」/「本期转回或转销<br/>…」）：
        `el-table-column :label` 与 Word 导出都不解析 HTML，留着显示字面量；
        源 xlsx（D67/B35/C35）本就是纯文本，md 的 `<br/>` 是表格排版残留
  - [x] 18.5 幂等脚本校验加固：flat/group 必须二选一表态、guidance 必备、
        headers 纯文本、headers 与 `columns[].label` 逐位一致
  - [x] 18.6 同步载荷侧「（续）」表补 `flat`，与模板两侧一致；
        前端加「每张子表必须在 flat/group 之间表态」+「列标签纯文本」两条契约
  - [x] 18.7 回归：后端 147 passed（结构 52 / Word 导出 / seed 列元数据 / 多区块导入导出 / AI）、
        前端 112 passed
  - [x] 18.8 **实测边界（重要，勿误读为已生效）**：对真实后端拉
        `GET /api/disclosure-notes/{project}/{year}/五、9`（投影后）实测：
        - `groups`：房企 3 表 + 数据资源表已是 `[]`（显式单级，✅ 同步载荷的 flat 生效）；
          但「存货跌价准备及合同履约成本减值准备（续）」仍为 **`None`** —— 18.6 改的是前端
          载荷代码，**既有项目库里的 `_sub_table_columns` 是上次同步写入的旧值**，不会回填
        - `guidance`：**全部 0 字**。18.2 补的是 `note_template_*.json`，只经
          `disclosure_engine._carry_seed_table_guidance` 在 **seed 路径**生效；
          该项目附注是**同步路径**产生的，`sub_table_data`/`_sub_table_columns` 里没有
          guidance，投影器（纯函数、无 IO）也不会回查模板
        → 二者同一根因：**模板改动不回流既有项目**。让既有项目也拿到 guidance 需要在
        三个消费方（模块页 / Word / 批量导出）加「无 guidance 时回退模板」，属平台级改动
        → 已纳入 `disclosure-note-follow-actual-content` R2。
        **本 spec 范围内的结论**：新建项目 / 重新生成附注即可看到 14 张表的 guidance 与
        全部显式 flat；既有项目待新 spec 的模板回流
  - _Requirements: 10.1, 10.2, 10.3, 11.1_

- [x] 19. R14 附注不跟随实际内容 → 独立 spec
  - [x] 19.1 取证：`note_section IN ('五、9','八、10')` 共 6 条记录，**仅 1 条**
        （被人工点过同步的项目）`sub_table_data` 有 9 张表，其余 5 条为 **0 张表**，
        界面显示的是 legacy `rows`/`_tables` 旧快照（3 张表 + 已删的 `header_label` 假数据行）
  - [x] 19.2 新建 `.kiro/specs/disclosure-note-follow-actual-content/` 三件套
        （R1 底稿保存自动同步 / R2 模板回流既有项目 / R3 收敛单一真源清 legacy /
        R4 空表「本期无此情形」+ 互斥组 / R5 过期可见可修 / R6 零回归；
        10 条 Correctness Property；11 个 Task 分 6 wave）
  - _Requirements: —（平台级，超出本 spec 范围）_

- [x] 16. R11 补齐验证手段（A3 / A4）
  - [x] 16.1 为 Property 1（计提比例口径）补 fast-check PBT；或修正 design 措辞（二选一，不留不实标注）
  - [x] 16.2 Word 导出实测：导出附注存货章节，确认「存货分类」为两行表头且合并单元格正确
  - [x] 16.3 勾选 tasks 10.5
  - _Requirements: 11.1, 11.2, 11.3_

- [x] 17. R12 守卫前移与脚本更名（C1 / C2）
  - [x] 17.1 `governance-checks.yml` 增 `fix_note_inventory_structure.py --check`
  - [x] 17.2 `validate_note_template.py` → `validate_note_docx_placeholders.py`（名实相符）
  - [x] 17.3 更新全部引用点（测试 / CI / 文档），确认无悬空引用
  - _Requirements: 12.1, 12.2, 12.3_

- [x] 11. 收尾
  - [x] 11.1 清理 `scripts/_tmp_*` 临时脚本与 dump
        （本 spec 产生的 18 个已删；根目录残留的 `tmp_f4*` / `tmp_h1*` / `tmp_note_fa*`
        属其它并发会话，未代删）
  - [x] 11.2 更新 `.kiro/specs/INDEX.md`
  - [x] 11.3 提交 —— **已随分层批次提交**（2026-07-30，用户确认口径）
        **按 spec 单独提交不成立**（实测：工作树 411 项、纳入 352 项，其中 f2 专属仅 8 个文件，
        但本 spec 的核心交付同时落在 `note_template_{listed,soe}.json` /
        `disclosure_engine.py` / `note_sub_table_projector.py` 这些**被 8 个在飞 spec
        同时修改**的共享真源上 → 按文件白名单切分必然「漏核心改动」或「误纳他人未完成工作」，
        按 hunk 切机器生成的 JSON 亦不可靠）。仓库历史本身也是按层分批（`feat(frontend)` /
        `test(backend)` / …），非按 spec。
        → 改为**按层 8 个 commit**覆盖全部改动（`work/2026-05-30-wp-specs`，未 push）：
        `21cdd06a` feat(backend) 42 / `f5debfa4` data(note-templates) 4 /
        `4678ec3b` test(backend) 31 / `02f122b8` feat(frontend/workpaper) 179 /
        `9a9cf12e` feat(frontend) 16 / `a2a4feb2` test(frontend) 63 /
        `1c3241af` ci 1 / `030d2535` docs(specs+steering) 16。
        提交前已排除疑似密钥/本地配置（0 命中）与产物/临时脚本（59 项，多为并发会话的
        根目录 `tmp_*`，仍留在工作树未跟踪）。

## Notes

- 附注模块行集合以附注模版为准，**不加**「委托加工物资」「发出商品」（见 design「行不动原则」）
- 两级表头不新建机制，复用 `ColumnDef.group → _extract_column_groups → _column_groups`
- 「其中」子项与父项是校验关系（`F9-10`）而非公式，父项独立录入
- 附注模板 JSON 体量大，修订必须走脚本（禁手改），且必须幂等

### 实测结论（Task 10.4，2026-07-29）

- 上市 Tab 8 小节齐备（(4) 独立卡片 + 摊销文本框、(8) 数据资源表），0 console error
- (3) 比例实测：组合 15.00% / 6.25%，合计 8.00%（`D/B` 口径）；占比列 20% / 80% / 100% 不变
- (8) 公式实测：合计 100+250=350；期末 100+40−15=125；期末账面价值 125−10=115；期初 100−10=90
- 国企 Tab 5 小节齐备，分类表「期末数/期初数」两级表头、变动表 8 列、数据资源段标题「二、跌价准备」
- 端到端：披露表 →「同步到附注」→ 附注模块 9 个 TAB 页签；「存货分类」渲染为
  `项目(rowspan=2) | 期末余额(colspan=3) | 上年年末余额(colspan=3)`，假数据行消失；
  数据资源表 21 行数值与披露表一致（350/375/365/340）

### 实测结论（Task 13，2026-07-29）

- Vite transform 200：两个披露 `.vue` + `useF2AiGenerate.ts` + `WpAmountInput.vue` +
  `f2DataResourceInventory.ts` 全 200（崩溃类以 Vite 为权威）
- 上市 Tab：6 个「🤖 AI 辅助」按钮全部 enabled、8 小节齐备、复核 chip 在，0 console error
- 国企 Tab：5 个 AI 按钮、复核 chip 在，0 console error
- **AI 点击→vLLM 端到端未在浏览器完成**：Chrome 实例被并发会话反复抢占（页面被导航走
  两次、token 过期产生一次 401）。改用后端断言覆盖（更硬且不受争用影响）：
  11 个 section 均在 `_SUPPORTED_SECTIONS`、均有 ≥20 字 prompt、端点均返回 200
- **测试抓出真问题**：`listed-note-category` / `listed-note-re` / `soe-note-category` /
  `soe-note-borrow` / `soe-note-amort` 5 条 prompt 仅 18~19 字（如「请撰写存货附注
  「分类说明」披露文字。」），过于笼统会诱导模型自造披露内容 → 已按源模板与
  15 号文口径补详并加「不得虚构」约束

### 多区块导入导出（Task 13.4，2026-07-29）

**设计**：后端 `_f2_disclosure_import_export.py` 用一张 `_Block` 表驱动导出/导入，
三种区块形态 `rows` / `override` / `dr`；`F2-note-listed` 出 10 个 sheet、
`F2-note-soe` 出 5 个。分发沿用 F2-1 模式接在既有三个 F2 路由里，不新建 router。

**两个必须记住的设计约束（均由测试抓出，不是预先想到的）**：

1. **DR 表只能按 `rowKey` 匹配，不能按行标签** —— 21 行三段骨架里「1.期初余额」
   「2.本期增加金额」「3.本期减少金额」「4.期末余额」在账面原值段与跌价准备段**同名重复**，
   按标签匹配会让跌价准备段静默覆盖账面原值段（`test_roundtrip_dr` 首轮即失败）。
   故 DR sheet 首列为「行标识(勿改)」= rowKey，次列才是可读标签。
   守卫：`test_dr_duplicate_labels_exist_hence_key_column_required`。
2. **override / dr 是整表覆盖** —— 清空某行 = 撤销该类别的手工覆盖（回归 F2-1 自动取数）；
   但整表一个数都没填时返回 `filled=0`，上层跳过写库，避免「拿空模板只导文本」误清既有覆盖。
   note 文案已写明，`test_override_note_documents_whole_table_semantics` 守文档实现一致。

**双真源风险与守法**：后端镜像了前端 4 组常量（上市 9 类 / 国企 13 行 / DR 21 行 /
sourceKeys）。`test_f2_disclosure_import_export.py` 直接正则读 `.ts` 源码逐条比对，
改前端漏改后端会立刻红。

**live 往返实测**（真实 9980 后端，`scripts/_tmp_ie_live.py`，已删）：
export-template 200（上市 10 sheet / 国企 5 sheet）→ export-data 200 →
改一格覆盖值 + 一个文本域 → import-data 200（上市 13 项 4 区块 / 国企 6 项 2 区块）→
再 export 读回 `43210.99` 与文本 probe 完全一致。
实测写入演示项目的 4 项 probe 数据（两个 `note-category`、两个 `s2-overrides`）
已用清理脚本还原为空 / `{}`，并经 postgres 复核。
浏览器实测：两 Tab「导入导出 ▾」渲染、可用、0 console error。

### 已知遗留（低优先，非本次引入）

1. **房企 3 表被平台通用前缀推断加了「本期」父表头**：`开发成本`/`开发产品`/`周转房`
   在源模版是单级表头，但 `note_sub_table_projector._infer_groups_from_headers` 会把
   `本期增加`/`本期减少` 归到推断出的「本期」父级。该推断是平台通用兜底（多个循环的
   扁平 `columns` 依赖它还原两级表头），收紧门控会造成跨循环回归，故本 spec 不动。
2. **`sheet_name` 口径**：`f2NoteSectionMap.spec.ts` 原断言 `F2-note-listed`，与平台
   统一约定（源 xlsx 中文 tab 名，见 N1/K1~K13/J1/I3~I6）不一致 → 已改测试对齐代码。
   `f3NoteSectionMap.spec.ts` / `d1NoteSectionMap.spec.ts` 存在同类漂移，未在本 spec 修。
3. **`validate_note_template.py` 校验的是 docx 模板的 `【` 占位符**，与本次改的 JSON
   无关，其 29/103 项失败为既有基线；本 spec 的有效守卫是
   `test_note_inventory_structure.py` + `fix_note_inventory_structure.py --check`。
   （Task 17.2 已更名为 `validate_note_docx_placeholders.py`）
4. ~~披露页导入导出需后端多区块支持~~ → **Task 13.4 已实现**，见下「多区块导入导出」段。
   其它循环的披露 Tab（K1/J1/L1/L3/H4…）可复用同一范式，属
   `disclosure-columns-coverage-rollout` 之外的独立推广项。
5. **孤儿 item_id `F2-note-listed-s5-dev-costs`**：库中存在 2026-07-15 的历史记录
   （值 `[]`），前端现用 `s5-rows`。属早期改名残留，不影响读写（前端只读 `s5-rows`），
   清理需批量脚本，未在本 spec 处理。

### 🔴 平台级发现（Sprint 6 实证，需另立 spec 收口）

**`el-input-number :formatter` / `:parser` 是空操作** —— element-plus **2.13.6** 的
`es/components/input-number/**` 编译产物中不存在 `formatter` / `parser` prop（全文检索无命中），
挂上去只是未知属性，**千分符从未生效**。

- `composables/wpAmountInput.ts` 的用法注释写错（写成「用于 el-input-number 的 :formatter」）
- 受影响（千分符实际未生效）：`K1TabDisclosureListed` / `K1TabDisclosureSoe` /
  `K1StageEclTable` / `E1TabCashCount` / `E1TabCreditReport` 等，合计 40+ 处
- 本 spec 的处置：新建 `shared/WpAmountInput.vue`（`el-input` 承载，Playwright 实测
  失焦显示 `1,234,567.50`、聚焦显示原始值、粘贴带千分符可解析），并在 F2 数据资源表落地；
  存量 40+ 处替换超出本 spec 范围，建议单独 spec 用该组件统一收口
- `F2FourTableSourcePanel.vue` 仍有本地 `fmtAmount` 副本（不响应全局单位），同批待清

### ⚠️ 并发编辑风险（已实测发生）

执行期间检测到**另一会话正在改同一批文件**（`disclosure_engine.py`、
`note_template_listed.json`、`note_template_soe.json`；对应 in-flight 的
`k1-other-receivable-disclosure-alignment` / `d2-ar-disclosure-template-alignment`），
导致本 spec 对这三个文件的改动被回退一次、需重新应用。

- `disclosure_engine.py`：`_carry_seed_column_meta` 已重新加回（K1 会话的
  `test_k1_note_section_alignment.py` 也 import 该函数，本实现同时满足其两条断言；
  该测试另需 `_carry_seed_table_guidance`，属 K1 会话范围，未代为实现）
- 两个 JSON：重跑 `fix_note_inventory_structure.py`（幂等）即可恢复
- **未执行 commit**：工作树含大量其它 spec 的未提交改动，单 commit 会误纳
