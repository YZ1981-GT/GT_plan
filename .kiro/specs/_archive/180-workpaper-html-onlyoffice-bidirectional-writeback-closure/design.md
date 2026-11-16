# 底稿 HTML ↔ OnlyOffice 双向回写剩余闭环 — 设计

> **状态**：设计补全，生产实施尚未按本轮任务验收。
>
> **需求真源**：`backend/data/workpaper_sync_migration_paradigm.json` 的
> `adjudication_criteria.acceptance_criteria`。当前 `requirements.md` 只是逐字投影，
> 一共 **7 条 AC**；本设计不补造第八条，也不直接修改该投影文件。
>
> **历史资料边界**：归档目录
> `.kiro/specs/_archive/17-2026-10-03-verified-batch/workpaper-html-onlyoffice-bidirectional-writeback-closure/`
> 与 `docs/operations/workpaper-html-onlyoffice-bidirectional-writeback-master-control.md`
> 只提供机制和事故背景，不代表 2026-11-01 的当前完成状态。

## 1. 目标与范围

### 1.1 目标

本轮不重建已经存在的同步内核，而是补齐三个仍断开的闭环：

1. **事实闭环**：源码挂载、manifest、逐循环 slice、contract/provider 登记、数据库中的
   published representation 与 evidence 必须能生成同一份当前事实。
2. **准入闭环**：静态 capability、某个项目底稿此刻能否注册 adapter、以及是否已有当前
   真实 OO 验收证据必须分层表达，不能再用一个 `capability` 字段互相冒充。
3. **界面闭环**：前端只展示真实可用模式；未注册、契约漂移或供给缺失时不宣称双向，
   并显示用户下一步能做什么。

### 1.2 纳入范围

- 四态 capability 与受约束的未裁决态。
- source-backed manifest 和 D～N、A/B/C/S/共享入口 slice 的当前投影。
- request-time adapter readiness 与项目/底稿/entry 级查询接口。
- 模式按钮、同步提示和 `WorkpaperSyncEditorHost` 的统一门控。
- 每个独立 entry 的 definition producer 交付与逐场景 evidence 对账。
- `single_html`、`single_onlyoffice`、`unreachable` 的诚实裁决和 legacy 物理删除。
- 全局 closure checker、干净检出验证、真实 OnlyOffice 与 Playwright 验收。

### 1.3 非目标

- 不重写 `ContentMutationService`、room、callback、application、merge、artifact 等既有内核。
- 不因追求 bidirectional 数量而修改权威模板或伪造 HTML 字段映射。
- 不把 formula、guidance 或模板 round-trip 冒充运行态 HTML ↔ OO 双向回写。
- 不在本设计中硬编码 entry 总数、adapter 数或迁移号；所有数量交付时现算。
- 不在 Word tagged-SDT 真实门未通过前增加 paragraph-index/中文正则 fallback。
## 2. 当前实现复核

### 2.1 已有可复用能力

| 能力 | 当前真源 | 复用结论 |
|---|---|---|
| 四态与迁移范式 | `workpaper_sync_migration_paradigm.json` | 保留；它定义终态、pending 蕴含式、12 步 producer 和反模式 |
| manifest 发现 | `generate_workpaper_sync_manifest.py` | 保留 AST 发现和 reviewed overlay；修当前投影与 schema，不另造发现器 |
| adapter 准入 | `WorkpaperSyncAdapterRegistry.register_from_manifest()` | 保留 fail-closed 注册、逐 entry failure/reason 分型和记账等式 |
| 目标底稿绑定 | `target_bound_registration.py` | 保留 `(entry_id, representation_id)` 绑定，禁止回退到第一家企业的身份清册 |
| 路由准入 | `wp_sync_router._registration()` | 保留 422 typed failure；readiness 查询复用同一判据但不得创建 room 或 artifact |
| 前端动作门 | `supportedModesForCapability()`、`useWorkpaperSyncBridge` | 保留执行时拒绝；补渲染前门控和 runtime readiness |
| 统一编辑宿主 | `WorkpaperSyncEditorHost.vue` | 保留 descriptor、ready、dirty、operation、recovery 状态机 |
| 删除计划 | `generate_task66_legacy_deletion_plan.py` | 保留 source-backed 计划；补“满足后必须真删除”的收缩门 |

