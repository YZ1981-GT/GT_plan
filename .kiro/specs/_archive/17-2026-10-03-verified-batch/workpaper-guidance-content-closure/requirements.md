# Requirements Document

## Introduction

本 spec 是三个闭环的契约与内容真源起点。目标不是让“编制说明永不为空”，而是让每个可达 sheet 的说明具备稳定身份、权威来源、九段内容、可验证引用、明确完成状态和可复现证据。

2026-09-07 只读基线确认：生产链仍以 `extract_exact_static()`、运行时 `exact_status` 和单一 `source` 为核心；endpoint 每次请求扫描/构建 inventory；custom guidance 写接口仍返回 501；前端 sheet context、缓存、AI 承载和 HTML sanitize 均存在缺口。上述事实只作为红基线，不构成任何任务完成证据。

本 spec 直接冻结以下最终模型，不保留旧模型兼容性描述作为第二真源：

1. **C0 wire contract bundle 由本 spec 唯一拥有**；formula 与 custom 只能引用，不得复制同名接口。
2. **catalog inventory 与 runtime inventory 分离**；前者服务标准内容 C1，后者服务项目实例和用户上传后的 C2/持续健康。
3. **来源生命周期、解析结果、完成状态三轴分离**；locator kind 不承担 source lifecycle。
4. **标准 exact 只来自 active methodology publication**；模板/BCD 抽取只能生成 candidate。custom exact 只来自 durable finalized handoff 的 ACK。
5. **C2 是带 cutoff 的不可变历史里程碑**；后续新增或变化由 `platform_guidance_health` 与 reevaluation evidence 表达，不反写历史 PASS。

本 spec 不实现公式工具栏和自定义 Excel 摄取；它发布供后两个 spec 消费的契约与里程碑。

## Requirements

### Requirement 1: C0 共享 wire contract bundle 单一真源

**User Story:** 作为三个闭环的维护者，我希望共享身份、引用、证据和 handoff 只有一份规范，避免字段漂移与隐藏依赖环。

#### Acceptance Criteria

1. WHEN 发布 `G-C0` THEN 必须在同一公共 contract bundle 中版本化定义 `CanonicalWorkpaperLocation`、`GuidanceSection`、`SourceRef`、`TemplateAuthorityIdentity`、candidate/finalized `CustomGuidanceHandoff`、`ConsumerAck`、`GuidanceRailAdapter` 与 `EvidenceEnvelope`
2. WHEN formula 或 custom 消费共享契约 THEN 必须 import 公共 bundle；任何同名本地 interface、字段投影副本或手写 JSON schema 都使 conformance 失败
3. WHEN `EvidenceEnvelope` 表示 contract/catalog/runtime/operation 证据 THEN subject 必须是判别联合；organization 级证据不得被迫伪造 `projectId/wpId`
4. WHEN `CustomGuidanceHandoff.phase=candidate` THEN payload 不得要求 `finalizationId/confirmedBy/confirmedAt`；只有 finalized variant 可以携带这些字段
5. WHEN producer/consumer 遇到未知 major、缺失 identity、非法判别字段或不支持的 minor capability THEN 必须 fail-closed，并返回结构化兼容性原因
6. WHEN C0 发布 THEN 必须同时发布兼容矩阵、canonical fixture、schema validation 和反向变异证据；仅有 TypeScript 类型不计里程碑完成

### Requirement 2: catalog/runtime inventory 与稳定身份

**User Story:** 作为方法论管理员，我希望标准模板清册和项目运行态清册各自按稳定身份枚举，既不漏项也不混淆版本。

#### Acceptance Criteria

1. WHEN 生成 catalog inventory THEN entry key 必须由 `template_lineage_id + template_version_id + wp_code + sheet_uid` 构成，并合并权威模板索引、render-config 与 publication facts
2. WHEN 生成 runtime inventory THEN entry key 必须由 `organization_id + project_id + wp_id + entry_id + sheet_uid` 构成，并引用对应 catalog identity 或 finalized custom authority
3. WHEN sheet 名称、顺序或显示 label 改变但 stable identity 未变 THEN inventory identity 不得改变；名称、数组下标和 DOM 文本不得承担主键
4. WHEN template override、sheet identity、publication、custom authority 或 render reachability 变化 THEN 受影响 entry 必须 stale 并进入新 inventory run，旧 snapshot 保持不可变
5. WHEN inventory materialize THEN 必须保存 run id、scope、cutoff、input digests、entry facts 和 inventory digest；API 不得在每次 guidance 请求中全目录重扫
6. WHEN 使用缓存 THEN 只能使用有界、不可变、按 digest 寻址的 snapshot/cache；运行时 mutable object 或无版本 singleton 不得跨项目复用

