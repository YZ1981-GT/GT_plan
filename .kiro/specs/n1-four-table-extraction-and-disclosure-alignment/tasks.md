# Implementation Plan: N1 四表取数与披露/附注结构对齐

## Overview

五个 wave：①后端接 `report_config` 科目映射并补 `2901` 负债侧取数；②幂等脚本把附注
`五、30` / `八、31` 的行集回归源模板（含删占位假行、修 `report_row_code`、剥离底层科目）；
③前端披露表接四表直通 + 亏损到期 6 行 + 净额表行镜像 + 二选一分支；④清理误挂 N1 的
公式预设并补齐缺口；⑤守卫收口 + 活体实测。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "后端四表取数与科目映射",
      "tasks": ["1.1", "1.2", "1.3", "1.4"],
      "parallel": false
    },
    {
      "wave": 2,
      "name": "附注模板行集对齐（幂等脚本 + 后端守卫）",
      "tasks": ["2.1", "2.2", "2.3", "2.4"],
      "parallel": false
    },
    {
      "wave": 3,
      "name": "前端披露表四表直通与结构对齐",
      "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5"],
      "parallel": false
    },
    {
      "wave": 4,
      "name": "公式预设清理与补齐",
      "tasks": ["4.1", "4.2", "4.3"],
      "parallel": false
    },
    {
      "wave": 5,
      "name": "守卫收口与活体实测",
      "tasks": ["5.1", "5.2", "5.3"],
      "parallel": false
    }
  ]
}
```

Wave 1 → Wave 3 有硬依赖（前端消费后端新键）。Wave 2 与 Wave 1 无依赖但与 Wave 3 的
同步载荷断言相关，故排在 Wave 3 前。Wave 4 独立。Wave 5 收口。

## Tasks

- [ ] 1. 后端四表取数与科目映射
- [ ] 1.1 接入 `report_config` 科目映射
  - `_n1_deferred_tax_assets.py` 新增 `_ASSET_ROW_CODE='BS-036'` / `_LIABILITY_ROW_CODE='BS-067'`（DB 实证值）
  - 新增 `_resolve_account_codes(ctx, row_code, fallback)`，走 `resolve_report_line_account_codes`，异常/空一律回退（fail-open）
  - 把 `_fetch_tb_data` 泛化为 `_fetch_tb_for_codes(ctx, codes)`，资产/负债共用
  - render 输出 `tb_source_codes`
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 1.2 递延所得税负债（2901）取数
  - 新增 `_classify_n1_liability_subaccount`（纯函数，5 语义槽；「投资性房地产」判定必须先于泛化「公允价值」）
  - 新增 `_build_liability_prefill`（叶子聚合、`abs()` 归一、全零槽跳过、只有父级返回 `{}`、异常 fail-open）
  - render 输出 `trial_balance_liability` + `liability_prefill`
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [ ] 1.3 后端守卫
  - 新增 `backend/tests/test_n1_account_mapping.py`（Property 1/2/3，含反向自检）
  - 新增 `backend/tests/test_n1_liability_prefill.py`（Requirement 2 全条）
  - _Requirements: 7.1, 7.3_

- [ ] 1.4 前端消费新键（消除 dead output）
  - `useN1FormData.selfLoad` 抽 `liabilityPrefill` / `tbLiability` / `tbSourceCodes`
  - `tb_source_codes` 至少一个 UI 消费点（取数溯源）
  - _Requirements: 1.5_

- [ ] 2. 附注模板行集对齐
- [ ] 2.1 幂等脚本行常量回归源模板
  - `fix_note_deferred_tax_structure.py`：资产段 7 项 / 负债段 5 项（分变体第 4 项）
  - 删自造行「开办费」及负债段 4 处不符行；国企表 0/表 1 同步
  - 亏损到期两版统一为 6 年 + 合计；互抵明细改空骨架
  - _Requirements: 5.1, 5.2, 5.4, 5.5_

- [ ] 2.2 占位行 / 报表行编码 / 科目白名单 / 截断文本
  - 删 5 处 `……` 假数据行，语义移入 `guidance`
  - `report_row_code`：`BS-018` → `BS-036` / `BS-067`
  - 剥离 `2601` / `1641` / `1642` / `1643`（底层资产负债科目不属递延税行）
  - 删 listed `text_sections` 中截断的证监会指引段
  - _Requirements: 5.3, 5.6, 5.7, 5.8_

- [ ] 2.3 `--check` 通过 + 幂等
  - `--dry-run` / `--check` 双模式；连续两次 `apply()` 字节一致
  - _Requirements: 5.9_

- [ ] 2.4 后端结构守卫扩展
  - `test_note_deferred_tax_structure.py` 增 `openpyxl` 直读源模板交叉比对（Property 9/10/11）+ 反向自检
  - _Requirements: 7.1, 7.3_

- [ ] 3. 前端披露表四表直通与结构对齐
- [ ] 3.1 四表直通预填
  - `useN1DisclosureTables` 新增 options `adjudicationPrefill` / `liabilityPrefill`
  - `applyTbAssetPrefill()` / `applyTbLiabilityPrefill()`：手工优先、N1-2 优先、不写 0、暂时性差异留 null
  - 新增 `N1_LIABILITY_SLOTS` + `N1_LIABILITY_SLOT_LABEL` 单一真源
  - 两个 Tab 组件 + 宿主透传
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [ ] 3.2 亏损到期骨架 5 → 6 行
  - `defaultLossExpiryRows(auditYear)` 返回 `auditYear .. auditYear+5`
  - _Requirements: 4.1_

- [ ] 3.3 国企净额表行镜像
  - `mirrorNetOffsetRows(src, prev)` 纯函数 + watch 表 1 行变化驱动
  - _Requirements: 4.2_

- [ ] 3.4 披露分支二选一
  - 国企 `offsetMode: 'gross' | 'net'`（源模板 R7）；上市表 (2) 适用性开关（R33）
  - 持久化 + 未选分支进 `_removed_table_keys`
  - _Requirements: 4.3, 4.4, 4.5_

- [ ] 3.5 前端守卫
  - 新增 `n1DisclosurePrefill.spec.ts` / `n1LossExpirySkeleton.spec.ts` / `n1NetOffsetMirror.spec.ts`
  - 扩展 `n1NoteSectionMap.spec.ts`（Property 8）与 `n1NoteSubtableContract.spec.ts`
  - _Requirements: 7.2_

- [ ] 4. 公式预设清理与补齐
- [ ] 4.1 删除误挂 N1 的「税金分析程序」块
  - `prefill_formula_mapping.json` 移除 `wp_code=N1 / sheet=分析程序N1-3` 块（科目 `2221`/`6401`/`6403`，含病态 `TB_SUM('2221~6403')`；N1 源模板无该 sheet，N4 已有自己的块）
  - _Requirements: 6.1, 6.2_

- [ ] 4.2 N1-2 补期初余额预设
  - `1811.01`~`1811.07` 各补 `=TB('1811.0X','期初余额')`
  - _Requirements: 6.3_

- [ ] 4.3 N1-4 / N1-5 / 披露表补预设
  - 只补可由源模板确定口径的 cell；跨底稿引用遵守「审定表可用 `WP()`、明细表禁 `WP()`」
  - 新增 `test_n1_preset_purity.py`（Property 12）
  - _Requirements: 6.4, 6.5, 6.6, 7.4_

- [ ] 5. 守卫收口与活体实测
- [ ] 5.1 全量测试
  - 后端 N1 相关 + 附注结构 + 预设；前端 N1 相关全量
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 5.2 CI job 挂载
  - `governance-checks.yml` 增/改 job 覆盖新守卫与 `--check`
  - _Requirements: 7.1_

- [ ] 5.3 活体实测
  - chrome-devtools + postgres 只读：四表已入库 → 披露表有数 → 推送 → 附注落库；切分支验孤儿清理
  - 验证后复原测试数据
  - _Requirements: 7.5_

## Notes

- **共享真源并发风险**：`note_template_{listed,soe}.json` 与 `prefill_formula_mapping.json`
  被多个在飞 spec 同时改动 → 一律经幂等脚本 / `str_replace` 增量修改，禁整文件覆盖；
  测试红了先重跑 `fix_note_deferred_tax_structure.py`。
- **既有键零回归**：render 只新增键，`trial_balance` / `adjudication_prefill` /
  `adjudicated_amount` / `formula_direction` 等既有键与语义不动。
- **不在范围内**（已实证但另立）：
  - N3 的 `prefill_formula_mapping` 块用 `6801`（所得税费用）与 `1812`（不存在的科目码）
    而非 `2901`；N5-8 块亦引 `1812`。
  - `page_key = workpaper:{wp_code}` 忽略 sheet → `上年审定数` 在 25+ 循环内撞键（平台级）。
  - `note_template` 全库 `report_row_code` 陈旧（平台级 data-hygiene 待办）。
  - 项目 `2aa00f57` 的 `trial_balance` 因两份数据集而双算（数据卫生，非代码）。
- **实测手法**：Playwright token 在 sessionStorage 不跨 page → 复用已登录 tab，
  或用 chrome-devtools MCP + postgres 只读比对落库结果。
