# Task 26 —— OO→HTML coordinator、最终授权 fence 与 canonical rematerialization

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 26
Requirements: 2.9, 4.2, 4.3, 4.5, 4.6, 4.11, 4.12, 5.8, 6.8, 6.9, 6.11, 8.9, 8.10, 8.11, 8.12, 10.10
Properties: P14 / P19 / P25 / P26 / P27 / P29 / P38 / P43 / P62 / P65

## 交付物

| 文件 | 角色 |
|---|---|
| `backend/app/services/workpaper_sync/oo_to_html.py` | 生产：唯一 OO→HTML 编排入口 |
| `backend/tests/workpaper_sync/test_task26_oo_to_html.py` | 离线守卫（纯判据 / AST 结构判据 / 轨迹 / merge 语义 / roundtrip） |
| `backend/tests/workpaper_sync/test_task26_oo_to_html_pg.py` | 真库守卫（rematerialize / fence / 双基线 / retry / 三层拒绝） |
| `backend/scripts/diagnose/mutate_task26_oo_to_html_guards.py` | 变异检验（70 条，跨行锚点） |
| `backend/app/services/workpaper_sync/merge.py` | 改动：`RETIRED_DEFERRALS` 追加本任务的 merge 消费方登记 |
| `backend/tests/workpaper_sync/test_task14_merge_conflicts.py` | 改动：消费方判据从「恰一个」升级为「登记表 ↔ 事实双向锁死」 |
| `backend/tests/workpaper_sync/test_task15_content_mutation.py` | 改动：共享登记表的第二个消费方守卫从全局等值判据改为归因型 |

## 判据分布

* **substrate 来源唯一**（AC 4.3 / 8.10）—— 只认 `application.incoming_artifact_id`。
  「不得猜」禁止的是**代码形态**（猜错的实现在运行期照样能读出一个文件），故由
  `assert_substrate_resolution_source_shape()` 做 AST 反查：被禁属性名 + repository
  调用白名单 + 必须真的出现 `incoming_artifact_id`。
* **三层拒绝 quarantined** —— DB / coordinator 入口 / engine 各一个**不同**异常类型。
  真库守卫 `test_coordinator_layer_is_not_shadowed_by_the_db_layer` 专门证明中间层
  不是冗余：准入判据排在 `assert_incoming_durable` **之前**，否则本层的 quarantine
  分支 provably-dead（R03 就是这条的回归变异）。
* **最终授权 fence**（AC 10.10 / P43）—— 十条逐条独立，各一个 `error_code`；
  `assert_final_authorization` 返回**实际比较过的项名序列**，于是「把某条挪走」
  也能打红。两道回调（publish 前 / 写库前）都跑，`_REQUIRED_FIRST_ASSERTION`
  用 AST 钉死轨迹前置断言必须是回调体第一条语句。
* **双基线裁决**（AC 2.9 / 4.11 / P62）—— `settlement_digest_pair` 把 Task 14 的
  **受管字段级**等值裁决翻译成 Task 21 的 digest 对，避免「Task 15 没标 refresh、
  Task 21 标了」的半状态（Word 底稿 + 金额格式上两个口径会分叉）。
* **incoming 永不晋升**（P65）—— 判据落在**数据库行**上：commit 后重读 incoming 行，
  逐列核对 `kind/state/published_at/relative_path/sha256` 未变；result representation
  指向的 artifact **行**必须与 incoming 不同行、不在 `.incoming/` 下。
  只比 sha256 是弱代理（内容寻址下 merged 恰好复现 incoming 字节完全可能）。

## 变异检验

判定四态：RED（打红且正是预期那条测试）/ GREEN（守卫缺陷）/ ANCHOR-MISS（锚点未命中或
命中 >1）/ WRONG-TEST（打红了但不是预期项）。只看退出码会把后三态误判成 RED。

跨行锚点 + `scope`/`offset`，不用绝对行号。用 `_mutation_kit.span` 而不是 `cli`：
后者用全仓 `*.mutbak` 扫描做前置门，会与并发会话的在途变异互相冲掉；`span` 在内存里
持有变异前字节、退出时按 sha256 逐文件核验还原。

报告文件：

| 文件 | 内容 |
|---|---|
| `mutation_report.json` | 第一轮 56 条（对应当时的 `oo_to_html.py`，已过期） |
| `mutation_report_registry.json` | M39/M40（`merge.py` 登记表，文件未变，仍有效） |
| `mutation_report_defects_a.json` | D01–D04（第二轮审计抓到的缺陷回归） |
| `mutation_report_defects_b.json` | D05–D08（同上） |
| `_chunk1.json` | M01–M16 在第二轮修复后的复核 |
| `mutation_report_defects_c.json` | **D09–D14**（第三轮审计抓到的缺陷④回归，6/6 RED） |
| `mutation_report_full_r3.json` | **权威**：全 70 条对当前代码的完整复跑（2026-08-27 20:22） |