### Requirement 3: gross/effective denominator 与阶段里程碑

**User Story:** 作为项目负责人，我希望完成分母、豁免和历史里程碑可核算，后续新增模板不会篡改过去的验收事实。

#### Acceptance Criteria

1. WHEN 核算任一 inventory snapshot THEN `gross_required` 必须无遗漏、无重复地分解为 `complete ⊎ pending ⊎ blocked ⊎ valid_exempted`
2. WHEN 计算有效分母 THEN `effective_required = gross_required - valid_exempted`，PASS 仅在 `complete = effective_required` 且 `pending=blocked=0` 时成立
3. WHEN 记录 exemption THEN 必须含 scope、entry ids、依据、owner、reviewer、source digest、批准时间与 `expires_at`；过期或 source digest 变化后自动回到 pending
4. WHEN 评估 C1 THEN scope 只包含当次 catalog snapshot 中 required 的 `standard/custom_blank` entries，并冻结 run id 与 digest
5. WHEN 评估 C2 THEN 必须生成不可变 `C2Milestone(run_id, inventory_digest, scope, cutoff_at, evidence)`，覆盖 cutoff 时全部 required runtime entries，且依赖 custom handoff conformance
6. WHEN cutoff 后新增、升级、回滚、撤回或 stale runtime entry THEN 不得改写历史 C2；必须更新 `platform_guidance_health` 并生成 `C2_REEVALUATION_REQUESTED` evidence

### Requirement 4: 来源、解析与完成三轴真值模型

**User Story:** 作为复核人，我希望能区分“内容来自哪里”“如何解析到它”“是否完成”，不再由一个 `exact_status` 混合表达。

#### Acceptance Criteria

1. WHEN API/inventory 返回 provenance THEN 必须分别提供 `primary_source_kind`、`overlays[]`、`extraction_source`、`resolution_status` 与 `completion_status`
2. WHEN 设置 `primary_source_kind` THEN 只允许 `methodology_publication/custom_confirmed/none`；`project_supplement` 只能出现在 overlays，不能单独成为 required canonical authority
3. WHEN 模板、BCD、docx 或 custom artifact 被抽取 THEN 只能登记为 `extraction_source` 和 candidate evidence；未经发布/ACK 不得转为 primary source
4. WHEN 设置 `resolution_status` THEN 只允许 `exact/parent_inherited/typed_fallback/generic_fallback/missing/invalid/stale/not_applicable`
5. WHEN 设置 `completion_status` THEN 只允许 `complete/review_pending/required_pending/blocked/exempted/out_of_scope`，并由 pure evaluator 从 required、authority、publication/ACK、九段、refs 和 resolution 推导
6. WHEN 任一非法组合出现（例如 candidate+exact、inherited+complete、withdrawn publication+complete）THEN entry 必须保留在分母并标 blocked，不能丢弃或 broad-warning 后放行

### Requirement 5: 九段 GuidanceSection 与 SourceRef locator registry

**User Story:** 作为审计助理，我希望每个 sheet 的说明覆盖真实编制流程，并能定位到权威依据。

#### Acceptance Criteria

1. WHEN guidance 成为 authoritative exact THEN 必须恰好覆盖稳定 key：`purpose/materials/data_sources/steps/formulas/judgments/evidence/common_errors/completion`
2. WHEN 返回任一 section THEN 必须至少包含一个通过 registry 验证的 `SourceRef`；缺段、重复 key、空引用或无效引用均不得 complete
3. WHEN 注册 locator THEN kind 至少覆盖 `xlsx/docx/bcd_markdown/methodology_publication/project_evidence/custom_artifact`
4. WHEN 验证 locator THEN handler 必须声明 authority、locator schema、digest 算法、边界、stale 判据与 cross-authority 规则；locator kind 不得使用 `custom_candidate/custom_confirmed` 这类生命周期名称
5. WHEN path/anchor/range 不唯一、越界、digest 不匹配、authority 不同或 kind 未知 THEN 返回结构化 invalid/stale reason，并阻断 publication/ACK
6. WHEN legacy 内容缺少九段或 refs THEN 必须进入迁移工作卡；不得用泛化自动文案补满形式后计 complete

### Requirement 6: immutable publication 与 project supplement

**User Story:** 作为方法论负责人，我希望标准说明先审核后发布，项目团队只能补充项目事实而不能改写平台方法论。

