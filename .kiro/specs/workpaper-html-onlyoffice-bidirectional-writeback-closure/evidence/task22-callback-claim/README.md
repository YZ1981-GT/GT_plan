# Task 22 证据：room callback claim / 流式下载 / delivery 去重 / request-first correlation / recovery case

spec: `workpaper-html-onlyoffice-bidirectional-writeback-closure` · Wave 2 Task 22
Requirements: 4.3, 4.9, 4.10, 5.1~5.8, 5.11, 5.12, 10.2, 10.3, 10.6~10.9
Properties: **P16 / P17 / P18 / P19 / P44 / P45 / P63 / P64**

## 〇、交接前提有一处与磁盘不符（先说这个）

交接说明写「Nothing from a prior attempt exists on disk; start clean」，**实况相反**：
磁盘上已有一次被中断的 Task 22 尝试 —— `callback_route.py`(454 行) /
`callback_download.py`(532 行) / `callback_delivery.py`(1488 行) 与
`test_task22_callback_claim.py`(47 KB)，mtime 18:15–19:03，本轮开工时间 19:30。

它**不是绿的**：`3 failed / 11 errors / 72 passed`。

处置选择了「审计 + 修完」而不是「删掉重写」，理由有三条：
① 这些文件在 git 里是 `??` 未跟踪，删掉**不可恢复**；
② 三个模块的职责切分、异常分型与 docstring 论证与 Task 22 正文逐条对得上，重写会丢掉这些；
③ 4 个失败的根因逐条定位后，其中 **2 个是真实生产缺陷**（见 §二），重写只会把它们换个位置再犯。

已按「未验证」重新对待每一行：全部判据本轮重跑，且新增真库层与变异层从零建立。

## 一、交付物

| 路径 | 作用 | git |
|---|---|---|
| `backend/app/services/workpaper_sync/callback_route.py` | claim/URL/room 绑定校验（durable 前第一道门）。本轮修 1 缺陷 + 拆 2 个异常类型 | `??` |
| `backend/app/services/workpaper_sync/callback_download.py` | allowlist / DNS 复核与 IP 固定 / 拒 3xx / 分离超时 / 流式上限。本轮修 1 缺陷 | `??` |
| `backend/app/services/workpaper_sync/callback_delivery.py` | delivery 去重、归属真值表、request-first correlation、recovery case。本轮修 4 缺陷 | `??` |
| `backend/data/onlyoffice_callback_state_contract.json` | 下载上限从漂移的 200 MiB 改回 Requirement 14.11 的 50 MiB | `??` |
| `backend/tests/workpaper_sync/test_task22_callback_claim.py` | 离线守卫 **90** 例（原 72 通过 + 修 2 + 新增判据） | `??` |
| `backend/tests/workpaper_sync/test_task22_callback_claim_pg.py` | **真实 PostgreSQL** 行为守卫 **50** 例（本轮新建） | `??` |
| `backend/scripts/diagnose/mutate_task22_callback_claim_guards.py` | **38** 条变异（本轮新建） | `??` |
| `backend/tests/workpaper_sync/test_task21_room_service.py` | 两处契约数值 pin 随 50 MiB 同步（`209715200` → `52428800`） | `M`（本就 `??` 目录内） |
| `mutation_report.json` | **38/38 RED**，零 GREEN / 零 ANCHOR-MISS / 零 WRONG-TEST | — |

基线：**140 passed**（90 离线 + 50 真库）。

> 🔴 全部产物在 git 里是 `??` 未跟踪（`backend/app/services/workpaper_sync/` 与
> `backend/tests/workpaper_sync/` 整目录如此）。**丢工作树即全部蒸发**，且挂进 CI 的 job
> 在干净 checkout 下会因文件不存在而挂。收口清单见 §八。

## 二、本轮修掉的 6 个真实缺陷（4 个只有真库能暴露）

