# Task 27 —— 冲突预览 API、resolve fence、recovery-aware retry 与 opaque-version rollback

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 27
Requirements: 6.18, 8.1~8.12, 10.10
Properties: **P35 / P36 / P37 / P38 / P43 / P65 / P67**

## 交付物

| 文件 | 角色 |
|---|---|
| `backend/app/services/workpaper_sync/conflict_resolution.py` | 生产：preview / resolve / retry / rollback 的唯一编排入口 |
| `backend/tests/workpaper_sync/test_task27_conflict_resolution.py` | 离线守卫 **59** 条（纯判据 / 封闭映射 / AST 形态 / 欠账退役双向锁；含 parametrize 展开） |
| `backend/tests/workpaper_sync/test_task27_conflict_resolution_pg.py` | 真库守卫 **56** 条 / **16** 个场景（14 + `resolve_via_duplicate` + `resolve_authorization`） |
| `backend/scripts/diagnose/mutate_task27_conflict_resolution_guards.py` | 变异检验 **42** 条（跨行锚点） |
| `backend/app/services/workpaper_sync/oo_to_html.py` | 改动：裁决折叠落地 + 登记从 `deferred` 翻 `retired` |
| `backend/app/services/workpaper_sync/content_mutation.py` | 改动：唯一 commit 边界上**独立重算**折叠 |
| `backend/app/services/workpaper_sync/merge.py` | 改动：refresh 判据从 `MergeOutcome.merged` 切到真正落库的 projection |
| `backend/app/services/workpaper_sync/repository.py` | 改动：artifact 内容寻址幂等（rollback 正常路径）+ 冲突行读写 |

## Task 26 那笔欠账：已接线、闸门已撤、登记已退役

Task 26 收口审计抓到的第四个真实缺陷是「人工裁决被校验覆盖率之后丢弃」：
`apply_durable_incoming` 收下 `resolutions` 却把它丢掉，分派走无冲突分支发布
`MergeOutcome.merged` —— 而 `merged` 对**每个冲突字段保留 current 侧值**。审计师点
「取 incoming」，落库的是 current，而 extract 等值（两边同为错值）、roundtrip 与最终
fence 全部照常通过。Task 26 因此加 fail-closed 闸门
（`assert_manual_adjudication_not_wired`）并把欠账登记成 `DEFERRED_ADJUDICATION_CONSUMER`。

本任务把它接线，落点是**三层**（缺任何一层都退回静默错值）：

1. `oo_to_html.settle_adjudicated_projection()` —— 「发布哪份 projection」的唯一决策点，
   带裁决时走 `merge.apply_resolutions`；四条分支各有独立异常类型，互不遮蔽。
2. `content_mutation.ContentMutationService._settle_projection` —— 在唯一 commit 边界上
   **独立重算**同一个折叠并逐字节比对，折叠错/忘折叠一律 `AdjudicationNotFoldedError`。
3. `merge.projection_requires_client_refresh` —— refresh 判据从 `MergeOutcome.merged`
   切到真正落库的那份 projection（AC 8.12 末句），否则 client-confirmed 基线会被推进到
   客户端从未见过的内容上。

闸门函数已**撤除**，登记翻转为 `RETIRED_ADJUDICATION_CONSUMER`（`intended_status=retired`,
`retired_by_task="27"`，保留 `retired_fail_closed_gate` 字段）。**退役 ≠ 删除**：删掉之后
没人能证明欠账真的还了，也没人能发现它被悄悄退回去。双向锁死由两份脚本共同保证：

| 方向 | 变异 | 归属脚本 |
|---|---|---|
| 登记说 retired、接线却消失 | Task 26 **D13**（删 import）/ Task 27 **A01**（折叠退回 `merged`） | 两份都有 |
| 接线在、登记退回 deferred | Task 26 **D12** | Task 26 |
| 闸门函数偷偷回来（只加定义、行为不变） | Task 26 **D15** | Task 26 |
| 绕过唯一决策点 | Task 26 **D09** | Task 26 |
| 决策点在、但它不干活 | Task 26 **D10** | Task 26 |
| 裁决不再交到 commit 边界（第二把锁恒不触发，行为完全不变） | Task 26 **D11** | Task 26 |

