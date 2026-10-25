# Requirements Document

## Introduction

本 spec 把“上传 Excel 自定义模板”收敛为真实二进制摄取、隔离预检、逐 sheet 确认、不可变候选、受控发布、项目整册实例化和 durable 双向同步闭环。

已确认红基线：现有批量入口只读取首 sheet 后创建空白底稿；元数据接口并未可靠提交真实文件；旧 route 接受客户端路径/空内容；`custom_cells.update_custom_cells()` 先原地修改 current 文件，再读取 revision 并调用 writer，CAS 失败也无法撤销；custom lane 尚无 unified room、durable forcesave ACK、content application；custom_cells 与 WOPI/offline 使用不同 entry namespace，rollback/evidence 互不可见。

本 spec 直接冻结以下最终裁决：

1. 一份多 sheet 文件只产生一个 `ProjectWorkbookInstance` 和多个 `ProjectWorkbookSheetEntry`，共享 workbook generation/current artifact/OnlyOffice room；不得按 sheet 复制整册。
2. UploadArtifact、MappingDraft/TemplateCandidate、TemplatePublication、ProjectOperation 是四条独立生命周期，不再由一个枚举混合表达。
3. candidate 保持 quarantine 边界，只能生成静态 HTML/图片/结构预览；不生成生产 OnlyOffice config。
4. `.xlsm` 仅 quarantine/preflight，v1 finalize 永久阻断；external link/data connection 在 v1 永久阻断，不承诺 sanitizer。
5. `editable_grid` 必须具备 `CustomProjectionManifest + CustomWorkbookAdapter`；`read_only_html` 至少具备 extractor；只有 `onlyoffice_only` 可无 adapter。
6. HTML mutation 必须在 immutable staging copy 上应用，再使用客户端 base revision CAS；writer 成功后才切 current pointer。
7. finalize 采用 `PENDING visibility → durable ACK ledger → commit-visibility transaction` saga，不宣称跨 guidance/renderer/shell 的 ACID 原子。
8. 本 spec 消费 `G-C0/G-ID/G-HANDOFF-CONSUMER/F-SHELL` 和既有 sync/version 外部门；只发布 `X-HANDOFF-CONFORMANCE/X-RUNTIME-EVIDENCE`，不等待 guidance C2 任务。

## Requirements

### Requirement 1: 三入口与业务动作彻底隔离

**User Story:** 作为用户，我希望批量建空白底稿、维护模板元数据和摄取 Excel 模板各自具有准确语义，不再由“上传成功”混淆。

#### Acceptance Criteria

1. WHEN 打开 `GtCustomWpBatchDialog` THEN action 必须为 `batch_create_blank`，只消费空白底稿清单，不得声称保存、解析或发布 Excel 模板
2. WHEN 维护模板名称、分类或描述 THEN action 必须为 `maintain_metadata`，不得接收二进制、生成 preflight/candidate/publication 或改变项目 artifact
3. WHEN 选择“上传 Excel 自定义模板” THEN action 必须为 `ingest_excel_template`，进入独立 route、权限和生命周期，并提交真实 multipart 文件字节
4. WHEN telemetry、审计、幂等或 UI 表达动作 THEN 必须使用稳定 action id，不能只靠中文按钮文字
5. WHEN 旧 API 仍接收 `template_file_path`、空 `file_content` 或首 sheet 元数据 THEN 它不得进入正式 ingestion/publication 路径，并必须有带期限的迁移删除门
6. WHEN 任一入口成功 THEN 成功文案必须只描述其真实副作用；元数据/空白创建不得显示“模板已上传或发布”

### Requirement 2: tenant/org/project scope、capability 与不可变审批意图

**User Story:** 作为组织管理员，我希望上传、项目发布和组织发布从开始即绑定正确租户与审批意图，不能在 finalize 末尾补权限。

#### Acceptance Criteria

