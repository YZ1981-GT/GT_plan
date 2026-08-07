# Implementation Plan: D 循环四表取数与披露附注收口

## Overview

5 个波次 30 个任务。W1 是全部后续工作的前置（取数不通，前端消费与联动 seed 都无数据可测）。

**开工前须知的三条实证**（详见 requirements.md 基线表）：

- `four_table/d_cycle_specs.py` 已存在且质量达标，本 spec 是它的第一个消费者，**不要重写它**，只改备抵槽 `names` 并加 `subject_keywords`
- **D7 是唯一有活体数据可验的循环**（那个 client 码为 `2204` 的项目，期末 7,855.34）；D5/D6 全库无数据，恒空是正确行为
- 附注 14 个主章节已由前序 spec 三向对齐，**不要重做行集与列结构**

**三个裁决门（W4 开工前需用户答复，未答复不得推进对应任务）**：

- 门 A（Task 23）D4 分解信息表改动态列时，既有 4 个硬编码行业列如何处置：① 保留旧列 + 追加动态列 ② 整表改动态 + 旧值按列名迁移、未匹配进 `legacy` 待归并
- 门 B（Task 22）孤儿重复章：① 只出 dry-run 报告 + 加守卫禁止指向 ② 经确认后 `--apply` 删除
- 门 C（Task 16）D6/D7 恒空的呈现：① 显示「本项目无此科目」灰态 tag ② 照常显示 `0.00`

## Tasks

- [x] 1. 备抵槽全名化与 `subject_keywords`
  - 改 `four_table/d_cycle_specs.py`：D1/D2/D6 备抵槽 `names` 改为带主体前缀全名，同时给出横杠与下划线两种写法
  - 给 `_provision` 辅助函数加 `subject_keywords` 参数并透传到槽
  - D6 备抵补第二候选兜底码 `1231-05`（standard 表 10 项目有定义）
  - D5 保持 `fallback=()` 不变，docstring 补「应收款项融资按名在两张科目表零命中」实证
  - _Requirements: 2.1, 2.2_

- [x] 2. 新建 `four_table/d_provision_filter.py`
  - `filter_provision_codes(codes, rows, subject_keywords) -> (kept, dropped)`，纯函数
  - `dropped` 每条含 `code` / `name` / `reason` 三字段
  - 专治 `account_mapping` 的 `1231.05 坏账准备_长期应收款 → 1231-02` `auto_fuzzy` 错映射
  - _Requirements: 2.3, 2.4_

- [x] 3. 新建 D2~D7 科目解析器与取数编排件（两个新模块，同一波交付）
  - **(a) `d_cycle_extraction/d_account_resolver.py`** —— D1 薄壳的参数化推广
    - D2~D7 各自的 `ReportLineAccountSpec`（`row_code` / 兜底码 / `provision_name_filter` / `is_liability`），参数取自 requirements.md 基线表的 DB 实证
    - 统一返回类型 `DCycleAccountCodes`，字段与 `D1AccountCodes` 同构（`gross`/`provision`/`gross_standard`/`provision_standard`/`resolved_from`/`provision_resolved_from`）+ 新增 `subject_keywords`
    - `resolve_d_cycle_account_codes(ctx, wp_code)` 委托既有 `report_line_accounts.resolve_report_line_accounts`，**不换解析器**
    - **D1 不动**（`d1_account_resolver` 与其守卫是零回归红线）；docstring 写明「D1 走自己的薄壳，两者委托同一共享件故口径一致」
    - `four_table/d_cycle_specs.py` 文件头补「当前不接线」的实证理由（Property 34）
  - **(b) `d_cycle_extraction/d_tb_fetch.py`** —— 取数编排，只串联不重造
    - `fetch_d_cycle_tb(ctx, codes, *, occurrence=False)`：`fetch_tb_subtree` → 备抵侧 `filter_provision_codes`（无条件）→ 逐前缀 `resolve_leaf_totals` → `fetch_trial_balance_rows` → `build_parent_check`
    - `build_d_tb_source_codes(...)`：四态（`found` / `tb_rows_count` / `prefix_mismatch` / `amount is None`）+ `dropped`/`warnings` + 向后兼容扁平投影
    - 🔴 `resolve_leaf_totals` 前不得 `select_leaves`（父行是符号约定的判定依据）
    - 🔴 `prefix_mismatch` 判据 = `query_codes` 含横杠 且 `tb_rows_count == 0`
    - 全流程 fail-open + WARNING（含 wp_code 与阶段）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.3, 2.4, 2.6, 2.7, 3.1, 3.2, 3.3, 3.6_

- [x] 4. `_d1_notes_receivable.py` 补齐载荷（**不动科目定位路径**）
  - 保留 `resolve_d1_account_codes` 与既有 `_net_tb_amount` / `_seed_tb_provision_amount` 逐字不变
  - 只做加法：`tb_source_codes` 补四态字段（`tb_rows_count`/`prefix_mismatch`/`dropped`/`warnings`）+ 新增 `parent_check`
  - 既有输出键（6 个 `tb_amount*`/`tb_provision_amount*` + `tb_amount_gross*`）逐字保留
  - 🔴 D1 是本 spec 的零回归红线，改动前后 characterization 必须逐字节相等（灰度关时）
  - _Requirements: 1.3, 1.6, 3.1, 3.2_

- [x] 5. `_d2_accounts_receivable.py` 接线
  - 硬编码 `1122`/`1231-02` 改委托 `resolve_d_cycle_account_codes('D2')`
  - **备抵必须无条件经名称过滤** —— 该循环是 `1231.05 → 1231-02` `auto_fuzzy` 错映射的唯一受害方，且既有 `use_provision_name_filter` 在此为 False 拦不住
  - 既有 6 个 `tb_amount*`/`tb_provision_amount*` 键逐字保留；补 `tb_source_codes` + `parent_check`
  - _Requirements: 1.1, 1.2, 2.1, 2.2, 2.3_

- [x] 6. `_d3_prepaid_accounts.py` 接线（🔴 **本波价值最高**）
  - **D3 当前完全没查自己的科目** —— 实证它只查了 D7 的 `2205%`（那是有意的 D3↔D7 交叉核对，落 `responses_snapshot['D3-d7-tb-audited-amount']`，**不要动**），而自己的 `2203` 一次没查 ⇒ `project_context` 无 `tb_amount` ⇒ D3-1 审定表拿不到 TB 核对数
  - 本任务补 `2203` 取数（`trial_balance` 实测 9 项目 / **77,338,768.39**），走 `resolve_d_cycle_account_codes('D3')`；`is_liability=True`（预收款项为贷方）
  - 写入 `tb_amount` / `tb_amount_unadjusted` / `tb_amount_audited`（与 D5/D6/D7 同键名，前端 seed 回退才能命中）
  - 客户子科目实证 `2203.01 预收货款` / `2203.02 预收项目款`，为 Task 26 的 seed 打基础
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 7. `_d4_operating_revenue.py` 接线
  - D4 已有 `D4AccountScope` + `build_d4_tb_values` + `tb_source_codes`，**是 D 类现状最完整的**→ 只做加法补 `parent_check`（`occurrence=True`）与四态字段
  - 损益类正方向按 `D_PL_POSITIVE_SIDE['D4'] == 'credit'`；确认既有 4 处 `select_leaves` 未被 `await`
  - _Requirements: 1.2, 1.6, 1.8_

- [x] 8. `_d5_receivables_financing.py` 接线
  - 硬编码 `1124` 改委托解析器；预期全部项目 `found=False` / `amount=None`，**不是 0**
  - 载荷须让「本项目无此科目」可见（该循环是四态之态 1 的唯一活体样本）
  - _Requirements: 1.1, 3.1_

- [x] 9. `_d6_contract_assets.py` 接线
  - 硬编码 `1141` 改委托解析器；备抵兜底 `1142` 与 `1231-05` 双候选
  - 🔴 预期形态是**态 2a**（`found=True` + `tb_rows_count=0` + `prefix_mismatch`）—— `1231-05` 在 `account_mapping` 零反解故保留横杠码，在点号体系的 `tb_balance` 必然命中 0 行。当前结果「恰好正确」但机理是碰巧，必须让它可见
  - 备抵不依赖 `IMP-004`（该报表行 formula 四准则全 NULL）
  - _Requirements: 1.1, 3.2, 3.6_

- [x] 10. `_d7_contract_liabilities.py` 接线
  - 硬编码 `2205` 改委托解析器 + 补 `tb_source_codes` 与 `parent_check`
  - ⚠️ **原「D7 取不到数」的判断已撤回**：D7 查的是 `trial_balance`（标准码体系），`LIKE '2205%'` 能命中 5 个项目 / 7,855.34（`trial_balance` 本就是 `account_mapping` 映射后的标准码）。本任务的收益是**消除硬编码 + 补溯源与三口径**，不是修取数 bug
  - 零回归判据：改造前后 `project_context.tb_amount` 在真实库上逐项目相等
  - _Requirements: 1.1, 1.2, 1.6_

- [x] 11. 后端守卫：规格证据与编排件纯函数
  - `tests/four_table/test_d_cycle_specs_evidence.py` — Property 7/34/35（连库快照用单次 `asyncio.run` 取全部数据后同步断言，禁每测试各自 async）
  - `tests/four_table/test_d_provision_filter.py` — Property 9/35，含反向自检（关键词写宽成「应收」必空转 / 不传关键词为空操作）
  - `tests/d_cycle_extraction/test_d_tb_fetch.py` — Property 4/5/10/33，含反向自检
  - 每条守卫写完必须真做一次变异检验（改一字看是否变红）
  - _Requirements: 2.1, 2.2, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3_

- [x] 12. 后端守卫：接线正确性与零回归
  - `tests/d_cycle_extraction/test_d_render_wiring.py` — Property 1/2/8/11（变量名无关判据 + `stripComments()` + 反向自检）
  - `tests/d_cycle_extraction/test_d_render_characterization.py` — Property 32 键集与取值零回归，**D1 单独一组逐字节断言**（零回归红线）
  - _Requirements: 1.1, 1.2, 1.3, 1.8_

- [x] 13. 真实库验收脚本与直跑
  - 新建 `scripts/diagnose/verify_d_cycle_extraction_live.py`（只读，逐项目逐循环输出 `resolved_from` / 金额 / `parent_check.diff` / `dropped`）
  - 直跑并逐条核对 design.md「真实库验收」5 条判据，D7 的 7,855.34 必须命中
  - **实测结果：8 项目 × 7 循环 → PASS / 判据违规 0**；四态分布 `{no_account: 24, no_data: 44, ok: 28}`；三口径差异 3 处（如实暴露，非违规）
  - **挖出并修掉一个真实 P0**（见下方 Notes「Task 13 实测结论」）
  - _Requirements: 1.3, 1.5, 2.5, 3.1_

- [x] 14. 前端 `composables/dCycleAccountScope.ts`
  - 委托平台共享工厂 `composables/shared/cycleAccountScope.ts`
  - `isAccountAbsent()` 区分「本项目无此科目」与「余额为 0」；render 未下发 ⇒ 返 false（未知不等于无）
  - 兼容 `slots` 与历史扁平两形态；无兜底码声明的槽 `queryCodes` 返空，绝不凭空造前缀
  - _Requirements: 3.1, 3.2, 3.3, 3.5_

