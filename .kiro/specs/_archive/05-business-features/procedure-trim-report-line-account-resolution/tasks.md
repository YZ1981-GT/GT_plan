# Implementation Plan: 裁剪判据的报表行科目定位

## Overview

把裁剪判据的科目金额定位从「程序名 ↔ 科目名子串匹配」改为「程序 → 报表行 → 报表公式 → 金额」，使重要性判据（决策内核档 7/8）在真实数据上真正可用。

**净新增 = 2 个后端模块 + 1 处前端优先级调整。** 三段映射的每一段都委托既有生产真源（`four_table/*_cycle_specs.py` 的 `row_code` 声明 · `report_config.formula` · `ReportFormulaParser`），本 spec **不新建任何映射知识、不写公式解析、不写科目聚合**。

### 落地前必读的五条约束

1. **索引模块的代码里不得出现任何 `BS-*` / `IS-*` / `IMP-*` 字面量**。`row_code` 一律 `getattr(spec, "row_code")` 从既有 per-cycle 声明取。写死一个就是双真源，而两侧各自的单测都会全绿（各用自己的常量构造样本）。
2. **金额一律走 `ReportFormulaParser`**。自己聚合科目会引入第二个金额口径，审计师会在报表页看到一个数、在裁剪建议里看到另一个数。
3. **非 `resolved` 态的金额恒 `None`，绝不为 `0`**。编造 0 会让该程序被误判成「低于任何阈值」而产生裁剪建议，正确结论是「该维度对它不可用」。
4. **不改 `decideTrim` 的 9 档顺序与短路语义**。新增的 `amountSource` / `reportLine` 只进 `evidence`，九档条件表达式一律不引用它们（有源码级守卫）。
5. **`_load_accounts` 等既有五个维度逐字不动**。它们有三个现存消费方（档 4 数据存在性 / 复核视图金额未知统计 / `resolveAccountName`），改结构会三处同时波及。

### Wave 1 守卫的断言分两类（防「全红分不清是功能未做还是守卫写坏」）

- **类 A = 独立口径判据**（守卫自己算出的事实：`report_config` 真实行、per-cycle 声明的实际取值、真实库 `wp_code` 的 distinct 形态、改造前的冻结基线）—— **现在就应全绿**，绿了才证明判据基础设施有效而非空转。
- **类 B = 被测实现**（新模块存在且导出约定接口、行为与类 A 口径一致）—— **现在应全红**，失败消息须写明「尚未实现（Task N）。本条红是预期的 Wave 1 打红结果」。
- 禁在模块顶层 import 生产模块（顶层 import 失败会让整个文件 collection error、零断言执行，那时"全红"既可能是功能没做也可能是守卫写坏）；改为测试内 try-import 后 `pytest.fail`（不是 skip）。

## Task Dependency Graph

