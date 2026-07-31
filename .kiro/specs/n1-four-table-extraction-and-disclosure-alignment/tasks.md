# Implementation Plan: N1 四表取数与披露/附注结构对齐

## Overview

五个 wave：①后端接 `report_config` 科目映射并补 `2901` 负债侧取数；②幂等脚本把附注
`五、30` / `八、31` 的行集回归源模板（含删占位假行、修 `report_row_code`、剥离底层科目）；
③前端披露表接四表直通 + 亏损到期 6 行 + 净额表行镜像 + 二选一分支；④清理误挂 N1 的
公式预设并补齐缺口；⑤守卫收口 + 活体实测。

**状态：五个 wave 全部完成 + 活体实测通过，待 commit。**

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

- [x] 1. 后端四表取数与科目映射
- [x] 1.1 接入 `report_config` 科目映射
  - `_n1_deferred_tax_assets.py` 新增 `_ASSET_ROW_CODE='BS-036'` / `_LIABILITY_ROW_CODE='BS-067'`（DB 实证值）
  - 新增 `_resolve_account_codes(ctx, row_code, fallback)`，走 `resolve_report_line_account_codes`，异常/空一律回退（fail-open）
  - 把 `_fetch_tb_data` 泛化为 `_fetch_tb_for_codes(ctx, codes)`，资产/负债共用；新增 `_code_predicate` / `_leaf_rows`
  - render 输出 `tb_source_codes`（`{asset,liability} → {row_code, codes}`，不设无法诚实计算的 `resolved`）
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 1.2 递延所得税负债（2901）取数
  - 新增 `_classify_n1_liability_subaccount`（5 语义槽；「投资性房地产」判定前置于泛化「公允价值」）
  - 新增 `_build_liability_prefill` + 共用 `_fetch_sub_account_rows` / `_aggregate_by_slot`
  - `abs()` 归一（活体实证 2901 期末同时存在 `-233512.19` 与 `200530.32` 两种符号约定）
  - 全零槽跳过 / 只有父级返回 `{}` / 异常 fail-open
  - render 输出 `trial_balance_liability` + `liability_prefill`
  - **附带修正**：`_build_adjudication_prefill` 原只 `like '1811.%'` → 平铺层级科目表（`181102`）静默返回空；改为 `{code}%` 排除父级 + 叶子判定
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 1.3 后端守卫
  - 新增 `backend/tests/test_n1_account_mapping.py`（26 例，含反向自检与 render 输出契约）
  - _Requirements: 7.1, 7.3_

- [x] 1.4 前端消费新键（消除 dead output）
  - `useN1FormData` 新增 `tbLiabilitySeed` / `liabilityPrefill` / `tbSourceCodes` + `_normTb` / `_normPrefill`
  - 两个披露 Tab 顶部「四表取数来源」展示 `tb_source_codes`
  - **附带修正**：原 `_applyTbSeedFromRenderConfig` 把 `adjudication_prefill` 抽取写在 `if (tb)` 块内，`trial_balance` 缺失时兄弟键一并丢弃
  - _Requirements: 1.5_

- [x] 2. 附注模板行集对齐
- [x] 2.1 幂等脚本行常量回归源模板
  - `fix_note_deferred_tax_structure.py`：新增 `SRC_ASSET_ITEMS`(7) / `SRC_LIABILITY_ITEMS`(分变体 5) / `_two_segment_rows` / `_loss_expiry_rows`
  - 删自造行「开办费」+ 负债段 4 处不符行；国企表 0/表 1 同步（16 行）
  - 亏损到期两版统一 6 年 + 合计；互抵明细改空行骨架
  - _Requirements: 5.1, 5.2, 5.4, 5.5_

