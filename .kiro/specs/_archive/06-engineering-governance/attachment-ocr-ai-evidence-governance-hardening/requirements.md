# Requirements Document
附件、OCR、AI 与证据链治理加固

## Introduction

本 spec 承接已归档的 `platform-evidence-knowledge-ai-governance`，把现有附件、OCR、知识检索、AI 内容确认、复核和交付件能力，从 DTO、软关联和模块局部接入，升级为持久、可验证、不可跨项目、可失效传播、可离线归档的审计证据链。

本 spec 优先处理已实证的 P0 风险：EvidenceRef 仅为 DTO；附件缺少证据元数据与内容哈希；OCR 缺少持久 Job/Result/Writeback；AI confirmed 尚未形成全入口硬门禁；附件关联未证明源目标项目一致；OCR 重试权限不完整；本地 `file_path` 可能越过存储边界；`created_by` 可能缺失；归档缺少统一证据 manifest。

## Glossary

- **Attachment_Version**：同一逻辑附件的一次不可变内容快照，内容变化必须创建递增新版本。
- **Storage_Boundary**：附件服务被授权访问的文件存储根范围。
- **Content_Hash**：由附件或内容字节计算的稳定摘要，用于完整性与版本绑定。
- **EvidenceRef**：持久化证据引用，绑定项目、年度、证据对象、版本、哈希和引用上下文。
- **Controlled_Module**：底稿单元格、抽样项、凭证、函证、复核意见、附注表格、报告段落、AI 输出、交付件或归档包。
- **OCR_Job**：绑定确定附件版本的持久识别任务。
- **OCR_Result**：包含原始文本、页码、区域、字段、置信度和引擎版本的不可变识别结果。
- **OCR_Writeback**：将人工确认后的 OCR 字段原子写入目标对象的操作记录。
- **Citation_Snapshot**：AI/RAG 使用来源时冻结的 EvidenceRef、页码、区域、摘录、版本和哈希。
- **AI_Content**：状态为 suggestion、draft、confirmed 或 rejected 的模型生成内容。
- **stale**：对象依赖的证据版本、哈希或确认依据已失效，必须重新计算、定位、确认或复核。
- **Formal_Output**：正式底稿结论、附注、报告、签发文件、QC/EQCR 结论、终态交付件或归档包。
- **Blocking_Review**：严重级别为高或关键且尚未有效关闭的复核意见。
- **Archive_Manifest**：归档包中列举证据对象、关系、版本、哈希、状态和责任主体的机器可读清单。
- **Legal_Hold**：解除前禁止删除、覆盖或清理指定证据及其链路记录的法律保全状态。
- **Service_Identity**：可追溯的系统作业主体，不等同于人工用户且不能执行人工确认。

## Requirements

### Requirement 1: 附件接收安全与责任主体（P0）

**User Story:** 作为审计助理，我希望附件在进入项目证据域前完成边界、类型、大小、项目权限和责任主体校验，避免错误文件或越权文件进入证据链。

#### Acceptance Criteria

1. WHEN 用户发起每次附件上传尝试，THE Evidence_Governance_System SHALL 在执行内容验证前先持久记录最小 UploadAttempt 审计元数据，包括项目、年度、清洗后的文件名、声明媒体类型、安全识别得到的实际媒体类型（如已识别）、已接收字节数与 Content_Hash（如已计算）、actor、尝试时间和 validation outcome；验证完成后 SHALL 更新同一尝试的 outcome，而不是另建匿名尝试。
2. IF 附件为空、超过平台配置上限、文件名非法、声明类型不在允许清单、声明类型与安全识别的实际内容不一致或创建主体缺失，THEN THE Evidence_Governance_System SHALL 拒绝该附件、不创建可用 Attachment 或 Attachment_Version、保留失败 UploadAttempt 的最小审计元数据并返回明确失败类别，且不得保留任何可访问的恶意或被拒绝文件内容。
3. IF 解析后的读取目标位于 Storage_Boundary 之外、附件不属于当前项目、用户无项目访问权、存储不可用、完整性校验失败、对象处于 quarantined 状态或其他安全/可用性前置条件不满足，THEN THE Evidence_Governance_System SHALL 拒绝请求；对边界或权限失败 SHALL 在读取任何文件字节前拒绝，所有拒绝均不得泄露路径或目标项目信息并 SHALL 记录安全审计事件。
4. WHEN 用户上传、创建或关联附件，THE Evidence_Governance_System SHALL 使用当前用户或明确的 Service_Identity 填充责任主体，禁止产生匿名新记录。