| # | 位置 | 缺陷 | 后果 | 谁发现的 |
|---|---|---|---|---|
| 1 | `callback_route.extract_bearer_token` | 先 `strip()` 再判 `startswith("bearer ")`：`"Bearer   "` 被 strip 成 `"Bearer"`，不再以 `"bearer "`（含尾空格）开头 | 「只有 scheme 没有 token」那条 `raise` **不可达**，`"Bearer"` 字面量被当 token 送进 `jwt.decode`，拒绝理由从「缺 token」漂成「签名坏了」 | 离线守卫 |
| 2 | `callback_delivery.classify_delivery_ownership` | 兜底 `raise` 引用三个从未定义的名字（`has_app`/`has_rec`/`has_req`） | 「真值表缺行」抛的是 `NameError` 而非 `DeliveryOwnershipError`，调用方 `except SyncDomainError` 抓不住，缺行会以 500 出现在与归属无关的位置 | 代码审计 |
| 3 | `callback_delivery.__all__` | 列了两个**不存在**的名字（`CloseCaptureAmbiguousError` / `RouteParticipantAuthorshipError`） | `import *` 直接 AttributeError；按名字 grep「这条拒绝实现了吗」得到假阳性 | 代码审计 |
| 4 | `callback_delivery` 的 4 处 `sa.text(...)` | 把 UUID 以 **str** 绑给 uuid 列 | asyncpg 强类型：`operator does not exist: uuid = character varying` ⇒ **整条 `handle_callback` 在 PostgreSQL 上一次都跑不通**。离线守卫用 `__new__` 造服务对象，永远看不见 | **真库端到端** |
| 5 | `callback_download.assert_address_allowed` | `addr.is_reserved` 无条件拒。`ipaddress` 把 `::/8` 整段标成 reserved ⇒ `IPv6Address('::1').is_reserved` 为 **True**（IPv4 的 `127.0.0.1` 为 False） | 该行在「loopback/私网按 allowlist 条目裁决」**之前**触发，而本机 `getaddrinfo('localhost')` 首个返回 `::1`、`resolve_and_verify` 逐个地址校验 ⇒ 平台真实部署（`localhost:8080` / `host.docker.internal`）**一次 callback 都下载不下来**，同时让 loopback 放行分支变成死代码 | **真库端到端** |
| 6 | `callback_delivery.handle_callback` | pre-durable 就把 `operation_id=shell.id` 写进 delivery 行 | `trg_wpcd_operation_link` 是 **DEFERRABLE INITIALLY DEFERRED**，COMMIT 时才跑且读 operation 行的**当前**状态而 NEW 是 INSERT 当时的值 ⇒ correlation 一把同一 shell 绑成 primary，COMMIT 就报「未归组的 delivery 引用了已绑定 application 的 primary operation」并回滚整笔 ⇒ **成功路径必然失败** | **真库端到端** |

第 4/5/6 条合起来说明一件事：**这三个模块此前从未在 PostgreSQL 上跑通过一次**。
离线守卫 72 例全绿与此并不矛盾 —— 它们测的是纯函数与判据分支，而这三条都在
「服务层 ↔ 驱动 ↔ 库内 deferred trigger」的接缝上。

另有一处**配置漂移**（不算缺陷但同源）：契约 `streaming_size_cap_bytes` 首版写
209715200（200 MiB），是 Requirement 14.11「压缩 OOXML ≤50 MiB」的 4 倍。后果是下载门
**永远不会先触发**（`stage_incoming` 在 50 MiB 就中止），超限错误码指向 OOXML 预算而真因
是「下载没有界」。按 14.11「单一配置与测试锁死」改回 52428800，并把 Task 21 那条数值
pin 同步（它 pin 的是漂移值 —— 一条「断言真实数据仍有缺陷」的守卫）。

## 三、归属真值表：14 行 × 兜底约束 × 真库归因

`DELIVERY_OWNERSHIP_TRUTH_TABLE` 是 V151 的**可遍历投影**，每行自带 `db_constraint`。
下表的「真库归因」列是 `test_task22_callback_claim_pg.py` 实测出来的拒绝来源。