- [x] 15. 7 个宿主补 `:html-data` 透传
  - `GtD1NotesReceivable` ~ `GtD7ContractLiabilities`，逐个核对模板传参
  - 注意：只改子组件不改宿主等于白改（平台已登记的「漏传 prop = 静默锁死」范式）
  - _Requirements: 4.2_

- [x] 16. 7 个审定表挂溯源面板 + TB 核对数 seed 回退
  - 7 个审定表全部挂平台共享件 `WpFourTableSourcePanel`（改造前**只有 D4 挂了**），属性名从被调组件 `defineProps` 动态抽取比对
  - 新建 `composables/dCycleTbSeed.ts`：`resolveTbAmountWithSeed` / `hasManualTbAmount` / `isTbSeedFallbackActive` / `parseManualTbAmount`（手工优先，判据是**原始 remark 是否为空**而非数值是否为 0）
  - D2/D3/D5/D6 四个 composable 接 `tbSeedAmount` 只读回退（D1/D7 改造前已有）
  - 「本项目无此科目」用 `info` tag（经 `dSlotStateTagType`）；`conflicts` 非空出告警条（面板内建）
  - **裁决门 C 已按方案 ①落地**（「本项目无此科目」灰态 tag，与平台宁缺勿造一致）
  - 🔴 **原任务描述「从四表库带入未审数」按实证收窄** —— 见下方 Notes「Task 16 实证修正」
  - _Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 3.4_

- [x] 17. 前端守卫：宿主传参与带入语义
  - `dHostPropWiring.spec.ts` — Property 13/14（从 SFC 动态抽 `defineProps` 转 kebab-case 比对，排除 `v-*`/`@`/`key`/`ref`/`class`/`style`）
  - `dCycleAccountScope.spec.ts` — Property 12/15，并读后端 `d_cycle_specs.py` 源码交叉锁死槽键与兜底码
  - `REPO_ROOT` 用双哨兵**具体文件**向上查找，禁写死回退级数
  - _Requirements: 3.5, 4.2, 4.4, 4.6_

- [x] 18. 公式预设幂等脚本：sheet 名与口径纠偏
  - 🔴 **本轮重建**（此前为假绿：脚本在磁盘上不存在、4 处旧 sheet 名在 HEAD 与工作树都仍在）
  - 新建 `scripts/fix/fix_d_cycle_prefill_presets.py`（`--dry-run`/`--check`/`--apply` + round-trip 自检）
  - (a) 4 处 sheet 名纠偏 **+ 公式实参里的旧 sheet 名同步改写**（只改块名会留下 `PREV('D0','审定表D0-1',…)` 指向不存在的 tab —— 守卫抓出的）
  - (b) D4 审定表「期初余额」改 `PREV()`（原与「未审数」公式逐字相同，损益类无期初余额）
  - (c) D5 审定表 4 格改 `PLACEHOLDER` + 实证说明
  - (d) **本轮新发现两处口径错**（spec 未列）：D2-3 的 `LEDGER('6602',…)` → `6702`（6602 是管理费用）、`LEDGER('1231','credit')` 本期核销 → `PLACEHOLDER`
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - 新建 `scripts/fix/fix_d_cycle_prefill_presets.py`，支持 `--dry-run` / `--check` / `--apply`，含 round-trip 自检（不能逐字复现原文即退出码 2）
  - 4 处 sheet 名纠正：`审定表D0-1`→`函证结果汇总表D0-1`、`函证汇总表D0-2`→`核实被函证单位信息D0-2`、`分析程序D0-3`→`跟函函证过程控制D0-3`、`分析程序D4-3`→`其他业务收入明细表D4-3`
  - D4 审定表「期初余额」改 `PREV()`（现与「未审数」同为 `TB_SUM('6001~6099','本期发生额')`）
  - D5 引用 `1124` 的公式改 `PLACEHOLDER` + 描述写明零命中实证
  - **校验器只扫语义字段**（`formula`/`formula_type`/`account_codes`/`applies_when`），禁对整块 `json.dumps` 做「不得出现 xxx」断言（description 里会如实写反例）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 19. 补明细表预设块与 `WP()` 联动
  - 🔴 **本轮重建**（此前为假绿：六个明细块在 HEAD 与工作树都不存在）
  - 新增 6 块：`预收账款明细表D3-2` / `应收款项融资明细表D5-2` / `应收款项融资公允价值测算表D5-4` / `明细表D6-2` / `合同资产减值准备明细表D6-3` / `明细表D7-2`
  - 审定表补 6 条 `WP()`：D2←D2-2/D2-3、D3←D3-2、D6←D6-2/D6-3、D7←D7-2（D1 已有作范式）
  - 明细块**禁**反向引用本循环审定表；跨循环引用（D0 函证覆盖率 ← D2 审定数）是**合法的**，守卫按此区分
  - _Requirements: 5.6, 5.8_
  - 新增块：D3-2 / D5-2 / D5-4 / D6-2 / D6-3 / D7-2
  - 审定表补 `WP()` 引用本循环明细表（D2←D2-2/D2-3、D3←D3-2、D6←D6-2/D6-3、D7←D7-2；D1 已有作范式）
  - 明细表块**禁**反向引用审定表（防成环）
  - **本任务曾是「假红」** —— 复选框标 `[ ]` 而 Task 18 的脚本已把它一并交付（该脚本 docstring 自述覆盖 Task 18+19+20）。2026-08-06 实证核对后勾选，详见 Notes「Task 19/20 实证核对」
  - _Requirements: 5.6, 5.8_

- [x] 20. 补 12 张披露 sheet 预设块
  - 新建 `scripts/fix/fix_d_cycle_disclosure_presets.py`（改造前**只有 D4 两张**有预设，其余 12 张零预设 ⇒ 公式管理页完全空白）
  - sheet 名逐字取源 xlsx tab 名 —— **六种括号写法并存且禁「统一」**（D6 上市侧是**前半角后全角** `(上市公司）`）
  - D5 一律 `PLACEHOLDER`（`1124` 零命中是业务事实）；D2 的 4 张 **hidden** 旧版披露表显式登记为「不建预设」
  - `--check` 0 欠账；mappings 258 → 270
  - _Requirements: 5.7_

- [x] 21. 公式预设守卫
  - `tests/test_d_cycle_prefill_presets.py` — **22 例全绿，7 个变异逐条打红并还原**
  - Property 16 用 openpyxl 直读源 xlsx `wb.sheetnames`（含 hidden）做 sheet 存在性判据
  - Property 18 抽码时**跳过区间端点**（`TB_SUM('6001~6099')` 的上界不是被引用科目）
  - `PLACEHOLDER_REGISTRY` 9 条逐条登记理由 + **stale 反向锁死**（已改成真公式的条目留在表里即红）
  - 🔴 **两条首版判据过严已修**（见 Notes「Task 21 判据修正」）
  - _Requirements: 5.1, 5.3, 5.4, 5.8, 5.9_

- [x] 22. 母公司附注章禁删锁死：只读诊断 + 守卫（🔴 立项判断已撤回，**不建清理脚本**）
  - 裁决门 B 按方案 ① 落地：只出报告 + 守卫，**不删 tracked 数据**
  - 新建 `scripts/diagnose/diagnose_d_cycle_note_section_hygiene.py`（只读；源码经 `stripComments()` 后无 `DELETE`/`db.delete(`/`--apply`/`--confirm`，由 Property 23 断言）
  - `tests/services/test_note_d_orphan_sections.py` — Property 21/22/23，**17 例全绿**，禁删清单条目数上限锁死（listed 3 / soe 2，只许减少）
  - 🔴 **两条断言的判据本轮改过**：见下方 Notes「Task 22 判据修正」
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 23. D4「按分解信息」表动态列：稳定键 + 单调计数器 + 旧列迁移
  - 🔴 **立项描述与实测不符** —— 动态列本体（`section4Categories` + 增删改名 + `buildD4TransposeColumns(categories)` 两级 group + payload 传 `timingCategories`）**改造前已实现**，见下方 Notes「Task 23 实证修正」
  - 新建 `composables/d4RevenueSegmentColumns.ts`：`allocateSegment`（**持久化单调计数器**，取 `max(现有最大, 计数器)+1`）/ `appendSegment` / `removeSegment` / `removeSegmentCells`（按 `{key}_{rowIdx}_{type}` 精确段解析）/ `migrateSegments`（按列名迁移 + `（待归并）` legacy 保留）/ `parseSegmentState`（容错 + 规整历史 `cat0` 形态并搬移单元格）
  - `useD4Disclosure` 接线：`Section4TransposeData` 加 `seqCounter` 并落库、`loadSection4` 走 `parseSegmentState`、`addSection4Category` 走 `allocateSegment`、`removeSection4Category` 走 `removeSegmentCells`
  - **裁决门 A 按 ② 落地**：旧值按列名匹配搬到新列，未匹配的保留并标 `isLegacy` + label 前置 `（待归并）`
  - 🔴 **键前缀保持 `cat_` 不改成 design.md 写的 `seg_`** —— `section4Cells` 既有键是 `cat_1_0_revenue`，改前缀等于丢已录数据；Property 24 的实质是「稳定键 + 不复用序号 + 不含中文」，与前缀字面无关
  - `d4RevenueSegmentColumns.spec.ts` — **28 例全绿**，含 PBT（任意增删序列下 key 恒唯一且从未复用）+ 4 条反向自检（朴素 max+1 实现会复用已删序号 / stripComments 生效 / `D4_DEFAULT_CATEGORIES` 必须保留源模板示例名 / 相近但不同的板块名必须不命中）
  - 回归：D4 全量 **19 文件 / 522 例 / 0 失败**；3 个改动文件 `get_diagnostics` 零诊断
  - _Requirements: 7.1, 7.2, 7.3, 7.4_（7.5「两侧列头同构」被源 xlsx 实证阻断，见 Task 31）