### Requirement 2: 证据元数据与不可变附件版本（P0）

**User Story:** 作为现场负责人，我希望每份可引用附件都有完整证据属性和不可变版本，以便判断来源并复现历史结论。

#### Acceptance Criteria

1. WHEN 新附件完成上传，THE Evidence_Governance_System SHALL 记录来源、取得日期、提供方、是否关键证据及元数据完整状态；元数据不完整时禁止新建正式 EvidenceRef、确认 AI 内容或进入归档。
2. WHEN 用户替换附件内容，THE Evidence_Governance_System SHALL 创建版本号严格递增的新 Attachment_Version、计算新 Content_Hash，并保留旧版本字节、元数据和责任主体。
3. IF 用户请求删除或替换已被引用、已进入 Formal_Output 或处于 Legal_Hold 的附件版本，THEN THE Evidence_Governance_System SHALL 展示直接与传递影响范围、要求有权限用户确认、禁止覆盖旧版本并将受影响下游标记 stale。
4. WHILE Attachment_Version 已创建，THE Evidence_Governance_System SHALL 禁止修改其原始字节、Content_Hash、创建主体和创建时间。

### Requirement 3: 持久 EvidenceRef 与引用完整性（P0）

**User Story:** 作为质量控制复核人，我希望 EvidenceRef 是可查询、可保留的持久记录，而不是随请求消失的 DTO。

#### Acceptance Criteria

1. WHEN Controlled_Module 创建证据引用，THE Evidence_Governance_System SHALL 持久保存引用 ID、项目、年度、证据类型、目标 ID、目标版本、目标哈希、标签、引用上下文、created_by、创建时间和有效状态。
2. IF 目标不存在、源目标项目或年度不一致、目标版本或哈希不匹配、目标已删除或创建者无目标读取权，THEN THE Evidence_Governance_System SHALL 拒绝创建引用且不留下部分引用或反向关系。
3. WHEN 同一引用意图被重复提交，THE Evidence_Governance_System SHALL 幂等返回同一活动引用，不得产生重复引用或重复反向关系。
4. WHEN 用户停用 EvidenceRef，THE Evidence_Governance_System SHALL 要求原因、保留历史记录、停止其参与新的 Formal_Output 并触发影响评估。

### Requirement 4: 跨模块关联与项目隔离（P0）

**User Story:** 作为审计助理，我希望附件能关联到底稿、抽样、函证、复核、附注、报告和交付件，但任何关联不得跨项目或年度。

#### Acceptance Criteria

1. WHEN 用户建立跨模块关联，THE Evidence_Governance_System SHALL 校验源对象与目标对象属于同一项目和年度，且当前用户同时具备两端访问权。
2. IF 项目或年度不同、目标底稿不存在、目标已删除或用户对任一端无权，THEN THE Evidence_Governance_System SHALL 拒绝关联、保持两端不变，并不得暴露目标客户、项目、路径或对象名称。
3. WHEN 合法关联创建成功，THE Evidence_Governance_System SHALL 支持从源端与目标端查询到相同 EvidenceRef、版本和状态。
4. WHEN 用户查询证据影响范围，THE Evidence_Governance_System SHALL 返回去重后的直接与传递引用，并只包含当前项目、年度及用户有权读取的对象。

### Requirement 5: 持久 OCR 状态机与重试权限（P0）

**User Story:** 作为审计助理，我希望 OCR 在页面刷新或服务重启后仍可追踪，并且失败重试受到权限、幂等和次数限制。

#### Acceptance Criteria

