# Implementation Plan: 底稿 HTML ↔ OnlyOffice Excel/Word 双向回写收口

## Overview

本计划共 74 个任务、8 个 Wave。Task 1/2 的 `[x]` 只表示 discovery/characterization 已完成，不表示 adapter、DOM 或真实 OnlyOffice 闭环完成；Task 20 的 `[x]` 同型 —— 它表示「门可信 + 当期红基线冻结」，14 条准则的归零动作分别归属 Task 74 与 Task 71。当前暂停生产开发，先按修订后的 DAG 从 Wave 0 Task 3 继续。

实施顺序遵循四个硬约束：

1. 所有 HTML/upload/WOPI/OO/custom writer 未进入统一 business content revision，且 business revision/representation generation 未分离前，不允许批量 adapter 迁移。
2. Excel identity、Word tagged SDT、真实两用户 callback/撤销语义、Windows staged publish 四个真实 probe 未通过前，不允许建设依赖对应假设的通用 engine 或 participant attribution shortcut。
3. forcesave/close 必须先冻结 request base/sequence/definitions/write fence；merge/resolve 必须 canonical rematerialize + extract 等值，merged≠incoming 时 refresh/reopen，不能只提交 JSON、直接发布 incoming或推进伪 client base。
4. 每个 bidirectional entry 必须有持久化 sync test run、逐 scenario operation/version/representation/trace bundle 与服务端重算 evidence；pilot/单 operation 不替代逐 entry 验收。
5. 全局 legacy 删除必须晚于 Task 70 逐 entry 真实 evidence gate；Task 66 只做删前清册、隔离与 rollback plan，不执行全局删除。