### 2.2 已确认缺口

1. 2026-11-01 运行 `generate_workpaper_sync_manifest.py --check` 时，reviewed source digest
   与当前源码挂载不一致。当前 manifest 是 stale artifact，里面的任何计数都只能用于诊断。
2. 各循环 slice 多为早期调查快照；contract/provider 和宿主已经变化，但没有统一生成器把
   当前 manifest、生产登记和 runtime evidence 重投影回 slice。
3. `workpaperEntrySyncNotice.ts` 把 `capability === 'bidirectional'` 的 entry 直接视为
   “adapter 已注册”。它没有读取本项目底稿的 representation、bundle、contract drift 或
   `ManifestRegistrationOutcome`，违反 AC 1.4 的运行时语义。
4. `supportedModesForCapability()` 能阻止非法动作，但大量宿主仍自行声明 `modeOptions`；
   动作门正确不等于按钮和文案正确。
5. `check_workpaper_sync_closure.py` 从 `build_production_registry().registrations()` 读取注册，
   但生产 registry 的真实注册发生在异步 `register_from_manifest(session=...)`；静态空快照会
   把动态注册架构误判成全部未注册。
6. registry 仍有 A5-1 临时 capability bypass。canary 豁免不能成为长期生产准入路径。
7. manifest 标记的不可达旧桩 `GtG6OtherBondEcl.vue` 仍在磁盘；
   `usePilotBridgeAdapter.ts` 已无生产调用，但仍被旧测试直接依赖。两者都需按删除门处理。
8. Word adapter 仍在 `PENDING_ENGINE_ADAPTERS`，其前置是真实 tagged-SDT/OO 门；本轮不得
   通过放宽门禁或新增空壳 adapter 推绿。
9. 当前工作没有读写共享 PG，也没有执行真实 OO；bundle、representation、operation、
   scenario evidence 的当前数据库状态均记为 **UNKNOWN**，不能从代码存在性推断完成。
## 3. 架构裁决

### ADR-WB-001：权威链只保留一条

`paradigm JSON → requirements.md` 是 AC 文本链；
`源码 AST + reviewed overlay → manifest → cycle slices + frontend generated manifest` 是事实链。
两条链职责不同，但各自只能有一个生成入口。手改投影产物一律由 `--check` 拒绝。

### ADR-WB-002：四态是终态，pending 不是第五态

终态仅允许：

```text
bidirectional | single_html | single_onlyoffice | unreachable
```

尚未完成事实调查的独立 entry 使用：

```text
capability = null
capability_verdict_stage = 非空字符串
capability_target = 四个终态之一
capability_target_blocked_by = 非空数组
```

不得增加 `dual`、`pending`、`missing`、`opaque` 等第五种 capability。`opaque` 只能是
`authority_model` 或内部诊断，不进入 capability 取值域。

### ADR-WB-003：静态裁决、运行时准入、验收状态三层分离

- **Adjudication**：该 entry 最终应提供什么能力，来自 manifest/slice。
- **Runtime readiness**：某项目、某底稿、某 entry 此刻是否有可用 adapter、approved
  definitions/bundle 和 current published representation，来自请求期真实注册链。
- **Acceptance**：required scenarios、真实 OO operation 与 evidence 是否完整且新鲜。

只有三层均满足时才能标 `bidirectional_verified`。静态 `capability=bidirectional` 不能替代
运行时注册，运行时注册成功也不能替代真实 OO 验收。

### ADR-WB-004：slice 是当前投影，不是手工历史报告

建立一个参数化 cycle-slice generator，按 selection rule 从当前 manifest 生成 D～N 与
A/B/C/S/共享入口的骨架，再合并 lane owner 提供的裁决证据。旧 Task 48～57 校验器保留为
约束来源，但不再由各循环复制第二套生成算法。

### ADR-WB-005：所有生产交付按独立 entry 隔离