1. WHEN 用户对确定 Attachment_Version 发起 OCR，THE Evidence_Governance_System SHALL 在调度识别前创建持久 OCR_Job，绑定项目、年度、附件版本、Content_Hash、创建主体、解析配置和幂等键。
2. WHILE OCR_Job 存在，THE Evidence_Governance_System SHALL 只允许 `queued→running→awaiting_confirmation→confirmed→written_back`、`queued/running→failed` 和 `failed→queued`，并保存每次状态迁移主体、时间、进度和错误。
3. IF OCR 服务失败、任务超时、调用者无项目访问权或无 OCR 重试权限，THEN THE Evidence_Governance_System SHALL 将任务安全失败或拒绝重试、保留已有结果且不得创建越权执行。
4. WHEN 同一附件版本、Content_Hash 和解析配置被重复提交，THE Evidence_Governance_System SHALL 幂等复用活动或已完成任务，不得重复消费或覆盖历史结果。

### Requirement 6: OCR 结果、人工确认与原子写回（P0）

**User Story:** 作为审计助理，我希望先核对 OCR 来源和差异，再将确认结果一次性写回，避免未核实内容污染底稿。

#### Acceptance Criteria

1. WHEN OCR 成功，THE Evidence_Governance_System SHALL 创建不可变 OCR_Result，为文本或字段保存原始值、置信度、页码、页内区域、引擎、模型版本和解析配置版本。
2. WHEN 人工用户对 OCR 候选字段作出 accepted、corrected 或 rejected 决定，THE Evidence_Governance_System SHALL 同时保留原值、确认值、决定、确认人和确认时间；rejected 字段不得进入目标字段 mapping，Service_Identity 不得执行人工确认。
3. IF 任一 required 字段尚未作出 accepted、corrected 或 rejected 决定，或任一拟写回字段的决定不是 accepted 或 corrected，或目标版本已变化、附件版本已变化、用户无目标编辑权，THEN THE Evidence_Governance_System SHALL 按适用阶段拒绝确认或写回并保持目标无变化。
4. WHEN 已确认 OCR_Result 写回多个目标字段，THE Evidence_Governance_System SHALL 原子提交全部字段和 OCR_Writeback；任一字段失败时回滚全部字段，重复请求不得产生重复效果。

### Requirement 7: RAG 精确引用与可定位性（P1）

**User Story:** 作为质量控制复核人，我希望 AI 回答中的事实能跳转到确切来源版本、页码和区域，并验证引用未失效。

#### Acceptance Criteria

1. WHEN RAG 回答包含事实、金额、日期、条款或判断依据，THE Evidence_Governance_System SHALL 为该内容提供 Citation_Snapshot，至少包含 EvidenceRef、版本、页码、区域、摘录、Content_Hash 和索引版本。
2. IF 来源无法定位、哈希不匹配、EvidenceRef 已停用或用户无来源访问权，THEN THE Evidence_Governance_System SHALL 将该内容标记为不可验证，禁止进入 confirmed AI 内容或 Formal_Output。
3. WHEN 用户打开引用，THE Evidence_Governance_System SHALL 定位到确定来源版本、页码和区域；若该版本不可读取，则显示失效状态并触发 stale 评估。
4. WHEN 文档切片，THE Evidence_Governance_System SHALL 保留页级与区域边界，不得仅以无法回溯原位置的固定字符序号作为正式引用。

### Requirement 8: AI 全入口登记与人工确认硬门禁（P0）

**User Story:** 作为业务合伙人，我希望所有 AI 入口经过同一登记和确认门禁，并能证明不存在绕过入口。

#### Acceptance Criteria