2026-08-28 复核实测（`mutation_report_task27_reverify.json`）：Task 26 四文件基线
`491 passed`，D09–D15 + M40 + N06 **9/9 RED**。

## 四个 bullet → 判据落点

| bullet | 落点 | 关键判据 |
|---|---|---|
| 冲突预览（AC 8.1/8.2, P35） | `ConflictPreviewItem` 九要素 + 两个 fence 字段 | 真库 `preview` 场景逐项断言 JSON Pointer / OO 地址 / 三值 / kind / `value_type` 非空；分组按 sheet/table/row 且组键唯一 |
| resolve fence（AC 8.5, P36/P43） | 顺序判据在 Task 14 `conflicts.evaluate_resolve_fence`，本模块只读**服务端真值**并映射 HTTP | 五判定各一条真库场景：proceed / rejected / superseded / **fold 不 self-stale** / rebase；`fold` 落成功侧（<400），`superseded`=409 |
| 谁可提交裁决（AC 8.4） | 无编辑权限 → scope 授权门（403，与 404 分型）；复核锁定/归档/项目不可见 → 落地阶段最终 fence；权限 epoch → room fence | 三个理由各一条真库判据 + 「拒绝时零轨迹」+ application 落 `authorization_stale` 终态 |
| duplicate 请求（AC 8.5 末段, P38） | 四步读路径之后一律用 canonical primary 的 id | 真库 terminal duplicate 场景：预览返回 primary 的冲突、裁决折叠后发布、轨迹标在 primary 行上、零新建 operation/application |
| recovery-aware retry（AC 8.9, P38） | `assert_retry_operation_eligible` + 委派 Task 26 同一入口 | retry **无自己的执行体**（AST）；零 Command Service 符号；`operation_count`/`application_count` 逐个不变；`operation_id=NULL` 在任何资源查找前被拒 |
| opaque-version rollback（AC 8.7/8.8, P37/P67） | `/versions/{version_id}/rollback`，只认 immutable UUID | 跨 wp 同 numeric revision → 两个 UUID 无碰撞；越权与不存在共用一个 404 类型但带**可分辨内部标记** `refused_at`；`incoming`/candidate/staged 三种源各自被拒；projection 未变化 ⇒ **零写入 + revision 不变** |

**不在本任务**（据实登记，不冒充覆盖）：download-only 永零 operation 由 Task 22
`test_download_only_keeps_all_three_entities_at_zero` 证明；authorization-first claim
落成 primary/duplicate 由 Task 23 `test_recovery_claim_lands_as_primary_bound_to_the_same_application`
证明；本任务只负责「claim 之前普通 retry 必须拒」这一侧（D01/D02 + `retry_gate` 场景）。

## 本轮（2026-08-28 收口复核）修掉的生产缺陷：裁决「没落地也算成功」

**AC 8.4 / 8.5 / 8.6 / Property 43。这是本轮最贵的一处，且它是被「补 AC 8.4 的判据」逼出来的。**

先说事实链：AC 8.4 有三个独立拒绝理由（无编辑权限 / 复核锁定·归档 / 权限 epoch 变化），
此前只有第三个有判据。补前两个时发现 —— **复核锁定的 resolve 直接成功了**：
`conflict_rows_marked=1`、`http_status=200`，而 revision / version / entry pointer
一个都没动。

根因在两个模块的接口语义上：Task 26 的 `apply_durable_incoming` 在 incoming **已 durable**
之后**刻意不抛异常**（AC 5.7/5.8：durable 之后返回非零 ack 等于静默丢件），它把失败落成
`OoToHtmlResult.authorization_stale / error` 终态并保留 incoming。`resolve` 却把返回值
当成功用：直接写裁决轨迹并返回 `decision=proceed`。于是：

