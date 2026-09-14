# Implementation Plan: 公式管理运行层闭环

## Overview

按用户 2026-08-06 明确要求「按 6 个建议逐一修复」立项，requirements 已细化为 **10 个 R**。
**Wave 顺序不是随意的**：W1（`useFormulaStatus` 三处错配）修完才有观察窗口，
W2（未注册列名 48 格数字错）优先于死链，W3（存储收敛）是 W4（三类型有活数据）的前置。

**范围外**（design.md §范围外 已登记）：`WP()`/`PREV()` 死链本体修复（归
`prefill-wp-prev-resolution-repair`，本 spec 只做一致性守卫）· `formula.py::/execute`
改叶子聚合口径（只加告警，R7.5）· 18 个循环级 `tb_data` 局部构造点 · 6 个
`gN/hN/validate-formulas` URL 收敛 · 跨年度 `PREV()` 数据模型变更。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2", "3"], "note": "R1+R2 端点错配与面板展示（零风险，先建立观察窗口）" },
    { "wave": 2, "tasks": ["4", "5", "6", "7"], "note": "R3 未注册列名 48 格数字错（曾落盘被回退，需重做）" },
    { "wave": 3, "tasks": ["8", "9"], "note": "R4 两套公式存储收敛（0 行 = 零迁移压力）" },
    { "wave": 4, "tasks": ["10", "11", "12"], "note": "R6 三类型执行链接通与定性（依赖 W3 有活数据）" },
    { "wave": 5, "tasks": ["13", "14", "15"], "note": "R5 WP 双实现锁死 · R7 端点收敛与口径告警" },
    { "wave": 6, "tasks": ["16", "17", "18"], "note": "R8~R10 不可回退守卫 + 零回归 + 真实库验收" }
  ]
}
```

## Tasks

### Wave 1 — `useFormulaStatus` 孤儿处置与面板展示

> 🔴🔴 **立项前提已被实证推翻（2026-08-06，本会话）**：requirements R1 把
> 「`useFormulaStatus` 两个端点都不存在」当**活的 P0**，实测它是**零消费方孤儿** ——
> 全仓（排除 `__tests__` 与 `components.d.ts`）import `useFormulaStatus` 的文件 **0 个**；
> 而真正在用的 `FormulaStatusPanel.vue` **压根不 import 它**（命中 0），自己请求的是
> **正确**端点 `/api/workpapers/${props.wpId}/formulas` 且读的就是 `items`（17 处），
> 其 docstring 明写「Task 4.1：修正端点错配」= 该缺陷已由 spec
> `d-cycle-four-table-extraction-formulas` 修完。
> ⇒ 那两个坏端点是**死代码里的陷阱**，用户不可达；R1 的「面板恒空」不成立。
> 同族孤儿：`FormulaTooltip.vue`(0) / `FormulaSourceDrawer.vue`(0)，与它同批建、同批孤儿。

- [x] 1. `useFormulaStatus.ts` 孤儿三选一处置（**删 / 接 / 豁免**，按 memory 铁律）
  - **先复核孤儿判据**（判据 = import 路径，禁符号级匹配）：全仓 `.ts`/`.vue`
    （排除 `__tests__`、`components.d.ts`）grep `useFormulaStatus`，确认消费方仍为 0
  - **默认处置 = 删除**（连同同批孤儿 `FormulaTooltip.vue` / `FormulaSourceDrawer.vue`
    一并核，各自单独判定）：理由 —— 它与 `FormulaStatusPanel.vue` 是**双真源**
    （同一面板语义两份实现），接线即造第二套；而它持有的两个坏端点是陷阱
  - **若判定保留**（如另有 spec 声明要接线）THEN 必须①修正两个端点与响应键
    ②置 `loadError` ③在文件头登记「零消费方 + 保留理由 + 归属 spec」，三者缺一不许保留
  - **禁止**为了让 Property 1~3 转绿而给孤儿"修 URL 后留着" —— 那是给下个会话
    留一份「看起来已修好」的双真源
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 2. `FormulaStatusPanel.vue` 展示 issue / hint / 计算时间 / 中文类型
  - 文件在 **`components/workpaper/FormulaStatusPanel.vue`**（🔴 不在 `components/formula/`，
    实证前者 exists=True、后者 exists=False）
  - 渲染 `issue_description`（有值时红色 tag + tooltip）、`hint_text`（琥珀色提示条）、
    `last_computed_at`（相对时间 + tooltip 绝对时间，空时显示「未计算」）、`refs` 数量可展开
  - `formula_type` 由裸英文改中文标签，真源 **复用**
    `components/workpaper/composables/formulaEngineInventory.ts` 的 `FORMULA_TYPE_LABEL`
    （禁本文件内自建 `Record<FormulaType,string>` 字面量）
  - 无 issue 且无 hint 时不渲染空容器
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

- [x] 3. Wave 1 守卫（**平台级端点存在性 + 面板展示**，判据落在活代码上）
  - **新建平台级守卫** `composables/__tests__/formulaEndpointExistence.spec.ts`：
    扫 `components/formula/**` + `components/workpaper/Formula*.vue` +
    `composables/useFormula*.ts` 里所有 `/api/...formula...` URL，去掉 `${...}` 插值后
    **交叉锁死**「⊆ 后端真实注册路由」（`fs.readFileSync` 读 `backend/app/routers/*.py`
    抽 `@router.{get,put,post,delete}` 装饰器 + `prefix`）；
    未命中即打红 —— 这条守卫是**缺陷 1 那类错配的根治**，比只钉一个孤儿有价值
  - **反向自检**：注入一个替身 URL `/api/workpapers/{id}/formulas-NOPE` 必须打红；
    且断言「抽到的后端路由数 > 0」防解析器失效空转
  - `FormulaStatusPanel.spec.ts`：四字段（`issue_description`/`hint_text`/
    `last_computed_at`/中文 `formula_type`）渲染断言 + `FORMULA_TYPE_LABEL` 复用断言
    （源码级禁自建 `Record<FormulaType,string>` 字面量）
  - **孤儿基线**：若 Task 1 判定删除 THEN 断言 `useFormulaStatus.ts` 不存在；
    若判定保留 THEN 登记进孤儿基线（含 owner + 理由，条目数只许减少）
  - **变异检验**：①注入不存在的端点 ②删中文标签映射改自建表 ③删 `issue_description`
    渲染 —— 逐一必须打红；变异按「失败测试名集合差集」判定（不看 exit code），
    备份落 `.bak`、还原在 `finally`
  - _Requirements: 2.6, 8.3, 8.4, 8.5, 8.6_

### Wave 2 — 未注册列名与静默回退（48 格数字错，**曾落盘被回退需重做**）

> 🔴 **本 Wave 曾被交付后回退**：`tmp_verify_engine_out.txt` 记录过 len=60183 / 15 键 /
> 有 `_resolve_tb_column` 的状态，而磁盘真相是 len=**58166** / **8 键** / 两处静默回退仍在。
> 开工前先跑 `_wip_fmc_truth.py` 确认当前磁盘状态，别信任何过期产物。

- [x] 4. `COLUMN_ALIASES` 注册四个发生额列名（规范名 = 共享件 `DEBIT_KEY`/`CREDIT_KEY`）
  - 新增 `本期借方`/`借方发生额` → **`本期借方`**、`本期贷方`/`贷方发生额` → **`本期贷方`**
  - 🔴 **规范名必须是 `本期借方`/`本期贷方`，不是 `借方发生额`** —— 已交付共享件
    `four_table/occurrence_by_standard_code.py` 的 `DEBIT_KEY="本期借方"`，且
    `test_formula_column_alias_coverage.py::test_occurrence_keys_match_engine_standard_fields`
    断言 `DEBIT_KEY ∈ set(COLUMN_ALIASES.values())` ⇒ 写成 `借方发生额` 必打红
  - 既有 8 键的映射目标逐字不变（Property 22）
  - _Requirements: 3.1_

- [x] 5. 两条求值路径收敛到 `_resolve_tb_column`，静默回退改三态
  - `formula_engine.py` **L631**（`_handle_tb`，AST 路径）与 **L936**（`_execute_regex`，
    降级路径）**两处都改**，共用同一 helper（禁各写一份）
  - 三态：**未注册列名** → `None` + trace + 调用方记 `errors`；**已注册但无数据** →
    `Decimal("0")` + trace「该科目无此列」（诚实的 0，因 `aggregate_occurrence` 有意不产出
    零值键）；**正常** → 值
  - 「取不到」与「值确实为 0」必须可区分（前者进 errors）
  - _Requirements: 3.2, 3.3_

- [x] 6. 两个 `tb_data` 构造点补发生额键（复用已交付共享件）
  - **`app/routers/wp_template_files.py`**`::_get_tb_data_for_prefill`（🔴 在 `routers/`
    不在 `services/`，design 首版路径写错）
  - `app/services/formula_management/adjudication_writeback.py`（现 6 键）
  - 两者都 **复用** `four_table/occurrence_by_standard_code.aggregate_occurrence`
    （已含叶子聚合 + 最长前缀继承祖先映射 + fail-open），**禁各写一份 `tb_balance` 查询**
  - 无发生额数据时**显式不产出该键**（而非产出 0），使 R3.2 的「列缺失」语义成立
  - _Requirements: 3.5, 3.6_

- [x] 7. Wave 2 守卫（**扩充既有文件，不新建**）
  - 🔴 **复用 `backend/tests/test_formula_column_alias_coverage.py`**（h-cycle spec 已交付，
    12 例，当前已打红 48 格 + 2 处回退），**不要**新建
    `test_formula_column_alias_registration.py` —— 同一不变式两份守卫 = 双真源
  - 在该文件补：未注册列名格数 **== 0**（改造前 48，写进 docstring 作基线）、
    「列缺失」上下文求值 `errors` 非空且返回值 ≠ 期末余额、两处路径都已收敛
  - **变异检验**：①只改 AST 路径 ②只改 regex 路径 ③把规范名改成 `借方发生额`
    ④删共享件某键 —— 逐一必须打红
  - _Requirements: 3.4, 3.7, 8.1, 8.2, 8.4_

### Wave 3 — 两套公式存储收敛（0 行 = 零迁移压力）

- [x] 8. `user_formulas` 收敛进 `wp_formula` 表（**收敛不是双写**）
  - 🔴 **PUT/DELETE 不再写 `parsed_data['user_formulas']`** —— tasks 首版写「双写」与
    design 组件 3 / Property 9 打架；双写等于新造双真源，比现状更坏。R4 标题是「收敛」
  - 新增 `wp_formula_service.upsert_user_formula(db, *, wp_id, project_id, cell_key,
    expression, created_by)`：`cell_key`（`sheet!cell`）拆 `sheet_name` + `target_cell`，
    置 `formula_source='user'`，冲突键 `(project_id, wp_id, sheet_name, target_cell)`
    → 更新 expression + `definition_version += 1`
  - **GET 端点保留读兼容分支**（merge 旧 `parsed_data['user_formulas']`，旧键优先级低）；
    该分支必须有守卫钉死，否则下个会话当死代码删掉
  - 三个端点的**响应形状不变**（`cell_key` → formula 的 dict），前端零改动
  - `coordinator._load_formulas` 不改查询（已 `select(WpFormula)` 无 `formula_source` 过滤）
  - 实测 `wp_formula` 0 行 + `parsed_data ? user_formulas` 0 行 ⇒ **无存量迁移**；
    迁移脚本仍需存在且可空操作运行（R4.7）
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_

- [x] 9. Wave 3 守卫 + 遗留规模诊断
  - `backend/tests/test_user_formula_storage_convergence.py`：
    - 保存一条 user formula → `wp_formula` 出现对应行且 `formula_source='user'`
    - **源码级断言 PUT/DELETE 不含 `parsed_data["user_formulas"] =` 赋值形态**（Property 9）
    - GET 仍含读兼容分支
    - `cell_key` 拆列往返无损（PBT，Property 11）
    - upsert 幂等：同键连续两次只一行且 `definition_version` 递增（Property 12）
    - `_load_formulas` 查询不含 `formula_source` 过滤（Property 10）
  - 只读诊断脚本报告遗留 `parsed_data['user_formulas']` 规模（当前 0），守卫钉死只减不增
  - **变异检验**：①改回写 `parsed_data` ②删读兼容分支 ③`formula_source` 写成别的值
    ④给 `_load_formulas` 加 `formula_source` 过滤 —— 逐一必须打红
  - _Requirements: 4.6, 8.4, 8.5_

### Wave 4 — 三类型执行链接通与定性

- [x] 10. `logic_check` 结果落库 `cross_check_results`
  - `execute_report_cross_checks`（唯一有调用方的入口，挂
    `GET /api/projects/{pid}/formula/report-cross-check`）内把结果 upsert 进
    `cross_check_results`（同 `(project_id, year, rule_id)` 覆盖），fail-open + WARNING
  - `run_cross_checks` / `build_cross_check_formulas` 两个零调用方函数：查明是否为
    `execute_report_cross_checks` 的内部实现（若是则不算孤儿），否则接线或显式登记弃用理由
  - **待裁决**：`cross_check_results` 落库是否带 `year`（表有该列，需确认入参能否拿到）
  - _Requirements: 6.1, 6.2_

- [x] 11. `_load_formulas` 空结果可见化 + 三类型运行态定性 + 三张 0 行表登记
  - `generate_mutation_plan` 无公式时不再静默 early-return → `scope_failures` 追加
    `kind='no_formulas'` 条目；`draft_refresh.py` 透出到响应体，
    `GtRefreshScopeDialog.vue` 显示「本项目尚未定义任何公式」而非静默"成功"
  - `_exec_{auto_calc,logic_check,reasonability}` 与三个 `_batch_exec_*` 的 docstring 补
    「唯一调用方 = `coordinator.execute_batch`，依赖 `wp_formula`（实测 0 行）」+ 实测日期
  - 建 `FORMULA_TYPE_RUNTIME_STATUS` 真源（三类型 → `{执行入口, 调用方, 落库表, 实测状态}`）
  - 建 `formula_runtime_table_status.py`：`cross_check_results`（接线）/ `draft_marker`（保留待接线）/
    `formula_runtime_outbox`（保留待接线）三表各一条 `{判据, 处置, 读写方}`，
    处置取值域 `{'接线','保留待接线'}` **不含 `'弃用'`**（三表都有生产读写方，不删表）
  - `lifecycle_state` 补进 `_formula_to_dict`（实测**不在**里面）+ 前端中文标签
    （`draft`/`active`/`archived` → 草稿/生效/已归档）
  - _Requirements: 6.3, 6.4, 6.6_

- [x] 12. Wave 4 守卫
  - `backend/tests/test_formula_type_runtime_status.py`：三类型执行入口各有非测试调用方
    （零调用方即打红）；用**替身数据**验证执行链可达，不因真实库为空而跳过（R6.5）
  - `cross_check_results` 有 INSERT 生产代码（Property 15）
  - `FORMULA_TYPE_RUNTIME_STATUS` 与 `formula_runtime_table_status` 三条齐备、
    每条实测状态非空且含日期、处置取值域断言（Property 18）
  - `lifecycle_state` 进响应 + 前端有标签映射（Property 16）
  - `scope_failures` 三态断言 + 前端透出（Property 13）
  - **变异检验**：删落库语句 / 清空某条实测状态 / 处置写成 `'弃用'` / 让 `scope_failures`
    恒空 —— 逐一必须打红
  - _Requirements: 6.5, 8.4, 8.5_

### Wave 5 — WP 双实现锁死 · 端点收敛 · `/execute` 口径

- [x] 13. `WP()` 双实现语义登记与守卫（**只建守卫，不改实现**）
  - 新建 `backend/app/services/formula_wp_semantics.py`：登记两份实现的
    `{实参个数与位置语义, 数据源, 取不到时的返回}`
    —— `prefill_engine._resolve_wp_formula` 读 `parsed_data['cells']`（0 行 = 死）返 `None`；
    `formula_engine._handle_wp` 读 `ctx.wp_data` 返 `Decimal('0')`
  - 该差异**登记为已知差异**（改 `_handle_wp` 会波及 Tier A 求值，属范围外），每条带理由；
    未登记即打红
  - 守卫断言两份实现实参个数一致；`prefill-wp-prev-resolution-repair` 修其中一份时本守卫打红
  - 🔴 **本 spec 不实现取值逻辑**（R5.4）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 14. 27 处未登记 URL 收敛进 `apiPaths`
  - 新建 `services/apiPaths/formula.ts`，把 `components/formula/**` 与
    `composables/useFormula*.ts` 下的未登记 URL 声明为带参函数
  - **保持 URL 字符串逐字不变**（纯搬迁，零行为变化；任何"顺手规范化"属超范围）
  - 两个 `report-cross-check` 变体（`projectId.value` vs `projectId`）收敛为同一函数
  - 6 个 `gN/hN/validate-formulas` 登记为**范围外**（属各循环 spec，R7.6）
  - _Requirements: 7.1, 7.2, 7.6_

- [x] 15. `formula.py::/execute` 父子双算告警（**不改口径**）
  - 🔴 `FormulaEngine.execute` 自写 SQL 全量累加 `trial_balance.unadjusted_amount`
    存在父子双算；**改口径要动 `FormulaRequest`/`FormulaResult` 契约与前端两个已登记端点，
    风险高于收益** → 按 R7.5 只加 docstring 说明 + 显式告警 + 守卫钉住该说明存在，
    并在 Notes 登记待收敛
  - _Requirements: 7.4, 7.5_

### Wave 6 — 不可回退守卫 + 零回归 + 真实库验收

- [x] 16. 端点交叉锁死与硬编码归零守卫
  - `frontend/src/services/apiPaths/__tests__/formulaPaths.spec.ts`：扫全仓非测试
    `.ts`/`.vue`，`components/formula/**` 与 `composables/useFormula*.ts` 下未登记
    formula URL 数由常量钉死且**只许减少**（Property 19）+ 反向自检（用替身 fixture
    证明该扫描确实能发现硬编码）
  - **`apiPaths` 登记的公式端点 ⊆ 后端真实注册路由**（Property 1，杜绝缺陷 1 那类错配）
  - `formula.py` 父子双算说明存在（Property 20）
  - _Requirements: 7.3, 8.4, 8.5, 8.6_

- [x] 17. 零回归回归
  - `_REGISTRY` 15 个函数键集 + `_FORMULA_RESOLVERS` 9 个 resolver 键集逐字不变
    （基线常量钉死，Property 21）
  - 既有 8 键 `COLUMN_ALIASES` 映射目标逐字不变（Property 22）
  - 使用已注册列名的 **467 格公式**求值结果逐字不变（R9.3）
  - 三个 user-formulas 端点响应形状不变（R9.4）
  - `-k "formula"` 后端全量 + 前端 formula 域全量，与改造前基线**比对失败集合差集**，
    新增失败为 0；变异检验按差集判定不看 exit code
  - IF 某既有测试锁定了被修复的错误行为 THEN 诚实改写并在 Notes 说明，禁跳过/放宽断言（R9.6）
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

- [x] 18. 真实库诊断脚本 + 浏览器实测 + 收口
  - 新建 `backend/scripts/diagnose/diagnose_formula_runtime_state.py`（只读）：输出
    `wp_formula` 行数 / 按 `formula_source` 分布 / `user_formulas` 键数 / 三张运行时表行数 /
    未注册列名格数（修复前 48、修复后 0，两数字由守卫钉死，Property 24）
  - **四态区分**（`ok` / `missing_column` / `no_data` / `no_formula`），禁合并成「无数据」
    （Property 23）；取到数时同时输出取值路径（科目码 + 解析后列名 + 数据源表）
  - **浏览器实测**：底稿公式面板可见 issue/hint/计算时间、三类型中文标签、
    用户公式「保存 → 读回 → 复原」往返（真实库 `wp_formula` 0 行，靠往返证明链路可达），
    完成后按基线**逐字节复原**（`md5` + `jsonb_typeof` 双证，禁只看 length）
  - CI 新增 job `formula-management-runtime`（后端守卫）与 `formula-management-frontend`
  - 更新 `.kiro/specs/INDEX.md`；清理 `_wip_*` 与 `tmp_*` 诊断产物
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

## Notes

### 立项实证（2026-08-06，只读）

| 判据 | 实测 |
|---|---|
| `wp_formula` 表行数 | **0** |
| `parsed_data ? 'user_formulas'` | **0** |
| `parsed_data ? 'cells'`（`WP`/`PREV` 取值源） | **0** / 492 个有 parsed_data 的底稿 |
| `cross_check_results` / `draft_marker` / `draft_refresh_audit` / `formula_runtime_outbox` | 全部 **0 行** |
| `prefill_formula_mapping.json` cell 总数 | 1191 |
| 其中未注册列名的公式格 | **48**（本期借方 19 / 本期贷方 17 / 贷方发生额 7 / 借方发生额 5） |
| 前端硬编码 formula URL | distinct **41**，已登记 14（accounting 4 / report 4 / system 2 / workpaper 4），**未登记 27**，散在 **18 个文件** |
| `formula` 相关 router | **10 个** |
| `formula_engine.py` | len **58166** / `COLUMN_ALIASES` **8 键** / 静默回退 **2 处**（L631、L936）/ 无 `_resolve_tb_column` |

### Wave 2 交付实录（2026-08-06，Task 4/5/6/7 完成）

**核心证据**：`TB('1601','本期借方')` 改造前返 **1000**（期末余额），现返 **300**
（借方发生额）—— 48 格数字错已消除，`ast`/`regex`/`parallel` 三模式一致。

| 改动 | 文件 |
|---|---|
| `COLUMN_ALIASES` 8→14 键（规范名 `本期借方`/`本期贷方`，与共享件 `DEBIT_KEY` 一致）+ `OCCURRENCE_COLUMNS` 真源 + 三态 helper `_resolve_tb_column` + 谓词 `is_unregistered_column` + `FormulaColumnError`（插在兜底 `except Exception` **之前**）+ 两条求值路径收敛 | `formula_engine.py` |
| 拆死映射：`_COLUMN_MAP` 只留 TrialBalance 真实列，发生额走 `_OCCURRENCE_COLUMNS` + `_resolve_occurrence`（按**列名**先判，不能按 `_COLUMN_MAP` 结果判否则回退搬家） | `wp_formula_eval_service.py` |
| 两个 `tb_data` 构造点接共享件 `fetch_occurrence_by_standard_code` + `merge_occurrence_into_tb_data` | `wp_template_files.py`（`app/routers/`）· `adjudication_writeback.py` |

**验证**：守卫 `test_formula_column_alias_coverage.py` **15 passed**（改造前 7 红）·
**变异 6/6 全部准确打红 + 还原正确 + 基线 0 红** · HEAD 版换回比对
**新增失败 0 / 修好 7 条既有红** · 扩展组 **195 passed / 0 failed** ·
`app.main` 真实 import 通过。

**预存在 4 条未动**：`test_wp_formula_three_type.py` 的 sqlite fixture 缺
`working_paper` 表（HEAD 侧同样红，与本轮无关）。

### Wave 1 + Wave 3 交付实录（2026-08-07 本会话）

**🔴 接手时 Task 1 / 2 / 8 / 9 是「假红」** —— 复选框全 `[ ]` 而产物早已在磁盘：

| 任务 | 实证 |
|---|---|
| 1 | 三个孤儿 `useFormulaStatus.ts`(在 `composables/` 不在 `components/workpaper/composables/`) / `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` 均 **不存在**（`git status` 显示 ` D`），全仓 import 命中 **0** |
| 2 | 面板模板已渲染四字段（`issue_description` 3 / `hint_text` 3 / `last_computed_at` 2 / `refs` 8），`formula_type` 经 `formulaTypeLabel()` 走真源 `FORMULA_TYPE_LABEL` |
| 8 | `wp_user_formulas.py` HEAD=17162 → WT=25901；PUT 经 `wp_formula_service.save()` 写表（复用既有 upsert，**未新写** `upsert_user_formula`）、不写 `parsed_data`；GET 读时合并遗留键；DELETE 双清 |
| 9 | `test_user_formula_storage_convergence.py` **25 例全绿**（含 Property 9/10/11 + 三条提取器自检） |

⇒ **判「spec 任务是否真交付」不能信复选框，必须逐个探针**（memory 已记同族第 N 次）。

**本轮真实产出 = Task 3**：

1. **平台级端点存在性守卫** `components/workpaper/composables/__tests__/formulaEndpointExistence.spec.ts`
   （15 例）：读 `backend/app/routers/**` 抽 **2134 条**真实路由（其中含 formula 的 62 条）
   与前端 33 个 distinct formula URL 交叉锁死。四条判据设计：
   - **BASE 前缀式引用按前缀关系判定** —— `useFormulaImportExport.ts` 的
     `const BASE = '/api/formula-management/import-export'` 本身不是完整端点
     （真实请求 `${BASE}/export-template`），只做全等比对会误报 1 条；
   - **豁免逐条带两个判据**（后端未实现 + 前端有降级路径）+ 断言「豁免的路由后端确实不存在」
     （防豁免掩盖已存在路由）+ 断言「404 降级分支真在源码里」；
   - `Property 1` 孤儿清单扩到 **5 个**（见下）；
   - `Property 4` 把「活面板已修好的端点与 `items` 键」钉成不可回退。
2. **面板展示守卫** `components/workpaper/__tests__/formulaStatusPanelDisplay.spec.ts`（19 例）
   —— 独立成文件而非扩 `FormulaStatusPanel.spec.ts`，因后者属并发 spec
   `d-cycle-four-table-extraction-formulas`（同时编辑必互相回退）。
3. **顺带清理第四个同族孤儿** `components/workpaper/FormulaDependencyGraph.vue`
   （4540 字节，0 消费方 + 调后端零命中端点 `/api/projects/{}/workpapers/formula-dependencies`
   + `catch { /* Use empty graph */ }` 静默吞）+ 清 `components.d.ts` 残留条目。
   它不在 R1.1 的三个孤儿清单里，是 Task 3 守卫扫出来的 —— 处置按 memory
   「孤儿三选一 / 死代码立即删除」定为**删除**（留着修 URL 就是把陷阱擦亮）。
4. **顺带清面板死 CSS 6 个选择器 + 2 处重复规则**
   （`.formula-issue-label` / `.formula-hint-label` / `.formula-meta` /
   `.formula-meta-item.is-muted` / `.formula-refs-toggle` / `.formula-refs-list`；
   `.formula-issue` 与 `.formula-hint` 各定义两次）。清理后结构性核验：
   六个 SFC 块各在位、死选择器 **0**、重复规则 **0**。

**变异检验 10/10 全部准确打红 + 还原完整**（基线两侧均 0 红）：
端点守卫 5 条（坏端点 / projects 作用域 / 响应键回退 / 404 降级分支消失 / 孤儿复活）·
展示守卫 5 条（issue 门控恒假 / 自建标签表 / 空值文案回退 / 裸英文值 / refs 展开消失）。

**🔴 M5 抓出并修掉一处守卫自身缺陷**：`refs` 展开断言原写
`/expandedRefs\.has\(it\.id\)/.test(tmpl)`，而该标识符在展开箭头
`{{ expandedRefs.has(it.id) ? '▴' : '▾' }}` 处也出现 ⇒ 把
`<ul v-if="false">` 也放行（**删掉展开能力这个最核心的变异静默逃逸**）。
改判据为条件形态 `/<ul\s+v-if="expandedRefs\.has\(\s*it\.id\s*\)"/`。
与 memory 已记的「`toContain('a.b.length')` 抓不住删判断」「`toContain('<Foo')`
被 `<FooREMOVED` 骗过」同族 —— **判据必须落在条件表达式形态上，不是其中出现的标识符**。

### 收口实录 — Task 18（2026-08-07 本会话，18/18 全完成）

接手时 Task 1~17 全部 `[x]`、Task 18 `[ ]`。本轮做完 Task 18 并复盘，实测结论：

| 验收项 | 实测 |
|---|---|
| 后端守卫（5 文件） | 首轮 **1 failed / 132 passed** → 修后 **133 passed** |
| 前端守卫（3 文件） | **57 passed / 0 failed** |
| 诊断脚本 `--out` | rc=0，报告完整 |
| **未注册列名格数** | **0**（立项基线 48）⇒ Wave 2 修复确证 |
| 预设规模 | 公式格 **1280**（立项 1191，并发会话已扩），`本期借方` 21 / `本期贷方` 19 / `贷方发生额` 7 / `借方发生额` 5 **全部已注册** |
| `COLUMN_ALIASES` 键数 | **14**（8→14，规范名 `本期借方`/`本期贷方`） |
| 五张运行时表 | 仍全 **0 行**（`wp_formula` / `cross_check_results` / `draft_marker` / `draft_refresh_audit` / `formula_runtime_outbox`） |
| `parsed_data ? 'user_formulas'` / `? 'cells'` | **各 0 行** ⇒ 浏览器往返实测数据已复原 |
| CI | `governance-checks.yml` **133 jobs**，含 `formula-management-runtime`（7 步）+ `formula-management-frontend`（3 步），逐步引用文件全部存在 |

**唯一真实修复 = 一条过期守卫断言**：
`test_formula_type_runtime_status.py::test_frontend_has_lifecycle_label_map` 断言前端
标签真源必须含 `draft`/`active`/`archived`/`草稿`/`生效`/`已归档` —— 而这套取值是
**立项时的推测**，同 spec 后续浏览器实测已证明后端只写 `saved`（迁移 V104 列默认值 +
`wp_formula_service.save()` 两条分支）与 `succeeded`，前端真源
`FORMULA_LIFECYCLE_LABEL` 与前端守卫 `formulaStatusPanelDisplay.spec.ts` 都已按实证
改对，**唯独这条后端断言没跟上** ⇒ 恒红且零信号。
改法 = 判据改为「从后端 `wp_formula_service.py` 抽 `lifecycle_state = "xxx"` 赋值字面量
+ 从迁移抽 `DEFAULT 'xxx'`，断言前端映射键集 ⊇ 后端实际写入值」+ 抽取器自检
（抽到的值数 > 0、含 `saved`）+ 断言**不含**推测取值 `draft`/`active`/`archived`
（防下个会话又按推测写回）。→ 与 memory 已记的「反向自检若依赖旧行为，行为改对后
变成假红」同族，但这条更毒：**它锁定的是「推测的取值域」而不是「旧的错误行为」**。

### 归档前复核（2026-08-07 本会话，18/18 复验 + 1 处登记表同步）

接手时 18/18 全 `[x]`。按铁律逐个探针核实产物在位性与守卫有效性，结论：

| 复核项 | 实测 |
|---|---|
| 后端守卫 5 文件 | **133 passed / 0 failed** |
| 前端守卫 3 文件 | **57 passed / 0 failed** |
| 诊断脚本 `--no-db` | rc=0；未注册列名 **0 格**（立项 48）· `COLUMN_ALIASES` **14 键** |
| 预设规模 | 公式格 **1280**，四个发生额列名（`本期借方` 21 / `本期贷方` 19 / `贷方发生额` 7 / `借方发生额` 5）**全部已注册** |
| 五张运行时表 | 仍全 **0 行**（真实业务状态，非缺陷） |
| `parsed_data ? 'user_formulas'` / `? 'cells'` | **各 0 行** ⇒ 浏览器往返实测数据确已复原 |
| CI | **133 jobs**，两个 job 各 7 / 3 步，逐步引用文件全部存在 |

**🔴 唯一真实改动 = Task 13 登记表同步（守卫按设计打红）**：并发 spec
`prefill-wp-prev-resolution-repair` 已把 prefill 侧 `WP()` 的数据源从
`parsed_data['cells']`（全库 0 行 = 死链）换成 **`checklist_responses` + 声明式锚点映射**
（`prefill_anchor_map.resolve_anchor` / `read_anchor_value`，底稿定位改经 `wp_index` JOIN），
于是 `test_prefill_reads_cells_container` 打红 —— **这正是 Task 13 的设计意图**
（守卫 docstring 原文「修一份时另一份不会被忘掉」）。处置 = 同步登记表而非放宽断言：

- `WP_IMPLS[prefill].data_source` 改为 `checklist_responses(wp_id, item_id).remark`
  经锚点映射解析，`measured` 记「2026-08-07 由对方 spec 换数据源修复」；
- `WP_KNOWN_DIFFERENCES` 的 `data_source` 条目改为「**prefill 读 DB 的
  `checklist_responses`（已修复）vs engine 读内存 `ctx.wp_data`（调用方预载）**」，
  理由改为「让 engine 侧也走 `checklist_responses` 需给 Tier A 求值加异步 DB 访问」；
- 守卫判据由「读 `cells`」改为「**读 `read_anchor_value` + `resolve_anchor`** 且
  **不得回退到 `get("cells")`**」，反向锁死方向不变。

**变异检验 5/5 全 RED + 还原完整**（基线两侧 0 红）：①prefill 数据源回退成 cells
②丢掉 `resolve_anchor` ③实参解包改成 2 个 ④登记表删掉 `data_source` 差异
⑤`measured` 改占位 —— 逐一打红。

**两处首轮探针误判（已纠正，勿再照错结论找）**：
1. `execute_report_cross_checks` 的落库代码在 **`app/services/formula_management/logic_check.py`**
   （`CrossCheckResult(` 2 处 / `cross_check_results` 8 处），不在 `routers/formula_logic_check.py`
   （后者只是调用方）。按 router 路径查会得出「Task 10 未交付」的错误结论。
2. `wp_user_formulas.py` 仍有 `parsed_data["user_formulas"] =` 赋值（L497 PUT / L578 DELETE），
   但**只写 `original_preset` 一个键**（`preset_trace` 精简条目）——
   `WpFormula` 模型无 `original_preset` 列（V052/V100/V104 逐列核实），
   不写则「恢复默认预设」对新公式恒返 `None`。这是**有意的职责互斥**
   （表 = 公式本体唯一权威 / 遗留键 = 表无列的溯源元数据），不是 Property 9 违规。

### 归档轮复盘（2026-08-07 本会话，18/18 复验 + 2 处真实修复）

接手时 18/18 全 `[x]` 且已有一轮归档前复核。按铁律逐个探针复验，**产物全部在位、
守卫全部有效**，另**新查出两处此前三轮复核都漏掉的缺陷并已修**。

| 复验项 | 实测 |
|---|---|
| 15 个产物文件 | 全部存在（4 个孤儿确认已删：`useFormulaStatus.ts` / `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` / `FormulaDependencyGraph.vue`） |
| 后端守卫 5 文件 | **133 passed / 0 failed** |
| 前端守卫 3 文件 | **57 → 60 passed / 0 failed**（本轮新增 3 条 barrel 断言） |
| 抽样变异检验 | **5/5 全 RED**（静默回退复活 / 删新注册列名 / 用户公式回写 parsed_data / 三表处置改「弃用」/ WP 登记表删 data_source 差异），基线两侧 0 红、字节完整还原 |
| 诊断脚本 `--no-db` | rc=0；未注册列名 **0 格**（立项 48）· `COLUMN_ALIASES` **14 键** · 公式格 1280 |
| `formula.ts` 硬编码扫描 | 作用域内 **0 个**未登记 URL |
| 面板 | 已走 `apiPaths.wpFormula`（3 处 `api.` 调用零字面量 URL）· `issue_description` 5 / `hint_text` 5 / `last_computed_at` 4 / `refs` 17 / `formulaTypeLabel` 2 / `lifecycle_state` 3 全部真实引用 |
| lifecycle 标签真源 | `formulaEngineInventory.FORMULA_LIFECYCLE_LABEL = {saved:'定义已保存', succeeded:'求值成功'}`，与后端实际写入值（`wp_formula_service` 的 `'saved'` + V104 `DEFAULT 'saved'`）对齐 |
| `_formula_to_dict` | **19 键**，含 `lifecycle_state` / `definition_version` / `formula_source` |
| `logic_check.py` 落库 | `cross_check_results` 8 处 + `db.add` **2 处** ⇒ Task 10 确已接线 |
| CI | **134 jobs**（另一 spec 又加了一个），两个 job 各 8 / 3 步 |

**🔴 真实修复 1 —— `test_wp_formula_layer_contract.py` 恒红零信号（本 spec 半径内）**：
该守卫的「三层一致」判据是**手写按迁移分组的列清单**，只写到 V100，而
**V104（`V104__formula_runtime_outbox.sql`）又给 `wp_formula` 加了三列**
`lifecycle_state` / `definition_version` / `definition_hash`（ORM 早已跟进）
⇒ 断言 `orm_cols == _V052_BASE ∪ _V100_EXT` **恒不成立**，每次都报
「ORM 列与期望不符」，把「真的漂移了」与「清单自己过期了」混为一谈。
**双证它是预存在的**（不是本 spec 造成）：守卫与 ORM 两文件 `git status` 均 clean ·
`git show HEAD:` 侧 ORM 已有三列而守卫已不认 V104 · 工作树 diff 里无这三个字段。
**根治不是补一次清单**（那样下次加列还会过期）而是**改为扫描全部 `V*.sql`**
抽「`CREATE TABLE` 建表列 ∪ 各次 `ALTER TABLE wp_formula ADD COLUMN` 新增列」
与 ORM 列集精确相等，并把报错信息**按方向拆开**：
- `orm_only` 非空 = 新增 DB 列没写迁移；
- `mig_only` 非空 = **ORM 漏 `mapped_column`**（memory 已记的「表里有列、代码写不进去」那类静默缺陷）。

配三条自检防空转：建表列抽取必含 V052 的 11 个基线列 + 「约束名不得被当列名」+
「必须从某个 `V*.sql` 抽到过 ALTER」；另加 `test_extension_columns_live_in_their_own_migration`
钉死 V100/V104 各自的扩展列出现在**声明它的那次**迁移里（防迁移号与列归属漂移）。
建表体用**圆括号配对**截取（禁固定字符窗口，memory 已记该坑）。
结果：该文件 **0 → 5 passed**。
→ 与 tasks.md 已记的「过期 lifecycle 守卫断言」同族，是**同一类根因的第二例**：
判据写成「按当时状态手抄的清单」而非「从真源派生」。

**🔴 真实修复 2 —— `draftRefresh` 导出漏进 apiPaths barrel**：
`apiPaths/formula.ts` 导出 9 个常量，而 `apiPaths/index.ts` 的具名 re-export 清单
只列了 8 个（漏 `draftRefresh`）。memory 已记该 barrel 用**具名 re-export** 不是
`export *` ⇒ 漏登记者从 `@/services/apiPaths` 取到 **`undefined`**，而
`get_diagnostics` / vitest / Vite 全绿（TS 侧 barrel 没有该键，取用时才是 undefined）。
当前**不是活缺陷**（唯一消费方 `GtRefreshScopeDialog.vue` 走深路径
`from '@/services/apiPaths/formula'`），但属登记不齐、且下一个消费方按 barrel 写就中招。
处置 = 补进 barrel + 在 `formulaPaths.spec.ts` 追加 **Property 25「barrel 完整性」**
三条断言（`formula.ts` 的每个 `export const` 都在 barrel 清单里 / barrel 不引用
不存在的导出 / 提取器自检非空）。变异检验：从 barrel 删掉 `draftRefresh` → **RED**。

**其余 101 条 `-k formula` 失败全部逐簇钉死为预存在**（本 spec 新增 0 条）：
判据 = 「失败测试文件是否引用本 spec 改动的符号」+ 「该文件 `git status` 是否干净」双证。
36 个失败文件对本 spec 8 个生产改动文件的符号命中数**均为 0**；最需要核的三例
（`test_formula_save_validation.py::test_user_formulas_*`，直接测本 spec 改过的 PUT 端点）
逐条看报错：`assert 404 == 200` 根因是 **`wp_access_security_outbox` 外键**
（fixture 的 `actor_user_id=…099` 不在 `users` 表）、另两例是 **sqlite fixture 缺
`working_paper` 表** —— 都是测试环境问题，与端点逻辑无关。
最大一簇 22 例在 `test_report_formula_filler_mirror.py`（`git status` 为 `??`，
未跟踪 = 另一 spec 的未提交产物）。

**🔴 本轮方法论纠正**：零回归**未**采用「HEAD 换文件比对失败集合」——
memory 已记该判据在「改动文件含他人未提交成果」时会破坏数据（`git show HEAD:`
拿到的不是「我改之前」而是「别的 spec 之前」，且 Ctrl+C 打断会把 HEAD 版留在工作树）。
本 spec 的 `formula_engine.py` / `wp_template_files.py` / `logic_check.py` 等
都是多 spec 共享热点 ⇒ 改用「符号引用 + git 状态」双判据定向归因。

### 三处 spec 文档路径/命名偏差（已实证，勿再照文档找）

1. **`formula.py::/execute` 不存在** —— requirements 缺陷 6 与 design 组件 7、Task 15
   都写 `formula.py::FormulaEngine.execute`，实测 `class FormulaEngine` 在
   **`app/services/formula_engine.py`**（`app/routers/formula.py` 只是薄路由层，
   4037 字节、无 `父子双算`/`叶子`/`unadjusted_amount` 任何命中）。Task 15 的产物
   （`PARENT_CHILD_DOUBLE_COUNT_WARNING` 常量 + docstring 「已知口径缺陷」段 +
   `warnings` 返回键 + `logger.warning`）全部落在 `formula_engine.py` 且正确。
   按文档路径写守卫会 0 命中空转。
2. **`formula_column_aliases.py` 有意未建** —— design §Data Models 计划把
   `COLUMN_ALIASES` 提取为独立真源模块并由 `formula_engine.py` re-export，实际
   **保留在 `formula_engine.py` 内**（该文件 66828 字节，`OCCURRENCE_COLUMNS` /
   `_resolve_tb_column` / `is_unregistered_column` / `FormulaColumnError` 全在其中）。
   这是**正确的偏离**：提取会新增一个 import 层且既有 `from app.services.formula_engine
   import COLUMN_ALIASES` 的引用面广，收益仅「文件更小」；守卫按 `formula_engine.py`
   写、已全绿。design 该行应视为未采纳。
3. **「静默回退残留 1 处」是 docstring 反例** —— 扫 `account_data.get(..., account_data.get("期末余额"` 形态在
   `formula_engine.py` L192 命中，位于 `_resolve_tb_column` 的 docstring 里
   （写明「改造前两处求值路径都写 ……」）。守卫剥注释后判定故全绿。
   → 复核这类「禁用形态」时必须先 `stripComments()`，否则会误判成未修完。

### 复盘：五处进一步优化的评估结论

逐项评估后**四项不做、一项已做**，理由如下（避免下个会话重复提议）：

| 候选 | 结论 | 理由 |
|---|---|---|
| 提取 `formula_column_aliases.py` 独立真源 | **不做** | 见上文偏差 2；纯文件拆分零功能收益，且要改既有 import 面 |
| `execute` 改叶子聚合口径（消除父子双算） | **不做** | R7.5 已裁决：要动 `FormulaRequest`/`FormulaResult` 契约与前端两个已登记端点，风险高于收益；现已有显式 `warnings` + 单一真源文案 + 守卫钉死 |
| 让 `wp_formula` 有真实数据（造种子） | **不做** | 0 行是**真实业务状态**（用户尚未创建自定义公式），造种子等于往生产库塞测试数据；链路可达性已由「保存→读回→复原」往返实测 + 替身数据守卫（R6.5）证明 |
| 收敛 6 个 `gN/hN/validate-formulas` URL | **不做** | R7.6 已显式登记范围外（属各循环 spec） |
| 那条过期 lifecycle 守卫断言 | **已修** | 见上文「唯一真实修复」 |
| `test_wp_formula_layer_contract` 列清单只到 V100（恒红） | **已修**（2026-08-07 归档轮） | 手写清单改为扫全部 `V*.sql` 派生；同族第二例 |
| `draftRefresh` 漏进 apiPaths barrel | **已修**（同上） | 补 barrel + Property 25 三条断言 + 变异 RED |

### 本轮新查出三处 spec 未记的缺陷（第九~十一处）

9. **`SUM_TB` 两条路径取了 `col_name` 却丢弃**，写死 `data.get("期末余额")` ——
   连别名表都不查、trace 也不打印列名，比 `TB` 的静默回退更彻底。影响面实测
   **0 格**（预设里 `SUM_TB` 第二实参全是期末余额语义）⇒ 潜伏缺陷。
   **已修**（两条路径同时改，`期末余额` 走 helper 与原 `data.get` 逐字等价 = 零回归）。

10. **`wp_formula_eval_service._COLUMN_MAP` 是第三个列名映射真源**，把
    `借方发生额→debit_amount` 映到 **`TrialBalance`**，而该表**没有**
    `debit_amount`/`credit_amount` 列（ORM 实测只有 `unadjusted_amount`/
    `rje_adjustment`/`aje_adjustment`/`audited_amount`/`opening_balance`），
    加上取值处 `getattr(row, field, None)` **带默认值** ⇒ **静默返 0** =
    看着已注册实则死映射。**24 个生产消费方**（D1~D7 / H5~H10 / I1~I6 全部
    render 策略）。**已修**（发生额路由到 `tb_balance` 共享件）。

11. **`_TOKEN_PATTERNS` 的 TB 正则缺词边界**，`TB\('...'\)` 会匹配
    `SUM_TB('a~b','col')` 的后半段（实测混合公式里 TB 命中 2 次）。旧实现靠
    「`a~b` 在 tb_data 里查不到 → 0」侥幸不影响最终值，但改造后会**多记一条
    error 把 `ok` 误判成 False`**。**已修**（TB 分支显式跳过含 `~` 的区间形态；
    `SUM_TB` token 排在 TB 之前已整段替换，故跳过等价）。修后两条路径的
    trace 与 errors **逐条一致**。

### 三件套复核修正（2026-08-06 本轮，共七处）

1. **🔴 Wave 2 曾落盘后被并发会话回退** —— `tmp_verify_engine_out.txt` 记录 len=60183 /
   15 键 / 有 `_resolve_tb_column`，磁盘真相 len=58166 / 8 键 / 两处静默回退仍在。
   ⇒ 开工前必须跑 `_wip_fmc_truth.py` 核磁盘状态，**不信任何过期产物**。

2. **🔴 规范字段名与已交付共享件打架** —— design 首版写映射到 `借方发生额`，而 h-cycle spec
   已交付 `four_table/occurrence_by_standard_code.py` 的 `DEBIT_KEY="本期借方"`，其守卫
   `test_occurrence_keys_match_engine_standard_fields` 断言
   `DEBIT_KEY ∈ set(COLUMN_ALIASES.values())` ⇒ 照 design 写必打红。已改为 `本期借方`/`本期贷方`。

3. **🔴 守卫重复造** —— Task 6 原要新建 `test_formula_column_alias_registration.py`，而
   `backend/tests/test_formula_column_alias_coverage.py` 已覆盖同一不变式（12 例，已打红
   48 格 + 2 处回退，且含 `aliases_nonempty` 反向自检）。同一不变式两份守卫 = 双真源，
   改一处另一处不红。已改为扩充既有文件。

4. **🔴 路径错** —— `wp_template_files.py` 在 **`app/routers/`** 不在 `app/services/`
   （实测 `app/services/wp_template_files.py` exists=False）。按 design 首版路径写守卫必 0 命中空转。

5. **🔴 三套编号并存** —— requirements 已重写为 10 个 R，而 design 的 24 条 `**Validates:**`
   与内文 15 处引用、tasks 的全部 `_Requirements` 都用旧编号（design 旧：R7=端点/R2=列名/R1=存储；
   tasks 旧：R1=端点+展示/R3=三类型/R5=运行时空转），tasks 有 3 处越界（`1.7`/`5.5`/`5.6`）。
   本轮已全部重映射，越界归零。

6. **🔴 Task 10「双写」与 design 组件 3 / Property 9 打架** —— tasks 首版写「双写
   `parsed_data` + `wp_formula`」，而 design 与 Property 9 要求 PUT 不再写 `parsed_data`。
   R4 标题是「存储**收敛**」，双写等于新造双真源、比现状更坏。已按 design 定为收敛
   （GET 保留读兼容 + 守卫钉死该分支）。

7. **🔴 R5 与 R10.4/10.5 原无任务覆盖** —— 旧 tasks 只有 16 个任务、无 `WP()` 双实现守卫、
   无浏览器实测与往返复原。已补 Task 13 与 Task 18。

### 两处立项前判断被实证推翻（勿再按旧结论行事）

1. **`issue_description`/`hint_text` 不是零消费** —— 实测各有 3 / 5 个消费方
   （`GtFormulaHintPanel.vue` / `GtFormulaEditDialog.vue` / `FormulaTab.vue` /
   `useFormulaScopeCatalog.ts` / `useFormulaIssueHint.ts`）。上一轮结论「六个字段全为 0」
   是**只查了 `FormulaStatusPanel.vue` 与 `useFormulaStatus.ts` 两个文件**就过度概括。
   真正零消费的只有 `lifecycle_state`(0) 与 `definition_version`(0)。
   ⇒ R2 已收窄为「`FormulaStatusPanel` 这一个面板缺展示」，不是全平台缺。

2. **`useFormulaStatus` 的缺陷远比「没展示」严重** —— 它调的**两个端点都不存在**，
   且读的响应键 `formulas` 与后端 `items` 不符，三处叠加 + `catch { = [] }` ⇒ 整个
   composable 恒空。**且实测 `useFormulaStatus` 全仓零消费方**（`<NONE>`）—— 它本身
   就是孤儿 composable，Wave 1 修完需连带确认有渲染宿主，否则修了也不可达。

### 已知风险与顺序约束

- **Task 5 改静默回退会打红一批既有测试** —— 那些测试可能锁定了「取不到列返回期末余额」
  的旧行为。按 R9.6：诚实改写并在 Notes 说明，禁跳过/放宽断言。
- **Task 8 收敛后 GET 的读兼容分支必须有守卫** —— 0 行状态下它是纯保险，无守卫会被
  下个会话当死代码删掉，将来某环境有存量就静默丢数据。
- **Task 14 是纯搬迁** —— URL 字符串逐字不变。
- **Task 6 复用共享件前先 `inspect.signature` 实证** —— memory 已记 G6 因照抄调用形态
  把同步纯函数 `await` 导致整段静默失效。
- **变异检验按「失败测试名集合差集」判定，不看 exit code** —— 本 spec 的 Wave 2 守卫
  基线本身就是红的（故意先打红），按 rc 判会得出「全部 GREEN = 守卫缺陷」的假结论。

### 待裁决项 — 三项均已在实现中定案（2026-08-07 归档前复核）

| 原待裁决 | 定案 | 依据 |
|---|---|---|
| 1. 旧 `parsed_data['user_formulas']` 读兼容分支保留多久 | **永久保留 + 守卫钉死**，且用途已收窄为「只承载 `original_preset` 溯源」 | `WpFormula` 表无 `original_preset` 列；`test_user_formula_storage_convergence` 已钉死 GET 合并分支存在 + PUT 不回写公式本体 |
| 2. `cross_check_results` 落库要不要带 `year` | **带**（`logic_check.py` 落库处已按 `(project_id, year, rule_id)` upsert） | 表有该列且 `execute_report_cross_checks` 入参可拿到 |
| 3. `useFormulaStatus` 零消费方如何处置 | **删除**（连同 `FormulaTooltip.vue` / `FormulaSourceDrawer.vue` / `FormulaDependencyGraph.vue` 共 4 个同族孤儿） | 与活面板 `FormulaStatusPanel.vue` 是双真源；孤儿基线守卫 `formulaEndpointExistence.spec.ts::Property 1` 钉死不复活 |