**并发边界**：本 spec 不读取、修改、暂存或带入 `backend/data/amount_input_migration_status.json`。每个 Wave 开始前重新扫描迁移号、active spec mtime 与共享文件归属。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 0,
      "name": "事实清册、writer inventory 与真实技术探针",
      "tasks": ["1", "2", "3", "4", "5", "6", "7", "8"],
      "depends_on": [],
      "rationale": "先把「现在到底有多少入口、各自什么能力、谁在写盘」变成可复算的清册，再谈迁移。入口 manifest 与 writer inventory 是后续每一波的分母；技术探针（OO 9.4 行为、SDT 保真、instrumentation 可行性）先取证，避免把假设写进设计"
    },
    {
      "wave": 1,
      "name": "统一内容版本、artifact、contract、merge 与 writer 迁移",
      "tasks": ["9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "73"],
      "depends_on": [0],
      "rationale": "统一内容版本域是双向回写的地基：没有单一 canonical 指针，两侧就各写各的。artifact/contract/merge 三件必须同波，因为 merge 的判据要引用 contract 声明的字段级归属。Task 73（entry profile）在此波承接，供后续按 profile 分波"
    },
    {
      "wave": 2,
      "name": "room/participant、durable callback、双层幂等与 coordinator",
      "tasks": ["21", "22", "23", "24", "25", "26", "27", "28", "29", "30"],
      "depends_on": [1],
      "rationale": "OO → HTML 这一侧的生命周期：doc_key 由 room 身份派生（不再靠 mtime，否则任何写盘都切断协同会话）、callback 必须 durable ack、幂等要双层（application 与 protocol）。全部依赖 Wave 1 的内容版本域已统一"
    },
    {
      "wave": 3,
      "name": "统一前端 descriptor/bridge 与 Excel engine",
      "tasks": ["31", "32", "33", "34", "35", "36", "37", "38", "39"],
      "depends_on": [2],
      "rationale": "前端 launch descriptor 与 bridge 要消费后端下发的能力态与 room 身份，故依赖 Wave 2。Excel engine（instrumentation / materialize / extract / verify）在此波成形，为 Wave 4 的四个 pilot 提供共用底座"
    },
    {
      "wave": 4,
      "name": "四类 Excel pilot、真实 OO 9.4 gate 与平台级发布链补齐",
      "tasks": ["40", "41", "42", "43", "44", "45", "75", "76", "77"],
      "depends_on": [3],
      "rationale": "四个 pilot（simple checklist / 大 JSON / 分组动态 / 两级表头）覆盖四种结构形态，是 engine 的最小可证集合。Task 75/76/77 补齐「published representation → frozen definitions」的公共观测器与 provisioner —— 没有它们，后续全量 lane 的 adapter 注册只能靠登记态而非请求路径实跑"
    },
    {
      "wave": 5,
      "name": "Excel 全量 lane 与 Word F2 pilot lane",
      "tasks": ["46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "58", "59", "60", "61"],
      "depends_on": [4],
      "rationale": "全量铺开必须在 pilot 已真实 OO 验收之后，否则是把未证的机制批量复制。Excel 与 Word 两条 lane 并行推进：Word 走 SDT 结构化岛，与 Excel 的显式契约是两套判据，不共用"
    },
    {
      "wave": 6,
      "name": "Word 全量、custom、legacy 删前隔离与 pre-reconcile",
      "tasks": ["62", "63", "64", "65", "66", "67"],
      "depends_on": [5],
      "rationale": "删 legacy 之前必须先做结构性对账（pre-reconcile）：哪些 legacy 对象真的无人消费、替代面是否已入库。顺序反了就会删掉仍在生产路径上的东西"
    },
    {
      "wave": 7,
      "name": "独立验证、逐 entry evidence、全局 legacy 删除与归档",
      "tasks": ["68", "69", "70", "71", "72", "74"],
      "depends_on": [6],
      "rationale": "最后一波才允许真删：先独立回归、再逐 entry 取证据、再按 Wave 6 的清单精确删除、删后全场景重验。Task 74（writer/version domain 归零）压在此处，因为它的 14 条准则要在全部迁移落地后才可能同时为零"
    }
  ],
  "dependencies": {
    "1": [], "2": ["1"], "3": ["1", "2"], "4": ["1", "2"],
    "5": ["1", "2"], "6": ["1", "2"], "7": ["3"], "8": ["1", "2", "3"],
    "9": ["3", "4", "7", "8"], "10": ["9"], "11": ["7", "9", "10"],
    "12": ["3", "11"], "13": ["8", "12"], "14": ["10", "13"],
    "15": ["3", "10", "11", "12", "13", "14"], "16": ["9", "10", "15"],
    "17": ["5", "11", "12", "13", "15"], "18": ["15", "16"], "19": ["15", "16", "18"],
    "20": ["3", "18", "19"], "73": ["1", "13"],
    "21": ["4", "9", "10", "12"], "22": ["4", "9", "10", "11", "21"],
    "23": ["9", "10", "14", "21", "22"], "24": ["4", "21", "23"],
    "25": ["13", "15", "20", "21"],
    "26": ["11", "13", "14", "15", "20", "22", "23"],
    "27": ["14", "15", "26"], "28": ["24", "25", "26", "27"],
    "29": ["16", "22", "23", "26", "28", "73"],
    "30": ["21", "22", "23", "24", "25", "26", "27", "28", "29"],
    "31": ["28", "30"], "32": ["31"], "33": ["31", "32"],
    "34": ["31", "32"], "35": ["16", "32"],
    "36": ["5", "13", "17", "30"], "37": ["11", "14", "15", "17", "36"],
    "38": ["36", "37"], "39": ["29", "31", "33", "34", "38", "73"],
    "40": ["39"], "41": ["39"], "42": ["39"], "43": ["39"],
    "44": ["40", "41", "42", "43"], "45": ["44"],
    "75": ["13", "15", "36", "44"], "76": ["12", "13", "15", "36", "75"],
    "77": ["6", "13", "36", "75", "76"],
    "46": ["45"], "47": ["45"], "48": ["45"], "49": ["45"],
    "50": ["45"], "51": ["45"], "52": ["45"], "53": ["45"],
    "54": ["45"], "55": ["45"], "56": ["45"], "57": ["45"],
    "58": ["6", "12", "13", "20", "30"],
    "59": ["6", "12", "13", "15", "26", "58"],
    "60": ["33", "34", "39", "58", "59"], "61": ["60", "75", "76", "77"],
    "62": ["58", "59", "61", "77"], "63": ["58", "59", "61", "77"],
    "64": ["58", "59", "61", "77"], "65": ["20", "30", "33", "39"],
    "66": ["45", "46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "61", "62", "63", "64", "65"],
    "67": ["46", "47", "48", "49", "50", "51", "52", "53", "54", "55", "56", "57", "61", "62", "63", "64", "65", "66", "73"],
    "68": ["30", "37", "38", "59", "67"], "69": ["33", "34", "35", "66", "67"],
    "70": ["44", "61", "67", "68", "69", "75"], "71": ["7", "8", "30", "44", "61", "68", "69", "70"],
    "74": ["20", "71"],
    "72": ["67", "68", "69", "70", "71"]
  },
  "gates": {
    "excel_engine": ["5"],
    "word_engine": ["6"],
    "multi_user_callback": ["4"],
    "artifact_publish": ["7"],
    "bulk_adapters": ["20", "30", "44"],
    "definition_publish": ["75", "76"],
    "word_entry_gate": ["77"],
    "word_bulk": ["61"],
    "legacy_delete": ["67", "68", "69", "70", "71"],
    "archive": ["72"]
  }
}
```

依赖图中的每个依赖必须指向更早 Wave 或同 Wave 更小任务号；CI 解析 JSON 做拓扑排序并拒绝环、缺节点和越门执行。

## Tasks

### Wave 0：事实清册、writer inventory 与真实技术探针

- [x] 1. 生成全量入口 manifest 与独立入口归一化清册
  - 保持 source-backed AST 发现、reviewed overlay、前端 generated 投影与 source digest fail-closed；逐 entry 机器字段至少包含 `editable`、`room_model`、`scenario_profile`，并由宿主、descriptor 与 room 事实生成，禁止自由文本或手填布尔降级。
  - 当前事实由生成器输出，禁止在生产代码复制 185/276/186 等数字。
  - 本任务 `[x]` 只代表 discovery/characterization 已完成，不代表 profile、adapter、DOM、真实 OO 或回写闭环已验收；父组件重复 entry 只指向独立 entry，Task 67 必须按最终源码重新生成并核对 manifest/profile。
  - 验证 Property 1、Property 2。
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.8, 12.14_

- [x] 2. 建假双向红基线与能力态守卫
  - 保持逐 entry template-only/reload-only/no-forcesave/no-ack/no-adapter characterization 与默认阻断 closure guard。
  - single 模式仍显示切换、unreachable 桩或 bidirectional 无 adapter 时保持红，不允许改成豁免即绿。
  - 验证 Property 3。
  - _Requirements: 1.4, 1.5, 1.7, 12.8, 12.9, 12.14_

- [x] 3. 生成 writer/resolver/version domain 迁移清册
  - 从调用链生成 HTML save、专属 router、上传/导入、WOPI、OO callback、custom、F2、rollback、历史恢复及 export/storage resolver 清单。
  - 每行记录读写字段、`parsed_data._version/file_version/content_revision`、commit 点、orchestrator、副作用、canonical resolver 与 characterization test。
  - 任何未裁决 writer 使统一 revision gate 保持红；不修改业务数据。
  - 验证 Property 4、Property 61。
  - _Requirements: 2.1, 2.2, 2.12, 9.11, 13.4_

- [x] 4. 固化 callback/Command Service 生命周期、JWT、下载安全与真实多人语义真值表
  - 基于现有 router、OO 9.4 文档行为和可控 callback 样本，定义 status 1/2/3/4/6/7、URL/userdata、response error、clean-close request、timeout、TTL、in-flight grace 与确定性 correlation。
  - 用真实 OO 9.4 两个独立用户同 room 编辑：记录 A 发起 forcesave、B 同时贡献、status 6/2、无 userdata close、OO `users/actions`、drop/revoke 后 artifact/payload 行为；保存 build、artifact、payload digest 与 trace。
  - 由实证锁死 callback 是 room/generation route 事件；若无法证明撤销用户已被安全 drop，则固定 write-fence + generation rotation，不设计 participant-bound callback authorization。
  - 定义 claim schema/version、issuer/audience/action、room/generation/doc_key route token 与 URL binding；做 SSRF、DNS rebinding、redirect、流式超限 characterization，不接通生产 callback。
  - 验证 Property 16、Property 17、Property 63 的真实行为前置判据。
  - _Requirements: 4.3, 4.9, 4.10, 5.1, 5.2, 5.3, 5.4, 5.6, 10.2, 10.4, 10.7, 10.9_

- [x] 5. 真实 OnlyOffice 9.4 Excel identity instrumentation 黑盒 probe
  - 用平台自有真实模板分别验证 hidden `_GT_SYNC`、defined names、Excel Table/隐藏 UUID 列。
  - 操作覆盖编辑、插入、删除、排序、复制、粘贴、sheet 展示名调整、forcesave、下载、重开。
  - 比对 identity inventory、公式、merge、样式、drawing/chart/pivot；保存 OO build、artifact hash 和 probe script evidence。
  - 未通过的载体不得进入 Task 17/36/37；不修改运行时权威模板。
  - 验证 Property 66。
  - _Requirements: 6.13, 6.14, 6.15, 6.16, 6.17, 14.5, 14.16_

- [x] 6. 真实 OnlyOffice 9.4 Word tagged SDT 载体黑盒 probe
  - 在隔离副本注入 field/row SDT tag，验证跨 run、多实例、插删段落/行、forcesave、下载与重开。
  - 只证明 tag/层级/row UUID/SDT 外正文的载体保留能力，不提前宣称生产 extractor、缺 tag fail-closed 或 operation 回写已实现。
  - 失败时只回到 design 选择新稳定载体，不创建通用 Word engine；禁止 paragraph/regex fallback。
  - 生产 extractor/tag 缺失 fail-closed 与 operation 回写由 Tasks 59/61/68 承接；本 probe 不提前自证。
  - 验证 Property 33。
  - _Requirements: 7.2, 7.5, 7.6, 14.4, 14.16_

- [x] 7. 验证 Windows staged artifact、DB rollback 与 orphan GC 边界
  - 在项目同卷验证流式 staging、fsync、content-addressed publish、`os.replace`、文件占用和进程中断。
  - 注入 immutable publish 后 DB rollback，证明 content/representation pointers 不变、artifact 不可见、reconciliation 可标 orphan、RetentionPolicy/GC grace 后才删除。
  - 禁止宣称文件系统与 PostgreSQL 同一事务。
  - 验证 Property 5、Property 9、Property 42。
  - _Requirements: 2.4, 3.4, 5.9, 9.6, 9.7, 14.6_

- [x] 8. 建三件套覆盖矩阵、变异骨架与 migration 只读基线
  - 生成 AC→Design oracle→实现 task→独立验证 task→evidence type 矩阵；悬挂 AC、单任务自证或无 evidence type 打红。
  - 变异 runner 区分 RED/GREEN/ANCHOR-MISS/WRONG-TEST，CRLF 归一、唯一锚点、还原 hash 自证。
  - 重新扫描 `backend/migrations/V*.sql` 和既有 version/file 分布；只建立诊断快照，不读取或触碰禁止文件。
  - 验证 Property 57。
  - _Requirements: 1.8, 5.12, 14.7, 14.13, 14.15_

### Wave 1：统一内容版本、artifact、contract、merge 与 writer 迁移

- [x] 9. 新增 content/representation/application/definition bundle、candidate、room/request/recovery、scope index 与 evidence 迁移
  - 实施前重新实扫迁移号；新增幂等 V/R 脚本、FK/unique/check/index/trigger 和 revision 0 回填台账。
  - 显式迁移 `working_paper_content_application`、`working_paper_sync_scope_index`、`working_paper_sync_definition_artifact`（含 `authority_model` definition）、`working_paper_sync_definition_bundle`、`working_paper_representation_upgrade_candidate`、content version/representation/entry state、pending mutation、room/participant/client confirmation、forcesave request/delivery/contributor/operation/conflict/test-run/scenario/trace entities；application新增immutable `origin_request_sequence`与单调`effective_request_sequence`，room新增`latest_durable_application_id/latest_durable_sequence`；`working_paper_sync_operation.application_id`为nullable UNIQUE primary FK，另增nullable `duplicate_of_operation_id` direct self FK与terminal `duplicate`状态：winner primary绑定application，loser shell保持application空并直指primary，禁止self/链/环；`application_key`、frozen identity、incoming/result artifact只落application。
  - artifact state 增 `durable`；`.incoming/{wp_id}/{delivery_id}` 以 delivery identity sealing，路径不依赖 operation/application。bundle 的 authority model 与 template/instrumentation/contract typed slots 全部 `NOT NULL`，以 CHECK + trigger + service validator 锁死 child kind/state/digest；slot omission、SQL/JSON NULL、空串和全零 hash 均拒绝，`projection_contract` 必须引用 approved template/instrumentation/per-entry contract child，custom/opaque 只能使用 registry 中版本化 typed null marker。
  - 显式迁移 `working_paper_oo_close_intent`、participant `closing`状态、generation close barrier/leader + eligibility epoch/digest、`working_paper_callback_recovery_case`与独立append-only recovery event；close-capture建generation内open-state partial unique。forcesave request以`(room,generation,initiated_by_participant_id,kind,idempotency_key)`唯一并保存`frozen_request_fingerprint`。正常Command Service前同事务创建request与`application_id=NULL` shell，durable correlation后才创建/命中application；winner绑定primary，same-key loser原子fold effective sequence并成为direct duplicate。leader promotion前authorization stale允许审计successor；无successor落generation supersede/recovery-required终态。recovery claim前request/application/operation全空，成功claim同事务create-or-hit并收敛primary/duplicate，download-only三者恒空。
  - `working_paper_sync_scope_index`只存非敏感project/wp/entry与对象类别/opaque对象id，可在业务row前授权定位；content version的resource_id只用immutable UUID `version_id`，numeric revision禁作scope key。scope row与child必须同事务创建或以`retired_at`退役，tombstone永不物理删除/清空且resource id永不复用。pending mutation保持作用域绑定、短TTL、单次逻辑消费和幂等重放；room双基线、frozen request bundle/authority model、canonical application/effective sequence与timeline按design落库。application incoming FK只允许`state=durable`，quarantined不得引用。
  - 回填只引用/复制项目现有 artifact，不写模板库、不改业务值；无法形成合法 approved bundle 的 entry 保持 single/unverified，纯 representation baseline、candidate 与 descriptor confirmation 均不推进 content revision。
  - 验证 Property 4、Property 5、Property 10、Property 11、Property 18、Property 62、Property 64、Property 68、Property 69。
  - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6, 3.1, 3.6, 3.7, 4.1, 4.11, 5.4, 5.5, 5.10, 8.1, 12.10, 12.11, 13.5_

- [x] 10. 建 ORM、repository、允许状态边与数据库并发/不可变约束
  - repository 只 flush 不 commit；实现 wp row/advisory lock、business revision optimistic lock，以及 content/representation/definition artifact/bundle/candidate/entry state、room/lease/close-intent/request/delivery/recovery/application/operation/scope-index/event/scenario 原子写入。
  - `working_paper_forcesave_request`以`(room_id,generation,initiated_by_participant_id,kind,idempotency_key)`唯一并保存immutable canonical `frozen_request_fingerprint`；cache hit必须逐项等值，跨participant/kind/payload冲突返回409且不返回旧ID。`working_paper_content_application.application_key`建唯一约束并唯一持有frozen identity/incoming/result；application的`origin_request_sequence`不可变、`effective_request_sequence`只可GREATEST单调提升并与room `latest_durable_application_id/latest_durable_sequence`同事务，same-app fold不得self-supersede。`working_paper_sync_operation.application_id`为nullable UNIQUE primary FK，`duplicate_of_operation_id`为nullable direct self FK。pre-correlation二者均空；winner只能`application非空/duplicate空`，loser只能`application空/state=duplicate/duplicate指向同scope+bundle且已绑定该application的primary`，禁止self/链/环/stranded/self-supersede，operation schema禁止复制`application_key`。request与application可同时被delivery/operation引用，不施加错误XOR。application incoming FK必须`kind=incoming,state=durable`，quarantined引用由CHECK/trigger拒绝。
  - delivery ownership只按`durable_at`判定：pre-durable received/downloading/rejected/error可零application/recovery owner但禁双owner；durable fact存在的correlated/unmatched/post-durable error由deferred trigger强制application/recovery恰一并保留owner，request/application不做XOR。delivery引用duplicate时以其direct primary application校验一致。scope index row与request/application/operation/recovery/delivery child同事务创建或设置`retired_at`，repository/trigger拒绝物理删除、清空tombstone、id复用、孤儿或跨scope绑定。
  - 数据库约束与 repository 双向校验 bundle typed slots 的 `NOT NULL`/kind/state/digest、`projection_contract` approved contract child、candidate 非 current/non-resolvable，以及 recovery claim 原子 request + shell + application create-or-hit及primary/duplicate canonical关系；任何 slot omission、NULL、空串、全零 hash 或非法 typed null marker 均拒绝。
  - close-capture partial unique 只证明 generation 内 **at-most-one**；行为测试必须覆盖 single close、A/B 两种关闭顺序、A terminal 前/后 B close、reconciler 重入，以及leader promotion前revoke/expire后的`authorization_stale` successor与无successor `generation superseded/recovery_required`终态，并断言可capture路径最终恰一条、recovery-required路径零capture且不永久阻塞，任何>1都失败。同eligibility snapshot不得换leader。request origin/effective sequence、room canonical application/durable fence、opaque content `version_id`与 scenario 外键同样以约束锁死，numeric revision禁止作scope/resource/route key。
  - PostgreSQL integration test 验证多 worker、forcesave复合幂等键+fingerprint冲突、N个不同request同application key最终1 primary+N-1 direct duplicates且零stranded shell、same-app较高sequence原子fold且不self-supersede、pre-durable failure零owner/post-durable error保留owner、quarantined不可建application/进入engine、scope tombstone不可删/不可复用、两个wp相同numeric revision由不同opaque UUID无碰撞、leader successor/no-successor、claim并发幂等、同 wp 串行/跨 wp 并行、最终 authorization fence、candidate 不可见与 representation-only 零 revision。
  - 验证 Property 4、Property 5、Property 18、Property 36、Property 43、Property 59、Property 63、Property 64、Property 68。
  - _Requirements: 2.1, 2.4, 2.5, 2.9, 4.3, 5.4, 5.5, 5.10, 8.5, 10.5, 10.9, 10.10, 10.11, 13.5, 14.10_

- [x] 11. 建 CanonicalArtifactRepository、安全校验、candidate 隔离、RetentionPolicy 与 orphan reconciliation
  - 实现 `.staging/.versions/.incoming/.evidence/.upgrade-candidates`、definition/bundle/trace store、流式 hash、fsync、immutable publish、path/symlink/project 边界和 Windows `FILE_IN_USE`；staging 以 `artifact_stage_id` 标识，incoming sealing 固定 `.incoming/{wp_id}/{delivery_id}`，不依赖尚未存在或后绑定的 operation/application。
  - incoming 下载完成并校验后只可转为 `durable`，失败隔离只可为 `quarantined`，两支不可互转且quarantined保持`durable_at=NULL`；quarantined仅允许authorization-first download-only、expire、retention/legal-hold，禁止release、转durable、创建application或进入extract/merge/retry/rematerialize。incoming 永不转 `published`、不成为 current/published representation，也不得被 canonical resolver、room 或 rollback 直接解析。`working_paper_representation_upgrade_candidate` 只能引用已校验 staged artifact；candidate path/id 同样永不进入 canonical resolver、room、download、current pointer、application substrate 或 evidence。finalize 前后都校验 artifact/bundle digest，DB 失败仅留下 non-current candidate/orphan。
  - 锁死 Requirements 14.11 的 ZIP/行/field 预算，校验外部关系、宏和 OOXML 类型；bundle canonical bytes 与 typed marker artifact 同样使用内容寻址不可变发布。
  - 实现版本化 `RetentionPolicyService`：按 artifact class/敏感级别/TTL/grace/access/legal hold dry-run，二次查 DB/operation/representation/candidate/recovery/evidence 引用，逐对象删除审计；不确定即保留告警。
  - 验证 Property 5、Property 17、Property 42、Property 60。
  - _Requirements: 2.4, 3.4, 5.6, 5.7, 5.8, 5.9, 5.11, 9.6, 9.7, 10.7, 10.8, 14.11_

- [x] 12. 统一 canonical resolver、immutable definition/bundle store 与 writer/resolver 迁移矩阵
  - config/download/callback/materialize/extract/rematerialize/retry/rollback/history/evidence 均按 content version + entry + representation generation 解析同一 published artifact、approved authority model 与 frozen `working_paper_sync_definition_bundle`；candidate 和当前 alias 均不能改变历史读取。
  - 建 authority-model/template/instrumentation/contract definition artifact 与 bundle publish/alias API；发布 DAG 固定为 `template → instrumentation → contract → bundle → representation`。bundle canonicalizer 强制 authority model 与三个 child typed slots 全出现且非空，optional child 只接受版本化 typed null markers；slot omission、SQL/JSON NULL、空串、全零 hash、child kind/state/digest 不符及 projection contract 缺 approved contract child全部 fail closed。
  - 建 candidate register/finalize guard：`working_paper_representation_upgrade_candidate` 在 approved per-entry contract、authority model、bundle 与 compatibility 全通过前不可发布、不可 current、不可被 resolver/room/evidence 使用；finalize 只创建新的 immutable representation，不改旧 row或 business revision。
  - 处理 `wp_export/wp_file_resolver.py`、WOPI、storage/version 等现有权威分叉；sheet 隐藏只作用于 room/staged representation。
  - 验证 Property 7、Property 28、Property 39、Property 40、Property 41、Property 42。
  - _Requirements: 2.3, 2.10, 6.2, 6.10, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.8, 9.11, 9.12_

- [x] 13. 建通用 adapter protocol、canonical contract/bundle schema 与 fail-closed registry
  - contract semantic payload 只包含跨环境稳定语义，禁止内嵌自身 UUID/hash（含 definition artifact identity）；definition 与 representation 发布 DAG 固定为 `template → instrumentation → contract → bundle → representation`：contract 单向引用已发布 template/instrumentation digests，instrumentation 禁止反向 contract/bundle digest，bundle 在 authority model 与 child definitions approved 后生成，最后才允许 representation finalize。
  - contract 强校验 stable key、JSON Pointer、source_ref、template/instrumentation definition digest、structure/identity carrier、保护模式和文档类型；registry 逐 entry 交叉校验 source-backed manifest 的 `editable`、`room_model`、`scenario_profile` 与宿主能力、descriptor mode、room 配置事实，任一漂移 fail closed，并拒绝 matcher 重叠、`col_a` 占位、未登记 probe gate 的载体、stale adapter 和 single entry 伪 bidirectional。
  - bundle schema 强制 authority model + template/instrumentation/contract 三类 typed canonical slots；optional child 只接受 registry 版本化 typed null markers，slot omission、JSON/SQL NULL、空串、全零 hash 或 child kind/state/digest 不符立即拒绝；`projection_contract` 的三个 child 必须均为 approved definition，不能用 marker 冒充 contract。
  - generator 只产候选，人工审核的 per-entry contract 发布后才能组 approved bundle；历史 operation/retry 只读 frozen bundle FK+digest，不按 alias 重组。统一 canonicalizer 的 golden bytes、跨 Python/TypeScript、键序/换行扰动、自引用、typed marker 版本变化与非法空值反例必须通过。
  - 本任务只建文档无关 schema/registry，不等待或实现 Excel/Word engine，也不把 upgrader candidate 发布为 representation。
  - 验证 Property 3、Property 20、Property 21、Property 28。
  - _Requirements: 1.4, 6.1, 6.2, 6.3, 6.10, 6.14, 6.20, 9.8, 12.1_

- [x] 14. 建 stable-field 三方 merge 与冲突 domain
  - 实现 base/current/incoming、MISSING、类型规范化、protected、delete/update、重复 Word instance 和结构冲突。
  - 不同字段自动合并；同字段冲突保留 JSON Pointer、OO address、三值与 identity。
  - Hypothesis 验证幂等、未改保持、不同字段合并、同字段不自动选边。
  - 验证 Property 24、Property 25、Property 26、Property 27、Property 32、Property 35。
  - _Requirements: 6.6, 6.7, 6.8, 6.9, 7.4, 8.1, 8.5_

- [x] 15. 建唯一 `ContentMutationService.commit(...)` 与独立 `RepresentationService`
  - bidirectional 业务 mutation 在一次 lock/expected revision 中同时 stage projection 与兼容 representation，roundtrip 后单事务写 content version/revision、representation/entry pointer、outbox；不得 projection-only commit 后再增一次 revision。
  - `RepresentationService` 只接受 approved immutable definition bundle；finalize 必须沿 `template → instrumentation → contract → bundle → representation` 校验 authority model、typed slots、child state/digest 与 candidate compatibility。`projection_contract` 缺 approved per-entry contract、bundle 未 approved、slot omission/NULL/空串/全零 hash 或 candidate 未 ready 时一律拒绝。
  - candidate finalize 仅为既有 content version 创建新 immutable representation generation并切 entry pointer；不得递增 content revision、修改旧 row，或让 candidate 直接进入 resolver/room/current/evidence。失败保持原 pointer/revision并留下 non-current candidate/orphan。
  - adapter 不 commit、不递增 revision、不发布事件；DB rollback 只留下不可见 orphan；custom/single 模式遵守各自 approved authority model 与 non-null bundle。
  - 验证 Property 4、Property 5、Property 10、Property 61、Property 65、Property 67。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.6, 6.18, 8.10, 8.12, 13.1_

- [x] 16. 复用 durable outbox 并把 after-save 改成可重放副作用
  - 抽 facade 复用现有 outbox/DLQ；typed replay 保留完整 payload。
  - `WorkpaperSaveOrchestrator.after_save` handler 不再递增 `file_version/content_revision`，失败可重放且幂等。
  - commit 前不发布，重复 event 不重复副作用。
  - 验证 Property 52、Property 53、Property 54。
  - _Requirements: 2.12, 13.1, 13.2, 13.3, 13.4_

- [x] 17. 建 Excel instrumentation definition 与 non-current upgrade candidate 生成器
  - 仅采用 Task 5 已通过的 Excel identity carrier；经 Task 12 immutable definition store 先发布 template，再发布只单向引用 template digest 的 instrumentation definition，权威源固定 `backend/wp_templates/`。instrumentation semantic payload 不含自身 UUID/hash、contract 或 bundle digest。
  - Excel `_GT_SYNC`/defined name/row UUID 均有 instrumentation definition、visible-equivalence 与 business-sheet exclusion；运行时 binding 只能在后续 finalize 时写入已计算的 authority-model/template/instrumentation/contract/bundle digests。
  - 存量 xlsx artifact 只可复制到 staging、增强、反读并登记 `working_paper_representation_upgrade_candidate`；本任务只能生成 non-current candidate，不得创建 published/current representation，不得切 pointer、进入 resolver/room/evidence或递增 content revision。
  - 本任务不得伪造 per-entry contract、authority model 或 definition bundle。Task 36 与具体 Tasks 40–57 adapter migration 负责发布 approved per-entry contract/bundle并调用 `RepresentationService.finalize_candidate()`；缺任一 approved child 时 candidate 保持 awaiting-contract/ready 之外的不可见状态。
  - 保持 Excel/Word lane 解耦：不依赖 Task 6，不实现 Word SDT；custom/user-upload 默认不 instrumentation。
  - 验证 Property 28、Property 66、Property 67、Property 71。
  - _Requirements: 2.1, 2.3, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.19, 9.1, 9.8, 9.9, 9.10, 14.16_

- [x] 18. 迁移普通 HTML save 与 orchestrator 到统一 revision
  - 修 `wp_html_save.py` 中 `_version/file_version` 跨域；普通 single_html 保存恰增一次 business revision，bidirectional flush 只形成 pending mutation并由 Task 15 单次 commit 同时发布 representation。
  - 状态/复核变化不增 content revision；orchestrator 异常进入 outbox retry，不被 warning 吞掉。
  - characterization 与反向变异证明旧路径不可复活。
  - 验证 Property 4、Property 54、Property 61。
  - _Requirements: 2.1, 2.2, 2.12, 3.1, 13.4_

- [x] 19. 迁移上传、WOPI、custom、F2、rollback 与历史恢复 writer
  - 按 Task 3 矩阵逐行迁入 `ContentMutationService`，删除各自 revision/pointer commit。
  - custom 保持 xlsx 权威；F2 暂保现有能力但版本域统一，后续 Task 60 删除第二流程。
  - 每个 writer 有 characterization + migrated behavior test。
  - 验证 Property 50、Property 61。
  - _Requirements: 2.2, 2.11, 9.11, 12.6, 12.7_

- [x] 20. 关闭 writer/version domain gate
  - 重新生成 writer matrix，并把 writer/version domain 收进一道**不可 fail-open** 的统一 revision 门（`backend/scripts/check/check_workpaper_writer_revision_gate.py`，14 条准则）：verdict 全部由 AST 派生、无豁免列、`source_digest`/`inventory_digest`/retired ledger/upgrade lane 四重新鲜度 fail-closed、三处空分母一律 `raise WriterGateError` 而非报 0、retired writer 走正向判定、characterization 证据必须解析到调用点（实测揪出 2 处误记）。**本任务的完成语义 = 「门可信 + 当期红基线冻结」，不等于「债已清零」** —— 与 AC 12.14 同型：Task 1/2 的早期 `[x]` 同样只表示 discovery/characterization 已完成，不代表闭环已验收。
  - **当期红基线（冻结）**；生产写路径未裁决=0、绕过统一 commit=264、resolver 未裁决=0、写 legacy 版本字段=5、自有直接 commit=105、只有非 canonical resolver=72、writer 无 characterization 测试=208、多 resolver writer=4、bidirectional projection-only/双 revision=0、after-save 增 revision=0、representation upgrade 增 business revision=0、artifact-snapshot writer 不可验证=0、retired writer 不可验证=0、缺必需 domain=0；合计 658 条 blocking facts。这 14 个数字**不是手抄常量**：`test_task20_writer_gate.py::test_the_frozen_red_baseline_is_derived_from_the_live_gate` 现场解析本行、经「标签 → issue key」表映射后与 `evaluate_gate()` 的实测计数逐条比对 —— 数字写错打红，源码变了没同步更新本行也打红。**2026-09-02 更新**：Task 74 的第一半（逐 domain 裁决）把「生产写路径未裁决 236 → 0」「resolver 未裁决 34 → 0」，合计 916 → 646；其余 12 条一条未动（裁决只写 lane 标签，13 条 blocking verdict 全部由源码派生）。第二半（逐 writer 迁 `ContentMutationService`）未做，故 264/105/208/72/5 如实留红。**2026-09-04 更新**：Task 74 的探测器盲区修复（_record_ad_hoc_path 现能解析模块级路径常量，如 TEMPLATES_DIR = BACKEND_DIR / "wp_templates"）把分母从 319 行补回 327 行 —— d1262c80 的文件拆分曾把 8 个真实 resolver/export writer 移到常量旁边而使其静默离开分母（其中 2 个的 overlay 裁决行因此报「no longer exist in source」，门直接崩在 ssert_inventory_is_current）。**这是补分母不是缩分母**：8 行已逐条裁决（export_storage_resolver 5 条 / 	emplate_provisioning 3 条，全部零 version 写、零 SQL、零 commit、无 content store），故两条「未裁决」仍为 0；绕过统一 commit 261 → 264、只有非 canonical resolver 63 → 72、合计 646 → 658 是新可见行如实计入的结果。
  - **14 条准则的归属**（门的 `has_debt` 就是这 14 条的 `any()`；一条准则从报告里消失与它归零逐字相同，故守卫双向校验：门里有的 key 必须在本行有归属、本行点名的 key 必须在门里有实现）。归属 Task 20：`keeps_legacy_write_path_beside_unified_commit`、`after_save_still_increments_revision`、`representation_upgrade_increments_business_revision`、`artifact_snapshot_writer_not_verifiable`、`retired_writer_not_verifiable`、`missing_required_domain`；归属 Task 74：`unadjudicated_writer`、`bypasses_unified_commit`、`unadjudicated_resolver`、`writes_legacy_version_field`、`owns_direct_commit`、`non_canonical_resolver_only`、`writer_without_characterization_test`；归属 Task 71：`multi_resolver`。
  - **上述七条的归零动作已移交 Task 74**（gate issue key `unadjudicated_writer` 起，逐条名单见上一行的「归属 Task 74」）：清零要求逐 domain 裁决 + 逐 writer 迁到 Task 15 的 `ContentMutationService`，而 adapter 供给落在 Wave 5–7（Task 46–57 / 62–65），Task 20 在 Wave 1 —— criterion 留在本门即成环（不等供给永远归不了零，供给又要等本门放行 `bulk_adapters`）。移交形态照 `multi_resolver` 的范式：移交的是**裁决归属**，`check_workpaper_writer_revision_gate.py` 必须**继续算**这七条、继续把它们计入 `has_debt`，一行计算都不许删 —— Task 74 正是靠这些计数验零。因此本门在这七条上保持红。
  - **`多 resolver writer=0`（gate issue key `multi_resolver`，实测 4 行全在 `wp_onlyoffice_router`）已移交 Task 30**：这 4 行的 substrate 必须先变成 room/staged representation（Task 25/26），而 Task 20 又是 Task 25 的依赖 —— criterion 留在本门即成环（不等 25/26 落地永远归不了零，25/26 又要等本门过）；Task 12 的 resolver 矩阵已把这 4 行记为 `status=deferred`。移交的是**裁决归属**（谁负责清零、谁的验收卡在它上面），**不是**把它从门里摘掉：`check_workpaper_writer_revision_gate.py` 必须继续计算并把它计入 `has_debt` —— 一条准则从报告里消失与它归零逐字相同（fail-open），而 Task 30 正是靠这个计数验零。因此本门在该 criterion 上同样保持红，这与「Task 20 本就因 236 `unadjudicated_writer` + 261 `bypasses_unified_commit` 而红」并不冲突：Task 20 的验收不因这 4 行而改变结论。**第二跳**：Task 30 实测证明它在 Wave 2 同样不可满足（供给只能来自 Task 36，而 Task 36 依赖 Task 30），已再移交 Task 71，移交链 Task 20 → Task 30 → Task 71，接手侧正文见 Task 71。自第二跳起该 criterion **不再挂** `bulk_adapters` gate `["20","30","44"]`：bulk adapter 迁移在 Wave 5，Task 71 在 Wave 7，挂上即 Wave 5 依赖 Wave 7 成新环 —— bulk adapter 不能等在排在它之后的全局 legacy 删除上；`bulk_adapters` 的放行仍由 Task 20/30/44 各自的其余准则把守，本 criterion 改由 `legacy_delete` gate 中的 Task 71 把守。
  - 注入旧 `_version/file_version/direct commit` 路径时守卫打红。
  - 本门未过，Wave 2 coordinator 与任何 adapter pilot 不得宣称 base 可靠。
  - 验证 Property 4、Property 61。
  - _Requirements: 2.1, 2.2, 2.12, 9.11_

- [x] 73. 收口 Task 1 的 source-backed entry profile 三字段欠账
  - `editability` / `room_model` / `scenario_profile` 由**独立于业务裁决**的源码事实派生（宿主入边可达性、挂载点 readonly 绑定、组件 prop 默认值、OO config 端点字面量、后端 doc_key 路由表达式、挂载基数、room service 接线态），三字段 + `profile_source` 进 `_REQUIRED_ENTRY_FIELDS` 与 `manifest_digest`，overlay `expected_profile` 与推导值双向锁死，`source_digest` fail-closed 门不变。
  - 命名裁决取 `editability`（三值，与 V151 `ck_wpstr_editability` 及 `entry_profile.PROFILE_KEYS` 同名同域）；AC 12.12 的布尔 `editable` 由 `EntryProfile.editable` 单点派生，磁盘上不留第二种拼写。
  - **禁止从 `capability` / `html_store` / `migration_state` / `adapter_id` 派生任何 profile 字段** —— 否则 RG-15/16/17 退化成恒真重言式（假绿第③源），比欠账更糟。三道判据：推导函数签名不含业务裁决字段、`assert_derivation_ignores_business_adjudication()` AST 传递闭包（生成器无条件调用）、翻转全部 capability 后三字段逐字节不变。
  - RG-15/16/17 改为跑在真实 manifest 上（`build_report(facts_observer=...)` + 闭合门传实测观察器）：`registry_missing_entry_profile` 142 → 0，`registry_profile_drift` = 142 且能红能绿（换合规实测事实后须缩到只剩 RG-15 层）。
  - Task 21 room service 未接线，故 `room_service_state=pending_room_service`、`participant_lease=False`、RG-17 全量必红 —— **有意驻留**，不得手填一个「看起来合理」的 room 事实。
  - 验证 Property 3、Property 6。
  - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 12.12, 12.14_

### Wave 2：room/participant、durable callback、双层幂等与 coordinator

- [x] 21. 建 shared room、participant lease、frozen bundle 双基线与 generation write fence
  - room 绑定 generation/opened/server last-applied/client-confirmed base、published representation、approved definition bundle、单调request sequence、`latest_durable_application_id/latest_durable_sequence` canonical fence 与 write fence；participant 逐用户绑定 mode/epoch/TTL/revoke，mtime 不参与 doc_key。
  - room、descriptor confirmation 与每个 forcesave/close request 都冻结同一 bundle id/digest、authority model 与 typed-slot inventory；candidate、unapproved bundle、projection contract 缺 approved contract child或 alias 漂移均不能进入 active room。
  - callback 使用 room/generation route credential；initiator、route 与 contributor 分表。撤销 writer 有 OO drop 证据才可留在原 generation，否则取消 outstanding request、提升 fence并 supersede/reopen。
  - application 只无条件推进 server last-applied；同application key的较高request只原子提升其`effective_request_sequence`并让room canonical fence仍指向同application，不得按raw sequence自我supersede。result managed projection 与 incoming 等值或 editor ack 新 descriptor后才推进 client-confirmed，后续 request 从该确认快照冻结 bundle/base。
  - 验证 Property 6、Property 15、Property 43、Property 44、Property 62、Property 63。
  - _Requirements: 2.5, 2.6, 2.7, 2.8, 2.9, 4.7, 4.11, 10.2, 10.3, 10.4, 10.9, 10.10_

- [x] 22. 建 room callback claim、流式下载、delivery 去重、request-first correlation 与 recovery case
  - router 只委派；按 Task 4 真值表校验 JWT/room/generation/doc_key/route token/action，不把 participant 当聚合 artifact 唯一作者。
  - SSRF/DNS/redirect/timeout/大小与OOXML安全均在durable前；delivery key含status/discriminator并记录OO users/contributor digest。`durable_at`为空的received/downloading/rejected/error可零application/recovery owner但禁止双owner；durable fact存在后恰归属application或recovery case，post-durable error保留owner；request/application可同时关联，不做错误XOR。
  - callback 有 `userdata/request_id` 时先精确绑定 frozen request及其normal `application_id=NULL,duplicate_of_operation_id=NULL` pre-correlation shell，校验client base/representation、approved bundle/authority model、permission/write fence；incoming完整下载、校验并sealing为durable后才计算/命中`working_paper_content_application.application_key`。winner shell原子绑定application成为primary；different-request loser shell保持`application_id=NULL`并原子写terminal duplicate/direct `duplicate_of_operation_id`，delivery以canonical primary校验同application，不得先按incoming或operation猜application。status=2无userdata优先绑定唯一eligible close-capture；不存在eligible/newer request时才可去重到frozen identity唯一的同incoming application。
  - 无request、候选冲突或browser crash时，incoming durable后只创建`working_paper_callback_recovery_case`与recovery event；claim前request/application/operation均为0，不猜base、不伪造operation。后续只允许authorization-first claim原子创建request+shell并创建/命中application，commit前shell落为primary或direct terminal duplicate且case/delivery canonical application一致；或download-only保持三者为0。
  - incoming artifact 只保持 `durable`/`quarantined`，永不成为 published/current representation或 resolver-visible substrate；仅`kind=incoming,state=durable`可绑定application并进入engine，quarantined保持`durable_at=NULL`且只可download-only/expire/retention，禁止release/转durable/application/extract/merge/retry/rematerialize。durable 前失败返回非零，durable 后已有关联 operation 的处理失败返回 0并保留 incoming，未关联则 recovery case 可恢复。测试锁死 same incoming + different frozen base/representation/bundle/authority model 不折叠；forcesave同key lookup必须使用`(room,generation,participant,kind,key)`并比较`frozen_request_fingerprint`，跨participant/kind/payload冲突409且不返回旧ID，任何重放都不能绕过当前 permission/write fence。
  - 验证 Property 16、Property 17、Property 18、Property 19、Property 44、Property 45、Property 63、Property 64。
  - _Requirements: 4.3, 4.9, 4.10, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.11, 5.12, 10.2, 10.3, 10.6, 10.7, 10.8, 10.9_

- [x] 23. 建 frozen forcesave/close/recovery request、content application 去重与 sequence 收敛
  - normal forcesave/clean close 在调用 Command Service 前，于同一事务持久化 frozen request 与 `application_id=NULL,duplicate_of_operation_id=NULL` operation shell；request唯一键为`(room,generation,initiated_by_participant_id,kind,idempotency_key)`，冻结 request/incoming sequence、client-confirmed base/representation、approved definition bundle id/digest + typed slots、authority model、adapter build、initiator epoch、contributors、write fence并保存canonical `frozen_request_fingerprint`。authorization-first cache hit只有全部冻结字段等值才返回旧ID，另一participant、不同kind/payload复用key返回409且不返回旧标识。accepted 前不得预建 application，callback 绝不读取到达时 mutable room pointer或当前 alias计算 key。
  - incoming durable 且 request-first correlation 成功后才创建/命中 `working_paper_content_application`。同application key的winner shell绑定application成为唯一primary；different-request loser shell在锁定primary后保持application空、写direct `duplicate_of_operation_id`与terminal duplicate event，禁止链/环或停在waiting_application。application保存immutable `origin_request_sequence`，同key后续request原子把`effective_request_sequence=GREATEST(...)`并与room `latest_durable_application_id/latest_durable_sequence`同事务推进；same-app fold不得self-supersede。`application_key`只存在于application，包含`wp/room/generation/frozen base version/frozen base representation/incoming sha/bundle sha/authority-model sha/adapter build`，不含status/request id；status 6/2仅在同一frozen identity下多delivery一application，相同incoming+不同frozen base/representation/bundle/authority model必须不同key。
  - recovery claim 仅在authorization-first校验prior confirmation、bundle、generation/fence与contributors后，于一个事务中创建`kind=recovery_claim` request与pre-correlation shell并创建/命中application；commit前shell必须成为primary或direct terminal duplicate，case/delivery绑定同一canonical application。claim前与download-only的request/application/operation三者全空，nullable-operation recovery case不得进入普通retry。
  - primary retry复用既有operation timeline与application；duplicate GET/timeline/conflict/retry/resolve固定执行requested operation显式scope/当前权限 guard → direct-primary invariant → canonicalize → 仅要求canonical primary唯一绑定application，禁止先要求requested duplicate绑定application或新建operation/application。resolve先比较canonical application identity，再比较`effective_request_sequence`；same-app较高sequence只fold且不判stale，只有较新durable full snapshot属于不同canonical application时才supersede旧未应用conflict/operation。并发相同key返回primary或可轮询duplicate终态但仍先重验当前授权。merged≠incoming时只推进server last-applied并返回refresh-required，拒绝下一request直至新generation ack。
  - 验证 Property 18、Property 36、Property 56、Property 62、Property 64。
  - _Requirements: 2.9, 4.1, 4.3, 4.10, 4.11, 5.4, 5.5, 5.10, 8.5, 10.5, 10.11, 14.3_

- [x] 24. 建 OnlyOffice Command Service forcesave 与 close-intent exactly-one client
  - 普通 forcesave 先按 Task 23 同事务持久化 frozen request + `application_id=NULL,duplicate_of_operation_id=NULL` operation shell，再签短期 JWT、传 doc_key/request id，设置 timeout 与错误分类；HTTP 200 只标 accepted。
  - clean close 在 room row lock 内创建 `working_paper_oo_close_intent`并立即将该 participant `active→closing`；`closing` 不再计入 active editor。若仍有其他 active editor，为该 participant 建普通 forcesave predecessor 后 leave；active 首次归零时冻结 generation barrier，并按最高 `(intent_sequence,id)` 选择 deterministic leader；`created_at` 只作审计、禁止参与仲裁，时间戳/插入顺序扰动不得换 leader。
  - 普通 predecessor 全部 durable terminal 后，由可重入 `reconcile_close_intents()` 在同一 room lock 下处理leader。same eligibility snapshot内重试、崩溃恢复和后台重放不得换leader；若leader在promotion前revoke/expire，先写append-only `authorization_stale`并推进eligibility epoch/digest，再从仍合法intents按最高`(intent_sequence,id)`选successor。存在successor且predecessors安全时CAS创建唯一close-capture；无successor时不造request，原子supersede generation并把未终结intents落`recovery_required/authorization_stale`显式终态，禁止永久blocked或第二capture。partial unique 仅证明 at-most-one，不能单独证明最终存在。
  - forcesave/close-intent 都要求已完成 descriptor confirmation 的 authenticated active edit participant并冻结非空 participant id、permission epoch、bundle与 fence。revoked/expired/view、superseded/refresh-required、bundle/fence 变化或 null initiator 在 Command Service 前拒绝，system/route identity 不可替代用户授权。
  - 行为测试覆盖 single close、A/B 两种关闭顺序、A predecessor terminal 前/后 B close、reconciler 重入，并分别打乱`created_at`与插入顺序，最终仍按最高sequence leader产生exactly-one close-capture；另覆盖leader promotion前revoke/expire时合法successor接任且仍exactly-one，以及无successor时generation supersede + recovery-required且零capture/不永久阻塞，任何>1均失败。把comparator改回`created_at`、同eligibility snapshot换leader、漏`authorization_stale`或无successor仍blocked的定向变异必须打红。对应request达durable terminal后才允许editor destroy；浏览器崩溃/OO自发close无request时只允许incoming durable recovery case，timeout保持OO，相同Idempotency-Key重放仍先重验当前授权与frozen fingerprint。
  - 验证 Property 12、Property 13、Property 15、Property 43、Property 64。
  - _Requirements: 4.1, 4.4, 4.7, 4.10, 5.5, 10.10_

- [x] 25. 建 HTML→OO coordinator 与唯一 launch descriptor
  - `flushHtml()` 只调用 pending-mutations API，返回 `expectedRevision/pendingMutationToken/payloadSha256/expiresAt`；coordinator 以 token + Idempotency-Key 校验 project/wp/entry/sheet/user、payload digest、TTL 与 expected revision，再调用 Task 15 在一次 business commit 中完成 projection + compatible published representation staging/roundtrip/publish，禁止两次 revision。
  - commit/operation 冻结 approved authority model 与 definition bundle id/digest/typed slots；`projection_contract` 缺 approved per-entry contract、bundle 不 approved/非法空 slot或 representation 仍是 candidate 时 422并零 room/零挂载，不得按当前 alias补齐。
  - pending mutation 在同一逻辑事务中单次消费；事务前失败可安全重试。任何重放先经过 authorization-before-idempotency guard；仅当前 project/workflow/lease/generation/fence/bundle 仍有效时成功重放才返回同 operation/content version/representation，撤权后不得泄露 cached descriptor。
  - 无业务变化复用 content version；仅 definitions 变化只能由 Task 15 finalize 合法 candidate生成新 representation generation、revision 不变。descriptor 含 server/client revision、published representation、artifact、authority model、bundle/typed slots与 fence，字段完整后才 mount；ready 后仍须 descriptor-confirm API。
  - 验证 Property 8、Property 9、Property 10、Property 11、Property 67。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 6.18_

- [x] 26. 建 OO→HTML coordinator、最终授权 fence 与 canonical rematerialization
  - 只从 `application.incoming_artifact_id` 读取 `kind=incoming,state=durable` artifact 作为只读 substrate，并按 application 冻结的 client base/representation、approved definition bundle/authority model与 adapter build extract/merge；application FK、coordinator入口与engine三层都拒绝quarantined，后者只可download-only/expire/retention且不得release/转durable。不得使用 callback 到达时 room pointer、当前 registry alias、candidate或 operation path 猜 substrate。
  - 无冲突时在独立 staging 中对 incoming substrate 重写 merged projection，形成新的 result artifact；先按同一 frozen bundle extract 等值并校验未管理区域，再重验 final authorization、generation/write fence、eligibility 与 artifact/bundle digest，全部通过后才发布新的 representation。incoming 本身永不晋升、复制标记为 published/current或被 resolver 直接采用，projection-based result 缺 approved contract child立即失败。
  - DB commit 前再次重验 project/visibility/workflow、generation/write fence、initiator epoch/contributors与 bundle identity；单事务提交 business projection/version、result representation/pointers、server last-applied、application/operation timeline与 outbox。
  - merged projection 与 incoming 等值才推进 client-confirmed；不等则 room refresh-required、supersede/reopen，禁止下一 forcesave。durable 后任一失败保留 incoming与同一 operation error，不推进 current/server/client pointers。
  - 验证 Property 14、Property 19、Property 25、Property 26、Property 27、Property 29、Property 38、Property 43、Property 62、Property 65。
  - _Requirements: 2.9, 4.2, 4.3, 4.5, 4.6, 4.11, 4.12, 5.8, 6.8, 6.9, 6.11, 8.9, 8.10, 8.11, 8.12, 10.10_

- [x] 27. 建冲突预览 API、canonical-application/effective-sequence resolve fence、recovery-aware retry 与 opaque-version rollback
  - 冲突含业务标签、JSON Pointer、OO 地址、base/current/incoming、kind、client edit epoch/incoming sequence、frozen bundle/authority model与保护策略。
  - resolve 同时带 expected revision/generation、canonical application id、application `effective_request_sequence`、room latest durable canonical application/sequence与conflict digest；先比较canonical identity再比较effective sequence，same-app较高request只fold不stale，只有较新durable incoming属于不同canonical application时才supersede旧conflict；仅current变化时按原frozen bundle/authority model rebase。
  - primary operation retry只从其一对一application的`application.incoming_artifact_id`与原bundle FK开始，并要求artifact仍为`kind=incoming,state=durable`；quarantined在FK/入口即拒绝。复用同一append-only timeline，不新建operation/application、不再forcesave或读取当前alias。duplicate operation的GET/timeline/conflict/retry/resolve固定按requested id authorization-first guard → direct primary同scope/bundle invariant → canonicalize → canonical primary唯一application检查；禁止先要求requested duplicate绑定application、链/环、授权前跳转或为duplicate重跑apply。unmatched/ambiguous recovery case在claim前`operation_id=NULL`，普通retry必须拒绝；authorization-first claim创建request+shell并创建/命中application、落为primary或duplicate后才可进入retry。download-only永远零operation。
  - rollback route固定为`/versions/{version_id}/rollback`，`version_id`是immutable opaque content-version UUID；numeric revision只展示/作expected-current乐观锁，禁止作route/scope/resource key。rollback 只能从该UUID定位的既有 published content/representation 生成新的 content/published representation并固定 approved bundle；`incoming`（无论 durable 或 quarantined）与 candidate 均不可作 rollback source，纯表示 rollback 不增 business revision。跨project/wp/entry存在相同numeric revision时必须由不同UUID无碰撞且越权统一404。
  - 验证 Property 35、Property 36、Property 37、Property 38、Property 43、Property 65、Property 67。
  - _Requirements: 6.18, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 10.10_

- [x] 28. 建完整显式 scope sync router、兼容委派与 authorization-before-resource/cache 端点门
  - 用户 API 统一挂在 `/api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}`；实现 pending-mutations、materialize、confirm-descriptor、forcesave、close-intents、recovery-cases list/claim/download-only、operations query、conflicts query、timeline query、resolve与`versions/{version_id}/rollback`。recovery list 必须显式带 `room_id/generation`，rollback必须显式携带entry scope + opaque version UUID，numeric revision不得作route/scope key；forcesave cache以`(room,generation,participant,kind,key)`定位并比对`frozen_request_fingerprint`，跨participant/kind/payload冲突409且不得返回旧ID。pending token/confirmation/claim 的 Idempotency-Key、409 stale identity与零 revision语义不得由前端约定代替。
  - 所有 POST/GET/list/query/download-only 端点共用固定 guard：认证 → 校验显式 project/wp/entry scope及 signed claim → **只查**非敏感 `working_paper_sync_scope_index` → visibility → action/workflow/lease/generation/fence/bundle → 业务 resource/cache lookup；严禁先查 room/operation/recovery/application 来反推 scope。scope 缺失、对象不存在或跨 scope 使用同一 404 envelope/阶段/时序预算；仅 scope 可见但 action 不允许时返回统一 403，撤权后原 key 重放必须零泄露/零副作用。
  - recovery list只在guard后按显式room/generation给候选confirmation摘要；claim在case/room lock与auth-first校验prior confirmation、approved bundle/authority model、fence/contributors后，于一个事务创建recovery-claim request与pre-correlation shell并创建/命中application及全部scope index rows，commit前shell落为primary或direct terminal duplicate且case/delivery canonical application一致。claim前三者为空；download-only只终结case并签短期下载，三者保持0；nullable-operation case不得调用普通retry。
  - normal request/application/operation与delivery的scope rows同样随child同事务创建；child退役只设置`retired_at`并永久保留tombstone，禁止DELETE/清空/id复用。旧config/callback URL只委派新服务；callback单独校验room/generation/doc_key/route token，不伪造participant attribution；descriptor-confirm写confirmation+append-only transition后才允许同generation forcesave。
  - 验证 Property 10、Property 11、Property 45。
  - _Requirements: 3.1, 3.6, 3.7, 5.8, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 11.4_

- [x] 29. 建 append-only timeline、source-profile-derived test-run/scenario evidence、脱敏与告警
  - operation、application 与 recovery case transition event 均先写、current state 后投影；查询按 wp/room/request/participant/operation/recovery case/application/sequence/correlation id，normal accepted 已有 nullable-application shell timeline，recovery claim 前不得伪造 operation timeline。
  - 持久化 `sync_test_run`、scenario rows、immutable trace bundle；evidence recomputer 从 source-backed manifest 的 `editable/room_model/scenario_profile` + capability + frozen approved definition bundle + authority model 推导 required scenario set，固定 manifest/profile/source digest，并逐项重算 recovery case、application IDs、operation/content version/published result representation/bundle typed children/artifact/timeline 外键、hash与 bundle digest，变更自动 stale。
  - projection-based 基础场景强制包含 HTML→OO、OO→HTML、identity、different-field merge、same-field conflict/resolve、frozen-base status 6/2 dedupe、same-application higher-sequence fold不self-stale、跨participant同Idempotency-Key及不同kind/payload均409且不泄露旧ID、quarantined拒绝application/engine、opaque `version_id` rollback与跨wp同numeric revision无碰撞、browser crash no-userdata recovery case、authorization-first claim、错误 prior confirmation/bundle/fence/contributor 拒绝、download-only 三实体为 0、refresh/reopen、rollback；每个 `editable=true AND (capability=bidirectional OR room_model=shared)` entry 无条件加入 single close、两个用户两种关闭顺序、A terminal 前/后 B close、leader promotion前revoke/expire后的successor与无successor`recovery_required`分支、reconciler 重入与适用分支最终 exactly-one close-capture。custom/opaque 按枚举 authority model替换字段级场景，不接受自由文本豁免。
  - 实现版本化 `RedactionPolicy`（嵌套 payload/异常/URL/token allowlist）与 `AlertRuleRegistry`（阈值、窗口、severity、dedupe、recovery、runbook）；synthetic event与泄露反向测试必过。
  - 指标覆盖 accepted/durable/application bind/correlation、forcesave fingerprint 409、application origin/effective sequence fold、recovery claim/download-only、close exactly-one/leader `authorization_stale` successor/`recovery_required`、bundle-candidate finalize、incoming sequence/refresh-required/extract/merge/apply/dedupe/retention/orphan/outbox；同一指标必须能按 room/generation/requested+canonical operation/application 与 participant 归因，禁止把 same-app fold、跨 participant 冲突或无 successor 恢复态压成普通 error。
  - 验证 Property 52、Property 53、Property 54、Property 68、Property 69、Property 70、Property 71。
  - _Requirements: 5.10, 5.11, 10.7, 12.10, 12.11, 12.12, 13.1, 13.2, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 14.16_

- [x] 30. 关闭 durable protocol、application/scope、close exactly-one 与 recovery 生命周期 gate
  - 后端独立集成验证room route/participants/contributors、forcesave复合幂等键+`frozen_request_fingerprint`、跨participant/kind/payload复用key返回409且不返回旧ID、normal pre-correlation shell→durable application correlation、application key/frozen identity、N个different-request同key shell最终1 primary+N-1 direct terminal duplicates且零stranded shell、application immutable `origin_request_sequence`与same-app higher-sequence原子fold`effective_request_sequence`并保持room canonical fence且不self-supersede、duplicate按requested authorization→direct-primary invariant→canonical-primary application完成GET/timeline/retry/resolve、status 6/2多delivery、same incoming+differentbase/representation/bundle/authority model、双基线refresh/reopen、SSRF、durable失败、最终authorization fence与canonical rematerialize。
  - **`多 resolver writer=0`（gate issue key `multi_resolver`）已移交 Task 71**（移交链 Task 20 → Task 30 → Task 71；第一跳的成环理由见 Task 20 正文，接手侧正文见 Task 71，两处都不必再推导一遍）：本门在活体库上把该 criterion 在**本位置**的不可满足性钉成事实 —— `content_representation` / `content_version` / `definition_bundle` / `oo_room` / `sync_entry_state` 五张表**全 0 行**，而 `working_paper` 有 **2806** 条存活底稿；统一 resolver 只接受 published representation + approved 非空 bundle，其供给只能由 Task 36 的逐 entry `finalizeCandidate` 产生，**而 Task 36 依赖本门** —— criterion 留在本门即与「Task 20 → Task 30」同形的第二次成环。它真正能归零的时点是「每个 entry 都已有 published representation」，那恰好也是 legacy 回退可删的时点，故裁决归属落到 `legacy_delete` gate 成员 Task 71（Task 71 本就依赖本门，方向不成环）。移交的仍然只是**裁决归属**：`check_workpaper_writer_revision_gate.py` 必须继续计算 `multi_resolver` 并计入 `has_debt` —— 一条准则从报告里消失与它归零逐字相同（fail-open），这条结论是本门修 Task 20「不再评估」措辞时立下的，此处逐字沿用。本门其余准则均已独立验证通过，故该 criterion 移出后本门判**过**。
  - 验证delivery以`durable_at`而非terminal判owner：pre-durable rejected/error零application/recovery owner、durable correlated/unmatched恰一、post-durable error保留owner、双owner失败，request/application不做错误XOR；delivery引用duplicate时canonical primary application一致。incoming只为durable/quarantined且永不published/current/resolver-visible；application FK与Excel/Word engine只接受durable，quarantined保持`durable_at=NULL`且只可download-only/expire/retention，禁止release/转durable/application/extract/merge/retry/rematerialize。只有独立staged result经verifier/final authorization/eligibility后可publish。
  - 对完整用户端点验证显式project/wp/entry scope、`working_paper_sync_scope_index`-before-resource/cache、recovery list room/generation、rollback使用`versions/{version_id}` + entry scope、numeric revision禁作route/resource key且跨wp同revision无碰撞、统一404/403阶段/时序及撤权原key重放；child退役与scope `retired_at`同事务、tombstone不可物理删除/清空、resource id不可复用且retired访问走统一404。覆盖no-userdata browser crash仅建recovery case且claim前request/application/operation均为0；authorization-first claim创建request+shell并创建/命中application+scope rows，commit前落primary或duplicate；错误prior confirmation/bundle/fence/contributor保持三者为0；download-only三者为0；普通retry拒绝nullable-operation case。
  - close liveness 覆盖 single、A/B 两种关闭顺序、A terminal 前/后 B close、closing 排除 active与 `reconcile_close_intents()` 重入；leader promotion前revoke/expire时先`authorization_stale`，合法successor按最高`(intent_sequence,id)`接任且适用路径最终exactly-one；无successor时generation supersede + `recovery_required`且零capture/不永久阻塞。任何>1失败，partial unique 只算 at-most-one 证据，同eligibility snapshot replay不得换leader。
  - 覆盖 candidate/unapproved/missing-contract bundle 不可 resolver/room/current/evidence、bundle slots 非空与 typed null marker约束、历史 retry只读 frozen bundle/application incoming且不新建 operation/application。
  - 变异预建application、漏normal shell、漏复合幂等/fingerprint或跨participant返回旧ID、删除/链化duplicate pointer、duplicate再绑application/先要求requested duplicate绑定application/授权前跟随primary、same-app raw sequence自我supersede、把delivery gate改回terminal、pre-durable error强制owner、quarantined进application/engine或release、scope tombstone DELETE/id复用、numeric revision作route/scope key、close comparator改`created_at`、closing仍计active、leader auth-stale无successor终态缺失、reconciler不重入、incoming publish、cache-before-auth、status/可变room base入key、允许null close initiator、route participant当唯一作者、merged≠incoming仍放行、直接发布candidate或跳过transition event均打红。
  - 未过门不得进入前端/engine pilot；不把 Task 4–7 的真实 probe文档声明当作已通过。
  - 独立验证 Property 16、Property 17、Property 18、Property 19、Property 36、Property 43、Property 44、Property 45、Property 62、Property 63、Property 64、Property 65、Property 68。
  - _Requirements: 2.9, 4.1, 4.3, 4.9, 4.10, 4.11, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 8.5, 8.10, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 13.5_

### Wave 3：统一前端 descriptor/bridge 与 Excel engine

- [x] 31. 建前端 DTO/API、generated manifest、recovery client 与 `EditorLaunchDescriptor`
  - 穷尽 pending mutation receipt、descriptor confirmation、operation/room/participant/error DTO；operation DTO显式含nullable `applicationId/duplicateOfOperationId/canonicalOperationId`，normal accepted时两link均空，correlation后成为primary或terminal duplicate；recovery case在claim前`requestId/applicationId/operationId`三者必须为空。未知状态fail visible，平台envelope只在API层解一次。
  - descriptor 是 Excel/Word editor 唯一 config 来源，包含 server-applied/client-confirmed、published representation generation、authority model、approved bundle id/digest/typed slots；所有 client method 显式接收 project/wp/entry，API 提供 `createPendingMutation()`、`materialize()` 与 `confirmDescriptor()`，逐项回传 generation/doc_key/representation/artifact/bundle/fence 和 Idempotency-Key。
  - 显式提供带 project/wp/entry + `room_id/generation` 的 `listRecoveryCases()`、`claimRecoveryCase()`、`downloadRecoveryArtifact()`，以及`rollbackVersion(versionId)`调用显式entry scope的`versions/{version_id}/rollback`；`versionId`只能是opaque immutable UUID，numeric revision只展示/作expected-current。claim 请求只能提交 case/participant/prior-confirmation/expected bundle/fence，不能由客户端指定 base。仅 claim 成功响应可同时带 request/application/operation；download-only响应三者均为空，不得伪造 applied。
  - SSE 优先、轮询恢复，按 operation/revision 去重；stale descriptor/recovery identity 的 409 不得转成 editing、retryable operation 或可 forcesave。
  - 验证 Property 10、Property 11、Property 47。
  - _Requirements: 3.1, 3.6, 3.7, 5.8, 11.2, 11.4, 11.5, 11.6, 11.11_

- [x] 32. 建统一 `useWorkpaperSyncBridge` 与 recovery 状态机
  - 状态覆盖flush/commit/materialize/descriptor mounted/confirming/confirmed/request frozen/accepted/waiting-application/application-bound/duplicate/durable/merge/rematerialize/conflict/refresh-required，以及`close_authorization_stale/close_recovery_required`与`recovery_pending/recovery_claiming/recovery_download_only/applied/error`；非法转换显式失败且不改mode，duplicate必须是terminal并保留requested/canonical ids，close leader 失权时必须先显示 authorization-stale/successor 进展，无合法 successor 则显示 recovery-required 而非永久 loading 或普通成功。
  - `switchToOnlyOffice()` 消费 pending token，materialize 成功后才 mount；真实 `onDocumentReady` 后 await `confirmDescriptor()`，确认成功前不得 `oo_editing`/forcesave。token或 bundle identity 失败停留 HTML。
  - OO→HTML等待terminal；normal accepted后先跟踪两link均空的shell，durable correlation后沿同一requested operation进入primary application-bound或terminal duplicate；duplicate的GET/timeline/conflict/retry/resolve固定先按requested scope/current permission授权，再校验direct primary并canonicalize，最后只要求canonical primary绑定application且不新建operation/application。same-app higher sequence只更新canonical application effective sequence与room fence，不把primary/conflict显示为stale；不同canonical application才进入superseded/rebase。merged≠incoming时重开新generation并重新confirm。no-userdata crash只能进入`recovery_pending`且request/application/operation三者为空；`claimRecoveryCase()`成功后才同时关联三者并进入primary/duplicate终态，错误prior confirmation/bundle/fence/contributor仍保持三者为0；download-only走独立终态且三者为0，不能转applied；普通`retryOperation()`拒绝空operation。
  - `listRecoveryCases()`/claim/download-only/`rollbackVersion(versionId)` 始终携带显式 project/wp/entry，list 另带 room/generation；rollback只接受opaque UUID，numeric revision不得拼route。scope 或授权失败保持可诊断但不泄露对象存在性。同步失败保持原模式，beforeunload/route leave 阻断 dirty/in-flight。localStorage 按 entry/wp/sheet 幂等迁移，不支持模式自动回落。
  - 验证 Property 10、Property 11、Property 12、Property 13、Property 14、Property 15、Property 46、Property 48、Property 58。
  - _Requirements: 3.1, 3.6, 3.7, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8, 5.8, 11.1, 11.2, 11.3, 11.6, 11.8, 11.10, 14.8_

- [x] 33. 升级 Excel/Word editor 为 descriptor consumer 与可 await/recovery-aware bridge
  - `GtOnlyOfficeSheet`/Word editor 不再自行请求 config；只接 descriptor，并把 DocsAPI `onDocumentReady` 的真实触发上报 bridge，组件自身不得伪造服务端 confirmation。
  - 暴露 forceSave/getSyncState，真实触发 ready/dirty/saveRequested/incomingDurable/terminal/recoveryCase/error；bridge 未拿到 confirm-descriptor 成功响应前，`forceSave()` 必须 fail visible。`recoveryCase` 在 authorization-first claim 成功前不得携带 operation id。
  - mounted test 锁死 `descriptor→DocEditor mount→onDocumentReady→confirm API→oo_editing/forcesave enabled`，并验证 crash callback 进入 recovery UI而非普通 retry；不存在 prop、零消费方、ready 即可保存、确认失败仍 editing或 claim 前伪 operation 均打红。
  - 验证 Property 11、Property 47、Property 48。
  - _Requirements: 3.7, 4.8, 5.8, 11.4, 11.5, 11.6, 11.10, 11.12_

- [x] 34. 建状态条、冲突对话框、recovery panel 与详情 timeline
  - 全中文区分request frozen/accepted pre-correlation shell/primary application-bound/duplicate（显示requested→canonical operation）/durable/applied/conflict/refresh-required/recovery pending，以及 close leader 失权后的`close_authorization_stale`、合法 successor 接任进展和无 successor 的`close_recovery_required`；后两者不得渲染成“保存成功”或无限等待。金额走displayPrefs store `fmtAmount()`。
  - 冲突按 sheet/table/row 分组，支持逐项与明确范围批量裁决；关闭不应用。
  - `WorkpaperSyncRecoveryPanel` 负责带显式 project/wp/entry 与 room/generation 的 list/claim/download-only：仅 scope-index + auth-first list 成功后显示候选 prior confirmation、bundle digest与阻断原因；claim 前 request/application/operation 均为空且不显示普通 retry，claim 成功后才同时显示三者并跟踪原 operation；错误 bundle/fence/contributor保持 recovery 三者为 0，download-only 不显示“回写完成”。
  - 展示 content revision（仅展示/乐观锁）、opaque `versionId`、representation generation、room/participant、opened/server last-applied/client-confirmed、canonical application origin/effective sequence、refresh-required、artifact/bundle/evidence correlation，并提供 recovery/operation 各自 timeline；rollback动作必须提交`versionId` UUID，禁止按numeric revision拼route。
  - 验证 Property 35、Property 46、Property 47、Property 48。
  - _Requirements: 5.8, 8.1, 8.2, 8.3, 8.4, 11.2, 11.3, 11.5, 11.6, 11.7, 11.10, 11.11_

- [x] 35. 接通 commit 后 content event 与前端刷新
  - 按 wp/revision 去重，dirty 时不静默覆盖；typed replay 完整恢复。
  - event/刷新失败显示可恢复状态，不影响已提交内容，不产生新 revision。
  - 验证 Property 52、Property 53、Property 54。
  - _Requirements: 11.9, 13.1, 13.2, 13.3, 13.4_

- [x] 36. 建 Excel per-entry contract/bundle loader 与 candidate finalize gate
  - 只采用 Task 5 已通过载体。对每个标准 Excel entry 先人工审核并发布自己的 per-entry contract与 approved authority model，再按 `template → instrumentation → contract → bundle → representation` 组装 approved non-null bundle；`projection_contract` 的 template/instrumentation/contract slots 必须均为 approved definition，禁止 typed null marker。
  - loader 按 frozen bundle FK/digest 校验 immutable children、structure/identity inventory与 adapter build，禁止执行中解析当前 alias；slot omission、NULL、空串、全零 hash、非法 marker、missing/unapproved contract均 fail closed并指出首个 slot/sheet/table/field/identity。
  - `finalizeCandidate(entry)` 只有在 approved per-entry contract、authority model、bundle与 candidate compatibility/roundtrip/visible-equivalence 全通过后，才调用 Task 15 为同一 content version创建 published immutable representation generation；candidate/unapproved/missing-contract bundle 不可 resolver、room、current pointer或 evidence，失败不改 revision/pointer。
  - `_GT_SYNC` 显式排除业务 sheet 枚举；动态 label 与 stable key 解耦。Tasks 40–57 的每个标准 entry 在启用前必须调用本 gate完成自己的 bundle与 candidate finalize，不能复用另一 entry 的 contract/evidence。
  - 验证 Property 20、Property 21、Property 22、Property 23、Property 28、Property 66、Property 67。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.10, 6.13, 6.14, 6.15, 6.16, 6.17, 6.18, 6.20_

- [x] 37. 建 Excel identity-aware extractor 与 shared roundtrip/unmanaged verifier
  - 按 representation 固定的 stable identity 读取受管字段；空/重复/删除 UUID、公式篡改、位置多值按 contract 形成结构/保护冲突，不按 label/坐标猜 identity。
  - table 分块和 streaming gzip，N-1/N/N+1 锁死大小、行、field、ZIP 边界；输出类型化 projection、identity inventory 与 unmanaged-region digest。
  - 提供 materializer/rematerializer 共用的反读等值、公式/结构和未管理区域 verifier；未通过不得交 commit。该任务先于 Task 38，禁止 extractor 反向依赖 materializer 实现。
  - 验证 Property 23、Property 24、Property 27、Property 29、Property 60、Property 66。
  - _Requirements: 6.5, 6.6, 6.7, 6.8, 6.9, 6.11, 6.12, 6.15, 6.16, 6.20, 8.11, 14.11, 14.12_

- [x] 38. 建 Excel identity-aware materializer/rematerializer
  - HTML 以 current/instrumented template 为 substrate；OO merge/resolve 只以application固定的`kind=incoming,state=durable` artifact为substrate，quarantined在engine入口拒绝。写 editable、动态 UUID/列、footer/公式并保护 formula/auto-source。
  - zip-level patch 默认；openpyxl 仅对 capability 清单证明安全的模板开放。动态 label 不作 identity，任何 structural edit 都交 Task 37 extractor 分类。
  - 保存后必须调用 Task 37 shared verifier 反读，证明 projection 与 merged target 类型化等值、identity/公式正确且未管理区域按 policy 不变，才可交 `ContentMutationService`；纯 representation upgrade 不增 revision。
  - 验证 Property 9、Property 22、Property 23、Property 24、Property 29、Property 65、Property 66、Property 67。
  - _Requirements: 3.4, 3.5, 6.3, 6.4, 6.5, 6.6, 6.9, 6.11, 6.15, 6.16, 6.17, 6.18, 8.10, 8.11, 8.12_

- [x] 39. 建 pilot harness、source-profile-derived sync test-run/逐 scenario evidence 与 freshness guard
  - harness 持久化 test run，并从 source-backed manifest 的 `editable/room_model/scenario_profile` + capability + frozen approved definition bundle + authority model 推导 required scenario set；每次 run 固定 manifest source/profile digest，每场景记录自身 recovery case/request/application IDs/operation/content version/published result representation/artifact/projection/authority-model digest/bundle id+digest+typed slots/OO+browser build/trace bundle。
  - projection-based entry 无条件独立覆盖 HTML→OO、OO→HTML、identity retention、different-field merge、same-field conflict/resolve、frozen-base status 6/2 dedupe、same-application higher-sequence fold不self-stale、跨participant同Idempotency-Key及不同kind/payload均409且不返回旧ID、quarantined拒绝application/engine、opaque version UUID rollback与跨wp同numeric revision无碰撞、browser crash no-userdata recovery case、authorization-first claim、错误 prior confirmation/bundle/fence/contributor 拒绝、download-only 三实体为 0、merged≠incoming refresh/reopen与 rollback；每个 `editable=true AND (capability=bidirectional OR room_model=shared)` entry 还无条件执行 single close、两个用户两种关闭顺序、A terminal 前/后 B close、leader promotion前revoke/expire后的successor与无successor`recovery_required`、`reconcile_close_intents()` 重入及适用路径最终 exactly-one close-capture，dynamic/Word-only再按 profile追加相应场景。
  - custom/opaque 只能由 approved bundle中的枚举 `authority_model` 把字段级两场景替换为 authoritative artifact revision conflict/no-silent-overwrite；未知枚举或自由文本豁免 fail closed。claim/download-only不得共用伪 operation，recovery claim 前必须证明 request/application/operation IDs 全空。
  - 服务端 recomputer 重读 DB/recovery+application+operation timeline/artifact/bundle child 重算外键、hash、bundle digest与时序；禁止手填 verified_at/result、跨 entry/场景复制、单 application/operation代表全部场景或仅截图。
  - runner/source commit、manifest/profile digest、OO/browser build、authority model、bundle/任一 child或 scenario set变化自动 stale；容量 profile仅登记待 Task 71执行，不宣称真实 OO probe/pilot已通过。
  - 验证 Property 25、Property 26、Property 49、Property 69、Property 70、Property 71、Property 72。
  - _Requirements: 4.10, 5.8, 6.8, 12.2, 12.10, 12.11, 12.12, 14.1, 14.10, 14.14, 14.16_

### Wave 4：四类 Excel pilot、真实 OO 9.4 gate 与平台级发布链补齐

- [x] 40. 简单 checklist Excel pilot
  - 从 manifest 冻结真实 entry，逐 sheet 读权威模板和 HTML store；为该 entry 人工审核并发布自己的 approved authority model、per-entry contract与 non-null bundle，经 Task 36 finalize Task 17 candidate为 published representation 后，方可注册 adapter/接宿主/启用 capability。不得复用其他 pilot 的 contract、bundle或 candidate。
  - 验证两方向、不同字段 merge、同字段 conflict/resolve、server last-applied 与 client-confirmed 分离、`onDocumentReady` descriptor confirmation、merged≠incoming refresh/reopen、rollback/rematerialize。
  - evidence 绑定该 entry 自身各 required scenario 的 recovery/operation/published representation/bundle digest，禁止一条 operation 复用填满场景；真实 OO 未执行前保持 UNVERIFIABLE。
  - 验证 Property 11、Property 25、Property 26、Property 29、Property 49、Property 55、Property 62、Property 69。
  - _Requirements: 3.7, 4.11, 6.8, 6.11, 12.1, 12.2, 12.10, 12.12, 14.1, 14.2_

- [x] 41. D2 大 JSON 子表 Excel pilot
  - 为该真实 D2 entry 逐 sheet 审核 stable-field contract并发布自己的 approved authority model/per-entry contract/bundle；仅在 Task 36 将其 non-current candidate finalize为 published representation 后启用 adapter/宿主，禁止用 checklist pilot bundle代替。
  - 以真实约 866KB 载荷拆 stable field/row UUID，不把整 JSON 当一个字段；验证增删重排、分块 sidecar、预算、roundtrip与不覆盖其他 item/section。
  - evidence 按该 bundle digest记录独立 required scenarios；真实 OO 未执行前保持 UNVERIFIABLE。
  - 🔴 **2026-09-06 D2-2 真实浏览器实测（Playwright + OO 9.4 + 真库，项目 `0ec33ac9`/wp `4eac7362`）抓出两条 P0 缺陷，均由今日新增的直连通道 `d2_sync_router` + `useD2SyncBridge` 引入，与 room 协议供给缺口无关**。实测已证 `d2_bidirectional_bridge` 引擎本身正确（独立真跑 push 后 `AL13=13571.99`、1260 行/49140 字段、行身份 `AN` 列与 store `rowId` 逐行一致、`write_strategy=zip_patch`），两条缺陷全在**接线与时序**：
    - **缺陷 A —— HTML→Excel 丢最新录入（宿主漏接 flush 钩子）**：`useD2SyncBridge` 定义了 `flushBeforeOo` 且在 `switchMode('onlyoffice')` 里 `await` 它，但宿主 `GtD2AccountsReceivable.vue` 只传了 `wpId` + `reloadHtml`，**`flushBeforeOo` 全文 0 次引用**（`formData.flushPendingSave()` 仅用于 `onUnmounted`）。实测时序：Excel 写于 `19:41:12.077`，HTML store 落库于 `19:41:14.771` ⇒ **push 比 HTML 保存早 2.7 秒，推的是旧数据**，审计师刚录的值在 OO 里看不到。这正是「bridge 定了可选参数、宿主没接 ⇒ 静默失效，Volar/vitest/get_diagnostics 三层全绿」那类坑。
    - **缺陷 B（更严重）—— Excel→HTML 假成功并覆盖 HTML 新值**：`pull_excel_to_html` 读的是**磁盘 canonical 文件**，而 `GtOnlyOfficeSheet.vue`（368 行）里 `forceSave` / `forcesave` / `onDocumentStateChange` / `callback` / `descriptor` **全部 0 次出现**，只有 `onBeforeUnmount` 里一句 `destroyEditor()`；OO 的编辑在编辑器销毁后才由服务端异步落盘 ⇒ pull **没有任何「已耐久」信号可等**。实测时序：OO 内输入 `88888.77` 后切回结构化视图，`19:51:19` pull 读到仍是 `19:41:12` 那份旧文件（`AL13=0`、`artifact_bytes=338438`）并**把 `0` 写回 store，覆盖掉 HTML 侧的 `13571.99`**，接口却返回 `{"ok":true,"rows_persisted":1260,"fields":40320}`、UI 显示「已从在线编辑回写 1260 行」；`19:51:31` OO 才真正 forcesave 落盘（`AL13=88888.77`，size 315300），此时已无人再 pull ⇒ **两侧永久分叉：Excel=88888.77 / HTML=0，且伴随一条成功文案**。这同时违反 11.3（不得统一显示「同步成功」，须区分「命令已接受 / 文件已耐久 / 结构化回写完成」）与 11.5（`GtOnlyOfficeSheet` SHALL 暴露可 await 的 `forceSave()` 并发 `incoming-durable` / `applied` 事件）。
    - **同时实测到的登记态与运行时不符**：`GET /d2-sync/status` 返回 `bidirectional: true`、manifest 亦记 `capability=bidirectional` + `adapter_id=d2.receivable_detail` + `migration_state=adapter_registered`，但 `check_task44_oo94_excel_pilot_gate.py` 同日实测该 entry `adapter_registered=False`、finalize 被 `supply_gap[d2.receivable_detail]` 阻塞（`capability_enabled=True`）⇒ 直连通道绕过了 Requirement 11.1「业务组件只提供 entry/flush/reload，不得自行拼 URL」与「adapter 未通过契约校验时前端不得显示可双向」。UI 侧「在线编辑」按钮**未禁用、无任何能力态提示**（`isOoAvailable` 硬编码 `ref(true)`，页面正文不含「双向」字样）。
    - **修复方向（三条，按代价排序）**：①宿主补传 `flushBeforeOo: () => formData.flushPendingSave()` —— 一行，直接消灭缺陷 A；②`GtOnlyOfficeSheet` 暴露可 await 的 `forceSave()`（走 OO `docEditor.downloadAs`/命令服务 + 等 callback status 2/6 的 durable ack），`pullFromExcel` 前必须 `await forceSave()` 且**只有拿到耐久确认才允许 pull**，拿不到就**拒绝切换并报「OO 尚未落盘」**，绝不 fail-open 写库；③pull 落库前做**陈旧校验**：比对 artifact mtime/size/digest 与本次 room 生命周期内的 forcesave ack，检测到「读的是切换前的旧版本」即 409 不写库。另建议 pull 改为**按 `rowId` 三方合并**而非整表覆盖，避免任一侧陈旧就抹掉对侧新值。
  - **✅ 2026-09-06 晚：上述五条改进全部落地，并经真实浏览器 + 真库 + OO 9.4 复测确认两条 P0 缺陷消失。**
    - **交付内容**：①宿主补传 `flushBeforeOo` + `requestForceSave` 两个钩子并新增 `ooSheetRef`；②`GtOnlyOfficeSheet` 新增可 await 的 `forceSave()`、`defineExpose` 暴露，并发 `incoming-durable` / `save-requested` / `save-error` 三个语义分离事件（AC 11.5）；③新建后端端点 `POST /d2-sync/forcesave`：向 OO Command Service 发 `c=forcesave` 后**轮询磁盘 sha256 直到真的变化**才回 `durable=true`（12 秒上限，超时如实回 `false` 不降级）；④`pull-from-excel` 接收前端回传的 `durable_fingerprint` 做**服务端二次陈旧校验**，读到切换前旧版本即 409 且**不写库**（前端那道门可被绕过，写库前的判定必须在服务端）；⑤`_assign_store_value` 改为**只在值真变化时写并计数**，`rows_changed` 与 `rows_persisted` 分别返回。
    - **🔴 三条 fail-open 反向约束**：`forceSave()` 的 catch 分支恒 `durable:false`；bridge 拿不到确认时抛 `NotDurableError` 并**不切模式**（留在数据确定最新的 OO 侧）；`_issue_forcesave` 用**三态**（`accepted` / `nothing_to_save` / `rejected`）而非布尔 —— 复测实证压成布尔必误判：OO 对「打开没改就切回」回 `error=4`，若只算 accepted 不算 durable，最常见操作会被永久误拒。
    - **能力态诚实化**：`isOoAvailable` 从硬编码 `ref(true)` 改为 computed 读 `/d2-sync/status`（`bidirectional=false` 或 Excel 不存在即禁用），并新增 `unavailableReason` 中文原因 + 工具条上「同步中… / 在线编辑不可用 / 已同步」三态 tag（AC 1.4、11.3）。
    - **浏览器复测实录（同一底稿 `4eac7362` / 项目 `0ec33ac9`）**：OO 内 AL13 输入 `31415.92`，切回时磁盘仍是 20:57 的旧文件（AL13=0）⇒ forcesave 命令落盘、`21:09:19` 磁盘更新、指纹 `5f9feb4e→b501458c`、pull 读到新文件 ⇒ **两侧同为 31415.92**。第二轮在 AL14 输入 `7788` 复现同一链路，pull 返回 `rows_changed: 1` / `visited_writable_fields: 40320` —— 修复前这里会显示「回写 1260 行 / 40320 字段」的假成功。三行逐行核对（行身份 + 值）**全部一致**。另实测「OO 无改动时切回」返回 `outcome=nothing_to_save` / `durable=true`，正常放行。
    - **守卫与变异**：新增 `d2SyncDurableGate.spec.ts`（10 例，行为判据：调了哪些 API、顺序、失败时切没切模式）+ `d2SyncHostWiring.spec.ts`（15 例，**宿主接线形态**判据）+ `backend/tests/test_d2_sync_durable_gate.py`（27 例）。变异脚本两份（`backend/scripts/diagnose/mutate_d2_sync_durable_gate_{frontend,backend}_guards.py`）实测 **7/7 与 9/9 全 RED**，迁移到正式路径后复跑仍全 RED，每次变异后源文件均校验干净还原。
    - **🔴 变异检验当场抓出三个自身缺陷（都是本 spec 反复记录的假绿形态，值得复用）**：①`useD2SyncBridge` 漏在 options 里解构 `requestForceSave` ⇒ 运行时 `is not defined`，而 TS 不报错（options 上确实有这个键）—— 与缺陷 A 完全同型；②首版守卫只测 bridge 自身行为，**把宿主的两个钩子整行删掉照样全绿**（M06/M07 判 GREEN），故必须另建 `d2SyncHostWiring.spec.ts` 用源码形态判据锁死「宿主真的接了」；③后端首版只测 `_assert_not_stale` 函数本身，**把 pull 里那行调用删掉也全绿**（M03 判 GREEN）⇒ 属「additive 注入即死代码」，补 `inspect.getsource` 形态判据 + 顺序判据（校验必须早于 `_read_store_rows`）。另有一处复测才暴露：`forceSave()` 只取 3 个字段导致 `artifact` 指纹被丢、pull 请求体变成 `{}`、服务端那道门永远拿不到判据 —— 已补守卫锁死原样转发。
    - **未做的部分（如实登记）**：本次修的是**直连通道**的接线与时序，`d2_sync_router` 仍绕过 room/descriptor 全协议（Requirement 11.1 未兑现），`adapter_registered` 仍为 `False`、finalize 仍被 `supply_gap[d2.receivable_detail]` 阻塞。`_issue_forcesave` 刻意**不**复用 `CommandServiceClient.forcesave()`（其首参类型 `AcceptedRequest` 在类型层强制「先落库再出站」，直连通道没有 room/request 行，硬造凭据等于绕过该不变量），并在 docstring 写明 room 协议供给就绪后应整体让位给 Task 23/24。全量 `vue-tsc` 因仓库既有内存问题（8GB 堆仍 OOM）无法跑通，非本次改动引入；`b23ProcessControl` / `useC23C24Registration` / `disclosureColumnsCoverage` 三个文件 46 条既存红已用 `git status` 证明与本次改动无引用关系。
  - 验证 Property 27、Property 29、Property 49、Property 60、Property 69。
  - _Requirements: 6.9, 6.11, 6.12, 11.1, 11.3, 11.5, 12.1, 12.2, 12.10, 14.1, 14.11_

- [x] 42. H1 分组/动态结构 Excel pilot
  - 为该真实 H1 entry 发布自己的 approved authority model、per-entry contract与 bundle，经 Task 36 校验动态 identity/visible equivalence并 finalize其 candidate为 published representation后才启用；不得借用 D2/G7 definition identity。
  - contract 覆盖分组表头、动态行、footer、样式源与 stable UUID；骨架行数取 `max(seed,1)`。插删重排/复制后 identity、公式范围与未管理区域正确。
  - evidence 固定该 entry bundle digest与独立 scenarios；真实 OO 未执行前保持 UNVERIFIABLE。
  - 验证 Property 22、Property 23、Property 27、Property 49、Property 66、Property 69。
  - _Requirements: 6.3, 6.4, 6.5, 6.9, 6.16, 12.1, 12.2, 12.10, 14.1_

- [x] 43. G7 两级动态表 Excel pilot
  - 为该真实 G7 entry 发布自己的 approved authority model、per-entry contract与 bundle，经 Task 36 反读四边真源并 finalize其 candidate为 published representation后才启用；metadata sheet、candidate与其他 entry bundle均不得作为运行态 substrate。
  - 复用源 xlsx↔seed↔运行时↔渲染层真源；contract 覆盖两级表头、动态 `{slot}_{seq}`、merge/公式 mask。label 重名/改名不改 identity；metadata sheet 不进入披露表。
  - evidence 固定该 entry bundle digest与独立 scenarios；真实 OO 未执行前保持 UNVERIFIABLE。
  - 验证 Property 22、Property 28、Property 49、Property 66、Property 69。
  - _Requirements: 6.3, 6.4, 6.10, 6.16, 12.1, 12.2, 12.10, 14.1_

- [x] 44. 真实 OnlyOffice 9.4 Excel pilot gate
  - 仅测试 Tasks 40–43 已按 Task 36 finalize、且 resolver返回 published representation + approved per-entry bundle的四类 entry；candidate、unapproved/missing-contract bundle或任一 probe 未真实执行时标 UNVERIFIABLE并阻断 Wave 5，不得以文档声明通过。
  - 每类逐项运行 HTML→OO、OO→HTML、identity、different-field merge、same-field conflict/resolve、frozen-base status 6/2 dedupe、same-application higher-sequence fold不self-stale、跨participant同Idempotency-Key及不同kind/payload均409且不泄露旧ID、quarantined拒绝application/engine、opaque version UUID rollback与跨wp同numeric revision无碰撞、browser crash no-userdata recovery case、authorization-first claim、错误 prior confirmation/bundle/fence/contributor 拒绝、download-only 三实体为 0、merged≠incoming refresh/reopen与 rollback；动态能力再跑插删/排序/复制。
  - 四类 pilot 中每个命中 `editable=true AND (capability=bidirectional OR room_model=shared)` 的 entry 均必须运行 single close、两个用户两种关闭顺序、A terminal 前/后 B close、leader promotion前revoke/expire后的successor与无successor`recovery_required`、`reconcile_close_intents()` 重入并验证适用路径最终 exactly-one close-capture，同时核对聚合 artifact、initiator/route/contributors 分离及 revoke/drop/generation rotation；任何一个缺场景都保持 UNVERIFIABLE。
  - 联合 Playwright network/console、recovery+application+operation timeline、DB timestamps、published result representation/authority model/bundle digest/typed slots与 artifact/identity inventory；逐 scenario 记录独立 application IDs并入库，完整复原数据。
  - 独立验证 Property 18、Property 25、Property 26、Property 29、Property 43、Property 44、Property 49、Property 55、Property 56、Property 58、Property 62、Property 63、Property 64、Property 65、Property 66、Property 69。
  - _Requirements: 4.10, 4.11, 5.5, 6.8, 6.11, 6.16, 8.10, 10.2, 10.3, 10.4, 10.9, 10.10, 12.2, 12.10, 14.2, 14.3, 14.5, 14.6, 14.7, 14.8, 14.9, 14.16_

- [x] 45. 删除四个 pilot 宿主 legacy，执行 post-delete 全场景重验并冻结迁移范式
  - 真实 gate 后才按 source-backed plan 删除 pilot 的旧 composable/endpoint/localStorage/success 文案；不得双路并存。
  - 宿主只传 entry/flush/reload，DOM 与 API 顺序有守卫；删除提交导致 source commit 变化时，Task 44 evidence 立即 stale。
  - 重新生成 manifest/registry，为四个 pilot 创建新 test run，完整重跑各自 required scenario set 与服务端 evidence recomputation；真实 smoke 只能作为附加证据，不能恢复 verified。post-delete 全绿后才冻结可复用迁移范式，Task 1/2 历史 `[x]` 语义不变。
  - 验证 Property 47、Property 48、Property 51、Property 69、Property 71。
  - _Requirements: 11.1, 11.5, 11.8, 11.10, 11.12, 12.10, 12.13, 12.14, 14.16_

- [-] 75. 建 published-representation → frozen entry definitions 公共观测器并按 manifest 真实注册 adapter
  - 交付公共观测器：只从 published representation artifact 加上 operation/representation 冻结的 definition bundle FK + digest 现读 `FrozenEntryDefinitions`（authority model、template/instrumentation/contract typed child identity、structure/identity inventory、字段实例计数）；同一 `(content version, entry, representation generation)` 重复观测必须返回逐字节相同结果，registry alias 改名后历史读取一字不变。**不得**按 registry 当前 alias 或运行时 registry 快照重组 bundle，**不得**读取 `working_paper_representation_upgrade_candidate` 或任何 non-current representation。
  - 把 `pilot_simple_checklist` / `pilot_d2_large_json` / `pilot_h1_grouped_dynamic` / `pilot_g7_two_level_dynamic` 四处 `_load_from_published_representation()` 从 `raise` 改为调用该观测器的真实现，并**删除**四处 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` 欠账登记。**拒绝**两种中间形态并各有一条打红判据：欠账登记已删而函数仍 `raise`；欠账登记已删而函数改成 `return None` / 返回空 identity。
  - `build_production_registry()` 按 source-backed manifest 逐 entry 真实注册 adapter：仅当该 entry 已有 approved per-entry contract、approved authority model、typed slots 全非空的 approved bundle，且观测器读出的 identity 与 contract 声明逐项一致时才注册，manifest 的 `adapter_id` 随之落为真实 id、未满足供给的 entry 保持 `null` 加显式原因。**不得**为抬高注册数放宽 bundle approved / typed slot 非空 / authority model 匹配任一校验，**不得**保留「只 `return WorkpaperSyncAdapterRegistry()` 由调用方补注册」的空壳，**不得**用占位 id 充数，**不得**在 `PENDING_ENGINE_ADAPTERS` 的 `forbidden_paths` 仍禁止 `adapters/word.py` 时落地任何 Word adapter。
  - 观测器与注册器**不得**以宽泛 `except Exception` 兜底成「取空 / 本项目无此数据 / 未注册」：缺 artifact、缺 bundle FK、digest 不符、typed slot 非法空值、identity 与 contract 不符一律记 ERROR 态（error code + stage + bundle/authority identity + typed child inventory + correlation id）并向调用方抛出，**拒绝**降级为 WARNING；反向自检必须证明故意写错函数名/列名/参数形态时守卫一定失败。
  - 验收判据落在**请求路径实跑**而非登记态：四个 Excel pilot 的 `adapter_registered` 从 `False` 变 `True`，且逐 entry 真实调用一次 render-config、materialize、extract 证明 adapter 可解析并返回 frozen identity（不是注册成功但一调即抛）；manifest 全部 entry（当前实测 186 条）的 `adapter_id` 不再全 `null`。真实 OO required scenarios 未按 Task 70 刷新前 evidence 保持 UNVERIFIABLE，**不得**以本任务的注册成功宣称 pilot 已验收。
  - **🔴 2026-09-03 复选框由 `[x]` 退回 `[-]`（假绿更正，非回退）**：本任务前四条 bullet 确已交付 —— `published_identity_observer.py` 在位且 Task 44 门禁实测 `observer=available`；四处欠账登记 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER` 真删（守卫用 `not hasattr(module, name)` 断言，非字符串判）；`_load_from_published_representation` 已从生产源码消失、改名 `resolve_published_frozen_definitions`；`build_production_registry()` 也不再是空壳（现调 `bind_registration_plan(build_manifest_registration_plan(...))`）。
    - **但第五条 bullet 自述的验收判据未兑现**，而它恰恰写明「验收判据落在**请求路径实跑**而非登记态」：`check_task44_oo94_excel_pilot_gate.py` 实测四个 Excel pilot 全部 `adapter_registered=False` · `capability_enabled=False` · `attach=()`（b60 / d2 / g7 / h1 逐个如此），判定分布 `{failed: 28, unverifiable: 140, passed: 5}`、`pilot_not_admitted` 136 条；Task 61 门禁独立测得 `registered_adapter_ids=[]`。manifest 186 条 entry 的 `adapter_id` 因此仍全 `null`。两条独立路径互证，不是单侧读数。
    - **真实阻塞不在本任务**：注册计划现算 186 个 entry、`DELIVERED_PER_ENTRY_CONTRACTS` 4 行、可注册 4 条，与四个 pilot 逐一对应 —— 即静态供给已就位。卡住的是观测器要读的那个**输入**：这四个 entry 都没有 current published representation（库实测 `working_paper_content_representation` 仅 1 行且属 opaque lane，见 Task 61 的 2026-09-03 更正），观测器按第四条 bullet 的 fail-closed 约定必须抛 ERROR 而不得降级取空 ⇒ 注册必然失败。这与 Task 61 的 BP-61-1 是同一条根因。
    - **禁止的推绿方式**：不得放宽 bundle approved / typed slot 非空 / authority model 匹配任一校验来抬高注册数；不得用占位 adapter_id 充数；不得把观测器改成 `return None` / 空 identity（本任务第二条 bullet 已为这两种中间形态各留一条打红判据）。要让判据真兑现，只有让这四个 entry 之一先有 published representation。
    - **🔴 2026-09-05 阻塞点已换一环，复选框仍 `[-]`（诚实登记，不推绿）**。上一条说的「四个 entry 都没有 current published representation」**已解除**：Task 76 现已收口，`working_paper_content_representation` 4 行（其中 3 行是 projection 链的 G7 / H1 / D2），`working_paper_representation_upgrade_candidate` 1 行且已 `ready`。但 `check_task44_oo94_excel_pilot_gate.py` 现读四个 pilot **仍全部** `capability_enabled=False` / `adapter_registered=False` / `observer=available`（判定分布 `{failed: 28, passed: 5, unverifiable: 140}`，`pilot_not_admitted` 136 条）。
    - **新的绑定约束是「顺序」而不是「供给」**，且它由 spec 自己规定：四个 provider 的 `assert_manifest_capability_enabled()` docstring 与 Tasks 46–57 的启用前置都写明「经 **Task 36** 校验动态 identity / visible equivalence 并 finalize 其 candidate 为 published representation **之后**才允许注册 adapter / 接宿主 / 标 bidirectional」。现有三条 published representation 走的是 P spec 的**首版发布**路径（`ContentMutationService.commit`），**不是** Task 36 的 `ExcelEntryFinalizeGate` ⇒ 严格按 spec，今天没有任何一个 entry 可以标 `bidirectional`；而 `attach_pilot_adapters()` 的第一道门就是 `manifest_capability_enabled()`，capability 不翻则 `adapter_registered` 结构上不可能为 True。**H1 现在有了 `state=ready` 的 candidate，它是第一个可被 Task 36 处理的 entry** —— 本任务的解锁顺序因此是 Task 36 finalize → overlay 裁决 capability → 重生成 manifest → adapter 注册 → 本任务第五条 bullet 的请求路径实跑。
    - **第二个独立阻塞（工程性、非本任务）**：`generate_workpaper_sync_manifest.py --check` 当前直接 FAIL —— overlay 的 `approved_source_digest` 已 stale（approved `b0fd31f1…` vs current `d9fddb64…`）。只读量化后确认是**机械** staleness 而非语义变更：挂载 **277 → 277**、新增 77 / 消失 77 落在**同一批 42 个 host Vue、同一 component**，只是 `mountId`（内容/span 哈希）位移；四个 pilot 宿主里只有 `GtD2AccountsReceivable.vue` 在内。⇒ 重新 approve 是机械动作，但按五泳道分工书 §6 规则 3 应在**收口时一次做完**（并发会话仍在改前端，早改早 stale）。
    - **✅ 2026-09-06 实测更正：第五条 bullet 的验收判据（`adapter_registered` 由 False 变 True）在请求路径上已兑现，此前三轮判「未兑现」是被一个自身有缺陷的测法测出来的。** 三条独立证据：
      - **请求路径真跑**（独立 `NullPool` 引擎 + 真库 session，复刻 `wp_sync_router` 的注册序列）：`build_production_registry()` 绑定 **186** 条计划 → 四条 pilot attach 显式返回 `('d2.receivable_detail', 'h1.disposal_check', 'g7.soe_subsidiary_disclosure')` → `await registry.register_from_manifest(session=...)` 实测 `registered_entries=3` / `reasons=183`，registry 最终持有 **3** 个 adapter。183 条未注册**全部带显式原因**且分型干净：182 条「尚无该 entry 自己的 approved per-entry 生产契约」（属 Tasks 46~57 范围，样例 `docx/gt-a10-bundle`）、1 条「还没有 current published representation」（`xlsx/b60/gt-b60-bundle`）⇒ AC 5.12 的「未注册必带可操作原因」成立，零静默跳过。
      - **逐 pilot attach 真跑**：`d2` / `g7` / `h1` 各自返回自己的真实 adapter_id，`b60` 返回 `()`（它确实还缺 representation）。这与上一条互证，不是单侧读数。
      - **库侧供给已远超上一轮记录**：`working_paper_content_representation` 现 **9** 行（上轮记 4 行），D2 / G7 / H1 三个 entry 各有 `is_current_version=True` 的行且 `adapter_id` 与契约逐字相符（`d2.receivable_detail` / `g7.soe_subsidiary_disclosure` / `h1.disposal_check`），`reason=content_commit`。故上一轮「新的绑定约束是顺序（必须先经 Task 36 finalize）」这条**已不再是当前绑定约束** —— provider 的实际前置是 `manifest_capability_enabled()` + 能从 `entry_state` 取到 current published representation，两者今天都满足；Task 36 的 `ExcelEntryFinalizeGate` 仍无生产宿主（全仓只有测试实例化它，Word 侧有对应宿主 `fix_task77_finalize_word_entry_representation.py`），但它是**同 content version 的新代际**升级门，不是首版发布的必经路径。
      - 🔴 **测法缺陷的两条根因（都由真实执行证伪，不是读注释得出）**：① `adapter_registered = adapter_id in registered`，而 `registered` 取自**不带 session** 的 `build_production_registry()` —— Task 75 起该函数**只绑定注册计划、不执行注册**（真实注册在 `register_from_manifest(session=...)`），故它恒为空集 ⇒ 该信号**结构上恒 False，与供给是否就绪无关**。实测两口径对同一事实给出相反结论：`()` vs 三个 adapter。② `admitted` 的第四个合取项写的是 `bool(self.attach_without_representation)` —— `attach_without_representation` 是「**无** published representation 时 attach 的返回值」，要求它非空等于要求「没有 representation 也注册 adapter」，而那正是 registry RG-18 / AC 1.4 明令禁止的**伪双向**，provider 的正确行为就是 `return ()` ⇒ 该合取项要求的是被禁止的行为，同样结构上不可满足。两条叠加使**任何 pilot 永不可准入**，与实现好坏无关。
      - **修法（不放宽任何准入判据）**：新增 `request_path_registered_adapter_ids` 信号，用独立 `NullPool` 引擎跑真实 `register_from_manifest`；拿不到真库返回 `None` ⇒ 判 `unverifiable`，**绝不记 False**（「环境不可得」与「实现没做」必须分型）。`admitted` 改为 `capability_enabled and adapter_registered_on_request_path is True and observer==available and refuses_without_representation`，其中第四项是**反向不变量**（无 representation 时必须返回空元组，证明注册不是无条件的）。原 `adapter_registered` 字段**保留**并在输出里标注「registry快照=False，恒空属设计」—— 它恒 False 这件事本身要被钉住，防有人把它当供给判据用回去。
      - **门禁实跑对比**：`pilot_not_admitted` 阻断 **152 → 34**、`failed` **28 → 16**、`passed` 5 → 5；三个 pilot 的 `adapter_on_request_path` 由 False 变 **True**，剩余阻断变成诚实原因（`real_onlyoffice_not_executed` / `execution_record_missing`，即真实 OO 场景尚未执行），不再是假的「adapter 没注册」。门**自身 5 项自检全绿**（此前 `gate.admission_is_state_sensitive` 恒红）。
      - 🔴 **顺带修掉自检自身的两处缺陷**：① 该自检的替身把 `attach_pilot_adapters` 换成返回 `(PILOT_ADAPTER_ID,)` 来模拟「已注册」，与修正后的 `refuses_without_representation` 直接矛盾 ⇒ 替身态永不可 admitted、自检恒红；改为替身**保持**空元组（「已注册」由请求路径信号的替身表达），探的才是「饿死状态下会不会伪注册」。② 自检原判据是 `real.admitted != substituted.admitted`，它**预设「真实态必然 False」** —— 测法修好后 d2/g7/h1 的真实态已是 True，于是 `real == substituted`，自检把「实现真做好了」误判成「本门读的是死值」；改为「信号就绪 ⇒ True、信号饿死 ⇒ False」的双向判据。这条教训通用：**任何形如 `real != substituted` 的状态敏感性判据都隐含了对真实态的假设，实现变好时会反过来打红**。
      - **仍未兑现的部分（不推绿）**：第五条 bullet 还要求「逐 entry 真实调用一次 render-config、materialize、extract 证明 adapter 可解析并返回 frozen identity」——本轮只证到注册成功与拒绝原因分型，三条请求路径的逐一实调**未做**；manifest 全部 entry 的 `adapter_id` 也仍非全部非 `null`（182 条缺自己的 per-entry 契约，属 Tasks 46~57）。真实 OO required scenarios 未按 Task 70 刷新前 evidence 保持 UNVERIFIABLE。故复选框**保持 `[-]`**。
      - **✅ 2026-09-07 逐 entry 真调已兑现（第三条欠账解除，但复选框仍保持 `[-]`）**：新增伴生探针 `backend/scripts/check/_task75_entry_adapter_probe.py`，走的是**请求路径冻结的 adapter**（`register_from_manifest()` → `resolve_for_entry(entry_id).adapter`），不是重新 `build_excel_adapter()` 一份 —— 重造等于自我比对，测不出注册链路冻结的 definitions 是不是错的那份。published representation 的物理路径按四个 pilot provider 的同一口径现读（`resolve_visible_current_representation_id` → representation join `working_paper_artifact.relative_path`），不硬编码 —— manifest 里**没有** representation 路径字段，它是运行时供给。实测三条全部 `verified`：

        | entry | adapter_id | stable keys | materialize→extract |
        |---|---|---|---|
        | `xlsx/gt-d2-accounts-receivable` | `d2.receivable_detail` | 28491 | round-trip 28491，sha256 `5c0735e1…` |
        | `xlsx/gt-g7-long-term-equity-main` | `g7.soe_subsidiary_disclosure` | 5 | round-trip 5，sha256 `90649d9e…` |
        | `xlsx/gt-h1-fixed-assets` | `h1.disposal_check` | 14 | round-trip 14，sha256 `2796e1a1…` |

        三者 `contract_id` / `document_type` 与注册时契约逐字段一致，`artifact_kind='canonical'` / `state='published'` / `generation=1` / `reason='content_commit'`。

        - **两个首跑实测缺陷（都是探针自己的，但都指向真实判据，故各自落成守卫）**：① `extract` / `materialize` 是**同步**方法（protocol 只有 `read_current_projection` / `stage_projection_mutation` 是 async），首跑三 entry 全报 `TypeError: object Projection can't be used in 'await' expression` —— 探针 `await` 了同步方法。这类错误一旦被混进断言会被读成「adapter 实现有问题」，故 `test_extract_is_called_sync_not_awaited` 锁死调用形态。② substrate 形态门首跑写成 `kind=='published'`，三 entry 静默变成 `3 unverifiable / 0 verified` —— artifact 表的 `kind` 与 adapter 构造时的 `substrate_role` 不是同一维，published representation 的 substrate 是 `(canonical, published)`。写错这一处**不抛错**，只产出看起来像「供给不足」的结果，故 `test_substrate_gate_uses_canonical_published` 锁死词表并禁止 `kind != "published"` 出现。
        - **`failed` / `unverifiable` 分型是本轮新增的判据维度**，不是既有登记：拿不到真库 / 无 published representation / artifact 不在磁盘 ⇒ `unverifiable`（环境不可得）；adapter 抛异常 / identity 漂移 / 返回类型不对 ⇒ `failed`（实现缺陷）。`TestRealRun` 在无库 CI 上走 `registered==0` 分支并断言 `note` 非空，不记 failed。
        - 守卫 `backend/tests/workpaper_sync/test_task75_entry_adapter_roundtrip.py` **10 passed**，含真库在场的 `TestRealRun`。
        - **变异检验 4 条全 RED 且各命中预期项**：M1 `summary["failed"] += 1` → `["unverifiable"]` ⇒ RED（`test_failed_verdict_reaches_the_failed_counter`）；M2 删 `contract_id` 比对 ⇒ RED；M3 `await adapter.extract(` ⇒ RED（两条）；M4 `kind != "canonical"` → `"published"` ⇒ RED。**M1 首跑实测 GREEN** —— 原判据只数 `failed` 计数**槽位**（恒 4 处），而 M1 改的是分支里的下标字面；已改为数**所有** `failed` 下标字面（槽位 + 初始字典 + 3 个分支 = 5 处），改一处必然变少。这是「假绿第①源」的又一种变体：判据数的是不变量而不是会被改动的那一侧。
      - **仍然不推绿的三条**：① manifest 全部 entry 的 `adapter_id` 仍非全部非 `null`（本探针实跑 `planned=186` / `registered=3` / `blocked_reason=183`，182 条缺自己的 per-entry 契约，属 Tasks 46~57）；② 真实 OO required scenarios 未按 Task 70 刷新；③ 依赖链上 Task 61 / 71 / 72 / 74 仍为 `[-]`（Task 74 归零依赖 Task 71）。故复选框**保持 `[-]`**，且按「任务标记不能假绿」不在此推绿。
  - 验证 Property 3、Property 7、Property 28、Property 49、Property 67。
  - _Requirements: 1.4, 2.10, 3.3, 5.12, 6.1, 6.10, 6.18, 6.20, 12.1, 12.2_