W1 三个守卫互不依赖可并行；W5 前端三任务依赖 W4 下发的新键，但在新键缺失时须表现为「退回科目名兜底」（守卫覆盖该态）⇒ 前端可与 W4 并行开发、但验收须在 W4 之后。

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "判据先行（必须先打红）",
      "depends_on": [],
      "tasks": ["1", "2", "3"],
      "parallel": true
    },
    {
      "wave": 2,
      "name": "跨循环索引",
      "depends_on": [1],
      "tasks": ["4"]
    },
    {
      "wave": 3,
      "name": "报表行金额解析",
      "depends_on": [2],
      "tasks": ["5", "6"]
    },
    {
      "wave": 4,
      "name": "判据上下文接线与零回归",
      "depends_on": [3],
      "tasks": ["7", "8"]
    },
    {
      "wave": 5,
      "name": "前端优先级与溯源",
      "depends_on": [4],
      "tasks": ["9", "10", "11", "12"]
    },
    {
      "wave": 6,
      "name": "守卫收口与验收",
      "depends_on": [4, 5],
      "tasks": ["13", "14", "15", "16"]
    }
  ],
  "notes": [
    "Task 1/2/3 三个守卫必须在 Wave 2 之前完成并打红；类 A 部分现在就应全绿。",
    "Task 4（索引）是 Task 5（金额）的硬依赖 —— 后者消费 ReportLineRef。",
    "Task 8（零回归）必须与 Task 7 同一轮完成：既有七键逐字节比对要在改动落地后立即验。",
    "Task 9~12 在 Wave 4 未下发新键时须表现为退回科目名兜底，该态由 Task 3 守卫覆盖。",
    "Task 13（变异）须在 Task 4~12 全部落地后；Task 16（浏览器实测）须在变异全 RED 之后。"
  ]
}
```

## Tasks

- [x] 1. Wave 1 守卫先打红：跨循环索引的零字面量与交叉锁死
  - 新建 `backend/tests/procedure_trim/test_report_line_index.py`
  - **类 A（现在应全绿）**：逐个 import `four_table` 的 11 个 per-cycle 模块并读出各自 `row_code` 实际取值，冻结成本轮基线（供 Task 4 交叉比对）；`report_config` 连库查这批 `row_code` 全部存在（`is_deleted = false`）；真实库 `procedure_instances.wp_code` 的 distinct 形态清单（含 `D2-1至D2-4` / `E1-14至E1-15` 这类区间型）
  - **类 B（现在应全红）**：`report_line_index` 模块存在且导出 `ReportLineRef` / `resolve_report_line_ref` / `normalize_wp_code` / `indexed_wp_codes` / `NON_BALANCE_DRIVEN_CYCLES`；索引代码剥注释后**零** `BS-\d+`/`IS-\d+`/`IMP-\d+` 字面量；A/B/C/S 返 `REF_NON_BALANCE_DRIVEN` 而 D~N 未登记码返 `REF_NO_REPORT_LINE`（两态可区分）
  - **反向自检**：剥注释 helper 必须能被「docstring 里写了 `BS-002`」骗过前后表现不同（raw 侧命中数 > clean 侧），否则零字面量判据是空转
  - 剥注释一律 `tokenize` 剥 `#` + AST 剥 docstring，**保留普通字符串字面量**（否则查不到真正写死的码）
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7, 7.1_

- [x] 2. Wave 1 守卫先打红：金额四态与不兜 0
  - 新建 `backend/tests/procedure_trim/test_trim_report_line_amounts.py`
  - **类 A（现在应全绿）**：`ReportFormulaParser` 的 `execute` / `extract_account_codes` / `extract_row_refs` 三个方法存在且签名可调用（读源码断言，不实例化）；`report_config` 里 `BS-002` 四个变体的 `formula` 逐字相同（本 spec 的 E 循环基准）；`BS-006` 在 `listed_consolidated` 与 `listed_standalone` 下 `formula` **不同**（准则维度真实存在的证据）
  - **类 B（现在应全红）**：`trim_report_line_amounts` 模块存在且导出 `ReportLineAmount` / `resolve_trim_report_line_amounts` + 四个状态常量；四态取值域恰为四个；非 `resolved` 态 `amount` 为 `None`
  - **反向自检**：构造一个「状态非 resolved 而 amount = 0.0」的样本，四态判据必须打红（证明它查的是 `None` 而不是 falsy）
  - _Requirements: 4.1, 4.2, 4.3, 7.1_

- [x] 3. Wave 1 守卫先打红：前端优先级与决策内核中立性
  - 新建 `audit-platform/frontend/src/views/__tests__/trimAmountSourcePriority.spec.ts` 与 `.../composables/__tests__/trimDecisionAmountSourceNeutrality.spec.ts`
  - **类 A（现在应全绿）**：冻结 `resolveAccountName` 的当前实现（函数体 md5 + 行为快照），Task 10 之后必须逐字不变；冻结 `decideTrim` 的 9 档条件表达式清单（源码级抽取 `if` 条件），Task 11 之后档位数与顺序必须相同；`subjectPrefixOf` 的归一正则字面量（供与后端 `normalize_wp_code` 交叉锁死）
  - **类 B（现在应全红）**：`resolveAccountAmount` 存在且返回 `{amount, source, reportLine, accountName, divergence}`；`TrimDecisionInput` / `TrimEvidence` 含 `amountSource` / `reportLine`；**`decideTrim` 函数体内 `amountSource` / `reportLine` 只允许出现在 `buildEvidence` 调用链**（九档条件不得引用）；复核视图无第二个取金额实现
  - 前端读 `.vue` / `.ts` 源码前必 `stripComments()` + 一条反向自检（raw 命中 > clean 命中）
  - _Requirements: 5.4, 6.2, 6.3, 7.1_