### 为什么必须整轮复跑

`restored_sha256` 是每条变异记录里的还原后校验值。第一轮 `mutation_report.json` 里
`oo_to_html.py` 的 `restored_sha256` 与当前文件不符 ⇒ 那 31 条（M17–M25 / M30–M38 /
C01 / C02 / R02–R05 / N01 / D01–D04）是对**已被改过的旧版本**做的判定，不能继续当证据。
第三轮修完缺陷④后文件再次变化，因此 70 条全部重跑。

**自检判据**：`mutation_report_full_r3.json` 里每条的 `restored_sha256` 必须等于当前
生产文件 sha256。实测 70/70 相符、`restored=true` 70/70、无残留 `*.mutbak`。

### 结果

```
tally      : {"RED": 70}      ← 68 条真打红 + 2 条对照项按预期保持绿
GREEN      : 0                ← 无守卫缺陷
ANCHOR-MISS: 0                ← --check-anchors 亦为 70/70 OK
WRONG-TEST : 0                ← 每条的 hit 集合都包含它声明的 want
STALE      : 0
```

🔴 **读 `tally` 时的陷阱**：`span.py:369` 对 `expect_green=True` 的对照项做
`verdict = RED if verdict == GREEN else WRONG_TEST` —— 也就是说 `verdict` 字段的语义是
「**是否符合预期**」，不是「是否变红」。C01/C02 的 `summary` 是 `482 passed`、
`added: []`，它们**没有**打红，而这正是对照项的正确结果（证明判定不是「只要改了文件
就红」）。把 `tally: {RED: 70}` 读成「70 条全部打红」会高估两条。

真打红的 68 条按生产文件分布：`oo_to_html.py` 55 · `content_mutation.py` 7 ·
`merge.py` 5 · `conflicts.py` 1。

## 辐射面测试

改动的生产文件只有 `oo_to_html.py`（`content_mutation.py` / `merge.py` / `conflicts.py`
的 sha256 与上一轮报告记录一致 ⇒ 未改）。按**真实 import** 反查它的消费方：只有两个
Task 26 测试文件（`app/services/workpaper_sync/__init__.py` 零 import 语句，仅 docstring
提及），因此辐射面即变异面的四个文件。

| 口径 | 结果 |
|---|---|
| 四文件（变异面 = 冻结基线） | **482 passed** |
| `backend/tests/workpaper_sync/` 全目录 | **2135 passed, 2 failed**（两条先存在的红，见下） |

两种口径的四文件数一致（129 + 96 + 178 + 79 = 482，与合并跑相同）。

## 生产缺陷（本任务实际修掉的）

### 缺陷① `EligibilityEpochAdvancedError` 是重言式

`room.close_leader_eligibility_epoch` 是 bigint、server_default 0、全仓库唯一写入点
只做 `+1` ⇒ 永远非负，而判据当时写的是 `if int(...) < 0` ⇒ 分支 provably-dead，
`compared` 返回值却报着 `close_leader_eligibility_epoch`，向调用方宣称已重验。
修前 S17 的结果是 `applied`：leader 在 promotion 之后失格，内容照样提交。
回归变异 **D03/D05**。

### 缺陷② 「同一 frozen application 只应用一次」没有任何判据

`FrozenApplicationIdentity.state` 被逐列冻结却从未被消费。真库实测：对已 `applied`
的 application 再调一次会**跑完整条 pipeline**（三侧 extract + materialize 写出新的
staged result + 未管理区域比对，adapter 调用 6 次），直到写库才撞出一个不带业务语义的
`StateTransitionError`；而 `_record_post_durable_failure` 自己也要走 `applied → error`
（同样非法）⇒ 异常穿透入口，timeline 零 event。
没有观测到第二个 business revision —— 但那份保护是**偶然的**：它依赖
「`APPLICATION_EDGES[applied]` 恰好是空集」这个与 AC 4.3 无关的事实。
回归变异 **D01/D02**。

### 缺陷③ AC 10.10 末句「并 supersede/recovery」缺失

`reconcile_close_intents` 见到 `state=promoted` 就提前返回并把这条路显式交给最终
fence，所以 fence 不 supersede 就没有第二个人会做：room 停在 `close_barrier`，
clean close 永远等不到内容，UI 只能无限 loading（违反 Property 63「不能永久 blocked」）。
回归变异 **D07/D08**。