- [x] 76. 建生产侧 `projection_contract` definition 链 provisioner 与 candidate bundle 受控 attach 入口
  - 交付按 `(project_id, wp_id)` 作用域的幂等 provisioner：沿 `template → instrumentation → contract → bundle → representation` 发布 approved definition，bundle 的 authority model 与 template/instrumentation/contract 三类 typed slot 全部非空且逐项校验 child kind/state/digest；重跑按 canonical bytes 命中既有 artifact/bundle，**不得**产生第二份同内容 definition。现有 `writer_migration.OpaqueAuthorityProvisioner.ensure()` 对非 opaque authority model 显式抛 `ProjectionAuthorityNotAllowedError`，故 projection 侧必须自建 provisioner，**不得**靠放宽该 guard 复用 opaque 通道。
  - **拒绝**一切伪造供给，五种形态各有一条 fail-closed 判据并指出首个非法 slot：自造 uuid 或 digest；在 `projection_contract` 的 contract slot 用版本化 typed null marker 冒充 contract；写空串 / 全零 hash；slot omission 或 SQL NULL；把 generator 候选当已人工审核的 per-entry contract 发布。
  - 交付 candidate 受控 attach 入口，补上 repository 现只有 create-with-bundle 而缺的 attach/update：只允许把已 approved 的 contract/bundle 绑到 `state=awaiting_contract` 的 `working_paper_representation_upgrade_candidate`，state 迁移写 append-only 审计。**不得**修改已 finalize 的 candidate、**不得**绕过 `assert_candidate_finalizable`、**不得**因 attach 让 candidate 进入 resolver / room / current pointer / evidence。
  - provisioner 与 attach **不得**递增 `content_revision`、**不得**改写既有 content version/representation row、**不得**经 MCP 写库（写库只走服务层或幂等脚本，PG MCP 保持 `restricted` 只读）；任一步失败只允许留下不可见 candidate/orphan，current pointer 与 revision 逐字不变。
  - 验收判据是**库里有真实行加幂等重跑无新增**：`working_paper_sync_definition_artifact` / `working_paper_sync_definition_bundle` / `working_paper_representation_upgrade_candidate` / `working_paper_content_representation` 四表从实测 0 行变为有真实行且外键与 digest 自洽，随后 `--check` 幂等重跑 0 新增、0 修改、`content_revision` 不变；只被 `test_task4x_*_pg.py` 调用的 `publish_pilot_definitions(publisher=...)` **不得**继续是唯一发布路径。
  - **🔴 2026-09-03 复选框由 `[x]` 退回 `[-]`（假绿更正，非回退）**：provisioner 本体确已交付并真写了库 —— `working_paper_sync_definition_artifact` 从 0 → **14** 行、`working_paper_sync_definition_bundle` 从 0 → **5** 行，其中 3 条是 approved `projection_contract`（`b60.hour_budget.authority-model` / `d2.receivable_detail.authority-model` / `h1.disposal_check.authority-model`），另 2 条是 opaque/custom 权威模型；全部 `state=approved` 且 typed slot 三类均为 `definition`（非 typed null marker），外键自洽。
    - **但自述验收判据点名的四表里有两表未兑现**。判据原文是「四表从实测 0 行变为有真实行」：① `working_paper_representation_upgrade_candidate` 实测**仍为 0 行** —— 本任务交付的 candidate 受控 attach 入口因此从未在生产路径上被真实调用过（Tasks 17 与 59 的 upgrader 也是同一状况，两者都声明「只登记 non-current candidate」而库里一条没有 ⇒ 属「additive 注入即死代码」形态，假绿第①源）；② `working_paper_content_representation` 字面上确有 1 行，但它**不是本任务这条 projection 链产出的** —— 该行的 `definition_bundle_id` 指向 `authority.opaque_single_onlyoffice`（`adapter_id=opaque.authoritative.v1`、`entry_id=opaque-{wp_id}`、`source=upload`），走的是 opaque lane。三条 projection_contract bundle 一条都没被 representation 引用。
    - **净判定**：definition 侧（artifact + bundle）真交付且可复算；candidate 与 representation 侧未兑现。差的是把已 approved 的 projection bundle 真正走通 `ContentMutationService.commit` / `finalize_candidate` 落成 published representation —— 与 Task 75 的注册失败、Task 61 的 BP-61-1 是同一条根因。**禁止的推绿方式**：不得为凑「四表有行」而自造 uuid/digest、用 typed null marker 冒充 contract、或把 generator 候选当已人工审核的契约发布（本任务第二条 bullet 已为这五种伪造各留一条 fail-closed 判据）。
  - **✅ 2026-09-05 复选框由 `[-]` 转 `[x]`：自述验收判据的四表全部兑现，且幂等重跑实测 0 新增。** 差的那两表（candidate / representation）现已由真实生产路径产出，不是凑数：
    - `working_paper_content_representation` **1 → 4 行**，其中 **3 行是本条 projection 链产出的**（`xlsx/gt-g7-long-term-equity-main` gen1 bundle `889fcb95dded` / `xlsx/gt-h1-fixed-assets` gen1 / `xlsx/gt-d2-accounts-receivable` gen1 bundle `9b98b794cf1d`），发布路径是 P spec 的 `fix_projection_first_publication.py --apply`（十阶段全过，含 `roundtrip_verified` 与 `unmanaged_regions_verified`）。原判定说的「那 1 行走的是 opaque lane」现在只是四行里的一行。
    - `working_paper_representation_upgrade_candidate` **0 → 1 行**，且它**正是本任务第三条 bullet 那个受控 attach 入口的第一次生产调用**：candidate `cfcb99ab-0186-432a-8d03-d4c0e52f7b29`（entry `xlsx/gt-h1-fixed-assets`）由新建宿主 `backend/scripts/fix/fix_excel_instrumentation_upgrade_candidate.py --apply` 以 `state=awaiting_contract`、三个 target 全 `None` 登记；随后 `fix_task76_provision_projection_definitions.py --apply` 经 `CandidateDefinitionAttachService.attach()` 绑上 approved contract `064b11a66d37` + bundle `b2284d1fd77d`，状态 `awaiting_contract → ready`。append-only 审计在位（`working_paper_representation_candidate_event` seq 1 `contract_bundle_attached`，correlation `task76-projection-provisioning@f663b18c…/xlsx/gt-h1-fixed-assets`）。原判定说的「attach 入口从未在生产路径上被真实调用过、属死代码」因此解除。
    - **四条否定式承诺逐条实测为真**：四个 entry 的 entry pointer、`representation_generation`、representation 行数、`content_revision` 在 attach 前后**逐值不变**；candidate 的 `finalized_representation_id` / `finalized_at` 仍为 `NULL`（finalize 属 Task 36 的 `ExcelEntryFinalizeGate`，本任务不越线）。
    - **幂等判据**：`--apply` 二次重跑 `created_total=0`，四表 before == after = `{artifact: 23, bundle: 9, candidate: 1, representation: 4}`；`--check` 亦全部落 `reused`。
    - **顺带修掉本任务宿主自身两处缺陷**（都是本轮实测抓出的，不是注释不准）：① `TARGET_ORDER_SQL` 与 P spec 首版宿主**不同源**（本宿主那份少了 `has_store_payload DESC`），实测 D2 / B60 两个 entry 解析到与已发布行**不同的底稿** ⇒ `--check` 对已发布的 D2 报 `blocked`；已收敛到新建生产模块 `app/services/workpaper_sync/projection_target_resolution.py`，两宿主 import 同一对象（BP-24）。② `preview_representation_settlement` 比生产 `_settle_representation_stage` **少一条分支**（`reused_candidate`）⇒ attach 完 `--check` 仍报 `blocked` 而 `--apply` 给 `reused_candidate`，预演与真跑对同一库状态给出不同结论；已补齐并改用 `target_definition_bundle_id` + `finalized_representation_id IS NULL` 作判据（不拿 `state=='ready'` 当代理）。
    - 守卫：`test_task76_projection_definition_provisioner.py` + `test_task17_excel_instrumentation.py` + `test_projection_first_publication.py` 合计 **223 passed**。
  - 验证 Property 4、Property 5、Property 10、Property 28、Property 67。
  - _Requirements: 2.1, 2.3, 2.4, 3.3, 3.4, 3.6, 6.2, 6.10, 6.18, 12.1_