- [x] 4. 跨循环索引 `report_line_index.py`
  - 新建 `backend/app/services/four_table/report_line_index.py`：`ReportLineRef` dataclass（`wp_code` / `row_code` / `status` / `source_symbol` / `reason`）+ `normalize_wp_code()` + `resolve_report_line_ref(wp_code, applicable_standards=None)` + `indexed_wp_codes()` + `NON_BALANCE_DRIVEN_CYCLES = frozenset({"A","B","C","S"})`
  - dispatch 表按循环字母分发到既有件，**每个分支只取值不判断**：D/F/G/L/M/N → 各自 `spec_of(code).row_code`；E → `e_cycle_specs.E1_REPORT_ROW_CODE`；H → `h{n}_account_scope.H{n}_ACCOUNT_SPEC.row_code`；I → `i_cycle_accounts.resolve_row_code(code, standards)`；J → `j_cycle_account_scope.pick_spec(J{n}_SPEC_BY_ENTITY, standards).row_code`；K → `k_cycle_specs.get_k_cycle_spec(code)` 的 `row_code_soe`/`row_code_listed`
  - `source_symbol` 必填（形如 `d_cycle_specs.D2_SPEC.row_code`）—— 它既是溯源也是守卫交叉锁死的锚
  - `normalize_wp_code`：取首个「字母段 + 数字段」（`D2-1至D2-4` → `D2`），与前端 `subjectPrefixOf` 的 `/^([A-Z]+\d+)/` 同语义
  - **模块代码零 `row_code` 字面量**；A/B/C/S 返 `REF_NON_BALANCE_DRIVEN`（不适用，非失败）；D~N 未登记码返 `REF_NO_REPORT_LINE` + reason 写明是哪个循环的哪个码
  - 跑 Task 1 守卫：类 B 转绿、类 A 保持绿、交叉锁死逐个相等
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7_

- [x] 5. 报表行金额解析 `trim_report_line_amounts.py`
  - 新建 `backend/app/services/trim_report_line_amounts.py`：`ReportLineAmount` dataclass + 四个状态常量 + `resolve_trim_report_line_amounts(db, project_id, year, wp_codes)`
  - 准则取值走项目既有字段；未设置 → 全部 `AMOUNT_STANDARD_UNSET`（**不默认取某变体**）
  - `report_config` **一次批量查回**（按 `(row_code, applicable_standard)` IN 列表），不逐 wp_code 发查询
  - `ReportFormulaParser` **每项目只建一个实例**（内部 `_tb_cache` / `_tb_prefix_cache` 复用即天然批量）
  - 公式含 `ROW()`（判据 `parser.extract_row_refs(formula)` 非空）→ `AMOUNT_FORMULA_UNAVAILABLE`，**不传伪造 `row_cache` 凑值**
  - `standard_codes` 取 `parser.extract_account_codes(formula)`
  - 求值异常 → **ERROR 级日志**（不是 WARNING）+ `AMOUNT_FORMULA_UNAVAILABLE`；日志含 wp_code / row_code / formula
  - **不引用 `SemanticAccountSpec` 的 slot 结构**：实证多槽规格下报表公式兜底会把整行金额分配给某槽，E1 曾因此把 `1002`/`1012` 算两遍（8,935,072.24 vs 真值 4,467,536.12，虚增一倍）
  - 跑 Task 2 守卫：类 B 转绿
  - _Requirements: 2.1, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4_

- [x] 6. 连库独立算术复核：前缀聚合 / 区间 / 符号
  - 在 `test_trim_report_line_amounts.py` 追加连库判据组（专用 `NullPool` engine + 同 loop `dispose()`）
  - **前缀聚合**：构造或选取同时有 `1231` 与 `1231-03` 的真实项目，断言 `TB('1231')` 结果含子科目（与直接 SQL `LIKE '1231%'` 聚合相等）
  - **符号运算**：对 `BS-006` 的 `listed_standalone` 公式（`TB('1122') - TB('1231')`）断言结果等于两项按符号加权和，且**不等于**两项绝对值之和（后者是最常见的实现错误）
  - **区间语义**：对 `IS-001` 的 `SUM_TB('6001~6099')` 断言覆盖区间内全部科目
  - **索引 row_code 存在性**：`indexed_wp_codes()` 的每个 `row_code` 在 `report_config` 至少一行
  - 判据一律「真跑一次并把异常记 ERROR 态」，反向自检要「故意写错必失败」—— 本平台已实证 `except Exception` 会把函数名/列名拼错吞成「本项目无此数据」
  - _Requirements: 1.5, 2.2, 2.3, 2.4_

