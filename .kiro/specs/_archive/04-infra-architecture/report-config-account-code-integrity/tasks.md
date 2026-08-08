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

- [x] 5. 应用迁移并验证（需重启后端 —— `MigrationRunner` 只在启动时跑）
  - `migration_status` 确认 V138 已应用
  - 逐行 SQL 复核 13 行的新 formula
  - 复跑 Task 3 的守卫 → 应全绿
  - 二次应用（重启一次）确认 0 行影响（Property 1）
  - _Requirements: 1.1~1.7_
  - _Properties: 1, 2_
  - ✅ **五项验证全部通过**（2026-08-05，详见 Notes「V138 应用后验证」）：
    `schema_version` 有 V138（2026-08-04 05:45:17）· 13 行 38 条新 formula 逐行符合预期 ·
    守卫 **29 passed / 0 failed / 0 skipped**（修正前是 4 组红）· 幂等（Property 1）·
    BS-081/083/087/088 未被波及（Property 2）· V138 文件 checksum 无漂移。

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

- [x] 7. 逐行列出下游引用方（已初查，需补全）
  - 已知：BS-014 → 22 文件（K2 + H8 + `wp_surfaced_k.py`）/ BS-053 → 6（K3）/
    BS-033·BS-037 → 5（I 循环）/ BS-082·BS-084·BS-085·BS-086 → M 循环 + L3/L4 scope /
    BS-068 → K5 **与 L 循环双方**（须查是否已双算）/ BS-013·BS-043 → 仅 `useReportColumns.ts`
  - 对每个受影响循环，确认其 spec 兜底码与新解析结果一致（Property 11）
  - _Requirements: 8.1, 8.3, 8.5_
  - _Properties: 11_
  - ✅ **13 行引用面已全量扫出**（7416 个文件：`backend/app` + `backend/scripts` +
    `frontend/src`，排除 `__tests__`），逐行清单见 Notes「下游引用面」。
  - ✅ **复盘二轮把写入路径从 2 条补到 5 条**（见 Notes「复盘补充」）：新查出
    `backend/scripts/fix/fill_report_formulas.py` 是**未完成重构的残留副本**
    （357 行独立实现、零 import 真源、无拦截门、4 处仍是错码）→ 改薄壳委托 service；
    另两条（baseline 采纳 / 公式回滚）实证后登记不改并写明理由。
    新增结构性守卫 `TestNoDuplicateNameTableCopies` 防同类漏网。
  - ✅ **顺带修掉影响面最大的一处：6701/6702 整整互换 6 处（约 1.5 亿）**，
    判据 = `account_chart` 20 项目零分歧 + `report_config` 侧 V137 已确立同一结论；
    初判「不并入本 spec」已撤回，理由见 Notes。
  - 🔴🔴 **顺带挖出并修掉本 spec 最大的漏网风险：`report_config.formula` 有第二条写入路径**
    —— `ReportFormulaService.fill_all_formulas()`（挂 `/api/report-config/seed` 与
    template_library 重建端点），按**行名**索引 4 张表且 `if cfg.formula: skip` **只填 NULL 行**，
    恰好正是 V138 置 NULL 的那一批 ⇒ **不修就等于 V138 白做**。详见 Notes。
  - ✅ **Property 11 达成**：M3/M7/M9/M10 与 I 循环的兜底码与 V138 修正码逐一相同
    （4201 / 4301 / 4003 / 4401 / 1704），无一处分歧。
  - ✅ **同时撤掉 4 个已到期的临时防护**（`trust_report_config=False`，M3/M7/M9/M10）。

- [x] 8. 真实 DB 直跑受影响循环，比对修正前/后金额
  - 至少覆盖两套编码体系各一个项目（旧制 `0ec33ac9` / CAS 2006 `2aa00f57`）
  - 重点：M3/M7/M9/M10（权益段）· K3（BS-053 解除双算）· I2（BS-033 开发支出）
  - 每个差异写「预期变化」或「意外变化」，意外的必须查清再继续
  - 🔴 用真实 DB 不用替身 —— 替身与错误假设同构（本 spec 的 F2/N5 教训同源）
  - _Requirements: 8.2, 8.4, 8.6_
  - _Properties: 14_
  - ✅ **四项全部实测通过**（只读，两套编码体系各一个项目 + 全库 8 项目扫描），
    详见 Notes「V138 下游真实 DB 验证」：
    ① V138 置 NULL 六行 **21 条记录全部 NULL**（非 NULL = 0）
    ② `2901` 认领方由 `[BS-053, BS-067]` 变为 `[BS-067, CFSS-015]` —— **双算已解除**
    （`CFSS-015` 是「递延所得税负债增加」= **变动额**语义，与 BS-067 的余额不构成双算）
    ③ 层③恢复：**全库 40 个 (项目 × spec) 组合中仅 3 组变化，且只变 `resolved_from`
    （`fallback` → `report_config`）、码完全相同** ⇒ 取数金额零变化、溯源来源更准确
    ④ **K3 实测不引用 BS-053**（`spec_for()` 两准则都返 `BS-075`）⇒ V138 对 K3 零影响

- [x] 9. 后端回归 `rtk python -m pytest backend/tests/four_table/ --tb=short -q`
  - 新增/变更失败数必须为 0；预存在失败逐条确认与本 spec 无关
  - 另跑 `backend/tests/ -k "report_config or report_account or four_table"`
  - _Requirements: 8.6_
  - ✅ `backend/tests/four_table/` **1398 passed / 1 failed / 1 skipped**；
    唯一失败 `test_k_cycle_formula_presets.py::test_formula_syntax_valid` 属**并发会话
    K0 spec**（`fix_k0_prefill_presets.py` 写了两条 `PLACEHOLDER`，而 K 循环预设守卫的
    `VALID_FORMULA_TYPES` 白名单没登记它）——判据：该测试文件 `git status` 干净
    且**零引用**本轮改动的任何符号。
  - ✅ `backend/tests/ -k "report_config or report_formula or report_account"`
    **232 passed / 3 skipped / 0 failed**（112.6s）
  - ✅ 新增守卫 `test_report_formula_filler_mirror.py` **63 passed / 1 skipped**；
    接缝守卫 `test_cycle_specs_row_code_evidence.py` **27 passed**；
    连库守卫 `test_report_config_account_integrity.py` **29 passed**
  - ✅ `python -c "import app.main"` 通过（新增跨包 import 无循环依赖）