- [x] 77. 建 Word per-entry entry gate 与 candidate finalize gate
  - 新建 `app/services/workpaper_sync/word_entry_gate.py`（`WordEntryDefinitionLoader` + `WordEntryFinalizeGate`），判据换成 tagged-SDT 形状：`w:tag` 是唯一锚点，逐 entry 校验 tag 集合、SDT 层级、`row_uuid` 与 contract 声明的字段实例计数一致；tag 缺失、实例计数与声明不符（含重复实例）、层级漂移一律 fail closed 并指出首个漂移 tag/XPath。**不得**沿用 `excel_entry_gate.py` 的 sheet/cell 判据（`assert_no_structure_drift` 的 4 元组、`observed_business_sheets`、`_GT_SYNC` 排除、动态列）——Word 无 sheet 无 cell，套用即恒真重言式。
  - **拒绝**一切降级锚点与 fallback，每条禁令各有一条变异锚点：不得以 `alias_display_name` / `sdt_id` / `paragraph_index` / `run_index` 作锚点（Task 6 probe 已裁 failed）；不得有 paragraph 绝对索引或中文正则 fallback；不得把已替换 placeholder 文本当锚点。row 载体按 Task 6 `downstream_gate.carriers_blocked` **恒拒**，**不得**因某 entry「只差 row 就能过」单点豁免。
  - gate 必须校验 SDT 外 Word-only 区域按 policy 等值，并覆盖跨 run token、同段多 token、插删段落后仍能经 tag 读写；不等值即拒绝并保留原 Word 文件版本。**不得**用模板重生成覆盖审计师已编辑的 Word-only 正文，**不得**把 Word-only 差异降级成 warning 后继续发布。
  - `finalizeCandidate(entry)` 只在该 entry 的 approved per-entry contract、approved authority model、typed slots 全非空的 approved bundle 与 candidate compatibility/tag-retention/Word-only 等值全部通过后，才调用 Task 15 为同一 content version 创建新 published immutable representation generation。candidate、unapproved bundle、`projection_contract` 缺 approved contract child 的 bundle **不得**进入 resolver / room / current pointer / evidence；失败时 pointer 与 `content_revision` 逐字不变，**不得**跨 entry 复用 contract/bundle/candidate/evidence。
  - 验证 Property 28、Property 30、Property 31、Property 32、Property 34、Property 67。
  - _Requirements: 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.10, 12.5_