- [x] 7. 判据上下文 additive 第八维
  - `backend/app/services/trim_decision_context.py`：新增 `DIM_REPORT_LINE = "report_line"` 进 `DEGRADATION_DIMENSIONS`；`_RESULT_KEYS` 加 `report_line_amounts`；新增 `_load_report_line_amounts(db, project_id, year, cycles)`
  - 目标 wp_code 清单复用 `_collect_probe_wp_codes()`（与底稿录入探测同一口径，**不新建第二套目标集**）
  - 整体取数失败 → `{}` + 一条 degradation（前端据此退回科目名兜底并标注）；单个 wp_code 失败不影响其余
  - **既有七键逐字不动**；`build_trim_decision_context` 返回值从七键变八键（additive）
  - 新建 `backend/tests/procedure_trim/test_trim_context_report_line_wiring.py`：第八键存在性 + 既有七键零回归 + degradation 维度取值域 + 目标集与 `_collect_probe_wp_codes` 同源（源码级断言无第二个目标集查询）
  - _Requirements: 4.5, 5.5_

- [x] 8. 零回归验证（前后对照，禁用 HEAD-swap）
  - 既有五个维度（`accounts` / `materiality` / `risk` / `completeness_override` / `workpaper_entry`）的输出与改造前**逐字节相同**
  - `decideTrim` 在 `amountSource` / `reportLine` 缺省时输出与改造前逐字相同（characterization，构造输入）
  - `decideTrim` 的档位数量与顺序不变（复用 Task 3 冻结的 9 档条件清单）
  - `backend/tests/procedure_trim/` 全目录基线 **328 passed / 1 skipped**（2026-08-12 实测），改造后新增例数应**恰等于**新守卫例数
  - 前端 `ProcedureTrimming.vue` 的既有守卫（`trimDecisionWiring` / `trimAdequacyReview` / `completenessScopeOverride` 等）零新增失败
  - 零回归判据用「施加改动前 vs 施加改动后」前后对照；**禁用「把改动文件换成 `git show HEAD:` 版跑同一组」**（本仓库并发度高，HEAD 侧可能含他人未提交成果，且被 Ctrl+C 打断时 HEAD 版会留在工作树）
  - _Requirements: 5.3, 5.5, 5.6_

- [x] 9. 前端类型与 API additive
  - `audit-platform/frontend/src/services/commonApi.ts`：新增 `TrimReportLineAmount` 接口；`TrimDecisionContext` 加 `report_line_amounts`
  - `fetchTrimDecisionContext` 解析新键，缺失时为 `{}`（**不是 `undefined`**，避免调用方各自兜底）
  - 既有七键的解析逻辑逐字不动（含 `materiality` 不套 `asObj` 兜底这条既有约定）
  - _Requirements: 5.5_

- [x] 10. `resolveAccountAmount()` 优先级与兜底
  - `ProcedureTrimming.vue` 新增 `resolveAccountAmount(p, ctx)` → `{amount, source, reportLine, accountName, divergence}`，它是 `buildAndDecide` 取金额的**唯一入口**
  - 报表行 `status === 'resolved'` 且 `amount` 为有限数 → `source = 'report_line'`；否则退回 `resolveAccountName()` → `source = 'account_name'`；两者都未命中 → `amount = null`（与改造前同）
  - 两者都命中且金额不等 → 采用报表行值并填 `divergence`（记两个数，供溯源）
  - **`resolveAccountName` 逐字不动**（Task 3 已冻结其函数体 md5）—— 它仍是科目名兜底的唯一实现，也仍供复核视图定位科目名
  - 跑 Task 3 守卫：优先级、兜底保留、divergence 三条转绿
  - _Requirements: 5.1, 5.2_

- [x] 11. 决策内核 additive（只进 evidence，不参与判断）
  - `procedureTrimDecision.ts`：`TrimDecisionInput` 与 `TrimEvidence` additive 加 `amountSource` / `reportLine`
  - `buildEvidence` 把两者写进 evidence；**九档条件表达式一律不引用它们**
  - 单测：缺省时输出与改造前逐字相同；传入不同 `amountSource` 时 `verdict` / `reasonCode` / `narrative` 完全不变（只有 evidence 变）
  - _Requirements: 5.4, 6.1, 6.4_

