# Implementation Plan: prefill-wp-prev-resolution-repair

## Overview

修 `prefill_engine` 的 `WP()` / `PREV()` 两个死链 resolver（337 条预设恒返 `None`），
并把「预设锚点 → `checklist_responses` 真实落点」的对齐关系建成单一真源。

**开工前必读**

- 判据全部来自 2026-08-07 真实库复核，关键数字见 requirements.md 的 Introduction
- **Wave 1 的守卫必须先对当前状态打红**（先改后写无法区分「守卫有效」与「空转」）
- 立项文档的三处判据已被实证纠正（cell_ref 两个口径 / 真实规模 / 键必须含 sheet），
  照旧版数字干活会做错事
- **第三个缺陷（新发现）**：目标列大量是前端派生列（不落库）⇒ 本 spec **不在后端复刻公式**，
  派生列锚点一律进待对齐清单
- `PREV()` 的跨年度修复**在范围外**（数据模型无 year 列），本 spec 只做 fail-closed + 登记

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"], "note": "守卫先打红：cells 零命中实证 + 死链 characterization + 源码守卫（已交付）" },
    { "wave": 2, "tasks": ["4", "5", "6"], "note": "修正 probe 实参 + 锚点映射真源骨架 + 三种聚合纯函数" },
    { "wave": 3, "tasks": ["7", "8"], "note": "持久化列交叉锁死守卫 + WP resolver 接线" },
    { "wave": 4, "tasks": ["9", "10", "11"], "note": "PREV fail-closed + D 循环 12 锚点对齐 + 待对齐/范围外守卫" },
    { "wave": 5, "tasks": ["12", "13"], "note": "真实库验收脚本 + 直跑并反转 characterization" },
    { "wave": 6, "tasks": ["14", "15"], "note": "零回归 + 变异检验 + CI + 收口" },
    { "wave": 7, "tasks": ["16", "17"], "note": "复盘补强：SQL schema 契约（本轮 P0 防线）+ 非底稿 target 独立登记（PL 灰区）" }
  ]
}
```

## Tasks

- [x] 1. 连库实证守卫：`parsed_data.cells` 全库零命中
  - 新建 `backend/tests/test_prefill_wp_prev_resolution.py`
  - 断言 `working_paper` 未删且 `parsed_data` 非空的行中 `? 'cells'` 计数为 **0**
  - 配正向锚点：`? 'html_data'` > 0 且 `? 'wp_code'` > 0（证明扫描面非空，不是查了个空表）
  - 一次 `asyncio.run` 取快照 + 全部断言同步（连接池绑定首个事件循环，每测试各自 async 必炸）
  - _Requirements: 5.2_

- [x] 2. characterization：锁死「修复前恒返 None」
  - 同文件，对 `_resolve_wp_formula` / `_resolve_prev_formula` 用真实库直跑 D 循环实参
  - 断言当前**全部返回 `None`**，并在 docstring 写明「本断言在 Task 7/8 交付后必须反转」
  - _Requirements: 1.1, 4.2_

- [x] 3. 源码守卫：禁 `cells` 读法 + 禁 `PREV` 声称取上年
  - Property 2：扫 `prefill_engine.py`，两个 resolver 函数体内不得出现 `"cells"` / `'cells'`
  - **必须先 `strip_comments()`**（修复说明注释里会如实写出被禁的 `cells` 字样）
  - 反向自检：断言原始源码里确实含该字样（否则计数恒 0 = 断言空转）
  - 截函数体用**圆括号配对跳参数列表 + 缩进配对**，缩进正则写 `[ \t]*` 不写 `\s*`
  - **Wave 3 前预期打红**（当前状态：2 failed / 11 passed，符合预期）
  - _Requirements: 5.1, 5.3, 5.4, 4.1_

- [x] 4. 修正 Task 2 的 probe 实参（已交付守卫的缺陷）
  - 已交付的 `_WP_PROBES` / `_PREV_PROBES` 共 6 条实参**全部不是真实预设**
    （`期末未审余额` / `明细表期末未审数` / `减值准备期末未审数` 等在两个口径下都不存在）
  - 换成 design.md 表格里的 12 个真实三元组（至少取 4 条覆盖 D1/D2/D4/D7）
  - 🔴 不修这条，Task 13 反转 characterization 时**分不清是接线没生效还是实参不存在**
  - 新增一条守卫：probe 实参必须能在 `prefill_formula_mapping.json` 里找到
    （从 JSON 实时解析，防将来预设改动后 probe 又变成幻想实参）
  - _Requirements: 1.1, 2.2_

- [x] 5. 新建锚点映射真源骨架 `backend/app/services/prefill_anchor_map.py`
  - `AnchorAggregate` 三值枚举（`SUM` / `SUM_LIST` / `ROW`）
  - `AnchorSpec` frozen dataclass：`item_id` / `column` / `aggregate` / `row_key` /
    `evidence`（≥20 字带实证标记）/ `serializer_module`
  - `AnchorReadStatus` **六态**枚举 + `AnchorReadResult{status, value, detail}`
  - `ANCHOR_MAP: dict[tuple[str,str,str], AnchorSpec]`（**三元组键**）
  - `UNALIGNED: dict[tuple[str,str,str], str]` / `OUT_OF_SCOPE_CYCLES: dict[str,str]`
  - `OUT_OF_SCOPE_CHANGES: dict[str, str]` —— 需另立 spec 的数据模型/前端变更登记
    （`prev_year_dimension` 与 `frontend_persist_derived_columns` 两条，各带理由与依据）
  - import 期 `assert_map_consistent()`：两表键集互斥 · 键长必须 3 ·
    `ROW` 必带 `row_key` 且非 `ROW` 必不带 · evidence 长度与实证标记
  - _Requirements: 2.2, 2.3, 2.4, 2.5_

- [x] 6. 三种聚合的取值纯函数 + 六态
  - 同模块：`parse_anchor_value(raw: str | None, spec: AnchorSpec) -> AnchorReadResult`
  - **零 DB 依赖**（便于单测 + PBT）
  - 标量态：`'1234.56'` → `HIT`；空串 → `EMPTY`；非数值 → `EMPTY`
  - `SUM`：对 `spec.column` 跨全部行求和；**非数值行跳过不当 0**；全非数值 → `EMPTY`
  - `SUM_LIST`：列值是数值数组（`months[12]`），行内求和后跨行求和
  - `ROW`：按 `row_key` 匹配 `rowId`/`id`/`label`/`category`/`noteType`/`name`（按序），
    **未命中返 `NO_COLUMN` 不回退第一行**
  - 列键不存在于任何行 → `NO_COLUMN`；空数组 → `EMPTY`
  - `detail` 输出取值路径（item_id + 列键 + 聚合方式 + 参与行数）
  - 单测含 Property 7/8 反向自检（空串必得 `EMPTY` / 缺列必得 `NO_COLUMN` /
    `row_key` 未命中不得返第一行值）
  - _Requirements: 1.2, 1.3, 1.4, 7.2, 7.3_

- [x] 7. 🔴 持久化列交叉锁死守卫（本 spec 最有价值的一条）
  - 守卫读前端 composable 源码（`serializer_module` 指向的 `.ts`），抽 `serializeRows()`
    或等价持久化函数真正写入的字段名集合
  - 断言 `ANCHOR_MAP` 每条的 `column` 都在该集合内（`SUM_LIST` 的数组列同样要求）
  - **两条反向自检**：① 拿 `D1-cat-rows` 的 `currentUnadjusted`（已实证的派生列）
    构造替身条目，断言守卫打红 ② 断言抽出的字段集非空（正则失效时集合为空会让断言恒成立）
  - 该守卫把「后端复刻前端派生公式」这一双真源风险变成编译期可检测
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 8. `_resolve_wp_formula` 接线
  - `resolve_anchor` 未命中 → `logger.warning` 点名三参组后返 `None`（不静默）
  - 经 `wp_index` JOIN 定位 `wp_id`（**不依赖 `parsed_data['wp_code']`**，该键仅 63/407），
    多份记录按 `ORDER BY updated_at DESC, id ASC` 确定性选取并在 docstring 说明
  - 查 `checklist_responses(wp_id, item_id).remark` → `parse_anchor_value`
  - 取值调用用 `try/except` 包裹，except 分支内 `logger.warning(..., exc_info=True)`
  - 保持 `len(args) < 3 → None` 与整体 fail-soft 语义
  - _Requirements: 1.1, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1_

- [x] 9. `_resolve_prev_formula` fail-closed + docstring 纠正
  - 删除「同项目 year-1」「从上年底稿取值」失实表述，如实写明「数据模型无 year 维度」
  - 函数体**直接返 `None`**，删掉整个 `WorkingPaper` 查询（绝不回退本年值）
  - 守卫：源码不含 `WorkingPaper` 查询与 `year-1`/`上年底稿` 字样；
    变异「让它回退查本年」必须打红
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [x] 10. D 循环 12 个锚点逐条对齐
  - 对 design.md 表格的 12 个三元组逐个查真实存储键、列键、该列是否在序列化字段集内
  - 表里标「待查/待裁决」的 6 条（#4 D2-3 三个候选键 / #5 D2-1 审定表 / #7 D3-2 /
    #10 D6-3 / #11 D6-2）必须读 `useD2BadDebt*` / `useD3Detail` / `useD6Detail` /
    `useD6ImpairmentDetail` 源码定案
  - 能对齐的进 `ANCHOR_MAP`（`evidence` 写实测列键与序列化位置），
    不能的进 `UNALIGNED`（写原因，派生列一律走这条）
  - **禁按名称相似度猜** —— 每条都要有源码或真实库样本支撑
  - _Requirements: 2.2, 2.4, 3.1, 7.3_

- [x] 11. 待对齐清单 + 范围外登记守卫
  - Property 3：`ANCHOR_MAP` ∪ `UNALIGNED` **== 从 `prefill_formula_mapping.json`
    实时解析出的 D 循环 12 个三元组**（不写死清单，预设变动时自动打红）
  - Property 5：每个键 `len(key) == 3`；并断言真实预设里确实存在「同 `(wp_code, cell_ref)`
    跨两 sheet」的组（D 循环内 `D6 | 期末合计` 即是）—— 证明二元组键会塌
  - Property 13：`UNALIGNED` 条目数 ≤ 上限常量且上限只许下调；每条理由 ≥20 字含实证标记
  - Property 14：`OUT_OF_SCOPE_CYCLES` 覆盖 E/F/G/H/I/J/K/L/M/N 全部非 D 循环，
    每条理由 ≥20 字；且 `ANCHOR_MAP` 里不得出现非 D 循环 wp_code
  - Property 15：显式登记 `prefill_engine._resolve_wp_formula` 与
    `formula_engine._handle_wp` 是两套寻址空间，防后来者"统一"
  - Property 16：`OUT_OF_SCOPE_CHANGES` 必须含 `prev_year_dimension` 与
    `frontend_persist_derived_columns` 两键（后者是让后端能取派生列的正解），
    每条理由 ≥20 字；且断言 `UNALIGNED` 里凡「派生列」原因的条目都指向后一条登记
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 3.4, 4.4, 5.4, 6.1_

- [x] 12. 真实库验收脚本
  - 新建 `backend/scripts/diagnose/verify_prefill_wp_prev_live.py`（**只读**）
  - 对真实项目逐条求值 D 循环 12 个 `WP()` 三元组，按**六态**分组输出
  - 取到数时同时输出取值路径（item_id + 列键 + 聚合方式 + 参与行数）与金额
  - `--all-cycles` 扫全部 337 条只报六态分布
  - 输出用 `Path.write_text(encoding='utf-8')` 自己写盘（绝对路径），控制台只打 ASCII
  - 全部 `NO_ITEM` 时如实报告，**禁构造 fixture 冒充「已修好」**
  - _Requirements: 7.1, 7.2, 7.3, 7.5_

- [x] 13. 直跑验收并反转 characterization
  - 跑 Task 12 脚本，确认已对齐锚点**真取到数**；金额与 `checklist_responses` 逐分核对
  - 反转 Task 2 的「恒 None」断言（改为「已对齐锚点非 None / 未对齐锚点仍 None」）
  - 把实测结果写进 Notes（含具体金额与取值路径，便于下个会话核对）
  - 若真实库该锚点未编制（`NO_ITEM`），Notes 如实记录并说明验收改用哪条 `HIT` 作证据
  - _Requirements: 1.1, 7.1, 7.4, 7.5_

- [x] 14. 零回归验证
  - Property 10：`_FORMULA_RESOLVERS` 键集不变（复用既有
    `test_formula_runtime_zero_regression.py` 基线，**本 spec 不得改它**）；
    其余 8 个 resolver 函数体按哈希断言逐字不变
  - 跑 `-k "prefill or formula"` 全量，与 `git show HEAD:` 版**按失败测试名集合求差集**
  - IF 某既有测试锁定 `cells` 读法 THEN 诚实改写并在 Notes 说明，禁跳过/放宽断言
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 15. 变异检验 + CI 接入 + 收口
  - 变异脚本逐条施加并**按失败测试名集合求差集**判定（不看退出码 —— baseline 本身有红）：
    ① 改回读 `cells` ② 去掉 `wp_index` JOIN 改读 `parsed_data['wp_code']`
    ③ 去掉 `ORDER BY` ④ 让 `PREV` 回退查本年 ⑤ `ROW` 匹配回退第一行
    ⑥ 键改二元组 ⑦ 映射到派生列 ⑧ 去掉 `logger.warning` ⑨ 放宽 `UNALIGNED_MAX`
    ⑩ 删掉 `OUT_OF_SCOPE_NON_WORKPAPER_TARGETS` 的 `PL` 登记（Task 17 的灰区）
  - **实测 10/10 全部 RED**，各由一条**不同**的测试抓住（无一条靠同一断言兜住），baseline 72 passed / 0 failed
  - 变异脚本必须：备份落 `.bak`（不只在内存）+ `try/finally` 无条件还原 + 字节级哈希核验
    + 锚点命中数必须 == 1（多命中/零命中都显式报 ANCHOR-MISS 而非静默跳过）
  - `governance-checks.yml` 新增 job（含 postgres service，因有连库守卫）
  - _Requirements: 5.3, 5.4_

- [x] 16. 🔴 SQL schema 契约守卫（本轮 P0 的唯一防线）
  - **背景**：本轮实测抓到 P0 —— 取值层写 `WHERE workpaper_id = ...` 而
    `checklist_responses` 的真实列名是 **`wp_id`**（无 `workpaper_id` 列）⇒ 每次求值
    抛 `UndefinedColumnError` 被 `except Exception` 吞成 WARNING ⇒ 8 条已对齐锚点
    **全部**仍返 None，而源码守卫 + 44 个纯函数单测 + characterization「恒返 None」
    **三层全绿**（恰好与「修好了」不可区分）
  - `TestAnchorSqlSchemaContract`：连库**真跑** `read_anchor_value` 逐条，
    异常记 `EXC:` 并断言无 `EXC`/`ERROR` 态；断言至少一条 `HIT`
  - 两条自检：① 故意写 `workpaper_id` 的同形查询**必须失败**（证明探针真在发 SQL）
    ② 正确列名 `wp_id` 必须可执行
  - 变异 M2（把列名改回 `workpaper_id`）必须打红
  - _Requirements: 1.8, 1.9, 7.1, 7.2_

- [x] 17. 非底稿 target 独立登记 + 范围外守卫改按预设派生
  - **背景**：原判据 `expected = set("EFGHIJKLMN")` 是写死字母表，结构上表达不了
    非循环字母的 target。实测 `WP('PL','利润表','净利润')` 与 `'上期净利润'` 两条
    （宿主 `M6 明细表M6-2`）：**`PL` 是利润表（报表）不是底稿**，`wp_index` 无此
    wp_code ⇒ 本 spec 取值链结构上取不到；`P` 落在字母表外 ⇒ 这两条既不在
    `ANCHOR_MAP`、也不在 `UNALIGNED`、也不被范围外登记覆盖 = **无人认领的灰区**
  - 新增 `OUT_OF_SCOPE_NON_WORKPAPER_TARGETS` 并登记 `PL`（写明正解是新增一条读
    `financial_report` / `report_config` `ROW()` 的 resolver，属另一 spec）
  - `test_all_non_d_cycles_registered` 改**从预设实时派生**非 D 目标集合，
    要求每个都被两张登记表之一覆盖（前缀与全名两级匹配）
  - 反向自检：登记为「非底稿」的 key 不得是循环编号形态 `^[A-N]\d+$`
    （防有人把真实循环塞进去绕过 per-cycle 对齐）
  - 变异 M10（删掉 `PL` 登记）必须打红
  - _Requirements: 2.6, 2.8, 7.4_

## Notes

### 裁决门状态

无待裁决门。两项已明确为范围外：`PREV()` 跨年度定位（数据模型变更）·
前端把派生列/小计另存为标量 `item_id`（让后端可取用派生值的正解）。

### 🔴 立项判据的三处修正（2026-08-07 实证）

| 项 | 立项文档 | 实测 | 影响 |
|---|---|---|---|
| `WP()` 条数 | 191 | **176** | 规模描述 |
| `PREV()` 条数 | 143 | **161** | 规模描述 |
| WP 分布 D 循环 | 37 | **21** | 工作量估算 |
| PREV 分布 D 循环 | 20 | **38** | 工作量估算 |
| `PREV` 第三参「审定数」 | 118 | **118** ✅ | — |
| D 循环 distinct 三元组 | 22 / 23 / 37（三个版本） | **WP 12 / PREV 32** | Task 10 对象 |
| 「22 个 cell_ref 全 ABSENT」表 | — | **混了宿主 cell_ref 与第三参两个口径**；13 个样例里 7 个两侧都不存在 | 映射对象定义 |
| 「同 wp_code 下 cell_ref 唯一」 | 唯一 | **34 对跨 sheet 复用**（`F2\|期末余额合计\|12 sheets`） | 键必须三元组 |
| `D1-tb-total` / `D2-1-tb-total` / `D1-cat-rows` / `D2-aging-rows` 作实证 | 引用其值 | 前两个 + `D2-aging-rows` **全库不存在**；`D1-cat-rows` 存在但本项目未保存 | Task 10 无正确起点 |
| `checklist_responses` 值形态分布 | 58/25/19/10/5 | **60/28/17/10/5** ✅ 量级一致 | — |

### 🔴 第三个缺陷（本轮新发现）：派生列不落库

`useD1DetailCategory.serializeRows()` 只写录入列，`priorAudited`/`currentUnadjusted`/
`currentAudited` 由 `recalcRow()` 加载时重算、「小计」是 `computed` ⇒ 后端读
`checklist_responses` 拿不到「期末未审数合计」。在后端复刻那套公式就是双真源。
⇒ 本 spec 宁缺勿造：Task 7 的守卫把这条约束结构性钉死。

实测大多数锚点的目标列**确实落库**（`D1-bd-notetype-rows.currentUnadjusted` ·
`D2-detail-rows.endBalance` · `D7-2-rows.endAudited` · `D4-2-rows.months`），
只有 D1-2 这一族是派生列 ⇒ 待对齐清单规模可控。

### 与 `d-cycle-...` spec 的接缝

`d-cycle-four-table-extraction-and-disclosure-completion` 的 Task 20（12 张披露 sheet
预设）依赖本 spec 修通链路才能真正取到数。两 spec 分工：

- 本 spec：修 resolver + 建 `ANCHOR_MAP` + 对齐 D 循环 12 个 `WP()` 三元组
- 该 spec：披露块的**声明**（已落盘，`--check` 归零）

⇒ 该 spec 的 Task 20 可按「声明已交付」勾选，但其 Notes 必须写明「取数依赖本 spec」，
否则下个会话会因 `--check` 归零而误判链路是通的。

### 范围外

- `PREV()` 跨年度定位（需 `working_paper` / `wp_index` 加 year 列或改走 project 年度）
- 前端把派生列/小计另存为独立标量 `item_id`（让后端可取用派生值的正解）
- 其余 9 个循环（E/F/G/H/I/J/K/L/M/N）共 164 条 `WP()` + 全部 161 条 `PREV()`
  的锚点对齐 → 各 per-cycle spec，按本 spec 的机制补
- `formula_engine._handle_wp` 的两参路径（另一条求值链，第三参被静默忽略）

### 🔴🔴🔴 本轮（2026-08-07）抓到的 P0：取值层 SQL 列名写错，四层验证全绿

`read_anchor_value` 的第二条查询写 `WHERE workpaper_id = CAST(:wp_id AS uuid)`，
而 `checklist_responses` 的**真实列名是 `wp_id`**（全列 = `id/project_id/wp_id/item_id/
conclusion/remark/wp_ref/updated_by/created_at/updated_at`，**没有** `workpaper_id`）
⇒ 每次求值抛 `UndefinedColumnError`，被 `_resolve_wp_formula` 的 `except Exception`
吞成 WARNING ⇒ **8 条已对齐锚点全部仍返 None**。

为什么四层验证都没抓到：

| 验证层 | 当时状态 | 为什么漏 |
|---|---|---|
| `get_diagnostics` | 零诊断 | SQL 是字符串字面量，静态分析不校验列名 |
| Property 2/4/5/11/12 源码守卫 | 全绿 | 只查「不许出现 cells」「有没有 ORDER BY」，不查列名是否存在 |
| 44 个纯函数单测 | 全绿 | `parse_anchor_value` 零 DB 依赖，压根不发 SQL |
| characterization「恒返 None」 | 全绿 | **恰好与「已修好」不可区分** —— 这是最毒的一层 |

⇒ 「源码守卫 + 替身单测 + fail-soft 吞异常」这三层组合，**本身就是本 spec 要修的那个
缺陷模式**。唯一防线只能是**真实执行** → 新增 Property 17 / Task 16。

### 真实库验收实测（T13，项目 `0ec33ac9` 重药控股安徽有限公司_2025）

六态分布（3 个项目 × 12 三元组 = 36 次求值）：
`HIT 6` / `NO_ITEM 11` / `NO_WORKPAPER 7` / `UNALIGNED 12` / `EMPTY 0` /
`NO_COLUMN 0` / **`ERROR 0`**

| 锚点 | 实测 | 取值路径 |
|---|---|---|
| `WP('D2','明细表D2-2','期末合计')` | **624,025,343.06** | `D2-detail-rows.endBalance [sum] 1260/1260 行` |
| `WP('D1','坏账准备明细表D1-4',…)` | 0 | `D1-bd-notetype-rows.currentUnadjusted [sum] 2/2 行` |
| `WP('D4','主营业务收入明细表D4-2',…)` | 0 | `D4-2-rows.months [sum_list] 7/7 行` |
| `WP('D4','其他业务收入明细表D4-3',…)` | 0 | `D4-3-rows.currentUnadjusted [sum] 4/4 行` |
| `WP('D7','明细表D7-2','期末合计')` | 0.0 | `D7-2-rows.endUnadjusted [sum] 1/1 行` |
| `WP('D1','原值明细表（按类别）D1-2',…)` | None | UNALIGNED（派生列，**预期**） |

🔴 **`624,025,343.06` 已用独立 SQL 交叉核对** —— `SELECT SUM((r->>'endBalance')::numeric)
FROM checklist_responses cr, jsonb_array_elements(cr.remark::jsonb) r WHERE
cr.item_id='D2-detail-rows'` 得**同值同行数（1260）**，不是拿被测函数的输出证明它自己。

**`value=0` 同样是 `HIT`** —— 「余额为 0」（实证值）与「取不到」（`None`）必须可区分，
这正是六态存在的意义。

### 零回归双证（T14）

1. **函数体逐字节比对** —— 6 个未触碰 resolver（`ADJ`/`LEDGER`/`AUX`/`NOTE`/
   `LEDGER_DETAIL`/`COUNT_LEDGER`）与 `git show HEAD:` 版**逐字节相同**；
   resolver 函数总数 HEAD=9 / 当前=9，`added=[] removed=[]`
2. **广域差集** —— `-k "prefill or formula"` 跑两遍（含本 spec 两个测试文件 vs 不含），
   两侧失败集合**逐条相同 126 条**，「仅在含本 spec 侧新增失败」= **0**；
   且 127 个失败文件中引用 `prefill_anchor_map` 的数量 = **0**
   ⇒ 广域失败属预存在红 / 前序会话遗留（最大簇 `test_report_formula_filler_mirror.py`
   22 条已在 memory 登记）

**顺带修掉一个自己引入又已修的污染源**：模块级 `asyncio.run()` 借用
`app.core.database.async_session` 的共享连接池后关闭 loop ⇒ 同批连库测试报
`RuntimeError: Event loop is closed`（广域 23 errors）。改用 `create_async_engine`
开**专用一次性引擎**（`poolclass=NullPool`）并在**同一 loop 内 `dispose()`` 后：
errors 23→12、passed 3327→3338，且 A/B/C/D 四种加载顺序下 victim 结果逐条相同。

