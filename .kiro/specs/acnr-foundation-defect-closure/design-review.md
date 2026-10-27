# 设计评审（第 3 轮）：ACNR 地址坐标名称库底座缺陷收口（acnr-foundation-defect-closure）

- 评审对象：`design.md` 修订轮 2（含 §20 对第 2 轮 23 条意见的回应、§19 对第 1 轮 34 条的回应）
- 对照：`requirements.md`、第 2 轮 `design-review.md` / `design-review.json`（HIGH 4 / MEDIUM 9 / NIT 10）
- 本轮基线：HEAD `bb7aff842`（设计声明 `b5fc200e0..bb7aff842` 间 ACNR 目录/生成器/服务/V2/高级查询 0 改动，§1 现算沿用）
- 本轮现算证据复核：`tmp_acnr_foundation/out/q01~q06`（均存在，已逐份读取）；关键源码路径直接对照
- 结论：**APPROVED**（HIGH 0 / MEDIUM 0 / NIT 3）

## 一、重点核查结论（评审任务指定的四项）

### A. 用户拍板两处是否正确落到 design

1. **R2-F1（孤儿 cell 判无效 + deprecated 迁移映射）——正确落地。**
   - §3.2「R2-F1（用户拍板 2026-10-27）」明确：25 个孤儿 cell 从种子 loader 输入清除，逐个写进 `cell_verdicts`（`verdict: "deprecate"`、`replaced_by` 指向 `add_platform_sheet` 新补父 sheet、reason「无物理来源」），生成 `deprecated: true` 条目，默认不进地址树，acnr_targets 返回 422 `deprecated`（§2.3 分类表一致）。
   - 5 张父 sheet 保留 `add_platform_sheet`，目的被正确限定为「让停用 cell 有可解析的 `replaced_by`、让导航落到 wp_index 实例」，sheet 本身不带有效 cell。
   - 保留 `replaced_by` 别名指向以满足铁律 3；并明确「实施前以当时 HEAD 现算复核是否被引用，被引用不得静默消失，存疑按铁律 3 暂停向用户说明」。
   - 现算证据核对一致：`q01` 证实 25 个 addr_id/formula_ref 在 `formula_presets_seed`/`cross_wp_references`/`prefill` 中 0 命中；`q02` 证实全 `backend/data` 仅目录自身 4 份快照出现这些 addr_id/formula_ref，种子名只在 i/j/m 种子、`wp_account_mapping`、`procedure_table_templates` 与 J2-1/J2-3/J3-1/M6-1 的 `cross_refs`（数据流声明，不带坐标）出现；渲染 schema `i6-research-development-expense.yaml` 不含 I6-7/M6-5。设计 §3.2 描述与证据逐项吻合。
   - §3.3 停用行为表同时覆盖「停用 sheet（K14~K18）」与「停用 cell（25 孤儿）」，二者 `deprecated=true` + `replaced_by` 行为一致，区别只在 `replaced_by` 指向替代 sheet 还是父 sheet，表述清楚。
   - 计数自洽：§3.2「sheet 1215 + 5 + 5 = 1225；cell 474 − 25 = 449 有效 cell，另 25 deprecated cell + 14 §6.4 超范围停用 cell」。5 张父 sheet 非 classification 派生（§3.1 证据表 classification 0/0），故 +5 补登正确；K14~K18 +5 为新增 deprecated sheet；474 含 25 孤儿，停用后 449 有效。内部一致。

2. **§16 Q0（跨 spec 冲突以本 spec 为准）——正确落地。**
   - §16 Q0 标「已裁定 2026-10-27，用户拍板」；§1.4、§2.6、§20 一致：以本 spec D1「实现、不下线」为准；`acnr_targets` 字段只在本 spec 定义一次；`QueryDSL.project_id`/`year`、`QueryRequest` 新字段「谁先实施谁加、另一方复用」；对方撤回「面板开发中」；不改对方 spec 文件，仅在本 spec design 记录裁决并在 INDEX 注明。
   - R2-N1 的闸门要求也落地：§20 R2-N1 要求 tasks 把前端面板/结果区标「用户闸门：Q0（已裁定以本 spec 为准）」，不改对方文件——与「已裁定」状态自洽。

### B. 第 2 轮 HIGH（R2-F1~F4）是否逐条解决