- [x] 12. 溯源展示（复用既有机制，不新建第二套）
  - 建议列 tooltip 与确认后写入 `skip_reason` 的规范文本追加「取自报表行 {row_code} {row_name}（{formula}）」
  - 兜底来源显式标注：`source === 'account_name'` 时建议列渲染「科目名匹配」标记（`source === 'report_line'` 时不渲染），使复核者知道该金额可靠性较低
  - 裁剪充分性复核视图改读 `resolveAccountAmount()` 同一函数（源码级断言无第二个取金额实现）
  - 报表行信息落既有 `TrimEvidence`，**不另开溯源字段**
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 13. 变异检验
  - 新建 `backend/scripts/check/mutate_report_line_resolution_guards.py`，至少 10 个变异逐条必须 RED：
    ①索引写死一个 `row_code` 字面量 ②索引改取另一循环的 spec ③归一正则去掉数字段 ④A/B/C/S 从不适用改成无落点 ⑤非 resolved 态 `amount` 从 `None` 改 `0.0` ⑥含 `ROW()` 改为传空 `row_cache` 强行求值 ⑦求值异常从 ERROR 降 WARNING ⑧前端优先级反转（科目名优先） ⑨`decideTrim` 某档条件引用 `amountSource` ⑩复核视图另算一份金额
  - **判据按失败测试名集合求差集**（不看退出码），并区分三态：`new_fails` 非空 = RED 有效 / 空 = **守卫缺陷** / 某条基线红转绿 = 亦为有效信号
  - 锚点必须行级唯一且 `hits == 1`（多命中或零命中 = ANCHOR-MISS 脚本缺陷，不得当 GREEN 处理）
  - 备份落 `.bak` 并提供 `--restore`；`try/finally` 无条件写回；变异后以 md5 核验字节级还原
  - 锚点禁用跨行字面量（工作树多为 CRLF，含 `\n` 的锚点必 MISS）
  - _Requirements: 7.2_

- [x] 14. 真实库验收
  - 新建 `backend/scripts/diagnose/verify_report_line_amounts_live.py`（默认只读）
  - 遍历有 `procedure_instances` 的项目 × 各自准则变体，逐 wp_code 输出四态分布与索引 `status` 分布
  - 对 `resolved` 态做**独立算术复核**：另按 `extract_account_codes` 的标准码直接 SQL 聚合 `trial_balance`，与 `ReportFormulaParser` 结果比对（含减项公式的符号）
  - 覆盖不到的准则变体输出 `UNVERIFIABLE`，**不用构造数据冒充通过**
  - 连库用专用一次性 engine（`poolclass=NullPool`）+ 同 loop `dispose()`，不借共享连接池
  - 中文输出前设 `PYTHONIOENCODING=utf-8`，或直接写盘不 print
  - _Requirements: 7.3_

- [x] 15. CI job
  - `.github/workflows/governance-checks.yml` 新增两个 job：`report-line-account-resolution`（后端守卫 + 变异脚本）与 `report-line-account-resolution-frontend`（前端两个守卫）
  - 加挂前用 `yaml.safe_load` 验证可解析并核对 job 名无重名（平台曾出现同名 job 被静默去重、前一个从未运行）
  - 引用的测试文件必须全部已存在（否则 CI 红）
  - _Requirements: 7.5_

- [x] 16. 浏览器实测与数据复原
  - **E 循环是本 spec 的立项缺陷现场**，必须实测：切到 E 循环跑智能裁剪 → 建议列出现重要性类理由码；建议金额与 `report_config` 的 `BS-002` 公式独立计算结果一致（`1001 + 1002 + 1012` 的 `trial_balance` 聚合）；溯源可见报表行编码与公式原文
  - 顺带验兜底标记：找一个无报表行落点的 wp_code，确认建议列显示「科目名匹配」
  - 实测前抓基线、实测后复原并以**独立查询**核实（复用 `backend/scripts/e2e/trim_e2e_baseline.py`，它已收六个域并经三次真实写入→复原验证）
  - ⚠️ **委派预览会同步物化行任务**（已实证 `procedure_row_tasks` 3 → 27），本 spec 实测不涉及委派故不应触发；若触发须如实登记漂移
  - ⚠️ **交叉核实查询必须与基线工具同口径**（如 `disclosure_notes` 要带 `is_deleted = false`），否则交叉核实自己会造假漂移
  - 实测中若发现只有浏览器能暴露的缺陷（传了不存在的 prop、宿主漏传参数、命名导出缺失、按钮文案与源码不一致），一并修复并补守卫
  - _Requirements: 7.4, 7.6_