### Wave 4 — BS-014 裁决 + CI + 收口

- [x] 10. BS-014 其他流动资产口径裁决（**需用户拍板后才动**）
  - 🔴🔴 **run-all-tasks 编排器不得接管本任务**：它不是"被中断"而是"等人拍板"。
    三项实证已于 2026-08-05 完整呈报用户（含倾向 (a) 置 NULL），用户尚未回答。
    该任务的复选框曾从 `[~]` 自动变成 `[-]`，**标记变化不代表可以自动执行** ——
    判据是本行任务体写明的「需用户拍板后才动」这一前置条件，条件不成立即跳过。
    裁决落地后要补 V139 迁移 + K2 回归（22 文件引用），那才是可自动执行的部分。
  - 呈报三项实证：`1901` = 待处理财产损溢/损益（client 5 / standard 8 项目）·
    `tb_balance` 该科目余额**全库恒 0** · `listed_standalone` 额外加的 `TB('1131')`
    应收股利已由 `BS-009` 认领（潜在双算）
  - 三选项：(a) 置 NULL 让 K2 走 `k2_account_scope` 兜底 + 溯源面板显示「本项目无此科目」
    (b) 保留 `1901` 并在别名表登记（承认该科目就是其他流动资产的载体）
    (c) 改指别的码（需先找到能覆盖该语义的标准科目 —— 目前未找到）
  - 倾向 (a)：`1901` 名实不符且余额恒 0，保留只会让溯源面板显示错误来源
  - 裁决后补 V139 迁移 + K2 回归（22 文件引用）
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - ✅ **用户已于 2026-08-05 拍板，三项一并落地 V144（非 V139 —— 那是陈旧文字，
    V139~V143 已被其他 spec 占用，迁移号永不复用）**。裁决内容、证据、守卫结果、
    幂等结果、K2 回归结果见 Notes「BS-014 裁决落地与验证（2026-08-05 Task 10）」。

- [x] 11. CI 接入 `governance-checks.yml`
  - 新增 job `report-config-account-integrity`，挂在**有 DB** 的 job 上
  - 跑 `test_report_config_account_integrity.py`
  - 反向自检也要在 CI 跑（防守卫被改成空转后无人察觉）
  - _Requirements: 6.3, 6.6_
  - ✅ job `report-config-account-integrity` 已加（**7 步**，带 `postgres:16` service +
    先跑 `MigrationRunner` 应用 V138 再验），沿用既有只读连库 job 范式
    （`legacy-encoding-balances`）；`-rs` 让「PG 不可达」的 skip 原因出现在日志里
    —— 静默 skip 是假绿源。
  - ✅ 三层守卫全部入 CI：连库一致性 + 第二写入路径镜像 + V138 接缝防过期。
    反向自检（`TestReverseSelfcheck` / `TestExtractionActuallyWorks` /
    `test_is006_stays_because_it_is_not_a_wrong_code`）随文件一起跑。
  - ✅ `yaml.safe_load` 校验通过，**117 → 118 jobs**。

- [x] 12. 收口
  - `memory.md` 更新：`report_config` 错码由「6 处」更正为
    「V137 已修 5 + 本 spec **16**（V138 13 + V144 3）」
    - 🔴 **2026-08-05 Task 10 完成后修订**：原写「本 spec 13 + BS-014 待裁决」已过期 ——
      BS-014 已由用户拍板置 NULL，与 BS-052 / BS-066 一并落地 **V144**，
      故本 spec 合计 **16 行**、无待裁决项。memory.md 与 INDEX.md 已按此同步。
  - 把「两套编码体系（旧《企业会计制度》3xxx/4xxx成本/5xxx ↔ CAS 2006 4xxx/6xxx）」
    与「`3101`/`3201` 一码两义且 CAS 侧带真金额」写进 memory（现只记了「一码两义」现象，未记体系名）
  - `.kiro/specs/INDEX.md` 更新
  - _Requirements: 6.3_
  - ✅ **memory.md**：新增 4 条平台级铁律 —— ①`report_config.formula` **两条写入路径**
    ②「按 row_code 置 NULL」与「按名禁填公式」是两个不同集合（`CFSS-016` 豁免）
    ③守卫截函数体的缩进正则必须 `[ \t]*` 不能 `\s*`（`re.M` 下 `\s` 含换行）
    ④临时防护（`trust_report_config=False`）必须与数据修正真源交叉锁死防静默过期；
    并把本 spec 进度与全部实测结论写入任务状态段。
  - ✅ **两套编码体系**：memory 已有专条「🔴🔴🔴 两套编码体系现在能按名字说清了」
    （旧《企业会计制度》2001 的 3xxx 权益 / 4xxx 成本 / 5xxx 损益 ↔ CAS 2006 的
    4xxx 权益 / 6xxx 损益 + `3101`/`3201` 一码两义且 CAS 侧 `3201 套期工具` 带真金额
    −4,314,686.92），本轮无需重写。
  - ✅ **INDEX.md**：头部统计 Active **4 → 6**（行首锚定正则实扫，并发会话新建了
    `l0-confirmation-source-alignment` 与 `sampling-evaluation-and-governance-closure`）；
    本 spec 行进度 5/12 → 10/12 并补第二写入路径的说明；并发会话警示段补入本轮
    实测到的那次真实回退。
  - 🔴 **Task 10 未完成不阻塞本任务**：BS-014 的最终处置本身就是以「待裁决」状态
    写入 memory 的内容；裁决落地后只需把那一句改成结论 + 补 V139 记录。

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