### 缺陷④ 人工裁决被「校验覆盖率后丢弃」（第三轮审计发现）

**修前形态**（两处一起才构成缺陷）：

1. 分派写 `if merge.has_conflicts and not resolutions:` ⇒ 带裁决时走**无冲突分支**；
2. 无冲突分支提交 `merge.merged` —— 它对每个冲突字段保留 **current 侧**值
   （`merge.py` 模块头原文：「merged 保持 c 并把三值原样写入冲突记录，由人工裁决
   `apply_resolutions` 收敛」）。

而 `merge.apply_resolutions` 在本模块**从未被 import**（AST 判据：既不在 imported
也不在 called），Task 15 的 `_settle_projection` 又只用 `assert_all_conflicts_resolved`
校验裁决**覆盖**了每条冲突、覆盖通过后返回的仍是那份未收敛的 projection。

**后果**：审计师点「取 incoming」，落库的是 current；而
`MergeOutcome.requires_client_refresh(incoming)` 同样读 `self.merged`，
连「要不要让编辑器重载」都按错值算。四道关全绿 —— 覆盖率校验过、extract 等值两边
同为错值必等、未管理区域无关、最终 fence 只看授权与身份。当时**没有任何测试**
传过非空 `resolutions`，所以整条分支从未被执行。

**修法分两层**（各自可证伪）：

* 结构层：分派不再读 `resolutions` ⇒「带裁决走无冲突分支」不可能。
  判据 `test_resolutions_is_read_only_by_the_guard`（AST：`resolutions` 在入口函数体里
  只能作闸门实参）。回归变异 **D14**。
* 闸门层：入口 `assert_manual_adjudication_not_wired()` 显式 fail closed ⇒
  「静默忽略裁决」不可能。回归变异 **D09**（删调用点）/ **D10**（短路判据体）/
  **D11**（挪到 bundle 加载之后，证明「立即失败」这半句有自己的判据）。

**为什么是 fail closed 而不是在本任务里接线** —— 正确的 resolved 路径还需要把 refresh
判据从 `MergeOutcome.merged` 切到 resolved projection（要动 Task 15 的
`_settle_projection`/`_advance_room` 口径），并配 resolve fence（expected revision /
canonical application identity / effective sequence / conflict digest）与 409 映射；
整体属 Task 27 的 AC 8.5/8.10–8.12。本任务正文只承诺「**无冲突**时…重写 merged
projection」。欠账登记在 `oo_to_html.DEFERRED_ADJUDICATION_CONSUMER`，与
`assert_manual_adjudication_not_wired` **双向锁死**（登记说接了却没接 ⇒ D12 打红；
接了却没退役登记 ⇒ D13 打红）。

## 已知遗留（不属本任务，未修）

* `backend/tests/workpaper_sync/test_task21_room_service.py::test_contract_numbers_have_single_source_in_oo_contract`
  与 `test_task22_callback_claim.py::test_jwt_decoding_lives_only_in_callback_route`
  两条**先存在的红**。归因不是靠推断，而是直接复算两条守卫自己的 offender 判据：

  ```
  guard 1（契约字面量单一来源）: OFFENDER command_service.py ['forcesave_callback_wait_timeout_seconds']
  guard 2（jose 使用者）      : OFFENDER callback_route.py（合法）, command_service.py（超出期望）
  ```

  两条的 offender 列表里都**没有** `oo_to_html.py`；唯一超出期望的都是
  `command_service.py`（Task 24 的交付物）。属 Task 24 对 Task 21/22 守卫的欠账，
  应由 Task 30 的门收口，本任务不动它（改它等于替 Task 24 裁决契约读取口径）。

  ⚠️ 这两条红在跑变异时**不会**出现：变异面只含四个文件，两条守卫都不在其中。
  也就是说 Task 26 的冻结基线（482 passed）是干净的，但「workpaper_sync 全目录绿」
  这件事在 Task 24 收口前不成立。
* `assert_substrate_resolution_source_shape()` 的第 1 条判据用的是**子串**匹配
  （`name in src`）。今天成立（被禁的是属性名，docstring 里只有中文散文），但若有人
  在 docstring 里逐字引用某个被禁属性名来解释「为什么不许读它」，这条判据会永久变红
  —— 与 R05 修掉的那个形态同源。留作观察，本任务不动（改它会牵动多条锚点）。
* `oo_to_html.py` 目前**没有生产调用方**（用户端 router 是 Task 28、resolve 是 Task 27）。
  它非死代码这一点当前由 `merge.RETIRED_DEFERRALS` + Task 14 的「merge 域恰一个生产
  消费方且正是本模块」双向判据背书；Task 28 接线后应翻转成真实调用链判据。