* 审计师看到「裁决成功」，实际内容一个字都没发布；
* 冲突行被标成「已裁决」——「已裁决」这条审计事实被记在一次没有发生的应用上（AC 8.6）；
* 触发面正是 AC 8.4 的复核锁定 / 归档 / 项目可见性 —— 这三样只活在 `AuthorizationProbe`
  后面，`RoomDurableFence` 读不到，所以 resolve **自己**那道 fence 拦不住。
  已有的 `resolve_initiator_revoked` 判据碰不到它（permission epoch 在 room fence 里）。

修法（三条，都在 `conflict_resolution.py`）：

1. `assert_resolve_apply_landed()` —— 模块级纯函数，落地态白名单
   `RESOLVE_LANDED_RESULTS = {applied, refresh_required}`（`refresh_required` 也算落地：
   内容已发布，只是 client-confirmed 基线不推进，AC 8.12 末句）；
2. 两个**分型**异常：`ResolveAuthorizationStaleError`（不可重试 ⇒ supersede/recovery）与
   `ResolveApplyFailedError`（可重试），各带 `apply_error_code` 保留**十条 fence 里的哪一条**；
3. rebase 分支同样自证，但白名单放宽一格（`REBASE_ADMISSIBLE_RESULTS` 含 `conflict`）——
   否则 rebase 的正常结果会被判失败；而失败终态必须原样透出，不得包成 409「刷新再来」。

判据：离线 11 条（逐终态参数化 + 封闭集合 + 全终态归类 + 分型 + 归因 + 调用顺序 +
两处调用点）+ 真库 6 条（AC 8.4 三个理由 × 拒绝语义、application 落
`authorization_stale` 终态、三次拒绝零轨迹）。变异 **H01~H05** 全 RED。

## 本轮补齐的覆盖空洞（一）

**duplicate 请求在 canonicalize 之后的 id 归属**（AC 8.5 末段 / P38）。

此前的证据链是：AST 形态判据证明 `preview`/`resolve` 确实走 Task 23 的四步入口，
Task 23 的真库判据证明 `read_operation` 会正确跟随 duplicate。两者都不覆盖
**canonicalize 之后本模块用的是哪个 id** —— 其余 13 个真库场景里 requested 恒等于
canonical，于是把 canonical 换成 requested 时一条判据都不会红。实测两种退化形态：

| 变异 | 退化形态 | 补场景之前 |
|---|---|---|
| **G01** 冲突改按 requested id 读 | **完全静默**：预览回 200 + `conflict_count=0`，审计师看到「没有冲突」，那些冲突永远不会被裁决，下一次 forcesave 又被 refresh-required 挡住 | `405 passed` 一条不红（GREEN，实测） |
| **G02** 裁决轨迹改按 requested id 回写 | **commit 后失败**：内容已发布、revision 已 +1，随后 `mark_conflicts_resolved` 抛 `ScopeIntegrityError` ⇒ AC 8.6 的轨迹整批丢失 + 一个与裁决无关的完整性错误 | 无 duplicate 场景 ⇒ 不可观测 |

补齐方式 = 真库场景 `resolve_via_duplicate` + `TestDuplicateRequestedOperation` 五条判据。
duplicate 用**真实的 status 6/2 多 delivery** 造：第二个 delivery 的 payload 与第一次
逐字节相同 ⇒ incoming sha256 相同 ⇒ application key 相同（key 不含 request id/sequence/
status，P64）⇒ 第二个 shell 落成 direct terminal duplicate。不手写 UPDATE 伪造 duplicate
指针 —— V151 的 `ck_wpso_duplicate_shape` / `wpsync_check_operation_duplicate_link` 会拒，
而绕过它们造出来的行根本不是协议里的形态。

## 本轮补齐的覆盖空洞（二）：载体替身的字节确定性 —— 一条**既有**判据原来靠运气