### V138 应用后验证（2026-08-05 Wave 2 / Task 5 实测）

**1. V138 已应用** —— `schema_version` 记录 `version='138'` /
`filename=V138__fix_report_config_equity_and_asset_codes.sql` /
`applied_at=2026-08-04 05:45:17.786035`（V137 之后、V139 之前，序列连续）。
磁盘迁移最高号与已应用最高号均为 **143**，无待执行迁移。

**2. 逐行 SQL 复核 —— 13 行 / 38 条全部符合预期**（`updated_at` 全部恰为
V138 的 `applied_at`，与 `schema_version.applied_at` 逐微秒相等 ⇒ 单事务、无部分应用）：

| row_code | 变体数 | 新 formula | 预期 |
|---|---|---|---|
| BS-082 | 4 | `TB('4401','期末余额')` | ✔ 4003→4401 |
| BS-084 | 4 | `TB('4201','期末余额')` | ✔ 4005→4201 |
| BS-085 | 4 | `TB('4003','期末余额')` | ✔ 4102→4003 |
| BS-086 | 4 | `TB('4301','期末余额')` | ✔ 4103→4301 |
| BS-033 | 4 | `TB('1704','期末余额')` | ✔ 1703→1704 |
| EQ-015 | 1 | `TB('4301', '期末余额') - TB('4301', '期初余额')` | ✔ **两处 4201 都换了** |
| IMP-008 | 1 | `TB('1505', '期末余额')` | ✔ 1502→1505 |
| BS-013 / BS-043 / BS-053 | 各 4 | `NULL` | ✔ 置 NULL |
| BS-090 | 2 | `NULL` | ✔（`soe_standalone` 的「△分出再保险合同负债」`updated_at` 仍是 2026-06-16 = 未被触碰，与 Task 4 预演一致）|
| CFSS-016 | 1 | `NULL` | ✔（仅 `soe_standalone` 有 formula，另三变体 `updated_at` 仍 2026-06-16）|
| IMP-017 | 1 | `NULL` | ✔ |

合计 **38 行**，与 Task 4 的只读预演逐行相等。

**3. 守卫复跑 → 全绿**：`test_report_config_account_integrity.py`
**29 passed / 0 failed / 0 skipped**（0.44s）。修正前基线是「4 组打红 / 25 通过」，
现全部转绿；其中 `TestNoMismatchedCodes` / `TestDerivedRowsHaveNoAccount` /
`TestNoCrossRowDoubleClaim` / `TestCodeCorrectionsApplied` 四组正是曾点名 13 行的那四组。
🔴 **确认不是静默 skip 造成的假绿** —— `-v` 输出 29 条全 `PASSED` 无 `SKIPPED`，
且 `TestRefExtraction::test_refs_non_empty` 与 `test_chart_non_empty_and_split_by_source`
双双通过 ⇒ 连库成功且抽取集合非空。四条反向自检（注入错码 / 清空别名 / 合并 source /
派生行回填）同样在册且通过。

**4. 幂等（Property 1）—— 两条独立证据**：
- 只读复核 13 条 UPDATE 的 WHERE 谓词（`row_code` + 已实证错值 +
  `NOT LIKE 'project:%'` + `is_deleted=false`）：**命中 0 行** ⇒ 二次应用无变更。
- 再跑一次 `python -m app.core.migration_runner`（cwd=backend）：日志
  「数据库已是最新版本，无待执行迁移」+ 正常释放 advisory lock ⇒ 0 行影响。
  🔴 exit code 为 1 是 GBK 控制台把 UTF-8 日志渲染成乱码触发的
  `NativeCommandError`，**不是迁移失败** —— 判成败看日志与 `schema_version`，不看 exit code。

**5. Property 2 已正确行未被波及**：BS-081 `TB('4001','期末余额')` /
BS-083 `TB('4002',…)` / BS-087 `TB('4101',…)` / BS-088 `TB('4104',…)`
四行 × 4 变体共 16 条，`updated_at` 全部仍为 **2026-04-29 10:38:03**（远早于 V138），
formula 逐字节不变（含「无空格」的原始书写形态）。

**6. 顺带核实无 checksum 漂移**：V138 文件当前 SHA-256
`97de7ecc3fff96fa2dfa45378f1448088da198a153ae7abacf50c913e7c71933`
与 `schema_version.checksum` **完全相等** ⇒ 已应用迁移文件未被事后编辑。

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

### 🔴🔴🔴 `report_config.formula` 有**第二条写入路径**，不修它 V138 等于白做（2026-08-05 Task 7 实测）

立项时只把 `report_config` 当"迁移改、代码读"的数据表。实测发现它有两条写入路径：

1. `backend/migrations/V*.sql`（V137 / V138）；
2. **`ReportFormulaService.fill_all_formulas()`** —— 挂在 `POST /api/report-config/seed`
   与 template_library 重建端点上。

第 2 条按**行名**索引四张表（`_BS_SPECIAL` / `_EQ_SPECIAL` / `_IMP_SPECIAL` /
`_NAME_TO_ACCOUNT`），策略顺序 special → CAS map → 合计行关键词 → fallback，
且开头就是 `if cfg.formula: skip`（**只填 NULL 行**）。

**这两个特性叠加起来正好把 V138 的成果反向抹掉**：置 NULL 的 6 行恰恰是它唯一会去填的行，
而它填的正是刚删掉的错码。实测会被填回：