### Wave 5：Excel 全量 lane 与 Word F2 pilot lane

**Tasks 46–57 标准 Excel entry 启用前置**：以下每个标准 Excel 独立 entry 都是自己的 definition producer/consumer：逐 entry 读权威模板与业务模型，发布 approved authority model、人工审核的 per-entry contract及 non-null approved bundle，再经 Task 36 对 Task 17 的对应 non-current candidate做 compatibility/roundtrip/visible-equivalence校验并 finalize为 published representation，之后才允许注册 adapter、接宿主或标 bidirectional。不得跨 entry 复用 contract/bundle/candidate/evidence；candidate、unapproved/missing-contract bundle不可进入 resolver/room/current/evidence。裁决为 single 的 entry 不伪造 contract或 candidate finalize；真实 OO required scenarios未完成前保持 UNVERIFIABLE。

**Tasks 61–64 启用前置（Task 60 PHASE 2 勘查实证的平台级欠账）**：除各自任务正文既有前置外，Tasks 61–64 的启用还额外要求 Tasks 75–77 全部交付。三条欠账各有实证：**B4** 四处 `_load_from_published_representation()` 一律 `raise` 且四处登记 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER`，这是四个 Excel pilot `adapter_registered=False`、manifest entry 的 `adapter_id` 全 `null`、`build_production_registry()` 只 `return WorkpaperSyncAdapterRegistry()` 的同一条根因（Task 75）；**B1** `OpaqueAuthorityProvisioner.ensure()` 对非 opaque authority model 显式抛 `ProjectionAuthorityNotAllowedError`、`publish_pilot_definitions(publisher=...)` 只被 `test_task4x_*_pg.py` 调用、PG 只读实测 `working_paper_sync_definition_artifact` / `..._definition_bundle` / `working_paper_representation_upgrade_candidate` / `working_paper_content_representation` 四表全 0 行，即生产路径从未发布过任何 projection bundle，加上 **B2** `WordInstrumentationUpgrader` 无条件包 `CandidateOnlyRepository`、candidate 以 `target_contract_definition_id=None, target_definition_bundle_id=None, state=awaiting_contract` 写死且 repository 只有 create-with-bundle 无 attach/update，使 Task 59 产出的 candidate 结构上永不可 finalize（Task 76）；**B3** 只有 `app/services/workpaper_sync/excel_entry_gate.py`，判据是 sheet/cell 形状，Word 无 sheet 无 cell（Task 77）。三者全部完成前**不得**翻 `PENDING_ENGINE_ADAPTERS` 中禁止 `adapters/word.py` 的那行，也**不得**以离线 engine、文档声明或 Task 59 的 engine 交付替代。

- [x] 46. 逐一迁移 D 循环 Excel 独立 entry
  - manifest 冻结 slice，逐 entry 读权威模板/BCD md、建 instrumentation/contract/adapter/宿主/evidence。
  - 复用 `app/services/four_table/`；纯 OO/HTML 如实裁决。
  - 验证 Property 20、Property 21、Property 28、Property 69、Property 70。
  - _Requirements: 6.1, 6.2, 6.10, 9.1, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 47. 逐一迁移 E 循环 Excel 独立 entry
  - 处理账户动态行、币种变体和稳定账号/UUID；防 variant 切换抹零。
  - slice 未裁决、未验收、stale evidence 归零。
  - 验证 Property 23、Property 69、Property 70。
  - _Requirements: 6.5, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 48. 逐一迁移 F 循环 Excel 独立 entry
  - 与 F2 Word lane 分开计数；核验复合传输键、估值/监盘模板，不凭 wp_code 猜 sheet。
  - 验证 Property 21、Property 28、Property 69、Property 70。
  - _Requirements: 6.2, 6.10, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 49. 逐一迁移 G 循环除 G7 外 Excel 独立 entry
  - 先修/排除自造 `G6TabDisclosureListed`；只认 `backend/wp_templates/` 权威版，跳过锁文件。
  - 不把虚构表或 metadata sheet 同步到附注。
  - 验证 Property 20、Property 28、Property 69、Property 70。
  - _Requirements: 6.1, 6.2, 6.10, 9.1, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 50. 逐一迁移 H 循环除 H1 外 Excel 独立 entry
  - 动态公司列复用 H7 stable key 范式；不硬编码列数/行数。
  - 验证 Property 22、Property 23、Property 69、Property 70。
  - _Requirements: 6.4, 6.5, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 51. 逐一迁移 I 循环 Excel 独立 entry
  - 分类/行模型由源 xlsx 真源派生，source_ref 守卫含源标签，防同源错仍自洽。
  - 验证 Property 20、Property 28、Property 69、Property 70。
  - _Requirements: 6.1, 6.2, 6.10, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 52. 逐一迁移 J 循环 Excel 独立 entry
  - 先解清 J2 orphan composable 与真实传输键；无可靠 HTML 映射时单模式，不造 contract。
  - 验证 Property 3、Property 20、Property 69、Property 70。
  - _Requirements: 1.4, 1.5, 6.1, 12.1, 12.4, 12.8, 12.10, 12.11, 12.12, 14.1_

- [x] 53. 逐一迁移 K 循环 Excel 独立 entry
  - 复用 K1/K2 scope 与四表真源；纯客户端 writeoff 能力必须 adapter 化或单模式裁决。
  - 验证 Property 20、Property 24、Property 69、Property 70。
  - _Requirements: 6.1, 6.2, 6.6, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 54. 逐一迁移 L 循环 Excel 独立 entry
  - 核验 sheet 粒度与 router 参数；无法干净映射的分类保持宁缺勿造。
  - 验证 Property 20、Property 28、Property 69、Property 70。
  - _Requirements: 6.1, 6.2, 6.10, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 55. 逐一迁移 M 循环 Excel 独立 entry
  - 每 entry 独立 contract/evidence；公式/分类 summary 保持受保护。
  - 验证 Property 24、Property 28、Property 69、Property 70。
  - _Requirements: 6.6, 6.10, 12.1, 12.4, 12.10, 12.11, 12.12, 14.1_

- [x] 56. 逐一迁移 N 循环 Excel 独立 entry
  - 核验真实传输键、动态 identity 和纯 OO entry；无对端不伪造映射。
  - 验证 Property 3、Property 23、Property 69、Property 70。
  - _Requirements: 1.4, 6.5, 12.1, 12.4, 12.8, 12.10, 12.11, 12.12, 14.1_

- [x] 57. 逐一迁移 A/B/C/S 与跨循环共享 Excel entry
  - 按 componentType/持久化通道分组，跨循环函证复用 adapter，不复制合同。
  - 程序表、控制判断、动态宽表、附件/OCR 只投影既有业务模型。
  - 验证 Property 3、Property 22、Property 69、Property 70。
  - _Requirements: 1.4, 1.6, 6.4, 12.1, 12.4, 12.8, 12.9, 12.10, 12.11, 12.12, 14.1_

- [x] 58. 统一 Word canonical resolver 与完整模板裁决清册
  - config/download/callback/materialize/extract 全走同 resolver。
  - 逐一裁决 18 generic DOCX、9 个 B 子码错取父级 XLSX、`S33-REV`、A16/A17；最具体 wp_code 优先且异类型 fail closed。
  - 清册直接承接 Requirement 7.7，不再遗漏。
  - 验证 Property 39、Property 40、Property 41、Property 42。
  - _Requirements: 7.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.11, 9.12, 12.5_

- [x] 59. 建 Word definition/instrumentation candidate upgrader 与 tagged-SDT engine
  - 只采用 Task 6 真实通过的载体；经 Task 12/13 发布 template 与只引用 template digest的 instrumentation definition。通用 tagged-SDT materialize/extract/rematerialize engine 可实现并只认 frozen bundle/tag，但本任务不得为任何 entry伪造 contract/bundle或把 candidate带入运行态。
  - versioned upgrader 在 staging 对存量 DOCX 做 zip-level SDT/tag/row UUID 注入，校验可见结构、样式、批注、修订、图片与业务 projection 等值后，只登记 non-current `working_paper_representation_upgrade_candidate`；不得创建 published/current representation、切 pointer、进入 resolver/room/evidence或递增 revision。
  - per-entry approved authority model/contract/bundle与 candidate finalize 分别由 Task 60（F2）及 Tasks 62–64（各 Word entry）承接，并严格执行 `template → instrumentation → contract → bundle → representation`；缺 approved bundle 时 engine只能离线验证candidate。
  - extract 只认 tag；缺失/重复/层级漂移 fail closed，无 paragraph/regex fallback。merge/resolve 只把 application 固定的 `kind=incoming,state=durable` artifact 作为只读 substrate，在独立 staging 中重写结构化岛并验证 Word-only 区域不变；application FK与engine入口都拒绝quarantined，后者只可download-only/expire/retention且禁止release/转durable。只有新的 result artifact 经 frozen bundle verifier、final authorization/eligibility 后才能 publish representation，incoming 永不晋升为 published/current或 resolver-visible。
  - 验证 Property 28、Property 30、Property 31、Property 32、Property 34、Property 65、Property 67、Property 71。
  - _Requirements: 2.3, 6.10, 6.18, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.9, 7.10, 8.10, 8.11, 9.1, 9.8, 9.9, 9.10, 14.16_

- [x] 60. 把 F2-22/F2-23 迁成统一 Word adapter并 finalize published representation
  - 为 F2-22/F2-23 各自建立逐字段 source_ref/tagged-SDT contract，发布 approved authority model、per-entry contract与 non-null bundle；按 Task 59 candidate compatibility/Word-only等值报告调用 Task 15 finalize为各自 published representation后，才注册 adapter、接 descriptor/bridge/冲突与 recovery UI。
  - candidate、unapproved/missing-contract bundle不得进入 F2 resolver/room/current/evidence；历史 operation只读 frozen bundle。现有 to/from OO endpoint先委派统一 coordinator，Task 61全场景通过后才删除第二流程。
  - HTML materialize 仅更新结构化岛，不覆盖 Word-only正文；每个 F2 entry保存自身 bundle digest与scenario evidence，不交叉复用。
  - **PHASE 2 勘查实证脚注**：per-entry Word 契约、authority model、发布记录、守卫与变异脚本已交付；`definition_bundle` / `published_representation` / `adapter` 三段因 B1–B4 平台欠账未完成（`OpaqueAuthorityProvisioner.ensure()` 对非 opaque authority model 显式抛 `ProjectionAuthorityNotAllowedError`；`WordInstrumentationUpgrader` 的 candidate 以 `target_contract_definition_id=None, target_definition_bundle_id=None, state=awaiting_contract` 写死且 repository 无 attach/update；无 Word entry gate，只有 sheet/cell 判据的 `excel_entry_gate.py`；四处 `_load_from_published_representation()` 一律 `raise`），已登记 BP-10 ~ BP-15 与各自解除条件，归零动作改由 Tasks 75–77 承接。本任务 `[x]` 与 Task 1/2/20 同型 —— 只表示上述已交付部分完成，不代表 F2 adapter 已注册或 published representation 已 finalize。
  - 验证 Property 31、Property 32、Property 47、Property 69。
  - _Requirements: 7.3, 7.4, 7.9, 11.5, 12.3, 12.7, 12.10, 14.1_

- [-] 61. 真实 OnlyOffice 9.4 F2 Word gate
  - 只允许测试 Task 60 已 finalize、resolver返回 published representation + approved F2 per-entry bundle的 F2-22/F2-23；candidate、unapproved/missing-contract bundle或 Task 6 probe未真实通过时保持 UNVERIFIABLE，不得借离线 engine宣称通过。
  - 每个 F2 entry运行 HTML→OO、OO→HTML、tag/row UUID retention、different-field merge、same-field conflict/resolve、frozen-base status 6/2 dedupe、same-application higher-sequence fold不self-stale、跨participant同Idempotency-Key及不同kind/payload均409且不泄露旧ID、quarantined拒绝application/engine、opaque version UUID rollback与跨wp同numeric revision无碰撞、browser crash no-userdata recovery case、authorization-first claim、错误 prior confirmation/bundle/fence/contributor拒绝、download-only 三实体为 0、refresh/reopen、rollback与 Word-only保留。
  - F2-22 与 F2-23 每个 entry 均无条件运行 single close、两个用户两种关闭顺序、A terminal 前/后 B close、leader promotion前revoke/expire后的successor与无successor`recovery_required`、`reconcile_close_intents()` 重入与适用路径最终 exactly-one close-capture；联合浏览器、recovery+application+operation timeline、DB、published result representation/authority model/bundle digest/typed slots与 DOCX unzip，逐 scenario 记录独立 application IDs/evidence并完整复原数据。
  - 失败/UNVERIFIABLE 时 Tasks 62–64 阻塞，禁止 paragraph fallback。
  - **驻留原因与本轮新增实证（2026-09-01，gate 版本 `task61-gate/2`）**：本轮不再复述上一轮的「四条平台欠账」结论 —— 那四条已由 Tasks 75/76/77 解除，逐条真调生产符号复核：`writer_migration.OpaqueAuthorityProvisioner` 现有 `.provision()/.resolve()`（`.ensure()` 已删）· `repository.WorkpaperSyncRepository` 现有 `attach_candidate_definitions` / `append_candidate_event` / `create_upgrade_candidate` / `finalize_candidate` 四个入口 · `word_entry_gate.py`（1856 行）交付 `WordEntryDefinitionLoader` + `WordEntryFinalizeGate` + 13 条 `WORD_ENTRY_FAILURE_CODES` · `published_identity_observer.py`（1341 行）交付 `PublishedIdentityObserver`。OO 容器亦真实可达（`GET :8080/healthcheck` → `200 'true'`，build 9.4.0-129）。**故本轮的阻塞既不是环境不可得、也不是那四条**。
    - 🔴 **三臂反事实实测证伪了「BP-10 是绑定约束」这个前提**（新 probe `gate.binding_constraint_is_measured`，真跑真库、独立 `NullPool` 引擎）：**arm_a**（真实 manifest）186 个 planned entry、`registered_adapter_ids=[]`、拒绝原因恰 **2 类**；**arm_b**（进程内把 manifest 补上一条 `docx/gt-f2-stocktake-bundle`、往交付登记表加一行、provider 走白名单内模块 —— 即把 manifest 缺 entry 这条整格移除）后 F2 的拒绝原因与 **Task 76 已完整 provision 的 `xlsx/b60/gt-b60-bundle`** 的原因**逐字相等**（判据是字符串相等，不是关键词，原因文案的真源在 `registry._describe_entry_supply`）；**arm_c**（再用替身满足供给门）原因才改变为「provider 返回空元组」。⇒ 真正的绑定约束是 **published representation 供给**，而且它是**平台级**的：`working_paper_sync_entry_state` / `working_paper_content_version` / `working_paper_content_representation` 三表实测 **0 / 0 / 0** 行，186 个 planned entry **一个都注册不上**，连供给最完整的 Excel pilot 也一样。它的生产者是 `ContentMutationService.commit(...)` 与 Tasks 36/77 的 finalize gate，**不属 Task 61**。
    - 新登记 **BP-61-1 / BP-61-2 / BP-61-3**（🔴 刻意用 task-scoped 前缀：全局 `BP-16`~`BP-22` 已被 Tasks 60/63/64 各自重复占用、同号不同义；守卫用 `re.fullmatch(r"BP-61-\d+")` 锁死，并断言 `kind=="binding"` 恰 1 行）。**BP-61-1** = published representation 供给平台级为 0（`scope=platform_wide_not_f2_specific`，唯一 binding）· **BP-61-2** = F2 Word lane 无 docx manifest entry（`document_type=='docx'` 的 entry 现算 7 条、F 前缀 0 条；唯一的 F2 entry 是 xlsx，宿主挂 `GtOnlyOfficeSheet`）⇒ 拿它注册 docx adapter 被 RG-6 `assert_document_types_agree` 以 `error_code=adapter_document_type_mismatch` 拒绝，四方实测 `{adapter:docx, matcher:docx, contract:docx, manifest:xlsx}`；**已由 arm_b 证明它排在 BP-61-1 之后、不是当前绑定约束** · **BP-61-3** = `adapters/word.py`（B5 / Task 62 的 BP-62-2，owner 确实是本任务）**本轮刻意不建**：实测 `build_excel_adapter` 的唯一构造点在四个 `pilot_*.attach_pilot_adapters` 里，没有 docx manifest entry + 自己的 provider 模块时 Word adapter **零构造点** ⇒ 建了就是 additive 死代码（假绿第①源）；而建它同时会让 `PENDING_ENGINE_ADAPTERS` 的 forbidden-path 判据失守（Task 64 的 M13 教训：禁令清单必须包含真实目标）。**净效果为负，故不做**。
    - Task 60 的两份 per-entry Word 契约仍**只 staged 不入生产清册**：`contracts.CONTRACTS_DIR` 现算 4 条（全是 Excel pilot），两份 Word 契约在 `backend/data/workpaper_sync_word_contracts/`；`contracts.parse_contract()` 对 `f2.stocktake.plan` 真跑通过（`document_type=docx` / `review_status=reviewed` / 17 字段），故**不是契约不合格**，而是装载它的前置（RG-11 + manifest 归属）未成立。真实库 definition 侧本轮已从 4→**6** 行 artifact、1→**3** 个 bundle（全属 `b60.hour_budget` 与两个 opaque authority model，Word lane 仍 **0** 条）。
    - 产物：gate `backend/scripts/check/check_task61_oo94_word_pilot_gate.py`（`task61-gate/1`→`/2`，新增第 7 条 gate 自检 + `BINDING_CONSTRAINTS` 登记 + `_isolated_session_factory`）· 生成器 `backend/scripts/gen/generate_workpaper_task61_word_pilot_probe_registry.py`（`--check` 幂等）· 数据文件 `backend/data/workpaper_task61_word_pilot_gate_probes.json`（probe 41 条 / rows **75** / 内嵌 `binding_constraints`）· 守卫 `backend/tests/workpaper_sync/test_task61_oo94_word_pilot_gate.py`（140→**160 passed**，新增 `TestBindingConstraintIsMeasured` 20 条）· 变异 `backend/scripts/diagnose/mutate_task61_oo94_word_pilot_gate_guards.py`（30→**41 条**，`--run all` **41/41 全 RED**、0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST，`--check-anchors` 41/41 OK 且三个目标文件 md5 未变、无 `.mutbak` 残留）· 台账 `.kiro/specs/.../evidence/task61-oo94-word-pilot-gate/mutation_four_state.json`。gate 现读 75 行、分布 `{failed: 60, passed: 11, unverifiable: 4}`、`entries_verified=[]`、退出码 1。
    - 🔴 **本轮抓出的两个真实缺陷**：①**旧 gate 第④条结构事实是重言式** —— 首版把「生产 registry 无 docx adapter」当 `word_bulk` 门未被跨越的证据，arm_b 证明把前三条前提逐一移除后它**仍然**成立（顶着它的是 BP-61-1 这条完全不同的平台级约束）⇒ 用它当门禁证据属假绿第③源（守卫把恒真值当基线锁死）。修法不是删判据，而是新增三臂 probe 把「哪一条才是绑定约束」变成可执行、可复算、且**改一位就打红**的事实。②**假 ERROR 态** —— gate/2 首跑被打成 exit 2 报 `DatabaseUnreadable`，而库其实完全可达：根因是三臂复用了 `app.core.database.async_session`，本门 `read_db_snapshot` 那次 `asyncio.run` 留在**共享池**里的连接绑定在已关闭的 event loop 上，第二次 `asyncio.run` 取到它就报 `'NoneType' object has no attribute 'send'`。修法 = 三臂专用 `NullPool` 引擎 + 用完 `dispose()`；守卫断言的是**实参** `poolclass=NullPool` 而不是符号名（只查 `"NullPool" in source` 会被那行 `from sqlalchemy.pool import NullPool` 顶住）。两条都各有一条变异（M39 / M31）把守卫钉住。
    - 辐射面回归（按引用关系反查，未跑全量）：`test_task61` + `test_task44` + `test_task13` + `test_task75` 共 **577 passed / 2 failed**，两条 failed 均为 brief 登记的长期既存红（`test_task44_oo94_excel_pilot_gate` 的两条 `*_is_fresh`），与本轮改动无引用关系。未改 `registry.py` / `word_entry_gate.py` / `projection_provisioning.py` / manifest / overlay / `backend/wp_templates/` 任何字节，未建 `adapters/word.py`，未往 `DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 加行，未写库（三臂只读）。
    - **判定：`failed`，不是 `unverifiable`** —— 沿用本 spec 的 `upstream_gap` 口径：缺的是**实现**（published representation 供给）不是**环境**（OO 容器实测可达、库可达），故 60 条 scenario probe 判 `failed/upstream_gap`；仅 4 条真正结构不可表达的判 `unverifiable`（2 条 `row_sdt` 载体在 OO 9.4 上不保留 + 2 条 quarantined 场景在本 lane 无载体）。两个 entry 的 `verification_state` 仍是 UNVERIFIABLE，**Tasks 62–64 保持阻塞**。本任务 `[-]` 与 Task 63 同型：阻塞原因已写明，属**有意驻留**，不是被中断。
    - **🔴 2026-09-03 实测更正：BP-61-1 的行数事实已过期，但约束本身未解除**。上一轮记的「`working_paper_sync_entry_state` / `working_paper_content_version` / `working_paper_content_representation` 三表 **0 / 0 / 0** 行」现已变成 **1 / 1 / 1**（definition 侧同步 6→**14** artifact、3→**5** bundle，新增 `d2.receivable_detail.authority-model` 与 `h1.disposal_check.authority-model` 两条 approved `projection_contract`）。
      🔴 **不得据此宣布 BP-61-1 解除** —— 那唯一一条 representation 走的是 **opaque lane**：库实测 `entry_id = opaque-017624e2-...`（逐底稿 opaque id，由 `opaque_entry_gate.opaque_entry_id(...)` 派生）· `adapter_id = opaque.authoritative.v1` · `source = upload` · `document_type = xlsx` · wp_code **D2** · 项目 `proj_478827f6`（测试夹具）。它**不是** 186 个 manifest planned entry 之一，因此对「manifest entry 注册」这件事供给仍为 0。
      同日 gate 真跑复核（`task61-gate/2`，退出码 1）：F2-22 / F2-23 两个 entry 的 `published_repr=False` · `manifest_entry=False` · `adapter=False` · `approved_bundle=False` · `entries_verified=[]` · 60 failed / 11 passed / 4 unverifiable，与上一轮逐字一致。⇒ BP-61-1 的**判据应从「三表行数是否为 0」改为「是否存在某个 manifest entry 的 current published representation」**；按行数判会在下一轮把 opaque lane 的产出误读成解除条件（假绿第③源：把易变的旁路观测值当门禁基线）。
      另一处值得警惕：`d2.receivable_detail.authority-model` 这条 approved `projection_contract` bundle 已存在，而**同一张 D2 底稿**的 representation 却是经 opaque 权威模型发布的 ⇒ projection lane 与 opaque lane 对同一 wp 同时可达，谁被选中取决于调用点而非 bundle 供给。解除 BP-61-1 时必须一并确认选路判据，否则「provision 了 projection bundle」与「representation 真按 projection contract 发布」是两件事。
    - 解除顺序（不可交换）：**BP-61-1**（任一 entry 先有 current published representation；最短路径是让 Task 76 已 provision 的 b60 Excel pilot 走通 `ContentMutationService.commit` 首版 content version）→ **BP-61-2**（F2 前端需要一个 `document_type=='docx'` 的真实挂载点，manifest 才会扫出 docx F2 entry；改的是 `GtF2StocktakeBundle.vue` + overlay 的 `defaults_by_component`，属 Task 60 的 descriptor/bridge 一段）→ **BP-61-3**（此时 `adapters/word.py` 才有构造点，建它不再是死代码）→ 本任务正文列举的全部真实 OO 场景。
  - 独立验证 Property 30、Property 31、Property 32、Property 33、Property 34、Property 55、Property 56、Property 58、Property 62、Property 65、Property 69、Property 71。
  - _Requirements: 4.11, 7.1, 7.3, 7.4, 7.6, 7.8, 8.10, 12.3, 12.10, 14.2, 14.3, 14.4, 14.6, 14.7, 14.8, 14.9, 14.16_