`_JsonCarrierAdapter.materialize()` 与 `_ooxml()` 用 `zf.writestr("name", data)` 写 zip，
而 `ZipInfo` 在这种写法下取 `time.localtime()`（**秒级**）⇒ **同一份内容在不同秒写出来
字节不同、sha256 不同**。本文件有两处判据依赖「同内容 ⇒ 同字节」：

| 依赖它的判据 | 需要的等值 | 不固定时的后果 |
|---|---|---|
| 新增 `resolve_via_duplicate` | 第二个 delivery 的 payload 与第一次逐字节相同 ⇒ 同 application key | 跨秒时根本造不出 duplicate |
| **既有** `rollback` + 变异 **R02** | 重新 materialize 的 representation 与历史那一份逐字节相同 ⇒ 走到 `register_artifact` 的内容寻址幂等分支 | 跨秒时路径不同 ⇒ 撞不到唯一约束 ⇒ R02 判 GREEN |

发现过程本身值得记：新场景第一版用「再调一次 `_ooxml()`」造同内容 payload，**连跑三次全绿**，
直到整套变异跑慢下来才炸（在 `expect_green` 对照项 **A09** 上表现为 WRONG-TEST）。修完
自己那处之后，**同一份代码**的 R02 又在 14 条一批的慢跑里翻 GREEN、在 19 条一批的快跑里
是 RED —— 那不是守卫缺陷，也不是生产缺陷，是**判据靠运气**。

修法两层：
1. `_zip_entry()` 给每个条目固定纪元时间戳（1980-01-01），确定性来自构造而不是时序；
2. 补一条**守机制本身**的判据 `test_the_carrier_payload_is_byte_deterministic`：直接断言
   每个 zip 条目的 `date_time == _ZIP_EPOCH`，而**不是**「跑两次比 sha」—— 后者在同一秒内
   恒成立，正是它让这个问题藏了这么久。
3. `_stage_world` 额外**返回**它用过的 payload 字节，需要「同一份 incoming 的第二个
   delivery」的场景复用同一份字节；并补两条前提自证（两行 artifact 不同 + 两个 digest 相同），
   于是「没造出 duplicate」会失败在原因上，而不是失败在某条无关断言上。

修后 R02 稳定 RED（三批全量复跑 + 一次单条复核，四次均 RED）。

## 变异检验

判定四态：RED（打红且正是预期那条测试）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点 0 命中或
>1 命中）/ WRONG-TEST（打红了但不是预期项）。**只看退出码会把后三态误判成 RED**；
`span.run_cli` 还会把 `expect_green` 对照项的 GREEN 映射成 tally 里的 RED，因此读报告必须
逐条看 `added`/`hit`，不能把 `tally.RED = N` 读成「N 条被打红」。

用 `_mutation_kit.span` 而不是 `cli`：①不落 `*.mutbak`（内存持有变异前字节 + sha256 还原
自证），与并发会话互不干扰；②本任务多条判据的**本体就是相邻两行的组合**（准入判据与
resolver 的先后、fence 判定与 coordinator 调用的先后），单行锚点在这些位置多处命中。

报告文件：

| 文件 | 内容 |
|---|---|
| `mutation_report.json` | 首轮 34 条（28 RED / 6 GREEN，对应当时代码，已过期） |
| `mutation_report_round2.json` | 补完覆盖后 D04/E01/E02/F02/F05 + E04 复核 |
| `mutation_report_c02.json` | C02 单条复核 |
| `mutation_report_g_block.json` | G01/G02 首次验证（H01 那条记录是**过期的**：当时替换体有语法错，见下） |
| `mutation_report_h_block.json` | H02–H05 首次验证 + H01 的语法错记录 |
| `mutation_report_h01.json` | H01 修正后单条复核 |
| `mutation_report_r02_recheck.json` | R02/G01/H01 在字节确定性修好之后的复核 |
| `mutation_report_final_a.json` | **权威**：A01–A09 / B01 / B02（+ C01/C02/C05 已被 `_b` 覆盖），14/14 |
| `mutation_report_final_b.json` | **权威**：C01–C10 / D01–D05 / E01，14/14 |
| `mutation_report_final_c.json` | **权威**：F01 / F02 / F05 / R02（+ 其余已被 `_d` 覆盖），14/14 |
| `mutation_report_final_d.json` | **权威**：E02–E04 / F03 / F04 / R01 / G01 / G02 / H01–H05，13/13 |