#### Acceptance Criteria

1. WHEN 创建标准 guidance THEN 生命周期必须为 draft → reviewed → published，published version immutable；模板抽取只创建 draft/candidate
2. WHEN 发布、撤回、恢复或 supersede THEN 必须记录 publication id/version、actor、reviewer、diff、source digests、reason 与时间，并通过 audit/outbox 可重放
3. WHEN 普通项目用户增加说明 THEN 必须创建独立 `project_supplement`，绑定 project/wp/entry/sheet/section/base publication version 与 project evidence refs
4. WHEN 解析展示 THEN base publication 与 supplements 必须分别返回 provenance；supplement 不得覆盖 canonical 文本或补齐缺失 canonical required section 后伪造 complete
5. WHEN publication、template authority、formula boundary、supplement 或 source ref 变化 THEN response/cache/evidence 必须 stale 并重新校验
6. WHEN 用户无发布、审核、撤回或 supplement 权限 THEN 服务端拒绝且 UI 给出角色、owner 与下一步；只隐藏按钮不算权限控制

### Requirement 7: authoritative exact 与父链解析

**User Story:** 作为审计师，我希望当前 sheet 只在有有效权威内容时显示 exact，否则明确继承或降级。

#### Acceptance Criteria

1. WHEN 请求带 sheet identity THEN 服务端必须先验证其属于当前 wp/render authority；跨项目、跨底稿或不存在的 sheet 返回 4xx 且不泄漏内容
2. WHEN child 有 active methodology publication 或 durable custom-confirmed authority THEN `resolve_authoritative_exact()` 返回 child exact
3. WHEN child authority 缺失、invalid 或 stale THEN 必须进入 parent authoritative chain；raw static/template extraction、typed fallback 不得抢先伪装 child exact
4. WHEN parent chain 解析 THEN 顺序必须为 parent authoritative exact → typed fallback → generic fallback，并记录 requested/resolved identity 与真实 reason
5. WHEN legacy static JSON 尚未迁移 publication THEN 可作为 review candidate 显示，但不得成为 exact/complete authority
6. WHEN 返回结果 THEN 必须含 requested/resolved identity、inheritance、三轴状态、primary/overlay/extraction provenance、missing sections 与 structured errors，前端不得比较文案猜状态

### Requirement 8: 模板权威、sheet identity 与可达性单一来源

**User Story:** 作为平台维护者，我希望 guidance 与 renderer 使用同一模板与 sheet 身份，避免短码或文件名猜测命中错误模板。

#### Acceptance Criteria

1. WHEN 定位标准模板 THEN 必须复用 `wp_template_finder`/override/index 权威链，删除未排序目录遍历与 substring resolver
2. WHEN render-config 发布 sheet THEN 必须携带 `sheet_uid/sheet_code` 或结构化 null reason，并关联 template authority identity
3. WHEN code 含小写后缀、复合码或 sheet 重名 THEN 后端、HTML、Univer 与 catalog inventory 必须消费同一 stable identity
4. WHEN 打开不可观察原生 tab 的完整 workbook THEN location 必须使用 whole-workbook locator，不得伪造当前 sheet
5. WHEN template/index/override 改变 THEN authority digest、catalog identity projection、source refs 与旧 evidence 必须共同 stale

### Requirement 9: API 版本、稳定缓存与失败可见性

**User Story:** 作为并发使用者，我希望切换项目和 sheet 后不会串内容，缓存也不会把新版本永久遮住。

#### Acceptance Criteria

1. WHEN API 返回 guidance THEN 必须携带 schema/contract version、response version、source/inventory digests、generated_at、ETag 与三轴状态
2. WHEN 服务端缓存 authoritative result THEN key 必须基于稳定 subject identity、authority/publication/supplement/source digests 与 schema version；不得包含瞬态 `contextRevision`
3. WHEN 前端缓存 THEN key 必须含 project/wp/entry/sheet-or-whole/schema，短 TTL 后 revalidate；`contextRevision` 只作竞态门，不作持久 cache identity
4. WHEN context、权限或 response version 变化 THEN abort 旧请求并清理旧 guidance/AI/tab；旧响应只有 identity、owner epoch 与 revision 全匹配才可落地
5. WHEN 一个 context 首次加载 THEN 必须只有一个 fetch owner；panel/store 双请求为失败
6. WHEN source/ref/timeout/permission 失败 THEN 返回结构化 error state；broad catch、warning 后成功态或空数组不得掩盖失败

