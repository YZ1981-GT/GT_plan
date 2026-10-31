# 设计：裁剪生成后续优化复盘的范围外问题收口

## 1. 取舍

| 议题 | 采用 | 否决 |
|---|---|---|
| H5 / H7 / M8 适用性 | 不按行业拦截；按本底稿语义科目是否在试算表里找到（`accounts_found`）给不阻断的提示 + 程序裁剪深链 | 新增项目行业字段（产品功能，需另立 spec 定字典与录入口）；继续读分类码（永不命中） |
| M8「标记为不适用」 | 删除，改走程序裁剪（有理由、权限、留痕） | 保留：它写的 `M8-industry-guard` 生产代码没有读者，标了也不生效 |
| 无调用方的行业校验端点 | 删除端点与 service 函数 | 修成按科目判断：概念与名字不符，且没有调用方 |
| AI 提示词「行业」行 | 没有来源就不出现该行 | 填「未登记」：模型会把它当事实复述 |
| 内置模板集初始化 | 启动任务（best_effort、singleton）+ 管理员手动入口 | 列表 GET 内兜底写库（GET 带副作用）；前端「列表为空才 seed」（仍是浏览器写请求） |
| seed 端点权限 | admin / partner（与「种子加载」面板 ADR D7 一致） | 保持只校验登录（只读账号可写全局表） |
| 前端组别解释 | `@/types/projectClassification` 提供 `categoryGroupOfCode`（只给非项目字段中的登记码归组）、`classificationOf`（只读后端 `project_classification`）与 `describeCategoryGroup` | 每个组件各自 `charAt(0)` / `startsWith`，或拿 `business_category` 猜组别 |
| 中间件拦只读角色写入 | 不做（范围外，涉及全平台写端点语义） | — |

## 2. 行业误用（R1）

**渲染策略**

- `_h5_oil_gas_assets.render`：删除 `_check_industry_applicability` 与 `industry_error` 早返回，所有项目走完整取数（已填内容、试算表三层、项目上下文、四表增强）；删除重复的 `_APPLICABLE_INDUSTRIES`；返回体删 `industry`，加 `accounts_found`。验收期纠正其判据：解析器在科目表不可用时会给出裸 fallback 查询码，`ResolvedSlot.found` 只代表“有查询落点”，故新增共享 `has_resolved_tb_rows`，按 active `tb_balance` 实际行判定；空查询为 `false`、查询失败为 `null`、零余额行仍为 `true`。`account_codes` 继续保留兜底查询码，不参与存在性判断。`_load_project_context` 保留分类原值透传（字段名照旧，注释改正为「质控分类」）。
- `_h7_biological_assets.render_h7_biological_assets`：同样删除行业判定；四表增强不再包在 `if is_applicable` 里；返回体删 `industry` / `is_applicable`，`accounts_found` 与 H5 走同一实际 TB 行判据。
- `_m8_general_risk_reserve.render`：`project_info` 只留 `client_name`（`getattr(proj, "industry")` / `client_industry` 恒空）；`accounts_found` 只看 gross 槽在 active TB 的实际行，查询失败为 `null`；SQL 前缀同时收紧为 `code` 等值或 `code + "."` 子科目，防 `4102` 误命中 `41020`。
- B1-3 `_load_project_context` 不再 SELECT 分类、`industry` 留空，预填 `basic-industry` 的分支删除；B1 风险评估、B1-4 尽调同样留空（字段保留，前端读 `|| ''`）。

**端点**：删除 `GET /api/h5/industry-check`（`h5_oil_gas_assets_service.check_industry_applicability` 一并删）、`GET /api/workpapers/{wp_id}/h7/industry-check`（`h7_biological_assets_service.check_industry_applicability` 一并删）。`wp_bound_entry_coverage.json` 只删这两条（台账本身对现网已有 30+ 条历史漂移，整份重生成会把别的会话的路由变化一起写进来），`summary` 按 `_rebuild_summary` 重算；`test_raw_sql_unqualified_column_contract` 删 `projects.industry` 基线项；`test_project_endpoint_authz_body_carried._BODY_IDENTITY_ONLY_BASELINE` 按现算下调。

**AI 上下文**：B1-4 AI 生成 system prompt 的项目信息按行拼接，行业行只在有值时出现（当前恒无值）；N2 `_load_project_context` 不再取分类、提示词不出现「行业」；A17 `_get_project_context` 删 `hasattr(project, "industry")` 分支，分类行改为「质控业务分类：A1」，RAG 检索词改为章节标题（原取「第 3 行」，实际拿到截止日）；同类 grep 找到的 H1~H3、I1~I6、K1~K13 共 22 个 `*_ai_generate.py` 与 `context_injector` 全部把分类标签改为「质控业务分类」。前端 I4 行业推荐删 `ctx.business_category`，B1 / B1-4 不再发送空行业键。