- [x] 31. D4（4）分解信息表行列与源模板对齐（🔴 Task 23 实测新发现，Property 25 成立的前置）
  - **源 xlsx 实证**（`D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`，权威运行时模板）：该表 **9 列 / 9 行**
    - 列 = `A` + `B46:C46 消费品` / `D46:E46 汽车` / `F46:G46 能源` / `H46:I46 其他`（各辖 收入/成本）+ 顶层 `B45:I45 本期发生额` ⇒ **三级表头，且无「合计」列**
    - 行 = 主营业务(`=SUM(B49:B51)`) / 其中：在某一时点确认 / 在某一时段确认 / **R51 空可扩行（在 SUM 范围内）** / 其他业务(`=SUM(B53:B55)`) / 其中：在某一时点确认 / 在某一时段确认 / 租赁收入 / 合  计(`=B52+B48`)
    - 国企 R38:R49 结构同构（顶层 `B38:I38`、类别 `B39:C39` 等、行 R41~R49，空可扩行为 R44）
  - **两处与源模板不符**：① `buildD4TransposeColumns` **自造 `total_revenue`/`total_cost` 两列**（横向合计，源模板没有；源模板的合计是**行**）② `D4_TRANSPOSE_CHECK_ITEMS` 只有 3 项，**丢了主营业务/其他业务父行、空可扩行、合计行**
  - 处置（**列与行必须一起改**，只删合计列会让用户看不到任何合计）：去掉自造合计列 → 行模型扩为 9 行（父行与合计行为**只读派生**，`section4ColTotal` 已有纵向求和且有源模板依据；`section4RowTotal` 随合计列一并退役）→ 附注模板 JSON 行集 6→9 行 → 两侧 columns 同构
  - 影响面（实测）：`d4DisclosureModel.ts` / `useD4Disclosure.ts` / `D4TabDisclosureListed.vue` / `D4TabDisclosureSoe.vue` / `d4NoteSectionMap.ts` + 3 个既有测试断言了 `total_revenue`/`total_cost`
  - **交付**：`d4RevenueSegmentColumns.ts` 追加行集真源 `D4_SEGMENT_ROWS`（9 行 + `subtotal`/`detail`/`expandable`/`total` 四态）+ `deriveSegmentCell`（读时派生、三态返 null）+ `segmentRowAcrossCategories`（横向合计只供底稿内部核对、**不进列定义**）+ `migrateSegmentCellKeys`（`{catKey}_{rowIdx}_{type}` → `{catKey}_{rowKey}_{type}`，幂等、未识别键原样保留）
  - `buildD4TransposeColumns` 去掉自造合计列（9 列）；`D4_TRANSPOSE_CHECK_ITEMS` 标 `@deprecated`；两个组件模板改按 `section4RowDefs` 渲染 9 行（父行/合计行只读派生 + 空可扩行提示）；`useD4Disclosure` 的 `getSection4Cell` 改**读时派生**、`updateSection4Cell` 拒绝写父行
  - 幂等脚本 `backend/scripts/fix/fix_note_d4_segment_structure.py`（`--dry-run`/`--check`/`--apply` + round-trip 自检）：两版模板 columns（`cat0_*`→`cat_N_*`）/ headers / rows（listed 8→9、soe 修掉主营业务下多出的「租赁收入」）/ guidance 全部对齐源 xlsx，`--check` **0 欠账**
  - 守卫：后端 `test_note_d4_segment_structure.py` **29 例全绿**（openpyxl 直读源 xlsx 三向比对：4 个 `colspan=2` 合并区 / **J 列及其后必须为空**证明无合计列 / 父行 SUM 覆盖 3 行含空可扩行 / 合计行 `=B52+B48` / 模板 JSON 对齐 / 前端源码交叉锁死）；前端 `d4SegmentRowAlignment.spec.ts` **21 例**
  - 回归：D4 全量 **20 文件 / 547 例 / 0 失败**；5 个改动文件 Vite transform 全 200
  - 🔴 **守卫抓出自己一处漏改**：guidance 里写了 markdown 粗体 `**无横向合计列**` —— 平台铁律禁此（TAB/Word 都不解析，且会与平台级 `fix_note_bold_markers.py` 互相打架）
  - _Requirements: 7.5_

- [x] 24. D3/D7 账龄口径边界守卫（🔴 **立项判断被实证推翻，改为只钉边界不加功能**）
  - **D3 的账龄贯通早已完整实现**（方案 A：`useD3DisclosureSoe` segment-driven 两桶 + `rowKey` + `d3NoteSectionMap` 经 `toDisclosureAgingLabel(r, SOE_AGING_OVERRIDES)` 映射）
  - **soe 八、38 主表源模板就是两档**（`1年以内（含1年)`/`1年以上`），按项目配置展开成 3/5 年段 = 自造披露行
  - **D7 源模板无账龄档位表**（上市 五、39 只有超1年**逐户明细**，国企 八、39 连这张都没有）⇒ 不引入账龄枚举，同 J2/H 类裁决
  - `dCycleAgingWiring.spec.ts` — **13 例全绿，6 个变异逐条打红**；含 D1/D5/D6/D7 不得引用账龄真源的反向锁死 + 合计行字面按章节实证（禁套全局 `DISCLOSURE_TOTAL_LABEL`）
  - 详见 Notes「Task 24 立项判断修正」
  - _Requirements: 8.1, 8.3, 8.4, 8.5_（8.2「按项目配置改变行集」按源模板实证不成立，见 Notes）

- [x] 25. 金额控件收敛（**实测 63 处**，立项写 64）
  - 新建幂等脚本 `scripts/fix/fix_d_cycle_amount_inputs.py`（`--dry-run`/`--check`/`--apply` + 结构自检）
  - `D2DisclosureNoteBody.vue` 43 / `D5TabDisclosure.vue` 14 / `D7TabDisclosure.vue` 4 / `D6TabDisclosure.vue` 2（该文件已有 8 处，属部分迁移）→ **`el-input-number` 全部归零**
  - 顺带清 `:controls="false"`（`el-input-number` 专属，留着会落成无意义 HTML 属性）
  - 63 处逐个核过邻近列头，**全部是金额语义**，无一命中反向边界；脚本对命中非金额语义的格**拒绝改写并告警**
  - `dCycleAmountControl.spec.ts` — **30 例全绿，3 个变异逐条打红**；标签存在性用 `/<WpAmountInput(?=[\s/>])/` 带边界（`toContain` 会被 `<WpAmountInputREMOVED` 骗过）
  - _Requirements: 9.1, 9.2, 9.3, 9.5_

- [x] 26. D3「款项性质 / 关联方类型」枚举单一真源收敛（原「D3-2 客户子科目联动 seed」，判据已按源模板推翻）
  - 🔴 **原描述「按 `2203` 叶子子科目建行」按源模板实证不成立**（详见 Notes「实证修正 · Task 26」），
    `d3DetailSeed.ts` 不建；改为收敛枚举双真源 + 反向锁死禁按科目名建 D3-2 行
  - 新建 leaf 真源 `composables/d3NatureCategories.ts`（`D3_NATURE_CATEGORIES` 四类 + `D3_RELATION_TYPES` 三类，
    每项带 `sourceRef` 指向源 xlsx 单元格；`d3NatureOptions`/`d3RelationTypeOptions` 兼容历史枚举外值）
  - `useD3Adjudication.NATURE_ROWS` 与 `NATURE_LABEL_TO_KEY` 改**派生**；`D3TabDetail.vue` C/D 两列改 `v-for` 真源
  - 守卫：`__tests__/d3NatureCategoryWiring.spec.ts`（23 例，8 变异 RED）+
    `backend/tests/services/test_d3_nature_categories.py`（18 例 openpyxl 三向锁死，6 变异 RED）
  - _Requirements: 10.1, 10.3, 10.5, 10.6_

- [x] 27. D4 按行业披露联动 seed（实证**立项前已完整交付**，本轮只核实并登记）
  - 🔴 `d4SegmentSeed.ts` **不需新建** —— 功能已在 `_d4_operating_revenue.build_d4_segment_prefill`
    （`pair_revenue_cost_leaves` 按后缀镜像配对 + `rollup_asymmetric_pairs` 归并层级不对称 +
    `name_mismatch`/`cost_missing`/`revenue_missing` 三类告警，两侧皆空返空列表）
  - 前端消费方 `useD4Disclosure.seedSection2FromSegmentPrefill`（手工优先 / 同名空行只填金额 / 新建行），
    两个披露组件各有「从四表」按钮
  - 某侧缺失时留 `null` 不填 0 —— 已由 `cost_missing`/`revenue_missing` 标记表达
  - `dCycleSeed.spec.ts` — Property 30/31
  - _Requirements: 10.2, 10.3, 10.4, 10.5_

- [x] 28. CI job 接入
  - `governance-checks.yml` 新增 **`d-cycle-four-table-completion`（后端 15 步）**与
    **`d-cycle-four-table-completion-frontend`（前端 10 步）**两 job
    （job 名避开既有 `d-cycle-extraction-chain` / `d4-four-table-extraction`）
  - 后端挂 Task 11/12/21/22/26/31 守卫 + 4 个幂等脚本 `--check` + 只读诊断烟测；
    前端挂 Task 16/17/23/24/25/26/31 守卫
  - 提交前校验：`yaml.safe_load` 可解析 + **原文 job 头计数 == 解析后 job 数**（防重复 key
    被 yaml 静默去重）+ 步骤里引用的 22 个文件路径逐个存在
  - 🔴 **顺带修掉一处预存在缺陷**：`note-m-equity-structure` 在 yml 里**出现两次**
    （128 vs 原文 130），GitHub Actions 对重复 key 是后者覆盖前者 ⇒ 前一份从未生效。
    两份**执行的命令逐字相同**（同一 `--check` + 同一 pytest 文件）故覆盖面未丢，
    已删前一份并把其背景注释（「本期」前缀推断 / 八、61 第 6 列「备注」）并入保留份
  - 提交前用 `yaml.safe_load` 验证可解析并断言 job 名无重复
  - _Requirements: 5.1, 6.5_

- [x] 29. 回归与浏览器实测
  - 后端 `four_table` 全量 + D 类相关；前端 D 类相关全量；判「失败是否预存在」用 traceback 行号是否落在本次改动行上
  - 浏览器实测三件套（录 ≥2 行真实数据 → 看目标区域真出数 → postgres 查落库），至少覆盖：D7 审定表带入取到 `2204` 的数、D3 账龄一键生成、D2 披露金额千分符、D4 分解信息动态列增删、推送后附注章节 `last_sync_at` 前移
  - 测完按快照逐字复原（`parsed_data` / `checklist_responses` / 附注 `last_sync_at` 与 `text_content`）
  - _Requirements: 1.3, 4.4, 8.2, 9.2, 10.2_