### Wave 6：Word 全量、custom、legacy 删前隔离与 pre-reconcile

- [x] 62. 逐一迁移 18 个 generic DOCX entry
  - 每份读真实模板并为该 entry发布自己的 approved authority model、tagged-SDT per-entry contract与 non-null bundle；经 Task 59 candidate的 tag/Word-only等值校验并由 Task 15 finalize为 published representation后，才注册 adapter/接宿主/标 bidirectional。不得跨 entry复用 bundle/candidate/evidence。
  - 多 token、跨 run、重复实例逐项处理；candidate/unapproved/missing-contract bundle不可 resolver/room/current/evidence，缺真实 OO required scenarios保持 UNVERIFIABLE。
  - **裁决实证脚注（本任务不发布 per-entry 契约，理由如下）**：18 份权威模板逐份 zipfile + python-docx 现读后，**18/18 全部 blocked**，`entries_with_instrumentable_verdict = 0`。verdict 由事实派生、封闭词表、五档分布：`blocked_non_discriminating_literal_anchor` **10**（B5-1/2/3/4/6/7/8-1/8-2/9-1/9-2）· `no_managed_field_candidate` **3**（A26-2 / A8-2 / B1-7）· `blocked_nested_literal_anchor` **2**（B5-5 / S12A）· `blocked_partial_field_fragment_anchor` **2**（A26-1 / A26-4）· `blocked_literal_anchor_split_across_runs` **1**（A26-3）。🔴 **不发契约的理由不是「零 `${}` token 所以造不出锚点」**（与 Task 64 脚注逐字对齐）—— 该说法已由本任务的 impl 真跑证伪：`WordFieldInjection(literal_anchor=True)` 可构造，记录内的 `mechanism_probe` 对 A26-1 / A26-4 真跑了 `instrument_docx_bytes` → `verify_docx_visible_equivalence` → `read_back_word_tags` 并逐条通过（`equivalent=true`、`outside_sdt_text` 覆盖 123 / 61 字符非空转、`untouched_parts=21`、非 document part 逐字节相同、tag 反读 1 tag/1 instance/0 untagged）⇒ 机制在 F2 之外的真实 generic 模板上确实可用。真实理由是五条各自独立现算的结构性障碍：①**锚点不具区分度** —— 一个 literal token 只能绑一个 stable key 且全部出现处注入同一 tag，而 `××` 在单份约定书里最多出现 **22** 次、语义各不相同；②**候选 span 互相嵌套/重合**（实测 2 identical + 6 contained，典型 = `202X年` 落在 `202X年12月31日` 内，`_LEGACY_PATTERNS` 自身互相重叠所致）⇒ 两者同时注入 SDT 结构上不可能；③**锚点被 run 边界切断** —— 本轮新发现：`instrument_docx_bytes._token_paragraphs` 要求 token **verbatim 出现在原始 `word/document.xml`**，而 python-docx 会把跨 run 的 `w:t` 拼起来，A26-3 的 `202X年` 在原始 XML 里连 `202X` 都搜不到（6 个 entry 至少一个 literal 命中此类，已由「真喂进注入引擎必抛 `WordTokenAnchorError`」实证）；④**锚点只是更大人类占位的片段**（`截至202X年X月X日` / `202X年第YY次`），注入后旁边的 `X月X日` / `第YY次` 仍是死文本，17/18 个 entry 存在 parser 不认的占位形态；⑤**字段身份不稳定** —— HTML 对端（`_word_template.py` + `GtWordTemplateStructuredView.vue`，持久化 `checklist_responses.item_id = wt-{wp_code}-{field_id}`，DB 实测 `wt-%` **0 行**）的字段由 `wp_docx_template_parser._LEGACY_PATTERNS` 中文标记正则现算（Requirement 7.1 逐字禁止中文正则作回写协议），136 个候选里 **115** 个 field_id 带 `_dedupe_field_id` 的文档扫描顺序序号后缀、全部只有「审计年度 / 待填内容 / 报告日期」3 种 label，而 design 对 `stable_field_key` 的定义是「adapter 全局稳定键」；另实测 `parse_template` 的表格循环 `for cell in row.cells` 会把横向合并单元格按跨列数重复扫描（A26-1 的 4 个 `audit_year` 实为 1 个合并单元格）。把这批候选写成 `review_status="reviewed"` 契约会让机器侧全绿（`assert_projection_supply_authentic` 只查 `review_status` 字面），实质是伪造供给。产物：生成器 `backend/scripts/gen/generate_task62_generic_docx_adjudication.py`（`--check`/`--write` 互斥必选，三边锁 = Task 58 清册 ↔ `backend/wp_templates/` 磁盘真读 ↔ impl 现读 `_LEGACY_COMPILED`/`_NEW_PLACEHOLDER_RE`/`WordSdtCarrierGate.load()`/`PENDING_ENGINE_ADAPTERS`/AC 7.7 声明数，`--check` 与磁盘逐字节比对）+ 裁决记录 `backend/data/workpaper_sync_task62_generic_docx_adjudication.json`（204 KB，逐 entry 模板身份/结构事实/候选清册含 context/两视图计数/verdict/blocking_reasons/evidence=UNVERIFIABLE，counters 全现算）+ 守卫 `backend/tests/workpaper_sync/test_task62_generic_docx_entries.py`（**53 passed**，10 个测试类）+ 变异脚本 `backend/scripts/diagnose/mutate_task62_generic_docx_guards.py`（19 条，`--run all` **19/19 全 RED**，`--check-anchors` 19/19 OK 且目标文件 md5 未变）。新登记 **BP-62-1 / BP-62-2 / BP-62-3**：🔴 **id 刻意用 task-scoped 前缀而非全局 `BP-NN`** —— 实测 Tasks 63 与 64 的裁决记录**各自**登记了 `BP-16`~`BP-20`（Task 64 到 `BP-22`）、同号不同义，全局单调编号在多会话并发下已被双重占用，接回去只会制造第三份冲突（守卫用 `re.fullmatch(r"BP-62-\d+")` 锁死）。BP-62-1 = `word-template` HTML 业务模型没有稳定字段身份（解除动作跨 `word-template-dual-mode` feature 与运行时权威模板库，需自己的 spec 三件套，**明确不属 Task 62 权限**；记录内 `same_root_cause_as` 指向 Task 64 的 BP-17 与 Task 63 的 `field_identity_admissible_entries: []`，并写明三条独立取样路径复现同一根因：本任务 18/18 模板 `declared_dollar_token_count=0`、Task 63 记录 `dollar_token_total=0`、Task 64 记录 A16 链 HTML 字段面为 0）· BP-62-2 = Word adapter 仍被 `PENDING_ENGINE_ADAPTERS` 禁止落地（owner = Task 61）· BP-62-3 = Word lane 的 published representation 供给为 0（`working_paper_content_version` / `..._representation_upgrade_candidate` / `..._content_representation` / `..._sync_entry_state` 实测 0 行，唯一 bundle 属 `b60.hour_budget` Excel pilot）。未越 Task 61 的 `word_bulk` 门：未建 `adapters/word.py`、未往 `DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 加行、未改 manifest、未改 `backend/wp_templates/` 与 `wp_docx_template_parser.py` 任何字节、未往 `workpaper_sync_word_contracts/` 写一份文件（守卫断言该目录内容**恰等于** F2 发布记录登记的两份）、未碰 DB（守卫用 **AST** 断言生成器无 DB import、无发布链调用、`write_text` 只对 `OUTPUT_PATH`）、未宣称任何真实 OO probe 通过。本任务 `[x]` 与 Task 1/2/20/60/64 同型 —— 只表示上述裁决与守卫已交付，**不**代表 adapter 已注册或 published representation 已 finalize。🔴 **两条通用教训**：①**M15 首轮判 GREEN，追因确认是「等价变异」而非守卫缺陷** —— 两个探针 entry 上 `raw_xml_verbatim_counts` 与 `literal_anchor_multiplicity` 恰好都等于 1（该 literal 没落在合并单元格里），任何**数值**断言都测不出差别；修法不是删变异，而是把**取值来源**做成 AST 结构判据（`occurrences` 的下标必须是 `raw_xml_verbatim_counts`、不得是 `literal_anchor_multiplicity`）⇒ 转 RED。②**守卫读源码判「有没有调用某函数」必须走 AST，不能走子串** —— BP-62-3 的 evidence 文案里就写着 `WordEntryFinalizeGate.finalize_candidate`，首版子串判据被这句**说明文字**打成假红。辐射面回归（按引用关系反查，不跑全量）：`test_task58/60/77` + `test_task57/56/52` 共 **601 passed / 5 xfailed / 1 failed**，另跑并发方的 `test_task63/64` **61 passed / 7 xfailed**（我的新文件不破坏它们）。唯一那条 failed = `test_task60_f2_word_adapter.py::TestNothingUnapprovedReachesTheRuntime::test_the_lane_writers_still_declare_the_pre_task60_authority_model`，**归因为并发 Task 65 会话**而非本任务：`_f2_stocktake_{plan,summary}_sync.py` 两个 tracked 文件的 mtime 为 **08-31 23:53:42/43**（早于本会话首次写盘），`git diff` 里新增注释逐字写着「Task 65：authority model 由 lane 登记决定（`f2_stocktake_plan` → `opaque_single_onlyoffice`），不再由调用点传一个可漏可错的身份参数」—— 该 writer 把字面量搬进 lane 登记后，Task 60 那条「源码里必须出现 `opaque_single_onlyoffice` 字面量」的判据随之失守，属 Task 60/65 两方的接口，本任务未改这两个文件一个字节。**产物入库状态：4 个产物在 git 里全是 `??` 未跟踪**，需与并发方一并入库（干净 checkout 下守卫必挂）。
  - 验证 Property 30、Property 31、Property 32、Property 33、Property 34、Property 69、Property 70。
  - _Requirements: 7.1, 7.3, 7.4, 7.5, 7.6, 7.8, 12.1, 12.5, 12.10, 12.11, 12.12_

- [x] 63. 逐一处理 9 个 B 子码错型与 `S33-REV`
  - 有合法 DOCX+HTML 对端时，为该 entry发布 approved authority model、tagged-SDT per-entry contract与 non-null bundle，并在 Task 59 candidate通过后 finalize published representation才启用；不得回退父级 XLSX、复用父 entry bundle或让 candidate进入运行态。
  - 无合法模板/HTML 对端则裁决 single/missing并移除假切换，不为满足数字伪造 contract/bundle/finalize；每个 entry保留自身 evidence/UNVERIFIABLE状态。
  - **驻留原因与已交付部分（2026-08-31 实证）**：裁决清册 `owner_task=63` 恰 10 行 = 9 个 B 子码 + `S33-REV`，逐 entry 记录见 `backend/data/workpaper_sync_task63_subcode_adjudication.json`（生成器 `backend/scripts/gen/generate_workpaper_task63_subcode_adjudication.py --check` 幂等，守卫 `backend/tests/workpaper_sync/test_task63_subcode_adjudication.py` 33 passed，变异 `backend/scripts/diagnose/mutate_task63_subcode_guards.py` 23 条全 RED、覆盖面 2/2）。
    - **第二条 bullet（`S33-REV`）已完整闭环**：模板库零载体 ⇒ Task 58 resolver 现算判 `template_missing`；新增 `word_resolution.WordCarrierVerdict` 封闭三值（与清册 `unified_verdict` 同名同域）+ `word_carrier_verdict()`，经 `_word_template._carrier_absence_payload()` 下发到 `html_data.word_carrier`，宿主 `WorkpaperWordEditor.vue` 按它门控掉双模式切换/结构化视图/在线编辑三处入口（零 wp_code 字面量），并删除 `wpPopupDocxConfigsS.ts` 里 S33-REV 的假切换条目。载体线索 `S/S33-1程序修订说明.docx`（业务名与 wp_name 逐字对应，且同一笔误使严格 resolver 对 `S33-1` 亦误指）连同 OPT-A 改名 / OPT-B 显式映射两方案登记为 `pending_business_confirmation`，**不擅自改运行时权威模板库**。
    - **第一条 bullet（9 个 B 子码）结构上不可执行**，两条并列阻塞：① **BP-18** `registry.PENDING_ENGINE_ADAPTERS` 仍禁 `adapters/word.py`，放行门是 Task 61（当前 `[-]`；🔴 原文此处写「其 BP-10~BP-15 六条全 open」已于 2026-09-04 重验时**删除** —— 该转述已被 Task 61 自己 2026-09-01 的记录证伪，详见下方重验条目）；② **BP-20** 字段身份基础不合法 —— 9 份权威 DOCX 的 `${token}` 占位符现算共 **0 个**，HTML 侧 11 个字段全部由 `wp_docx_template_parser` 的 legacy 中文标记（`××`）+ 出现顺序编号派生成 `placeholder_generic_N`，违反 Requirement 7.1 且与 Task 6 裁 `failed` 的 `paragraph_index` 同一失效模式；`B40-1`/`B40-2` 结构化岛为空集。故本轮 `published` 五个 id 全 `null`、`registered_adapters=0`、9 个 entry 保持 `UNVERIFIABLE`，**不发布任何 contract**（守卫 `test_no_word_contract_was_staged_for_b_subcodes` 对 staged 与生产两个目录同时把关）。解除需底稿模板编制方为这 9 份引入 `${token}` 或逐份裁定每个 `××` 的业务语义。
    - `B2-3` 载体二义（两封沟通函，sha256/size 均不同 ⇒ 两份不同文档）登记为 **BP-19** + OPT-SPLIT / OPT-PRIMARY 两方案，`recommended` 均为 `null`（正本归属与新 wp_code 编码属业务判断）。
    - 本任务 `[-]` 与 Task 61 同型：阻塞原因已写明，属**有意驻留**，不是被中断。
    - **🔴 2026-09-04 逐条重验（四条阻塞全部现算，判定仍 `still_open`；判据与现算结果写进裁决 JSON 的 `blocking_preconditions[].measured` 与新增 `residency_reverification` 块，`--check` 幂等）**。上一轮证据写于 2026-08-31，其后 Tasks 62/64/67/76/77 落地，故本轮先重验而非复述。🔴 顺带更正一处常见误记并留一条方法论：**Task 75 今日复选框实扫是 `[-]` 而非 `[x]`**；而 **Task 76 在本轮会话进行中由并发方从 `[-]` 翻成 `[x]`**（本轮开工时实扫 `[-]`，收尾时实扫 `[x]`，tasks.md mtime 两次分别为 `00:46` 与 `00:55`）—— 故引用「其他任务的复选框状态」这类**并发可变量**时必须写明取数时刻，否则同一份记录里前后两句就会互相矛盾。今日全量实扫仍为 `[-]` 的是 **61 / 63 / 71 / 72 / 74 / 75** 六条。
      - **BP-16 `still_open`**（owner = manifest 生成侧 / Task 67，**不在 Task 63**）—— 本条最被怀疑已因 Task 67 重生成 manifest 而漂移，实测**未漂移**：`workpaper_sync_entry_manifest.json` 现有 **186** 条 entry（`document_type` 分布 `{docx: 7, xlsx: 179}`），9 个 B 子码在任何 entry 的 `wp_match.wp_code_patterns` 里**逐字命中 0/9**，仍只被泛匹配 entry `docx/gt-wp-renderer`（`wp_code_patterns: []`、`independent_entry: true`）覆盖；7 条 docx entry 里仅 4 条带 patterns（`A10B` / `A12B` / `A16B` / `A17B`），无一覆盖 B 子码。🔴 判据刻意定为「9 个 wp_code 里有几个能逐字命中」而**不是**「manifest entry 总数」—— 后者每次 Task 67 重生成都会变，拿它当判据必然周期性假红/假绿。
      - **BP-17 `still_open`**（owner = 平台侧 published representation 供给，**不在 Task 63**）—— 代码层两条同时成立：`assert_may_publish()` 在非 `bundle_bound` 或 `bundle is None` 时**恒抛** `WordApprovedBundleRequiredError`；candidate 登记处仍把 `target_contract_definition_id` / `target_definition_bundle_id` **双双写死 `None`** 且 `state=CandidateState.awaiting_contract`（`word_instrumentation.py` L1715–1717）。库侧 lane 内实测全 **0**：`document_type='docx'` 的 representation **0** 条；9 个 B 子码在 `working_paper_content_representation` / `working_paper_sync_entry_state` / `working_paper_sync_definition_artifact` 三处各 **0** 行。🔴 **两处措辞已修**：其一 `source_refs` 补上 `word_sdt_engine.py` —— `assert_may_publish` 的**定义处**在那里（L494），首版只列 `word_instrumentation.py` / `word_entry_gate.py`，读者按 refs 去找那个「恒抛」的方法会找不到（`word_entry_gate.py` 里只有**调用**）；其二补 `scope_note` 写明判据是 **lane 内**而非平台级 —— 平台侧今日已有 **23** 条 definition artifact / **9** 个 bundle / **4** 条 current published representation（属 `b60` / `d2` / `g7` / `h1` 与 opaque lane，其中 3 条是真 manifest planned entry、全为 xlsx），按平台行数判会把别的 lane 的产出误读成本 lane 解除 —— Task 61 的 BP-61-1 已在 2026-09-03 踩过这个坑。
      - **BP-18 `still_open`**（owner = Task 61）—— `PENDING_ENGINE_ADAPTERS.forbidden_paths` 现算 = `['app/services/workpaper_sync/adapters/word', 'app/services/workpaper_sync/adapters/word.py']`，**逐字包含**真实目标且两者磁盘上均不存在；`blocking_task` 字段仍是 `"59,60,61"`，Task 61 复选框现扫仍 `[-]`。判据按 Task 64 M13 的教训写成「必须**包含**那个真实路径」而非「清单非空 + 逐项不存在」（后者可被改名成 `adapters/word_DISABLED.py` 绕过）。🔴 **措辞已修**：删掉「其 BP-10~BP-15 六条全 open」—— 已被 Task 61 自己 2026-09-01 的记录**证伪**（那四条平台欠账由 Tasks 75/76/77 解除，Task 61 改登记 BP-61-1/2/3，唯一 `kind=binding` 的是 **BP-61-1** published representation 供给，`scope=platform_wide_not_f2_specific`，生产者是 `ContentMutationService.commit(...)` 与 Tasks 36/77 的 finalize gate，**owner 既不在 Task 61 也不在 Task 63**）。本轮起 BP-18 **不再转述上游阻塞编号** —— 转述上游编号正是这次失准的根因；反向守卫 `test_bp18_no_longer_restates_upstream_blocking_ids` + 变异 **M28** 钉住不许回退。
      - **BP-20 `still_open`**（owner = **底稿模板编制方，属业务输入不属编码**）—— 10 份权威 DOCX（9 个 wp_code，`B2-3` 二义两份）逐份重新解压现算：`${...}` 在 `word/document.xml` 与全部 `word/*.xml` 里**双双为 0**、合计 **0**；`backend/wp_templates/` 下 `~$` 锁文件 **0** 个，10 份 sha256 与记录逐字一致。生产 parser 现算派生字段按 wp_code 合计 **11**（B18-3-1·1 / B18-3-2·1 / B2-1·2 / B2-11·1 / B2-3·1 / B2-6·4 / B2-8·1 / B40-1·0 / B40-2·0），**全部**是 `placeholder_generic*`、label **只有一种**（「待填内容」）、position **全部**是 `paragraph_index` 绝对索引 —— 与 Task 6 裁 `failed` 的失效模式逐字同型；`B2-6` 更有 3 个字段**同落 `paragraph_index: 1`**（连段内都不具区分度）；`B40-1` / `B40-2` 字段集为空 ⇒ 契约必空转。
      - **顺带修掉一个既存脚本缺陷**：变异 **M11** 首跑判 **WRONG-TEST**，追因确认**既不是守卫缺陷也不是行为回归** —— 变异确实把该门那条测试打红了（`8/9 passed`，红的正是它），但 `want` 写的是一个**已不存在的测试标题**（旧名「不发起 template-structure / onlyoffice-config 请求」）；前端 spec 在 2026-09-01 被改名为「不发起结构化取数与 onlyoffice-config 请求」，`want` 随之过期（`WorkpaperWordEditor.vue` mtime 2026-09-06 属并发会话，本轮未改它一个字节）。**通用教训**：fe 侧 `want` 是**测试标题子串**，标题一改就悄悄失配，而四态里 WRONG-TEST 长得很像「污染残留」，容易被误判成守卫问题去改生产代码。
      - **本轮交付**：生成器新增 `_manifest_lane_facts()` / `_word_adapter_gate_facts()` / `_word_publish_gate_facts()` 三个现算判据 + `sources` 增锁 4 份源文件 digest（manifest / `registry.py` / `word_sdt_engine.py` / `word_instrumentation.py`）+ `residency_reverification` 块；守卫新增 `TestResidencyReverification` **6** 条（逐条**重算**期望值而不采信记录里的数，含「digest 与磁盘现算相等」与「重验判定必须覆盖 entry 真正挂着的每条 BP，分母由 `blocked_by` 现算」）；变异 **23 → 29** 条，`--run all` **29/29 全 RED**（0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST，覆盖面 2/2、目标文件 md5 全部未变、无 `.mutbak` 残留），守卫 **33 → 39 passed**，生成器 `--check` 幂等。
      - **解除条件（不可交换）**：**BP-20**（业务输入：为这 9 份 DOCX 引入 `${token}`，或逐份裁定每个 `××` 的业务语义并落成显式字段清册）→ **BP-16**（为 9 个 wp_code 建 per-entry manifest entry）→ **BP-17**（平台侧 published representation 供给）→ **BP-18**（Task 61 的 `word_bulk` 门）。🔴 **只要 BP-20 未解除就不存在合法的 `stable_field_key`，任何 per-entry contract 都不得发布** —— 即便 BP-16 将来因 Task 67 重生成而解除，那也只改变「阻塞清单」，不改变「9 个 entry 仍 UNVERIFIABLE」这个结论。本轮**未**发布任何 contract / authority model / definition bundle / finalize representation，**未**建 `adapters/word.py`，**未**改 `PENDING_ENGINE_ADAPTERS` / manifest / `backend/wp_templates/` 任何字节，**未**写库（重验全程只读），**未**碰 `backend/data/amount_input_migration_status.json`。**判定：保持驻留。**
  - 验证 Property 40、Property 41、Property 69、Property 70。
  - _Requirements: 7.7, 9.4, 9.5, 12.5, 12.8, 12.10, 12.11, 12.12_

- [x] 64. 迁移 A16/A17 专用 Word 链与全部 Word editor 宿主
  - 为每个保留的 A16/A17/Word editor独立 entry读真实模板，发布 approved authority model、tagged-SDT per-entry contract与 non-null bundle；Task 59 candidate通过后 finalize published representation，才统一 room/forcesave/callback/merge并接宿主，不以 structuredFlush/load或 candidate冒充闭环。
  - 每个 `WorkpaperWordEditor`/`OnlyOfficeWordDialog` 宿主有自身 DOM、recovery/operation、published artifact与 bundle digest evidence；不得跨 entry复用 contract/bundle/scenario。
  - **裁决实证脚注（本任务不发布 per-entry 契约，理由如下）**：逐 entry 现算后，四条 docx entry 无一条同时满足「保留」与「projection 有对端」两个前提，故按 Task 63 同款条款「无合法模板/HTML 对端则裁决 single/missing，不为满足数字伪造 contract/bundle/finalize」交付**裁决 + 如实登记**。四条裁决各自独立推导：`docx/gt-a16-bundle` = `opaque_ooxml_authority`（mount 真实可达、承载 A16-1..A16-7 七个真实 DOCX，但生产 HTML 侧字段面实测 **0** —— `_word_template.py` 经 `wp_docx_template_parser.parse_template` 对七份模板全返 0 个 placeholder，审计师在 Word 里写整篇声明书 ⇒ docx 本体即业务权威）；`docx/gt-a17-bundle` = `unreachable_stub`（`WorkpaperWordEditor` 挂载点外层门控是 `v-else-if="tab.kind === 'word'"`，而静态 TABS 十条无一条 `kind: 'word'`，该 kind 只存在于 TabDef 类型联合里 ⇒ 运行时恒假，Requirement 1.7）；`docx/workpaper-word-editor` = `parent_duplicate_follows_parent`（manifest `independent_entry=false`）；`docx/wp-popup-docx-editor` = `shared_room_opaque_multiplexer`（一条 entry 复用给 97 个 popup 配置，而 `SyncContract.template` 是单个 `TemplateRef`）。🔴 不发契约的理由**不是**「零 `${}` token 所以造不出锚点」—— 该说法已由 impl 真跑证伪（`WordFieldInjection(literal_anchor=True)` 可构造、Task 6 对 B30-11-2 用的就是字面标题；`WordRowInjection` 支持一次性单元格坐标；15/15 模板都有 `w:tbl`），真实理由是**投影无对端**：给没有消费方的投影建 SDT/契约即 additive 死代码（假绿第①源），且 `registry.assert_authority_model_contract_pairing` 对非 projection 传 `SyncContract` 直接抛 `AuthorityModelMismatchError`。产物：生成器 `backend/scripts/gen/generate_task64_dedicated_word_chain.py`（`--check`/`--write` 幂等）+ 裁决记录 `backend/data/workpaper_sync_a16_a17_word_chain_adjudication.json`（内嵌逐 entry evidence、模板 zip 级事实、HTML 投影字段面、mount 门控链、五条 impl 真跑反证、counters 与 property 分母）+ 守卫 `backend/tests/workpaper_sync/test_task64_dedicated_word_chain.py` + 变异脚本 `backend/scripts/diagnose/mutate_task64_dedicated_word_chain_guards.py`。新登记 **BP-16 ~ BP-22**（续接 Task 60 的 BP-15）：BP-16 A16 链 HTML 字段面为 0 · BP-17 生产定位仍靠 legacy 中文正则 + `paragraph_index` 绝对索引 + 序号后缀 field_id（14 处占位符 100% 命中 Task 77 三条禁令）· BP-18 manifest 的 `mounts[].condition` 缺外层 kind 门控致死代码不可见 · BP-19 两个 Word 宿主均非 descriptor consumer 且 `WorkpaperWordEditor` inbound 跨 Task 62/64 · BP-20 opaque authority 通道归 Task 65 且需 DB 侧 definition 行 · BP-21 单 `TemplateRef` 无法表达一对多 popup · BP-22 A17 七个 docx 子码有 HTML 对端与自有 DOCX 载体（清册裁 `resolved_docx`）但 manifest entry 全是 `document_type=xlsx`。未越 Task 61 的 `word_bulk` 门：未建 `adapters/word.py`、未往 `DELIVERED_PER_ENTRY_CONTRACTS` / `_ALLOWED_PROVIDER_MODULES` 加行、未改 manifest、未改 `backend/wp_templates/` 任何字节、未改 capability、未宣称任何真实 OO probe 通过。本任务 `[x]` 与 Task 1/2/20/60 同型 —— 只表示上述裁决与守卫已交付，**不**代表 adapter 已注册或 published representation 已 finalize。变异检验 **17/17 全 RED**（0 GREEN / 0 ANCHOR-MISS / 0 WRONG-TEST），覆盖数据侧 M01–M10、真源码侧 M11–M14、反向变异 M15–M16（把 BP-17/BP-19 的缺陷「修好」时对应 `xfail(strict)` 解除探测 XPASS ⇒ 必红，杜绝「代码改好而记录仍挂 open」）、观测值口径 M17；守卫 28 passed / 7 xfailed（7 条 BP 解除探测各一条）。🔴 **M13 首轮判 WRONG-TEST 并因此抓出一个真实的守卫缺陷**：把 `PENDING_ENGINE_ADAPTERS` 的被禁路径从 `adapters/word.py` 改名成 `adapters/word_DISABLED.py`（等于把 Task 61 的门挪开、Word adapter 换个文件名即可落地）时，原守卫「清单非空 + 逐条不存在」两条**仍然满足**故全绿；已补「清单必须**包含**真实 `app/services/workpaper_sync/adapters/word.py`」一条后转 RED —— 这条教训通用：**禁令清单类判据必须断言「包含那个真实目标」，只断言「非空 + 逐项成立」会被改名绕过**。六条真源码变异跑完已逐条核验干净还原（变异文本零残留、原文在位）。**产物入库状态：5 个产物（生成器 / 裁决记录 / 守卫 / 变异脚本 / 本 tasks.md）在 git 里全是 `??` 未跟踪**，且实测 `backend/app/services/workpaper_sync/adapters/registry.py` 本身也未被 git 跟踪（Task 13 产物从未提交）⇒ 干净 checkout 下守卫必挂，需各推进方尽快入库。
  - 验证 Property 30、Property 31、Property 47、Property 69、Property 70。
  - _Requirements: 7.1, 7.3, 11.4, 11.5, 11.12, 12.1, 12.5, 12.10, 12.11, 12.12_

- [x] 65. 收敛 custom/user-upload xlsx 单一权威 bundle 协议
  - custom 继续以 xlsx artifact为唯一业务权威并进入统一 room/durable ack/content version/representation/evidence，不调用标准 JSON projection writer。
  - 每类 custom/opaque entry必须先发布 approved `custom_authoritative_ooxml` 或 `opaque_single_onlyoffice` authority-model definition与 non-null approved definition bundle；template/instrumentation/contract optional child只能使用 registry中版本化 typed null markers，slot omission、SQL/JSON NULL、空串、全零 hash均拒绝。无 explicit contract的 user upload不强制 instrumentation，sidecar不得改变原文件语义。
  - application key仍冻结 bundle/authority-model digest；same incoming在不同 bundle或authority model下必须产生不同 identity，不能折叠或借旧终态绕过当前 authorization/write fence。
  - 验证 Property 50、Property 64、Property 69。
  - _Requirements: 2.11, 3.9, 5.5, 6.19, 12.6, 12.10_

- [x] 66. 建 legacy 删前清册、逐 entry replacement map 与 rollback 隔离门（只生成计划，不改源码）
  - 为旧 composable/factory/endpoint/localStorage/状态机/paragraph fallback/成功文案逐项绑定 replacement entry、owner、最后调用点、rollback target 与所需 scenario evidence。
  - 本任务只生成 source-backed deletion plan、精确待删 digest 与反向守卫；不 feature-disable、不删除、不改调用点，避免在 Task 70 前改变 source commit 使 evidence stale。Task 45 已完成的 pilot 局部删除以其 post-delete 新 evidence 为准。
  - 证明无消费 bridge、旧 config 二次请求、single 假切换、fail-open 文案与 unreachable 桩全部被唯一归入 replacement 或 pending-delete；未通过 Task 70 的全局共用路径、兼容 endpoint 与 fallback 不得变更。
  - 验证 Property 3、Property 46、Property 47、Property 48、Property 51。
  - _Requirements: 1.4, 1.5, 1.7, 11.1, 11.2, 11.5, 11.8, 11.10, 12.7, 12.8, 12.9, 12.13, 12.14_

- [x] 67. structural pre-reconcile manifest/registry/definition/bundle/candidate/deletion-plan
  - 从最终源码重新生成 mounts 与 source-backed manifest，逐 entry 锁定 source digest、`editable`、`room_model`、`scenario_profile`，并与 registry、宿主 DOM、descriptor/room 配置、authority-model/contract/definition bundle、candidate/published result representation及 Task 66 deletion plan 双向核对；父入口不重复计数，profile 降级、计划外 legacy/unreachable 或 digest/owner/rollback缺失立即报结构错误。
  - 校验 `template → instrumentation → contract → bundle → representation` 的 child kind/state/digest、projection contract approved child、typed null marker规则、candidate non-current/non-resolvable、pure upgrade revision不变与历史 retry frozen bundle；同时核对forcesave `(room,generation,participant,kind,key)` + frozen fingerprint、application origin/effective sequence与room canonical fence、application↔primary operation一对一、duplicate direct canonical约束与零stranded shell、delivery durable_at owner约束、application/engine durable-only且quarantined不可release/消费、close authorization-stale successor/recovery-required结构、scope tombstone存在/retired不可删除复用、content version scope只用opaque UUID且numeric revision非route/resource key及incoming非published，并按source/manifest/profile/definition/bundle/candidate变化逐entry生成evidence重跑集合。
  - 本任务是 structural pre-reconcile，只允许并如实报告未裁决、假双向、未验收、unreachable、evidence stale及 planned-delete 计数；允许报告 stale，不要求 stale 清零，不运行真实 OO场景，不授权删除，也不把 planned-delete当作最终五个零。
  - 输出只供 Tasks 68/69 独立结构复验与 Task 70全 entry required-scenario刷新；真正删除前判断只在 Task 72 Stage A执行。
  - 验证 Property 1、Property 2、Property 3、Property 28、Property 51、Property 67、Property 69、Property 70、Property 71。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 6.10, 6.18, 9.8, 9.9, 9.10, 12.10, 12.11, 12.12, 12.13, 14.16_

### Wave 7：独立验证、逐 entry evidence、全局 legacy 删除与归档

- [x] 68. 后端全链、bundle/candidate/recovery 与辐射面独立回归
  - 运行 migration/repository/artifact/retention/content+representation mutation/definition-bundle store/candidate finalize/room/close-intent/request/delivery/recovery/content-application/operation/scope-index/merge/coordinator/outbox/evidence/Excel/Word targeted tests。
  - 真实PostgreSQL独立校验forcesave request复合唯一键`(room,generation,initiated_by_participant_id,kind,idempotency_key)`与immutable `frozen_request_fingerprint`，跨participant/kind/payload复用key 409且不返回旧ID；`working_paper_content_application.application_key` UNIQUE、`origin_request_sequence`不可变、`effective_request_sequence`单调GREATEST并与room canonical fence同事务，same-app higher sequence不self-supersede；operation nullable primary application FK+direct duplicate self FK、normal request+shell原子创建、N个different-request同key shell最终1 primary+N-1 terminal duplicates且零stranded/链/环；recovery claim前三实体为0及claim request+shell+application create-or-hit后primary/duplicate canonical收敛。delivery以`durable_at`为gate：pre-durable rejected/error零owner、durable correlated/unmatched恰一、post-durable error保留owner、双owner失败且request/application不做XOR。scope index与child创建/退役同事务，tombstone不可DELETE/清空/id复用，跨scope/孤儿拒绝；content version只用opaque `version_id` UUID，两个wp相同numeric revision无碰撞且numeric revision作route/resource key失败。
  - 真实PostgreSQL继续校验bundle slot NOT NULL/CHECK/trigger、projection contract approved child、typed marker非法空值拒绝、candidate不可见、incoming state只允许durable/quarantined且永不published/current/resolver-visible；application incoming FK只接durable，quarantined保持`durable_at=NULL`且禁止release/转durable/application/engine。close-capture partial unique只证明at-most-one，single/A-B两顺序/A terminal前后B close/reconciler重入最终exactly-one且0/>1均失败，打乱created_at/插入顺序仍按最高`(intent_sequence,id)`选leader；leader promotion前revoke/expire必须写`authorization_stale`，合法successor接任且无successor时generation supersede + `recovery_required`不永久阻塞，同eligibility snapshot不换leader。application key frozen bundle与同incoming不同bundle不折叠。
  - 对pending/materialize/confirm/forcesave/close-intents/recovery list/claim/download-only/operations/conflicts/timeline/resolve/`versions/{version_id}/rollback`全用户端点，独立验证显式project/wp/entry、list room/generation、rollback opaque UUID + entry scope、numeric revision禁作route key、scope-index-before-resource/cache、统一404/403阶段/时序、撤权后原Idempotency-Key重放零泄露/副作用；duplicate operation必须按requested id授权→direct-primary invariant→canonicalize→canonical primary application顺序，删除pointer/指向duplicate/先要求requested绑定application/授权前跳转均失败；错误prior confirmation/bundle/fence/contributor拒绝及nullable-operation普通retry拒绝。
  - 独立文件/契约套件验证完整 `template → instrumentation → contract → bundle → representation`、历史 frozen bundle、contract字段、动态列/行、Word tag/Word-only、resolver子码、custom approved bundle与 candidate-only upgrader/finalize owner；不得由实现任务自证。
  - 按引用关系反查辐射面，不跑无边界全量；从仓库根执行。本任务只做代码/数据库独立回归，不冒充真实 OO probe/evidence已通过。
  - 独立验证 Property 4、Property 5、Property 6、Property 7、Property 9、Property 10、Property 16、Property 17、Property 18、Property 19、Property 20、Property 21、Property 22、Property 23、Property 24、Property 25、Property 26、Property 27、Property 28、Property 29、Property 30、Property 31、Property 32、Property 36、Property 37、Property 38、Property 39、Property 40、Property 41、Property 42、Property 43、Property 44、Property 50、Property 52、Property 53、Property 54、Property 59、Property 60、Property 61、Property 62、Property 63、Property 64、Property 65、Property 67、Property 68、Property 69、Property 70、Property 71。
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.7, 2.10, 3.4, 3.6, 4.1, 4.11, 5.2, 5.5, 5.6, 5.8, 6.1, 6.2, 6.4, 6.5, 6.6, 6.8, 6.9, 6.10, 6.11, 6.18, 7.1, 7.3, 7.4, 8.5, 8.7, 8.9, 8.10, 9.3, 9.4, 9.5, 9.6, 10.3, 10.9, 10.10, 12.6, 12.10, 12.12, 13.1, 13.2, 13.4, 13.5, 14.1, 14.3, 14.6, 14.10, 14.11, 14.13, 14.14, 14.16_

- [x] 69. 前端状态机、recovery、descriptor、宿主与 DOM 独立回归
  - bridge PBT、editor mounted、状态条、冲突/recovery panel、localStorage、event refresh、server/client双基线、normal accepted pre-correlation shell→primary bound或terminal duplicate、requested/canonical operation授权跟随、refresh-required reopen与真实宿主API顺序；另独立挂载验证 leader promotion 前 revoke/expire 先显示`close_authorization_stale`，合法 successor 接任后继续同一 generation，且无 successor 时进入`close_recovery_required`并停止 loading/禁止成功文案。
  - 独立断言所有请求显式携带 project/wp/entry，recovery list另带 room/generation、rollback API/DTO使用opaque `versionId`并保留 entry scope，numeric revision不得拼route；scope/404/403失败不泄露对象。browser crash进入 recovery_pending且 claim 前 request/application/operation均为空；claim API仅成功后同时关联三者，错误 prior confirmation/bundle/fence/contributor仍保持三者为0；download-only 三者为0且不显示回写成功；普通 retry拒绝空 operation。
  - DOM/network顺序覆盖 descriptor mount→ready→confirm与 recovery list/claim/download-only；判据不以 import/字符串存在，不存在 prop/expose、editor自行取config、normal shell提前伪 application、claim前伪三实体或fail-open文案立即失败。
  - 独立验证 Property 8、Property 11、Property 12、Property 13、Property 14、Property 15、Property 35、Property 46、Property 47、Property 48、Property 58。
  - _Requirements: 3.2, 3.7, 4.1, 4.4, 4.5, 4.7, 5.8, 8.1, 11.2, 11.4, 11.5, 11.6, 11.9, 11.10, 11.11, 11.12, 14.7, 14.8, 14.13_

- [x] 70. 在 Task 67 structural report 后按 source profile 运行真实 OO 9.4 全 entry required scenarios并刷新 evidence
  - 先消费 Task 67结构报告与 Tasks 68/69回归结果；对每个保留 entry 从 source-backed manifest 的 `editable/room_model/scenario_profile` + capability + approved bundle + authority model重新推导完整 required scenario set，固定 source/profile digest并以新的 test run刷新 stale evidence。Task 67只报告 stale，本任务负责真实刷新但不执行删除判断。
  - projection-based entry逐一运行 HTML→OO、OO→HTML、identity、different-field merge、same-field conflict/resolve、frozen-base status 6/2 dedupe、same-application higher-sequence fold不self-stale、跨participant同Idempotency-Key及不同kind/payload均409且不泄露旧ID、quarantined拒绝application/engine、opaque version UUID rollback与跨wp同numeric revision无碰撞、browser crash no-userdata recovery case、authorization-first claim、错误 prior confirmation/bundle/fence/contributor拒绝、download-only 三实体为0、merged≠incoming refresh/reopen与 rollback；每个 `editable=true AND (capability=bidirectional OR room_model=shared)` entry 无条件执行 single close、两个用户两种关闭顺序、A terminal 前/后 B close、leader promotion前revoke/expire后的successor与无successor`recovery_required`、`reconcile_close_intents()` 重入及适用路径最终 exactly-one close-capture，dynamic/Word-only再按 profile追加场景。
  - custom/opaque仅按 approved bundle中的枚举 authority model替换字段级场景；未知枚举、自由文本理由、profile降级、普通 smoke或同一 application/operation跨场景复用不得豁免。
  - 每 scenario持久化自身 recovery case/request/application IDs/operation/content version/published result representation/artifact/projection、authority-model digest、bundle id/digest/typed children、manifest/profile digest、OO/browser build与 trace bundle；服务端从 DB/recovery+application+operation timeline/artifact重算。authorization-first claim 必须证明 request + shell 原子创建并创建/命中 application，且 commit 前 shell 收敛为 primary 或 direct terminal duplicate、case/delivery 指向同一 canonical application；download-only则证明三者均为0。
  - 联合浏览器和服务端 timeline；失败修复并重跑，无法运行标 UNVERIFIABLE且保持未验收，不宣称任何 probe已通过。所有 required scenarios刷新完成前 Task 72 Stage A保持红。
  - 独立验证 Property 20、Property 21、Property 22、Property 23、Property 25、Property 26、Property 28、Property 30、Property 31、Property 32、Property 33、Property 34、Property 39、Property 40、Property 41、Property 49、Property 50、Property 55、Property 56、Property 58、Property 62、Property 63、Property 64、Property 65、Property 66、Property 67、Property 69、Property 70、Property 71。
  - _Requirements: 4.3, 4.10, 4.11, 5.5, 6.1, 6.2, 6.4, 6.5, 6.8, 6.10, 6.16, 6.18, 7.1, 7.3, 7.4, 7.6, 7.8, 8.10, 9.3, 9.4, 9.5, 10.4, 10.9, 12.2, 12.6, 12.10, 12.11, 12.12, 12.13, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.8, 14.9, 14.14, 14.16_

- [-] 71. 变异、容量、故障恢复、retention/脱敏/告警与数据复原验收
  - application/protocol变异覆盖把`application_key`错放operation、incoming durable前预建application、normal forcesave未创建pre-correlation shell、forcesave唯一键漏generation/participant/kind或cache hit不比`frozen_request_fingerprint`并向跨participant/kind/payload调用返回旧ID、N个different-request同key后删除`duplicate_of_operation_id`/指向duplicate/形成链环/duplicate再绑application/留下stranded waiting shell、duplicate resolve先要求requested operation绑定application/授权前跟随primary或retry新建operation/application；sequence变异覆盖改写`origin_request_sequence`、不GREATEST提升`effective_request_sequence`、room只推进raw sequence不保存canonical application或same-app fold自我supersede。delivery变异覆盖把owner gate改回terminal、pre-durable rejected/error强制owner、durable零owner、post-durable error丢owner、request/application错误XOR或application/recovery双归属、incoming state=`published`/成为current或resolver可见，以及quarantined被release/转durable/建application/进入engine。
  - scope/close/DAG变异覆盖scope index缺失或篡改仍可读、child退役时物理删除/清空tombstone或复用resource id、先查业务row/cache再授权（cache-before-auth）、跨project/wp/entry、recovery list漏room/generation、rollback漏entry/`version_id`或使用numeric revision作route/resource key并让两个wp同revision碰撞、404/403阶段或时序泄露；把Task 24对Task 23依赖删掉、leader comparator改为`created_at`、closing仍计active、barrier/leader漂移、promotion前revoke/expire不写`authorization_stale`、同eligibility snapshot换leader、合法successor不接任、无successor不supersede generation/不落`recovery_required`、`reconcile_close_intents()`不重入/不幂等、A terminal前后B close最终0条或>1条close-capture均必须打红。
  - 其余协议变异覆盖 writer bypass/双 content commit/representation增 revision、mtime doc_key、claim None、participant-bound callback、撤权 cached replay、incoming-first lookup、same incoming不同 bundle/authority model错误折叠、mutable room base/status入 key与 null close initiator。
  - definition/candidate变异必须覆盖完整 DAG断裂、bundle slot omission、SQL/JSON NULL/空串/全零 hash、非法 typed null marker、`projection_contract` unapproved/missing contract仍 current、candidate被 resolver/room/current/evidence看见、Task17/59直接发布 representation、历史 retry改读当前 alias。
  - recovery变异必须覆盖 no-userdata crash未建 case、claim前预建任一 request/application/operation、claim非原子 request + shell + application、错误 prior confirmation/bundle/fence/contributor仍成功、download-only创建任一三实体、nullable-operation普通 retry放行；evidence变异覆盖漏same-app sequence fold/跨participant key冲突/quarantined拒绝/opaque version碰撞/leader successor-no-successor任一场景、跨 entry复用、单 application或operation伪全场景、无 bundle或manifest profile digest，以及 profile降级后跳过任一 `editable=true AND (capability=bidirectional OR room_model=shared)` close liveness场景。
  - 删除门变异必须使“Task 67 structural pre-reconcile错误要求 fresh/stale=0或宣称 eligibility”打红；同时覆盖 Stage A错误要求待删 unreachable预先为0、post-delete仅 smoke恢复 evidence。
  - **`多 resolver writer=0`（gate issue key `multi_resolver`）—— 自 Task 30 移交至本门**（移交链 Task 20 → Task 30 → Task 71；两跳的成环理由分别写在 Task 20 与 Task 30 正文里，不必再推导一遍）：`wp_onlyoffice_router` 的 4 条 resolver 行（`get_sheet_onlyoffice_config`、`get_sheet_wopi_contents`、`get_whole_excel_grid`、`post_sheet_onlyoffice_callback`）必须已改为只经 published representation + approved 非空 bundle 的 substrate 取数、从 Task 12 resolver 矩阵的 `status=deferred` 名单移出并落到已迁移状态，且重新生成 writer matrix 后 `check_workpaper_writer_revision_gate.py` 的 `multi_resolver` issue 计数为 0。任一行仍 `deferred` 或计数非零则本门不过，`legacy_delete` gate 随之不放行 Task 72 的全局 legacy 删除。**本 criterion 不挂 `bulk_adapters` gate `["20","30","44"]`**：bulk adapter 迁移在 Wave 5、本门在 Wave 7，挂上即 Wave 5 依赖 Wave 7 —— bulk adapter 不能等在排在它之后的全局 legacy 删除上；`bulk_adapters` 的放行由 Task 20/30/44 各自的其余准则把守。Task 12 矩阵按**两个独立字段**登记：`blocking_task` 仍指向真实阻塞（Task 36 的逐 entry 供给），`adjudication_owner_task` 指向本门（71）—— 合并成一个字段会让「登记的阻塞必须真的把守发布门」那条判据失去意义。
  - 跑 6000 sessions/1200 participants/120 burst/20 applications/s×10min并锁死安全/p95预算；注入 OO/Redis/PG/磁盘/Windows lock/进程中断，验证 orphan/outbox/retry/pointers/双基线。执行 RetentionPolicy、RedactionPolicy与 alert synthetic测试。
  - 测试数据、incoming、trace/evidence artifact完整复原/清理；所有结果持久化并按 RED/GREEN/ANCHOR-MISS/WRONG-TEST判定，不以退出码代替证据，且不宣称未运行的真实 OO probe已通过。
  - 独立验证 Property 4、Property 5、Property 17、Property 18、Property 19、Property 28、Property 36、Property 42、Property 43、Property 44、Property 45、Property 57、Property 59、Property 60、Property 61、Property 62、Property 63、Property 64、Property 67、Property 68、Property 69、Property 70、Property 71、Property 72。
  - _Requirements: 2.1, 2.2, 2.4, 4.11, 5.5, 5.6, 5.8, 5.10, 5.11, 6.10, 6.18, 8.5, 9.6, 9.8, 10.3, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 12.10, 12.12, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 14.7, 14.9, 14.10, 14.11, 14.12, 14.14, 14.16_

- [-] 72. 执行真正 pre-delete eligibility、删除全局 legacy、post-delete 全场景重验与归档
  - **Stage A — 真正 pre-delete eligibility**：先消费 Task 67 structural report、Tasks 68/69独立回归、Task 70全 entry required-scenario刷新结果与 Task 71变异/恢复证据；此处才要求所有保留入口的未裁决=0、假双向=0、bidirectional未验收=0、evidence stale=0，并要求每个待删 unreachable/legacy唯一命中 Task 66 path/digest/owner/rollback plan。same-app fold、跨participant幂等冲突、quarantined拒绝、opaque version UUID、leader successor/no-successor任一required scenario未真实执行即保持UNVERIFIABLE并使Stage A为红；不得用文档/离线测试代替真实OO。不得要求待删 unreachable在删除前已为0。
  - **Stage B — 精确删除**：按 Task 66 plan删除 legacy dual-mode/composable/factory/旧 endpoint/localStorage/paragraph fallback/不可达桩/假成功文案，不留 DEPRECATED墓碑；计划外路径变化立即中止并回滚本阶段。
  - **Stage C — source commit 变化后完整重跑**：重新生成 manifest/registry/DOM/deletion report与 source-backed `editable/room_model/scenario_profile`；旧 evidence自动 stale。为所有受影响 entry创建新 test run，完整重跑 Task 70从 manifest profile + capability + bundle + authority model推导的全部 scenarios；每个命中 `editable=true AND (capability=bidirectional OR room_model=shared)` 的 entry仍必须重跑same-app sequence fold、跨participant幂等冲突、quarantined拒绝、opaque version UUID rollback、recovery claim/download-only、single close、双关闭顺序、A terminal前后B close、leader promotion前revoke/expire successor/no-successor及 reconciler重入，并持久化独立 application IDs后由服务端重算 bundle/profile-bound evidence；smoke只能附加，不能恢复 verified。
  - **Stage D — 最终五个零与归档**：仅在 post-delete 未裁决、假双向、bidirectional未验收、unreachable、evidence stale五类计数全为0后运行最终 CI/容量/retention/redaction/alerts/tracked-files门；禁止静默 skip。机器核对全部 AC/Properties/DAG/gate/禁止文件边界后才更新 INDEX并按功能归档。
  - 独立验证 Property 1、Property 2、Property 3、Property 46、Property 47、Property 48、Property 51、Property 57、Property 69、Property 70、Property 71、Property 72。
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.7, 11.1, 11.2, 11.5, 11.8, 11.10, 12.7, 12.8, 12.9, 12.10, 12.12, 12.13, 12.14, 14.7, 14.10, 14.13, 14.14, 14.15, 14.16_

- [-] 74. 清零 writer/version domain 归属本任务的七条准则（未裁决两条已归零，余五条留红；计数一律由门现算，见正文）
  - 接手 Task 20 冻结的红基线里**七条**准则的归零：`unadjudicated_writer`（gate issue key `unadjudicated_writer`，实测 236 行）、`bypasses_unified_commit`（261）、`unadjudicated_resolver`（34）、`writes_legacy_version_field`（5）、`owns_direct_commit`（105）、`non_canonical_resolver_only`（63）、`writer_without_characterization_test`（208）—— 自 Task 20 移交至本门，成环理由与移交形态见 Task 20 正文，不必再推导一遍。
  - 做法只有两条：**逐 domain 裁决**（每行进 `workpaper_writer_domain_overlay.json` 的 reviewed overlay，`version_domain_note` 写清它属于哪条 lane、为什么，禁止空注解），与**逐 writer 迁到 `ContentMutationService.commit(...)`**（删掉各自的 `_version`/`file_version`/`content_revision` 推进与第二个事务边界，每行补落在调用点上的 characterization + migrated behavior test）。
  - **完成判据 = `check_workpaper_writer_revision_gate.py` 的 14 条准则全为零**（默认命令退出码 0），不是「上面七条为零」：`multi_resolver` 的裁决归属仍在 Task 71（本任务依赖 71，故它先归零），`keeps_legacy_write_path_beside_unified_commit` / `after_save_still_increments_revision` / `representation_upgrade_increments_business_revision` / `artifact_snapshot_writer_not_verifiable` / `retired_writer_not_verifiable` / `missing_required_domain` 由 Task 20 守住，迁移过程中把它们从 0 顶回非零同样算本任务未完成。
  - **禁止四件事**：加豁免列或 overlay 级 `allow_bypass`；缩小分母（收窄 `_APP_ROOT`、给 `_is_production_source` 加业务目录排除、从 `_CONTENT_STORES` 删表）；把 `raise WriterGateError` 改成报 0；删掉任何一条 criterion 的计算。四件事各自已有守卫（`test_task20_writer_gate.py` §5–§7）与变异锚点，绕不过去。
  - 归零后同步更新 Task 20 正文冻结的那 14 个数字（它们由守卫与门现算逐条比对，改了源码不改文档必打红），并重跑 `mutate_task20_writer_gate_guards.py --run all` 确认锚点仍全部命中。
  - **🔴 2026-09-03 复选框由 `[x]` 退回 `[-]`（假绿更正，非回退）**：本任务自己写明「完成判据 = `check_workpaper_writer_revision_gate.py` 的 14 条准则全为零（默认命令退出码 0）」，而默认命令实测 **退出码 1 / 646 条 blocking facts**，14 条里 **5 条非零**：`bypasses_unified_commit` **261**、`writer_without_characterization_test` **208**、`owns_direct_commit` **105**、`non_canonical_resolver_only` **63**、`writes_legacy_version_field` **5**。真归零的只有 `unadjudicated_writer`（236→0）与 `unadjudicated_resolver`（34→0），以及 Task 20 守着的 6 条零基线（`keeps_legacy_write_path_beside_unified_commit` / `after_save_still_increments_revision` / `representation_upgrade_increments_business_revision` / `artifact_snapshot_writer_not_verifiable` / `retired_writer_not_verifiable` / `missing_required_domain`）与 `multi_resolver`=4（归属 Task 71）。    - 判据来源：`backend/scripts/check/check_workpaper_writer_revision_gate.py` 默认命令现算（`rows=319 writers=269 resolvers=71 retired=3`），与 Task 71 门禁报告 `multi_resolver_adjudication.writer_gate_criteria` 的 14 条逐字一致（那份是 live 重算、不写盘），两条独立路径互证，不是单侧读数。
    - **两条禁令仍然成立**：不得为了让复选框好看而缩小分母或加豁免（Task 20 §5–§7 守卫 + 变异锚点把着）；也不得把「已裁决 2 条」当成「七条已清零」—— 剩下 5 条要的是**逐 writer 迁到 `ContentMutationService.commit(...)`** 与逐行补 characterization test，不是登记动作。
    - **🔴 2026-09-05 数字刷新（本行以上的 261 / 63 / 646 / 642 为 09-03 读数，已过期）**：默认命令现算 **退出码 1 / 658 条 blocking facts**，五条非零为 `bypasses_unified_commit` **264**、`writer_without_characterization_test` **208**、`owns_direct_commit` **105**、`non_canonical_resolver_only` **72**、`writes_legacy_version_field` **5** ⇒ 待迁 **654** 行。归因：`excel-template-override-layer-and-onlyoffice-template-editor` 的覆盖层接线给 `wp_template_finder.py` **新增**了 `_find_template_file_override_first` / `_find_all_template_files_override_first` / `_find_template_file_any_override_first` 三个函数（HEAD 12 个顶层函数 → 现 15 个，**无删除**），使该模块被判为 non-canonical resolver 的行由 2 增至 5，连带 `non_canonical_resolver_only` +9、`bypasses_unified_commit` +3。Task 20 正文的 14 个数字已同步为 264/72/658，`test_task20_writer_gate.py` / `test_task74_domain_adjudication.py` / `test_workpaper_writer_inventory.py` 三个守卫实测 **81 passed / 0 failed** ⇒ 文档与门现算一致。
    - **同期一次瞬时故障已自愈，留档备查**：09-04 该覆盖层接线在途时，overlay 里 `wp_template_finder::find_all_template_files` / `::find_template_file_any` 两条裁决曾一度成为孤儿（生成器抛 `overlay adjudicates writers that no longer exist in source`），连带上述三个守卫共 **9 条判据**变红（4 ERROR + 5 FAILED，其中 `test_generator_refuses_an_unverifiable_retirement` 的预期错误被孤儿错误抢先掩盖）。当时判断为「在途中间态、不在移动目标上改 overlay」，未动 overlay；09-05 复查确认两函数仍在、孤儿消失、九条全绿 —— **该判断成立，overlay 无需改动**。教训：生产源重构期间 overlay 的「孤儿」可能只是瞬时态，先复查再裁决。
    - 前置依赖未变：`multi_resolver` 归零在 Task 71（其四条 resolver 行 `blocking_task=21,25,26,36`、`intended_status=deferred`，真实阻塞是 Task 36 的逐 entry published representation 供给 —— 库里 2806 张底稿现仅 1 张有 representation，硬改这四个端点会打断全部底稿的 OnlyOffice 视图）。
  - 验证 Property 4、Property 61。
  - _Requirements: 2.1, 2.2, 2.11, 2.12, 9.11, 12.6, 12.7, 13.4_

## Notes

### 文件占用面与并行安全（2026-09-04 补）

🔴 本 spec 写在**行为层**，任务正文几乎不提具体文件路径（全 77 条任务里只出现 1 个
`backend/app/**` 路径）。好处是不被实现细节绑死，代价是**无法机械判断它与其它 active spec
能否并行**。下表按剩余 7 条阻塞任务现读正文里点名的模块/符号，登记它们的占用面与碰撞点。

| 本 spec 任务 | 主要占用面（现读正文点名） | 与下游 spec 的碰撞 |
|---|---|---|
| Task 75 | `published_identity_observer.py`、`adapters/word.py`、`adapters/registry.build_production_registry()`、`working_paper_content_representation` / `..._representation_upgrade_candidate` 两表 | 🔴 **与 `published-representation-production-path-and-lane-adjudication` 是同一份工作**（该 spec 的首版发布服务层 = 本任务的公共观测器 + Task 76 的 provisioner）。**不得两边同时做** |
| Task 76 | `projection_provisioning.py`、`repository.attach_candidate_definitions`、`working_paper_sync_definition_artifact` / `..._bundle` 两表、`finalize_candidate` | 🔴 同上，与 P spec 重合 |
| Task 61 | `check_task61_oo94_word_pilot_gate.py`、`adapters/word.py`、`GtF2StocktakeBundle.vue`、`build_excel_adapter` | ⚠ 与 P spec 共 `check_task61_oo94_word_pilot_gate.py` |
| Task 63 | `adapters/word.py`、`registry.PENDING_ENGINE_ADAPTERS`、`wp_docx_template_parser`、`WorkpaperWordEditor.vue`、`wpPopupDocxConfigsS.ts` | 无（Word 域独占） |
| Task 71 | `wp_onlyoffice_router.py` 的 `get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` / `get_whole_excel_grid`、`check_workpaper_writer_revision_gate.py`、`bulk_adapters` | 🔴 **与 `excel-template-override-layer-and-onlyoffice-template-editor` 共 `wp_onlyoffice_router.py`** |
| Task 72 | 前端 legacy 删除面（`createDualMode.ts` / `useWorkpaperSyncBridge.ts` / `usePilotBridgeAdapter.ts` 等，清单在 Task 66 plan 里）+ `wp_onlyoffice_router.py` 的 `paragraph_index` 消费点 | 🔴 同上，与 T spec 共 `wp_onlyoffice_router.py` |
| Task 74 | `check_workpaper_writer_revision_gate.py`、`workpaper_writer_domain_overlay.json` | ⚠ 与任何改 `backend/app/**` 的 spec 间接相关：writer inventory 会因生产源变更而 stale，需重跑生成器 |

### 并行规则

1. **P spec 与本 spec 的 Task 75/76 不得同时进行** —— 它们是同一份工作的两种组织方式。
   建议：以 P spec 为唯一执行面，完成后把本 spec 的 Task 75/76 按其产出勾掉。
2. **T spec 与本 spec 的 Task 71/72 不得同时改 `wp_onlyoffice_router.py`** ——
   T spec 已实际改过该文件（`_hide_non_target_sheets` / `_ensure_all_sheets_visible` 换 zip 级实现，
   净 +6 行），且该改动已导致 Task 66 plan 的 5 个行号与 task67 报告的 2 个 digest 需要同步更正。
   再有并行改动会继续引发这类连带更正。
3. **改动 `backend/app/**/*.py` 后必须重跑 `generate_workpaper_writer_inventory.py`** 等生成器，
   否则 `test_task20` / `test_task30` / `test_task44` 一批 freshness 判据会连带打红。
   归因方法：`git status --porcelain -- <path>` 空输出 = 未修改，用它区分自己的债与并发会话的债。
4. **S spec 与 W spec 之间的串行门**由 W spec 的 Task 101 承担（现读 S spec 的 tasks.md
   断言其 Wave 4 已 `[x]`），与本 spec 无交集。

### 两条硬阻塞需要人裁决，不是代码工作

* **BP-18**：`registry.PENDING_ENGINE_ADAPTERS` 仍禁 word adapter ⇒ Task 63 的第一条 bullet
  （9 个 B 子码）结构上不可执行。
* **BP-19**：`B2-3` 载体二义（两封沟通函，sha256 与 size 均不同 ⇒ 两份不同文档），
  OPT-SPLIT / OPT-PRIMARY 两方案均未选定。