| 行 | state | `durable_at` | app | recovery | request | incoming | correlation | 裁决 | 兜底约束（实测归因一致） |
|---|---|---|---|---|---|---|---|---|---|
| T01 | received | ∅ | — | — | — | — | ∅ | **允许** | `ck_wpcd_durable_exactly_one_owner`（`durable_at IS NULL` 短路放行） |
| T02 | received | ∅ | — | — | ✓ | — | ∅ | **允许** | 同上（request-first 已绑定但未 durable ⇒ 保留 request、零 owner） |
| T03 | downloading | ∅ | — | — | ✓ | — | ∅ | **允许** | 同上 |
| T04 | rejected | ∅ | — | — | ✓ | — | ∅ | **允许** | 同上（AC 5.7 pre-durable 失败零 owner） |
| T05 | error | ∅ | — | — | ✓ | — | ∅ | **允许** | 同上（不得伪造 recovery/application） |
| T06 | durable | ✓ | ✓ | — | ✓ | ✓ | correlated | **允许** | 同上 —— **request 与 application 同时存在合法（不做 XOR）** |
| T07 | acknowledged | ✓ | ✓ | — | — | ✓ | correlated | **允许** | 同上（status 2 无 userdata 走 frozen-identity，request 可空） |
| T08 | unmatched | ✓ | — | ✓ | — | ✓ | unresolved | **允许** | `ck_wpcd_unmatched_zero_entities` |
| T09 | received | ∅ | ✓ | ✓ | — | — | ∅ | **禁止** | `ck_wpcd_no_double_owner` |
| T10 | durable | ✓ | — | — | ✓ | ✓ | correlated | **禁止** | `ck_wpcd_durable_exactly_one_owner` |
| T11 | durable | ∅ | ✓ | — | ✓ | ✓ | correlated | **禁止** | `ck_wpcd_durable_state_requires_fact` |
| T12 | unmatched | ✓ | — | ✓ | ✓ | ✓ | ∅ | **禁止** | `ck_wpcd_unmatched_zero_entities` |
| T13 | durable | ✓ | ✓ | — | ✓ | ✓ | unresolved | **禁止** | `ck_wpcd_ambiguous_zero_entities` |
| T14 | durable | ✓ | ✓ | — | — | — | correlated | **禁止** | `ck_wpcd_durable_requires_incoming` |

Task 22 正文逐字要求的三条语义，各自的正面证据：

* **`durable_at IS NULL` 可零 owner、禁双 owner** —— T01~T05 五个 state 各自真能插入（零 owner），
  T09 被 `ck_wpcd_no_double_owner` 拒；
* **durable fact 存在 ⇒ 恰属一类，post-durable error 保留 owner** —— T10（零 owner）被 XOR 那条拒；
  post-durable error 走真行实测：`state=error`、`response_error=0`、`durable_at` 保留、
  `application_id` 保留、`incoming` 保留，且**丢弃 owner** 与**清空 `durable_at`** 两个 UPDATE
  都被 `wpsync_check_delivery_durable_fact` 拒；
* **request/application 不做 XOR** —— T06 必须被**接受**（这是「不许错做成 XOR」的正面判据，
  只有禁止行时这条语义无法证伪）。

### 归因为什么必须逐行、且「只违反一条」

只断言「被拒了」不够：一行若被**另一条**约束偶然挡住，表里的归因就是错的，而下一个人会据此
以为「我声明的那条约束还活着」。所以：

1. 每个 forbidden 行都构造成**只违反自己那一条**（T09 刻意取 pre-durable 让 XOR 短路；
   T12 的 `correlation_result` 取 NULL 让 ambiguous 那条短路）；