### 权威复跑的自检

`--run` 分批只是为了单条命令不超时（每批 13~14 条 ≈ 17 分钟），判定口径与全量一致
（覆盖面分母在各批 `added_files` 的并集上核对）。`_d` 与 `_b` 的存在是因为收口末尾又改了
`conflict_resolution.py` 的**模块 docstring**（把落地自证写进模块叙事）—— 按「每条的
`restored_sha256` 必须等于当前生产文件」这条自检，凡 `path` 指向该文件的 27 条全部重跑，
**同 id 以后写的报告为准**。2026-08-28 最终实测（42 个唯一 id）：

* 各批基线均 `428 passed`，失败名集合为空集（差集判定可信）;
* **42/42 RED**（去重后 42 个唯一 id），`restored=true` 42/42，无残留 `*.mutbak`;
* 除 `expect_green` 对照项 **A09**（`added=[]`，正是它该有的样子）外，每条的 `hit` 都命中
  自己声明的 `want`，没有靠「碰了文件就红」蒙过去的条目;
* 每条的 `restored_sha256` 等于当前生产文件 sha256（5 个文件全部相符）⇒ 这份判定描述的
  就是现在的代码，不是某个中间版本;
* 覆盖面分母 5 个守卫文件全部被命中。

### 一条**变异声明**自己的缺陷（不是守卫缺陷）

H01 首版把 `assert_resolve_apply_landed(` 换成 `_skipped = (`，于是后面的
`error_code=outcome.error_code` 成了元组里的关键字实参 ⇒ **模块 import 失败** ⇒ pytest 报
collection error 而不是测试失败 ⇒ `judge` 的失败名差集为空 ⇒ 判 **GREEN**。
指纹是运行时长 **4.2s**（正常一轮 ≈ 66s）。改成 `_skipped = dict(` 后同一条立刻 RED
（4 条命中）。**替换体必须语法合法**，否则「守卫有没有牙」根本没被测到。

### 回归类变异（真库实测修掉的缺陷重新注入）

| id | 缺陷 | 为什么离线全绿也拦不住 |
|---|---|---|
| **R01** | `_frozen_fence` 读手写 SQL 的错列名（`frozen_write_fence_epoch` 不存在） | `get_diagnostics`/vitest/离线守卫全绿，只有真库执行 `UndefinedColumnError`；改用 ORM 列引用后列名错误在 import 期就暴露 |
| **R02** | rollback 重新 materialize 出**逐字节相同**的 representation ⇒ 撞 `uq_wpa_relative_path` | 文件名是 `{generation:09d}-{sha12}`、新 content version 的 generation 又从 1 起 ⇒ 这是回滚的**正常**路径而不是边缘情况 |
| **D03**（正文里称 R03） | 准入判据排在 canonical resolver **之后** | resolver 的通用 `ArtifactNotPublishedError` 接住同一输入 ⇒ **行为上仍然拒绝**，但本域判据在所有可达输入上不可达（provably dead） |

另有两条首版判 GREEN、按项目规则**删除生产分支**而不是留一条恒 GREEN 变异的：D04 原锚
`version.revision > current_revision`（content version 与 `content_revision` 同事务推进 ⇒
该分支在任何可达状态下都不成立）；E01 原 want「两个 404 共用一个 code」（业务行那道门会
接住同一输入并抛同一类型 ⇒ 改成断言「拒绝发生在 `scope_index` 那一道」）。