1. WHEN 创建 upload、mapping、candidate、publication 或 project operation THEN 必须显式绑定 tenant/organization，project-local 对象还必须绑定 project；服务端不得从客户端文件名或 wp_code 推断 scope
2. WHEN 启动组织级或项目级发布 THEN 必须创建 immutable `ApprovalIntent`，冻结 scope、candidate digest、policy version、requested capability、initiator、required approver class 与 expires_at
3. WHEN 组织级发布审批 THEN initiator 与 approver 必须为不同主体；方法论/模板管理员发起，业务合伙人或质量控制复核合伙人批准
4. WHEN 项目级 finalize/instantiate/upgrade/rollback/remap THEN 服务端必须按项目 visibility 与现场经理 capability 复验；审计助理只能上传和编辑 draft mapping
5. WHEN approval intent 过期、candidate/policy/scope/digest 变化或 authorization epoch 改变 THEN 原审批失效，必须创建新 intent；不得原地改批准对象
6. WHEN capability snapshot 未 ready、失效或与 operation write fence 不匹配 THEN preflight 之外的确认、发布、实例化和写入必须阻断
7. WHEN 业务合伙人、QC 或 EQCR 仅有项目读取权限 THEN 不得自动获得 raw quarantine 下载或组织发布权限

### Requirement 3: 单一 ingestion policy、流式 quarantine 与资源预算

**User Story:** 作为安全负责人，我希望所有上传先进入不可执行隔离区，并由一份版本化政策约束文件、解析器和组织资源。

#### Acceptance Criteria

1. WHEN 接收文件 THEN 服务端必须通过 multipart `UploadFile` 流式写 private quarantine，同时校验扩展名、MIME、ZIP magic、大小并计算 SHA-256；原文件名只作转义显示值
2. WHEN preflight 未通过 THEN 原始字节不得公开、执行、交给 OnlyOffice、生成项目底稿或进入 active runtime inventory
3. WHEN 应用 `CustomTemplateIngestionPolicy v1` THEN 单一配置至少定义 upload/expanded bytes、ZIP entries、单项及总压缩比、sheet、非空 cell、declared range、XML bytes/depth/nodes、CPU、wall time、RAM、file descriptor、temporary disk 与 organization concurrent/storage quota
4. WHEN policy 阈值或 policy version 改变 THEN 旧 preflight/candidate evidence stale，重新评估前不得 finalize
5. WHEN parser/scanner 执行 THEN evidence 必须记录 scanner build digest、parser/library versions、policy version、worker image digest 与资源用量；未知构建不得复用旧 PASS
6. WHEN 任一预算、组织 quota、timeout、worker crash 或取消触发 THEN 状态必须结构化失败/阻断，临时资源幂等清理；不得返回空报告或 `valid=true`
7. WHEN 原文件名、metadata 或 OOXML 文本进入日志/HTML THEN 必须转义/清洗，且日志不得记录文件正文、token 或个人敏感数据

### Requirement 4: 包路径、XML 与 OOXML 高风险政策

**User Story:** 作为安全负责人，我希望 ZIP 路径、XML 和 Office 高风险能力有明确 fail-closed 判据，不被平台静默执行或删除。

#### Acceptance Criteria