2. 守卫断言「归因名 == `db_constraint`」**且**「报文里没有第二条 `ck_*`/`wpsync_check_*`」；
3. 6 条 V151 变异（M33~M38）逐条把某个 CHECK 削成 `CHECK (true OR ...)`，实测**只有**声明它
   的那一行翻成 accepted —— 这是「归因不是抄的」的唯一判据形态。为此给 6 个 forbidden 行
   各配了一个**独立命名**的测试（逻辑全部委派 `_assert_forbidden_row`，表仍是唯一真源）：
   参数化 nodeid 里的 `[T09]` 不是源码字面量，变异脚本的 `want` 定位不到，只能退化成
   「六个参数任一红即算命中」，那就丢掉了本任务的核心交付物。

`_blame()` 把拒绝分成 `unique / foreign_key / check_constraint / trigger_raise / probe_defect / other`。
`probe_defect`（42804/22P02 等）这一类是必需的：首轮 quarantine 探针漏了 `CAST`，报 42804，
若不分类就会被读成「trigger 工作正常」—— 典型 WRONG-TEST。

## 四、quarantined artifact 到不了 application / engine：三层 + 两条否证

| 层 | 落点 | 覆盖的绕过路径 | 实测结果 |
|---|---|---|---|
| ① 内存 | `assert_incoming_admissible_for_application`（`SealedIncoming` 对象） | 内存对象直传 engine，不经 DB | `quarantined_operation_forbidden` |
| ② 仓储 | `repo.assert_incoming_durable(artifact_id)`（读 DB 行） | 拿 artifact id 绕过服务层 | `SyncDomainError` |
| ③ 库内 | `wpsync_check_application_identity`（trigger） | 直接写 SQL 改 `application.incoming_artifact_id` | 拒绝，报文含 `durable` 要求 |

另加两条否证（都在真库上执行，都必须被拒）：

* `quarantined → durable`（release/解除隔离）—— 被 `wpsync_check_artifact_transition` 拒；
* `incoming → published` 与 `incoming → candidate` —— 被同一 trigger 拒。

以及一条「resolver 不可见」的**可测投影**：
`SELECT count(*) FROM representation r JOIN artifact a ON a.id=r.artifact_id WHERE a.kind='incoming'` **= 0**。
representation 是 resolver 的唯一入口，它不指向 incoming ⇒ resolver 拿不到 incoming。
（这是把「永不成为 resolver-visible substrate」变成可断言形态的办法；直接断言「resolver
不返回它」需要 Task 26 的 engine，本任务不在范围。）

安全门失败的完整形态实测：`text/plain` 伪装 xlsx ⇒ 轨迹只有 `sealed_quarantined`
（**无** `sealed_durable`）⇒ artifact `state=quarantined`、`durable_at IS NULL`、
`quarantined_at` 非空 ⇒ delivery `rejected`、`durable_at IS NULL`、零 owner ⇒
`response_error != 0` 且 `error_code` 非空。允许集实测恰好 `{download_only, expire, retention}`，
`QUARANTINE_FORBIDDEN_OPERATIONS` 九项逐条被拒。

## 五、request-first correlation / recovery / 失败语义（真库端到端）

一次完整 callback 走的是**生产同一条链路**（真 room + 真 participant lease + 真 confirmation +
真 frozen request + 真 xlsx 字节 + 真 sealing + 真 correlation），只有 HTTP 落点是可编程替身
（被测判据全在生产模块内，替身只提供字节与状态码）：

* 轨迹实测 `route_verified → status_resolved → plan_decided → request_bound →
  delivery_recorded → download_started → download_finished → sealed_durable → correlated → responded`，
  且断言 `request_bound < download_started`、`sealed_durable < correlated`、`route_verified` 在首位；
* `application_key` 等于「按 frozen request 各字段 + **实际下载并 sealing 后**的 incoming sha 重算」的值，
  且 application 行的 `incoming_sha256` 就是下载字节的 sha256（少了后半段，「key 用了另一个 digest」
  不会被发现）；
* winner shell 成为唯一 primary（`application_id` 非空、`duplicate_of_operation_id` 为空），
  room canonical fence（`latest_durable_application_id/latest_durable_sequence`）指向它；