1. WHEN 任一入口生成、改写、摘要或补全 AI_Content，THE Evidence_Governance_System SHALL 在内容可写回前记录 prompt hash、模型、上下文 EvidenceRef、Citation_Snapshot、输出、Content_Hash、服务状态、创建主体和生命周期状态。
2. WHEN CI 扫描后端与前端 AI 入口，THE Evidence_Governance_System SHALL 要求全部入口声明并经过统一登记与确认门禁；发现未登记入口时阻断合并。
3. IF AI_Content 未由人工确认、确认记录不完整、内容哈希变化、任一已有 EvidenceRef 依赖为 stale 或引用不可验证，或缺少适用策略明确声明为必需的证据，THEN THE Evidence_Governance_System SHALL 阻止其进入底稿结论、附注、报告、签发、QC、EQCR、交付件或归档；门禁 SHALL 仅检查策略声明为必需的证据和对象已有依赖，不得仅因历史对象没有附件而自动判为违规，但任何已有或被引用证据仍须满足全部 P0 完整性约束。
4. IF AI 服务不可用、超时或返回 stub，THEN THE Evidence_Governance_System SHALL 明确显示降级状态，禁止自动确认或正式写回，并保留原始业务数据不变。

### Requirement 9: stale 传播与下游阻断（P0）

**User Story:** 作为现场负责人，我希望证据变化后所有依赖对象自动失效，旧证据不能继续完成正式流程。

#### Acceptance Criteria

1. WHEN 附件产生新版本、OCR 确认值被修正、知识文档更新、EvidenceRef 停用、引用哈希失配或 confirmed AI_Content 变化，THE Evidence_Governance_System SHALL 标记直接下游 stale 并传播至项目内依赖闭包。
2. WHILE Controlled_Module 依赖任一 stale 证据，THE Evidence_Governance_System SHALL 显示失效来源与影响路径，并阻止确认、签发、正式导出、QC/EQCR 完成或归档。
3. WHEN 对象使用当前证据版本重新计算、重新定位引用并完成人工确认，THE Evidence_Governance_System SHALL 只清除满足条件对象的 stale 状态并保留历史失效链。
4. WHEN stale 传播执行，THE Evidence_Governance_System SHALL 保证其他项目和年度的对象状态不发生变化。

### Requirement 10: 复核、QC 与 EQCR 证据闭环（P1）

**User Story:** 作为质量控制复核人或EQCR技术复核人，我希望意见提出、回复、关闭和再打开都绑定当前有效证据。

#### Acceptance Criteria

1. WHEN 用户创建复核意见，THE Evidence_Governance_System SHALL 允许关联当前可访问 EvidenceRef，并冻结提出时的证据版本快照。
2. IF 用户关闭 Blocking_Review 时未提供充分关闭说明、至少一个非 stale EvidenceRef 或所需权限，THEN THE Evidence_Governance_System SHALL 拒绝关闭并保留完整历史。
3. WHEN 已关闭意见的证据被替换、停用或标记 stale，THE Evidence_Governance_System SHALL 将意见置为待重新复核，并阻止对应 QC、EQCR 或业务合伙人结论完成。
4. WHEN QC/EQCR 查看证据，THE Evidence_Governance_System SHALL 展示来源版本、哈希、人工确认记录、stale 状态及可定位引用，不得只展示脱离来源的摘录。

### Requirement 11: Archive Manifest 与完整性闭环（P0）

**User Story:** 作为质量控制复核人，我希望归档包完整列出并校验证据版本和治理记录，以便离线证明审计链未被篡改。

#### Acceptance Criteria

1. WHEN 用户请求归档项目，THE Evidence_Governance_System SHALL 生成 Archive_Manifest，覆盖附件版本、EvidenceRef、OCR 任务/结果/确认/写回、Citation_Snapshot、AI_Content、复核记录、stale 链、交付件和保留状态。
2. IF manifest 对适用策略明确声明为必需的证据或对象已有依赖存在缺失，或存在主体缺失、哈希缺失或不匹配、活动 stale、未确认 AI 内容、未确认 OCR 写回、Blocking_Review 或 Legal_Hold 范围不一致，THEN THE Evidence_Governance_System SHALL 阻止归档并仅在此次归档因验证失败被阻断时生成完整 blocking difference report；历史对象没有附件本身不得自动构成违规，但任何已有或被引用证据仍须满足全部 P0 完整性约束。WHEN manifest 校验通过并成功归档，THE Evidence_Governance_System SHALL NOT 生成 blocking difference report。
3. WHEN manifest 校验通过，THE Evidence_Governance_System SHALL 创建不可变归档包，支持离线重算全部哈希，并保证再次归档创建新版本而不覆盖历史包。
4. WHEN 归档完成，THE Evidence_Governance_System SHALL 冻结归档时点的证据关系、确认状态和交付件版本，后续变化不得改写该快照。

