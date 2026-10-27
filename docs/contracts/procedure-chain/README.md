# 程序链契约 v1（程序裁剪 → 底稿生成 → 委派 → 可见性）

给 Java 版实现用的接口与数据契约。Python 现行实现是参考实现：`backend/tests/contracts/test_procedure_chain_contracts.py`（SQLite，纯判定与服务层）和 `backend/tests/procedure_chain_e2e/test_procedure_chain_contracts_pg.py`（真实路由 + PostgreSQL 回滚事务）用同一组 schema 与 `cases/` 用例断言；Java 版复用这些文件，不另写一套口径。

来源 spec：`.kiro/specs/procedure-chain-hardening-and-java-contracts`（R22~R24）。改契约 = 改这里的文件 + 两边实现 + 用例，三者同一次提交。

## 文件

| 契约 | 内容 | Python 来源 | 接口 |
|---|---|---|---|
| `trimmed-scope.schema.json` | 粗裁结果快照、单码判定；粗裁预览 / 应用的请求与响应（`$defs`） | `procedure_scope_retention`、`procedure_trim_service` | `POST /api/projects/{pid}/procedure-trim/preview`、`/apply` |
| `generation-plan.schema.json` | 一次生成的四类分流 | `procedure_scope_retention.plan_generation` | （服务层） |
| `generation-receipt.schema.json` | 建底稿统一回执；按编码生成 / 模板集生成的请求与响应（`$defs`） | `wp_generation_receipt` | `POST /api/projects/{project_id}/working-papers/generate-from-codes`、`/generate` |
| `workpaper-lifecycle-event.schema.json` | 移入 / 恢复回收站事件；旧去向记录（`$defs`） | `workpaper_recycle_service`、V207 | 回收站列表「删除人」 |
| `program-row-identity.schema.json` | 程序行身份、定义、任务定位；「本人能改哪些行」响应（`$defs/rowAccess`） | `procedure_definition_importer`、`wp_visibility.program_row_guard` | `GET /api/workpapers/{wp_id}/program-row-access` |
| `delegation-preview.schema.json` | 委派预览请求与响应 | `procedure_delegation_service.preview` | `POST /api/projects/{pid}/procedure-delegations/preview` |
| `delegation-apply.schema.json` | 委派应用请求、响应与错误体 | `procedure_delegation_service.apply` | `POST /api/projects/{pid}/procedure-delegations/apply` |
| `member-scope.schema.json` | 成员有效循环范围 | `wp_visibility.effective_scope` | （服务层：可见性、委派校验、循环过滤） |
| `program-row-patch.schema.json` | 程序表行字段覆盖值批量写入 | `routers/wp_field_overrides` | `POST /api/workpapers/field-overrides/batch` |
| `workpaper-file-materialization.schema.json` | 底稿文件落盘、存量分类与 dry-run 汇总 | `wp_generate_file`、`workpaper_file_backlog` | `scripts/fix/report_workpaper_file_backlog.py` |
| `procedure-task-event.schema.json` | 任务 outbox 事件载荷、任务历史行 | `procedure_task_transition_service` | （outbox：`task_events`） |
| `common.schema.json` | 公共类型 | — | — |
| `openapi.procedure-chain.json` | 上述 8 个接口的 OpenAPI 子集（生成物，勿手改）：请求取自真实应用，响应 data 与错误详情挂到契约 | `scripts/gen/export_procedure_chain_openapi.py` | — |

## 校验方式

