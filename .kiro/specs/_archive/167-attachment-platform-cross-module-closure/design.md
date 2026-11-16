# 设计：附件平台跨模块闭环

## 1. 现状确认与约束

当前生产主链仍是 `AttachmentService + attachments`；治理链使用同一根外加 `attachment_versions/EvidenceRef`；知识库和 AI 会话各自有独立文件模型。已有产物可复用：

| 能力 | 已有产物 | 本轮处理 |
|---|---|---|
| 底稿整稿/行级证据 | `workpaper_evidence_intake`、`attachment_wp_view`、`EvidenceLink` | 保留为权威关系，补 readiness/trace |
| 凭证身份 | `voucher_key`、查询/复用、前端索引 | 不重写，仅纳入统一就绪度 |
| 合同身份 | V232、`contract_evidence`、`contract-reuse` | 补查询、D4 写入/改绑/复用 |
| 函证 | `ConfirmationAttachmentLink`、OCR compare/apply | 合并上传事务、服务端能力 |
| 归档/QC | 证据声明 evaluator、QC-17、完整性 10 类 | 抽单一 readiness，正式门 fail-closed |
| 溯源 | `UnifiedLineageService`、`AttachmentLineage` | 底稿直接读权威表；输出域使用 lineage |
| 治理版本 | `AttachmentVersion`、alias、backfill、gateway | 兼容双写与安全读取，不删 legacy |
| 知识库 | ACL、OCR worker、RAG、版本 | 共享字节/安全原语，保留领域 ACL |
| AI 附件 | `AIChatAttachment`、run request | 保持临时模型，修授权资源接线 |

外部依赖与降级：Paperless/OCR/向量不可用时不生成伪成功；普通本地附件可按既有配置回退，治理 staged 保留；RAG 仍可词法降级。共享 PG 不做数据迁移和真实 purge，除非用户另行放行。

## 2. ADR

### ADR-APC-001　领域实体分离，字节底座统一

新增 `asset_blobs` 作为不可变字节描述，不含 ACL、不提供公开读取。AttachmentVersion、KnowledgeDocument 通过 nullable FK 引用；AIChatAttachment本轮只复用安全原语，不强制 blob 化。

### ADR-APC-002　先授权领域对象，再解析字节

`attachment_storage_resolver` 接受项目或知识根和存储键，使用 `Path.resolve(strict=True)`/realpath 后判祖先关系。调用方不能直接打开 DB 路径。拒绝返回统一 404/领域错误，日志不含真实路径。

### ADR-APC-003　公开 raw path 建档端点删除

仓库内无生产调用方。内部方法改名为 `create_attachment_record_from_storage`，只接受存储编排产生的结构；旧方法保留短期私有别名仅供兼容测试，公开 POST 不注册。

### ADR-APC-004　项目 purge 每项目原子

三类回收站入口委托 `ProjectPurgeService`。每项目显式事务、锁后重读、legal hold/外部引用预检、正常 FK 下叶到根删除；不能安全拓扑化就拒绝。批量按项目隔离结果。提交后再清物理对象。

### ADR-APC-005　就绪事实与阻断政策分离

`EvidenceReadiness` 四态：`ready/not_ready/not_declared/unknown`。evaluator只产事实；QC/签发/归档映射严重度。正式签发和归档对 `not_ready/unknown` 阻断；关键证据未确认 OCR 算 not_ready，普通 OCR 为 warning。

### ADR-APC-006　不双写底稿溯源

底稿 trace 直接查询 `EvidenceLink/AttachmentWorkingPaper`；输出域使用 `AttachmentLineage`。新增唯一索引防重复，target ref 使用稳定业务键，不使用显示序号。

### ADR-APC-007　跨域只做显式快照

知识文档晋升证据时复用不可变 blob，创建新的项目证据身份和 append-only provenance；知识 ACL不变。项目附件加入 AI run 时钉住 version/hash，只建立 run resource，不创建新附件。

## 3. 关键接口

```python
@dataclass(frozen=True)
class StorageReadPlan:
    kind: Literal["local", "remote", "rejected"]
    canonical_path: Path | None
    remote_locator: str | None

@dataclass
class WorkpaperEvidenceReadiness:
    status: Literal["ready", "not_ready", "not_declared", "unknown"]
    requirements: list[dict]
    missing_types: list[str]
    warnings: list[dict]
    errors: list[dict]
```

核心服务：

- `AttachmentStorageResolver.plan_for_project(project_id, storage_type, key)`
- `EvidenceReadinessService.evaluate_workpaper/evaluate_project`
- `ProjectPurgeService.purge_one/purge_many`
- `AttachmentTraceService.for_object`
- `AssetBlobService.ingest/read_plan`
- `KnowledgeEvidencePromotionService.promote`
- `AiRunResourceService.authorize_and_pin`