contract、provider、authority definition、bundle、candidate、published representation、
required scenario set 和 evidence 都绑定独立 `entry_id`。parent duplicate 只持有
`effective_entry_id` 并复用父 entry 的 readiness，不独立注册、不独立计数、不复制 evidence。

### ADR-WB-006：readiness 派生，不新增持久化状态表

readiness 由静态 manifest、生产 contract ledger、当前 representation/bundle、provider 注册结果
和 evidence 现算。新增数据库状态会成为第四份可漂移真源，因此本轮默认不增加迁移。
### ADR-WB-007：界面由 capability 与 readiness 的交集驱动

- `single_html`：只显示结构化视图，不显示 OO 切换。
- `single_onlyoffice`：只显示在线编辑，不显示 HTML 切换。
- `unreachable`：不生成入口。
- `bidirectional` 且 runtime ready：显示统一双向切换。
- pending 或 runtime not ready：不得显示“可双向回写”；保留的独立视图必须明确标注
  “两侧未互通”，同步动作禁用并显示可操作原因。

各宿主不得用本地 `isOoAvailable=true`、健康探测成功或静态 capability 代替该交集。

### ADR-WB-008：删除是验收动作，不是注释动作

unreachable 和已被统一桥完全替代的 legacy 文件必须物理删除。删除前须有 replacement、
零生产调用、回滚目标和当前 evidence；删除后 source digest 变化会使旧 evidence stale，必须完整
重跑 required scenarios。`DEPRECATED`、allowlist 或 feature-disable 不能作为终态。

### ADR-WB-009：所有规模值在运行时现算

设计和任务只规定集合关系、计数公式和命令，不冻结 entry 数、宿主数、adapter 数或 legacy 数。
报告可以记录带时间戳的 snapshot，但关闭判据必须从明细重新计算，不能与历史 INDEX 数字比较。

### ADR-WB-010：现有同步内核保持单一所有者

本轮只为 readiness、事实投影和 UI 门控增加薄层。业务写仍只走 `ContentMutationService`，
representation-only 变更仍只走 `RepresentationService`，adapter 仍只做投影/OOXML 转换，
router 统一 commit。任何 lane 不得借“补 readiness”再造 callback、merge 或版本域。

## 4. 数据契约

### 4.1 Manifest entry

独立 entry 的最小裁决字段：

```json
{
  "entry_id": "xlsx/gt-example",
  "independent_entry": true,
  "capability": null,
  "capability_verdict_stage": "counterpart_confirmed",
  "capability_target": "bidirectional",
  "capability_target_blocked_by": ["definition_bundle", "real_oo_evidence"],
  "html_counterpart_verdict": "exists",
  "html_counterpart_source_refs": ["frontend/...#symbol", "backend/...#route"],
  "adapter_id": null,
  "migration_state": "pending_definition_supply"
}
```

终态 entry 不保留 pending 三字段。`single_onlyoffice` 必须满足
`html_counterpart_verdict == 'none'`；`single_html` 必须有“OO 无业务价值”的 source-backed
理由；`unreachable` 必须绑定删除计划。
parent duplicate 的本地 entry 不复制 adapter identity：

```json
{
  "independent_entry": false,
  "parent_entry_id": "xlsx/gt-parent",
  "effective_entry_id": "xlsx/gt-parent",
  "capability": "bidirectional",
  "adapter_id": null,
  "migration_state": "parent_duplicate"
}
```

“bidirectional 必须有 adapter”只对独立 entry 断言；父入口通过 `effective_entry_id` 读取父级
readiness。这样既不重复注册，也不把父入口错误计入未交付集合。

### 4.2 Cycle slice

每个 slice 必须是当前 manifest 的可复算子集，保留 paradigm 已定义的：

- `slice_scope.selection_rule / independent_entry_count / excluded_from_slice`；
- 权威模板 `size / sha256 / belongs_to_entry`；
- 独立 entry 的 counterpart、capability/pending、五个 definition/representation 身份位；
- `blocking_preconditions` 的状态、解除条件和 source refs；
- `evidence.verification_state / required_scenario_set_digest / unverifiable_reasons`；
- 从明细现算的 capability 与四类 closure counters。