### 变异检验 10/10 RED（T15）

baseline `failed=[] passed=72`。判定按**失败测试名集合求差集**（不看退出码）：

| 变异 | 打红的断言 |
|---|---|
| M1 改回读 `cells` | `test_resolvers_do_not_read_cells` |
| M2 列名改回 `workpaper_id`（本轮 P0 原形态） | `test_read_anchor_value_executes_without_exception` + 另 2 条 |
| M3 去掉 `wp_index` JOIN | `test_at_least_one_anchor_hits_in_real_db` + 另 1 条 |
| M4 去掉确定性 `ORDER BY` | `test_workpaper_lookup_is_deterministic` |
| M5 让 `PREV` 回退查本年 | `test_extraction_is_not_vacuous` |
| M6 `ROW` 未命中回退第一行 | `test_row_mode_does_not_fall_back_to_first_row` |
| M7 映射到派生列 | `test_mapped_columns_are_persisted` |
| M8 去掉 `logger.warning` | `test_unaligned_warning_is_present` |
| M9 放宽待对齐上限 | `test_cap_is_not_raised` |
| M10 删掉 `PL` 非底稿登记 | `test_all_non_d_cycles_registered` |

**过程中修掉 4 个守卫缺陷**（M4/M8/M9 原本无任何断言覆盖；M10 是本轮新发现的灰区），
并纠正 1 个**无效变异**：M7 原本改 `D2-detail-rows.endBalance → priorAudited` 判 GREEN，
实测 `useD2Detail` 是**整行 stringify** 形态故 `priorAudited` 确实持久化（25 键内）
⇒ 该变异合法而非守卫失效；改用**显式白名单**序列化的 `useD1BadDebt`（9 键）才是有效变异。