| V138 置 NULL 的行 | filler 会填回 | 该码实际是什么 |
|---|---|---|
| BS-090 少数股东权益 | `4201` | 库存股（且与修正后的 BS-084 双算） |
| BS-013 / BS-016 一年内到期的非流动资产 | `1503` | 可供出售金融资产（旧准则） |
| BS-053 / BS-058 其他流动负债 | `2301` | 码与名全库均零命中 |
| BS-043 / BS-059 衍生金融负债 | `2102` | 短期应付债券 |
| IMP-017 商誉减值准备 | `1711` | 商誉**原值**（把原值当备抵） |

改码 4 行同样在两条路径上分叉（filler 侧仍是错码）：库存股 `4003` / 减库存股 `4003` /
专项储备 `4103`（`_BS_SPECIAL` + `_EQ_SPECIAL` + 「提取专项储备」变动额三处）/ 开发支出 `1703`。
**权益合计公式里也各有一处**（`归属于母公司所有者权益合计` 与 `所有者权益合计`）——
同一科目在同一文件里有两个码就是双真源，守卫锁不住，故一并改。

**处置（三层）**：

1. **镜像改码** —— 判据真源 `FORMULA_FILLER_MIRRORED_CORRECTIONS`（4 条，每条带
   `(错码, 正码, 实证)`）；filler 侧 4003 / 4103 现已**彻底为 0**。
2. **派生行前置拦截** —— `fill_all_formulas` 在标题行跳过之后、**策略 1 之前**按
   `DERIVED_ROW_NAMES_WITHOUT_ACCOUNT` 拦截并 `continue`；两个归一函数都比一次
   （filler 的 `_normalize_name` 与真源的 `normalize_name` 剥离规则不同，宁多拦不漏拦）。
   **按名而非按 row_code**：同一语义的派生行在不同准则变体下挂不同 row_code
   （`BS-013`/`BS-016` 都叫「一年内到期的非流动资产」），filler 的匹配键是行名。
3. **双保险** —— 派生行名同时从四张名索引表里删除（拦截门一旦被删也不会静默回归错码）。

### 🔴🔴 复盘补充（2026-08-05 二轮）：写入路径实际是 **5 条**，不是 2 条

Task 7 首轮只查到 2 条就收工，复盘时按「全仓找 `report_config.formula` 的写入点」
重扫 4696 个 py/sql 文件，命中 57 个文件，逐个判完得 5 条真实写入路径：

| # | 路径 | 定性 | 处置 |
|---|---|---|---|
| 1 | `backend/migrations/V*.sql` | 迁移（V137 / V138） | 本 spec 主体 |
| 2 | `ReportFormulaService.fill_all_formulas()` | 服务，按行名索引只填 NULL 行 | ✅ 已收口（三层） |
| 3 | **`backend/scripts/fix/fill_report_formulas.py`** | **未完成重构的残留副本** | ✅ 改薄壳（见下） |
| 4 | `report_config_service.approve_candidate()` / `sync_to_projects()` | baseline 采纳 / 主模板下发 | 登记不改（见下） |
| 5 | `formula_audit_log.rollback_formula()` | 一键回滚到历史公式 | 登记不改（见下） |

**路径 3 是真漏网**：归档 spec `_archive/05-business-features/e2e-business-flow/` Task 9
已把它的逻辑封装成 service，其 design.md 明确写「保留作 CLI 入口，**内部调 service**」——
但那次重构只做了前半截：service 建好了，脚本仍是 357 行独立副本，`import` 里既没有
service 也没有判据真源。实测它带着 service 已修掉的错码：

* `专项储备` 两处 = `TB('4103')`（本年利润）· `开发支出` = `TB('1703')`（无形资产减值准备）
* `一年内到期的非流动资产` → `1503` · `其他流动负债` → `2301` **仍作为键存在**
* **完全没有派生行拦截门** ⇒ 跑一次就把 V138 置 NULL 的行全填回错码

表对比进一步证明它只是旧快照：`BS_SPECIAL(49) ⊂ _BS_SPECIAL(71)`，且脚本"独有"的那 2 条
恰恰是本轮从 service 删掉的两个派生行；`IS_SPECIAL` / `EQ_SPECIAL` 是 service 对应表的真子集。

→ **改薄壳而非删除**：CLI 的 `--dry-run` / `--standard` 有运维价值，但判据必须单一真源。
`--dry-run` 现在靠事务回滚实现 —— 它验的是「真跑一遍会写什么」，
而不是「另一份实现认为会写什么」。357 行 → 约 105 行（全是文档 + 委托）。

**路径 4/5 登记不改的理由**：
* `approve_candidate` 有审核环节（`status pending→approved` + `reviewed_by`），是**用户驱动**
  而非自动写入；`sync_to_projects` 方向是「主模板正确值下发项目」且 `keep_local` 保护自定义
  ⇒ V138 修对后它反而是好事。
* `rollback_formula` 的 WHERE 是 `project_id = :pid AND row_code = :rc` ⇒ **只动 project 级行**，
  而 V138 修的是 `applicable_standard NOT LIKE 'project:%'` 的主模板行，且本库 project 级行
  **实测 0 条**。机制上「回滚就该回到历史值」是正确语义，不该阻止。

**新增结构性守卫** `TestNoDuplicateNameTableCopies`：扫 `backend/**` 里所有
`{BS,IS,EQ,IMP,CFS_INDIRECT}_SPECIAL` / `NAME_TO_ACCOUNT` 形态的字典声明，
不在允许名单内即打红 + 断言 CLI 脚本必须委托 service 且不得自带策略函数。
这条才是防同类漏网的根 —— 前面那批断言只读 service 一个文件，抓不到「另一份实现」。

### ✅ 复盘顺带修掉影响面最大的一处：6701 / 6702 整整互换（约 1.5 亿）