slice 生成不得修改权威模板，不得从归档 spec checkbox 推导生产完成状态。

### 4.3 Runtime readiness DTO

新增只读 DTO，字段按“裁决 / 运行时 / 验收”分组：

```json
{
  "entry_id": "xlsx/gt-example",
  "effective_entry_id": "xlsx/gt-example",
  "capability": "bidirectional",
  "adjudication_state": "terminal",
  "allowed_modes": ["html", "oo"],
  "runtime": {
    "ready": false,
    "adapter_id": null,
    "authority_model": null,
    "definition_bundle_id": null,
    "definition_bundle_sha256": null,
    "typed_slots_complete": false,
    "representation_id": null,
    "representation_generation": null
  },
  "acceptance": {
    "state": "UNVERIFIABLE",
    "stale": false,
    "required_scenario_set_digest": null
  },
  "reason": {
    "code": "REPRESENTATION_MISSING",
    "message": "当前底稿尚未发布可用于双向回写的在线编辑版本。",
    "next_action": "先完成该底稿的首版 representation 发布并重新验收。"
  }
}
```
`reason.code` 使用封闭词表，至少覆盖：

- `ENTRY_UNADJUDICATED`
- `ADAPTER_NOT_REGISTERED`
- `CONTRACT_NOT_REVIEWED`
- `DEFINITION_BUNDLE_MISSING`
- `DEFINITION_SLOT_INVALID`
- `REPRESENTATION_MISSING`
- `CONTRACT_DRIFT`
- `EVIDENCE_MISSING`
- `EVIDENCE_STALE`
- `UNREACHABLE_PENDING_DELETE`

后端返回 typed code 和中文可操作文案；前端不得从英文异常文本猜状态。

## 5. 生成与一致性流程

```text
Vue/TS 生产挂载 + htmlRendererRegistry + backend dispatcher
                         │
                         ▼
        generate_workpaper_sync_manifest.py
                         │
          reviewed overlay + source digest gate
                         │
                         ▼
 workpaper_sync_entry_manifest.json ──→ workpaperSyncManifest.generated.ts
                         │
                         ▼
         parameterized cycle-slice projection
                         │
       ┌─────────────────┴──────────────────┐
       ▼                                    ▼
D～N slices                         A/B/C/S/shared slice
       │                                    │
       └──────── contract/provider/runtime evidence overlay ────────┐
                                                                    ▼
                                                     closure current-state report
```

规则：

1. manifest 生成失败时停止下游生成，不用旧产物继续算“当前状态”。
2. source digest 变化先输出语义 mount diff；审核后才能更新 overlay digest。
3. manifest JSON、前端 TS 和所有 slice 在同一次生成中采用同一内存快照。
4. generator 的 `--check` 只比较目标态，不写文件；`--write` 内容未变时保持幂等。
5. 生成时间不得让内容相同的产物产生 diff；若保留时间戳，内容相同时沿用旧值。
6. 生成器对每个 required 字段都有删除式负例；只测正例视为不完整。
7. closure report 保存取数时间、source/manifest/overlay digest 和命令，但关闭判据只读明细。

## 6. 后端 readiness 设计

### 6.1 接口

```http
GET /api/projects/{project_id}/workpapers/{wp_id}/sync/entries/{entry_id}/readiness
```
接口沿用平台 `{code,message,data}` 信封，挂项目级 readonly 权限。处理顺序固定为：

1. 认证并校验 project/wp/entry scope；
2. 将 parent duplicate 解析到 `effective_entry_id`；
3. 读取静态 adjudication，不合法时返回 `ready=false`；
4. 复用 `build_production_registry()` 的 manifest registration plan；
5. 优先用 `entry_scoped_registration.prepare_entry_only()` 与
   `bind_registration_to_target()` 检查目标底稿；
6. 调用与 `_registration()` 相同的 bundle、authority model、contract 和 target identity 判据；
7. 只读 evidence 当前投影；
8. 返回 DTO，不创建 pending mutation、room、operation、artifact，也不推进 revision。