1. WHEN 扫描 ZIP entry THEN 必须统一分隔符并做 Unicode NFKC/casefold 规范化，拒绝绝对路径、drive/UNC、`.`/`..`、空 segment、尾随点/空格、ADS/冒号、Windows reserved device names、symlink/reparse 和规范化后重复碰撞
2. WHEN 解析 XML/relationship/content types THEN 必须禁用 DTD/entity/external fetch，限制 XML 大小/深度/节点/relationship 数量，并拒绝损坏、加密或密码保护包
3. WHEN 文件为 `.xlsx` THEN 可进入完整 preflight；公式只作为不可信文本与依赖 token 解析，不在服务端计算或执行
4. WHEN 文件为 `.xlsm` THEN v1 只允许 quarantine 与只读 preflight，必须 `FINALIZE_BLOCKED`；不得改扩展名或用 `keep_vba=false` 静默丢宏后发布
5. WHEN 包含 VBA/XLM、DDE、ActiveX、OLE/可执行嵌入对象、远程数据连接 THEN 必须 BLOCKER，普通用户不得豁免，也不得交浏览器/OnlyOffice 执行
6. WHEN 包含 external link、external relationship 或 external data connection THEN v1 必须永久 BLOCKER；本 spec 不实现 sanitized candidate，未来解除必须另立 policy/spec
7. WHEN 出现未知 OOXML feature THEN 必须 `BLOCK_PENDING_POLICY`；image/chart/drawing/comment/name/table/validation/conditional formatting/merge/hidden/protection 等允许项也必须进入 preservation inventory，不得因 HTML 不消费而静默丢失

### Requirement 5: 包级与逐 sheet preflight 可解释且可复现

**User Story:** 作为上传者，我希望看到整册与每个 sheet 的真实结构、风险和投影边界，而不是一个无解释力的布尔值。

#### Acceptance Criteria

1. WHEN 执行 preflight THEN 必须先完成 package/security gate，再由禁网隔离 worker 做 workbook semantic scan；package blocker 不得继续进入可执行预览
2. WHEN 生成 workbook report THEN 必须包含 artifact/policy/scanner digests、workbook relationships/features、sheet 数、defined names、cross-sheet formulas 与 preservation inventory
3. WHEN 生成 sheet report THEN 至少包含 stable observed sheet identity/name/order/visibility、used/non-empty range、freeze/protection/merge/hidden rows/cols、title/header/data/formula/read-only/dynamic region candidates
4. WHEN 分析 cell/formula THEN 必须列出 types/formats/formulas/dependencies/errors/circular-risk、tables、names、validation、conditional formatting、drawings/images/charts/comments
5. WHEN 分析身份 THEN 必须报告 existing stable key carriers、可安全 instrument 的候选、重复/空 key、动态行列稳定性和 locator drift 风险
6. WHEN 分析 guidance THEN 只能生成九段 extraction candidate/source refs/缺口，状态为 `custom_candidate/review_pending`，不得自动 confirmed
7. WHEN 产生 finding THEN 每项必须含 code、severity、workbook/sheet stable locator、source ref、policy decision、remediation；总体建议只能是 `editable_grid/read_only_html/onlyoffice_only/BLOCKED` 的派生结论

### Requirement 6: 四条独立生命周期与可恢复状态机

**User Story:** 作为模板管理员，我希望上传、候选、发布和项目操作各自可审计、可恢复，不被一个混合状态枚举掩盖。

#### Acceptance Criteria

1. WHEN 管理原始字节 THEN `UploadArtifact` 生命周期只能表达 quarantine/preflight/failed/rejected/expired，不得表达 publication 或项目 current 状态
2. WHEN 编辑 mapping/guidance THEN `MappingDraft` 可变且版本化；生成 `TemplateCandidate` 后 artifact/mapping/guidance revision immutable，修改必须创建新 candidate revision
3. WHEN 发布模板 THEN `TemplatePublication` 只能表达 `PENDING_VISIBILITY/ACTIVE/WITHDRAWN/SECURITY_REVOKED` 等发布状态，并引用 immutable finalized authority
4. WHEN 项目实例化、HTML mutation、OO forcesave、merge、upgrade、rollback 或 remap THEN 必须创建独立 `ProjectOperation`，含 base/current/incoming revisions、idempotency key、lease 与结果
5. WHEN 任一生命周期转换 THEN 必须校验 allowed transition、base revision、actor/capability、idempotency 和 write fence，并记录 input/output digests、reason、clock time
6. WHEN worker/process 崩溃 THEN watchdog 必须根据 durable operation/outbox/lease 恢复或补偿；不得靠单个混合状态猜测跨域事务是否完成
7. WHEN cleanup/retention 运行 THEN 必须使用 injectable clock；测试不得依赖真实墙钟或 sleep