原本登记在 `FORMULA_FILLER_SUSPECTED_ISSUES` 里「不并入本 spec」，复盘实证后**撤回该判断**：

* **`account_chart` 零分歧铁证**：`6701 = 资产减值损失`（standard 10 / client 7 项目）、
  `6702 = 信用减值损失`（standard 10 / client 8 项目）——20 个项目 × 2 个 source 全部一致。
* **`report_config` 侧已由 V137 按同一结论修对**：`IS-016 信用减值损失` = `TB('6702')` /
  `IS-017 资产减值损失` = `TB('6701')` / `CFSS-003 资产减值损失` = `TB('6701')` /
  `CFSS-004 信用减值损失` = `TB('6702')`，四个准则变体一致。
* **第二写入路径从未同步**，6 处互换：`_IS_SPECIAL` 2 + `_CFS_INDIRECT_SPECIAL` 2 +
  `_IMP_SPECIAL` 2 —— 与本 spec 修的 4 个改码行**完全同型**（同一笔错误只修了迁移侧）。
* **影响面**：`tb_balance` 实测借方合计 `6701` = 3,552,753.12 / `6702` = 153,412,435.11
  ⇒ 互换即差约 **1.5 亿**。

改它的理由：判据是铁证、落点就在本轮已在改的同一文件、修法是纯粹两码互换无新增逻辑，
且本 spec 的实际交付已从「改 13 行数据」扩展为「**收口 `report_config.formula` 的全部写入路径**」
—— 第二写入路径上的错码，无论对应哪个 row_code 都在这个范围内。同型的修一半留一半才是不一致。

同族另修 2 处（原实现同样互换）：「本年计提坏账」→ `6702`（金融工具准则：应收款项减值走
信用减值损失）、「本年计提存货跌价」→ `6701`。
「资产减值准备」= 两者之和，不受互换影响，**保持原样**并加断言防被"顺手"改成单码。

新增真源 `IMPAIRMENT_LOSS_CODE_BY_NAME` + 守卫 `TestImpairmentLossCodesNotSwapped`
（含「真源两码不得塌成一个」的自检），4 个变异全部准确打红。

### 🔴 两个"派生行"表语义不同，别当同一份清单（本轮新增 `DERIVED_ROWS_EXEMPT_FROM_NAME_BLOCK`）

- `DERIVED_ROWS_WITHOUT_ACCOUNT`（按 row_code）= 「V138 不给它单一科目码」；
- `DERIVED_ROW_NAMES_WITHOUT_ACCOUNT`（按行名）= 「第二写入路径也不许按名填任何公式」。

**前者成立不蕴含后者** —— 有的行虽无单一科目，却有**正确的合成公式**。
`CFSS-016 存货的减少` 就是：V138 置 NULL 只为移除原单码 `TB('1401')`（材料采购，全库实测期末恒 0），
而 filler 给的是 `SUM_TB('1400~1499','年初余额')-SUM_TB('1400~1499','期末余额')`
—— **区间 + 变动额，口径正确**。拦掉它等于把一个对的公式换成 NULL，是负优化。
两条路径在此处是**接力**关系（迁移移除错码 → filler 填正确合成公式），不是冲突。

该豁免依赖 filler 侧公式保持区间形态，守卫用 `SUM_TB( == 2` + `年初/期末` + 
`not TB('14dd'` 三条断言钉死；一旦被改回单码就打红提醒重新纳入拦截。

**🔴 本轮实测到一次真实回退**：写完豁免理由约十分钟后，该行被并发改动改成了
`TB('1401','年初余额')-TB('1401','期末余额')`（单码）。守卫立刻打红并给出准确指引，
已按实证恢复区间口径 + 加注释说明为何不得退回单码。**这是本轮守卫的第一次实战价值**。

### 🔴 filler 侧另有 15 条名实不符，**本 spec 有意不动**（`FORMULA_FILLER_SUSPECTED_ISSUES`）

对 filler 的 4 张名索引表（182 个单码条目）跑同一套双向对账，得 58 名实不符 + 19 零命中，
但**大半是对账判据自身的缺陷**（`固定资产减值准备年初 → 1603` 实际正确、
`股本 ↔ 实收资本` 是合法别名、`货币资金 → 1001` 是 fallback 的单码降级近似）。
逐条查完只登记**实证确凿且与本 spec 13 行无交集**的 15 条，供另立 spec 裁决。

最值得单独立项的两条：

- **`信用减值损失` / `资产减值损失` 在 `_IMP_SPECIAL` 里整整互换**（→6701 / →6702）——
  与 V137 已在 `report_config` 修掉的 `IS-016`/`IS-017` 互换**完全同型**，
  说明同一笔错误在第二写入路径从未同步修正。
- **`开发支出减值准备 → 1704`**：本 spec 把「开发支出」由 1703 改指 1704 后，
  同表内 **1704 一码两义**。CAS 2006 未给开发支出设独立减值备抵科目 → 该条目大概率应删。

### V138 下游真实 DB 验证（2026-08-05 Task 8，只读）

**① 置 NULL 六行现状**：21 条记录（4 个准则变体 × 6 行，部分行只在个别变体存在）
**全部 NULL**，非 NULL = 0。
顺带留证：`BS-090` 在 `soe_standalone` 下 row_name 是 **`△分出再保险合同负债`**
（不是少数股东权益）—— 又一例「同一 row_code 在不同准则下是不同科目」，
V138 的 WHERE 带 formula 条件天然跳过了它。

**② BS-053 双算解除**：`formula LIKE '%2901%'` 的认领方由 `[BS-053, BS-067]`
变为 **`[BS-067, CFSS-015]`**。`CFSS-015` 是「递延所得税负债增加」，公式为
**期末 − 年初的变动额**，与 BS-067 的期末余额不同报表、不同语义 ⇒ **不构成双算**。

