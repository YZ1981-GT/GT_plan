# Implementation Plan: F1 取数链路与披露表源模板保真

## Overview

5 波共 18 项。Wave 1 先把源模板事实写成守卫（后续所有改动的裁决基准），
Wave 2/3 可并行（后端取数链路 vs 前端披露②表），Wave 4 依赖 Wave 2 的科目口径，
Wave 5 收口验证与活体实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "源模板事实固化（守卫先行）",
      "tasks": ["1.1", "1.2"],
      "parallel": true
    },
    {
      "wave": 2,
      "name": "后端取数链路补齐",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "parallel": false,
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "国企披露②表源模板保真",
      "tasks": ["3.1", "3.2", "3.3", "3.4"],
      "parallel": false,
      "depends_on": [1]
    },
    {
      "wave": 4,
      "name": "公式预设",
      "tasks": ["4.1", "4.2"],
      "parallel": false,
      "depends_on": [2]
    },
    {
      "wave": 5,
      "name": "验证与实测",
      "tasks": ["5.1", "5.2", "5.3"],
      "parallel": false,
      "depends_on": [2, 3, 4]
    }
  ]
}
```

## Tasks

## Wave 1 — 源模板事实固化

- [x] 1.1 后端守卫 `backend/tests/test_f1_source_template_facts.py`
  - openpyxl 直读 `backend/wp_templates/F/F1 预付账款.xlsx`
  - 断言 `长期挂款检查表F1-5` R5 表头字面：A=债务人名称 / B=期末余额 / C=账龄 /
    E=未偿还或未结转的原因 / I=计提坏账准备金额 / J=审定余额
  - 断言 `附注披露信息(国企)` A18 是 `RIGHT($A$3` 形态；B18/C18/D18/E18 分别引用
    F1-5 的 `!A6` / `!J6` / `!C6` / `!E6`
  - 断言 `附注披露信息(上市公司)` B10:E13 引用 `审定表F1-1`、A28:B32 引用 `实质性分析F1-4`
  - 反向自检：把断言用的列字母换一个（如 J→I）必须失败
  - _Requirements: 6.1_

- [x] 1.2 前端守卫补强 `f1NoteSubtableContract.spec.ts`
  - 沿用共享 helper 跑 P1~P6；不新造机制
  - 追加：`F1_SOE_COLUMNS[OVER1]` 的 5 个 key 与附注模板 §八、7 表2 `columns` 逐字段相等
  - _Requirements: 6.3_

## Wave 2 — 后端取数链路补齐

- [x] 2.1 `_f1_prepayment.py` 新增纯函数 `resolve_impairment_prefill`
  - tb_balance 路径优先；其空且 trial_balance 期末非零 → `{"end": x}`（无 prior）
  - 两条都空 → `None`
  - _Requirements: 3.2, 3.3_

- [x] 2.2 `_f1_prepayment.py` 新增 `_fetch_provision_from_trial_balance`
  - 复用 `build_trial_balance_code_filter`；审定优先回退未审；取绝对值；fail-open
  - _Requirements: 3.1, 3.5_

- [x] 2.3 `render` 接线 + 溯源输出
  - `tb_source_codes` 增 `provision_trial` / `provision_trial_amount`
  - `impairment_prefill` 改由 `resolve_impairment_prefill` 产出
  - _Requirements: 3.1, 3.4_

- [x] 2.4 `_f1_import_export.py` 关联方自动识别
  - 新增纯函数 `match_related_party`（双向包含 + 去空白）
  - `build_f1_detail_rows_from_aux` 增 `related_parties` 入参（缺省 None = 行为不变）
  - `aggregate_f1_detail_rows_from_aux` 增查 `related_party_registry` 并透传（fail-open）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 2.5 后端单测
  - `test_f1_four_table_extraction.py` 扩展：`resolve_impairment_prefill` 三态 + PBT
  - 新增 `test_f1_related_party_match.py`：双向包含 / 空名单恒等 / merge 语义不变
  - _Requirements: 6.2_

## Wave 3 — 国企披露②表源模板保真

- [x] 3.1 `useF1DisclosureSoe.ts` 抽纯函数 `buildSoeOver1Rows`
  - 入参 `{longTermSheetRows, crossSheetRows, dynamicRows, metaMap, defaultCreditorUnit}`
  - F1-5 非空则用 F1-5（期末余额取 `auditedBalance`、账龄取 `aging`、原因取 `reason`）
  - F1-5 空则回退 `crossSheetRows`
  - `metaMap` 覆盖优先；`creditorUnit` 空则取 `defaultCreditorUnit`
  - 行带 `source: 'f1-5' | 'f1-2' | 'manual'`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2_

- [x] 3.2 `useF1DisclosureSoe.ts` 接线
  - 读 `F1-lt-rows`；新增 `clientName` 入参
  - `getSyncSnapshot` 用最终值（不推 `source`）
  - _Requirements: 1.5, 2.3_

- [x] 3.3 `GtF1Prepayment.vue` 透传 `client-name`
  - 取 `project_context.client_name`（兼容 camelCase 回退）
  - _Requirements: 2.4_

- [x] 3.4 `F1TabDisclosureSoe.vue` UI
  - ②表加只读「来源」tag 列；债权单位 placeholder = 被审计单位名
  - `.src-hint` 补源模板口径说明
  - _Requirements: 1.5_

- [x] 3.5 前端单测
  - `useF1DisclosureSoe.spec.ts` 扩展 + 新增 PBT（Property 1~4）
  - _Requirements: 6.2_

## Wave 4 — 公式预设

- [x] 4.1 `prefill_formula_mapping.json` 新增 3 个 F1 块
  - sheet 名逐字取源 xlsx tab 名；`cell_ref` 带 sheet 语义前缀保证页内唯一
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 4.2 守卫 `backend/tests/test_f1_formula_presets.py`
  - `convert_prefill_presets()` 中 `workpaper:F1` 的 `target_cell` 集合大小 == 条目数
  - 三个新 sheet 各至少一条；`validate_formula` 返回空错误列表
  - 披露块不得被别的块 `WP()` 引用（防循环）
  - _Requirements: 4.4, 4.5, 6.2_

## Wave 5 — 验证与实测

- [x] 5.1 全量测试
  - 后端 F1 相关 + `four_table` 全绿；前端 F1 相关全绿
  - 改动文件 Vite transform 200
  - _Requirements: 6.2_

- [x] 5.2 真实数据 render 直跑
  - postgres 只读复核：`1231-04` 在 `trial_balance` 命中、`impairment_prefill` 口径
  - _Requirements: 3.1, 3.4_

- [ ] 5.3 浏览器实测 + 数据复原
  - F1-5 录 2 行 → 国企②表带出（含审定余额/账龄/原因/债权单位）→ 推送 →
    postgres 复核 §八、7 落库 → 复原
  - _Requirements: 6.4_

## Notes

### 本 spec 明确不做（写下来防复盘重复提议）

- **附注①按账龄表不改 5 列 7 行**：国企源 xlsx 是 7 列三级表头（坏账准备作列），
  但 `note_check_preset_formulas.json` 的 `F7-6/F7-7/F7-8`（soe 与 listed 同形）明确要求
  「小计行 / 减值准备行 / 合计行」+「比例 = 行金额 ÷ 小计行金额」→ 附注是交付物，
  列结构随校验预设；底稿 Tab 已忠实渲染 7 列三级表头，同步时投影为附注形状。
- **附注 seed 骨架的 4 个账龄档不改**：`note_template` 是 variant 级共享骨架，
  推送时整表覆盖；`guidance` 已注明随项目账龄枚举（3 年段 / 5 年段 / 自定义）自适配。
- **上市②表保持手工**：源 xlsx R17~R19 无公式（空白可增删行），与国企②表（F1-5 驱动）不同。
- **soe ③表保持由 F1-2 派生前五名**：源 xlsx R24~R28 的 A/B 列无公式（手工），
  现实现自动派生属增强，不回退。
- **F1-5 不做自动 seed**：F1-2 自动归集后金额整笔落首个账龄段（辅助余额表无账龄维度），
  「超 1 年」筛选结果为空 → 自动 seed 是空操作；长期挂款的选取本身是审计判断，保留手动按钮。

### 实测结论

**真实 DB 直跑 render**（绕 HTTP，避开未重载的 uvicorn worker；三个真实项目 / 2025）：

| 项目 | `provision_standard` | `provision`（反解） | `provision_exact` | `provision_trial_amount` | `impairment_prefill` | `client_name` |
|---|---|---|---|---|---|---|
| `0ec33ac9` 重药控股安徽 | `['1231-04']` | `['1231']` | False | **0.0** | `None` | 重药控股安徽有限公司 |
| `2aa00f57` 和平药房 | `['1231-04']` | `['1231']` | False | **0.0** | `None` | 重庆和平药房连锁有限责任公司 |
| `c8621493` 新健康大药房临港店 | `['1231-04']` | `['1231']` | False | **0.0** | `None` | 重庆医药集团宜宾医药有限公司新健康大药房临港店 |

三条直接结论：

1. **第二取数路径确有必要且已生效** —— `provision_standard` 能解析到细分标准码 `1231-04`，
   而 `account_mapping` 反解只到宽前缀 `1231`（`provision_exact=False`）。新路径按标准码查
   `trial_balance` 拿到 0.0（该表确有 `1231-04 坏账准备-预付账款` 行，金额为 0）。
2. **宁缺勿造成立** —— 0.0 不算命中 → `impairment_prefill` 仍为 `None`，披露侧保持手工录入，
   与改造前行为一致（零回归）。若客户日后真计提了预付坏账，两条路径任一命中即可自动预填。
3. **债权单位缺省值可用** —— 三个项目 `client_name` 全部非空。

**取数链路自检不变量全部成立**（`nature_prefill` 各性质桶 `closing` 之和 == `prepaid_tb_leaf_amount`）：
`0ec33ac9` 13,576,792.21 / `2aa00f57` 1,301,918.43 / `c8621493` 127,955.76。

项目 `2aa00f57` 的 `prepaid_tb_amount`（trial_balance）= 2,603,836.86 = 叶子合计的 **2 倍**
—— 这是已知的 recalc 把 `dataset_id IS NULL` 历史行一并计入所致，两个口径由
`F1FourTableSourcePanel` 并列展示差异，非本 spec 引入。

**测试**：后端新增 66 例全绿（源模板事实 33 + 取数链路 18 + 公式预设 15）；
后端 `-k "f1 or F1 or four_table"` 584 passed / 7 failed，**7 条全为预存在基线**
（`test_f_cycle_audit_determination_writeback.py` 的 5 条断言 F1-1 用
`d-form-table` + `audited_amount` 字段名，而 F1 早已有专属组件 `f1-prepayment` +
`ending_audited`；另 2 条为 `test_import_engine` / `test_render_config_smoke`）。
前端 19 文件 277 例 276 绿，**唯一失败 `disclosureAutoSyncCoverage.spec.ts` 的
`D2TabDisclosure.vue`** 是 HEAD 上的预存在红（并发会话 D2 spec 用显式 props 委托，
守卫的 `resolveDelegate` 只认 `v-bind="$props"`）。

### 遗留

- Task 5.3 浏览器活测（F1-5 录 2 行 → ②表带出 → 推送 → §八、7 落库 → 复原）未做：
  共享 Chrome 被并发会话反复抢占，且用户要求本轮继续推进 F2。代码路径已由真实 DB 直跑 +
  纯函数守卫覆盖。
- commit。