* 下载侧实测：连接 URL 的 host 是**IP 字面量**（已校验 IP 固定给连接，不做第二次解析），
  `Host` 头保留原主机名，请求头**不含** `authorization`/`cookie`，`follow_redirects=False`、
  `max_redirects=0`，上限 = 50 MiB、超时 5s/30s。

**same incoming + 不同 frozen identity 不折叠**：7 个变体（baseline / base / representation /
bundle / authority / adapter build / generation）实测得 **7 个互不相同的 key**。另外把判据落在
**签名**上：`compute_application_key` 的参数集不含 `callback_status`/`status`/`request_id`/
`request_sequence`/`room_last_applied_version_id`/`delivery_*`。签名判据比「算一遍看变不变」强：
后者只证明当前实现没用它们，前者让「想把 status 塞进 key」必须先改签名（会被打红）。

**recovery case**（无 request 的 durable incoming）：
`response_error=0`、case `unclaimed`、**request/application/operation 三者全空**、
delivery `unmatched` 且 `forcesave_request_id`/`operation_id`/`application_id` 全空。
只读 participant 认领 ⇒ `recovery_claim_authorization_failed`，且 case 上三实体**仍然全空**
（两段一起断言：只断言抛错时，「抛错前已把 case 推进到 claiming 并写了 request」才是真缺陷；
只断言三实体空时，「什么都没发生」也恒真）。合法 claim ⇒ 一个事务内 request(`recovery_claim`) +
primary shell + application，`operation.application_id == case.application_id`、
`application.incoming == case.incoming`；同 Idempotency-Key 重放 ⇒ `cache_hit=True`、同 id，
库里 `recovery_claim` request 与其 application 各恰 **1 行**。download-only ⇒ `download_only` 终态，
三实体全空。

**失败语义**：durable **前**失败（transport 500）⇒ `response_error != 0`、`durable_at IS NULL`、
零 owner、保留已绑定 request、轨迹里**无** `sealed_durable`/`correlated`；durable **后**
已关联 operation 的处理失败 ⇒ `response_error=0`、保留 incoming 与 owner（Task 4 §5 实证 OO
返回非零**不会重发** ⇒ durable 后返回非零等于静默丢件）。

**forcesave 同 key 语义**：`(room, generation, participant, kind, key)` 全同且
`frozen_request_fingerprint` 等值 ⇒ cache hit 返回同一 request/operation；跨 participant /
跨 kind / payload 不等 ⇒ **409** 且异常文本**不含**旧 request/operation id（逐场景参数化，
合成一条时任一维度失效会被另两维遮蔽）。

> 三个冲突场景**绕过 room 资格门直接打仓储**。首轮用 `assert_can_initiate_request(kind=close_capture)`
> 构造 cross_kind，结果 room-policy 判据**先**抛 `RoomPolicyError` ⇒ 被测的幂等谓词一次都没跑到
> （假红）。一个场景只违反一个谓词：现在保持 freeze 完全等值，只改被测那一维。

## 六、变异检验：38/38 RED

`mutate_task22_callback_claim_guards.py --run all` ⇒ **38 RED / 0 GREEN / 0 ANCHOR-MISS /
0 WRONG-TEST**，`restored=True` 全条，`--check-anchors` 事后 38/38 OK、目标文件 md5 未变、
无 `.mutbak` 残留。

四类落点（缺一类就有判据盲区）：
① 服务层每条拒绝分支（M01~M19、M22~M30）；
② **V151 约束逐条削**（M33~M38）—— 归属真值表 `db_constraint` 归因的唯一判据形态；
③ 契约数值（M20）—— 锁死是两份配置的一致性，必须能从**契约侧**打红；
④ **已修缺陷回插**（M05/M21/M31/M32）—— 不配这类的话，「缺陷已被锁住」只是自述。

### 首轮 5 GREEN + 1 ANCHOR-MISS 的逐条归因与处置