- [x] 2.2 占位行 / 报表行编码 / 科目白名单 / 截断文本
  - 删 5 处 `……` 假数据行，语义移入 `guidance`（含「纯动态行区域」「10 年结转按需增行」）
  - `report_row_code`：`BS-018`/`BS-042`/`BS-019` → `BS-036` / `BS-067`
  - 剥离 `2601` / `1641` / `1642` / `1643`
  - 删 listed `text_sections` 中截断的证监会指引段（带 `**` markdown 残迹）
  - _Requirements: 5.3, 5.6, 5.7, 5.8_

- [x] 2.3 `--check` 通过 + 幂等
  - `--dry-run` 增强：`_describe` 报行数、`_print_row_diff` 逐表打印行集增删、文本节增删
  - `--check` exit 0
  - _Requirements: 5.9_

- [x] 2.4 后端结构守卫扩展
  - 新增 `backend/tests/services/test_note_deferred_tax_row_alignment.py`（21 例）
  - `openpyxl` 直读源 xlsx 交叉比对行集 + 3 条反向自检（读取有效性 / 国企资产段公式引用 / 净额表镜像公式）
  - _Requirements: 7.1, 7.3_

- [x] 3. 前端披露表四表直通与结构对齐
- [x] 3.1 四表直通预填
  - `useN1DisclosureTables`：`N1_LIABILITY_SLOT_DEFS` 单一真源（`N1_LIABILITY_ITEMS` 由它派生）+ `N1_LIABILITY_SLOTS` / `N1_LIABILITY_SLOT_LABEL` / `n1LiabilitySlotOf`
  - `applyTbAssetPrefill()` / `applyTbLiabilityPrefill()`：手工优先、N1-2 优先、不写 0、暂时性差异留 `null`
  - 两个 Tab 透传 `adjudicationPrefill` / `liabilityPrefill`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3.2 亏损到期骨架 5 → 6 行
  - `defaultLossExpiryRows(auditYear)` = `auditYear .. auditYear+5`；常量改名 `LOSS_EXPIRY_ROW_COUNT` 并写明 6 行的推导
  - _Requirements: 4.1_

- [x] 3.3 国企净额表行镜像
  - `mirrorNetOffsetRows(src, prev)` 纯函数（保值 + 幂等）+ 监听**行标签序列**的 watch（不监听整行对象，否则金额一变就重建）
  - _Requirements: 4.2_

- [x] 3.4 披露分支二选一
  - `N1OffsetMode = 'undecided' | 'gross' | 'net'`（**三态**）+ 上市 `netOffsetApplicable: boolean | null`
  - `n1BranchTableKeys` / `resolveN1BranchTables`；`buildN1SyncPayload` 按分支跳过 + `_removed_table_keys`（只删上次推过的表）
  - `columns` 键集随推送键集收窄
  - 两 Tab 分支 UI（radio + 卡头「本口径不披露」tag）+ 持久化
  - _Requirements: 4.3, 4.4, 4.5_

- [x] 3.5 前端守卫
  - 新增 `n1DisclosurePrefillAndBranch.spec.ts`（28 例，含 4 条 PBT）
  - _Requirements: 7.2_

- [x] 4. 公式预设清理与补齐
- [x] 4.1 删除误挂 N1 的「税金分析程序」块
  - 移除 `wp_code=N1 / sheet=分析程序N1-3` 块（`2221`/`6401`/`6403` + `TB_SUM('2221~6403')`）
  - 顺带消除 `上年审定数` 在 `workpaper:N1` 内的撞键（`--check` 报 `Skipped (duplicate page_key+target_cell): 64` 证实平台会静默吞掉重复键）
  - _Requirements: 6.1, 6.2_

- [x] 4.2 N1-2 补期初余额预设
  - `1811.01`~`1811.07` 各补 `=TB('1811.0X','期初余额')`（7 条）
  - _Requirements: 6.3_

- [x] 4.3 N1-4 / N1-5 补预设 + 纯净性守卫
  - N1-4：`递延所得税资产/负债 期末/期初账面余额`（源模板第 I / M 列，与第 G / K 列「应确认」比较得差异列）
  - N1-5：`期末/期初未分配利润_账面金额`（源模板 R14；`4104` 报表行 `BS-088` DB 实证）
  - 新增 `backend/tests/formula_management/test_n1_preset_purity.py`（14 例）
  - _Requirements: 6.4, 6.5, 6.6, 7.4_