- **R2-F1**：见上，用户拍板，正确落地。
- **R2-F2（删子串启发式致 14 处真实静态写法变 not_found）**：§6.5 承认「现算 0」是错口径（正则漏了预设里逗号后的空格），改为实施第一步导出 `head_resolvable_static_writings.json`（含 PG 公式存储五类表），逐条断言仍可解析或有登记处置；D5-1/I1-1/审定表I1-1 经 `merge_into` 落父级限定别名；其余 4 组登记 `ccr_unresolved` 并标 `head_resolvable_at`；无证据组暂停说明。`q03` 证实 `WP('I1','审定表I1-1',...)`、`WP('B23','B23-2 货币资金控制了解',...)`、`WP('I1','摊销测算表（不含减值）I1-10...',...)` 等子串写法真实存在。处置与证据吻合，解决。
- **R2-F3（11 条 CCR 改写至少 7 条会改错）**：§10.3 承认旧「11 条目标唯一」判据错误，改为「每条改写须两项证据（模板 tab 存在 + 字段文字在该 tab）」，B60×6、S14×1 不能改写，预计修 ≤4、豁免 ≥48，§7.4/§14.3/`check_ccr_resolve` 数字随之重算。`q04` 证实 CW-60/417/418/419/420/421 均 `B60/总体审计策略`、CW-79 为 S14；`q05` 证实 B60 唯一目录子 sheet 是 `B60-1 工时预算与控制板`、S14 唯一子 sheet 是 S14-1，且 B60 总体审计策略在 docx（未入目录）。处置与证据吻合，解决。
- **R2-F4（版本锁落库后启动期 GC 仍读进程内集合；「生产调用方 0」不实）——用户拍板，正确落地。** §8.3/§8.4 改为异步查库 `referenced_registry_versions(db)`（含软删、读 §8.2 新列），`run_db_aware_gc(session=None)` 自开短会话，查库失败 fail-closed；明确删除顺序（先改 GC 查库再删 `list_archived_projects`）；加启动期 GC `pg_only` 用例 + 变异；列出受影响既有测试。源码直接核对：`catalog_snapshot_gc.query_referenced_versions()` 确调用 `immutability.list_archived_projects()` 且被 `run_db_aware_gc` 使用（L220-274）；`startup_registry._task_acnr_catalog_snapshot_gc` 每次启动 `await run_db_aware_gc(keep_recent=10)`。R2-F4 的根因链在源码中完全成立，设计的重写正确覆盖。

### C. 现算类结论是否有真实依据而非照抄审计报告

- 本轮所有新/改现算结论均标注 `q01~q06` 并有对应证据文件，评审逐份读取核对：孤儿引用面（q01/q02）、子串写法（q03）、CCR 分组（q04）、B60/S14 与 wp_templates（q05）、BP-2（q06）。
- 设计 §1.1 明确区分「审计报告值 vs 现算值」（如别名冲突报告 5 / 生成器现算 4；gap_count 报告 33 / 现算 32），并说明差异来源（改名并组、gap_count 口径混入），不是照抄。
- 源码级抽验三处（均独立于审计报告）：①GC 调用链（R2-F4）在源码成立；②`Project.status` 赋值点现算与 §8.1 的 4 函数口径一致（`continuous_audit_service` 与 `project_wizard_service.confirm` 是构造器默认值 / 新建，`private_storage_service` 是 WorkingPaper 非 Project，设计守卫范围「给 Project.status 赋值的函数」口径正确）；③B60/S14 目录子 sheet 与 docx 事实在 `q05` 成立。

### D. 是否引入新的未验证假设

- 未发现实质性新未验证假设。本轮改动多为「把第 2 轮指出的错口径替换为可现算口径 + 实施期现算承诺」，且逐条配了证据文件或守卫。
- 设计一贯把「实施期须以当时 HEAD 现算后冻结」的项（BP-2 窄定义、`head_resolvable_static_writings`、CCR 修/豁免数、鉴权基线下调值）显式标为「现算后冻结、不写死」，符合方法论铁律②。
- 少数仍待实施期现算确认的项（见下 NIT），不构成阻塞：它们要么是实施顺序依赖（formula-hub 任务 22 是否带 J1 字段，已给回退流程 B），要么是可伪证守卫钉死的（D6「project_id 非空且 db 为空」应为 0）。