| # | 首轮 | 归因 | 处置 |
|---|---|---|---|
| M04 | GREEN | **守卫缺陷** —— 「无密钥 fail closed」与「签名坏了」共用 `CallbackTokenSignatureError`：删掉那道门后 `jwt.decode(token, "")` 仍抛同类型 ⇒ 判据永久不可达 | 拆出 `CallbackSecretMissingError`，并断言两者互不为子类（否则 `pytest.raises` 会被继承关系放过） |
| M10 | GREEN → WRONG-TEST | **守卫缺陷** —— 同上形态：jose 自己也校验 `exp`，原用例的 token `exp` 早已过期 ⇒ jose 先抛，显式时钟判据被完全遮蔽 | 拆出 `CallbackTokenExpiredError`，并新增**隔离场景**：签一个 jose 眼里仍有效的 token（exp 在真实未来），把平台参考时钟推过 exp ⇒ 只有显式判据能拦 |
| M20 | GREEN | **守卫缺陷（不可见 ERROR 类）** —— 改契约数值后 `build_download_policy` 抛，用到 `policy` fixture 的用例变成 pytest **ERROR** 而非 FAILED，失败集合差集看不见 ERROR；PG 侧则整个 module collection ERROR | ①补一条不依赖 fixture 的**正向**断言（契约值 == 预算值）；②PG 采集把策略构造失败**记录**成阶段错误而不是穿透 ⇒ `test_no_phase_crashed_during_collection` 打红 |
| M24 | GREEN | **守卫缺陷（场景未隔离）** —— `want` 指的用例改的是 `url`，即使 digest 成分被削空，`url` 那一项照样把两者分开 | 新增只改 body 其余字段（url/userdata 逐字不变）的隔离场景 |
| M25 | GREEN | **守卫缺陷 + 一处实况纠正** —— `canonical_digest()` 摘的是整个 raw body，`status` 就在里面 ⇒ 外层 `callback_status=` 在**值**层面不可观测，任何「只改 status」的场景都注定 GREEN | 判据改为**接线等值**：`build_delivery_key(...)` 必须逐字节等于「拿 `payload.status` 显式调 `compute_delivery_key`」，再配一条「key 函数确实按 status 分行」防重言式。同时把 `compute_delivery_discriminator` 的 docstring 从「不含 status」改成如实描述 |
| M02 | ANCHOR-MISS | **脚本缺陷** —— 用绝对 `line=295` 消歧，而本轮给 `callback_route.py` 补了两个异常类后行号整体下移 | 改用相对定位（`scope='    value = raw["cbv"]'` + `offset=1`） |

M24/M25 顺带印证一条：**光把「同一投递重试要折叠」写成断言是不够的** ——
首轮 `test_network_retry_of_same_delivery_dedupes` 是红的，根因是 fixture 里
`_body()` 每次调用都生成新的随机 `userdata`，于是那条用例实际测的是「userdata 变了
discriminator 会变」，与「重签 token 不影响去重」毫无关系。判据被自己的 fixture 遮蔽。

## 七、辐射面回归：按引用关系反查，不跑全量

全量 `backend/tests` 有 1522 个测试文件，前台跑数分钟无输出会被当卡死。改用**引用关系反查**：
扫全部 `test_*.py` 对本轮改动物（三个模块、契约、`normalize_callback_status`、
`streaming_size_cap_bytes`/`max_compressed_bytes`、`record_delivery` 家族、V151、
`compute_application_key` 等）的实际引用，并入交接指定的 Task 12/15/16/18/19/20/21 文件
⇒ **25 个文件**。

结果 **1151 passed / 5 failed（3 分 34 秒）**。5 条全在
`backend/tests/test_onlyoffice_word_template_callback.py`，形态一律 `assert 404 == 200`。

**判为既存失败，与本任务无关，双证**：

1. **机制**：callback 端点是 `@public_router.post(".../onlyoffice-callback")`，而该文件的测试 app
   只 `app.include_router(router)`（5 处，无一处 `public_router`）⇒ 必然 404；