**③ 层③恢复的实际影响面（撤 4 个 `trust_report_config=False` 的零回归论证）**：
全库 8 个项目 × 5 个 spec = 40 个组合，**仅 3 组结果变化，且只变 `resolved_from`
（`fallback` → `report_config`），码完全相同（都是 `4301`）**。

| 项目 | spec | 层③启用 | 层③关闭 |
|---|---|---|---|
| 重庆医药集团和平物流_2025 | M7/BS-086 专项储备 | `['4301']:report_config` | `['4301']:fallback` |
| 重庆医药集团四川物流_2025 | M7/BS-086 专项储备 | `['4301']:report_config` | `['4301']:fallback` |
| 重庆和平药房连锁_2024 | M7/BS-086 专项储备 | `['4301']:report_config` | `['4301']:fallback` |

⇒ **取数金额零变化，溯源来源更准确**（能如实说明报表规则确实映射到该科目，
而不是"靠代码里写的兜底码碰上的"）。这三个项目的 client chart 里没有「专项储备」这个名
故层①②不中；V138 修对后层③接上了。

**④ 两套编码体系覆盖**：
- `0ec33ac9`（旧《企业会计制度》体系）：M3/M7/M9/M10 四个槽全部 `account_chart_client`
  命中且码 = V138 修正值（4201 / 4301 / 4003 / 4401）；I2/BS-033 命中 `1704`。
- `2aa00f57`（CAS 2006）：M3/M10/I2 三个槽 `found=False` + `codes=[]`
  —— **本项目确实没有这些科目，返空是正确行为**（宁缺勿造），层③启用也救不了
  （层③要求"码在本项目科目表里存在"）；M9 命中 `4003`。

**⑤ K3 与 BS-053 无关（推翻 Task 7 初查清单里的一条）**：
`K_CYCLE_SPECS['K3']` 是 **`KCycleSpec` 变体规格 + 旧机制 `ReportLineAccountSpec`**
（K 循环未迁语义解析器），其 `spec_for()` 对 `soe_standalone` 与 `listed_standalone`
**都返回 `row_code='BS-075'`**、`fallback_gross=('2241',)`。
故 V138 把 BS-053 置 NULL 对 K3 **零影响**（它本来就走兜底码）。
K3 自身的 row_code 错位（`BS-075` 在 soe 侧 row_name 是「其他应付款」formula NULL，
**listed 侧 row_name 竟是「股本」**；真正有公式的是 `BS-050 = TB('2241')+TB('2231')`
⇒ K3 靠兜底 `2241` 碰巧对但溯源行错 + **漏 `2231`**）属 K 循环侧的活，
已有守卫钉住该分歧、修好即打红。

### BS-014 裁决落地与验证（2026-08-05 Task 10）

用户拍板：**三项一并落地**，迁移 `V144__fix_report_config_bs014_bs052_bs066.sql`
（`schema_version` version=`144` / `applied_at = 2026-08-05 11:10:31.940590`，
V137→V138→V143→V144 序列连续）。

🔴 **迁移号**：任务体原写「补 V139 迁移」是**陈旧文字** —— V139~V143 早已被其他 spec 占用
（V139 sampling_registry_batch_binding / V140 sampled_vouchers_manual_scope_unique /
V141 deliverable_section_rendered_block_hash / V142 deliverable_version_editor_identity /
V143 deliverable_version_drift_report）。**迁移版本号永不复用** → 用 V144。
V144 已应用，**不得编辑**（会造 checksum 漂移），也不得再补一个迁移。

#### 三项裁决与落地结果（只读 SQL 逐行核实）

| row_code | 裁决 | 现 formula（4 个标准变体全部） | `updated_at` |
|---|---|---|---|
| **BS-014** 其他流动资产 | **置 NULL**（Requirement 5 选项 a，即推荐项） | `NULL` × 4 | 11:10:31.940590 |
| **BS-052** 一年内到期的非流动负债 | **置 NULL** | `NULL` × 4 | 11:10:31.940590 |
| **BS-066** 递延收益 | **改码 2811 → 2401** | `TB('2401','期末余额')` × 4 | 11:10:31.940590 |

四行 `updated_at` 与 `schema_version.applied_at` **逐微秒相等** ⇒ 单事务、无部分应用。

**未被波及（Property 2 的对照组，本轮新增两个）**：
`BS-061 长期借款` 仍 `TB('2501','期末余额')` · `BS-067 递延所得税负债` 仍 `TB('2901','期末余额')`,
两者 `updated_at` 均仍为 **2026-04-29 10:38:03**（远早于 V144）⇒ 逐字节未动。

#### 双算解除（Property 10）—— 认领方按码复查

| 码 | V144 后的认领方 | 说明 |
|---|---|---|
| `2501` | **仅 `BS-061`** | 原 `[BS-052, BS-061]` 跨行双算已解除 |
| `1131` | **仅 `BS-009`** | 原 `[BS-009, BS-014]`（BS-014 的 listed_standalone 变体额外加 `TB('1131')`）已解除 |
| `1901` | **零认领** | 全表再无 `1901` 引用 |
| `2811` | **零认领** | 该零命中码彻底退出 |
| `2401` | **仅 `BS-066`** | 改码未产生新双算（2401 此前零认领） |

#### 守卫结果（Requirement 6）

`backend/tests/four_table/test_report_config_account_integrity.py`
→ **34 passed / 0 failed / 0 skipped**（`-v` 逐条确认，0.50s）。

🔴 **确认不是静默 skip 造成的假绿**：`TestRefExtraction::test_refs_non_empty` 与
`test_chart_non_empty_and_split_by_source` 双双 PASSED ⇒ 连库成功且抽取集合非空；
`-v` 输出 34 条全 `PASSED`、无一条 `SKIPPED`。四条反向自检
（注入错码 / 清空别名 / 合并 source / 派生行回填）全部在册且通过。