对象不存在、跨 scope 或项目不可见统一在 scope guard 返回 404；已知项目可见但无 readonly 权限返回
403；entry 合法但未就绪返回 200 + `runtime.ready=false`，便于界面稳定显示原因。DB/代码异常不能降级为
“未注册”，应返回可观测 5xx 并保留 correlation id。

### 6.2 缓存与性能

- 只按 `(project_id, wp_id, effective_entry_id, current_representation_id,
  definition_bundle_id, manifest_digest)` 缓存短期只读结果。
- capability/overlay、entry pointer、bundle 或 evidence freshness 改变时自动失效。
- 冷缓存只准备本 entry，不持全局注册锁重建全部 entry。
- readiness 请求不得解析整库模板；重型 structure hash 复用现有 warmup/cache。
- 对同一页面并发查询使用 single-flight，不依赖前端“取消先发请求”的 GET 去重行为。

### 6.3 临时 bypass 收口

`WorkpaperSyncAdapterRegistry.register()` 和 `assert_bidirectional_ready()` 中 A5-1 临时 bypass
必须删除。A5-1 若无法通过完整 manifest capability 与 runtime supply 判据，应返回明确 readiness 原因，
不能保留只对 canary 生效的生产后门。

## 7. 前端展示设计

### 7.1 单一状态入口

新增 `useEntrySyncReadiness(scope)`，只通过 `workpaperSyncApi.ts` 调 readiness 接口。它返回：

- `loading / ready / blocked / error` 请求状态；
- `allowedModes`、`canClaimBidirectional`、`canSwitchToHtml`、`canSwitchToOo`；
- `notice` 与 `nextAction`；
- 当前 response identity，换项目、底稿、entry 后丢弃旧响应。

`workpaperEntrySyncNotice.ts` 改为纯展示投影，输入 readiness DTO；删除
`SYNC_ADAPTER_REGISTERED_ENTRY_IDS = capability==='bidirectional'` 这一错误推导。
### 7.2 展示矩阵

| adjudication/runtime | HTML | OO | 切换控件 | 常显说明 |
|---|---:|---:|---|---|
| `single_html` | 显示 | 隐藏 | 不显示 | 可选：说明该底稿仅结构化编制 |
| `single_onlyoffice` | 隐藏 | 显示 | 不显示 | 可选：说明该底稿仅在线编辑 |
| `unreachable` | 不挂载 | 不挂载 | 不显示 | 不应到达用户界面 |
| pending | 按现有独立能力 | 按现有独立能力 | 不显示“同步切换” | 必须显示“两侧未互通”及 blocker |
| bidirectional + blocked | 保持当前侧 | 目标侧禁用 | 禁止发起 bridge switch | 必须显示 typed reason/next action |
| bidirectional + ready | 显示 | 显示 | 显示统一切换 | bridge 自身状态文案 |
| readiness 请求失败 | 保持当前侧 | 目标侧禁用 | fail-closed | “同步状态读取失败，请重试” |

如果产品仍需让 pending entry 打开 legacy OO，它必须命名为“独立在线编辑（不同步）”，且不得经过
`useWorkpaperSyncBridge` 的成功态或显示“已同步”。这是一种兼容观察入口，不是双向能力。

### 7.3 宿主接线

所有模式工具栏必须复用同一个 presentation helper；宿主只传 scope、当前模式和业务级 flush/reload。
禁止各宿主再定义 capability 分支、静态 `isOoAvailable=true`、第二套成功文案或第二份原因词表。

`GtEntrySyncCapabilityNotice.vue` 继续作为统一组件，但需满足：

- 原因摘要默认可见，不只藏在 tooltip；
- 与切换按钮位于同一门控层，不能“提示未互通但按钮仍声称同步”；
- loading/error/blocked 有不同 `data-*` 状态，供 DOM 守卫和 Playwright 读取；
- 所有用户可见文本为中文；键盘可达，窄屏不遮挡主操作。

## 8. 逐 entry 迁移协议

每个独立 entry 只允许沿 paradigm 的 12 步前进：