- [x] 5. 守卫收口与活体实测
- [x] 5.1 全量测试
  - 后端 N1 + 附注 + 预设 **202 例全绿**
  - 前端 `src/components/workpaper` 全量 19456 例 / 84 失败 / 14 文件 —— **N1 相关零失败**，失败全在未触碰区域
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 5.2 CI job 挂载
  - `note-deferred-tax-structure` 增挂行集守卫步骤（并补 `openpyxl` 依赖）
  - 新增 job `n1-four-table-extraction`（后端映射/叶子/负债预填/预设纯净）
  - 新增 job `n1-disclosure-frontend`（披露预填/骨架/镜像/分支）
  - _Requirements: 7.1_

- [x] 5.3 活体实测
  - _Requirements: 7.5_

## 实测记录（2026-07-31）

**① 后端全链（真实 DB 直跑 render，项目 `2aa00f57` / wp `c48c1ad8`）**

| 项 | 实测值 | 核对 |
|---|---|---|
| 科目映射 | `BS-036 → ['1811']` / `BS-067 → ['2901']` | ✅ |
| TB 资产 期初/期末 | 816,858.43 | = `tb_balance` 1811 ✅ |
| TB 负债 期初/期末 | 233,512.19 | `abs()` 归一（源 −233,512.19）✅ |
| 资产段预填 | 资产减值准备 −300,308.01；其他 1,117,166.44 | = 240,751.64 + 876,414.80 ✅ |
| 负债段预填 | `lease` 233,512.19 | ✅ |
| **勾稽** | 叶子分类合计 816,858.43 == TB 期末；负债 233,512.19 == TB 期末 | **逐分相等** ✅ |
| render 键 | 新增 3 键齐备 + 11 个既有键全在 | 零回归 ✅ |

**② 运行态 render-config**（浏览器内 fetch，`--reload` 已生效）：`trial_balance_liability` /
`liability_prefill` / `tb_source_codes` 三键均下发，值与直跑一致。

**③ 四表直通预填 UI**（项目 `0ec33ac9` / wp `a64c9e3e`，无持久化披露行的干净底稿）

- 资产段自动带出：资产减值准备 3,983,376.55 / 可抵扣亏损 1,172,298.25 / 其他 2,893,025.00
  → **小计 8,048,699.80 = `tb_balance` 1811 期末，逐分相等**
- 取数溯源渲染：「递延所得税资产 1811（报表行 BS-036）；递延所得税负债 2901（报表行 BS-067）」
- 负债段全空（该项目 2901 无非零叶子 → `liability_prefill={}`）—— 宁缺勿造
- 行名逐字对齐源模板（资产段 7 项 / 负债段 5 项含国企专用「租赁形成」）

**④ 二选一分支与孤儿清理**（项目 `2aa00f57` / wp `c48c1ad8`，八、31 基线 5 张子表）

| 操作 | 子表 | `last_sync_at` |
|---|---|---|
| 基线（未判断） | 5 | 07-30 09:24:27 |
| 切「不以抵销后净额列示（按（1））」 | **3**（`以抵销后净额列示…` + `互抵明细` 被删） | → 07-31 12:04:24 |
| 切「以抵销后净额列示（按（2））」 | **4**（`未经抵销…` 被删，另两张回归） | → 07-31 12:05:26 |
| 复原「未判断」 | **5**（回到基线） | → 07-31 12:06:04 |

**不点同步按钮**，全部由自动同步触发。表(2)A 首行 60,000.00 在三次切换后仍保留
→ `mirrorNetOffsetRows` 保值（Property 7）活体验证。

**⑤ 列元数据与行集落库**

- `_sub_table_columns.未经抵销…` = 5 列，国企子列序「递延所得税资产/负债」在前 +
  groups `期末余额` / `年初余额` ✅