### Requirement 7: `ProjectWorkbookInstance + ProjectWorkbookSheetEntry` 表示模型

**User Story:** 作为项目使用者，我希望多 sheet 模板保持一份整册语义和跨 sheet 公式，而每个 sheet 仍可拥有稳定底稿入口。

#### Acceptance Criteria

1. WHEN finalized 多 sheet template 为项目实例化 THEN 必须创建一份 `ProjectWorkbookInstance`，持有 project/wp workbook identity、pinned template version、current artifact pointer、content/representation revision、workbook generation 与 OnlyOffice room identity
2. WHEN 某 sheet 纳入项目 THEN 必须创建 `ProjectWorkbookSheetEntry` child，持有 stable entry id、sheet uid/code、wp_code、componentType、projection mode、manifest/guidance versions，并引用同一 workbook instance
3. WHEN workbook 有 N 个纳入 sheet THEN 不得复制 N 份 xlsx/current pointer/OO room；所有 child entry 必须共享 workbook generation 并保留跨 sheet formula/defined-name/整册关系
4. WHEN 任一 sheet 写入导致 xlsx 改变 THEN workbook artifact/content generation 整体推进，各 child projection 按受影响集更新；不得只推进某 sheet 私有二进制 revision
5. WHEN sheet rename/reorder 但 stable sheet uid carrier 保持 THEN child entry identity 不变；显示 label 与数组下标不得作为 entry key
6. WHEN renderer/guidance/public shell 定位 child entry THEN 必须能解析回唯一 workbook instance、sheet uid 与 current generation；多解/无解必须 blocked
7. WHEN legacy custom_cells、WOPI/offline 使用不同 `wp_code/wp_id` namespace THEN active 发布前必须通过统一 entry namespace migration gate；双 pointer/generation 不得并存

### Requirement 8: 稳定身份、mapping 与 projection adapter 契约

**User Story:** 作为结构化视图用户，我希望字段、动态行列和公式通过稳定身份映射，并且每种 projection mode 只承诺真实能力。

#### Acceptance Criteria

1. WHEN 进入确认向导 THEN 用户必须逐 sheet 确认业务名、wp_code/循环、纳入状态、区域、字段、公式、只读/动态边界、projection mode 与 preservation decisions
2. WHEN 定义 field/row/column identity THEN 必须来自已存在稳定 key carrier，或来自经用户确认、在新 immutable instrumented candidate 中写入并完成 roundtrip 验证的 carrier
3. WHEN 既无 existing carrier 又不能安全 instrument THEN 该动态区域不得选择 `editable_grid`，必须降为 `read_only_html/onlyoffice_only`
4. WHEN 选择 `editable_grid` THEN 必须存在版本化 `CustomProjectionManifest` 与非空 `CustomWorkbookAdapter`，支持 extract/apply/validate/diff/rebase，并声明 managed/unmanaged boundary
5. WHEN 选择 `read_only_html` THEN 至少存在 deterministic extractor 与 preservation evidence，所有编辑控件和“双向已验证”状态隐藏
6. WHEN 选择 `onlyoffice_only` THEN adapter/HTML projection 可为 null，但 UI 不得创建空 Grid、空对端或伪双向能力
7. WHEN field label、顺序或格式变化 THEN stable field/row/column identity、formula link、review thread 和历史值不得随之改变
8. WHEN mapping、adapter/manifest contract 或 formula boundary 不完整 THEN candidate/finalize 必须精确显示 sheet/region/field 缺口并阻断

### Requirement 9: candidate 静态预览与 guidance candidate

**User Story:** 作为上传者，我希望在不突破 quarantine 的前提下检查候选结构和说明，不让未发布字节进入生产文档服务。