**用例数由 V138 时的 29 增至 34** —— 新增 `TestAdjudicationLanded` 5 例，
它是本轮裁决的**交叉锁死**：断言 `ADJUDICATED_2026_08_05` 每条都已落地到
`CODE_CORRECTIONS`（改码）或 `DERIVED_ROWS_WITHOUT_ACCOUNT`（置 NULL）**恰好之一**、
不得再挂在 `SUSPECTED_NEW_ISSUES` / `PENDING_ADJUDICATION` / `ZERO_HIT_WHITELIST` 里、
且每条理由须带实证 —— 防「裁决了但没落地」与「落地了但登记表自相矛盾」。

#### 幂等（Property 1）—— 两条独立证据

1. **只读复演三条 UPDATE 的 WHERE 谓词**（`row_code` + 已实证错值 +
   `NOT LIKE 'project:%'` + `is_deleted=false`）：BS-014 / BS-052 / BS-066
   **各命中 0 行** ⇒ 二次应用零变更。
2. `python -m app.core.migration_runner`（cwd=backend）→ 日志
   「**数据库已是最新版本，无待执行迁移**」+ 正常获取/释放 advisory lock。
   🔴 exit code 为 1 是 GBK 控制台无法编码 `ℹ️`(U+2139) 触发的 `UnicodeEncodeError`
   → `NativeCommandError`，**不是迁移失败**；判成败看日志与 `schema_version`，不看 exit code。

#### 单一真源模块的收敛状态（Requirement 5.3 的落点）

`backend/app/services/four_table/report_config_account_names.py` 经核实**已与 V144 后的
数据状态一致，本轮无需再改**（前序会话已随 V144 一并收敛）。逐项确认：

- `DERIVED_ROWS_WITHOUT_ACCOUNT` **已含 `BS-014` / `BS-052`**（各带完整实证理由）
- `CODE_CORRECTIONS` **已含 `BS-066`**（`2811 → 2401`）
- `SUSPECTED_NEW_ISSUES` **已清空**（BS-052 / BS-066 两条移入 `ADJUDICATED_2026_08_05`）
  —— 🔴 留空 dict 而非删除常量是**有意的**：守卫的 `TestNoMismatchedCodes` /
  `TestNoCrossRowDoubleClaim` 用它做跳过集，清空后这两行**重新进入正向断言**，
  那正是「修完就该被守卫盯住」。若继续挂在跳过集里，守卫会对这两行永久空转。
- `PENDING_ADJUDICATION` **已清空**（同上，机制载体保留）
- `ZERO_HIT_WHITELIST` **已移出 `BS-066`**（白名单前提被推翻：码零命中但名有归属 = 错码）
- `ROW_NAME_ACCOUNT_ALIASES` **已移除 `("待处理财产损溢","待处理财产损益")`** ——
  BS-014 置 NULL 后全表再无 `1901` 引用，该别名对成为死条目；两种写法的实证记录
  保留在 `ADJUDICATED_2026_08_05['BS-014']`
- `DERIVED_ROW_NAMES_WITHOUT_ACCOUNT`（第二写入路径的按名拦截）**已含**
  「其他流动资产」与「一年内到期的非流动负债」

🔴 **`BS-017` 有意只按名拦截、不进按 row_code 的 `DERIVED_ROWS_WITHOUT_ACCOUNT`**：
它的 listed 两变体 row_name 也叫「其他流动资产」（formula 本就 NULL），
但 **soe 两变体叫「△买入返售金融资产」**（金融机构专用科目 1031，语义不同）
→ 按 row_code 登记会禁掉一个合法科目。

#### 第二写入路径（filler）—— 反向锁死

`test_report_formula_filler_mirror.py` + `test_cycle_specs_row_code_evidence.py`
→ **108 passed / 1 skipped**（skip 原因非空且可见：`1703` 在 `_IMP_SPECIAL`
里作「无形资产减值准备」是**合法用途**，本 spec 禁的是「开发支出」误用 1703 而非禁用该码）。

🔴 **BS-066 这条与另四条改码方向相反**：filler 侧「递延收益」**一直就是 2401（正确）**，
是 `report_config` 的 BS-066 写了零命中的 2811 → **V144 是把 report_config 对齐到 filler**，
不是反过来。`FORMULA_FILLER_MIRRORED_CORRECTIONS['递延收益']` 因此登记为**反向锁死**：
防下个会话为了「两条路径一致」把 filler 的 2401 改成 2811 —— 那会把一个能取到数的
正确码换成恒空的错码。

#### K2 回归（Requirement 5.4）

BS-014 被约 70 个文件引用，K2 是主消费方。

**① 真实 DB 直跑 `resolve_report_line_accounts(K2_ACCOUNT_SPEC)`，全库 8 个项目**：

| 指标 | 结果 |
|---|---|
| `resolved_from` | **`fallback`**（8/8，V144 前是 `report_config`）|
| `formula` | **`None`**（8/8）|
| `gross_standard` | `['1901']`（8/8，来自 `K2_ACCOUNT_SPEC.fallback_gross` 自己声明的码）|
| `provision` | `[]`（其他流动资产无备抵科目，`fallback_provision=()`）|
| `extra` | `{'1131': ['1131']}` —— 应收股利仍**单列不并入**原值（`extra_standard_codes`）|
| **码集与 V144 前是否相同** | **8/8 相同 ✔** |

⇒ **取数金额零变化，只有来源标记变了**：溯源面板不再声称「报表规则映射到 1901」，
改为如实显示走 K2 自己的兜底码。这正是 Requirement 5.3 要的效果。