### Requirement 12: 审计日志、可观测性与告警（P1）

**User Story:** 作为现场负责人，我希望敏感动作、拒绝事件和治理状态可审计、可度量并及时告警。

#### Acceptance Criteria

1. WHEN 发生附件读取/变更、EvidenceRef 变更、OCR 启动/重试/确认/写回、AI 确认/拒绝、stale 变更、复核关闭、归档或 Legal_Hold 变更，THE Evidence_Governance_System SHALL 对每个敏感命令及其 idempotency key 记录恰好一个 command-root 审计事件，并允许记录零到多个关联该 command-root 的状态迁移事件；事件 SHALL 记录主体、项目、年度、对象版本、动作、结果、追踪 ID、时间和原因，且不得遗漏、重复或因命令重放而重复创建 command-root。
2. IF 发生越界路径、跨项目访问或关联、OCR 重试越权、AI 门禁绕过、哈希不匹配或 Legal_Hold 删除尝试，THEN THE Evidence_Governance_System SHALL 产生安全事件和可聚合指标，且日志不得包含认证凭据或附件原文。
3. WHEN OCR 失败率、排队时长、stale 积压或门禁绕过超过配置阈值，THE Evidence_Governance_System SHALL 生成可关联到原始审计事件的告警。
4. WHILE 审计记录处于保留期或 Legal_Hold，THE Evidence_Governance_System SHALL 禁止修改或删除该记录。

### Requirement 13: 保留期限与 Legal Hold（P0）

**User Story:** 作为业务合伙人，我希望证据按统一期限保留，并在法律保全期间绝不被删除或覆盖。

#### Acceptance Criteria

1. WHEN 项目完成归档，THE Evidence_Governance_System SHALL 应用项目保留策略，并将策略版本写入 Archive_Manifest 与审计日志。
2. WHILE Legal_Hold 生效，THE Evidence_Governance_System SHALL 对其直接与传递关联的附件、EvidenceRef、OCR、RAG、AI、复核、交付件及 manifest 的物理删除、清理和覆盖实行同等严格的零效果禁止；任何角色、管理员、Service_Identity 或紧急授权均不得绕过，内容替换只能创建新版本且不得覆盖受 hold 保护的历史。
3. WHEN 有权限用户解除 Legal_Hold，THE Evidence_Governance_System SHALL 要求原因并保留解除记录；保留期未届满时仍禁止清理。
4. WHEN Legal_Hold 已解除且保留期已届满，THE Evidence_Governance_System SHALL 仅允许具备 `retention.purge` 能力的主体授权清理，保留不可变墓碑记录，并保证不存在悬空活动 EvidenceRef；任一条件不满足时清理效果 SHALL 为 0。

### Requirement 14: 迁移兼容与可恢复回填（P1）

**User Story:** 作为现场负责人，我希望新模型上线时不破坏既有附件调用，也不把未知历史字段伪造成真实证据。

#### Acceptance Criteria

1. WHILE 兼容窗口生效，THE Evidence_Governance_System SHALL 保持既有附件读取标识与响应字段可用，但兼容响应中的 `file_path` 只能返回脱敏 locator、opaque locator 或受控下载 URL，禁止返回绝对路径；所有新附件、新 OCR、新 AI 内容和新 EvidenceRef 必须满足本 spec。
2. WHEN 回填历史记录，THE Evidence_Governance_System SHALL 只补充可由现有记录或原始字节证明的哈希和元数据；无法证明的字段标记不完整，禁止臆造。
3. IF 迁移批次失败、中断或以相同输入重跑，THEN THE Evidence_Governance_System SHALL 从检查点恢复、保持失败记录原状态且不得创建重复版本、引用、任务或写回。
4. WHEN 历史 created_by 无法可靠推导，THE Evidence_Governance_System SHALL 使用明确的迁移 Service_Identity 并保留“原创建者未知”标记，不得冒充人工用户。