#### Acceptance Criteria

1. WHEN candidate 尚未 ACTIVE THEN 只能生成经 sanitizer 的静态 HTML、不可执行图片或结构化报告预览；不得生成生产 OnlyOffice config、WOPI URL 或可编辑 iframe
2. WHEN 静态 HTML 展示公式、链接、comments、names 或 properties THEN 只显示转义文本，不执行公式、脚本、外链、DDE 或 embedded object
3. WHEN 预览 mapping THEN 必须分别展示 managed/unmanaged、editable/read-only、projection mode、stable identity 和 preservation 风险
4. WHEN 预览 guidance THEN 必须使用 `G-C0` candidate handoff variant 与 SourceRef registry；不得填充 finalized-only 字段或生成 custom_confirmed
5. WHEN candidate artifact/mapping/guidance/policy/scanner digest 变化 THEN 所有预览和确认 evidence stale，必须重新生成/确认
6. WHEN candidate 过期、被拒绝或 superseded THEN 预览 token/URL 失效且 runtime discoverability 保持 0

### Requirement 10: pending visibility finalize saga 与 durable ACK ledger

**User Story:** 作为现场经理，我希望发布失败时模板完全不可见，所有 consumer 真正确认后才一次切换为 ACTIVE。

#### Acceptance Criteria

1. WHEN finalize 开始 THEN 必须锁定 immutable candidate revision、ApprovalIntent、policy/scanner/authority/mapping/guidance digests 与 idempotency key
2. WHEN 预生成 publication/workbook-entry/manifest identities THEN 数据库只能写 `PENDING_VISIBILITY` metadata、rollback point 和 outbox；renderer/runtime inventory 不得读取 pending 对象
3. WHEN 向 guidance 提交 handoff THEN 必须消费 `G-HANDOFF-CONSUMER`，使用 finalized variant，并等待绑定 handoff digest/consumer version/verdict 的 durable `ConsumerAck`
4. WHEN renderer/public-shell/entry-namespace 等 required conformance gate 存在 THEN 必须写同一 required ACK ledger；任一 REJECTED/timeout/unknown major 使 visibility 保持 0
5. WHEN required ACK 全 ACCEPTED THEN producer 在单一 commit-visibility transaction 中把 publication、runtime entries 与 discoverability 切 ACTIVE；跨系统过程不得宣称 ACID 原子
6. WHEN saga 任一步失败或进程中断 THEN 必须幂等重试或 compensation 回 candidate-ready/pending-failed，不能留下半发布/孤儿 active entry
7. WHEN 同一 idempotency key 重试 THEN 返回同一 finalization/result 或结构化 digest conflict，不生成重复 publication/entry

### Requirement 11: 项目实例化、pin、withdraw 与 emergency revocation

**User Story:** 作为项目负责人，我希望项目使用自己的 pinned 整册副本，新版本或普通撤回不会静默改变既有工作。

#### Acceptance Criteria

1. WHEN ACTIVE publication 实例化 THEN 从 immutable finalized artifact 创建项目 `ProjectWorkbookInstance` current representation；HTML/OnlyOffice 不得直接编辑 candidate 或组织模板
2. WHEN 项目上下文包含年度、准则、公司和模板类型 THEN 必须来自项目真源并进入 content context fingerprint，不能在上传时写死
3. WHEN organization 发布新版本 THEN 既有项目默认 pin 原版本，只生成 available-upgrade；不得自动替换 current artifact
4. WHEN publication 状态为 WITHDRAWN THEN 禁止新实例化，但已 pin 项目继续使用并显示状态/升级建议；不得因普通撤回变 orphan
5. WHEN 独立 emergency security revocation 被有权主体批准 THEN 可阻断已 pin 项目打开/写入，并必须包含影响清册、通知、恢复/迁移路径和审计证据
6. WHEN project instance 初始化失败或任一 child entry 无法被 renderer/guidance/F-SHELL 唯一识别 THEN current pointer 不创建且实例化回滚
7. WHEN 计算 content fingerprint THEN 不得包含用户权限/角色；权限变化使用独立 `authorizationEpoch/writeFence`，避免无内容变化却制造 artifact 冲突