## 二、Findings

> HIGH 0 / MEDIUM 0。以下 3 条为 NIT，不阻塞，供实施期关注。

### N1　NIT　§2.3 `resolve_builder_scope` 登记为 body-carried 项目级校验函数的「可伪证条目」形状未定

- 位置：design.md §2.3「把 `resolve_builder_scope` 登记为项目级校验函数（带可伪证条目，仿 `check_project_access` 的登记方式）」
- 问题：R2-F5 已把构建器鉴权正确收敛到 `resolve_builder_scope`（与业务视图同一 `ownership_guard`），但 body-carried 扫描器识别「首句无条件调 `assert_project_permission`」的旧判据对 `resolve_builder_scope` 不成立（它不是 `assert_project_permission`，也未必是函数体首句）。设计说「仿 `check_project_access` 的登记方式」但未给该登记的字段形状，实施时若登记项与扫描器口径不吻合，可能出现「守卫看不到鉴权 → 误报欠账」或「登记项失效不报」。
- 建议：实施期按扫描器真实读取的字段落登记项，并补「登记项真的对应一个生效的项目级校验」的反向断言（可伪证），与 `test_project_endpoint_authz_body_carried.py` 现有可伪证条目同构；tasks 中写明字段形状。

### N2　NIT　§2.4 J1 回退流程 B 对 `test_wp_cell_reader.py` 整对象相等断言的改动清单待实施期确认

- 位置：design.md §2.4「未带（预期）：由本 spec 单独一次提交给 `WpCellRead` 追加两个默认 None 的可选字段…逐条列出要同步改的 `test_wp_cell_reader.py` 断言」
- 问题：R2-F6 的回退流程 B 正确（两字段默认 None、不改对方三态语义），但「要改哪些整对象相等断言」依赖 formula-hub 任务 22 入库时的实际测试形状，当前只能预判。若任务 22 的 `WpCellRead` 构造/断言与预判不同，追加字段时可能触发对方测试红。
- 建议：实施动手前 `git log -S "reason_code" -- backend/app/services/wp_cell_reader.py` 与 `git log -p -- backend/tests/**/test_wp_cell_reader*.py` 核对任务 22 实际形状，再据实列改动清单并在 formula-hub 任务 22 下登记；设计已承诺该核对，属实施期确认项。

### N3　NIT　§8.3 `effective_catalog` 与 `get_locked_version` 的请求级记忆在「同一请求内目录版本不变」假设下成立，建议补一句失效边界

- 位置：design.md §2.4 R2-F7 `effective_catalog(db, project_id)`、§8.3 `get_locked_version` 记忆于 `db.info["acnr_lock"]`
- 问题：R2-F7/R2-F4 的记忆口径（请求级会话即请求级记忆、不跨请求，避免另一 worker 归档后读旧值）正确。但 `effective_catalog` 在同一请求内多次调用会复用 `get_locked_version` 记忆值；若某请求内先取值、随后同请求内又触发归档/解锁（同事务改 `acnr_registry_version`），记忆值会滞后。现算中「同请求内既取值又改锁」的路径应为 0（取值是只读链，归档是写链，不混在一个请求），但设计未显式声明这一边界。
- 建议：实施期在守卫或注释中声明「取值请求与归档/解锁请求互斥，`db.info` 记忆只在只读取值请求内有效」，或在归档/解锁写入后清掉 `db.info["acnr_lock"]`；属防御性补强，不影响当前正确性。

## 三、Verified Assumptions（本轮新核实 / 复核）