**前端宿主**：新增 `components/workpaper/shared/WpAccountAbsenceHint.vue`（props：`projectId`、`cycle`、`accountName`、`usualScope`、`accountsFound`；`accountsFound === false` 才显示 info 级 `el-alert`，按钮「去程序裁剪」跳 `ProcedureTrimming` 带 `?cycle=`）。GtH5 / GtH7 删除 `inject('projectContext')` 守卫与 el-empty，模板顶部挂提示；GtM8 删除整页 `industry-guard`、`checkIndustryApplicability`、`markNotApplicable`，改挂提示。`accountsFound` 取 `props.htmlData?.accounts_found`，自加载路径从 render-config 首个带该字段的 sheet 取。删除只被测试引用的 `useH5IndustryGuard.ts` / `useH7IndustryGuard.ts` 与 `useM8CrossSheet` 的 `isFinancialEntity`（同步删相应测试段，补提示组件与宿主的新测试）。H5 编制手册与对话框、H5TabIndex 的适用说明改为 CAS 27 油气资产（原文与 H7 生产性生物资产混写，把 1631 写成生产性生物资产）；`wp_surfaced_m.py` 的 M8 适用性条目改为按科目提示。

## 3. 生成弹窗与内置模板集（R2）

- 前端 `listGenerationTemplateSets` 只 `GET /api/template-sets`；`e2e/generation-plan-dialog-perf.spec.ts` 的 `EXPECTED_API` 去掉 seed，生成计划接口改具名常量，另断言夹具期间没有非 GET 请求。
- 新模块 `app/services/builtin_template_sets.py`：`seed_builtin_template_sets_safely(db)` 逐条在 SAVEPOINT 里插入，`IntegrityError`（并发首插撞 `set_name` 唯一约束）回滚该保存点后按已存在处理；`ensure_builtin_template_sets()` 自开会话、调用、提交，供启动任务用。`TemplateEngine.seed_builtin_template_sets` 改委托给它（端点、seed-all、启动三处同一实现、同一覆盖语义：编码集合与映射表不同即覆盖）。
- `startup_registry.STARTUP_TASKS` 在 `run_schema_drift_check` 与 `warm_render_caches` 之间加 `seed_builtin_template_sets`（phase=`seeds`，best_effort、singleton：热重载交接期间推迟到成为 primary 后才写）；冻结序列由注册表派生无需改，`test_reload_handoff` 的 singleton 集合同步。
- `POST /api/template-sets/seed` 依赖改 `require_role(["admin", "partner"])`；`template_library_mgmt._exec_seed("template_sets")` 改调同一函数，回报 inserted / updated。
- `test_template_engine` 三条「6 个内置集」的过期断言改为现行 1 个（标准年审，编码 = 映射表全部编码）。

## 4. 组别解释（R3）

- `@/types/projectClassification` 新增 `CATEGORY_CODES`（A、A1~A8、B、B1~B6、C）、`categoryGroupOfCode(code)`（只给 A1-11 表内“鉴证业务分类”等非项目字段用：登记码归组，空 / 未登记按 C）、`classificationOf(source)`（只认后端下发的 `project_classification` 或对象本身，不回退猜 `business_category`）与 `describeCategoryGroup(info)`（`A 类` / `A 类（A1）` / `C 类（分类未填写）`）。后端 `test_project_classification` 对拍 `CATEGORY_CODES` 与 `category_codes()`。
- 读者：WpPopupSigning（`isTypeA = group === 'A'`）、WpPopupChecklist（标签色与 C 类提示按组别）、GtA17Bundle（读 `proj.project_classification`）、GtA171AuditSummary（读 `project_context.project_classification`）、GtReviewChecklist（读 `context.project_classification`）都改调该函数；A1-11 签发表 `useA111Signing` 对传入值先折算组别（`'A1'` ⇒ A），`GtA111SigningForm.isSlotNA` 用同一结果；`useA111FormData` 预填只在 `!defaulted` 时写组别。
- 后端：`_a171_audit_summary` 的 project_context 加 `project_classification`（`resolve(原值).as_dict()`，原 `business_category` 字段保留）；`review_checklist_service.get_review_context` 加 `project_classification`（`business_category` 键保持原语义供 auto_na）；`a17_consistency_checker.is_a_class_or_listed` 改为 `resolve(cat).category_group == "A"`（中文旧别名照旧）。
- 棘轮：前端删 7 个文件条目（24 文件 / 34 处 ⇒ 17 / 26）；后端按现算下调。

## 5. 验证

| 风险 | 证据 |
|---|---|
| H5 仍按行业拦截 | 渲染单测：分类为 A1 / C / NULL 都返回 `responses_snapshot`、`tb_source_codes`、`accounts_found`；变异恢复 `industry_error` 早返回必红 |
| M8 仍整页拦截 | 宿主挂载测试：`project_info` 无行业时内容照常渲染、`accounts_found=false` 才出提示；变异恢复旧判定必红 |
| 删端点留下悬空 | 路由挂载 / 台账 / 原生 SQL 基线 / 鉴权基线测试；全仓 grep 0 调用 |
| 弹窗仍发写请求 | `generationPlanApi` 单测断言 post 未调用；性能夹具断言无非 GET；浏览器网络记录 |
| 启动 seed 失败或撞约束 | 单测：空表建「标准年审」、重跑无变化、并发首插第二个不报错；启动序列冻结测试 |
| 组别仍按精确码 | A1 / B3 / NULL 三组挂载测试（签字行数、标签色、C 类提示、A1-11 必签槽位）；变异改回 `=== 'A'` 必红 |