### Requirement 12: HTML mutation 的 immutable staging、客户端 base CAS 与单一 writer

**User Story:** 作为 Grid 用户，我希望写入失败或并发冲突时 current xlsx 完全不变，成功后 OnlyOffice 能读到同一整册版本。

#### Acceptance Criteria

1. WHEN Grid 提交 mutation THEN payload 只能包含 workbook/sheet/managed stable identities、typed values、客户端已观察的 base content/representation revision、authorization epoch、operation id 与 reason
2. WHEN 服务端接收 THEN 必须先读取并校验客户端 base revision、permission/write fence、mapping/adapter/type/protected boundary；不得先修改 current 文件再读取 revision
3. WHEN 校验通过 THEN 必须从 immutable base bytes 创建私有 staging copy，在 staging 上 apply adapter、重开反读、做 managed/unmanaged preservation diff 与 projection refresh
4. WHEN staging 验证通过 THEN 只允许通过既有 `AuthoritativeContentWriter.commit_bytes` 或同一单一 writer，携客户端 base revision执行 CAS；writer 成功后才切 current pointer/generation
5. WHEN CAS stale、writer/adapter/diff/反读失败 THEN 必须丢弃 staging、不推进 pointer/revision，UI 保留编辑并返回 conflict/remediation
6. WHEN commit 成功 THEN 所有受影响 child projections 使用新 workbook generation 刷新，OnlyOffice 下次打开读取新 current pointer
7. WHEN 现有实现原地调用 `write_cells_to_xlsx(ctx.wp.file_path, ...)` THEN 必须删除该正式写链，不能靠失败后补偿掩盖不可回滚修改

### Requirement 13: OnlyOffice durable/application、room 与 namespace 外部门

**User Story:** 作为在线 Excel 用户，我希望切回 HTML 前先真正 durable，且所有 sheet/入口围绕同一整册 room、pointer 和 application 身份。

#### Acceptance Criteria

1. WHEN custom workbook 启用 OnlyOffice THEN 必须消费 `SYNC-UNIFIED-ROOM`，整册只有一个 active room/document key；child sheet entry 不得各建独立 room
2. WHEN callback/route 从 wp_code、wp_id、entry_id 等入口定位 workbook THEN 必须消费 `SYNC-MULTI-RESOLVER`，所有合法入口唯一解析到同一 workbook instance/generation，多解或无解 fail-closed
3. WHEN 从 OnlyOffice 切回 HTML THEN 必须创建带 request/operation identity 的 forcesave，等待 `SYNC-DURABLE-APPLICATION` 证明 callback artifact 已 durable 且 content application 成功；accepted 不等于 durable
4. WHEN legacy namespace 不一致 THEN 必须先通过 `SYNC-ENTRY-NAMESPACE` migration/conformance；custom_cells 与 WOPI/offline 的 pointer/generation/rollback/evidence 必须合一
5. WHEN durable artifact 就绪 THEN projection refresh 必须使用 expected workbook content/representation revision和 adapter version，成功后 HTML 才 reload
6. WHEN forcesave timeout、callback 未 durable、artifact fingerprint 不符、status 6/2 重试或 application 失败 THEN 留在 OO/显示阻断，不得提前 pull/refresh/success
7. WHEN nothing_to_save THEN 仍须证明 room artifact、current pointer、generation 与 projection fingerprint 一致后才切回

### Requirement 14: 三方 merge、结构 remap 与 crash recovery

**User Story:** 作为并发用户，我希望不同字段可合并，同字段和结构冲突可见且可恢复，不被整文件最后写入覆盖。

#### Acceptance Criteria