### Requirement 10: HTML、Univer 与 OnlyOffice 诚实 context

**User Story:** 作为编制人，我希望默认页、切页、定位和整册编辑都同步正确说明，并诚实表达宿主不可观察边界。

#### Acceptance Criteria

1. WHEN render-config 首次完成、deep-link、wpId 或 initial sheet 变化 THEN host 必须立即发布稳定 sheet/location input
2. WHEN HTML 发生 tab、navigate、locate 或 section 切换 THEN 所有路径必须汇入同一 emitter，不得只在手工点击时更新
3. WHEN Univer 原生 tab、自定义导航或 locate-cell 改变 active sheet THEN 必须通过 engine id→sheet uid/code 映射发布；`onSwitchSheet` 不得 no-op
4. WHEN OnlyOffice 使用外层单-sheet entry THEN 使用外层 stable sheet identity；完整 workbook 无受支持事件时固定 whole-workbook
5. WHEN宿主无法观察 cell/sheet THEN 必须降到可证明的 page/sheet/workbook locator；禁止 DOM 穿透、轮询或伪事件
6. WHEN 快速连续切换至少三个 location THEN network、store、DOM 标题与 source badge 必须只呈现最后 owner epoch/context revision

### Requirement 11: Guidance UI、安全展示与 rail adapter

**User Story:** 作为底稿用户，我希望看到诚实、可操作且安全的说明状态，并由公共壳层统一承载右侧入口。

#### Acceptance Criteria

1. WHEN 展示 guidance THEN primary source、overlays、extraction candidate、resolution、completion、publication version、refs 与缺口必须分层呈现中文状态
2. WHEN状态为 inherited/fallback/candidate/missing/invalid/stale/exempted THEN UI 必须显示依据、owner、下一步和是否阻断，不能伪装 exact
3. WHEN 渲染 section/raw text/source metadata THEN 必须使用项目统一 sanitize；script、事件属性、javascript URL 和不可信 SVG 不得执行
4. WHEN context/权限/AI capability 变化或请求失败 THEN 旧 AI 内容和 active tab 必须清理；guidance 不再内嵌第二条 AI 承载链
5. WHEN 发布 `GuidanceRailAdapter` THEN adapter 只声明 visibility、disabled reason、location、version、draft 与 open/close 行为，不拥有最终 DOM/top/right/z-index
6. WHEN接入公共壳层 THEN 最终 review/guidance/AI trigger、panel 与 CSS 由 formula spec 的 `F-SHELL` 独占；本 spec 删除 fixed offset 并通过 adapter 接入

### Requirement 12: 权限、审计与可见性边界

**User Story:** 作为质量控制复核人，我希望 guidance 的读取、发布、补充和豁免都遵守可见性并留下完整审计。

#### Acceptance Criteria

1. WHEN 读取 guidance、inventory evidence 或 source ref THEN 必须复用 working paper/project visibility gate；不可通过错误详情推断无权项目内容
2. WHEN 方法论管理员发布标准内容 THEN 必须满足独立 reviewer capability；actor 与 reviewer 的角色组合由服务端验证
3. WHEN 项目用户维护 supplement 或 exemption THEN 必须按 project capability、scope 与双人审批规则校验，且不能升级为平台 publication
4. WHEN 日志/telemetry/audit 记录 THEN 必须含 correlation、subject、operation、version 与结果，但不得记录 token、完整附件正文或敏感项目内容
5. WHEN 权限在 panel 打开期间变化 THEN 必须 revalidate 并关闭/降级能力；旧 capability 不得持续到刷新后

### Requirement 13: custom candidate/finalized handoff、ACK 与 visibility saga

**User Story:** 作为自定义模板上传者，我希望 candidate 可供审核但绝不提前可见，finalized 内容只有在 durable ACK 后才成为 confirmed。

#### Acceptance Criteria