## 4. 数据模型

动态取当前最大迁移号后新增 V/R 配对：

- `asset_blobs`：不可变身份、hash、size、MIME、storage_type/key、security_status、actor、created_at。
- `attachment_versions.blob_id`、`knowledge_documents.blob_id` nullable FK。
- `knowledge_evidence_promotions`：source doc/version/blob/hash → target attachment/version/project/year + actor/idempotency。
- `ai_chat_run_resources`：run/session/kind/resource/version/blob/hash + actor。
- `attachment_lineage` 幂等唯一索引；迁移前报告重复，不静默删。

旧列全部保留。切换开关：`ATTACHMENT_ASSET_PHASE=M0..M4`、`KNOWLEDGE_BLOB_MODE=legacy|shadow|prefer_blob|blob_only`、`AI_PROJECT_ATTACHMENT_INPUT`。默认 M1/shadow/false，待对拍后提升。
## 5. 交付单元

### A. P0 安全

删除 raw-path HTTP 路由；建立项目级 resolver；迁移下载、预览、Office、OCR、归档、purge；加入历史路径只读清册。项目 purge 单独服务化，任何真实删除仅在测试事务/测试项目执行。

### B. 就绪度

先把 `attachment_wp_view` 逻辑包进四态服务，再逐一迁移 QC、归档、sufficiency、签发和旧 SignReadiness。项目聚合首版允许正确优先的逐稿调用，同时记录查询数；后续批量预取优化。

### C. 合同与函证

合同查询放入既有 `wp_evidence` router，避免新 router 漏挂；前端索引镜像凭证单飞。D4 只在用户确认后的最终字段上绑定。函证新增 multipart 单端点，数据库事务失败时本地删除，Paperless 记补偿失败。

### D. 溯源

`AttachmentTraceService` 合并权威底稿关系与 AttachmentLineage。报表、附注复用现有 trace 菜单；交付件扩 `deliverable_section` 并转现有 LinkageContract。

### E. 资产和跨域桥

安全 blob schema/服务先 additive；普通附件新写双投影但 legacy API 不变。知识新二进制写 shadow blob，授权后预览对拍。晋升与 AI run resource 都要求幂等、版本钉住和零权限放宽。

### F. 前端与验收

错误状态、能力门、预览竞态、缓存上限、分页与 a11y 分批落地。浏览器使用 `127.0.0.1:3030`；只用【测试】项目，写入前后逐表/文件对账并恢复。

## 6. 安全与事务

- 文件系统/Paperless 与数据库不能同事务：先写临时/隔离对象，DB commit 后升格；失败通过持久补偿记录重试。
- 任何客户端不得提交 hash、storage key 或服务器路径作为权威值。
- project/knowledge/AI 各自先做领域授权；blob id/hash 不构成权限。
- active content 默认下载；所有下载加 `nosniff` 和安全 Content-Disposition。
- service 只 flush，router/command 统一 commit；fail-open DB 查询必须在 SAVEPOINT 内。

## 7. 测试设计

| 层 | 重点 |
|---|---|
| 纯函数/PBT | realpath、合同键、四态 readiness、版本解析、依赖拓扑、上下文预算 |
| SQLite | DTO、UI contract、无 PG 专属语义的服务 |
| PG | FK/触发器、并发版本、purge 原子性、legal hold、跨项目、迁移三层一致 |
| 端点 | 未登录/非成员/readonly/edit/review/admin 正反角色；真实请求信封 |
| 前端 | 请求形状、竞态、错误≠空、缓存 TTL、readonly、a11y |
| Playwright | 七条真实业务链，刷新后回读与数据恢复 |

变异重点：删除边界判定、去掉 project 条件、把 unknown 当 ready、合同不改绑、函证恢复两步上传、lineage 双写断一边、AI 静默丢附件，均须对应测试打红。

## 8. ROI 与延后项

本轮高收益必做：P0 安全、就绪度、合同/函证真实闭环、输出溯源、知识上传安全、AI 附件接线。它们直接影响数据泄露、法定保全、签发正确性或用户可用性。

本轮只做兼容底座、不强制上线：全库物理去重、M4 删除 legacy、AIChatAttachment blob 化、自动跨域索引、跨域统一保留期。原因是改动面大、真实容量/覆盖率未知，且不影响先关闭当前风险。对应开关和观测点必须实现，切换需另附真实清册证据。

## 9. 验收与回退

- 每个交付单元可单独关闭；schema additive 不回滚删除数据。
- 候选提交在干净 worktree 复跑；聚合型守卫比较违规集合差集。
- 共享库迁移执行前备份 schema_version 与受影响行，写回退 SQL并向用户停点确认。
- 完成标记只接受代码、测试、变异、浏览器和数据恢复证据；环境阻断项保持未勾选。