- `sub_table_data.未经抵销…` **16 行**：资产段标题 + 7 项 + 小计 + 负债段标题 + 5 项 + 小计
  → 与 Wave 2 修正后的模板 seed **同构**（同步与未同步项目结构一致）

**⑥ 上市 Tab**（同一 wp 的 `附注披露信息（上市公司）` sheet）

- 挂载正确；表(2) 适用性三态（未判断 / 适用 / 不适用）
- 两级表头 `期末余额` / `上年年末余额` + 子列序 **`可抵扣/应纳税暂时性差异` 在前**
  → 与国企**相反**，对齐源模板 listed B11:E11 ✅
- 未推送（该项目 `entity_type=soe`，推 listed 会被服务端 `detect_standard_conflict` 拦成 409）

## Notes

- **共享真源并发风险**：`note_template_{listed,soe}.json` 与 `prefill_formula_mapping.json`
  被多个在飞 spec 同时改动 → 一律经幂等脚本 / `str_replace` 增量修改，禁整文件覆盖；
  测试红了先重跑 `fix_note_deferred_tax_structure.py`。
- **既有键零回归**：render 只新增键，`trial_balance` / `adjudication_prefill` /
  `adjudicated_amount` / `formula_direction` 等既有键与语义不动（已由 render 契约测试钉死）。

### 本轮发现但不在范围内（已实证，需另立 spec）

- **`formula_presets/inventory.json` 预存在漂移**：物化 232 页 vs 运行时 255 页
  （差 23 页来自并发会话）。本 spec 的改动**新增 0 页**（`workpaper:N1` 页已存在），
  故未重生成 —— 重生成会把别人 23 页未验证成品一并提交。
- **N3 / N5 预设科目错**：N3 块用 `6801`（所得税费用）与 `1812`（不存在的科目码）
  而非 `2901`；N5-8 块亦引 `1812`。
- **`page_key = workpaper:{wp_code}` 忽略 sheet**：`上年审定数` 在 **25+ 个循环**内撞键
  （D1~D7 / E1 / F2 / G1 / G4 / G6~G8 / G13 / H1 / H3 / I1 / J1 / J2 / K8 / L1 / L3 / M1 / N3 / N4），
  平台级。本 spec 只消除了 N1 内的那一处。
- **`note_template` 全库 `report_row_code` 陈旧**：平台级 data-hygiene 待办。
- **可编辑金额输入把 `null` 渲染成 `0.00`**：共享 `WpDisclosureSegmentTable` 的既有行为
  （无预填的行同样显示 `0.00`）→ 审计师无法区分「未填」与「零」。小计行显示 `—` 说明
  底层值确为 `null`。属平台级 UI 口径，波及 N1/N2/N4/N5，未动。
- **项目 `2aa00f57` 的 `trial_balance` 双算**：1,633,716.86 = 2 × `tb_balance` 816,858.43
  （两份数据集），数据卫生问题非代码。
- **项目 `2aa00f57` 的 `五、30`（上市章节号）残留 4 张子表且 `source_template='soe'`**：
  既有 `applicable_standards` 变体错配遗留，本 spec 未触碰。
- **wp `c48c1ad8` 有 2026-07-30 遗留的披露测试数据未复原**（`unoffset` 352000 等）；
  本轮实测在其上只改动 `offset-mode` 并已复原为「未判断」（`'undecided'` 与「无该键」
  行为等价，postgres MCP 只读故未删该行）。

### 实测手法

Playwright token 在 sessionStorage 不跨 page → 用 chrome-devtools MCP 复用已登录 tab，
把「等待挂载 + 点击 + 等防抖 + 读 DOM」压进**单个原子脚本**（分步调用会被并发会话导航走，
本轮实测已复现一次）。另注意子串匹配陷阱：`'不以抵销后净额列示'` **包含**
`'以抵销后净额列示'` → 选择器须用 `startsWith`。