- [x] 30. 收口与提交
  - 清掉本会话 `tmp_*` 诊断产物
  - 三个裁决门的答复与落地结果写进本文件 Notes
  - 分层 commit（data / feat(be) / test(be) / feat(fe) / test(fe) / ci / docs），push 前必先 fetch 看实际 base
  - _Requirements: 6.2, 7.4_

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "取数接线（后端）",
      "tasks": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13],
      "notes": "Task 1→2 已完成；Task 3 内部 (a)→(b) 串行（(b) 依赖 (a) 的返回类型与 Task 2 的过滤件）；4~10 都依赖 Task 3，可并行；11/12 依赖 4~10 全部完成；13 是本波验收闸，D7 的 7,855.34 未命中不得进入 W2。方案已于开工后修正：不换解析器而是推广 D1 的 report_line_accounts 范式，理由见 requirements.md R1"
    },
    {
      "wave": 2,
      "name": "前端消费与溯源",
      "tasks": [14, 15, 16, 17],
      "notes": "全部依赖 wave 1 的 13 通过；Task 16 依赖裁决门 C；15 必须先于 16（漏传 prop 会让 16 静默失效）"
    },
    {
      "wave": 3,
      "name": "公式预设纠偏与补全",
      "tasks": [18, 19, 20, 21],
      "notes": "可与 wave 2 并行（不共享文件）；18→19→20 串行同一脚本，21 最后"
    },
    {
      "wave": 4,
      "name": "披露与附注结构",
      "tasks": [22, 23, 24, 25, 31],
      "notes": "22 依赖裁决门 B（已定①只报告不删），23 依赖裁决门 A（已定②按列名迁移+legacy）；24/25 无裁决门可先做；23 与 20 都碰 D4，需串行；31 是 Task 23 落地时源 xlsx 实证新发现，必须在 23 之后（复用其稳定键与迁移件），且行与列要一并改（只删自造合计列会让用户看不到任何合计）"
    },
    {
      "wave": 5,
      "name": "联动兑现与收口",
      "tasks": [26, 27, 28, 29, 30],
      "notes": "26/27 依赖 wave 1（需真实取数）与 wave 4 的 23（D4 动态列）；28 依赖前四波守卫齐备；29 是全局验收闸；30 最后"
    }
  ]
}
```

## Notes

### 实证修正 · Task 26（2026-08-06，requirements 10.1 按源模板不成立）

**原描述「D3-2 明细表按 `2203` 叶子子科目建行」是错的 —— D3-2 的行维度是「对方单位（客户）」。**

源 xlsx `backend/wp_templates/D/D3 预收账款.xlsx` 逐格实证（openpyxl，`data_only=False`）：

| 坐标 | 值 | 含义 |
|---|---|---|
| `预收账款明细表D3-2!A10` | `对方单位名称` | 行维度 = 客户，不是科目 |
| `…!C10` / `D10` | `款项性质` / `关联方类型` | 两个枚举列 |
| `…!C12:C22` 数据验证 | `预收销售固定资产款,预收销售土地使用权款,合同不成立时已收取的对价,其他` | 与 D3-1 性质行逐字一致 |
| `…!D12:D23` 数据验证 | `合并范围内关联方,合并范围外关联方,非关联方` | 三项 |
| `审定表D3-1!A8:A11` | 同上四类性质 | SUMIF 匹配键 |
| `审定表D3-1!B8` | `=SUMIF('预收账款明细表D3-2'!$C$12:$C$22, '审定表D3-1'!A8, '预收账款明细表D3-2'!$E$12:$E$22)` | **C 列是联动键** |

客户子科目实证只有 `2203.01 预收账款_预收货款` 与 `2203.02 预收账款_预收项目款`（后者在所有项目
全为 0），与 D3-1 四类性质**不同构**、SUMIF 匹配不上 ⇒ 按子科目建行会造出「对方单位名称 = 预收货款」
这种错行。数据来源已由 `_d3_prepaid_accounts.py` 明确记为 `tb_aux_balance` 2203 **客户维度**归集
（前端既有 `importFromAuxBalance` → `/d3/import-aux-balance`），render 侧「宁缺勿造」决策在案。

**真实缺口是枚举双真源**：`D3TabDetail.vue` 把那四个性质 label **内联硬编码**，与
`useD3Adjudication.NATURE_ROWS` 各写一份 ⇒ 改一处另一处不动，`natureAggregation`（按 `row.nature`
字符串分组）与 `natureAgg[label]` 匹配不上则该性质行**恒为 0**。且 D 列关联方枚举与源模板不符
（前端 6 项 `非关联方/母公司/子公司/联营企业/合营企业/其他关联方` vs 源模板 3 项）。

**顺带查出源模板自身两处缺陷（按意图实现，不照抄，已登记 `D3_SOURCE_TEMPLATE_DEFECTS`）**：

1. **`C23` 单独挂另一套 6 项数据验证** `货款,工程款,设备款,服务费,建造合同形成的已结算尚未完工款,其他`
   —— 与 D3-1 SUMIF 匹配的四类完全不同，疑从其它循环明细表复制残留。
2. **SUMIF 范围 `$C$12:$C$22` 止于 R22，而合计 `E24=SUM(E12:E23)` 含 R23** ⇒ 在源模板 R23 录入的
   金额进合计但不进任何性质行 = 「性质合计≠账龄合计」假差异。

平台侧 D3-2 是**动态行**，四类性质统一适用于全部数据行、不按行号分叉，故两处缺陷在平台上都不存在。

### 交付实录 · Task 26

**新建 leaf 真源** `composables/d3NatureCategories.ts`（零 Vue 依赖，避免 SFC 为拿常量而 import 整个 composable）：
`D3_NATURE_CATEGORIES`（四项，每项 `rowKey`（持久化键，禁改名）+ `label` + `sourceRef` 指向源 xlsx 单元格）
/ `D3_NATURE_LABELS`、`D3_NATURE_LABEL_TO_KEY`（均派生）/ `D3_RELATION_TYPES` + `D3_RELATION_TYPE_SOURCE_REF`
/ `d3NatureOptions(current)`、`d3RelationTypeOptions(current)`（**历史枚举外值动态追加为候选**，
数据零丢失红线；不用 `allow-create` 以免放任新造枚举）/ `D3_SOURCE_TEMPLATE_DEFECTS`。

**接线**：`useD3Adjudication.NATURE_ROWS` 与 `NATURE_LABEL_TO_KEY` 改为派生；`D3TabDetail.vue` C/D 两列
改 `v-for` 候选函数。两个 D3 测试文件里的 `NATURE_OPTIONS` fixture 副本也改为引用真源（防漂移）。

**守卫与变异**：

| 守卫 | 例数 | 变异 |
|---|---|---|
| `composables/__tests__/d3NatureCategoryWiring.spec.ts`（Property 32~37） | 23 | **8/8 RED** |
| `backend/tests/services/test_d3_nature_categories.py`（openpyxl 三向锁死 + 反向锁死） | 18 | **6/6 RED** |

回归：D3 相关 **16 文件 / 154 例 / 0 失败**；三个改动文件 Vite transform 全 200。

**修掉守卫自身两处缺陷（均是平台已登记的坑再现）**：

1. `_array_body` 首版从 `export const X` 之后找第一个 `[` → **命中类型注解 `readonly T[]` 的括号**，
   body 退化成 `[]` ⇒ 三条交叉锁死断言变成空集比较（假红）。正解 = 从赋值号 `=` 之后再找 `[`。
2. `test_defects_registered_in_frontend` 用「整段包含 `'C23'`」判定 ⇒ 被**第一条 note 正文里的 C23**
   骗过，改坏 `ref` 值仍通过（MB5 变异实测 GREEN）。正解 = 逐个抽 `ref:` **字段值**精确比对 + note 长度闸。
3. `_strip_py_comments` 的反向自检原用「宁缺勿造」当锚点，而它**也出现在 `logger.debug(...)` 字符串里**
   ⇒ 自检恒失败。改用只在 `#` 注释里出现的 `【宁缺勿造决策】`，并另断言字符串里那份**必须保留**
   （证明只剥注释不剥字符串）。

### 实证登记 · Task 27（立项前已完整交付，本轮只核实）

`d4SegmentSeed.ts` **不需新建**。后端 `_d4_operating_revenue.build_d4_segment_prefill` 已完整实现：
`pair_revenue_cost_leaves`（按后缀镜像配对 `6001.xx` ↔ `6401.xx`）+ `rollup_asymmetric_pairs`
（归并层级不对称）+ 逐项 `label`/`section`/`current_revenue`/`current_cost` 与三类告警
`name_mismatch`/`cost_missing`/`revenue_missing`，**两侧皆空返空列表**（宁缺勿造）。
前端消费方 `useD4Disclosure.seedSection2FromSegmentPrefill`（手工优先 / 同名空行只填金额 / 新建行），
两个披露组件各有「从四表」按钮。「某侧缺失留 `null` 不填 0」由那两个 missing 标记表达。

### 回归实录 · Task 29（2026-08-06）

**后端**：本 spec 守卫全集 **191 passed / 9 skipped / 0 failed**（8 个文件）。
D 类广域（`backend/tests/d_cycle_extraction` + `four_table` + `-k "d1 or d2 or ... or note_d"`）
**801 passed / 34 failed**，34 个逐簇归属如下（全部与本会话 D 类改动零交集）：

| 簇 | 数 | 归属证据 |
| --- | --- | --- |
| `test_tier_a_writeback_save` / `_characterization` / `_detail_seed_properties_pbt` / `test_formulas_endpoint_extraction` | 23 | 报错落在 **`wp_formula.py:254` 的 `_formula_to_dict` 读 `f.lifecycle_state`**；`git show HEAD:` 实证该字段 **HEAD 无、工作树有**（`wp_formula.py` 是并发会话的 ` M`），测试替身 `SimpleNamespace` 未跟进 |
| `four_table/test_report_formula_filler_mirror.py` | 9 | 文件是 `??`（并发会话新建），配套 `report_formula_service.py` 亦为并发会话 ` M` |
| `test_d6_d2_render_characterization.py` | 2 | memory 已登记的预存在：守卫拿 `_k9_admin_expenses` 当「`_build_adjudication_prefill` 范式基准」，而 K9 已重构走共享件 |

**前端**：`src/components/workpaper` 全量 **1205 文件 / 3692 例 / 3687 passed / 5 failed**，
5 个全部预存在（`disclosureColumnsCoverage` ×3 = 22 个 J1/J2/L4/M\* builder 未登记 `P1_ROUTE`
+ 1 张 allowlist 漂移 + 5 张 flat/group 互斥；`disclosureAutoSyncCoverage` ×1 = `D2TabDisclosure.vue`
显式 props 委托被 `resolveDelegate` 误判；`g7SoeDisclosureModel` ×1 = 断言参数类型错）。
**三个失败清单里 D3/D4 命中数逐条为 0** ⇒ 本会话零新增缺口（这是「预存在」判据，
不是「看着像别人的活」—— 按 memory 铁律必须用清单内容而非文件名归属）。

**幂等脚本 4 个 `--check` 全 exit 0 / 欠账 0**：`fix_d_cycle_prefill_presets.py`
（round-trip 自检 OK）/ `fix_d_cycle_disclosure_presets.py`（同）/
`fix_note_d4_segment_structure.py` / `fix_d_cycle_amount_inputs.py`（待改写 0）。

### 诚实修正 · 两个「测试镜像旧行为」的失败（Task 29 回归中暴露）

**① `test_d1_account_resolver::test_resolve_as_dict_shape_for_render_output`**
断言 `as_dict()` 键集恰为 6 键，而本 spec **Task 13 给 `D1AccountCodes` 加了
`subject_keywords`** —— 那是真实库验收挖出的 P0（`fetch_d_cycle_tb` 读
`getattr(codes, "subject_keywords", ())`，D1 原先没这字段 ⇒ 那道「无条件名称过滤」
对 D1 **静默空转**，5 个项目备抵取到整个 `1231`，`52c04ed1` 虚增到 **102,358,291.13**）。
⇒ 键集断言改为「7 键（含 `subject_keywords`）」+ 新增
`test_subject_keywords_present_and_narrow_enough`（值必须是 `('应收票据','票据')`，
**不得含裸「坏账准备」**，否则过滤退化成放行全部 `1231.*`）。

**② `test_d1_prefill_presets::test_detail_sheets_have_no_wp_formula`**
判据「除审定表外一律禁 `WP()`」把**披露 sheet** 也算进去了，而两个披露块的
`WP('D1','原值明细表（按类别）D1-2','期末合计')` 的 description 明写
「勾稽用，不参与披露取数」—— 与 memory 已记的「『明细表不得引用审定表』误伤跨循环引用」
同族（判据写太宽）。**披露 sheet 引明细表不构成循环**（明细表不反引披露表；真正要防的是
审定表 ↔ 明细表互引）。⇒ 三分 sheet：审定表（可引）/ 披露 sheet（**只许引明细表、
禁引审定表**）/ 明细表（一律禁），披露 sheet 判定用 openpyxl 直读的真实 tab 名做
子串匹配（源模板括号有全角/半角/前半后全多种写法，写死字面量必分叉）。
新增两条：`test_disclosure_wp_targets_are_detail_sheets_not_adjudication`
+ `test_disclosure_wp_is_reconcile_only`（description 必须自证勾稽用途）。

**变异检验 3/3 RED**（真明细表塞 `WP(审定表)` 必红 / 披露块 `WP` 改指审定表必红 /
`subject_keywords` 改空元组必红）⇒ 判据是**放宽了适用范围、不是放宽成空转**。
该文件 24 → **26 例全绿**。

### 浏览器实测 · Task 30（2026-08-07，D4 侧完成；抓出 3 个只有浏览器能发现的 P0）

**实测环境**：协作者同时在用共享浏览器 ⇒ 用 chrome-devtools 的 **`isolatedContext`** 开独立
browser context（cookie/storage 完全不共享）。**Playwright MCP server 是共享单实例**，
实测中我的 tab URL 被协作者导走过一次（`browser_tabs list` 只有 1 个 tab 却换了 URL），
故不能用它做隔离实测。另：chrome-devtools 这条通道**只能传纯字符串参数**，
`boolean`/`number`/`array` 会被序列化成字符串而报 schema 错 ⇒ 避开
`includeSnapshot` / `timeout` / `fill_form` / `wait_for` 这类带非字符串参数的调用。

#### P0-1 `DisplayPrefs_Key` 引入来源错误 —— 整个底稿页白屏（5 处，横跨 3 循环）

打开 D4 国企披露 Tab 直接崩成
「页面渲染出错：The requested module '/src/stores/displayPrefs.ts' does not provide an
export named 'DisplayPrefs_Key'」。真源是 `composables/displayPrefsKey.ts`，
`stores/displayPrefs.ts` 只导出 `useDisplayPrefsStore` / `TableDensity` /
`TABLE_DENSITIES` / `FixedColumnsConfig`。全前端扫描 **72 处引对 / 5 处引错**：

| 文件 | 归属 |
| --- | --- |
| `d4/core/D4TabDisclosureSoe.vue` | 本 spec（**正是它挡住了 Task 30 实测**） |
| `d4/core/D4TabDisclosureListed.vue` | 本 spec |
| `f3-notes-payable/F3TabDisclosureListed.vue` / `F3TabDisclosureSOE.vue` | F 循环 |
| `custom/GtCustomGridSheet.vue` | 并发会话的 custom spec |

后三处不属 D 类，但同一笔缺陷、修 import 路径是零行为变更 ⇒ 一并修（否则那三页同样白屏）。
新增平台守卫 `__tests__/displayPrefsKeyImportSource.spec.ts`（7 例），
含四条反向自检：真源确实导出该 key / store 确实**不**导出（钉死崩溃根因不是笔误）/
扫描面 >30 / 正确来源不得被误判。**变异检验闭环**：把 `D4TabDisclosureSoe` 改回从 store
引入 → 准确打红并点名该文件；还原 → 7/7 绿。
过程中修掉守卫自身一处缺陷 —— 它把**自己文档字符串里的反例**数成真实 import
（`stripComments` 只剥注释、不剥字符串），已改为排除自身文件 + 反例用字符串拼接书写。

#### P0-2 （4）表 9 个行标签全部消失 —— 模板绑定了不存在的字段

模板写 `{{ row.item }}`，而 `D4SegmentRowDef` 的字段是 **`label`**。Vue 对不存在的属性
渲染空串且不报错 ⇒ 主营业务 / 其中：在某一时点确认 / … / 合  计 **9 个标签一个都不显示**，
表格只剩空可扩行的提示文字。两个变体同款（soe L569 / listed L680）。

#### P0-3 派生行未只读 —— 用户可直接改写小计与合计

`:class="{ 'font-bold': row.readonly }"` 与 `v-if="!isReadonly && !row.readonly"` 里的
`row.readonly` **恒 `undefined`**（真源无此字段）⇒ 小计/合计行既不加粗也**没被禁用**，
可以手工改写派生格、把「小计 = Σ 明细」的勾稽改坏。
修法 = 真源新增 `isSegmentRowReadonly(row)`（判据只看 `kind`，单一真源）+
`useD4Disclosure.section4RowDefs` 派生下发 `readonly`（此前只做 `{ ...r }` 浅拷贝）。

**P0-2/P0-3 都是新守卫 `__tests__/d4SegmentRowLabelBinding.spec.ts` 抓出的**（12 例）：
从真源 `.ts` **动态抽** `D4SegmentRowDef` 字段名（不写死清单），再扫两个 SFC 里
`v-for="row in section4RowDefs"` 块内所有 `row.xxx` 引用求差集。P0-3 正是它在我修完 P0-2
后立刻打红报出来的（`readonly` 不在合法字段集）。派生字段走 `DERIVED_FIELDS` 豁免，
并配一条「该字段必须在 composable 里真被赋值」防豁免退化成空转。
D4 三守卫合跑 **59 例全绿**（新 12 + 既有 47 零回归）。

#### D4 侧实测结果（项目 `2aa00f57` / wp `da4df97e`，soe 变体）

| 判据 | 实测 |
| --- | --- |
| 崩溃 | 修后 `crashed:false` |
| （4）表列结构 | `项 目[rs=2]` + 4 类别 × `[cs=2]`（收入/成本）= **9 列**，**末尾无横向合计列** |
| 行结构 | tbody **9 行**，标签逐字与源模板一致 |
| 空可扩行 | 第 4 行显示「（可按实际情况补充项目）」 |
| 派生行只读 | 第 0/4/8 行 `font-bold` 且 **输入框数 = 0**；其余 6 行各 8 个输入框 |
| 读时派生 | 录 `main_point` 消费品收入 1,000,000 + `main_period` 250,000.5 ⇒ 主营业务小计 **1,250,000.50**、合计 **1,250,000.50**；成本 600,000.00 同步上卷 |
| 三态 | 「其他业务」未录入显示 **`—`** 不是 0 |
| 金额格式 | 千分符 + 2 位小数生效 |

**Task 23 单调计数器经真实持久化数据确认**（`D4-disc-soe-section4-rows`）：
删掉 `cat_3`（能源）后新增得 **`cat_5`** 而非复用 `cat_3`，`seqCounter: 5` 已落库，
`cells` 里无任何 `cat_3_*` 残留，`cat_1_*` 三个已录值完好。
单元格键形态 `{catKey}_{rowKey}_{revenue|cost}`（用 **rowKey** 不是行号）= Task 31 目标形态。
删除类别的确认框正确提示「该类别下所有已录入的收入/成本数据将一并删除」；
新增类别走 `ElMessageBox.prompt` 先输名称（符合动态行铁律）。

**Task 27/31 推送链路顺带获得正向验收**：录入后自动同步把（4）表推进附注 `八、64`，
`_sub_table_columns['营业收入分解信息']` 实测 **9 列**、两级 `group`（消费品/汽车/其他/医疗器械）
+ 叶子 `label`（收入/成本）、**无合计列**，且动态类别变更如实传导（删掉的「能源」不在、
新增的「医疗器械」在）。

**数据已逐字节复原**（脚本 `--apply` 后核验）：D4 checklist 2→**0**、D3 保留基线那 3 条
（`D3-sampling-methodology`/`D3-vc-conclusion`/`D3-vc-current-rows`，本轮未触碰）、
D7 仍 0、三个 wp `parsed_data` 全 NULL；附注三章节 md5 **逐个等于实测前基线**
（八、38 `e557694b…` / 八、39 `53f6a3ce…` / **八、64 `46641aa3…`** —— 后者被自动同步写过，
已剥掉 `_source`/`sub_table_data`/`_sub_table_columns`/`_last_sync_*`/`_current_standard`
并把 `last_sync_at`/`last_sync_wp_id` 回 NULL）。

#### D3 侧实测结果（wp `d35c715a`，Task 26 联动闭环）

D3-2 的行入口是 **「+ 添加客户」**（不是通用「增行」）—— 从 UI 侧再次印证「D3-2 行维度是
对方单位（客户）、不是 `2203` 子科目」这一 Task 26 判据。

| 判据 | 实测 |
| --- | --- |
| D3-2 列头 | `对方单位名称 / 公司代码 / 款项性质 / 关联方类型 / 期初未审(E) / …` 与源模板一致 |
| C 列「款项性质」候选 | **`预收销售固定资产款 / 预收销售土地使用权款 / 合同不成立时已收取的对价 / 其他`** —— 与 `D3-2!C12:C22` DV 及 `D3-1!A8:A11` 逐字一致 |
| D 列「关联方类型」候选 | **`合并范围内关联方 / 合并范围外关联方 / 非关联方`（3 项）** —— 与 `D3-2!D12:D23` DV 一致；改造前自造的 6 项（母公司/子公司/联营/合营/其他关联方）已清除 |
| 落库形态 | `D3-det-rows` 的 `nature: "预收销售土地使用权款"` / `priorAudited: 880000` |
| **D3-1 SUMIF 聚合** | 「预收销售土地使用权款」行 = **880,000**，其余三类 `-`，合计 **880,000** |
| 三态 | 未命中的性质行显示 `-` 不是 0 |

这正是 Task 26 要保护的不变量：**C 列取值必须与 D3-1 性质行标签逐字相同 SUMIF 才命中**；
改造前双真源下改任一处都会让该性质行恒 0。

#### 复原核验（两轮，第二轮才真正干净）

**第一轮复原脚本有一处「假成功」缺陷**：`DELETE ... WHERE item_id <> ALL(:keep)` 传
Python list，asyncpg 下该参数绑不成数组 ⇒ 谓词恒不命中、`rowcount=0`，而脚本照旧打印
「已复原」。是 postgres 侧**独立查询**抓出来的（`D3-det-rows` 仍在、cr=4）。
⇒ 改用显式展开的具名参数 `NOT IN (:k0,:k1,:k2)`。
**教训**：复原成功的判据必须是独立查询，不能看脚本自己的输出（与 memory 已记的
「`--apply` 被 Ctrl+C 中断但写入已提交，判成败查数据不看退出码」同族）。

第二轮复原后逐项等于基线：D3 恰剩基线那 3 条（`D3-sampling-methodology` /
`D3-vc-conclusion` / `D3-vc-current-rows`）、D4/D7 各 0 条、三个 wp `parsed_data` 全 NULL；
附注 md5 与 text 长度逐项相等（八、38 `e557694b…`/1184 · 八、39 `53f6a3ce…`/972 ·
**八、64 `46641aa3…`/644**）。

#### D7 侧实测结果（wp `2805b63d`，裁决门 C 的落地确认）

| 判据 | 实测 |
| --- | --- |
| 崩溃 | 无 |
| 账龄行 | 6 档（1年以内 / 1-2 / 2-3 / 3-4 / 4-5 / 5年以上）+ 合计，与项目账龄配置一致 |
| TB 核对区 | **「与试算平衡表核对（科目2205）：`-` 核对一致」** |
| 全表金额 | 一律 `-`，**不是 0.00** |
| 交叉引用 | `D7-2` / `D7-5` / `D3` chip 就位 |
| AI 辅助 | 3 段（变动分析 / 账龄分析 / CAS14 区分结论）各有 🤖 + 💬 |

postgres 实证该项目 `2204`/`2205` 在 `tb_balance` **与** `trial_balance` 两侧**都无数据行**
⇒ 显示 `-` 且判「核对一致」是**正确行为**，不是取数断链。这与本文件已登记的
「D5/D6/D7 在全部 8 个项目都是 `no_data`/`no_account`」一致，也确认**裁决门 C**
（恒空显灰态而非 `0.00`）已落地。

**Task 30 三项浏览器实测全部完成**，数据经 postgres 独立核验仍在基线
（三个 wp checklist 3/0/0 + `parsed_data` 全 NULL；三个附注章节 `last_sync_at` 全 NULL
且 md5 全部命中实测前基线值）。**剩余**：commit。

### 裁决门状态

| 门 | 议题 | 状态 | 答复 |
|---|---|---|---|
| A | D4 分解信息表旧 4 列处置 | **已定** | ②旧值按列名迁移 + `legacy` 保留（Task 23 按此实现） |
| B | 孤儿重复章是否 `--apply` 删除 | **已定** | ①只出报告 + 守卫，**不删** tracked 数据 |
| C | D6/D7 恒空的 UI 呈现 | **已定（Task 16 已落地）** | ①「本项目无此科目」灰态 `info` tag |

三门均按 spec 自荐方案落地（A 避免旧列长期占位；B 删 tracked 数据风险高于收益；C 与平台宁缺勿造一致且能区分真实 0 余额）。

### 实证修正 · Task 23（2026-08-06，立项描述与代码现状不符）

**「D4 分解信息表改动态列」的动态列本体改造前已完整实现。**

| 层 | 现状（改造前） |
|---|---|
| `useD4Disclosure` | `section4Categories` + `section4Cells` + `addSection4Category` / `removeSection4Category` / `renameSection4Category` 齐全 |
| `d4DisclosureModel` | `buildD4TransposeColumns(categories)` 按 `{catKey}_revenue` / `_cost` 出两级 group，零入参可调 |
| 两个披露组件 | `section4Categories` 各 7 处引用、三个 CRUD 各 2 处、`timingCategories` 传给 payload |
| `d4NoteSectionMap` | `snapshot.timingCategories ?? D4_DEFAULT_CATEGORIES` → `buildD4TransposeColumns` |

**故真实缺口只有三条**：

1. 🔴 **`nextD4CategoryKey` 取「现有列表」max+1 ⇒ 复用已删序号** —— 删 `cat_4` 再新增又得
   `cat_4`，而单元格键是 `{catKey}_{rowIdx}_{type}` ⇒ 历史 `cat_4_0_revenue` 串到新板块列上
   显示成别的行业的金额。正解 = 持久化单调计数器（与平台已登记的 H0 矩阵动态列同款结论）。
2. **旧列迁移无路径**（裁决门 A ② 未落地）。
3. **模板 JSON 列 key 是 `cat0_revenue`（0-based 无下划线），前端产出 `cat_1_revenue`** ⇒
   seed 路径与推送路径列 key 不同构；`parseSegmentState` 已按此做规整并搬移单元格。

**两处有意偏离 spec 文字**（落地前已核实，勿再「纠正」）：

- design.md Property 24 写键形如 `seg_\d+`，实际保持 `cat_` —— `section4Cells` 既有键是
  `cat_1_0_revenue`，改前缀等于丢已录入数据（数据零丢失红线）。
- `D4_DEFAULT_CATEGORIES` 的 `消费品/汽车/能源/其他` **不删** —— 源 xlsx `B46:I46` 就是这
  四个示例（与 F2 `_F2_CATEGORIES[].account`「兜底/展示用」同性质）；Property 25 的禁令
  对象是 `d4NoteSectionMap.ts` 与组件（实测均 0；组件那 3 处在 guidance 提示文字里）。
  守卫用**正向断言**钉住它必须保留 —— 清空会让「历史无数据」时渲染成零列。

**过程中修掉自己写的一处缺陷**：`migrateSegments` 首版对每个目标 label 都无条件分配新
key ⇒ 对已迁移结果再迁一次会给同一 label 反复换 key（`cat_2 → cat_3 → …`），`seqCounter`
无界增长且单元格被反复搬移。正解 = 命中且历史 key 已是合法稳定键时**复用原 key**。
（守卫的「迁移幂等」用例正是它打红的。）

### 交付实录 · Task 31

**两处与源模板不符已修**：自造的横向合计列已删；行集 3 行 → 9 行。

| 层 | 改动 |
|---|---|
| `d4RevenueSegmentColumns.ts` | 追加 `D4_SEGMENT_ROWS` / `deriveSegmentCell` / `segmentRowAcrossCategories` / `migrateSegmentCellKeys` |
| `d4DisclosureModel.ts` | `buildD4TransposeColumns` 11 列 → **9 列**；`D4_TRANSPOSE_CHECK_ITEMS` 标 `@deprecated` |
| `useD4Disclosure.ts` | 单元格键 `rowIdx` → `rowKey`；`getSection4Cell` 改读时派生；`updateSection4Cell` 拒写父行；加载时 `migrateSegmentCellKeys` |
| 两个披露组件 | 模板按 `section4RowDefs` 渲染 9 行（父行/合计行只读 + 空可扩行提示）；thead 去合计列 |
| 附注模板 JSON | 幂等脚本对齐 columns/headers/rows/guidance |

**派生列禁持久化**：父行与合计行**读时派生**（源模板 R48/R52 是 `SUM(...)`、R56 是 `B52+B48`）。
存下来会与明细行漂移 —— 平台已登记的 D1「比例列显示 162.50%」正是同款。

**单元格键迁移的一处会计判断**：旧 `rowIdx` 0/1/2 对应「时点 / 时段 / 租赁收入」，
而新行集里「时点/时段」各有两处（主营业务下 + 其他业务下）⇒ 旧数据**无法确定归属**。
迁移按「0→`main_point` / 1→`main_period` / 2→`other_lease`」处理：**第三条是确定的**
（租赁收入在源模板只在其他业务下），前两条是推断（多数项目主营占绝大部分），
迁移后需审计师复核。无法识别的键一律原样保留（数据零丢失）。

**三处修掉的既有测试缺陷**（都是「测试镜像了自造行为」或「随机种子脆弱」）：

1. `d4DisclosureModel.spec.ts` 断言列数 **11** —— 镜像自造合计列 → 改 9 + 反向锁死
   「除标签列外列 key 必须全是 `cat_N_{revenue|cost}`」（防换个名字加回来）。
2. `d4NoteSectionMap.spec.ts` 断言 `total_*` 列有 2 个 → 改断言 0 个 + 反向自检
   「类别列确实推过来了」（否则在空列集上也会通过）。
3. 🔴 `d4DisclosureModel.spec.ts` 的 PBT Property 15 **无条件**断言年度列 label
   `not.toContain('2026')`，而 `auditYear=2025` 时 label 本就是 `2026年` ⇒ 必失败；
   下面几行才是作者本意的**带条件**版本（注释写着「除非 auditYear 恰好是 2025」）。
   多数随机 seed 抽不到 2025 就一直是绿的 —— 本轮 seed `-356235413` 命中才暴露。
   已删掉无条件版本 + 补一条 2025 边界用例钉死（防再次随机漏过）。

**`disclosureColumnsCoverage.spec.ts` 3 例失败经核实全部预存在**：
① 「同表 flat 与 group 互斥」列出 5 项，含**未改动**的 `buildD4TwoPeriodColumns` 与
L4×3（且 `buildD4TransposeColumns` 改造前就是 label flat + 类别 group 形态）；
② `buildI1ListedColumns` allowlist 漂移；③ 22 个 J1/J2/L4/M* builder 未登记 `P1_ROUTE`。
无一项由本次引入。

⚠️ 顺带记一条：该守卫的「同表 flat 与 group 互斥」判据与平台既有范式冲突 ——
memory 已登记「rowspan=2 的独立列不给 group（混合分组，前后端都支持）」，
即标签列 flat + 数据列 group 是标准做法。它已对 L4 打红，属该守卫自身过严，
归平台级 `disclosure-columns-coverage-rollout`。

### 源模板实证 · Task 31（2026-08-06，openpyxl 直读，与两侧现状都不符）

`D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx`（权威运行时模板）的（4）表：

| 维度 | 源模板 | 前端现状 | 附注模板 JSON |
|---|---|---|---|
| 列 | **9 列**（label + 4 类别 × 收入/成本），**无合计列** | **11 列**（多 `total_revenue`/`total_cost`） | 9 列 ✅ |
| 表头层级 | **三级**（`B45:I45 本期发生额` > 类别 > 收入/成本） | 两级 | 两级 |
| 行 | **9 行**（含主营业务/其他业务父行、R51 空可扩行、合计行） | **3 行**（只有时点/时段/租赁收入） | 6 行 |

上市 R44~R56 / 国企 R38~R49，两版结构同构（国企空可扩行为 R44）。

**结论**：前端**自造了横向合计列**（源模板的合计是 R56 那一**行** `=B52+B48`），并**丢掉了
父行、空可扩行、合计行**。`section4ColTotal`（纵向求和）对应源模板 R48/R52/R56 的 SUM ⇒
有依据；`section4RowTotal`（横向）与两个合计列 ⇒ 无依据，随 Task 31 一并退役。

⚠️ **列与行必须一起改**：只删合计列会让用户完全看不到合计（行侧还没有合计行）。

### 实证修正 · Task 16（2026-08-06，原任务描述与后端实际契约不符）

**「从四表库带入未审数」在 6 个循环上没有可带入的数据 —— 这是 R3.4 的既定设计，不是缺口。**

逐个读 render 源码实证：**只有 D4 与 D6 返回 `adjudication_prefill`**，另 5 个
（D1/D2/D3/D5/D7）源码里明确写着**有意不返回**，理由逐字如下：

| 循环 | render 源码自述 |
|---|---|
| D1 | 「本 render 仍**不返回** `adjudication_prefill` —— D1 seed 走 `responses_snapshot` 明细行」 |
| D2 | 「TB 叶子子科目**无法**干净映射到分类行（单项/账龄/客户类型）⇒ 不发」 |
| D3 | 「**不臆造**分类行未审数 = 诚实的部分覆盖，对齐 R3.4」 |
| D5 | 「无法把 TB 干净映射到分类行 ⇒ 不发」 |
| D7 | 「不臆造分类行未审数 = 诚实部分覆盖，对齐 R3.4，同 D3」 |

**根因**：这 5 个审定表的行是**分类维度**（按性质 / 按账龄 / 按信用风险组合 / 按票据种类），
而 `tb_balance` 只有科目维度 —— 把总额摊到分类行就是造假。D4 能带入是因为客户
`6001` 确有业务板块级子科目、D6 是因为动态行按叶子建行。

**故 Task 16 的真实缺口是另外两块**（都属「四层验证全绿但用户不可达」）：

1. **溯源面板孤儿** —— `WpFourTableSourcePanel` 改造前只有 D4 挂了，另 6 个循环
   `panelTag=0`。7 个 render 早已下发 `tb_source_codes`（含四态 / `dropped` /
   `prefix_mismatch`）⇒ 全是 dead output。
2. **TB 核对数 dead output** —— 7 个 render 都经 `seed_tb_amount_scalars` 写了三口径
   标量（`tb_amount` / `_unadjusted` / `_audited`），但 **D2/D3/D5/D6 的
   `trialBalanceAmount` 只读 `checklist_responses`**（`D2-adj-tb-amount` /
   `D3-adj-trial-balance-amount` / `D5-1-tb-amount` / `D6-1-tb-amount`）⇒ 用户未手工
   填过时恒 0 ⇒「审定合计 − 试算平衡表数」显示成**整额假差异**，而数明明已经取回来了。
   D1/D7 改造前已有 `tbSeedAmount` 回退，故只有 4 个中招。与平台已登记的 F2/F3/F4 同款。

**手工优先的判据必须是「原始 remark 是否为空」**，不能用 `parseNum(...) === 0` ——
审计师**手工填的 0**（「该科目余额确实为 0」）是有意义的审计结论，按数值判会被 seed
反复覆盖。守卫的 M1 变异正是复现这一点。

### 交付实录 · Task 16

**新建** `composables/dCycleTbSeed.ts`（三口径键名与后端 `seed_tb_amount_scalars` 逐字对称）
+ `__tests__/dCycleTbSeed.spec.ts`（**70 例全绿**）。

**改动** 4 个 composable（D2/D3/D5/D6 加 `tbSeedAmount` 可选入参 + `trialBalanceAmount`
由 `ref`+`watch` 改为带回退的 `computed`）+ 6 个审定表组件（挂面板 + 经单一真源
`pickDTbSourceCodes` 取载荷）+ D4 收敛到 `pickDTbSourceCodes`（原来自己写单层读法）。

**5 个变异逐条打红并还原**：

| 变异 | 结果 | 打红的断言 |
|---|---|---|
| M1 手工 0 被 seed 顶掉 | RED (2) | 手工 0 也算已录入 + 朴素实现反向自检 |
| M2 seed 为 null 当 0 用 | RED (2) | 同上两条 |
| M3 D3 不传 seed | RED (1) | D3 的 TB 数走 `resolveTbAmountWithSeed` 且传了 seed |
| M4 D5 面板标签改名 | RED (1) | D5 模板里真的渲染了面板标签 |
| M5 `pickDTbSourceCodes` 只读单层 | RED (2) | `project_context` 落点可读 + 单层朴素实现反向自检 |

**🔴 M5 一度不打红 = 守卫自身缺陷（已修）** —— 首版 Property 14 全是**源码级**断言
（只查组件有没有写 `pickDTbSourceCodes`），而 M5 改的是 `dCycleAccountScope.ts` 的
**实现**（去掉 `project_context` 分支）⇒ 源码没变自然不红。补 **Property 15 行为级
describe**（直接调 `pickDTbSourceCodes` 验两层落点 + 顶层优先 + 两层皆无返 `null`）后
才 RED。**教训：源码级断言拦不住实现层退化，两者都要有。**

**验证**：11 个改动文件 `get_diagnostics` 零诊断 + **Vite transform 全 200**；D 类作用域
回归 **129 文件 / 1973 例 / 1 失败**，唯一失败 `d4DisclosureModel.spec.ts:230` 是随机种子
脆弱的 PBT（该文件与 `d4DisclosureModel.ts` **git 干净**、单独复跑 29/29 全绿）⇒ 预存在基线。

**过程中踩到两个已登记的坑，各记一次**：

- **批量注入 import 必须避开多行 `import {` 语句** —— 脚本按「最后一个 import 行」定位，
  而 D1 最后是多行 import 的**首行** ⇒ 注入插进语句中间 ⇒ Vite 500
  `Unexpected keyword 'import'`，而 `get_diagnostics` **零诊断**。两轮修复叠加后 import
  区更是彻底破损（同一 import 出现两次）。正解 = 按**语句边界**（配对到 `} from '...'`）
  定位，且修完必须做「无 `import {` 紧跟 `import` 行」的结构性自检。
- **复用 terminal 会读到上一轮旧日志** —— 变异报告连读三次都是旧内容，误以为 M5 修不好。
  正解 = 每轮换输出文件名，或读前先 `shutil.copy` 到新名字。

### 实测结论 · Task 13（2026-08-05，真实库只读直跑，最终 PASS）

**修掉一个真实 P0：`D1AccountCodes` 缺 `subject_keywords` → D1 备抵名称过滤静默空转**

`fetch_d_cycle_tb` 用 `getattr(codes, "subject_keywords", ())` 读关键词，而 D1 走的
`D1AccountCodes` 没有该字段 ⇒ 那道「无条件名称过滤」对 D1 **完全空转**，5 个项目的备抵
取到整个 `1231`：

| 项目 | 修前备抵 | 修后 |
|---|---|---|
| 52c04ed1 | **102,358,291.13** | 剔除 `1231`，如实标 `no_data` |
| 2aa00f57 | 1,718,193.78 | 同上 |
| f064f5e4 | 1,110,214.59 | 同上 |
| b39809ed / 4f6dbc36 | 0.00 / 3,834.60 | 同上 |

与 K1「虚增 31.6 倍」完全同源。**失效条件是「`provision_resolved_from == report_config`
但反解出宽口径 `1231`」** —— 而 `use_provision_name_filter` 只在 `fallback` 时为 True，
故既有机制拦不住。修法 = 给 `D1AccountCodes` 加 `subject_keywords=("应收票据","票据")`
（**加法式，不动科目定位路径**，零回归红线保持）。

**单测查不出**：替身按各 render 原 SQL 的字段别名定制，而该组合只存在于真实
`account_mapping`（同一项目同时有 `1231` 与 `1231.01` 两条 `auto_exact` 反解行）。

**🔴 Wave 2 必读：`tb_source_codes` 落点平台有两套并存约定**

| 落点 | 循环 | 前端读它的件 |
|---|---|---|
| `html_data` **顶层** | D1/D2/D3/D5/D6/D7（6 个） | `composables/shared/cycleAccountScope.ts`、`shared/tbSourceCodes.ts`、`semanticAccountSource.ts` |
| `html_data.project_context` | **D4 独一个** | `composables/d4AccountScope.ts` |

design.md 的 Architecture 段写的是 `project_context.*`（按平台惯例），**与 6 个循环的实际
落点不符**。Task 14/16 必须按**实际落点**读（顶层优先、`project_context` 兼容），否则又是
一个 dead output（E1 已实证过同款：读错层 → 恒 undefined → 面板永不渲染，四层验证全绿）。

**顺带确认的两件事**

- `trial_balance` 父子双算再添两例：`2aa00f57` 的 D2 gross（叶子 75,636,774.31 vs trial
  151,273,548.62）与 D3 gross（−6,828,009.01 vs 13,656,018.02）都正好 **2.00 倍**，与
  memory 已记的 H2/H8 同款。三口径如实暴露，未静默取其一 ⇒ Property 5 成立。
- **门 C 的决策依据已齐**：D5/D6/D7 在**全部 8 个项目**都是 `no_data`/`no_account`
  （`amount=None`），无一例外 ⇒ 若选 ②「照显 0.00」，这三个审定表在所有活体项目上都会显示
  一片 0.00 而无法与真实 0 余额区分。建议选 ①。

**验收脚本自身修掉 3 处字段名错**（修前把 48 处脚本异常报成「判据违规」，看起来像取数全线
失败）：`tb.fetch_ok`→`tb.ok`（`fetch_ok` 只存在于载荷 dict）· `slot.standard_codes`→
从 codes 对象取（该字段在 `DCycleAccountCodes` 上）· `dropped` 元素是 **dict** 不是二元组
（两处 `for c, r in ...` 均 `ValueError`）。

### 补齐说明 · Task 11/12（复选框曾是假绿）

复选框标 `[x]` 但**三个守卫文件在磁盘上不存在**，本轮补齐并逐条做变异检验：

| 守卫 | 例数 | Property | 变异 |
|---|---|---|---|
| `tests/d_cycle_extraction/test_d_tb_fetch.py` | 30 | 4/5/10/33 | 6/6 打红 |
| `tests/four_table/test_d_cycle_specs_evidence.py` | 35 | 7/34/35 | 6/6 打红 |
| `tests/d_cycle_extraction/test_d_render_characterization.py` | 33 | 32 | 5/5 打红 |

**变异检验抓出 4 个守卫自身盲区**（首版全绿而变异不打红）：`query_codes` 记未过滤码 ·
无科目槽返 `closing=0` · 备抵侧 `absolute=False` · D5 不再无条件写 `tb_amount`。

**该守卫填了一个平台级缺口**：`test_cycle_specs_row_code_evidence.py` 读的是
`D_CYCLE_SPECS`（**不接线**），从不读 `D_ACCOUNT_SPECS`（render 真实消费的那个）⇒ D2~D7
的 row_code 长期无守卫。新守卫按后者交叉锁死（正是 memory 已登记的「守卫导入错模块」）。

回归：`backend/tests/four_table` + `backend/tests/d_cycle_extraction` = **2014 passed /
2 failed**，2 个失败是 memory 已登记的预存在基线（`test_reference_prefill_*` 拿 K9 当范式
基准，而 K9 已重构走共享件；文件 `git status` 干净且零引用本轮新增符号）。

### Wave 2 交付实录（Task 14 / 15 / 17，2026-08-06）

**Task 14** 新建 `composables/dCycleAccountScope.ts`（委托平台共享工厂 `shared/cycleAccountScope.ts`）。

落地时**两处与 design.md 不符，按实测为准**：

1. **`tb_source_codes` 落点是 `html_data` 顶层，不是 `project_context`** —— 实测 D1/D2/D3/D5/D6/D7 六个写顶层、**只有 D4** 写 `project_context`（design.md 的 Architecture 段按平台惯例写的是后者）。故 `pickDTbSourceCodes` **两层都读**（顶层优先）。只读一层 ⇒ 恒 `undefined` ⇒ 面板永不渲染，而四层验证全绿（E1 已实证同款）。
2. **槽载荷字段名与共享工厂期望不同，必须先归一** —— 后端 `SlotAmounts.as_dict()` 用 `query_codes`，**没有** `codes` / `standard_codes`，而工厂的 `isAccountAbsent()` 在 `found !== false` 时会退到判后两者是否双空 ⇒ 直接委托会把「有科目、有数据」的槽全部误判成「本项目无此科目」。故 `normalizeDSlots()` 先把 `query_codes` 投影成两个字段再交给工厂。

**Task 15** 6 个宿主（D1/D2/D3/D5/D6/D7）补 `:html-data="props.htmlData"` + 6 个 `DNTabAdjudication.vue` 加可选 `htmlData` prop。改造前**只有 D4 传了** ⇒ Task 14 在补完宿主前是 dead output。6 个宿主本就声明了 `htmlData?: any`，缺的只是往下传那一行。

**Task 17** 两个守卫共 **52 例全绿**，**6 个变异全部打红**：

| 变异 | 结果 |
|---|---|
| 只读 `html_data` 顶层（D4 恒读不到） | RED |
| `isDAccountAbsent` 在「无数据」时也返 true | RED |
| `dSlotClosing` 把 null 当 0 | RED |
| D2 兜底备抵码与后端不符 | RED |
| D3 宿主漏传 `:html-data` | RED |
| D6 宿主漏传 `:html-data` | RED |

**🔴 守卫必须锁 `d_account_resolver.D_ACCOUNT_SPECS`（render 真实消费的），不能锁 `four_table/d_cycle_specs.py`** —— 后者 D5 的 gross 兜底是 `()`、前者是 `('1124',)`，锁错模块就是 memory 已登记的「守卫导入错模块」（平台 `test_cycle_specs_row_code_evidence.py` 正是这么漏掉 D2~D7 的）。

验证：7 个改动文件 `get_diagnostics` 零诊断 + **Vite transform 全 200**（Volar 查不出 SFC 结构损坏，必须验 transform）；D 类前端作用域回归 **678 文件 / 1920 例 / 0 失败**。

**剩 Task 16**（审定表带入 + 溯源面板挂载）—— 依赖裁决门 C。本轮验收已实证 D5/D6/D7 在全部 8 个项目都是 `no_data`/`no_account`，门 C 的答复直接决定 7 个审定表的呈现。

### 立项时的实证清单

见 requirements.md 的「关键实证基线」表。其中会被后续任务复核的数字：7 个 render 的 `resolve_semantic_accounts` 引用数（全 0）、`tb_balance` 中 `2205`/`1141`/`1142` 行数（全 0）、`account_mapping` 的 `2205 ← 2204`、`1231` 各子科目金额分布、5 个 NULL 余额子科目、`1122.11` 的 −114,209,110.16、孤儿章数（listed 3 / soe 2）、金额控件计数（43/14/4/3）。

**凡「N 处有问题」这类立项数字，落地前必须用数据驱动守卫复核一遍**（平台已多次出现立项数字偏差，如抽凭宿主 81→78、methodology 消费 42→9）。

### 假绿实证 · Task 18/19（2026-08-06）

复选框曾标 `[x]`，实证**产出全不存在**：

| 判据 | 结果 |
|---|---|
| `scripts/fix/fix_d_cycle_prefill_presets.py` | **文件不存在** |
| 4 处旧 sheet 名（`审定表D0-1` 等） | **HEAD 与工作树都仍在**，新名一个都没有 |
| 6 个明细块（D3-2/D5-2/D5-4/D6-2/D6-3/D7-2） | **HEAD 与工作树都不存在** |
| D 类块数 | HEAD **23** / 工作树 23（+ 本轮 Task 20 的 12 = 35） |

`git show HEAD:backend/data/prefill_formula_mapping.json` 对照证明 HEAD 侧也是旧状态
⇒ 那轮产出**从未落盘**（或被并发会话回退后连 HEAD 一起没了）。属平台已登记的
「并发会话互相回退同一文件」范式，第 4 次实测。

**判「spec 任务是不是真做了」只能按产出物 grep，不能信复选框** —— 且要同时看
**工作树与 HEAD 两侧**，只看工作树无法区分「被回退」与「从未提交」。

### 判据修正 · Task 21（守卫首版有两条过严，实测打红了正确配置）

**① 「明细表不得引用审定表」写得太宽 → 误伤跨循环引用**

首版禁一切「非审定表块引用审定表」，打红了
`D0 核实被函证单位信息D0-2 → WP('D2','审定表D2-1','审定数')`。

而这是**函证覆盖率的分母**（函证金额 ÷ 应收账款审定数），两者不在同一 wp_code 下、
不构成环。正确判据 = **只禁同 wp_code 内**明细表引用自己的审定表；另加一条反向锁死
断言「D0→D2 这条跨循环引用必须仍在」，防被后续会话「顺手清掉」。

**② 「PREV 必须指向自己所在 sheet」是错的判据**

首版打红 6 处，逐个查完全是平台既有范式：明细表/分析表取「上年审定数」自然指向
**本循环审定表**（`PREV('D2','审定表D2-1','审定数')`）。

真正的缺陷形态是**指向源 xlsx 里不存在的 tab**（平台已实证一例：`PREV('E1','分析程序E1-3',…)`
而该 tab 不存在 ⇒ 永远取不到值且不报错）。判据改为「PREV 目标必须是真实 tab」，
并加反向锁死「跨 sheet PREV 范式必须仍在」防被统一成指向自己。

**③ 守卫抓出一个我自己漏改的点（正面价值）**

Task 18 改了块的 `sheet` 字段，但**公式实参里的旧 sheet 名没跟着改** ⇒
`PREV('D0','审定表D0-1','审定数')` 指向不存在的 tab。这是「同一笔错误的两处出现」，
已在脚本里补 1b 步（改块名 + 改实参）并让 `plan()` 把它算进欠账（否则 `--check` 假绿）。

### Wave 3 交付实录

**两个幂等脚本**（都带 round-trip 自检：`json.dumps` 无法逐字复现原文即拒绝写回）：

| 脚本 | 处理项 | `--check` |
|---|---|---|
| `fix_d_cycle_prefill_presets.py`（Task 18+19） | 25 项（4 rename + 1 实参 + 8 cell patch + 6 块 + 6 WP） | 0 |
| `fix_d_cycle_disclosure_presets.py`（Task 20） | 12 块 / 62 cells | 0 |

`prefill_formula_mapping.json`：mappings **258 → 276**，D 类块 **23 → 41**。

**本轮新发现两处口径错**（spec 未列，已修）：

- `LEDGER('6602','credit'/'debit','全年')` 的 description 写「信用减值损失」，而
  **6602 是管理费用**（`account_chart` 20 项目 × 2 source 零分歧）；应收款项减值按
  金融工具准则走**信用减值损失 6702**（6701 = 资产减值损失）。
- `LEDGER('1231','credit','全年')`「本期核销」双重问题：`_resolve_ledger_formula` 是
  `account_code == args[0]` **精确等于**、非前缀匹配，而 `tb_ledger.account_code` 是
  **客户原始码（点号体系）** ⇒ 客户在 `1231.02` 记账时恒 0；退回父码又会把 D1/D6/K1
  的坏账核销一并算进 D2。标准码 `1231-02`（横杠）在点号体系同样命中不了 ⇒ 改
  `PLACEHOLDER` + 登记理由。

**六种括号写法（openpyxl 直读，逐字，禁统一）**：

| 循环 | 上市侧 | 国企侧 |
|---|---|---|
| D1 / D5 | `（上市公司）` | `（国企）` |
| D2 / D3 / D7 | `(上市公司)` | `(国企)` |
| **D6** | **`(上市公司）` 前半后全** | `（国企）` |

守卫 `test_disclosure_sheet_names_are_not_normalized` 断言三种写法必须**同时存在**于
D 类块里（证明没被批量统一），并逐字钉死 D6 的混合写法。

**验证**：守卫 22 例全绿 · 7 个变异（sheet 名错 / 跨循环科目码 / 同循环成环 /
PLACEHOLDER 未登记 / cell_ref 重复 / 披露块被删 / PREV 悬空）**逐条打红并还原** ·
两脚本 `--check` 均 0。

### 立项判断修正 · Task 24（2026-08-06，与原描述结论相反）

**立项按「D3/D7 披露 Tab 里 grep 账龄信号 = 0」判定「未接账龄枚举」，判据选错了。**

平台既定方案是用户 2026-07-30 定的**方案 A**：「账龄口径映射放**同步层**
（`XNoteSectionMap.ts`），项目账龄配置继续只服务底稿内部」⇒ **组件层本来就不该有
账龄真源的引用**，信号为 0 是正确状态而非缺陷。

逐个核实后三条事实：

**① D3 的账龄贯通早已完整实现**

| 层 | 实现 |
|---|---|
| `useD3DisclosureSoe.section1Rows` | **segment-driven**：读 `crossSheet.agingSegments`，按 `seg.dayFrom >= 366` 聚合成两桶 |
| 两桶行 | 带 `rowKey = within1 / over1`，供同步层做「底稿字面 → 附注口径」映射 |
| `d3NoteSectionMap` | `toDisclosureAgingLabel(r, SOE_AGING_OVERRIDES)` 把 `1年以内` 映射成模板字面 `1年以内（含1年）` |

⇒ 项目账龄配置改 3 段 / 5 段 / 自定义时聚合结果自动跟随，**行集无需变化**。

**② 需求 8.2「披露行集随项目账龄配置变化」按源模板实证不成立**

soe 八、38 主表实测 `rows=3`：`1年以内（含1年）` / `1年以上` / `合  计` —— **源模板
就是两档**。按项目配置展开成 6 档 = **自造披露行**（违反「源模板是裁决者」+
「宁缺勿造」）。故该验收标准不予实现，改为守卫**反向锁死**：出现 `1至2年` 这类
档位行即打红。

**③ D7 源模板没有账龄档位表 ⇒ 不引入账龄枚举**

上市 五、39 只有「账龄超过1年的重要合同负债」**逐户明细表**（列 = 项目 / 期末余额 /
未偿还或未结转的原因，数据行是空白可扩行），国企 八、39 **连这张都没有**。

与平台已登记的同族裁决一致：「J2 未折现的离职后福利预计到期分析是**到期分析**不是
账龄」「H 类长期资产无账龄维度，H4 库龄与应收账龄不同构」。

**⇒ Task 24 改为只钉死边界、不加功能**（与 H 类裁决 2 完全同型），防后续会话按
「信号数为 0」再判一次缺陷、把两档展开成多档、或给 D7 硬塞账龄档位。

**守卫的一处盲区已堵**：`it.each(NO_AGING_CYCLES)` 里若文件不存在会静默 `return`
（零断言执行）⇒ 变异脚本里加了**文件存在性自检**，实测 7 个文件全部存在。

### Wave 4 交付实录（Task 24 / 25）

| 任务 | 产出 | 守卫 | 变异 |
|---|---|---|---|
| 24 | 无生产代码改动（结论是「已实现 + 不得引入」） | `dCycleAgingWiring.spec.ts` 13 例 | **6/6 打红** |
| 25 | `scripts/fix/fix_d_cycle_amount_inputs.py` + 63 处替换 | `dCycleAmountControl.spec.ts` 30 例 | **3/3 打红** |

**Task 25 的 63 处（立项写 64）**：`el-input-number` 全部归零；4 个 SFC 的
Vite transform 全 200（Volar 查不出 SFC 结构损坏，必须验 transform）。

`el-input-number` 必须换掉的依据（平台双证）：EP **2.13.6** 的 `input-number` 组件
源码**没有** `formatter` / `parser` prop，浏览器实测输 `1234567.5` 显示
`1234567.50`（**无千分符**）—— 这 63 处金额格的千分符从来没生效过。

**Task 24 的 6 个变异**（逐条打红）：同步层去掉账龄映射 · 两桶聚合改写死档位 ·
给 D7 硬塞账龄真源 import · 映射文件里硬编码模板字面 · 套全局
`DISCLOSURE_TOTAL_LABEL` · soe 八、38 主表被展开成多档账龄。

**合计行字面不可统一**（实测三种并存）：listed 主表/超1年 `合 计`（一空格）、
soe 主表 `合  计`（两空格）、soe 超1年 `合计`（无空格）—— 守卫断言「至少两种不同
字面」以证明该事实仍成立，并禁 `d3NoteSectionMap` 引用全局 `DISCLOSURE_TOTAL_LABEL`。