### Requirement 15: 性能、容量与安全降级（P1）

**User Story:** 作为现场负责人，我希望证据治理支撑 6000 并发用户，并在外部依赖故障时安全失败。

#### Acceptance Criteria

1. WHERE 运行 6000 并发用户容量测试，THE Evidence_Governance_System SHALL 达到设计阶段确定的元数据读取、影响范围查询和写操作 P95 指标，错误率低于 1%，跨项目泄露数为 0。
2. WHEN 影响范围包含大量节点或归档包含大量文件版本，THE Evidence_Governance_System SHALL 使用有界分页或异步任务，不得阻塞请求线程或无限加载关系图。
3. IF 存储、OCR、知识检索或 AI 依赖不可用、超时或返回不可验证结果，THEN THE Evidence_Governance_System SHALL 保留已有数据、显示降级状态，并禁止生成 confirmed、written_back 或 archived 终态。
4. WHEN 自动重试外部依赖，THE Evidence_Governance_System SHALL 使用有界退避和幂等键，超过上限后进入可人工处理的失败状态。

### Requirement 16: 历史覆盖与持续质量治理（P2）

**User Story:** 作为质量控制复核人，我希望分批提升历史证据覆盖率并持续看到治理质量，而不改变历史原始文件。

#### Acceptance Criteria

1. WHERE 历史增强启用，THE Evidence_Governance_System SHALL 分批处理历史记录，只补充可证明的数据，并保证历史原始字节变化数为 0。
2. WHEN 治理质量面板刷新，THE Evidence_Governance_System SHALL 计算元数据完整率、created_by 完整率、RAG 可定位引用率、OCR 人工修正率、stale 数量及账龄、AI 门禁绕过数和归档校验失败数。
3. IF created_by 完整率低于 100%、RAG 可定位引用率低于 100%、AI 门禁绕过数大于 0 或归档哈希失败数大于 0，THEN THE Evidence_Governance_System SHALL 生成治理问题清单且不得自动修改业务结论。

## 4. Scope Boundaries

### In Scope

- 新上传附件及新版本的安全边界、项目隔离、证据元数据、哈希和责任主体。
- 持久 EvidenceRef、影响范围和附件到各 Controlled_Module 的类型化 adapter。
- OCR Job/Result/Confirmation/Writeback 状态机及人工确认。
- RAG 页码、区域、版本、哈希和 Citation_Snapshot。
- AI 全入口登记、人工确认硬门禁及覆盖守卫。
- 证据变化后的 stale 传播、复核/QC/EQCR 重开与阻断。
- Archive_Manifest、审计日志、可观测性、保留策略和 Legal_Hold。
- 兼容迁移、渐进回填及 6000 并发容量验收。

### Out of Scope

- 不替换现有附件存储后端、OCR 引擎、向量检索引擎、LLM provider 或 Office 编辑服务。
- 不允许 AI 自动形成或签发审计结论。
- 不在本 spec 中实现跨项目、跨客户或跨年度证据复用。
- 不强制一次性人工补齐全部历史业务元数据；未知字段必须显式标记不完整。
- 不改变现有底稿、附注、报告和交付件的业务计算口径。

## 5. Correctness Properties

