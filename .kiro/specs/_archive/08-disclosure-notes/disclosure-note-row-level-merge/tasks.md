# Implementation Plan: 附注同步行级合并（平台级）

## Overview

5 个 wave、14 个任务。核心是给 `wp_disclosure_sync_service` 加一层**可选**的行级合并
（`sub_table_data._row_scope` 触发），段边界读模板**已有**的 `rows[].report_row_code`。

**风险面**：改的是 90+ 个已接线披露 Tab 共用的核心写路径 → Wave 1 先把
characterization 零回归网织好（无 `_row_scope` 逐字节等价），再动合并逻辑。

**受益面**：全库 805 张附注表里 **29 张是多段共享表**（listed 23 / soe 6），
本 spec 只接 E1 外币章节作首个消费者与验收场景，其余 28 张由后续 per-cycle spec 逐个接入。

## Tasks

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "零回归网 + 段清单真源",
      "tasks": ["1", "2", "3"],
      "parallel": false,
      "rationale": "Task 1 的 characterization 是后续所有改动的安全网，必须先落；Task 2/3 的切段纯函数与生成器是 Task 4 的输入"
    },
    {
      "wave": 2,
      "name": "行级合并核心",
      "tasks": ["4", "5", "6"],
      "parallel": false,
      "rationale": "同改 wp_disclosure_sync_service 一个文件，串行；Task 6 的两入口一致性依赖 4/5 都落地"
    },
    {
      "wave": 3,
      "name": "_note_texts 按段合并",
      "tasks": ["7", "8"],
      "parallel": true,
      "rationale": "文本合并与行合并互不依赖（不同字段），守卫可并行写"
    },
    {
      "wave": 4,
      "name": "E1 首个消费者 + 守卫登记",
      "tasks": ["9", "10", "11"],
      "parallel": false,
      "rationale": "Task 9 的载荷是 Task 10 契约测试的输入；Task 11 的前端守卫要读 Task 9 的声明做反向自检"
    },
    {
      "wave": 5,
      "name": "实测与收口",
      "tasks": ["12", "13", "14"],
      "parallel": false,
      "rationale": "真实 DB → 浏览器 → 数据复原 + CI，顺序不可换"
    },
    {
      "wave": 6,
      "name": "接入前普查补强",
      "tasks": ["15"],
      "parallel": false,
      "rationale": "逐表核高优先级三张表结构时发现段窗口会吞掉表级合计行；验收表恰无合计行故 Wave 1~5 全绿也发现不了，必须在接入剩余 28 张表之前补掉"
    }
  ]
}
```

## Wave 1 — 零回归网 + 段清单真源

- [x] 1. Characterization 零回归网（**先于任何逻辑改动**）
  - 新建 `backend/tests/test_disclosure_sync_characterization.py`：取 5~8 个**真实载荷形态**
    （D1 应收票据 / D2 应收账款 / H2 在建工程 / K1 其他应收款 / N1 递延所得税，从各 spec 的
    既有测试 fixture 或 `build*SyncPayload` 单测里抄真实结构，**不自造**）
  - 对每个载荷跑 `sync_from_workpaper`（fake session），把结果 `table_data`
    用 `json.dumps(..., sort_keys=True, ensure_ascii=False)` 落成期望快照
  - 断言：无 `_row_scope` 的载荷合并结果**逐字节**等于快照（Property 1）
  - **反向自检**：故意把表级浅合并改成整体替换，本测试必须红（防快照恒真）
  - 顺带跑一遍既有 `test_wp_disclosure_sync*.py` 记录基线（当前全绿，后续任一变红都要解释）
  - _Requirements: 1.2, 6.1, 6.2_

- [x] 2. `note_shared_table_segments.py` 切段纯函数 + 变体解析
  - `Segment` dataclass（`row_code` / `label` / `start` / `end`）
  - `split_segments(rows)`：段 = 从带 `report_row_code` 的行起到下一个段首前，末段到表尾；
    首个段首之前的行不属任何段
  - `resolve_template_variant(current_standard, source_template)`：**禁止按章节号推导**
    （实测 20 个章节号两份模板都有、13 个标题不同 —— `八、1` listed 是政府补助 / soe 是货币资金；
    `五、42` listed 是其他应付款）。优先级 `current_standard` 前缀 > `source_template` > `None`
    （`None` → fail closed）
  - `template_rows(variant, section_number, table_name)`（`lru_cache`，查不到返 `None`）
  - `resolve_segment_window(...)` / `is_shared_table(...)` / `stamp_baseline_rows(rows)`
  - 守卫 `test_note_shared_table_segments.py`：真实模板行集（listed `五、73` 16 行 3 段 /
    soe `八、92` 25 行 5 段）区间逐个钉死 + **PBT**（随机插 `report_row_code` → 区间不重叠、
    并集连续、每段首带 code）+ Property 3b（撞号章节两变体各取对模板）
    + 两条反向自检（改成「按标签分组」则「标签重复不串段」必红；改成「按章节号谁有取谁」
    则 `八、1` 必取错模板）
  - _Requirements: 2.1, 2.5, 2.6, 2.7, 4.4_

- [x] 3. 共享表清单生成器 + drift 守卫
  - `backend/scripts/gen/gen_note_shared_table_segments.py`（`--write` / `--check`）→
    `backend/data/note_shared_table_segments.json`
  - 判据：同一表 `rows[]` 含 ≥2 个不同 `report_row_code`；**实测应得 29 张**（listed 23 / soe 6）
  - 清单含 `variant` / `section_number` / `section_title` / `table_name` / `row_count` / `segments[]`
  - 守卫：`--check` 0 欠账 + 表数 == 29 + **反向自检**（手改一处段区间必被抓出）
  - **注意**：清单只供**守卫与前端**消费；服务端运行期直接读模板（避免清单陈旧导致 fail closed 误判）
  - _Requirements: 8.1, 8.4_

## Wave 2 — 行级合并核心

- [x] 4. `_extract_row_scope` + `_merge_rows_by_scope`
  - `_extract_row_scope`：对称 `_extract_removed_table_keys`，剥离 `sub_table_data._row_scope`；
    非法形态（非 dict / 缺 `owner_row_code` / 表名以 `_` 开头）丢弃 + warning
  - `_merge_rows_by_scope`：`result = baseline[:start] + incoming + baseline[end:]`
    - 基线：`existing` 非空用它，为空用 `stamp_baseline_rows(template_rows(...))`
    - 段窗口：基线里有 `_seg == owner` 的**连续段**则用它；否则用模板下标并按基线长度裁剪
    - `incoming == []` → 段恢复模板骨架（**不删段**）
    - 写入行统一补 `_seg = owner_row_code`
    - 解析失败返回 `(原样 existing, error)` → 调用方**跳过该表**（fail closed）
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.2, 2.3, 3.1, 3.2, 3.4, 3.6, 4.1, 4.2, 4.3_

- [x] 5. 接入 `sync_from_workpaper` 写路径
  - 在既有表级浅合并循环里加分支：`key in row_scopes ? 行级合并 : merged_sub[key] = rows`
    （**不声明就一行不改**，保 Property 1）
  - 返回值加 `row_scoped_tables` / `row_scope_unresolved`（只加字段，向后兼容）
  - `logger.info` 记 `section/table/owner/window/baseline_source/rows_in/rows_out`
    —— 排查「他段被动了」的唯一线索
  - **JSONB 写入用 `CAST(:td AS jsonb)` + `json.dumps(ensure_ascii=False)`，禁 `sa.type_coerce`**
    （asyncpg 下 100% 失败，平台已实证）
  - 守卫 `test_disclosure_row_level_merge.py`：Property 2/3/5/6/9/10 用**真实模板行集**逐行断言
    + PBT（随机 owner 段 + 随机推送行数 → Property 3 恒等式 + 段外不变）
    + Property 5 反向自检（改成回退整表覆盖则 Property 2 必红）
    + Property 18（变体解析：撞号章节 `八、1` 两变体各取对模板）
  - _Requirements: 2.2, 3.1, 3.3, 6.4, 6.5_

- [x] 6. 接入 `sync_from_html_disclosure` + `_seg` 不泄漏（实际方法名 `sync_from_html`）
  - 第二个写入口同款加行级合并分支（现状是 `existing_table_data["sub_table_data"] = incoming_sub`）
  - 守卫 Property 13：同一载荷两入口产出的 `sub_table_data` / `_sub_table_columns` / `text_content` 相同
  - 守卫 Property 7：`project_sub_tables` 输出行**不含** `_seg`、`_sub_table_columns` 无 `_seg` 列、
    `note_word_exporter` 表头无 `_seg`；若实测漏出则在投影器显式过滤行内 `_` 前缀键
  - _Requirements: 3.5, 6.3_

## Wave 3 — `_note_texts` 按段合并

- [x] 7. `_merge_note_texts` + `_removed_text_sections`
  - 按 `section` 键浅合并：同 section 覆盖、未推送 section 保留、`_removed_text_sections`
    删除（**推送优先**，本次推了就不删）
  - 段序稳定：既有顺序在前、新 section 追加在后（`text_content` 重排不跳动）
  - **修掉「无 `_note_texts` 推送就置 `None`」**：改为保留既有 `text_content`（R5.2）
  - `text_content` 由合并后的 `_note_texts` 全量重排产出
  - _Requirements: 5.1, 5.2, 5.3, 5.5_

- [x] 8. `_note_texts` 合并守卫
  - Property 11：键集 == 既有 ∪ 推送 − removed；同名取推送；未推送不变；段序稳定
  - Property 12：无推送不清空 + **单 owner 场景合并 ≡ 整替换**（零回归论证）
  - 多 owner 真实场景：G2/G3/K1 共用 `五、8`/`八、9` 的真实 section 键（memory 已实证三方
    都开自动同步 → K1 录的 10 段说明会被 G2 的一段整体覆盖）
  - **诚实改既有测试**：若有断言锁定「无推送则 `text_content = None`」，改之并在测试里写明
    「原断言锁的是本 spec 要修掉的缺陷」，不得静默改
  - _Requirements: 5.4, 6.2_

## Wave 4 — E1 首个消费者 + 守卫登记

- [x] 9. `e1FxNoteSectionMap.ts` + 底稿接线
  - `E1_FX_NOTE_SECTION = { listed: '五、73', soe: '八、92' }` / `E1_FX_TABLE = '外币货币性项目'` /
    `E1_FX_OWNER_ROW_CODE = 'BS-002'`
  - `buildE1FxColumns()` **零入参**（覆盖率 sweep 用空参调用）：4 列 `flat`
    （`项目 / 期末外币余额 / 折算汇率 / 期末折算人民币余额`），**期初留底稿不扩列**
  - `buildE1FxSyncPayload(variant, wpId, applicableStandards, snapshot)` 声明
    `_row_scope: { 外币货币性项目: { owner_row_code: 'BS-002' } }`
  - 段内行 = 「货币资金」段首行 + 各币种「其中：」行，币种由 `e1CurrencyScope` 驱动（可增删）
  - `E1TabDisclosure.vue` 的自动同步**发第二个 payload**（同 K6 国企侧「一次发两个 payload」范式）
  - _Requirements: 7.1, 7.2, 7.3_

- [x] 10. E1 外币契约测试
  - 表名/章节号逐字命中模板；4 列必标 `flat` 且不声明 `group`；`owner_row_code` ∈ 该表段集合
  - `_row_scope` 形态正确；两变体列头 label 差异（若源模板有）；`sheet_name` 半角括号
  - `buildE1FxColumns` 登记 `disclosureColumnsCoverage.spec.ts` 的 `P1_ROUTE`
  - **改 E1 spec 的 Task 13 守卫**：原「全前端不得有 map 推向外币章节」→
    「只允许经 `_row_scope` 声明的 map 推向该章节」+ 保留「不得整表覆盖」正向断言
  - _Requirements: 7.1, 7.2, 7.5_

- [x] 11. 平台前端守卫：推共享表必带 `_row_scope`
  - 新建 `disclosureSharedTableRowScope.spec.ts`：扫全部 `build*SyncPayload`，
    推送表名 ∩ `note_shared_table_segments.json` → 必须带 `_row_scope`
    且 `owner_row_code` ∈ 该表段集合
  - **反向自检**：临时去掉 E1 的 `_row_scope` 声明，守卫必须红
  - 守卫读源码前 `stripComments()`（本 spec 的说明文字里写了被禁的反例）
  - 已知会命中但**暂不接线**的表登记 allowlist（每条写理由 + 归属 per-cycle spec），
    随各循环接入逐个移出
  - _Requirements: 8.2, 8.3, 8.5_

## Wave 5 — 实测与收口

- [x] 12. 真实 DB 直跑（绕过 HTTP）
  - 项目 `2aa00f57`（soe，`八、92` 有 25 行 5 段完整骨架）：
    推送前 SQL 快照全 25 行 → 跑 E1 外币推送 → 逐行比对
  - 验：货币资金段（`BS-002`，行 0~4）出现数据；**他四段（`BS-006`/`BS-031`/`BS-061`/`BS-062`，
    行 5~24）逐字未变**；每行带 `_seg`；`row_scoped_tables` 含该表、`row_scope_unresolved` 为空
  - 验 fail closed：构造不存在的 `owner_row_code` 推一次 → 该表**完全未写**、其余表照常
  - 验 `五、73`（listed 3 段 16 行）同款
  - _Requirements: 2.2, 3.4, 7.4_

- [x] 13. 浏览器实测 + 数据复原
  - chrome-devtools 驱动（`admin`/`admin123`）：E1 底稿录外币金额/汇率 →
    **不点按钮**自动同步 → postgres 只读查 `八、92`
  - 验：`last_sync_at` 前移、货币资金段有数据、他段骨架完好、
    `_column_groups == []`（4 列 flat）、`_last_sync_sheet` 半角括号、
    `_seg` 不出现在读时投影输出里
  - 验多 owner 文本：先用 E1 推一段说明，再模拟另一 owner 推另一 section →
    两段说明**都在** `text_content` 里（Property 11 活体）
  - **先快照后改，按 md5 逐字节复原**；不可复原的字段如实记录（E1 spec 已有先例）
  - 清理本会话 `tmp_*` 诊断产物
  - _Requirements: 7.4, 5.1_

- [x] 14. CI 登记 + 复盘
  - 新增 job `disclosure-row-level-merge`（后端合并语义 + 切段纯函数 + 生成器 drift +
    characterization 零回归）与 `disclosure-row-level-merge-frontend`（前端守卫 + E1 契约 +
    `disclosureColumnsCoverage` 回归）
  - `yaml.safe_load` 校验 + 确认引用的脚本/测试路径全部存在
  - 复盘写回 spec Notes：实测发现的缺陷、剩余 28 张共享表的接入清单与优先级
  - _Requirements: 8.4_

## Wave 6 — 接入前普查补强（逐表核结构时发现的平台缺口）

- [x] 15. 段窗口必须排除**表级合计行**（`Segment.data_end`）
  - 缺口：段 = 「从带 code 的行到下一个段首前」→ **末段会把表最后一行的合计吞进去**
    （实测 **14 个段**：`五、32`×2 / `五、71` / `八、91` / `八、81` / `三、` 章 9 个）
    → 末段 owner 一推数据就把整表合计删掉（附注缺合计 = 表没编完）
  - 区分**段级小计**与**表级合计**，判据**数据驱动不靠配置**：
    若**每个段**尾部都有汇总行 → 段级小计（如 `五、30`/`八、31` 递延所得税的
    「资产小计 / 负债小计」）→ 属段内不剔除；否则表最后一行的汇总行 → 表级合计，剔除
  - `Segment` 新增 `data_end`（默认 `= end` → 引入前后逐字等价；外币表五段皆如此）；
    `stamp_baseline_rows` 让合计行的 `_seg` **留空**（`find_stamped_window` 天然止于它前）；
    `_merge_rows_by_scope` 用 `data_end` 作替换右界（正常推送与空推送两条路径都改）
  - 生成器清单加 `data_end`；守卫：后端 6 条（含「段级小计不得剔除」正向 + 两条反向自检）
    + 5 张真实表参数化「合计行必须存活」+ 前端 2 条（`data_end` 齐备 + 14 个段基线）
  - _Requirements: 2.1, 2.5, 3.1, 3.2, 3.6_

## Notes

### Wave 6 落地实录（2026-08-02，接入剩余 28 张表前的必要补强）

**为什么必须先做**：本 spec 的验收表（外币货币性项目）**恰好没有合计行**，
所以 Wave 1~5 全绿也发现不了这个缺口。逐表核高优先级三张表的结构时才暴露 ——
`五、32`/`五、71`/`八、91`/`八、81` **每一张**的末段都挂着表尾合计。

**判据演进（两轮）**：首版「剔除段尾连续汇总行」一刀切 → 实测 20 个段受影响，
其中 `五、30`/`八、31` 递延所得税的**段级小计**被误剔除（那是各段自己的小计，
owner 应当能覆盖）。改为「每段都有尾部汇总行 ⇒ 段级小计模式 ⇒ 不剔除」后落到 **14 个段**，
逐条核实全是表最后一行的「合计 / 小计」。守卫断言被剔除行的 label 必含「计」字。

**`……` / `可无限量添加行` 不是无主行**：那是源模板留给该段 owner 的可扩行
（E1 实测推 5 个币种行替换 `[0,5)` 是正确行为）→ 必须留在可写区内，
守卫用 `八、92` 的 `BS-002` 段（`data_end == 5`，含 `……`）正向锁死。

### Wave 1~3 落地实录（2026-08-02）

**产出**：
- `backend/app/services/note_shared_table_segments.py`（切段纯函数 + 变体解析 + 模板缓存）
- `backend/scripts/gen/gen_note_shared_table_segments.py` + `backend/data/note_shared_table_segments.json`（29 张表，listed 23 / soe 6）
- `wp_disclosure_sync_service` 新增：`ROW_SCOPE_KEY` / `RowScope` / `_extract_row_scope` /
  `_merge_rows_by_scope` / `_apply_row_scoped_merge` / `REMOVED_TEXT_SECTIONS_KEY` /
  `_extract_removed_text_sections` / `_note_text_merge_keys` / `_merge_note_texts`
- 测试：`test_disclosure_sync_characterization.py`(16) / `test_note_shared_table_segments.py`(44) /
  `test_disclosure_row_level_merge.py`(37) / `test_disclosure_note_texts_merge.py`(22)

**落地时纠正 / 发现的事实**（design 已同步更新）：

| 事实 | 说明 |
|------|------|
| 第二写入口方法名是 `sync_from_html` | design/tasks 原写 `sync_from_html_disclosure` |
| `dropped_tables` 不在返回值里 | `_drop_removed_tables` 返回它但调用方只 `logger.info` |
| **基线不能取 `merged_sub`** | 表级浅合并已把 incoming 写进去了 → 必须显式传 `baselines=existing_sub`，否则「基线」就是 incoming 本身，段外行全丢 |
| `str(None) == "None"` | `_extract_removed_text_sections` 首版用 `str(item).strip()` → `None` 变成一个假 section 名（被测试抓出）。同款隐患在既有 `_extract_removed_table_keys` 里仍在（未动，属另一笔账） |
| 无键叙述段必须**位置化**占位键 | 存量有循环推 `[{"text": "…"}]`（无 section 无 title，F4 范式）。若按「保留 + 追加」处理，每同步一次多攒一条 → 附注正文无限膨胀 |
| `sync_from_html` 的**新建**分支不做行级合并 | 该分支拿不到变体（无 `_current_standard` / 无 `source_template`），且此时附注里没有任何他人数据 → 按现状整表写入 + warning；行级合并的真实消费者走 `sync_from_workpaper` |
| `sync_from_html` **不处理 `_note_texts`** | 该入口从不调 `_extract_note_texts` → `_note_texts` 留在 `sub_table_data` 里当元数据键（投影器与 `_count_rows_synced` 都跳 `_` 键，故无害）。属预存在分叉，本 spec 未动 → Property 13 的比对范围限定 `sub_table_data` |
| `sync_from_html` 表级是**整替换**不是浅合并 | 又一处预存在分叉（`existing_table_data["sub_table_data"] = incoming_sub`）。行级分支已接，表级语义未动 |

**诚实改动的既有断言（唯一一条）**：`test_no_note_texts_clears_text_content_CURRENT`
→ `test_no_note_texts_keeps_text_content`（Requirement 5.2）。原断言锁的是
「未推 `_note_texts` → `text_content = None`」，正是本 spec 要修掉的缺陷。
显式清空改由推 `_note_texts: []`（或全空文本）/ `_removed_text_sections` 达成，
另加 `test_explicit_empty_note_texts_clears_text_content` 钉死。

**回归基线**（2026-08-02 实测，`-k "disclosure or note_texts or shared_table_segments or projector"`）：
191 passed / 1 skipped（合并语义相关全绿）。另有 **58 例预存在失败**分布在 7 个文件，
逐条核对**无一触及**本次改动的符号（扫 `row_scope`/`_seg`/`note_texts`/`text_content`/
`sync_from_workpaper`/`sync_from_html` 全部 0 命中）：

| 文件 | 根因 |
|------|------|
| `tests/e2e/test_disclosure_table_e2e.py`(4) | 409 `STANDARD_MISMATCH` —— 用例往 soe 项目推 `listed_standalone`，属 `applicable-standards` 守卫上线后的失效用例 |
| `tests/services/test_disclosure_engine_v2.py`(7) | resolver 数 `9 != 8`；`'coroutine' object has no attribute 'wizard_state'` |
| `tests/test_disclosure_note_formula_wave3.py` | 附注公式灰度 fail-open（flag 默认关） |
| `tests/test_disclosure_note_hardening.py` / `test_disclosure_notes_hardening.py` | `app.routers.disclosure_notes` 无 `OwnershipGuard` / `_assert_project_edit` / `_mutation_id`（路由已重构） |
| `tests/test_e_cycle_linkage_verification.py` / `test_f_cycle_linkage_verification.py` | 断言 `E1-1` 应为 `d-form-table`，实为 `e1-monetary-fund`（E1 spec 已改 componentType） |

### Wave 4~5 落地实录（2026-08-02）

**产出**：
- `composables/e1FxNoteSectionMap.ts`（`E1_FX_NOTE_SECTION`/`E1_FX_TABLE`/`E1_FX_OWNER_ROW_CODE`
  + 零参 `buildE1FxColumns()` + `aggregateE1FxByCurrency()` + `buildE1FxSyncPayload()`）
- `E1TabDisclosure.vue` 发**第二个 payload**（`syncFxSectionToNote`，K6 国企侧范式）；
  自动同步 watch 加入 `foreignCurrencyRows`；消费 `row_scope_unresolved` 给用户提示
- 守卫：`e1FxNoteSectionMap.spec.ts`(23) + 平台级 `disclosureSharedTableRowScope.spec.ts`(11)
  + `test_note_e1_structure.py` 的 FX 段守卫由「禁止任何 map 推」改为「只许经 `_row_scope` 推」
- `backend/scripts/diagnose/verify_row_level_merge_live.py`（真实 DB 快照→推送→比对→md5 复原）
- CI 两 job：`disclosure-row-level-merge` / `disclosure-row-level-merge-frontend`（yaml 校验绿，80 jobs）

**🔴 顺带修掉一个被误判过的真缺陷（推翻本会话早先的判断）**：
`E1TabDisclosure` 把整个外币区 `v-if="variant === 'listed'"` → **国企 Tab 完全没有外币录入位置**。
早先把由此产生的假「不一致 4,467,536.12」归因为「源 xlsx 的外币表只在上市 sheet」，
openpyxl 逐格实证**推翻**该理由：两张披露 sheet 的 **R25~R62 逐字相同**
（表名/两级表头/四分组/五币种/合计公式全同），只有 R17 汇率中间价提示块是上市独有；
且国企 sheet 的勾稽单元格 **R12 列 E = `=B12-'附注披露信息(上市公司)'!D62`**
（主表合计 − 原币表人民币合计）反证国企版同样要求填这两张表。
→ 外币区改两变体都渲染、`fxRows` 两变体都传，`e1DisclosureConsistency.spec.ts`
里那条锁定「国企不得传 fxRows」的断言**诚实改写**并写明推翻依据。

**其他落地发现**：

| 事实 | 说明 |
|------|------|
| `ColumnDef.format` 缺 `'rate'` | 附注模板早已在用（外币表「折算汇率」列）→ 补进类型联合，否则推送侧与 seed 侧 format 分叉 |
| 浮点噪声必须在载荷侧收口 | 底稿 `endRmb = 原币 × 折算率`，实测 14000 × 7.1884 落库 `100637.59999999999` → 金额取 2 位（`money()`），汇率保留 4 位 |
| `e1FxNoteSectionMap.ts` 天然不进 registry | 生成器 `WP_CODE_RE = ^([a-z]+\d+)NoteSectionMap\.ts$`，大写 `F` 不匹配（同 M 循环共享 map 机制）。共享表一章多 owner，本就不该进 1:1 反查表 |
| 共享表清单里 **14 个可扫描表名**（17 去重 − 3 脏名） | 脏名 `''` / `项  目` / `续：` 拿去做源码扫描必大面积误报 → 显式登记豁免；另有 4 个 `项  目（…）` 派生名（其中一个含 `<br/>`）属另一个 data-hygiene 待办 |
| N1 递延所得税两表是**单一 owner 独占整张表** | 段是 `BS-036`(资产)+`BS-067`(负债)，两段都由 N1 的表(1) 录入推送 → 表级覆盖是正确语义，登记 `WHOLE_TABLE_OWNER` 豁免并校验段集合 |
| 复原脚本首版**漏了两列** | `sync_from_workpaper` 还写 `last_sync_user_id` / `updated_by`，首版只复位 7 列 → 在 `df5b8403` 的记录上留下一个 admin uuid（原值 NULL），靠与**未触碰的同章节兄弟记录**比对才发现。已补进脚本 + 加 3 条复原断言（26 项） |

**实测（真实 DB 直跑，两个 soe 项目各 23~26 项断言全绿）**：
- `c8621493` / `df5b8403` 的 `八、92`：`row_scoped_tables=['外币货币性项目']`、
  `row_scope_unresolved=[]`；落库 23 行、每行带 `_seg`、段集合 5 段齐全；
  货币资金段 3 行 = 推送行数、段内合计自洽；**他四段各 5 行骨架且无任何数值列**
- fail closed（`owner_row_code='BS-9999'`）：`row_scope_unresolved=['外币货币性项目']`、
  `row_scoped_tables=[]`、`sub_table_data` **逐字未变**
- **上市侧无活体**：唯一 `source_template=listed` 的 `五、73`（项目 `0ec33ac9`）
  其 `applicable_standard_v2.entity_type='soe'` → 推 `listed_standalone` 被
  `detect_standard_conflict` 拦下（`StandardMismatchError`，零写入），listed 路径由单测覆盖

**实测（浏览器，项目 `c8621493` / wp `72643cc3`，chrome-devtools + postgres 只读）**：
- 国企 Tab 现在渲染出「外币性质货币资金项目」（改造前完全没有）：4 张表、24 行外币明细
- 录 美元 14000 × 7.1884 → UI `100,637.60`；**不点按钮** 6s 内自动同步
- `八、92`：`last_sync_at` 由 NULL 前移、`_last_sync_sheet=附注披露信息(国企)`（半角）、
  `_current_standard=soe_standalone`、25 行 = 货币资金段 5 行 + 他四段 20 行骨架
- 再录 欧元 1400 × 7.8572 → 落库 `100637.6` / `11000.08` / 段首 `111637.68`（**无浮点噪声**）
- 读时投影：`_column_groups == []`（4 列 flat，无凭空父表头）、**`_seg` 泄漏 0 行**、
  headers 逐字对齐模板、他段 `values` 全 null
- **数据已逐字节复原**：`table_data` md5 回到 `b1999be560035bb5c6c3f30f5219c1a3`（原值），
  `text_content`/`last_sync_at`/`last_sync_user_id`/`updated_by` 全部回 NULL，
  `checklist_responses` 的 8 条 `E1-disclosure-*` 已删除（实测前为 0 条）

**剩余 28 张共享表的接入清单见本文档末尾「后续 per-cycle 接入清单」**（本 spec 不做）。

### 立 spec 时已实证的事实（不需重复验证）

| 事实 | 证据 |
|------|------|
| 合并粒度是**表级** | `wp_disclosure_sync_service` 注释原文「按子表 key 浅合并（同名 key 覆盖，未推送的 key 保留）」 |
| `text_content` 是**整替换**且无推送时置 `None` | 同文件 `note.text_content = formatted_texts` / `else: note.text_content = None` |
| 模板段首行**已带** `report_row_code` + `account_codes` | listed 2888 行中 95 行 / soe 1879 行中 26 行 |
| 全库 **29 张多段共享表**（listed 23 / soe 6） | 扫两份 note_template，判据 ≥2 个不同 `report_row_code` |
| `八、92 外币货币性项目` 25 行 5 段 | 段首 `BS-002 货币资金` / `BS-006 应收账款` / `BS-031 短期借款` / `BS-061 长期借款` / `BS-062 应付债券`，每段 = 段首 + 美元/欧元/港币 +「……」可扩行 |
| `五、73` 16 行 3 段 | `BS-002` / `BS-006` / `BS-061`，可扩行字面是「可无限量添加行」（非「……」） |
| 该表 4 列 | `项目 / 期末外币余额 / 折算汇率 / 期末折算人民币余额` |
| 外币章节**目前无任何 pusher** | registry 无该章节条目 / 无 `*NoteSectionMap.ts` 指向它 / 两处代码注释记录过历史误映射修正 |
| 已有一条 soe 记录表名是 `项  目`（表头首格泄漏） | `八、92` 的 `_tables[0].name` 实测；属另一个 data-hygiene 点，本 spec 不处理但守卫要容忍 |

### 关键踩坑预防（本 spec 直接适用）

- **改核心写路径必须先有 characterization 零回归网**（Task 1 先于 Task 4/5）
- **fail closed 不是可选项**：段边界解析不出时回退整表覆盖 = 静默清掉他循环数据
- **`_seg` 是行内键不是表键**：`_count_rows_synced` 跳的是 `_` 前缀**表**键，别混
- **JSONB 写入禁 `sa.type_coerce`**（asyncpg 下 100% 失败），用 `CAST(:td AS jsonb)` + `json.dumps`
- **`read_file` 对本会话改过/并发在改的文件返回陈旧版本** → 判落盘真相用
  `python -c "open(p,encoding='utf-8').read()"`
- **守卫读源码先 `stripComments()` 并加反向自检**（本 spec 说明文字里写了被禁的反例）
- **PowerShell `>` 重定向会把 UTF-8 中文腌成乱码** → 诊断脚本用 Python 自己写盘
- **服务端运行期读模板、不读生成的清单**：清单陈旧会导致 fail closed 误判把正常同步挡掉
- **诚实改测试**：若既有断言锁定「无 `_note_texts` 则 `text_content = None`」，
  改之并在测试里写明原因，不得静默改

### 与 E1 spec 的衔接

`e1-four-table-extraction-and-disclosure-alignment` 的 Task 13 按**选项 A** 收口
（只补 `五、73`/`八、92` 的列元数据 + guidance，`rows=None` 不动行集，不接推送），
其 guidance 已如实写明「尚未接自动推送」及原因。本 spec 的 Task 9/10 把它改成接线，
并把那条「全前端不得有 map 推向外币章节」守卫改成「只允许经 `_row_scope` 声明的 map 推」。

### 后续 per-cycle 接入清单（本 spec 不做，按收益排序）

章节号与表名逐字取自 Task 2/3 生成的清单（`--write` 后见
`backend/data/note_shared_table_segments.json`）：

| 优先级 | 章节 / 表 | 段数 | 归属循环 |
|--------|----------|------|---------|
| 高 | listed `五、32`（+「续：」表）/ soe `八、93` 所有权或使用权受到限制的资产 | 6 / 7 | E1 / D1 / D2 / F2 / H1 / H2 / H3 |
| 高 | listed `五、71` / soe `八、91` 资产负债表中的列报项目和相关信息 | 3 | K / L |
| 高 | soe `八、81` 筹资活动产生的各项负债的变动情况 | 4 | K / L |
| 中 | listed `五、30` / soe `八、31` 递延所得税（2 表） | 2 | N1 / N3 |
| 中 | listed `十四、分部报告` 本期/上期 两表 | 2 | D4 / F5 |
| 中 | listed `三、风险管理目标和政` 4 张表 | 2~8 | G / K / L |
| 低 | listed `三、非同一控制下企业` / `三、同一控制下企业合` | 8~9 | G7 合并范围 |
| 低 | listed `三、金融资产转移` 4 张表 | 2~4 | G / D2 |
| 低 | listed `三、资本管理` / `三、现金流量表项目注` / `三、在合营安排或联营`(2) / `三、重要会计政策、会` | 2~4 | K / L / G7 |

**接入前必看的两处脏数据**（Task 2 守卫已钉死，接入时要绕开）：
- listed 风险管理有一张表段序 `BS-041 / BS-002 / BS-041`（同 code 两段）→ 只能取首段
- listed 风险管理有一张表 `name=""`（空表名）→ 不可作 `sub_table_data` 键
- `三、` 章 `section_number` 是 **10 字符截断值**（`三、重要会计政策、会`）→ 逐字取真源