| 阶段 | 输入 | 输出 | 失败状态 |
|---|---|---|---|
| 事实冻结 | source manifest、权威模板 | slice、template digest、counterpart 二值结论 | pending，列明 blocker |
| 能力裁决 | counterpart 与 OO 业务价值 | 四态或受约束 pending | 不得用“尚未开发”裁 single |
| definition producer | authority model、reviewed contract | approved typed bundle | bundle/slot 缺失即阻断 |
| representation | non-current candidate 或首版发布 | current immutable generation | candidate 不可见 |
| adapter/host | provider、registry、统一桥 | request-time ready | 失败给 typed reason |
| evidence | required scenario set | test run、OO operation、验收态 | UNVERIFIABLE 必须给原因 |
| UI/closure | readiness 与 evidence | 诚实模式、slice counters | 任一 stale 不得关闭 |
### 8.1 Lane 责任边界

umbrella 只拥有 schema、生成器、readiness、共享 UI 门、closure 和删除总门。逐 entry 的字段语义、
contract、provider、模板 identity、真实数据和 OO evidence 由对应 lane spec 拥有。

按交付批次重算而不是按历史 checkbox 继承：

1. D/E；
2. F；
3. G/H/I；
4. J/K/L；
5. M/N；
6. A/B/C；
7. S 与跨循环共享入口；
8. Word/custom/opaque 特殊 lane。

每批先从 current projection 识别真正缺口。已有 contract/provider 只能证明代码侧供给；只有数据库
current representation、请求期注册和当前 evidence 都成立，才能复用为完成证据。发现缺口时创建或重开
最小 residual lane spec，不回填修改已归档历史 tasks。

### 8.2 Single 裁决

- `single_onlyoffice`：必须证明 HTML 对端为 `none`，包含宿主、持久化路由和业务模型搜索证据。
- `single_html`：必须证明 OO 侧没有业务内容或只有空白模板，并同步删除 OO 入口。
- `unreachable`：必须证明生产入边为零，并进入 source-backed deletion plan。
- single entry 的 adapter/authority/bundle/candidate/representation 身份位必须全空；不得为了 schema 完整
  造空 contract 或 typed identity。

## 9. Legacy 删除与回滚

删除前置条件：

1. replacement entry 已通过本 entry 的 runtime readiness 和 required scenarios；
2. AST/模板发现确认待删模块生产调用为零；
3. 删除计划记录文件 digest、owner、最后调用点、替代路径和 rollback commit；
4. 共享基类仍有消费者时保留，不能按名字批量删除；
5. 删除不会使未迁 entry 丧失唯一可用模式。

首批已知候选是 `GtG6OtherBondEcl.vue` 和 `usePilotBridgeAdapter.ts`。它们只能在上述判据通过后
物理删除；相应旧测试应改为断言文件不存在、调用为零、真实替代路径存在，而不是继续 import 墓碑。

删除后必须：重新生成 manifest/slices/TS、使旧 evidence 因 source digest 变化而 stale、完整重跑受影响
entry 的 required scenarios，再把 deletion-plan 项从 pending 收缩为 completed。回滚只恢复源码入口和
旧 current pointer；immutable content/representation/evidence 历史不删除、不改写。

## 10. 验证与 evidence

### 10.1 五层验证

| 层 | 证明内容 | 不可替代它的证据 |
|---|---|---|
| 静态/结构 | manifest/slice/schema/宿主/删除计划闭合 | 注释、INDEX 数字 |
| 单元/属性 | 四态蕴含式、reason 映射、presentation、registry 记账 | 只看测试退出码 |
| PostgreSQL | current pointer、bundle FK、注册、operation/application、事务边界 | SQLite 或 mock session |
| OnlyOffice | identity、forcesave/callback、往返、多人/恢复 | 离线 openpyxl roundtrip |
| Playwright | 按钮显隐、中文原因、真实网络路径、回读 | 组件源码字符串扫描 |
### 10.2 每个 bidirectional entry 的最低 evidence