### 🔴 本轮新发现的灰区：非底稿 target（Task 17 / Property 18）

`WP('PL','利润表','净利润')` 与 `'上期净利润'` 两条（宿主 `M6 明细表M6-2`）——
**`PL` 是利润表（报表）不是底稿**，`wp_index` 无此 wp_code ⇒ 本 spec 的
「`wp_index` JOIN + `checklist_responses`」取值链**结构上取不到**。

而原判据 `expected = set("EFGHIJKLMN")` 是**写死字母表**，首字母 `P` 落在表外
⇒ 这两条既不在 `ANCHOR_MAP`、也不在 `UNALIGNED`、也不被任何范围外登记覆盖
= **无人认领的灰区**（Property 3 只校验 D 循环并集，抓不到它）。

处置：①范围外登记改为**从预设实时派生**（预设新增别的目标会自动打红）
②非底稿 target 单开 `OUT_OF_SCOPE_NON_WORKPAPER_TARGETS`（混进循环登记表会暗示
「补个映射就行」，而真实情况是**取值层要换数据源** —— 读 `financial_report` /
`report_config` 的 `ROW()`，属另一 spec）③守卫按「完整 code 与首字母**两级**」判覆盖。

### 交付清单

| 文件 | 说明 |
|---|---|
| `backend/app/services/prefill_anchor_map.py` | 锚点映射真源（8 已对齐 / 4 待对齐 / 三张范围外登记表） |
| `backend/app/services/prefill_engine.py` | 两个 resolver 改写（前序会话交付，本轮未改） |
| `backend/tests/test_prefill_anchor_map.py` | 46 例（Property 3/4/5/6/7/8/13/14/15/16/18） |
| `backend/tests/test_prefill_wp_prev_resolution.py` | 26 例（Property 1/2/9/11/12/**17**） |
| `backend/scripts/diagnose/verify_prefill_wp_prev_live.py` | 只读六态验收，`--all-cycles` |
| `backend/scripts/diagnose/mutate_prefill_wp_prev_guards.py` | 10 变异，`.bak` + `try/finally` + 哈希核验 |
| `.github/workflows/governance-checks.yml` | job `prefill-wp-prev-resolution`（jobs 133→134） |

守卫合计 **72 passed / 0 failed**。