| Property | Invariant | Requirements |
|---|---|---|
| **P1 项目隔离** | 任意跨项目或跨年度读取、引用、关联均失败，且响应不泄露目标元数据 | R1, R3, R4 |
| **P2 存储边界封闭** | 仅规范化后仍位于 Storage_Boundary 内的路径可读取 | R1 |
| **P3 创建主体完备** | 所有成功的新记录都有人工主体或明确 Service_Identity | R1, R3, R5 |
| **P4 版本不可变** | 任意次数替换后旧版本字节、哈希和创建信息不变，新版本号严格递增 | R2 |
| **P5 哈希绑定** | 相同字节摘要一致，任意内容变化不能通过旧版本哈希校验 | R2, R11 |
| **P6 EvidenceRef 完整性** | 只有项目、年度、目标、版本、哈希及权限全部一致时可创建 | R3 |
| **P7 EvidenceRef 幂等性** | 同一引用意图重复提交只保留一个活动引用和一个反向关系 | R3, R4 |
| **P8 关联双向一致** | 合法关联从两端查询得到相同引用 ID、版本和状态 | R4 |
| **P9 OCR 状态机封闭** | 仅允许定义的状态迁移，非法迁移不改变当前状态或历史 | R5 |
| **P10 OCR 重试授权** | 只有具备项目访问权和重试能力的主体可重试，重复提交不重复执行 | R5 |
| **P11 OCR 原始结果不可变** | 确认、修正和写回不改变原识别值、来源版本、哈希、页码和区域 | R6 |
| **P12 未确认不可写回** | 任一 required 字段未决定，或任一拟写回字段不是 accepted/corrected 时，目标对象变化量恒为 0；rejected 字段永不进入 mapping | R6 |
| **P13 OCR 写回原子性** | 任一字段失败时全部字段保持旧值，成功时全部等于确认值 | R6 |
| **P14 OCR 写回幂等性** | 同一写回重复调用只产生一次业务效果和一个成功记录 | R6 |
| **P15 RAG 引用可定位** | confirmed 引用必须页码有效、区域非空、版本与哈希匹配 | R7 |
| **P16 RAG 权限不扩张** | 返回引用集合始终是当前主体可访问来源集合的子集 | R7 |
| **P17 AI 状态门禁** | 仅人工确认、内容哈希一致，且策略声明为必需的证据与对象已有依赖均有效的 AI 内容可进入 Formal_Output；历史对象无附件本身不构成违规 | R8 |
| **P18 AI 入口覆盖** | AI 入口扫描集合与门禁声明集合差集恒为空 | R8 |
| **P19 已确认内容变更失效** | confirmed 内容或任一依据变化后回到 draft/stale，原确认不再授权输出 | R8, R9 |
| **P20 stale 传递闭包** | 实际 stale 集合精确等于变化源在同一项目、同一年度“统一依赖图”中的可达下游闭包；统一图由活动 EvidenceDependency 边与经规范化纳入的 ACNR/legacy 边的并集构成，不得以任一单表闭包替代 | R9 |
| **P21 复核关闭门禁** | Blocking_Review 仅在权限、说明和有效证据同时满足时关闭 | R10 |
| **P22 复核自动重开** | 已关闭意见的依据失效后进入待重新复核并阻断 QC/EQCR | R10 |
| **P23 manifest 完备性** | manifest 对象与关系集合精确等于归档范围内策略声明为必需的证据及对象已有依赖所形成的可达证据图；历史对象无附件本身不扩大该图，已有证据的 P0 完整性不放宽 | R11 |
| **P24 manifest 防覆盖** | 重复归档始终创建新包，历史包字节和清单保持不变 | R11 |
| **P25 审计事件覆盖** | 对每个敏感命令及其 idempotency key，恰好存在一个脱敏的 command-root 审计事件，并允许零到多个可关联的状态迁移事件；命令执行与重放均不得漏记、重复记录 command-root，事件不得包含凭据或附件原文 | R12 |
| **P26 Legal Hold 单调保护** | hold 期间删除、清理和覆盖三类操作对任何授权级别均为零效果且无紧急绕过，替换只能新增版本 | R13 |
| **P27 保留期边界** | 只有 hold 已解除、保留期届满、主体获授权且无悬空活动引用时才允许清理 | R13 |
| **P28 迁移幂等守恒** | 迁移重跑不增加逻辑对象数量，不改变历史原始字节和业务内容 | R14 |
| **P29 降级安全** | 外部依赖失败时不产生 confirmed、written_back 或 archived 终态 | R15 |
| **P30 质量指标可复算** | 固定数据快照重复计算得到完全相同的指标、账龄桶和问题清单 | R16 |

## 6. UAT Scenarios