## Notes

### 与并发 spec 的边界

- **`e-cycle-extraction-formula-and-disclosure-completion`**：本 spec 只**读** `e_cycle_specs.E1_REPORT_ROW_CODE`，不改该模块。若届时该 spec 正在改 E 循环 spec 常量，Task 1 的交叉锁死守卫会自动跟随（这正是「索引零字面量」的目的）。
- **`i-cycle` / `k-cycle` / `l-cycle` / `g7-column-alignment`**：同上，对它们的声明只读不写。落地前重查这几个 spec 是否正在改各自的 `row_code`（改了不影响正确性，但会让 Task 1 冻结的类 A 基线需要同步刷新）。
- **`report_config` 数据**：本 spec 不改。若 Task 14 验收发现错码，登记独立议题（范式见已归档的 `report-config-account-code-integrity`，它实证过全表 132 条 `TB()` 引用里有 16 行错码）。
- **`procedure-trimming-and-delegation-intelligence`**：已归档（26/26）。本 spec 是它的后继，改动集中在 `trim_decision_context.py` 与 `ProcedureTrimming.vue`。

### 已知不做（避免后续会话重复提议）

- **不改 `decideTrim` 的 9 档顺序**：D 循环 17 条程序因档 5 完整性豁免不产生金额类建议是**设计使然**（完整性方向的漏记与账面金额无关，用金额豁免它方向就是反的）。
- **不补 `resolveAccountName` 那个 docstring 承诺而未实现的第二匹配方向**：实证即便补上也救不了本例（程序名「货币资金 - 函证（Leap应对措施-函证）」不被科目名「其他货币资金」包含），且报表行映射一旦生效它就退居兜底。
- **不把金额解析搬到前端**：`report_config` 与 `trial_balance` 都在后端。
- **不为 `cash_flow_statement` / `equity_statement` 补 `TB()` 公式**：实证这两类 `report_config` 行无 `TB()` 引用，且它们不是科目余额驱动循环的对象。
- **不做报表行 → 明细科目的反向展开**：裁剪判据只需行级合计。
- **不扩展到委派侧**：委派的风险匹配走 B50 科目名，与本 spec 无关。

### 真实库现状事实（影响验收判据，落地前必读）

以下来自 `procedure-trimming-and-delegation-intelligence` Task 26 的实测（2026-08-12）：

- **实测项目** `2aa00f57-1df4-4fe8-9840-2d65d0fd8749`（重庆和平药房_2025 / soe）：`procedure_instances` 61 条（B 39 / D 17 / E 5）· `trial_balance` 58 行（54 非零）· `materiality` 1 行（`performance_materiality = 26,104,487` / `trivial_threshold = 2,610,448.70`）· `tb_balance` 1176 行
- **E 循环 5 条程序名全部是「货币资金 …」**，而 `trial_balance` 无「货币资金」行、只有「其他货币资金」(1012, 8,280,881.84) 与「银行存款」(1002, 327,095.20) ⇒ 本 spec 改造后这 5 条的金额应为 `1001 + 1002 + 1012` 的合计（该项目无 1001 库存现金，故 = 8,607,977.04）
- **`checklist_responses` 全库 `B50-T3-*` 0 行** ⇒ 风险维度恒降级，这是真实状态而非缺陷；本 spec 的实测不依赖 B50
- **D 循环 accounts 经 `cycle_for_account` 过滤后只有 4 个科目**（应收账款 / 营业收入 / 预收账款 / 坏账准备-应收账款）—— 注意这是 `_load_accounts` 的科目名口径，与本 spec 的报表行口径**不同源**，两者并存是设计如此
- **`procedure_row_tasks` 27 行**（含 Task 26 实测时委派预览同步物化的 24 行，已固化为新基线）

---

## 落地记录（2026-08-15，16/16 交付）

### 立项缺陷已修复（浏览器实测证实）

实测项目 `2aa00f57-1df4-4fe8-9840-2d65d0fd8749`（重庆和平药房_2025 / soe_standalone）：