1. WHEN HTML 与 OO 基于同一 base 修改不同 managed stable fields THEN `CustomWorkbookAdapter` 的 three-way merge SPI 可自动合并，并保留双方 unmanaged parts
2. WHEN 双方修改同一 field 为不同 typed value THEN 必须生成字段级 conflict preview/decision；不得整文件 last-write-wins
3. WHEN OO 增删/移动受管行列、改 sheet identity、cross-sheet formula/defined name 或使 locator 失效 THEN 必须生成 `RemapCandidate` 并阻断自动 projection 覆盖
4. WHEN 用户确认 remap THEN 发布新 manifest/adapter mapping version、migration report、guidance stale evidence、review/formula anchor migration 和 rollback point
5. WHEN label/顺序变化但 stable carrier 存续 THEN identity/thread/formula/history 保持；当 carrier 丢失或重复时不得按 label 自动猜回
6. WHEN browser/server/OO 在 staging、forcesave、merge、remap 任一中间状态崩溃 THEN ProjectOperation 可重放或补偿，current pointer 不得指向半成品 artifact
7. WHEN merge/remap 需要的 adapter capability 缺失 THEN projection mode 必须降级或 blocked，不能把 adapter=null 解释为“无需冲突处理”

### Requirement 15: immutable 版本、升级/回滚、引用图与 retention

**User Story:** 作为平台管理员，我希望模板和项目历史不可变、升级可预览回滚，清理不会删除仍被引用的字节。

#### Acceptance Criteria

1. WHEN 发布新模板 THEN 必须创建 immutable publication/version/lineage，不原地覆盖旧 artifact、manifest、guidance 或 adapter version
2. WHEN 项目升级 THEN 必须先展示 workbook/sheet/field/formula/preservation/guidance/adapter diff、迁移计划、冲突、预计 hash 与 rollback point，并由有效 ApprovalIntent 确认
3. WHEN 升级应用 THEN 走 ProjectOperation + staging/CAS，保留项目数据、unmanaged parts、stable identity 与审计；失败不动 current pointer
4. WHEN 回滚 THEN 必须恢复 template/manifest/guidance/content/representation 指针并生成新的审计 revision，不删除失败升级或后续历史
5. WHEN cleanup 决策 THEN 必须查询 artifact reference graph，覆盖 upload/candidate/publication/project generation/rollback/evidence/legal hold/active lease；仅 reference count 数字不足以判定可删
6. WHEN 应用 retention THEN incoming/temp 最长 24h、failed/rejected 7d、未发布 candidate 30d 等期限来自 policy；ACTIVE、pin、rollback、evidence 或 legal hold 引用对象不得物理删除
7. WHEN cleanup 使用 injectable clock 运行 THEN 先写 tombstone/intent，再删对象，最后写结果；失败可重试且不能留下 metadata 指向已删 artifact

### Requirement 16: artifact 访问、审计、跨 spec contract 与 runtime evidence

**User Story:** 作为维护者，我希望文件访问和跨 spec 依赖可审计，custom 只发布自己的证据而不形成闭环依赖环。

#### Acceptance Criteria

1. WHEN 下载 raw/candidate/finalized/project artifact 或生成生产 OnlyOffice config THEN 必须做 scope/capability 检查并使用短期 token；storage key 不得公开枚举
2. WHEN 保存审计/telemetry THEN 必须使用 `G-C0` EvidenceEnvelope subject union，包含 tenant/org/project/operation、digests、contract versions、scanner build、revisions 与 verdict，不记录正文/token
3. WHEN custom UI/runtime 接入公共页面 THEN 必须消费 `F-SHELL` location/outlet/rail/capability contract，不复制按钮、dialog、location store 或 fixed CSS
4. WHEN finalize guidance THEN 必须消费 `G-HANDOFF-CONSUMER`；custom 只生产 handoff value 和 visibility saga，不复制 ConsumerAck schema/validator
5. WHEN完成 candidate/finalized/ACK/rollback conformance THEN 发布 `X-HANDOFF-CONFORMANCE` evidence，供 guidance 验收
6. WHEN runtime entry 创建、升级、回滚、withdraw 或 stale THEN 发布 user-upload runtime inventory projection 与 `C2_REEVALUATION_REQUESTED` evidence，形成 `X-RUNTIME-EVIDENCE`
7. WHEN 发布 X milestones THEN 不得等待 guidance Task 22/23 或 C2 PASS；guidance 消费 evidence 后独立评估，避免 `X→G→X` 隐藏环