1. **UAT-01 附件安全接收**：上传合法、超限、类型不符和主体缺失附件，确认每次尝试都先形成最小 UploadAttempt 审计，只有合法附件形成可用记录并带完整责任主体和哈希；失败尝试保留 outcome 但无可用 Attachment/Version 或可访问恶意文件。
2. **UAT-02 越界读取阻断**：构造 Storage_Boundary 外路径，确认系统在读取字节前拒绝且不泄露路径或文件存在性。
3. **UAT-03 跨项目关联阻断**：尝试把项目 A 附件关联到项目 B 底稿，确认关联数不变且响应不暴露 B 的信息。
4. **UAT-04 附件版本与影响范围**：替换被底稿、附注和报告引用的附件，确认生成新版本、旧版本不变、下游 stale。
5. **UAT-05 EvidenceRef 持久化**：创建引用后重启服务，确认引用 ID、版本、哈希和双向查询保持一致。
6. **UAT-06 OCR 状态恢复**：OCR running 时刷新页面并重启服务，确认同一 Job 与状态历史仍可查询。
7. **UAT-07 OCR 人工确认与写回**：修正低置信度字段，确认后原子写回；制造目标版本冲突时确认无部分更新。
8. **UAT-08 OCR 重试权限**：无权限用户重试失败任务被拒绝，有权限用户可按幂等规则重试。
9. **UAT-09 RAG 精确引用**：逐条打开事实引用并定位到正确版本、页码和区域；替换来源后旧引用失效。
10. **UAT-10 AI 全入口门禁**：从底稿、附注、报告和复核入口生成 draft，确认未经人工确认均不能进入正式目标。
11. **UAT-11 QC/EQCR 再复核**：关闭关键意见后替换其证据，确认意见重新打开且 QC/EQCR 完成被阻断。
12. **UAT-12 归档完整性**：制造缺失哈希、活动 stale 和未确认 AI，确认归档失败；修复后离线重算全部哈希通过。
13. **UAT-13 Legal Hold**：hold 生效后以普通授权、管理员和紧急授权分别尝试删除附件、清理 OCR 和覆盖归档包，确认三类操作全部零效果且无绕过；仅在 hold 解除且 retention 届满后，授权清理才可执行。
14. **UAT-14 迁移兼容**：同一历史回填批次重复执行并模拟中断，确认无重复对象、旧读取接口可用、未知字段不被臆造。
15. **UAT-15 容量与降级**：运行 6000 并发容量场景并中断 OCR、检索和 AI 依赖，确认零跨项目泄露且无降级结果进入正式终态。

## 7. Dependencies

- 依赖 `platform-evidence-knowledge-ai-governance` 的治理边界与现有 EvidenceRef DTO。
- 依赖 `retrieval-kernel-unification` 的统一检索内核、权限过滤和索引 stale 能力。
- 依赖 `platform-linkage-contract-stale`、`v3-linkage-stale-propagation` 与 ACNR 的影响图和失效传播能力。
- 依赖 `audit-report-deliverable-center` 及现有交付件版本链和归档能力。
- 依赖平台权限矩阵、项目成员校验、复核会话、附件服务、统一 OCR 服务和 AI 内容日志。
- 被底稿编制、抽样、凭证检查、函证、附注、报告、签发、QC、EQCR 和归档流程依赖。

## 8. Priority and Release Gates

- **P0**：R1–R6、R8、R9、R11、R13。任一跨项目泄露、边界外读取、匿名新记录、未确认 OCR 写回、未确认 AI 正式落地、Legal Hold 违规删除或归档哈希不一致均一票否决。
- **P1**：R7、R10、R12、R14、R15。要求可定位引用、复核闭环、审计覆盖、迁移幂等和容量验收全部通过；UAT-15 对应验证 R15 与 P29。
- **P2**：R16。P2 不阻断 P0/P1 上线；历史增强启用前，必须以预先固定且不可变的治理数据快照单独验收 P30，P30 不与 UAT-15 绑定。
- 本 spec 只有在 P0/P1 全部验收标准、P1–P29 属性及 UAT-01 至 UAT-15 通过后，才可进入归档评审；P30 按上述独立门禁在历史增强启用前验收。
