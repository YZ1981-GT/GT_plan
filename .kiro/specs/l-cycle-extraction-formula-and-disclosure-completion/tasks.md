# Implementation Plan: L 循环取数、公式预设与披露收口

## Overview

本 spec 分 7 波 24 个任务。**Wave 1 必须先对当前状态打红** —— 先改后写无法区分「守卫有效」与「守卫空转」（平台已多次踩此坑）。

三条施工铁律：

1. **改数据文件一律用幂等脚本**（`--dry-run` / `--check` / `--apply` + round-trip 自检），`prefill_formula_mapping.json` 与两份 `note_template_*.json` 是并发 spec 共享的回退高发文件。
2. **每写完一个守卫必须做变异检验**（改一字看是否变红），三态判定 RED / GREEN / ANCHOR-MISS；GREEN 表示守卫有缺陷必须修，ANCHOR-MISS 表示变异脚本有缺陷。
3. **判「某任务是否真交付」必须逐个探针**，不信 tasks.md 的复选框（本 spec 立项时已实证 L4 披露 Tab 有 4 个 input 但 `saveBatch`/`getField` 全 0 = 录入不落库，比"没做"更坏）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": "W1", "name": "判据先行（守卫先打红）", "tasks": [1, 2, 3], "depends_on": [] },
    { "id": "W2", "name": "公式预设错位修正", "tasks": [4, 5, 6], "depends_on": ["W1"] },
    { "id": "W3", "name": "L7 宁缺勿造呈现 + row_code 收敛", "tasks": [7, 8, 9], "depends_on": ["W1"] },
    { "id": "W4", "name": "附注结构对齐源模板", "tasks": [10, 11, 12, 13], "depends_on": ["W1"] },
    { "id": "W5", "name": "L2 接入 + K3 写权收敛", "tasks": [14, 15, 16, 17], "depends_on": ["W4"] },
    { "id": "W6", "name": "L4 常量校正与接入附注", "tasks": [18, 19, 20, 21, 22], "depends_on": ["W4"] },
    { "id": "W7", "name": "守卫收口、CI 与验收", "tasks": [23, 24, 25, 26], "depends_on": ["W2", "W3", "W5", "W6"] }
  ]
}
```

**并行性**：W2 / W3 / W4 三波互不重叠文件，可并行；W5 与 W6 都改附注载荷侧但章节不同（`五、42`/`八、42` vs `五、46`/`八、50`/`五、43`/`八、46`），亦可并行。W7 必须最后。

**W6 内部有硬前置**：Task 18（校正 `l4NoteSectionMap` 既有常量）必须先于 Task 19/20/21 —— 实证该 map 的 4 个子表名与附注模板不一致（`movement` 少了「的…（不包括…）」整段、`otherFinInstrument` 缺 `（3）` 前缀、缺 `应付债券（续）` 与优先股变动表、`overdue` 指向模板里不存在的表），先接线会一次性产出 4 张孤儿子表。

**W5 内部有硬前置**：Task 14（`l2NoteSectionMap`）与 Task 16（K3 侧撤写权）必须**同一波内成对落地** —— 只做前者会与 `buildK3SyncPayload` 双写同一子表（谁最后保存谁覆盖），只做后者会让「应付利息」子表短暂无人推送。

---

## Wave 1: 判据先行（守卫先打红）

- [x] 1. 公式预设科目一致性守卫（先打红 7 处）
  - 新建 `backend/tests/l_cycle_extraction/test_l_preset_account_coherence.py`
  - 判据分两类：**类 A = 独立口径判据**（源 xlsx 真实 tab 名集合、`L_CYCLE_SPECS` 兜底码、`report_config` 行名实证）现在就应全绿；**类 B = 被测实现**（cells 公式实参、description 科目名）现在应全红且消息写明「预期的 Wave 1 打红结果」
  - 抽科目码前必须整体消费 `SUM_TB('a~b')` / `TB_SUM('a~b')` 形态（区间端点不是被引用科目）
  - `PLACEHOLDER` 类型放行但要求 description ≥30 字
  - 禁在模块顶层 import 生产模块（顶层 import 失败会让整文件 collection error、零断言执行）
  - 配反向自检：把某块公式改回错位形态必须打红
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7, 3.4, 3.8_

- [x] 2. 附注结构三向比对守卫（先打红 5 处）
  - 扩 `backend/tests/test_note_l_cycle_structure.py`（既有 11194 B）
  - 三向 = openpyxl 直读源 xlsx ↔ `note_template_*.json` 的 `headers`/`columns` ↔ 前端同步 `columns`
  - 按 `(章节号, 表名)` 二元组索引（附注模板跨章节大量同名表，按表名全局索引会匹配到会计政策章的空壳版）
  - 打红目标：soe `八、45`/`八、46` 列 key 中文字面量 + `flat` 每列都标 · soe `八、57` 列序 · listed `五、46` t04 单级 5 列 · `五、52`/`八、57` text_sections 为 0
  - 断言「同表两侧 `is_label` 列数相等且为 1」（两侧表态不一致会让 group 索引整体偏移一位）
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 10.1, 10.2_

- [x] 3. 前端接线与契约守卫（先打红 L2/L4 + 常量偏差 + 写权冲突）
  - 扩 `lCycleNoteSubtableContract.spec.ts` 覆盖 L2/L4
  - 新建 `l2l4DisclosureWiring.spec.ts`：断言两循环四个 Tab 有 `useDisclosureAutoSync` + 宿主传 `:project-id`/`:html-data` + 金额走 `WpAmountInput` + 录入真落库（`saveBatch`/`getField` 非 0）
  - **新增判据①：L4 子表名常量必须与附注模板 `tables[].name` 逐字一致** —— 当前应打红 4 处（`movement` 两版 / `otherFinInstrument` 缺 `（3）` / `overdue` 模板不存在 / 缺 `应付债券（续）`+优先股变动表）
  - **新增判据②：`L4_WITHIN1Y_NOTE_SECTION` 必须同时有 `listed` 与 `soe` 两个键** —— 当前应打红（只有 `soe`）
  - **新增判据③：「应付利息」子表键的 payload 写者唯一** —— 扫全前端 `build*SyncPayload`，产出该表键的构造器必须恰为 1 个；当前应打红（`buildK3SyncPayload` 是唯一写者、`buildL2SyncPayload` 不存在）
  - 判据③的实现要能识别「表名来自常量引用」（`T.interest` / `K3_LISTED_SUBTABLE.interest`）而非只认字面量，否则恒判 0 个写者 = 假绿
  - 截函数体一律**圆括号配对跳参数列表**后再找 `{`（多行签名 + 内联返回类型注解会让「声明后第一个 `{`」命中类型字面量）
  - 断言「A 真的被 B 调用」的判据必须落在 B 的实参区/函数体内，不能在整份源码 `toContain`
  - `REPO_ROOT` 用双哨兵具体文件向上查找，禁写死回退级数
  - _Requirements: 4.7, 4.8, 4.9, 4.13, 5.5, 5.7, 5.8, 5.9, 5.10, 5.11, 5.13, 5.14, 10.1_

## Wave 2: 公式预设错位修正

- [x] 4. 幂等脚本修 5 个审定表块（类 A）
  - 新建 `backend/scripts/fix/fix_l_cycle_prefill_presets.py`
  - `审定表L2-1` `2501`→`2231` · `审定表L4-1` `2601`→`2502` · `审定表L5-1` `2502`→`2701` · `审定表L6-1` `2701`→`2711`，同步改 description 科目中文名
  - `审定表L7-1` 四个 cells 改 `PLACEHOLDER`，description 写明「其他非流动负债在 CAS 无专属科目；`2801` 是预计负债、`2901` 是递延所得税负债，均不得采用」
  - `审定表L1-1`/`L3-1`/`L8-1` 三块**逐字节不变**（零回归，脚本内 assert 钉死）
  - round-trip 硬闸：`json.dumps(indent=2)+"\n"` 不能逐字复现原文即 exit 2
  - 控制台输出禁 emoji（GBK 崩在写盘之后，会误判成 apply 失败）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.6_

- [x] 5. 幂等脚本修 2 块明细表 + 删 1 个幽灵块（类 B）
  - `明细表L5-2` 整块迁到 wp_code `L4` / sheet `应付债券明细表L4-2`（源 xlsx 真实 tab 名）
  - `明细表L6-2` 整块迁到 wp_code `L5` / sheet `明细表L5-2`
  - 删 `L1 分析程序L1-3` 块（sheet 在源 xlsx 不存在 + `TB_SUM('2001~2501')` 病态区间会扫进 2201~2241 整段负债），脚本内登记删除依据
  - 改 sheet 名时必须同步改同块内 `PREV('LN','<旧 sheet 名>',...)` 第二实参（否则 `--check` 假绿）
  - 迁移后 L5/L6 各自明细表若无预设则显式登记「无预设」及理由
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 6. Wave 2 验证与零回归
  - Task 1 守卫转全绿；`--check` 0 欠账；二次 `--apply` md5 逐字节不变
  - 变异检验：把任一块公式改回错位形态 → Task 1 守卫必须 RED
  - 零回归**前后对照**（改动前 vs 改动后，禁 HEAD-swap —— 该 JSON 混着并发会话改动）：L1/L3/L8 三块 md5 不变
  - 跑 `backend/tests/l_cycle_extraction/` 与 `four_table/` 全量，失败集合与改动前逐条相同
  - _Requirements: 10.6, 11.6_

## Wave 3: L7 宁缺勿造呈现 + row_code 收敛

- [x] 7. L7 溯源面板三态呈现
  - 复用共享件 `WpFourTableSourcePanel.vue`（已支持三态），**不得新建第二套判据**
  - `prefill_supported=False` 时显示「本项目无此科目，需手工填列」+ 展示 `note` 依据，用 `info` 不用 `danger`（宁缺勿造是正确行为）
  - 判据是 `prefill_supported === false` **显式为 false**，字段缺失（undefined）不等于「无此科目」
  - 审定表「未审数」格保持可手工录入、不被预填覆盖
  - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [x] 8. L7 row_code 双真源收敛
  - 以 `report_config` 实测为裁决依据统一 L7 的 row_code（`BS-071`/`BS-097` vs `BS-068`）
  - 两侧 docstring 交叉标注「另一份的用途与消费方」（`four_table/l_cycle_specs.py` 的 `L4_SPEC`/`L5_SPEC` 被 `l0_book_amounts.py` 消费，含 `is` 同一性断言）
  - 因 L7 `fallback_codes` 为空且报表公式不采用，取数金额必须逐字节不变
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [x] 9. Wave 3 守卫
  - 断言 L7 `fallback_codes` 为空元组 + 反向自检「给它加兜底码必须打红」
  - 断言 `report_config` 实证（行名 + 公式）已冻结进守卫常量
  - 变异检验：改 L7 兜底码 / 改 row_code / 把三态判据改成真值判断，逐条必须 RED
  - _Requirements: 8.5, 9.2, 10.3_

## Wave 4: 附注结构对齐源模板

- [x] 10. soe 八、45 / 八、46 列 key 规范化
  - 中文字面量 key（`项目`/`期末余额`/`期初余额`）改平台惯例（`label`/`end_amount`/`prior_amount`）
  - `flat` 只标标签列，不得每列都标
  - 改 key 前必须核实 `sub_table_data` 是否已有按旧 key 持久化的数据；投影器 `_project_row` 有标签列双向兜底，但**数据列 key 改动有真实丢数风险**，须逐项核实
  - _Requirements: 6.1, 6.2_

- [x] 11. soe 八、57 列序 + 五、46 t04 补列并恢复两级表头
  - **`八、57` 改为与源模板一致的列序**（已裁决，不留「登记偏离」逃逸阀）：源 xlsx `L7!附注披露信息(国企)!A6/B6/C6` = 项目 / **年初余额** / **期末余额**；模板当前是 项目 / 期末余额 / 期初余额 ⇒ 调换后两列的顺序与 label
  - 调换列序时 **`key` 保持不变**（`end_amount` 仍是期末、`prior_amount` 仍是期初），只改数组顺序与 label 字面 ⇒ 已持久化数据零丢失
  - 该改动使两版列序刻意相反（listed = 期末数/上年年末数），守卫必须断言两版列序**不相等**（防「顺手对齐」）
  - **`五、46` t04 不是「只加 group」而是「补 4 列 + 加 group」**：源 `r063/r064` 是 1 + 4 组 × (数量/账面价值) = **9 列**，模板当前 5 列只保留了「数量」（`begin_count`/`increase_count`/`decrease_count`/`end_count`）、**丢了全部 4 个「账面价值」列** ⇒ 必须新增 `begin_value`/`increase_value`/`decrease_value`/`end_value` 并按 `期初余额`/`本期增加`/`本期减少`/`期末余额` 四组各 span=2 加 group
  - **标签列不得标 `flat`** —— `flat` 标在任一列即让 `_extract_column_groups` 整表返 `[]`、group 被永久打掉
  - 注意 soe 侧同款表的组名是「期初数 / 期末数」（源 `r052`）而 listed 是「期初余额 / 期末余额」（源 `r063`），两版组名不同不得统一
  - t04 是条件表且本 spec 不接推送 ⇒ 只改模板 seed，不动载荷
  - _Requirements: 6.3, 6.4_

- [x] 12. text_sections 补齐 + columns/guidance 收口
  - `五、52`/`八、57` 补说明段；listed 源模板无说明段则如实登记为零，不得自造
  - 每张表同时有 `columns`（label/key/format）与 `guidance`；`guidance` 只取源模板红字 / 附注模版括注 / 准则条款
  - `guidance` 纯文本，禁 markdown 粗体（与平台级 `fix_note_bold_markers.py` 互相打架）
  - 裸表名不得作 text_sections（会被当披露正文渲染）
  - _Requirements: 6.5, 6.6, 6.7_

- [x] 13. Wave 4 幂等脚本与验证
  - 改扩既有三个脚本之一或新建，只声明本 spec 负责的章节（不得越权改别的循环）
  - `row_type` 取值域不得擅自扩张；已标 `expandable` 的行必须保留
  - 两次 `--apply` md5 逐字节不变；`--check` 0 欠账
  - 顺带核实既有三个 `fix_note_l*.py` 仍 0 欠账（判据可能被本次改动打破）
  - _Requirements: 6.8, 6.9, 7.8, 11.3_

## Wave 5: L4 既有常量校正（P0，硬前置于 Wave 7）

- [x] 14. 校正 `l4NoteSectionMap.ts` 的子表名与章节号常量
  - **本任务是 Wave 7 的硬前置** —— 不做就会一次性产出 4 张孤儿子表（`sync_from_workpaper` 按表名浅合并，模板里没有该表名 ⇒ 推过去投影器不渲染）
  - 实证 4 处不一致（`五、46` 真实 5 张表 / `八、50` 真实 2 张表）：
    - `movement`：`'应付债券增减变动'` → **`'应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）'`**（listed 与 soe 都要改）
    - `otherFinInstrument`：`'划分为金融负债的其他金融工具'` → **`'（3）划分为金融负债的其他金融工具'`**（模板表名带序号前缀）
    - 缺 `continued`：需新增指向 **`'应付债券（续）'`**（`五、46` t02，8 列，Task 17 的续表落点）
    - 缺 `otherFinInstrumentMovement`：需新增指向 **`'期末发行在外的优先股、永续债等其他金融工具变动情况'`**（`五、46` t04）
  - `overdue`（`'已到期未偿付的应付债券'`）：两份模板**均无此表**且源 xlsx 也无对应段 ⇒ **删除该键**并在 `L4_LEGACY_OBSOLETE_TABLES` 登记（附带理由：模板与源模板双侧均不存在）
  - 补 **`L4_WITHIN1Y_NOTE_SECTION.listed = '五、43'`**（实测该常量只有 `soe` 一个键 ⇒ listed 侧第二个 payload 无处可发）
  - `within1y`（`'一年内到期的应付债券'`）在 `五、43` t02 与 `八、46` t01 **都存在且同名**，listed 侧另有 `'一年内到期的应付债券（续）'`（t03，7 列）、soe 侧另有 `'（2）一年内到期的应付债券'`（t00，5 列）⇒ 两版 within1y 子表结构不同构，各自声明
  - 改常量前必须核实 `sub_table_data` 是否已有按旧表名持久化的数据；旧表名进 `L4_LEGACY_OBSOLETE_TABLES` 并由 `_removed_table_keys` 与本次推送键**求差集**后发送（禁无条件删）
  - 顺带核 `lCycleNoteSubtableContract.spec.ts` 对 L4 的既有断言是否锁定了旧表名（锁定则诚实改写并说明「旧值与模板不符」）
  - _Requirements: 5.11, 5.12, 5.13, 5.14, 5.15_

## Wave 6: L2 接入 K3 章节 + K3 侧写权收敛

- [x] 15. 新建 l2NoteSectionMap.ts
  - 章节号取 K3 的 `五、42`（listed）/ `八、42`（soe）
  - 子表名逐字取自附注模板：listed `应付利息` + `重要的逾期未付利息`；soe `应付利息` + `重要的已逾期未支付的利息情况`
  - 列 key 逐字对齐模板（`label`/`end_amount`/`prior_amount`；逾期表 `label`/`overdue_amount`/`overdue_reason`）
  - 行集：listed 7 行 / soe 6 行，**两版不对称是源模板事实不得对齐**（listed 有「其中：工具1/工具2」、soe 有「其他利息」）
  - 文件名必须匹配 `^([a-z]+\d+)NoteSectionMap\.ts$`（否则 registry 生成器与 sheet 名守卫都扫不到）
  - 章节号常量必须是**内联字符串字面量**、对象体内不得写注释（生成器正则限制）
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 16. L2 披露 Tab 接线（保留 L2-2 自动聚合口径）
  - 两个 Tab 当前是**纯只读展示**（input/textarea 全 0），数据来自 `useL2Disclosure` 从 `L2-L2-2-rows` 自动 SUMIF 聚合 —— **该聚合口径是源模板要求的，必须保留**（源 `附注披露（上市公司）信息!B8 = SUMIF('明细表L2-2'!A:A,…,'明细表L2-2'!U:U)`）
  - 故本任务**不加手工录入区块**，只接推送：`useDisclosureAutoSync` + watch `disclosureTableData`/`overdueRows`（**实际数据**，与构建载荷字段一致），禁 `scheduleAutoSync(syncToNotes)` 自调度
  - 宿主 `GtL2InterestPayable.vue` 传 `:project-id` 与 `:html-data`（实测宿主对披露 Tab 的 `TabDisclosure` 引用计数为 0，需先确认分发链是否用 `<template v-else-if>` 包住）
  - 只推自己负责的两张子表，`五、42`/`八、42` 内其余子表原样保留；不得声明 `_removed_table_keys` 指向 K3 的子表
  - 逾期利息行来自 `overdueRows`（`isOverdue` 或 `overdueMonths > 0` 过滤），源模板 r18~r33 是 16 行 IF 公式区 ⇒ 行数由实际数据决定，不预置占位行
  - _Requirements: 4.5, 4.6, 4.7, 4.8, 5.9_

- [x] 17. K3 侧写权收敛（应付利息 / 逾期利息两张表）
  - `buildK3SyncPayload` 停止写 `T.interest` 与 `T.interestOverdue`：既不进 `sub_table_data`、也不进 `_removed_table_keys`（后者会删掉 L2 刚推的数据）
  - 同步删掉 `columns` 里这两张表的条目（当前实现是 `delete columns[T.interest]` 的反向逻辑，改为**恒不写入**）
  - K3 两个披露 Tab 的 `interest` / `interest-overdue` 两个 section 改**只读展示 + 「前往 L2 编辑」跳转**（复用平台既有 `GtIndexChip` 或 `router.push` 范式），既有录入值**不删除**（数据零丢失）
  - K3 主表（`其他应付款` 汇总表）的「应付利息」汇总行：当前读 `sumEnd(interestRows)`（K3 自己的录入），改为读 L2 的持久化聚合结果；**L2 无数据时回退读 K3 旧键**（过渡期兼容），回退分支必须在守卫中登记退役条件
  - 顺带核 K3 的 `K3_SUMMARY_ROWS` 与 `K3_INTEREST_ROWS` 是否还有其他消费方（只改写权、不动行集常量）
  - **本任务与 Task 16 必须同批交付** —— 只做一侧会出现「两个写者」或「零个写者」的中间态
  - _Requirements: 4.10, 4.11, 4.12, 4.14, 11.7_

- [x] 18. L2/K3 守卫与 registry
  - 重跑 `gen_note_wp_sync_registry.py --write` 并核 diff 范围（`l2NoteSectionMap.ts` 文件名匹配 `^([a-z]+\d+)NoteSectionMap\.ts$` 才会被扫到）
  - 从 `MISSING_SYNC_PATH` 移出 L2 两个 Tab，**并删除那段「L2 有意豁免」的三行理由注释**（保留会让下个会话以为仍豁免）
  - **写权唯一性守卫**（Property 27）：全前端只有 `buildL2SyncPayload` 会产出 `应付利息` 子表键；`buildK3SyncPayload` 的产出键集不含它
  - 子表契约（表名/列 key/行集/合计行字面）+ 跨循环共享章节表名零交集断言（`五、42`/`八、42` 的 K3 与 L2 表名两两求交集为空）
  - 变异检验：改表名 / 改列 key / 两版行集对齐 / 加 `_removed_table_keys` / **让 K3 重新写 interest**，逐条必须 RED
  - _Requirements: 4.9, 4.13, 10.1, 10.3_

## Wave 6: L4 接入附注

**前置：Task 14/15 必须先完成** —— 常量未校正就接线会一次性产出 4 张孤儿子表。

- [x] 19. L4 上市披露录入区块（三张表 + 可转债文字）
  - 主表（项目/期末余额/上年年末余额）· 增减变动（6 列 + 小计）· 续表（8 列 + 小计/减：一年内到期的应付债券/合计）
  - 可转债说明提供文本录入位置，经 `_note_texts` 推送且**必须带中文 `title`**（否则附注正文渲染成英文键）
  - 金额走 `WpAmountInput`；票面利率/债券期限/是否违约不得套用
  - 派生列（小计/合计）**读时推导不持久化**
  - _Requirements: 5.1, 5.4, 5.9_

- [x] 20. L4 国企披露录入区块（两张表）
  - 主表（项目/期末余额/期初余额 + 小计/减：一年内到期的应付债券/合计）
  - 增减变动 10 列（债券名称/面值/发行日期/债券期限/发行金额/年初应付利息/本期应计利息/本期已付利息/期末应付利息/期末余额）
  - 与上市侧列结构不同构，禁共用一份列常量
  - 表名用 Task 15 校正后的 `L4_SOE_SUBTABLE.movement`（`应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）`）
  - _Requirements: 5.2, 5.5, 5.13_

- [x] 21. L4 条件表与一年内到期分发
  - 「划分为金融负债的其他金融工具」+「期末发行在外的优先股永续债变动情况」按条件表：有行才推；无行不推空表**且**键进 `_removed_table_keys`（底稿有录入区块的条件表语义）
  - 表名用 Task 15 校正后的值（`（3）划分为金融负债的其他金融工具` 带序号前缀 / `期末发行在外的优先股、永续债等其他金融工具变动情况`）
  - 一年内到期的应付债券：listed 落 `五、43`、soe 落 `八、46`，**分别发独立 payload**（`sync_from_workpaper` 定位键只含 `note_section`）；listed 落点依赖 Task 15 补上的 `L4_WITHIN1Y_NOTE_SECTION.listed`
  - listed 侧 `五、43` 是 `一年内到期的应付债券`(5 列) + `一年内到期的应付债券（续）`(7 列) **两张表**；soe 侧 `八、46` 是 `（2）一年内到期的应付债券`(5 列) + `一年内到期的应付债券`(7 列) 两张表（**soe 第二张表名无「（续）」且与 listed 第一张同名**，禁按同一常量套用）
  - `五、43`/`八、46` 是跨循环共享章节（L3 长期借款 / L4 应付债券 / L5 长期应付款），只推自己那两张、其余原样保留
  - 动态插行区：源模板 r050/r059/r070「可无限加行」必须支持增行；增行需命名的先 `ElMessageBox.prompt`
  - 骨架行数 `max(seed 行数, 1)`，不得预置空占位行
  - _Requirements: 5.3, 5.6, 7.3, 7.4, 7.6, 7.7_

- [x] 22. L4 接线、守卫与 L5/L6/L7 动态行
  - 两个 Tab 接 `useDisclosureAutoSync` + 宿主 `GtL4BondsPayable.vue` 传两个 prop
  - **修实测已发现的缺陷**：L4 现有 4 个 input 但 `saveBatch`/`getField` 全 0 = 录入不落库
  - L5 上市「按款项性质列示」r014/r018 两处 `…` 支持段内增行
  - L6 上市 r009~r018 / L7 两版 r007~r011 空白可填区改动态行，不得写死行数
  - 推送后删行必须让附注同步减少（整表覆盖语义）
  - 从 `MISSING_SYNC_PATH` 移出 L4 两个 Tab（连同「L4 需结构对齐重建」注释块一并删除）
  - _Requirements: 5.7, 5.8, 5.10, 7.1, 7.2, 7.5, 7.9_

## Wave 7: 守卫收口、CI 与验收

- [x] 23. 变异检验全轮
  - 新建 `backend/scripts/diagnose/mutate_l_cycle_guards.py`
  - 备份落 `.bak` + 提供 `--restore`；锚点**行级唯一**（命中数 == 1），禁含 `\n` 的跨行锚点（CRLF 工作树必 MISS）
  - 判定按失败测试名**差集**（不看退出码 —— Wave 1 守卫基线本就有红）
  - 三态报告 RED / GREEN / ANCHOR-MISS；GREEN 必须修守卫
  - 还原后核验：被变异那一行回到正确形态 + md5 与变异前逐字节相同
  - **≥18 项变异**（原 14 项 + 新增：K3 仍推 interest / L4 子表名改回旧值 / `within1y.listed` 删除 / 八、57 列序改回）
  - _Requirements: 10.3, 10.4_

- [x] 24. CI job
  - `governance-checks.yml` 新增后端 + 前端两个 job，把幂等脚本 `--check` 纳入步骤
  - 该 yml 混着并发会话未验证 job → 只加自己的、加完 `yaml.safe_load` 验证可解析且 job 名无重复
  - subprocess 跑幂等脚本必须 `encoding="utf-8", errors="replace"` 并断言 `stdout is not None`（`text=True` 在 GBK 下让 stdout 变 None、守卫恒红零信号）
  - _Requirements: 10.5, 11.6_

- [x] 25. 真实库验收
  - 新建 `backend/scripts/diagnose/verify_l_cycle_live.py`（**只读**，禁 `--apply`）
  - 对有 L 类数据的项目逐个直跑 render，输出 `tb_source_codes.resolved_from` / `parent_check.diff` / 各桶金额 / `current_portion`
  - 与**独立 SQL** 交叉核对（不拿被测函数证明自己）
  - 无合法验收对象时诚实输出「无法验收」+ rc=1，禁用 fixture 冒充
  - 连库探针用**专用一次性 engine**（`poolclass=NullPool`）+ 同 loop 内 `dispose()`，不碰共享池（否则污染同批连库测试）
  - _Requirements: 10.7, 9.3_

- [x] 26. 浏览器实测与数据复原
  - 实测三件套：录入真实数据 → 看目标区域出数 → postgres 查 `checklist_responses` 与 `disclosure_notes` 落库，缺一不算实测
  - 覆盖：L2 两版推送到 `五、42`/`八、42` 的应付利息子表 · **K3 两版该区块已转只读且「前往 L2」跳转可用** · L4 两版推送到 `五、46`/`八、50`（**校正后的表名**）+ 一年内到期分发（listed `五、43` / soe `八、46` 两个独立 payload）· L7 三态提示 · 动态行增删 · 金额千分符
  - **K3 收敛实测判据**：在 L2 录入 → K3 主表「应付利息」汇总行随之变化（证明 4.12 的取数口径已切换）；在 K3 侧确认无法编辑该区块（证明写权唯一）
  - **L4 表名校正实测判据**：推送后 `disclosure_notes.table_data.sub_table_data` 的键必须是 `应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）` 而非旧名，且 `五、46` 无孤儿子表
  - 实测前抓基线（全文 + `md5` + `jsonb_typeof`，不只记 length）
  - 复原走**原子事务**，复原后用独立只读查询逐项核实
  - 清理 `_wip_*` / `tmp_*`（判归属靠 mtime + 内容关键词，不靠文件名里的任务号）
  - _Requirements: 10.8, 10.9, 10.10_

---

## Notes

### 与并发 spec 的边界

| 并发 spec | 共享文件 | 处置 |
|---|---|---|
| `e-cycle-…`（16/8） | `prefill_formula_mapping.json` · 两份 `note_template_*.json` | 幂等脚本 + 只显式暂存自己路径 |
| `g7-column-alignment-…`（3/21） | 两份 `note_template_*.json` · `governance-checks.yml` | 同上；G7 在改列结构，本 spec 只碰 L 章节 |
| `procedure-trimming-…`（12/14） | 无交集 | — |
| `h-cycle-…`（17/0，Task 18 `[-]` 有意驻留） | `dual_family_codes.py`（H9 租赁负债 `2601`） | 只读不改 |
| `report-config-account-code-integrity`（已归档） | `report_config` 表 | 本 spec 不改该表数据 |

### 三条裁决（2026-08-09 用户拍板，开工前必读）

| # | 议题 | 裁决 | 落点 |
|---|---|---|---|
| 1 | L2 与 K3 竞争同一张「应付利息」子表 | **收敛到 L2**：K3 侧改只读 + 跳转，写权唯一 | R4.10~4.14 / Task 3、17、18 |
| 2 | `l4NoteSectionMap` 既有常量与模板不一致 | **作 Wave 5 前置任务先校正**，再接推送 | R5.11~5.15 / Task 14、15 |
| 3 | soe `八、57` 列序 | **改为与源模板一致**（项目/年初余额/期末余额），不留「登记偏离」逃逸阀 | R6.3 / Task 11 |

**裁决 1 的依据**：源模板 `附注披露（上市公司）信息!B8 = SUMIF('明细表L2-2'!A:A, …, '明细表L2-2'!U:U)` —— 该表本就由 L2-2 明细驱动；K3 侧那份是 `Array.from({length:3})` 的手工空行 = 重复录入。收敛后审计师只在 L2-2 录一次。

**裁决 2 的实证**（`l4NoteSectionMap.ts` vs 两份模板逐字比对）：

| map 声明 | 模板真实表名 | 处置 |
|---|---|---|
| `movement: '应付债券增减变动'` | `'应付债券的增减变动（不包括划分为金融负债的优先股、永续债等其他金融工具）'` | 改名（两版都要） |
| `otherFinInstrument: '划分为金融负债的其他金融工具'` | `'（3）划分为金融负债的其他金融工具'` | 补 `（3）` 前缀 |
| `overdue: '已到期未偿付的应付债券'` | **两份模板都不存在** | 删（源模板无对应表） |
| — | `'应付债券（续）'` | 新增 `movementCont` |
| — | `'期末发行在外的优先股、永续债等其他金融工具变动情况'` | 新增 `instrumentChange` |
| `L4_WITHIN1Y_NOTE_SECTION` 只有 `soe` | listed 侧要发 payload | 补 `listed: '五、43'` |

### 已知不做（防返工）

1. **L0 函证循环**：无披露 sheet，已由归档 spec `l0-confirmation-source-alignment` 收口；其「样本选择 6 项在 `L0SummaryLowerZone.vue` 内、共享组件里 `v-if="!isL0"` 有意关掉」是既有裁决，**不得**「补上 `isL0` 分支」。
2. **L6 独立附注章节**：专项应付款并入 L5 的 `五、48`/`八、53`，由 `l5NoteSectionMap.ts` 统一承载（`L6_LISTED_SUBTABLE`/`L6_SOE_SUBTABLE`），沿用不改。
3. **K5 预计负债 / K7 递延收益 / H9 租赁负债**：它们正是错位公式误指的科目，本 spec 只修 L 侧。
4. **`report_config` 错码**：归 `report-config-account-code-integrity`。
5. **L4 源模板两组同索引号 sheet**（两个 `L4-7`、两个 `L4-8` 且一个尾部带空格）：只加守卫防按尾码分发撞车，不改源模板。
6. **`procedure_table_templates.json` 根级独有的 `L0A`**（`get_template` 返 None）：平台级待办。

### 立项时的实证事实（备查）

- **取数链路完整**：`l_cycle_extraction/account_scope.py`（生产真源，`LCycleSpec` 形态）+ `render_support.build_l_tb_payload` 下发 `trial_balance` / `tb_source_codes` / `adjudication_prefill` / `l_bucket_defs`；含叶子聚合、父额勾稽、分类桶、「一年内到期」拆分。**本 spec 不重建取数链路**。
- **`L_CYCLE_SPECS` 两个同名导出**：`l_cycle_extraction/account_scope.py`（生产消费）vs `four_table/l_cycle_specs.py`（仅测试与 L0 消费）。一律改前者。
- **公式预设错位 7 处**（亲自复核）：审定表 L2→`2501` / L4→`2601` / L5→`2502` / L6→`2701` / L7→`2801`；明细表 L5-2 内容是应付债券、L6-2 内容是长期应付款。其中四处是活的错数（`2601` 在 `tb_balance` 该前缀 0 行故 L4 表现为恒空）。
- **既有守卫盲区**：`test_l_cycle_formula_presets.py` 对 `expression`/`description` 命中数为 **0**，只校验 `wp_name` 与 `account_codes`（这两项已被某轮修对）。
- **L2/L4 推送链路全死**：四个 Tab 的 `useDisclosureAutoSync`/`syncToDisclosureNotes`/`buildXSyncPayload` 计数全 0。L2 是纯只读展示（input/textarea 全 0）；L4 有 4 个 input + 2 个 textarea 但 `saveBatch`/`getField` 全 0 = 录入不落库。
- **L2 落点已确认**：`五、42`/`八、42` 的 t01「应付利息」是**独立子表**（listed 7 行 / soe 6 行），行标签与 L2 源模板逐字对应 ⇒ 走既有表级浅合并即可，**不需要行级合并**。
- **🔴 但 K3 已在推这两张表**（本轮新查出，是裁决 1 的由来）：`buildK3SyncPayload` 有 `if (snapshot.interest.length > 0) sub[T.interest] = interestRows`，`K3_LISTED_SUBTABLE.interest = '应付利息'` / `.interestOverdue = '重要的逾期未付利息'` 与 L2 目标表**完全同名**；且 `disclosureAutoSyncCoverage.spec.ts` 已把 L2 两个 Tab 登记为「有意豁免」并写明理由「K3 已实装推这两张表 → L2 再推会互相覆盖」。⇒ 不做收敛而直接接 L2，会变成「谁最后保存谁覆盖」。
- **🔴 `l4NoteSectionMap` 既有常量有 4 处与模板不一致 + 缺 2 张表 + `L4_WITHIN1Y_NOTE_SECTION` 缺 listed 键**（见上方裁决 2 表格）⇒ Requirement 5.5 的「用既有常量」与「与模板逐字一致」当前互相矛盾，必须先校正常量。
- **附注 16 个 L 章节 `aligned_by` 齐备**，columns/guidance 基本补全，长期借款两级表头（期末余额/上年年末余额 × 余额/利率区间）正确。
- **前端 6 个 map 齐备**（l1/l3/l4/l5/l7/l8），缺 l2（本 spec 建）与 l6（有意合并进 l5）。
- **披露 sheet 名五种写法并存**（`附注披露信息核对（上市公司）` / `附注披露（国企）信息` / `附注披露信息(国企)` 半角 等），禁统一。
- **L3 两版都有独立「（1）一年内到期的长期借款」表**（4 类 + 合计），listed 侧已在 `五、43`。
- **L7 两版列序相反**：listed「期末数/上年年末数」· soe 源模板「年初余额/期末余额」，而附注 `八、57` 现为「期末余额/期初余额」⇒ **soe 侧是真差异，裁决 3 定为改对齐源模板**（Task 12）。
- **🔴 动态插行区位置已按源 xlsx 逐格核正**（原立项记载有误）：**L2 上市 r12/r13 不是可扩位** —— 它们是固定行「其中：工具1」「工具2」且带 `SUMIF('明细表L2-2'!A:A,…)` 公式；L2 真正的可扩区是 **r18~r33 的逾期利息 16 行**（`=IF('明细表L2-2'!V12>0,…)` 由明细驱动，非手工增行）。L4 的三处 `可无限加行` 位置为 **listed r050 / r059**（`……` 在 r060）与 **soe r039 / r059**（`……` 在 r049）。
- **L4 披露 sheet 名是 `附注披露信息核对（上市公司）`/`（国企）`**（带「核对」二字，与 L1/L3 同族）—— 立项时列举的「五种写法」未含这一种，守卫的 sheet 名清单要补。

### 实测目标候选

需先查有 L 类数据（`2001`/`2501`/`2502`/`2701`/`2711`/`6603` 有余额）的项目。已知 `6603` 全库有数据（`543,020,073.49` 借贷双侧相等 —— 这正是 L8 曾用 `debit - credit` 恒为 0 的原因，现已改走 `trial_balance` 本期发生额）。