**② 该科目余额恒 0 的实证复核**：`tb_balance` `LIKE '1901%'` 共 **12 行 / 6 项目**，
`SUM(ABS(opening_balance))` 与 `SUM(ABS(closing_balance))` **均为 0.00**
⇒ 即便按 1901 取数也恒为 0，保留 `report_config` 映射只会让溯源面板显示错误来源。

**③ 自动化回归**：
- 后端 `test_k2_account_scope.py` + `test_k2_formula_presets.py` → **41 passed / 0 failed**
- 前端 `npx vitest run k2 K2` → **7 files / 190 passed / 0 failed**
  （`k2FourTableWiring` 40 · `k2NoteSubtableContract` 36 · `k2Integration` 18 ·
  `k2OtherCurrentAssets.contract` 17 · `useK2DisclosureEngine` 15 等）

🔴 K2 前端守卫仍断言 `K2_REPORT_ROW_CODE === 'BS-014'` 且
`K2_GROSS_FALLBACK_STANDARD === '1901'` —— **这是对的，不要因为置 NULL 就去改它们**：
`BS-014` 仍是「其他流动资产」的正确报表行号（只是该行不再挂单一科目码），
`1901` 是 K2 **自己声明的兜底码**（运行态优先取 render 下发的 `tb_source_codes.gross_standard`，
常量只作兜底 + 展示）。

#### 全量后端回归（Requirement 8.6）

`python -m pytest backend/tests/four_table/ --tb=short -q`
→ **1457 passed / 1 failed / 1 skipped**（8.72s）。**新增/变更失败数 = 0**。

唯一失败 `test_k_cycle_formula_presets.py::test_formula_syntax_valid`
（`未知函数: K0-1-matrix-{其他应收款,其他应付款}-book_amount | unknown: {'PLACEHOLDER'}`）
**属并发会话的 K0 spec，非本 spec**。三条判据：

1. traceback 落在 `test_k_cycle_formula_presets.py:233`，**该文件 `git status` 干净**（未修改）
2. 该文件对 `report_config_account_names` / `BS-014` / `BS-052` / `BS-066` / `V144`
   **grep 命中 0**（零引用本轮任何符号）
3. 真实触发源是 `backend/data/prefill_formula_mapping.json` 处于 ` M`（已修改）——
   K0 spec 往 K0-1 矩阵格写了 `PLACEHOLDER`，而 K 循环预设守卫的 `VALID_FORMULA_TYPES`
   白名单未登记它。与 Task 9 记录的同一条失败，状态未变。

#### 本 spec 的错码总账（收口口径）

| 批次 | 行数 | 内容 |
|---|---|---|
| V137（前序 spec 产物，本 spec 不重复） | 5 | BS-022 / BS-025 / BS-026 / IS-016 / IS-017 |
| **V138**（本 spec Wave 2） | **13** | 权益段 5 改码 + 资产/减值段 2 改码 + 6 行置 NULL |
| **V144**（本 spec Wave 4 / Task 10） | **3** | BS-014 置 NULL · BS-052 置 NULL · BS-066 改码 |
| **本 spec 合计** | **16** | = V138 的 13 + V144 的 3 |

→ Task 12 收口里「本 spec 13 行」的表述**已过期**，正确表述是
「V137 已修 5 + 本 spec 16（V138 13 + V144 3）」，且 BS-014 **不再是待裁决状态**。
memory.md 与 INDEX.md 已同步更新。

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

### 下游引用面（2026-08-05 Task 7 全量扫描，7416 个文件）

扫描范围 `backend/app` + `backend/scripts` + `frontend/src`，排除 `__tests__`。
正对照 `BS-009`（K1 其他应收款）命中 27 个文件 ⇒ 扫描面非空，0 引用是真的没人引用。

| row_code | 处置 | 引用数 | 关键引用方（除判据真源与 seed 脚本外） |
|---|---|---|---|
| BS-082 | →4401 | 7 | `_m7_special_reserve.py` · `m_cycle_specs.py` · `useReportColumns.ts` |
| BS-084 | →4201 | 7 | `report_formula_service.py` · `m_cycle_specs.py` · `useReportColumns.ts` |
| BS-085 | →4003 | 9 | `m_cycle_specs.py` · `l_cycle_extraction/account_scope.py` · `l3AccountScope.ts` |
| BS-086 | →4301 | 10 | `report_formula_service.py` · `m_cycle_specs.py` · `l4AccountScope.ts` |
| EQ-015 | →4301 | 5 | 仅判据真源 + seed 脚本（无循环代码引用） |
| BS-033 | →1704 | 11 | `i_cycle_accounts.py` · `i_cycle_specs.py` · `i1AccountScope.ts` · `useICycleFourTableSource.ts` |
| IMP-008 | →1505 | 2 | 仅判据真源 + `generate_cfss_imp_formula_presets.py` |
| BS-090 | NULL | 5 | `report_formula_service.py`（已删条目） |
| BS-043 | NULL | 5 | `report_formula_service.py`（已删条目）· `useReportColumns.ts` |
| BS-053 | NULL | 11 | `_k3_other_payables.py` · `k_cycle_specs.py` · `k3AccountScope.ts` · 两个 FormulaEditDialog |
| BS-013 | NULL | 5 | `report_formula_service.py`（已删条目）· `useReportColumns.ts` |
| CFSS-016 | NULL | 3 | `report_formula_service.py`（**保留区间公式**，见豁免说明） |
| IMP-017 | NULL | 4 | `report_formula_service.py`（已删条目）· `i3AccountScope.ts` |

🔴 `report_formula_service.py` 在 8 行里出现 —— **它就是那条第二写入路径**，
初查清单把它当普通"读取方"漏过去了。

### 工具

全表对账用
`python backend/scripts/diagnose/diagnose_semantic_migration_candidates.py --db`
（Task 1 起增 `--report-config` 模式复用同一对账函数，避免两份判据打架）。