- `source_commit / manifest_digest / overlay_digest`；
- `entry_id / effective_entry_id / scenario_profile_id`；
- authority model definition 与 template/instrumentation/contract typed slots；
- bundle id/digest、representation id/generation、artifact hash；
- request、delivery、application、operation 和 timeline identity；
- HTML→OO、OO→HTML、不同字段合并、同字段冲突、refresh/reopen、rollback；
- 适用时动态行/列、跨 sheet、多人 close、crash recovery；
- Playwright network/console/DOM 摘要；
- 测试数据恢复结果。

任何 `UNVERIFIABLE` 必须有非空原因和解除条件。download-only 场景必须证明没有伪造 application 或
operation。一个 entry 的 operation 不得替另一个 entry 或另一个 required scenario 签收。

### 10.3 变异要求

关键门至少覆盖以下反事实，并核对打红的是预期测试：

- 把 capability 改回 `dual` 或增加第五态；
- pending 缺任一三字段、target 非四态或 blocker 为空；
- `single_onlyoffice + counterpart=exists`；
- 用 capability 冒充 runtime registered；
- 删除 contract/bundle/current representation 后 UI 仍显示双向；
- parent duplicate 被独立注册或重复计数；
- source digest stale 时仍生成下游 current report；
- closure checker 跳过 `register_from_manifest()`；
- A5-1 bypass 被加回；
- unreachable 文件仍存在却把计划标完成；
- 删除后沿用旧 source evidence；
- Word 无稳定身份时启用 paragraph fallback。

结果分 `RED / GREEN / ANCHOR-MISS / WRONG-TEST`；只认目标反事实导致的 RED。变异文件必须在
`tmp_<任务名>/` 的隔离 worktree 中执行并逐字节还原。

## 11. 安全、事务与容量

- readiness 端点使用项目级 readonly 权限，并验证 `wp_id` 属于路径项目、entry 属于目标底稿。
- authorization 必须早于 adapter/provider、artifact、cache 和 idempotency 结果读取。
- readiness 是只读诊断：不得创建 room、operation、candidate、artifact 或 evidence，不得 commit。
- provider/module 路径继续受 `_ALLOWED_PROVIDER_MODULES` 白名单约束，不开放任意动态 import。
- contract drift、悬空 pointer、非法 typed slot 属故障，不得吞成“本项目无数据”。
- reason/evidence 不记录 JWT、Authorization、callback URL 查询值、业务正文或个人信息。
- runtime 查询只构建目标 entry；不能因工具栏挂载让每个页面冷建全部 registry。
- 本轮共享闭环预计无需 DB 迁移。若实施发现 schema 缺口，须先现扫磁盘和共享库最高版本，使用
  新的 V/R 配对迁移，并在写共享库前取得用户授权。
## 12. 发布与回滚顺序

```text
P0 重新建立当前 manifest/slice 基线
 → P1 补 runtime readiness 后端契约
 → P2 前端统一门控，先 fail-closed
 → P3 按 lane 补齐逐 entry supply/evidence
 → P4 裁决 single 与物理删除 unreachable/legacy
 → P5 全量 OO + Playwright + post-delete evidence
 → P6 closure 与归档
```

- P2 可先于全部 lane 完成：未就绪 entry 会得到诚实阻断，而不是假双向。
- lane 以一个 canary 开始；仅在同类 entry 的 template/contract/identity 结构一致时扩大。
- 删除动作严格晚于 replacement evidence；不得为让 closure 数字归零先删唯一可用入口。
- 回滚 UI/readiness 不回滚业务数据；回滚 entry migration 只切回上一 published pointer，保留 immutable
  history。发现数据不一致时停止该 lane，不继续批量推进。

## 13. 可选方案 ROI 裁决