- 全部 schema 都是 JSON Schema 2020-12。文件里不写 `$schema`（IDE 会去下载远程元模式），方言由校验器指定：Python `jsonschema.Draft202012Validator`；Java 用 networknt `json-schema-validator`（2.x：`SpecificationVersion.DRAFT_2020_12`；1.x：`SpecVersion.VersionFlag.V202012`）。
- `$id` 前缀 `https://contracts.gt-plan.local/procedure-chain/v1/` 只作标识（不可访问）；相对 `$ref` 按 `$id` 解析，校验器里把这个前缀映射到本目录，不要去网上取。Python 见 `backend/tests/contracts/_contract_schemas.py`（`referencing` 注册表）；networknt 2.x 用 `SchemaRegistry.withDefaultDialect(SpecificationVersion.DRAFT_2020_12, b -> b.schemaIdResolvers(r -> r.mapPrefix(前缀, "classpath:contracts/procedure-chain")))`，1.x 是 `schemaMappers(m -> m.mapPrefix(…))`。
- 所有 2xx JSON 响应外层是 `{code, message, data}`（`common.schema.json#/$defs/responseEnvelope`），契约描述的是 `data`；错误响应是 `{code, message}`，`message` 就是错误详情（字符串或对象）；422 是 `{code, message, detail}`（`$defs/validationErrorBody`，不是 FastAPI 默认的 `{detail}`）。
- Python：`cd backend; python -m pytest tests/contracts -p no:playwright`（schema 自检、共享用例、服务层产物、OpenAPI 子集）；`tests/procedure_chain_e2e/test_procedure_chain_contracts_pg.py`（真实接口响应 + 同事务落库的行）另需 `DATABASE_URL` 指向 PostgreSQL（`GT_REQUIRE_PG=1` 时地址不是 PG 直接报错）。
- OpenAPI 子集：请求体、参数与鉴权取自真实应用（pydantic 模型）；这些路由返回普通 dict，FastAPI 生成的响应 schema 是空的，所以 2xx 的 `data` 与登记的错误详情 `$ref` 到本目录的契约，每个接口的 `x-contract` 写明对应的请求 / 响应 / 错误定义；组件按模型名命名。`python scripts/gen/export_procedure_chain_openapi.py --check` 只比对（按解析后的 JSON，不计行尾），不一致退出码 2 并逐处列出；不带参数时内容不变不改文件。路由或请求模型改了：重跑导出，再按 `tests/contracts/test_procedure_chain_openapi.py` 的请求比对把契约里的请求定义改成同样的字段与必填。

## 共享用例（`cases/`）

| 文件 | 断言什么 |
|---|---|
| `trimmed-scope.cases.json` | 由（编码, 状态）行建快照（规范形）与逐码判定 |
| `generation-plan.cases.json` | 粗裁行 + 已有底稿索引 + 待生成编码 → 四类分流 |
| `program-row-identity.cases.json` | definition_key 摘要、文本规范化、引用快照、两种程序号规范 |
| `member-scope.cases.json` | 系统角色 / 人员档案数 / 成员行 / 团队分配 → 有效循环范围；主管角色表 |
| `task-state-machine.cases.json` | 每条状态转换的结果、版本增量与历史；非法转换的状态码 |
| `workpaper-file-materialization.cases.json` | 路径原值 → 存量分类（不依赖本机文件的几类） |

## 粗裁判定

- 粗裁结果存在 `procedure_instances`：编码 = `coalesce(wp_code, procedure_code)`，状态 `execute` 保留、`skip` / `not_applicable` 已裁。同一编码多行，任一行 `execute` 即保留（与程序裁剪页显示一致）。
- 判定一个底稿编码：先规范化（去首尾空白、字母大写），再从编码本身往上逐级找母码（`B22A-4-1` → `B22A-4` → `B22A` → `B22`；`M4A` → `M4`；`G10` 不是 `G1` 的子表）；每一级先看同码的普通行，再看覆盖它的区间行（`D2-6至D2-13`，右侧可省前缀 `D2-6至13`）；第一个命中的行决定结果。一直找不到 ⇒ 保留。
- 区间码本身作为底稿编码：成员全部已裁才算已裁。两侧前缀不一致、终点小于起点、跨度超过 200 的区间行按普通编码处理。
- 读不到裁剪结果 ⇒ 生成、委派一律停止（503 `trim_scope_unavailable`），不得按「没有裁剪」继续。
- 粗裁应用联动：被裁的已生成底稿（主码、子表、程序表）两层移入回收站并写事件；有编制内容（保存过、人工填写、附件、复核意见 / 对话）的须 `confirm_substantive_recycle=true`，否则 409 零副作用（预览凭证不消费）；恢复执行只恢复「最后一次因裁剪移入」的底稿，只重开「最近一条历史是粗裁级联取消」的任务（重开为待委派，原执行人不保留）。

## 生成