### Requirement 17: 行为测试、变异、Playwright 与完成门

**User Story:** 作为项目负责人，我希望从恶意上传到整册双向、冲突、升级和清理都有可复现证据，而不是模板列表多一行就宣称完成。

#### Acceptance Criteria

1. WHEN 建立自动化 THEN 必须覆盖三入口、scope/approval、policy/quota、path/XML/package security、semantic preflight、四生命周期、workbook/sheet model、mapping/adapter、preview、finalize saga、instantiate、CAS、durable gates、merge/remap、version/retention
2. WHEN 运行变异 THEN 至少覆盖绕 quarantine、Unicode/casefold/ADS path、空报告 valid、scanner digest 复用、xlsm/外链放行、candidate OO config、adapter=null editable、每 sheet 复制 workbook、原地改 current、先读 server revision 代替 client base、accepted 当 durable、namespace split、last-write-wins、撤回 orphan、权限进入 content fingerprint；每项准确 RED
3. WHEN 运行 Playwright THEN 必须覆盖三入口、真实 multipart、恶意/复杂文件、`.xlsm`/外链阻断、静态 candidate preview、三 projection mode、多 sheet 单 workbook、权限/双人审批、HTML→OO、OO→HTML、冲突/remap、升级/回滚/withdraw/revocation/cleanup
4. WHEN 保存 evidence THEN 必须附 original/candidate/publication/project hashes、policy/scanner/mapping/guidance/adapter versions、room/entry identity、content/representation revisions、network 顺序、trace、截图、console 和 cleanup result
5. WHEN 宣称 closure THEN active publication 无 blocker/未裁决 warning/半发布/孤儿 artifact；runtime entries 可由 renderer/guidance/F-SHELL/OO 唯一解析；required editable_grid 双向全通过；read-only/OO-only 无伪对端；stale evidence=0
6. WHEN 最终归档 THEN 正式 contract/migration/tests/mutation/evidence 均 tracked，clean checkout 可复现，临时诊断产物清理；X milestones 已发布但不等待 guidance C2

## Glossary

| 术语 | 含义 |
|---|---|
| `UploadArtifact` | 原始上传字节及 quarantine/preflight 生命周期 |
| `TemplateCandidate` | artifact+mapping+guidance 的不可变候选 revision，运行时不可见 |
| `TemplatePublication` | finalized authority 的发布/可见性生命周期 |
| `ProjectOperation` | 实例化、写入、forcesave、merge、升级、回滚、remap 的可恢复操作 |
| `ProjectWorkbookInstance` | 项目中一份完整 workbook 的 current pointer/revision/generation/OO room owner |
| `ProjectWorkbookSheetEntry` | 指向同一 workbook instance 的稳定 sheet child entry |
| stable identity carrier | workbook 中持久承载 field/row/column/sheet identity 的既有或经确认 instrumented 元数据 |
| `CustomWorkbookAdapter` | editable projection 的 extract/apply/validate/diff/rebase/merge SPI |
| `PENDING_VISIBILITY` | finalize ACK 完成前不可被 runtime 发现的 publication 状态 |
| `X-RUNTIME-EVIDENCE` | custom 发布给 guidance 的 user-upload runtime inventory 与 reevaluation evidence，不是 C2 PASS |