## 辐射面与回归

按**真实 import** 反查（`from|import app.services|models.workpaper_sync` 或
`workpaper_sync_models`）得 **35** 个测试文件 = `backend/tests/workpaper_sync/` 目录内 32
（该目录共 34 个文件，另 2 个是不 import 生产模块的元判据）+ 目录外 3
（`test_onlyoffice_single_file_dockey.py` / `test_wp_html_save.py` /
`test_wp_onlyoffice_router.py`）。**不跑全量 `backend/tests`**（1522 个文件，前台无输出
会被当卡死）。实跑口径 = 整个 `workpaper_sync/` 目录 + 目录外 3 个。

2026-08-28 最终实测：

| 口径 | 结果 |
|---|---|
| `backend/tests/workpaper_sync/`（34 文件） | **2259 passed, 2 failed** |
| 目录外 2 个真消费方（dockey / html_save） | 31 passed |
| 目录外 `test_wp_onlyoffice_router.py` | 26 failed（单跑口径） |
| 五文件变异面基线 | **428 passed** |
| Task 26 四文件面 | **491 passed**（D09–D15 + M40 + N06 9/9 RED） |

那 2 + 26 条全部判为**先存红、非本任务引入**：

* `test_task21…contract_numbers_have_single_source_in_oo_contract` 与
  `test_task22…jwt_decoding_lives_only_in_callback_route` —— prompt 已列明，归 Task 24 的
  `command_service.py` / Task 30 的门;
* `test_wp_onlyoffice_router.py` 26 条 —— 失败形态是 legacy 路由端点 `404`
  （`/onlyoffice/health`、WOPI、callback），属 router 挂载面，本任务不注册任何路由；
  该文件在工作树里相对 HEAD 有 +100/−41 的并发会话改动；同类先存红另见 prompt 列明的
  `test_onlyoffice_word_template_callback.py` 5 条 `public_router` 404。
  （合跑时是 28 条 = 26 + 上面那 2 条。）

## 变异清单（42 条，按落点）

| 块 | id | 落点 |
|---|---|---|
| 一 裁决折叠（Task 26 欠账接线本体） | A01–A08 | 折叠函数、四条分支、Task 15 独立重算 |
| — 对照项 | A09 | `expect_green`：只改登记表文案，**应当不红** |
| 二 refresh 判据落点 | B01 / B02 | 判据从 `MergeOutcome.merged` 切到真正落库的 projection |
| 三 fence 接线 | C01 / C02 / C05–C10 | 服务端真值、五判定各自出口、封闭映射、fold≠stale |
| 四 retry / rollback 准入 | D01–D05 | nullable-operation 闸、源准入不被 resolver 遮蔽、乐观锁、零写入 |
| 五 统一 404 + frozen contract | E01–E04 | scope 门先于业务行、两道门可分辨标记、contract digest 锁 |
| 六 冲突落行与轨迹 | F01–F05 | 落行、supersede 而非删除、未知裁决拒绝 |
| 七 回归（真库实测缺陷） | R01 / R02（+ D03） | 错列名、内容寻址幂等、准入判据被遮蔽 |
| 八 canonicalize 后的 id 归属 | G01 / G02 | 冲突读侧 / 轨迹写侧 |
| 九 裁决落地自证 | H01–H05 | 摘掉自证、放宽白名单、终态合流、rebase 白名单、丢归因 |

## 已知窗口（据实登记，不掩盖）

裁决轨迹（`_record_resolution_trail`）与内容 commit **不在同一事务**：唯一 commit 边界在
Task 15，它的同事务挂点 `after_pointers` 属 Task 26 的 fence hook。进程若在两者之间崩溃，
会留下「application=applied 而 `conflict.resolved_at IS NULL`」这一**可检测且可修复**的
不一致（application 上有 `merged_projection_sha256` 可复算）。刻意**不用** `except` 吞掉
失败 —— 那才会让轨迹缺失变成静默。