- 七个入口（模板集 / 按编码 / 自定义单张与批量 / 链路编排 / IPO / B60 / 准则转换）都先经保留范围分流（`generation-plan`），再逐码在保存点里建底稿，回执同一结构（`generation-receipt`）。
- 回执措辞（`message`，各段用「；」连接，列举最多 10 个编码、超出写「等」，失败最多列 5 条原因）：`已生成 N 个底稿`；`N 个编码已有底稿，未重复生成：…`；`N 个选中的编码不在所选模板集里，未生成：…`；`N 个编码已在程序裁剪中标为不执行，未生成：…`；`N 个编码的底稿在回收站中，请从回收站恢复：…`；`N 个编码没有找到底稿模板，已建空白底稿：…`；`N 个编码生成失败：编码（原因）…`；表头未填上的说明；`N 份底稿生成时未写入表头（编制单位、审计期间等），需在底稿文件中另行填写`。

## 任务状态机（workflow × applicability）

工作流：`unassigned` → `assigned` → `acknowledged` → `in_progress` → `submitted` → `reviewed`；退回支路 `submitted` → `changes_requested` → `in_progress`；`cancelled` 与 `reviewed` 为终态。适用性 `execute` / `not_applicable` 与工作流正交（细裁 = 取消 + 置不适用；恢复 = 重开 + 置执行，必须重新委派、重新确认）。

| 动作 | 允许的前态 | 后态 | 角色 | 版本 | 其他条件 |
|---|---|---|---|---|---|
| assign | unassigned | assigned | 委派人 | assignment +1、lock +1 | 适用性须 execute |
| reassign | 非终态且非 unassigned | assigned | 委派人 | assignment +1、lock +1 | 理由 5~500 字；同一人为 no-op；要求重新确认 |
| set_reviewer | 非终态 | 不变 | 委派人 | lock +1 | 同一人为 no-op；不要求重新确认 |
| acknowledge | assigned | acknowledged | 执行人 | lock +1 | 已确认为 no-op；可带 expected_assignment_version |
| start | acknowledged / changes_requested | in_progress | 执行人 | lock +1 | 适用性 execute 且已绑定底稿 |
| submit | in_progress | submitted | 执行人 | lock +1 | 执行说明与证据快照必填 |
| request_changes | submitted | changes_requested | 复核人 | lock +1 | 退回原因 1~5000 字 |
| review | submitted | reviewed | 复核人 | lock +1 | 须有复核人；关联退回工单须全部关闭 |
| cancel | 非 reviewed | cancelled | （裁剪 / 方案） | lock +1 | 原因必填；已取消且适用性不变为 no-op |
| reopen | cancelled | unassigned | （裁剪 / 方案） | lock +1 | 清执行人与确认 / 开始 / 提交时间，复核人保留 |

所有成功转换同事务写：任务更新 + 任务历史（`from_status` 为真实前态）+ 有序 outbox（`aggregate_version = lock_version`）+ 精确投影。可带 `expected_lock_version` 做乐观锁（不符 409 `lock_version_conflict`）。

## 委派

- 预览：同步前置（导入当前版本定义 → 物化缺的行任务 → 绑定已生成底稿，在一个保存点里；前置失败 `preparation_ready=false` 且计数清零，程序错误照常抛出），已裁 / 在回收站的底稿不进目标，生成一次性凭证（TTL 600 秒，绑定请求哈希、目标版本、成员快照）。
- 应用：凭证校验顺序 = 存在 → 已消费（同一 request_id 返回上次结果）→ 操作人 / 项目 / 操作类型 → 未过期 → 请求哈希 → 成员快照 → 目标版本；任一不符 409 零写。默认整批原子（冲突 409 `delegation_conflict`）；`best_effort` 每任务保存点。
- 被委派人看不到目标循环 ⇒ 400 `out_of_scope`（凭证不消费）；带 `expand_scope` + `scope_reason` ⇒ 同事务只补缺少的循环并递增可见性策略版本。不是项目成员 ⇒ 400 `not_project_member`。人员档案没关联账号 / 账号停用 ⇒ 422。

## 鉴权口径