- `tmp_acnr_foundation/out/q01~q06` 六份证据文件均存在且可读，内容与设计 §1.1/§1.2/§3.2/§6.5/§10.3/§14.1 引用一致。
- 25 个孤儿 cell 的 addr_id/formula_ref 在 `formula_presets_seed.json`、`cross_wp_references.json`、`prefill_formula_mapping.json` 中 0 命中（q01）；全 `backend/data` 仅目录自身 4 份快照出现（q02）；种子名出现处（种子/映射/render-schema cross_refs/procedure_table_templates）均不带坐标（q02）。R2-F1 判无效的依据成立。
- `catalog_snapshot_gc.query_referenced_versions()` 调用 `immutability.list_archived_projects()`，被 `run_db_aware_gc` 使用（源码 L220-274）；`startup_registry._task_acnr_catalog_snapshot_gc` 每次启动 `run_db_aware_gc(keep_recent=10)`（源码 L601-605）。R2-F4「生产调用方 0 不实」成立，§8.4 重写正确。
- CCR CW-60/417/418/419/420/421 均 `source_wp=B60, source_sheet=总体审计策略`，CW-79 为 S14（q04）；目录中 B60 唯一子 sheet 为 `B60-1 工时预算与控制板`、S14 唯一子 sheet 为 S14-1，B60 总体审计策略内容在 `B60 总体审计策略及具体审计计划.docx`（未入目录）（q05）。R2-F3 的「至少 7 条会改错」成立。
- 子串写法真实存在：`WP('I1','审定表I1-1',...)`×2、`WP('B23','B23-2 货币资金控制了解',...)`、`WP('I1','摊销测算表（不含减值）I1-10（剩余年限法）',...)`×2 等（q03）。R2-F2 的 14 处/7 组口径成立。
- `Project.status` 赋值点现算：`archived_exception`（→execution）、`deliverable_service`（→archived）、`event_handlers/_impl`（→execution，带 `cur not in ("created","planning")` 守卫）、`project_wizard_service.confirm`（→planning）；`continuous_audit_service`/`project_wizard_service` 建项是构造器默认、`private_storage_service` 是 WorkingPaper。§8.1 的 4 函数口径与守卫范围一致。
- `deliverable_service` 置 archived 处带 `project.status != archived` 前置判断、只 flush 不 commit（由路由 commit），与 §8.3 加锁事务边界一致。
- 第 1、2 轮已核实的假设（平台名一名多码 9 组、372 平台名写法、`resolve_builder_scope` 带 `requested_project_id`、`formulaRefIssues.ts` 结构、resolver `source_layer` 取值 `L1_cell/L1_sheet/L3/V1`、迁移最高 V205、http 拦截器 `_silent` 先返回/180s 超时等）本轮未被新改动推翻。

## 四、Unverified / Wrong Assumptions（本轮）

- 无新增错误假设。第 2 轮列出的四条错口径（J1 两份同文、进程内锁调用方 0、子串写法现算 0、父级单 sheet 推目标唯一）在本轮设计中均已勘误并改为可现算/可伪证的处置。
- 待实施期现算确认（非错误、已有承诺或守卫钉死）：BP-2 窄定义的最终文件清单（r07/q06 现算约 10/35，实施期冻结）；`head_resolvable_static_writings` 的 PG 公式存储命中集（实施第一步导出）；CCR 修 ≤4 / 豁免 ≥48 的最终数（逐条两项证据）；formula-hub 任务 22 是否带 J1 字段（回退流程 B 兜底）；D6「project_id 非空且 db 为空」应为 0（守卫钉死）。

## 五、本轮现算证据索引

| 文件 | 内容 |
|---|---|
| `tmp_acnr_foundation/out/q01_orphans.txt` | 25 孤儿 cell 分布，及 addr/ref 在 presets/CCR/prefill 0 命中 |
| `tmp_acnr_foundation/out/q02_orphan_refs_wide.txt` | 全 backend/data 扫描：仅 4 份快照含孤儿 addr/ref；种子名出现处（不带坐标）；渲染 schema 无 I6-7/M6-5 |
| `tmp_acnr_foundation/out/q03_substring_writings.txt` | 三参 WP 写法统计与子串写法样例（presets 31 / CCR 287 / prefill 212） |
| `tmp_acnr_foundation/out/q04_ccr_groups.txt` | B60×6 + B60D×1 + S14×1 的 CCR 分组 |
| `tmp_acnr_foundation/out/q05_b60_s14.txt` | B60/S14 目录子 sheet 与 wp_templates 下册（B60 docx） |
| `tmp_acnr_foundation/out/q06_bp2.txt` | BP-2 窄定义现算（本轮未逐项展开，R2-F12 已采纳窄定义） |
| 源码 `catalog_snapshot_gc.py` / `startup_registry.py` | R2-F4 GC 调用链直接核对 |
| 源码 grep `Project.status` 赋值点 | §8.1 四函数口径核对 |
