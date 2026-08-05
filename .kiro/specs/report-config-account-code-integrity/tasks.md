# Implementation Plan: report_config 科目码完整性修正与守卫

## Overview

13 行错码修正（幂等迁移 V138）+ 平台级一致性守卫（CI 连库 job）。
BS-014 单独隔出等用户裁决，不阻塞其余 12 行。

先建守卫再改数据 —— 守卫必须**先在现状下打红 13 行**，那是它有效的唯一证明；
改完再转绿。反过来（先改后写守卫）无法区分「守卫有效」与「守卫空转」。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "真源与守卫（先红）",
      "tasks": ["1", "2", "3"],
      "blocks": [2, 3, 4]
    },
    {
      "wave": 2,
      "name": "修正迁移 V138（12 行，BS-014 除外）",
      "tasks": ["4", "5", "6"],
      "depends_on": [1]
    },
    {
      "wave": 3,
      "name": "下游影响面与真实 DB 回归",
      "tasks": ["7", "8", "9"],
      "depends_on": [2]
    },
    {
      "wave": 4,
      "name": "BS-014 裁决落地 + CI + 收口",
      "tasks": ["10", "11", "12"],
      "depends_on": [3]
    }
  ]
}
```

---

## Tasks

### Wave 1 — 真源与守卫（必须先在现状下打红）

- [x] 1. 新建 `backend/app/services/four_table/report_config_account_names.py`
  - `ROW_NAME_ACCOUNT_ALIASES`（报表用语 ↔ 科目用语的合法差异，5 对已实证）
  - `ZERO_HIT_WHITELIST`（5 行业务事实，每条 value 写明实证查询与日期）
  - `DERIVED_ROWS_WITHOUT_ACCOUNT`（6 行派生项）
  - `normalize_name()` 纯函数（去 `△` / `加：` / `减：` / 中文序号 / 空格）
  - 🔴 别名表**只收「同一科目的两种叫法」**，不得用它掩盖真错码
    （守卫要有一条断言：别名两侧归一后不得指向 `account_chart` 里的**不同**科目）
  - _Requirements: 3.2, 3.3, 4.1, 6.4, 6.7_

- [x] 2. 新建守卫 `backend/tests/four_table/test_report_config_account_integrity.py`
  - `load_refs(db)` 抽全部 `TB*('code')`（排除 `project:%` 与 `is_deleted`）
  - `load_chart(db)` 返回 `{(code, source): {names}}` —— **分 source，禁合并**
  - 五组断言：`TestNoMismatchedCodes` / `TestZeroHitCodesWhitelisted` /
    `TestDerivedRowsHaveNoAccount` / `TestNoCrossRowDoubleClaim` / `TestReverseSelfcheck`
  - 反向自检三条：注入 `BS-090=TB('4201')` 必红 / 清空别名表后 `BS-088` 必由绿转红 /
    合并 source 后 `BS-087 4101` 必由绿转红
  - 无 DB 时 `pytest.skip(reason=...)`，**reason 非空**
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7_
  - _Properties: 6, 7, 8, 9, 10, 12_

- [x] 3. 验证守卫在现状下**打红 13 行**并记录清单
  - 期望红：BS-082 / BS-084 / BS-085 / BS-086 / EQ-015 / BS-090 / BS-033 /
    BS-043 / BS-053 / IMP-008 / IMP-017 / BS-013 / CFSS-016（+ BS-014 待裁决）
  - 期望绿：BS-081 / BS-083 / BS-087 / BS-088 及其余 ~88 行
  - 🔴 若红的行数 ≠ 13，先查判据不是查数据（可能别名表吸收过头或漏抽引用）
  - 把实际红清单写进本文件 Notes 作为修正前基线
  - _Requirements: 6.2_
  - ✅ **实测达成：4 组断言打红，去重后恰为预期的 13 个 row_code**（见 Notes「修正前基线」）。
    「若红的行数 ≠ 13 先查判据」这条指引直接生效 —— 第一版判据红了约 40 行，
    逐类查完全是判据缺陷，**一行数据都没改**。

### Wave 2 — 修正迁移

- [x] 4. 新建 `backend/migrations/V138__fix_report_config_equity_and_asset_codes.sql`
  - 文件头注释：全表对账基线（132 引用 / 102 行 / 13 错）+ **V136 失效原因**
    （WHERE 从不命中、前提错、真正写 `4103` 的是 BS-086）+ V137 已覆盖范围
  - 权益段 5 条：`BS-082 4003→4401` / `BS-084 4005→4201` / `BS-085 4102→4003` /
    `BS-086 4103→4301` / `EQ-015 4201→4301`（**EQ-015 两处 `TB('4201',…)` 都要换**）
  - 资产负债段 2 条：`BS-033 1703→1704` / `IMP-008 1502→1505`
  - 置 NULL 5 条：`BS-090` / `BS-043` / `BS-053` / `BS-013` / `CFSS-016` / `IMP-017`
  - 每条 WHERE 带 `row_code` + 已实证错值 + `applicable_standard NOT LIKE 'project:%'`
    + `is_deleted = false`
  - 每条上方注释写「现码实际是什么科目 + 实证项目数」
  - _Requirements: 1.1~1.6, 2.1, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1~4.3, 7.1~7.4_
  - _Properties: 1, 3, 4, 5, 13_
  - ✅ **13 条 UPDATE 写完，每条 WHERE 的命中数已只读预演**：
    BS-082/084/085/086/033/043/053/013 各 **4** 行（四个准则变体）· BS-090 **2** 行
    （仅两个 consolidated 变体有 formula；`soe_standalone` 的 row_name 是
    「△分出再保险合同负债」且 formula 本就 NULL，被 WHERE 的 formula 条件天然跳过）·
    EQ-015 / IMP-008 / IMP-017 / CFSS-016 各 **1** 行（仅 `soe_standalone` 有 formula）。
    **合计 38 行，无一条 > 4** —— 符合 design 的 Error Handling「>4 即中止人工复核」。
  - 改码统一 `REPLACE(formula, '''错码''', '''正码''')`：只替换被单引号包裹的码字面量，
    对 `TB('x','y')` 与 `TB('x', 'y')` 两种空格形态都成立（实证 BS-* 无空格、EQ/IMP/CFSS 有空格）；
    `EQ-015` 的 `TB('4201','期末余额') - TB('4201','期初余额')` 正需要「替换全部出现」。
  - 文件尾部显式列出**有意不含**的 4 类行（BS-014 / BS-052 / BS-066 / `project:` 覆盖行）
    及各自原因，防下个会话在同一文件里补。

- [ ] 5. 应用迁移并验证（需重启后端 —— `MigrationRunner` 只在启动时跑）
  - `migration_status` 确认 V138 已应用
  - 逐行 SQL 复核 13 行的新 formula
  - 复跑 Task 3 的守卫 → 应全绿
  - 二次应用（重启一次）确认 0 行影响（Property 1）
  - _Requirements: 1.1~1.7_
  - _Properties: 1, 2_

- [x] 6. 输出 `project:` 级覆盖行待确认清单
  - 查 `applicable_standard LIKE 'project:%'` 且 formula 引用被修正码的行
  - 逐条列出项目、行号、现 formula → 写进 Notes 等用户逐项目确认
  - 🔴 **不自动改** —— 客户自定义公式，改了可能破坏其已出的报表
  - _Requirements: 1.8_
  - _Properties: 3_
  - ✅ **清单为空**：本库 `report_config` 里 `applicable_standard LIKE 'project:%'` 的行
    **一条都没有**（`count = 0`，其中带 formula 的也是 0）→ 无待人工确认项，
    Property 3「project 级覆盖行零改动」自动成立。
  - 🔴 但迁移与守卫里的 `NOT LIKE 'project:%'` 排除子句**必须保留** ——
    这是环境相关的事实（本库恰好没有客户自定义覆盖），不是「该机制不存在」；
    一旦有项目启用覆盖，缺了排除子句就会改到客户公式。

### Wave 3 — 下游影响面与真实 DB 回归

- [ ] 7. 逐行列出下游引用方（已初查，需补全）
  - 已知：BS-014 → 22 文件（K2 + H8 + `wp_surfaced_k.py`）/ BS-053 → 6（K3）/
    BS-033·BS-037 → 5（I 循环）/ BS-082·BS-084·BS-085·BS-086 → M 循环 + L3/L4 scope /
    BS-068 → K5 **与 L 循环双方**（须查是否已双算）/ BS-013·BS-043 → 仅 `useReportColumns.ts`
  - 对每个受影响循环，确认其 spec 兜底码与新解析结果一致（Property 11）
  - _Requirements: 8.1, 8.3, 8.5_
  - _Properties: 11_

- [ ] 8. 真实 DB 直跑受影响循环，比对修正前/后金额
  - 至少覆盖两套编码体系各一个项目（旧制 `0ec33ac9` / CAS 2006 `2aa00f57`）
  - 重点：M3/M7/M9/M10（权益段）· K3（BS-053 解除双算）· I2（BS-033 开发支出）
  - 每个差异写「预期变化」或「意外变化」，意外的必须查清再继续
  - 🔴 用真实 DB 不用替身 —— 替身与错误假设同构（本 spec 的 F2/N5 教训同源）
  - _Requirements: 8.2, 8.4, 8.6_
  - _Properties: 14_

- [ ] 9. 后端回归 `rtk python -m pytest backend/tests/four_table/ --tb=short -q`
  - 新增/变更失败数必须为 0；预存在失败逐条确认与本 spec 无关
  - 另跑 `backend/tests/ -k "report_config or report_account or four_table"`
  - _Requirements: 8.6_

### Wave 4 — BS-014 裁决 + CI + 收口

- [ ] 10. BS-014 其他流动资产口径裁决（**需用户拍板后才动**）
  - 呈报三项实证：`1901` = 待处理财产损溢/损益（client 5 / standard 8 项目）·
    `tb_balance` 该科目余额**全库恒 0** · `listed_standalone` 额外加的 `TB('1131')`
    应收股利已由 `BS-009` 认领（潜在双算）
  - 三选项：(a) 置 NULL 让 K2 走 `k2_account_scope` 兜底 + 溯源面板显示「本项目无此科目」
    (b) 保留 `1901` 并在别名表登记（承认该科目就是其他流动资产的载体）
    (c) 改指别的码（需先找到能覆盖该语义的标准科目 —— 目前未找到）
  - 倾向 (a)：`1901` 名实不符且余额恒 0，保留只会让溯源面板显示错误来源
  - 裁决后补 V139 迁移 + K2 回归（22 文件引用）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 11. CI 接入 `governance-checks.yml`
  - 新增 job `report-config-account-integrity`，挂在**有 DB** 的 job 上
  - 跑 `test_report_config_account_integrity.py`
  - 反向自检也要在 CI 跑（防守卫被改成空转后无人察觉）
  - _Requirements: 6.3, 6.6_

- [ ] 12. 收口
  - `memory.md` 更新：`report_config` 错码由「6 处」更正为「V137 已修 5 + 本 spec 13 + BS-014 待裁决」
  - 把「两套编码体系（旧《企业会计制度》3xxx/4xxx成本/5xxx ↔ CAS 2006 4xxx/6xxx）」
    与「`3101`/`3201` 一码两义且 CAS 侧带真金额」写进 memory（现只记了「一码两义」现象，未记体系名）
  - `.kiro/specs/INDEX.md` 更新
  - _Requirements: 6.3_

---

## Notes

### 修正前基线（2026-08-04 Wave 1 实测，V138 应用前）

守卫 `test_report_config_account_integrity.py` 共 **29 例，4 组打红 / 25 通过**。
去重后被点名的 row_code **恰为 13 个**，与立项清单逐一吻合：

| 组 | 断言 | 打红内容 |
|---|---|---|
| A | `TestNoMismatchedCodes` | 11 行：BS-013 · BS-033 · BS-043 · BS-053 · BS-082 · BS-084 · BS-085 · BS-086 · BS-090 · IMP-008 · IMP-017 |
| C | `TestDerivedRowsHaveNoAccount` | 6 行 × 各准则变体 = 16 条：BS-013(4) · BS-043(4) · BS-053(4) · BS-090(2) · CFSS-016(1) · IMP-017(1) |
| D | `TestNoCrossRowDoubleClaim` | 1 组：`BS/2901[期末余额] = [BS-053, BS-067]` |
| E | `TestCodeCorrectionsApplied` | 7 行仍在用错码：BS-082 · BS-084 · BS-085 · BS-086 · EQ-015 · BS-033 · IMP-008 |

**A ∪ C ∪ E = 13 个 row_code** ✔（E 组覆盖了 A 组抓不到的 `EQ-015`，C 组覆盖了 `CFSS-016`）
抽取规模：396 条 TB 引用 / 449 个带 formula 的 (row_code, applicable_standard)。

期望绿且确实绿：`BS-081 4001` / `BS-083 4002` / `BS-087 4101` / `BS-088 4104`
（`TestKnownCorrectRowsStayCorrect`）。

### 🔴 第一版判据红了约 40 行 —— 四类结构性误报，全是判据缺陷不是数据问题

这一轮是 Task 3「若红的行数 ≠ 13，先查判据不是查数据」的直接兑现。四类误报及修法：

| 误报类 | 样本 | 根因 | 修法 |
|---|---|---|---|
| **多码合成行** | `BS-002 货币资金 = 1001+1002+1012`（无一叫「货币资金」）· `BS-028 固定资产 = 1601−1602` · `BS-005/006/009/010/027/031/032/050/063` 减备抵 | 行名是**合成/净额**语义，与任何单一科目名都不同 | `is_name_comparable` 要求**去重后单码**；多码行只过「码必须存在」与派生行两道检查 |
| **流量/变动额表** | `CFSS-005 固定资产折旧 ← 1602 累计折旧` · `CFSS-014 递延所得税资产减少 ← 1811` · `CFSS-013 投资损失 ← 6111 投资收益` · `EQ-001 一、上期期末余额 ← 五个权益科目` | 行名是**变动额/合计**语义，余额科目名天然不同 | 名称比对限定 `BALANCE_SHEET_TABLES = {BS, IMP}`；`CFSS`/`IS`/`EQ` 排除 |
| **「其中：」明细行** | `IMP-002 其中：应收账款坏账准备 ← 1231.02`（父科目名是「坏账准备」） | 行名 = 限定语 + 父科目名 | `names_match(detail_row=True)` 放宽为「父科目名 ⊂ 行名」，**仅对明细行** |
| **双算判据太粗** | `BS/1231 = [BS-005,BS-006,BS-009]`（实为 1231-01/1231/1231-03 三个不同备抵明细）· `IMP/1231 = [IMP-001, IMP-002]`（父行+明细行）· `CFSS/1001 = [CFSS-026, CFSS-027]`（期末 vs 期初两时点） | 按 `head` 归并 + 忽略取数列 | 改按 **(报表, 完整码, 取数列)** 归并 + 排除「其中：」行 → 只剩 `BS-053 vs BS-067` 一组真双算 |

### 🔴 顺带修掉一个抽取缺陷：函数名是 `SUM_TB` 不是 `TB_SUM`

全表实证 `regexp_matches(formula,'([A-Za-z_]\w*)\s*\(','g')` 去重只有 **`TB` / `SUM_TB` / `ROW`**。
第一版正则写 `\bTB(?:_SUM)?` 漏掉 `SUM_TB`（`_` 是词字符，`\bTB` 在 `SUM_TB` 中间不成立）
→ `BS-010 存货 = SUM_TB('1401~1499') − TB('1416')` 被误抽成**单码行**，
于是拿「存货」去比对备抵科目「存货跌价准备」而误报。
已加 `TestSumTbIsExtracted`（含「`TB_SUM` 形态不应被抽到」的反向断言 +
「全表 formula 只允许 TB/SUM_TB/ROW，出现新函数名即打红」）。

### 🔴 守卫架构：一次 `asyncio.run` 取快照 + 全部断言同步

首版按「每个测试各自 `async def` + `db` fixture」写，实测 **6 个连库断言静默 skip**
（`AttributeError: 'NoneType' object has no attribute 'send'`）—— `app.core.database`
的连接池绑定**首个**事件循环，而 pytest-asyncio 默认每个测试新建 loop。
自定义 module 级 `event_loop` fixture 被当前 pytest-asyncio 忽略（试过，无效）。
→ 改为 `Snapshot` dataclass + 一个 `_load_all()` 里跑完全部查询 + 一次 `asyncio.run`，
断言全部同步。与 memory 记的「一个脚本里两次 `asyncio.run()` 必炸」同源。

### 🔴 本轮新查出 2 个 spec 清单外的问题（已登记 `SUSPECTED_NEW_ISSUES`，**未擅自改**）

| row_code | 现状 | 判定 | 待裁决 |
|---|---|---|---|
| **BS-066 递延收益** | `TB('2811')` | **第 14 个错码** —— `2811` 全库零命中，而「递延收益」实际挂在 **`2401`**（standard 9 / client 6 项目，CAS 2006 口径）。按判据边界 2「码零命中 + 名有归属 = 错码」。**spec 立项时把它列进零命中白名单是错的** —— 白名单依据只查了码没查名 | 是否并入 V138 改码批次（`2811→2401`）|
| **BS-052 一年内到期的非流动负债** | `TB('2501')` | 与 BS-013/BS-053 同型：`2501` 实为长期借款，且**已由 BS-061 长期借款认领** → 重分类派生行 + 跨行双算 | 是否并入置 NULL 批次 |

BS-066 已从 `ZERO_HIT_WHITELIST` 移出（白名单前提被实证推翻）；两者都被守卫的
名称/双算断言显式跳过并在 `SUSPECTED_NEW_ISSUES` 登记理由，
另有 `TestSuspectedNewIssuesReported` 要求每条 ≥30 字且带发现日期、
且不得同时挂在白名单里（防判据自相矛盾）。

**→ V138 的范围因此需要先拍板**：12 行（原计划，BS-014 除外）还是 14 行（并入 BS-052/BS-066）。

### 判据的三条边界（防改坏）

1. **`row_name` 与科目名的差异 ≠ 错码**。报表用语与会计科目用语本就不同
   （`未分配利润` 对应科目 `利润分配`、`预收款项` 对应 `预收账款`）。
   别名表是**穷举**的，不是模糊匹配 —— 加一条就要有实证。
2. **码零命中 ≠ 错码**。要看该科目名在库里有没有别的归属：
   有 → 错码（BS-084 `4005`，库存股实为 `4201`）；
   没有 → 业务事实（BS-004 `1102`，衍生金融资产这批项目都没有）。
3. **按 source 分域判定**。`client` 8 项目 / `standard` 10 项目，
   且 standard 侧并存两套体系 → 合并判定会把 `4101`（client 盈余公积 /
   standard 制造费用+盈余公积）误判成一码多名。

### 与并发 spec 的边界

- `semantic-account-resolver-full-rollout`：它的定向名单结论依赖 `report_config`
  作为层③提示。本 spec 修完后，那边的「层③兜底会取到错科目」风险下降，
  但**不改变**它「剩余 31 个策略不迁移」的结论（那个结论建立在 `account_chart`
  与 `tb_balance` 实证上，与 `report_config` 无关）。
- `g-cycle-extraction-mapping-and-disclosure-alignment`：V137 是它的产物，
  本 spec 不重复其 5 行。

### 已排除的假阳性（记录以免重查）

| 行 | 看似问题 | 为何不是 |
|---|---|---|
| BS-050 其他应付款 = `2231` + `2241` | `2231` 是应付利息 | CAS 报表口径下「其他应付款」合并应付利息/应付股利/其他应付款，属有意聚合 |
| BS-087 盈余公积 = `4101` | standard 侧 `4101` 有「制造费用」 | client 侧 8 项目全是盈余公积；旧制项目的 `4101 制造费用` 属另一体系 |
| BS-088 未分配利润 = `4104` | 科目名是「利润分配」 | 报表用语 vs 科目用语，别名表已收 |
| IS-006 研发费用 = `6604` | client 某项目 `6604` 是勘探费用 | standard 侧 = 研发费用；单项目客户自定义，属 🟡 观察项非错码 |
| BS-117 专项储备 | V136 曾指向它 | formula 本就是 NULL，无需修正 |

### 工具

全表对账用
`python backend/scripts/diagnose/diagnose_semantic_migration_candidates.py --db`
（Task 1 起增 `--report-config` 模式复用同一对账函数，避免两份判据打架）。