| 操作 | 判定 |
|---|---|
| 粗裁 / 细裁 / 委派 / 成员负载 | 项目委派人：admin，或唯一有效人员档案 + 本项目唯一有效团队分配，角色 ∈ 合伙人 / 签字合伙人 / 经理（含中文别名） |
| 生成底稿 | 项目成员 edit 级（admin 放行） |
| 底稿详情 / 渲染配置 / 编辑锁 / 程序行归属 | 底稿门：admin 全部；主管（见 member-scope）本项目全部循环；受限成员 = （当前委派 ∪ 委派历史）∩ 有效循环；看不见一律 404 `资源不存在或不可访问`（不暴露存在性），拒绝记一条 |
| 编辑锁 | 取锁 / 续期须能看见并可编辑；强制接管只给 admin / 主管 / 主编；活跃锁列表仅 admin；续期被拒先放掉本人的锁 |
| 程序表行编辑 | 全权（admin / 主管 / 主编）改全部行；受限成员只改派给本人的行，且只改执行状态与执行说明；「不适用」的进出只归委派人 |
| 删除人员档案 | 仅 admin；仍在项目团队里 409 列出项目，确认撤权后同事务软删分配与成员行并递增策略版本 |

## 事务边界

- 服务只 flush 不 commit，路由统一 commit；跨服务编排保持原子。
- 单码保存点：生成每个编码、覆盖值批量每一项、委派 best_effort 每个任务、粗裁读取。保存点失败只回滚自己。
- 独立连接写入（不随请求事务回滚）：操作日志、拒绝记录、哈希链审计；可见性失效通知经 outbox 同事务写、提交后投递。
- 只追加表：`workpaper_lifecycle_events`、`procedure_row_task_history`、可见性委派历史（触发器拒绝 UPDATE / DELETE）。

## 错误码

| HTTP | 错误 | 场景 |
|---|---|---|
| 400 | `row_delegation_rejected` / `lead_delegation_rejected` + reason（out_of_scope、scope_reason_missing、not_project_member、mapping_invalid、binding_conflict、invalid_request…） | 委派被拒；`cycles` 为缺少的循环 |
| 403 | 字符串 | 不是项目委派人 / 项目成员级别不够 / 强制接管无权 |
| 404 | `资源不存在或不可访问` | 底稿门拒绝（看不见、跨项目、不存在） |
| 404 | `预览凭证不存在` | 委派 / 裁剪应用 |
| 409 | `substantive_recycle_unconfirmed`（带 codes / substantive） | 粗裁会移入有编制内容的底稿而未确认 |
| 409 | `workpaper_still_trimmed` | 回收站恢复仍被粗裁的底稿 |
| 409 | `delegation_conflict`（带 conflict_task_ids） | 默认原子模式有冲突目标 |
| 409 | `lock_version_conflict` / `assignment_version_conflict`（带 expected / current） | 乐观锁 |
| 409 | `staff_has_assignments`（带 projects） | 删除仍在团队里的人员 |
| 409 | `LOCK_HELD`（error_code，带 locked_by / locked_by_name） | 编辑锁被他人持有 |
| 409 | 字符串 | 凭证已消费 / 不匹配 / 过期 / 被篡改 / 成员变化；目标版本已变化；非法状态转换 |
| 409 | `trimmed` / `recycled`（委派 reason） | 委派到已裁 / 在回收站的底稿 |
| 422 | 字符串或 pydantic 校验体 | 原因 / 理由缺失或超长、批量超 200 项、账号不可委派 |
| 503 | `trim_scope_unavailable` | 读不到粗裁结果，生成 / 委派停止 |

## 已知差异与未覆盖

- 模板集生成在请求内不填表头（如实计入 `header_unfilled`）。
- 回收站列表与恢复目前只按项目成员判，不按底稿可见性（受限成员能看到别的循环里的底稿名称）—— 待定口径，Java 版不要照抄，见 spec design §11.4。
- 委派预览文档里提到的 `materialization_pending` 已不再产生（前置同步完成），`status` 恒为 `ready`。
- OpenAPI 子集只收有响应契约的 8 个接口；细裁（程序行不适用 / 恢复）、任务状态转换、成员负载等接口的语义见上文，没有进子集。
- 转派的任务历史与 outbox 的 `from_status` 2026-10-27 起记转派前的真实状态（此前一律记 `assigned`）；更早的历史行不回填。