- E 循环改造前 **0 条**金额类建议 → 现在 **4 条**「金额低于实际执行重要性」
- 金额 **8,607,977.04**（= `1001 + 1002 + 1012` 的 `trial_balance` 聚合，独立 SQL 复核一致）
- 溯源完整：`…（取自报表行 BS-002 货币资金（TB('1001','期末余额') + TB('1002','期末余额') + TB('1012','期末余额')））`
- 兜底标记门控双向验证：`report_line` → 0 个标记；翻成 `account_name` → 恰 1 个出现在那一行
- 零漂移：基线工具 `--verify` 差异 0 项 + 独立同口径交叉核实 6 域全一致
  （`procedure_instances` 61/61 · trimmed 0/0 · skip_reason 0/0 · suggestion_state 0/0 ·
  `row_tasks` 42/42 · `B50-T3-cscope-*` 0/0）

### 与 design 的三处偏离（均有论证）

1. **`resolveAccountAmount` 放独立纯函数模块** `composables/trimAmountSource.ts`，
   而非 design 写的「`ProcedureTrimming.vue` 内新增」。理由：R6.2 要求「两处逐项相等」，
   定义在 `<script setup>` 内部的函数 vitest 无法 import，只能做源码级断言（"两处都写了
   这个函数名"），而那**证明不了两处结果相等**。抽成纯函数后可喂同一入参断言逐项相等。
2. **H 循环走 `h_cycle_specs.H_CYCLE_SPECS`**，而非逐个 import 十个
   `h{n}_account_scope.H{n}_ACCOUNT_SPEC`。前者是后者的汇总注册表
   （`H_CYCLE_SPECS["H1"] is H1_ACCOUNT_SPEC`），同一真源、少十行重复。
3. **K 循环准则选择复用 `KCycleSpec.spec_for(standards).row_code`**（既有件），
   而非 design 写的直接读 `row_code_soe`/`row_code_listed` 两字段 —— 复用既有件才符合
   R3.2「不另写一套准则判断」。

### 实现判定：两组准则字段分叉时宁缺勿造（design 未预见）

平台有**两组**准则字段且真实库已分叉：

- `projects.applicable_standard_v2`（结构化，权威真源）
- `projects.template_type` + `report_scope`（旧字段，**报表页实际用的就是这组**，
  见 `report_config_service.resolve_applicable_standard`，缺失时兜底 `soe_standalone`）

实测 32 个项目：24 两组都未设 / 7 一致 / **1 分叉**（`0ec33ac9` 重药控股安徽，331 条程序，
`v2=soe_standalone` 而 `template_type=listed`）。

判定（写进 `trim_report_line_amounts` docstring）：两组一致 → 按该准则出数（与报表页同口径）/
`v2` 有而旧字段缺 → 按 `v2` / **两组分叉 → `standard_unset` + ERROR 日志** /
`v2` 未设 → `standard_unset` / 组合不在 `report_config` → `standard_unset`。
**不新增第五态**（R4.1 钉死四态）。

理由：报表页必须出一张报表所以它兜底，而裁剪判据是**自动裁掉审计程序**的依据 ——
用一个说不清的准则算出的金额去裁程序，风险远高于报表上显示一个可能不准的数。

⚠️ 连带影响：`derive_applicable_standards` **永不为空**（无法推断时补 `DEFAULT_STANDARD`），
故 R3.3 的「准则未设置」**不能**靠它判，必须直读 `applicable_standard_v2`。已有类 A 判据钉死。

### 浏览器实测暴露并已修的缺陷：汇总闸重复计入

`evaluateAggregateGate` 按 `accountName` 去重（语义 = 同一笔余额只算一次错报敞口），
但报表行映射生效后该键退化成 `wp_code` ⇒ E 循环 4 条程序落同一报表行
（同一笔 8,607,977.04）被算成 4 个科目 **34,431,908.16（虚高 4 倍）**
⇒ 超过实际执行重要性 26,104,487.00 ⇒ **过度阻断批量确认**。

改造前该缺陷被数据掩盖：科目名解析不出时金额也是 `null`（计 0），合计恒 0、闸门不亮。

修法：新增 `aggregateGateKey(evidence, accountName, wpCode)`（报表行 → 科目名 → 底稿编号
退化），`suggestedGateItems` 改走它。浏览器复验：「1 个科目 / 8,607,977.04 / 可批量确认」。
补 5 条守卫含反向自检（旧去重键必须复现虚高 4 倍与误触闸门）。

### 复盘补齐

- **删死代码** `traceArgsOf`（零消费方；宿主拼溯源时手上只有 `TrimEvidence`，走的是直接
  构造扁平参数那条路）