1. WHEN custom 提交 candidate handoff THEN 必须使用 candidate variant、candidate authority、九段 candidate sections/refs 与 evidence；consumer 只能登记 review_pending
2. WHEN custom 提交 finalized handoff THEN 必须使用 finalized variant，并包含 finalization、template version、entry/sheet、artifact/mapping/guidance digests、actor/time、stale fingerprint 与 supersedes
3. WHEN consumer 校验 finalized handoff THEN 必须依次验证 contract、authority、artifact、mapping/formula boundary、guidance revision、九段、refs 与 inventory membership
4. WHEN 校验成功或失败 THEN 必须写 durable、幂等 `ConsumerAck` ledger；ACK 必须绑定 handoff digest、consumer version、verdict 与 reasons
5. WHEN finalize 跨 custom/guidance/renderer/public-shell THEN 必须采用 `PENDING visibility → durable ACK ledger → producer commit-visibility transaction` saga；不得宣称跨系统 ACID 原子
6. WHEN 任一 required ACK 失败、超时或版本不兼容 THEN runtime visibility 保持 0，producer 可补偿/重试，candidate 不得被项目打开
7. WHEN template/sheet/mapping/formula/artifact/guidance 变化或 withdraw THEN 旧 confirmed stale；custom 只发布 reevaluation evidence，不等待本 spec 的 C2 归档任务

### Requirement 14: 行为测试、变异与浏览器证据

**User Story:** 作为项目负责人，我希望每层守卫都能被真实破坏打红，并在三个宿主观察到最终用户行为。

#### Acceptance Criteria

1. WHEN 建立 contract/data 测试 THEN 必须覆盖 C0 fixture、兼容矩阵、inventory identity、集合核算、publication、SourceRef registry 和 handoff/ACK
2. WHEN 建立 service/API 测试 THEN 必须覆盖 authoritative child、parent chain、candidate 不 exact、membership、权限、structured errors、stable cache 与 snapshot materialization
3. WHEN 建立前端测试 THEN 必须覆盖 host context、single fetch、三轴 UI、sanitize、adapter、owner epoch/revision 竞态和 whole-workbook
4. WHEN 运行变异 THEN 至少破坏 contract 单源、candidate/finalized discriminator、分母减 exemption、active publication 门、SourceRef digest、初始 emit、Univer switch、cache identity、sanitize、ACK visibility；每项必须准确 RED
5. WHEN 运行浏览器验收 THEN 必须覆盖 HTML、Univer、OnlyOffice 外层/整册、角色权限、快速切换、publication/supplement、rail adapter 消费、network/DOM/console
6. WHEN 保存 evidence THEN 必须使用共享 envelope，记录正向、预期失败、mutation 四态、trace、截图、版本与 inventory digest；grep 到字符串不得计通过

### Requirement 15: WIP 对账、跨 spec 依赖与最终闭环

**User Story:** 作为维护者，我希望现有 WIP、外部里程碑和最终归档都有可证明归属，任务不会因“文件存在”假绿。

#### Acceptance Criteria

1. WHEN 开始实施 THEN 必须逐文件把 guidance WIP 映射到 Task、AC、Property、owner、正向证据与 mutation 状态；无法归因项保持 frozen/blocked/foreign
2. WHEN 发布外部里程碑 THEN `G-C0/G-ID/G-RAIL/G-HANDOFF-CONSUMER` 必须各有 contract version、producer task、consumer list 与 evidence，不得靠自然语言隐含依赖
3. WHEN 消费外部里程碑 THEN `F-SHELL/X-HANDOFF-CONFORMANCE/X-RUNTIME-EVIDENCE` 必须在 tasks JSON 中显式声明；超时/缺失时标 blocked 而非勾选
4. WHEN 完成 C1 THEN catalog effective required 必须全 complete，pending/blocked 为 0，所有 exemption 有效，clean checkout 可复现
5. WHEN 完成 C2 THEN 只对 cutoff snapshot 生成不可变 milestone；最新 runtime 状态另由 `platform_guidance_health` 表达
6. WHEN 宣称 spec closure THEN 所有 required tasks、契约、tracked 产物、行为测试、变异、浏览器证据、C1、C2 与 WIP 对账必须完成；历史测试数字和未跟踪文件不得作为完成依据

## Glossary

| 术语 | 含义 |
|---|---|
| `G-C0` | 本 spec 发布的共享 wire contract bundle 里程碑 |
| catalog inventory | 按 template lineage/version + wp/sheet stable identity 枚举的标准内容清册 |
| runtime inventory | 按 organization/project/wp/entry/sheet 枚举的项目运行态清册 |
| primary source | 可成为 authoritative exact 的 active publication 或 durable custom-confirmed authority |
| extraction source | 从 xlsx/docx/BCD/custom artifact 抽取的 candidate 来源，不等于发布 authority |
| `C2Milestone` | 对固定 cutoff/runtime snapshot 的不可变历史闭环证据 |
| `platform_guidance_health` | cutoff 之后持续重算的当前健康状态，不反写历史 milestone |
| `ConsumerAck` | guidance consumer 对 finalized handoff 的 durable、幂等验证记录 |