2. **HEAD 取证**：`git show HEAD:` 取出两侧原文 —— HEAD 的测试文件同样只
   `include_router(router)`，HEAD 的端点同样挂在 `public_router` 上 ⇒ HEAD 上同样 404。

顺带说明：这个文件之所以进辐射面，是我的反查脚本把测试函数名
`test_callback_download_failure_returns_error_1` 里的 `callback_download` 当成了对模块的引用
—— **假阳性**，该文件与本轮三个模块零耦合。宁可多扫不可少扫，故不收紧匹配。

Task 21 的证据 §十一 记录的同一家族（`public_router` 家族 50 条）与此一致。

## 八、没能验证的部分 / 收口欠账

1. **无生产消费方（结构性，非遗漏）**。三个模块目前只有守卫在 import，**没有任何 router
   调用它们**。这不是「additive 注入即死代码」的假绿，而是 spec 的分工：Task 22 正文第一条
   是「router 只委派」，而用户 API / callback service route 的 HTTP 面属 **Task 28**
   （`- [ ] 28. 建完整显式 scope sync router…`），`callback_route` 的 docstring 也写明
   「签发属 Task 25 / Task 28，本模块只验」。本任务能给的是**委派缝的结构判据**：
   `handle_callback` 入参只有原始传输层输入（header/URL/body）+ room 事实、无任何「已判定」
   语义参数、无 `participant_id`/`user_id`；同步域内只有 `callback_route` 解 callback token
   （`test_jwt_decoding_lives_only_in_callback_route`）。
   🔴 **在 Task 28 接线之前，不得声称 OO→HTML 回写在生产上可用** —— 生产 callback 仍走
   Task 4 characterize 过的旧路径（`wp_onlyoffice_router.post_sheet_onlyoffice_callback`，
   `write_bytes` 直写共享 canonical 文件、`claim_version=None`）。
2. **未起真实 OO 9.4 做两用户实测**。本轮的 callback body 形态取自 Task 4 的
   `callbacks.jsonl`（15 条真实 payload）但 HTTP 落点是替身。「真实 OO 的 forcesave 回调能被
   这条链路正确归组」的终局证据只有 Task 44/70 的真实 OO gate 能给。
3. **并发 create-or-hit 未做真并发**。`correlate_durable_incoming` 的
   `INSERT ... ON CONFLICT DO NOTHING` + `SELECT FOR UPDATE` 分支本轮只在**串行**下走过
   （winner 建 application、重放命中）。P18 要求的「并发 N 个 shell ⇒ 1 primary + N-1 direct
   terminal duplicate + 零 stranded」需要多连接并发压测，属 **Task 23** 的 sequence 收敛范围。
   本轮给到的是 `application_key UNIQUE` + `uq_wpso_request` 两条唯一约束与串行路径实测。
4. **close-capture 仲裁未实现**（属 Task 24）。本模块只**消费** room 里已存在的唯一 open
   close-capture request；`plan_correlation` 的 status=2 三分支（唯一/零个/多个）在离线守卫里
   逐条驱动过，但「exactly-one close-capture 真的只会有一个」由 Task 24 的 partial unique +
   reconciler 证明。
5. **`RouteCredential` 被当 contributor 传入**那条纵深防御仍不可达（Task 21 §十二.3 已记）：
   credential 是 uuid5，不可能等于任何 participant id。它由类型结构兜住
   （`RouteCredential` / `mint_route_credential` 里根本没有 user/participant 字段）。
6. **产物全部 `??` 未跟踪**，须尽快入库：
   `backend/app/services/workpaper_sync/`（整目录）、
   `backend/tests/workpaper_sync/test_task22_callback_claim.py`、
   `backend/tests/workpaper_sync/test_task22_callback_claim_pg.py`、
   `backend/scripts/diagnose/mutate_task22_callback_claim_guards.py`、
   `backend/data/onlyoffice_callback_state_contract.json`、
   本证据目录。**未入库前不要把对应 job 挂进 CI**（干净 checkout 下必挂）。