- **新建常驻 CI 接线守卫** `backend/tests/procedure_trim/test_report_line_ci_wiring.py`
  （12 条）：Task 15 原用一次性脚本校验，导致 **Property 22 无常驻判据** —— 将来改坏
  workflow（重名 job 被 yaml 静默去重、门控 PATTERN 写坏致 job 恒跳过、引用未入库的测试）
  都不会被发现而 CI 一片绿。含内存内变异自检（不对共享热点 yml 做磁盘变异）。
- 复盘扫描全部新增导出符号的消费方：**死代码 0 个**；22 个 Property **全部**有守卫引用。

### 验证汇总

| 项 | 结果 |
|---|---|
| 后端 `procedure_trim` 全目录 | 419 passed / 1 failed（既有无关）/ 3 skipped |
| 前端 10 个相关守卫文件 | 360 passed |
| 变异检验 | **17/17 RED**，每条命中的正是预期判据；还原 md5 一致、`.bak` 零残留 |
| 真实库验收 | **PASS**，36 项独立算术复核全一致 |
| 准则变体覆盖 | `soe_standalone` VERIFIED；`listed_*` / `soe_consolidated` **UNVERIFIABLE**（库中无该变体项目，不用构造数据冒充） |

那 1 条既有 failed = `test_task23_zero_regression::test_linkage_module_is_new_not_a_rewrite`，
判据是 `_git_show(procedure_trim_note_linkage.py) is None` 而该文件已进 HEAD（396 行），
只读 HEAD 不依赖工作树 ⇒ **与本 spec 结构上无关**（另一 spec 收口遗留的自失效 HEAD-swap 守卫）。

### 发现的既有问题（非本 spec 引入，登记独立议题）

1. **HEAD 曾不自洽**：已 commit 的 `procedureTrimDecision.ts` import 的
   `completenessExemption.ts`（连同 `b50Completeness.ts`）在 HEAD 中不存在，
   归属 `procedure-trimming-and-delegation-intelligence`（标记 26/26 但从未入库）。
   后果是干净 checkout 下本 spec 与既有 `procedure-trim-intelligence-frontend` job
   **都会挂**。→ 本轮已连同各自配套测试一并入库（39 条测试全绿），HEAD 自洽性恢复；
   CI 依赖闭包复查 **160 个文件 / 0 个未跟踪**。
2. **`BS-055` 跨准则同码异义**：listed 侧行名「应付股利」/ soe 侧「短期借款」，
   `m_cycle_specs.M1` 指向它 ⇒ 国企项目行名不符。但两变体 `formula` 均为 `None`
   ⇒ 本 spec 返 `formula_unavailable`、**不出数**（验收脚本分级 LOW）。
3. **J1/J2 声明的 row_code 与循环语义不符**：`BS-051` 实为持有待售负债、
   `BS-069` 实为非流动负债合计且公式全 `ROW()`。索引如实跟随声明（这正是零字面量的
   设计目的）；soe 侧由 Property 9 的 `ROW()` 拒解析接住，listed 侧由 `row_name` 溯源
   让审计师看见行名不符。行名比对判为「无法判断」（`ReportLineAccountSpec` 无科目名字段）。
4. **项目准则字段分叉**：`0ec33ac9`（331 条程序）报表行取数整体不可用。

### 会话内新登记的坑（已写进各文件注释）

- **前端 vitest 里 `await import('字面量')` 会被 Vite 的 `vite:import-analysis` 在转换期
  解析**，模块不存在 → 整文件 collection error + `Tests no tests`（零断言执行，Wave 1 的
  分类价值全丢）。解法：说明符存变量 + `/* @vite-ignore */`。
- **`fs_append` 的内容可能被并发会话的完整重写覆盖**：本轮实测 `governance-checks.yml`
  在 append 后 85 秒内被另一会话整段重写。⇒ 加挂后必须**立即**用不依赖行号的归因型判据
  复验（基线 job 名集合 ⊆ 当前集合 + 新增恰为我的两个）。
- **PowerShell 的 `Measure-Object -Line` 不计空行**：据它取的"行数"会让字节区间切片错位，
  归因型判据必须避开行号。
- **交叉核实自己会造假漂移**：本轮两次踩到（漏 `is_deleted = false` 过滤；快照键名写错
  `procedure_row_tasks` 而实际是 `row_tasks`）⇒ 交叉核实必须与基线工具**同口径**，
  且核实脚本本身也要复核。
