# Implementation Plan: F1 预付款项披露表 ↔ 附注模板对齐

## Overview

三层同时对齐：底稿两版披露表（上市/国企）→ 同步载荷 `columns` → 附注模板 §五、7 / §八、7。

先做源模板核查（三源互证并裁决冲突），再以幂等脚本修订附注模板，然后改同步载荷契约，最后改两版底稿 UI。
附注模板修订与同步载荷改造互相独立，但必须一起验证（契约测试同时读两侧）。

## Task Dependency Graph

```
1 (源模板核查/裁决)
   ├──> 2 (附注模板幂等修订) ──┐
   ├──> 3 (同步载荷契约) ──────┼──> 6 (测试与回归)
   ├──> 4 (底稿上市) ──────────┤
   └──> 5 (底稿国企) ──────────┘
```

- `1` 阻塞全部（列结构裁决结果是其余任务的输入）
- `3` 依赖 `2`（子表名/列键需与模板逐字一致）
- `4`/`5` 依赖 `3`（snapshot 字段随载荷形状调整）
- `6` 依赖 `2`~`5`（契约测试同时读附注模板与同步载荷）

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "desc": "源模板核查与三源冲突裁决" },
    { "wave": 1, "tasks": ["2"], "desc": "附注模板幂等修订（两版 §五、7 / §八、7）", "depends_on": [0] },
    { "wave": 2, "tasks": ["3"], "desc": "同步载荷列契约 + 行投影", "depends_on": [1] },
    { "wave": 3, "tasks": ["4", "5"], "desc": "底稿上市 / 国企披露表（互不相干）", "depends_on": [2] },
    { "wave": 4, "tasks": ["6"], "desc": "测试与回归", "depends_on": [3] }
  ]
}
```

## Tasks

- [x] 1. 源模板核查与三源冲突裁决
  - [x] 1.1 openpyxl 读 `F1 预付账款.xlsx` 的 `附注披露信息(上市公司)` / `附注披露信息(国企)` / `审定表F1-1` / `实质性分析F1-4` / `长期挂款检查表F1-5`
  - [x] 1.2 读 `附注模版/{上市,国企}报表附注.md` §预付款项，比对 xlsx
  - [x] 1.3 读 `note_check_preset_formulas.json` F7-1~F7-14（listed/soe 双份）裁决冲突
  - [x] 1.4 `consol_note_sections_{listed,soe}.json` 第 4 方印证（结论一致）

- [x] 2. 附注模板修订（R1）
  - [x] 2.1 新增幂等脚本 `backend/scripts/fix/fix_note_prepayment_structure.py`（`--dry-run` / `--check` / `_aligned_by`）
  - [x] 2.2 listed §五、7：T1 两级表头 5 列 + 删 `header_label`
  - [x] 2.3 listed §五、7：T3 改名「按预付对象归集的预付款项期末余额前五名单位情况」
  - [x] 2.4 soe §八、7：T1 两级表头 5 列 + 删 `header_label`
  - [x] 2.5 soe §八、7：T3 消重名 → 「按欠款方归集的期末余额前五名的预付款项」
  - [x] 2.6 6 张表补 `columns`（键与同步载荷逐字一致）
  - [x] 2.7 6 张表补 `guidance`（仅源模板括注 / 附注模版说明 / 「勾稽：」前缀）
  - [x] 2.8 T2/T3 补空白明细行骨架（listed 3/5 行，soe 5/5 行）
  - [x] 2.9 执行脚本写入两个 JSON，`--check` 与二次 `--dry-run`（幂等）均通过

- [x] 3. 同步载荷契约（R4）
  - [x] 3.1 `F1_LISTED_COLUMNS` T1 改 `group` 两级；T2 列改 `impairment`「减值准备」+ `balance`「账面余额」
  - [x] 3.2 `F1_LISTED_SUBTABLE` 常量化 + T3 键改名 + `_removed_table_keys: ['单位名称']`
  - [x] 3.3 `F1_SOE_COLUMNS` T1 由 7 列收敛为 5 列 + `group`
  - [x] 3.4 `F1_SOE_COLUMNS` T3 列头「坏账准备」→「减值准备」
  - [x] 3.5 单级表头表标 `flat: true`（抑制后端前缀反猜父表头）
  - [x] 3.6 `buildF1ListedSubTableData` 三行尾（小计 / 减：减值准备 / 合计）双期给值
  - [x] 3.7 `buildF1SoeSubTableData` 账龄表补三行尾，逐段减值准备聚合入「减：减值准备」

- [x] 4. 底稿上市披露表（R2）
  - [x] 4.1 `useF1DisclosureListed`：新增 `impairmentPrior` / `agingImpairmentRow` / `agingNet` 双期；`agingTotal.label` → 小计
  - [x] 4.2 `F1TabDisclosureListed.vue`：三行并入账龄表，删表外 `impairment-row` 控件
  - [x] 4.3 (2) 表列结构改为 `债务人名称/账面余额/占比（%）/减值准备`（跨 sheet 行也可补录减值准备）
  - [x] 4.4 (2) 表 `type="expand"` 展开区录「未及时结算的原因」+「据此生成说明」按钮
  - [x] 4.5 内嵌源模板方法论上下文块（琥珀色）+ 编制提示/使用手册同步修订

- [x] 5. 底稿国企披露表（R3）
  - [x] 5.1 `useF1DisclosureSoe`：新增 `agingImpairmentRow` / `agingNet` 派生行；`agingTotal.label` → 小计
  - [x] 5.2 `F1TabDisclosureSoe.vue`：账龄表补小计/减：减值准备/合计行；列头「坏账准备」→「减值准备」
  - [x] 5.3 (2) 卡片标题「重要」→「大额」+ 索引 chip 改指 F1-5
  - [x] 5.4 (3) 前五名列头「坏账准备」→「减值准备」+ 占比列头补全角括号
  - [x] 5.5 内嵌源模板方法论上下文块 + 编制提示/使用手册同步修订

- [x] 6. 测试与回归（R6）
  - [x] 6.1 后端 `backend/tests/services/test_note_prepayment_structure.py`（26 项，含与 F7-7 交叉印证 + 复用脚本校验器）
  - [x] 6.2 前端 `f1NoteSubtableContract.spec.ts`（表名逐字/唯一、headers 无空串、`columns[0].label===headers[0]`、两级表头、全表 guidance、键序对应）
  - [x] 6.3 修正 `useF1DisclosureListed.spec.ts` / `useF1DisclosureSoe.spec.ts` 陈旧 `sheet_name` 断言
  - [x] 6.4 更新 `f1DisclosureColumns.spec.ts` 为新列契约（含 `_removed_table_keys` / 聚合投影）
  - [x] 6.5 账龄枚举测试（3年段/5年段/自定义 → 附注行数与标签）
  - [x] 6.6 全量 F1 vitest 122/122 绿；`test_note_prepayment_structure` 28/28 + `test_note_prepayment_backfill` 16/16 绿；`tests/services -k "note or disclosure"` 1682 passed（9 项失败为预存在，均与预付款项无关）
  - [x] 6.7 Playwright 端到端实测（详见 Notes §实测记录）

- [x] 7. 存量附注快照回填
  - [x] 7.1 实测发现存量项目 `_tables` 仍带修订前缺陷（国企 3 张表中第 2/3 张重名；更早版本用 `headers[0]` 当表名）
  - [x] 7.2 新增 `backend/scripts/fix/backfill_note_prepayment_snapshots.py`（默认 dry-run / `--apply` / `--check`）
  - [x] 7.3 安全门：`_tables`、顶层 rows、`sub_table_data` 任一格有值即跳过，改由底稿「同步到附注」整表覆盖
  - [x] 7.4 dry-run → apply → `--check` 全绿（4 条空骨架回填，1 条有数据安全跳过）
  - [x] 7.5 纯函数契约测试 `backend/tests/services/test_note_prepayment_backfill.py`（16 项）

## Notes

### 实测记录（2026-07-29，Playwright + PG 实证）

**底稿国企披露表**（项目 `c8621493…` / F1 `33b23de7…` / sheet `附注披露信息(国企)`）：

| 检查项 | 实测结果 |
|--------|---------|
| (1) 三级表头 | `账龄` \| `期末数`{`账面余额`{金额, 比例（%）}, `减值准备`} \| `期初数`{同上} ✓ |
| (1) 行集合 | `1年以内（含1年）/1至2年/2至3年/3至4年/4至5年/5年以上/小计/减：减值准备/合计` —— 该项目账龄配置为 **5 年段**，6 档全量呈现（不再折入「3年以上」）✓ |
| (2) 标题与列 | 「账龄超过1年的**大额**预付款项」+ 五列齐备 ✓ |
| (3) 标题与列 | 「按欠款方归集的期末余额前五名的预付款项情况」+ 第 4 列「减值准备」✓ |
| 方法论上下文块 | 3 张表各 1 块（琥珀色）✓ |

**附注模块 §八、7**（同项目 `/disclosure-notes`）：

- TAB：`预付款项按账龄列示` / `账龄超过1年的大额预付款项` / `按欠款方归集的期末余额前五名…` —— **重名已消除** ✓
- 两级表头：`["账龄","期末数","期初数"]` + `["金额","比例（%）","金额","比例（%）"]` ✓
- 行：7 行（4 档 + 小计 + 减：减值准备 + 合计），无 `header_label` 假行 ✓
- TAB 页签编制提示（guidance）已显示 ✓

**底稿上市披露表未能实测**：8 个在册项目的 `projects.applicable_standard_v2.entity_type` 全为 `soe`，
上市变体一律走「当前项目不适用上市公司附注披露格式」分支（**行为正确**）；唯一 listed 适用的项目
`12c15a96…` 已 `is_deleted = true`。如需活体验证，需把某项目主体类型改为上市（会影响其他会话正在使用的项目数据，未擅自改动）。
上市侧结构由 `f1NoteSubtableContract.spec.ts` + `test_note_prepayment_structure.py` + 生成期透传测试锁定。

### 交付说明（必须告知用户）

- `disclosure_notes.table_data._tables` 是**生成时快照** → 附注模板改名/加列只对**新建项目或重新生成附注**生效；「🔄 恢复模板结构」只重置当前单表。**存量项目已由任务 7 的回填脚本处理**（空骨架 4 条已回填；有数据的 1 条需在底稿披露表点「同步到附注」覆盖）。
- 改 `note_template_*.json` 不触发后端 `--reload`（模块级 `load()` 只加载一次）→ 验证前需重启后端。
- 上市项目 `0ec33ac9…` §五、7 已有录入数据（8 行金额），回填脚本按安全门跳过 → 请在 F1「附注披露信息(上市公司)」页签点「同步到附注」刷新为新列结构。

### 已知偏离

- 国企底稿 (1) 保留源 xlsx 的逐账龄段「减值准备」列（列头由「坏账准备」改为「减值准备」以对齐附注模版），附注侧按 5 列 + 「减：减值准备」一行呈现，由同步层聚合。信息不丢，两侧各守其源。
- `consol_note_sections_listed.json` 中预付款项第 3 张表 `title` 仍为「分别披露格式：」（合并报表附注模块自有表示法，另一套机制），本 spec 未动。

### 预存在缺陷（已移交，非本 spec 范围）

- `sheet_name` 断言漂移（F3/G1/G2/G3 合成标识 8 条 + G10/G11 短名 4 条，共 10 条失败）：与本 spec 修掉的 F1 §S7 同类缺陷，
  **已按用户 2026-07-29 决策并入 `disclosure-columns-coverage-rollout` 的 Requirement 8 / Task 16**（含待修清单、合法用法白名单、Property 11 守卫设计）。