磁盘变异放副本或原地逐字节恢复；浏览器只用【测试】项目，结束经平台软删。

## 6. 风险与边界

- 不处理：项目行业来源（需产品定义）；模板集增删改端点只校验登录（同类全局写端点权限，另立 spec）；内置集被管理员改过的编码在启动时被映射表覆盖（与原端点语义相同）；按 readonly 角色的全局写拦截。
- 启动任务在任何经 `app.main` lifespan 的进程里对所连库做一次幂等写（数据一致时只有查询 + 空提交）。

## 7. 实施期现状勘误与追加裁决（2026-10-30）

### 7.1 同根静默缺数一并修复

现状 grep 与真实 render-config 复现证明，行业误用外还有三处同根“异常被上层吞成空数据”：

- H7 自 2026-07-09 起读取 `RenderContext` 不存在的 `sheet_name`，并把本页结果多包成 `{"sheets":[{"html_data":...}]}`，所以路由按页读取时恒拿不到 `html_data`；改为直接返回本页数据。计量模式不能继续硬编码 `cost`，否则一旦渲染接通就会在重载时盖掉用户选的公允价值模式，改从 `H7-measurement-model` 保存行读取并用 SAVEPOINT 隔离。
- M4 / M7 读取不存在的 `ctx.workpaper_id`，并 SELECT `checklist_responses` 不存在的 `evidence` / `status` 列。只修属性会让 PG 首条坏 SQL 把事务置为 aborted，因此一次改为 `ctx.wp_id` + 现有 `conclusion` / `remark` 列，并放进 SAVEPOINT。
- 增加全策略 AST 守卫：渲染策略只能读取 `RenderContext` dataclass 的真实字段；扫描器自带原 H7 / M4 形态的反向样本，防止“空结果但测试绿色”复发。

### 7.2 `accounts_found` 的两层语义

浏览器在全新【测试】项目上复现：H5 / H7 的 `account_chart` 为空时，语义解析器按既有 fail-open 契约保留 1631/1632、1621/1622 fallback 码，槽的 `found=True` 仅表示“有查询落点”；原实现据此把顶层 `accounts_found` 写成 `true`，提示不显示。裁决为：

1. 不改 `ResolvedSlot.found`、fallback 和四表预填查询口径，避免误伤既有消费者。
2. 顶层 `accounts_found` 统一经 `has_resolved_tb_rows` 检查本次 active `tb_balance` 实际行；匹配必须是等值或点号子科目，金额为 0 仍算存在。
3. 查询成功零行 = `false`；查询异常 = `null`（未知，前端不误提示）；解析码继续通过 `account_codes` / `tb_source_codes` 下发。
4. 全仓后端生产写入方只有 H5 / H7 / M8 三处，已全部改并加静态棘轮；嵌套槽的 `found` 仍保留“已定位查询口径”语义。

### 7.3 依赖与范围边界

- `seed_builtin_template_sets` 必须是 `singleton=True`；对应 `test_reload_handoff.py` 与 overlap reload 实现来自同一工作树中另一会话的未提交改动。本 spec 已同步测试并在当前候选树验证，但在这些依赖入库前不能声称干净 HEAD 可独立通过。
- 未扩范围：H5 导入导出 service 内部的提交 / `project_id` 持久化问题；`a21_review` 只校验登录的既有端点；`GtH7BiologicalAssets.vue` 的 `openReviewDialog` `console.log`；A1-11 外部 readonly 时仍显示“已完成签发”的既有文案；A17 合集请求未注册的 `GET /api/projects/{id}/kam-references` 返回 404（页面已捕获，组别显示不受影响）。这些不影响本 spec 的行业、seed、组别三条闭环，留后续权限 / 持久化 / UI 状态与 A17 KAM 接线治理。

## 8. 验收摘要（2026-10-30）

- 后端最终永久聚焦组 176 passed（其中 `test_industry_misuse_closure.py` + `four_table/test_semantic_account_resolver.py` 102 passed）；R2 / R3 文件组通过。前端最终永久聚焦组 8 files / 97 passed，其中新增四宿主挂载 16 passed；较宽选集 130 files / 1459 passed，4 个失败均在未改文件且 HEAD 同红。
- 变异：后端 26 + 7 个正向变异均在预期判据红，3 + 1 个阴性对照绿；每轮逐字节恢复 SHA-256。前端 18 个正向变异均在点名用例文件红，3 个阴性对照绿，内存 load hook 未改主工作区源文件。
- 浏览器【测试】项目生成 8 份目标底稿：H5 / H7 / M8 提示与正文通过；A1-11 / A1-12 / A17 组别显示通过；生成弹窗只发两个 GET、零本应用写请求。项目随后经平台软删，PG 对账 `is_deleted=true` 且 `deleted_at` 非空。完整明细见 tasks.md 验收记录。