| 方案 | 预计改动 | 收益 | 风险 | 裁决 |
|---|---:|---|---|---|
| 请求期 readiness 薄层 | 8～12 个后端/前端/测试文件 | 直接关闭 AC 1.4/1.5 的静态冒充 | 中，需控制冷建成本 | **做** |
| 参数化 cycle-slice generator | 5～8 个代码/测试文件，加生成数据 | 消除各循环历史快照和第二算法 | 中，需先处理 source drift | **做** |
| 新建 readiness 数据表 | 8～15 个文件 + V/R 迁移 | 查询稍快 | 高，会形成第四真源并需失效编排 | **不做** |
| 重写整个 sync 内核 | 50+ 文件 | 理论统一 | 极高；现有内核已具备真实能力 | **不做** |
| 把所有 entry 强制改 bidirectional | 100+ 文件/模板 | 数字好看 | 极高，直接违反 12.8/12.9 | **不做** |
| 条件删除 `usePilotBridgeAdapter` | 3～6 个文件 | 清除可误用的零 API 空壳 | 低；需先改旧测试 | **做，受删除门约束** |
| Word paragraph/正则 fallback | 10+ 文件 | 短期可打开 Word | 数据串写风险高，违反稳定身份门 | **不做** |
| 每个 lane 自建 readiness API | 每 lane 3～5 文件 | 局部交付快 | 高，必然漂移 | **不做** |

本轮没有 `[ ]*` 可选实施项。上表被否决方案只保留为边界，不进入 tasks。

## 14. AC 追踪矩阵

| AC | 设计机制 | 主要任务 | 验收证据 |
|---|---|---|---|
| 1.3 | ADR-WB-002、manifest/pending schema | 1.1～1.3 | schema 正反例、前后端枚举对拍 |
| 1.4 | runtime readiness、typed reason、统一 notice | 2.1～3.6 | 端点级鉴权 + DOM/Playwright 反例 |
| 1.5 | capability/readiness 展示矩阵 | 3.2～3.6、5.1～5.2 | single 模式无切换按钮 |
| 1.7 | source-backed deletion 与 post-delete rerun | 5.3～5.5、6.5 | 文件/调用/rule 三项归零 |
| 12.1 | 12 步 producer、per-entry evidence | 1.4～1.7、4.1～4.8、6.1～6.5 | bundle/representation/operation/evidence 全链 |
| 12.8 | counterpart 二值结论、禁止假映射 | 1.3、4.2～4.8、5.1 | `single_onlyoffice ⇒ none` 及模板 digest |
| 12.9 | single_html/删除裁决、空入口清除 | 3.2、5.2～5.5 | OO 入口/descriptor/旧桩归零 |
## 15. 完成定义

本 spec 只有同时满足以下条件才能关闭：

1. paradigm JSON 与 requirements 投影逐字一致，仍只有权威定义的 7 条 AC。
2. manifest generator、前端投影和所有 cycle slice 的 `--check` 在同一当前源码快照上通过。
3. 每个独立 entry 要么有合法四态终裁，要么在实施过程中有完整 pending 三字段；最终全局关闭时
   `unadjudicated == 0`。
4. 每个 `bidirectional` 独立 entry 有 reviewed contract、approved authority/bundle、current
   representation、请求期 adapter、required scenarios、真实 OO operation 和新鲜 evidence。
5. `single_onlyoffice` 全部有 `counterpart=none`；`single_html` 全部无 OO 业务入口；single 身份位全空。
6. 前端不再用静态 capability 冒充 registered，所有宿主按同一 readiness 展示模式和原因。
7. 不可达旧桩、已替代 legacy 路径和零 API 过渡空壳按计划物理删除，无 `DEPRECATED` 墓碑。
8. closure checker 读取真实动态注册和 runtime evidence；摘要与明细逐项相等。
9. 后端、前端、PG、OnlyOffice、Playwright、变异与 clean-checkout 验证全部完成；测试数据已恢复。
10. INDEX 只登记可复算状态，归档后没有 active/archived 同名真源冲突。

### 当前已知阻塞

- source mount digest 已漂移，必须先审核语义 diff 后重生成 manifest。
- runtime DB/真实 OO evidence 尚未在本轮读取，所有相关状态保持 UNKNOWN。
- Word adapter 仍受 tagged-SDT/OnlyOffice gate 阻塞，不能用 fallback 绕过。
- 逐循环已归档文档与当前生产供给存在时间差，必须先生成 current projection 再拆 residual lane。
