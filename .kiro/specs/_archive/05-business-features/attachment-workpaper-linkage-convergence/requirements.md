# Requirements Document

## Introduction

附件（证据）与底稿之间的关联当前存在**多套并行、口径分叉**的机制，导致「本底稿关联了哪些附件」这一基本问题没有单一权威答案：不同入口写入不同的存储，各自的反查/统计彼此看不见对方的数据。本 spec 收敛这些分叉为**单一权威关联真源**，并在此基础上补齐三项联动能力（底稿驱动证据收集、OCR 双轨归一、失效提示前置）。

本 spec 承接已完成的两项快赢（不在本 spec 范围、作为既有事实）：
- **C（已完成）**：附件管理页消费 `?id=` 深链高亮定位（GtIndexChip Layer-4 跳转）。
- **B（已完成）**：底稿编辑器工具栏「关联附件」抽屉，只读复用反查端点 `GET /api/working-papers/{wp_id}/attachments`（读 `attachment_working_paper` 链表）。

### 实证现状（不可臆造，代码实测）

平台存在**至少三套**"附件↔底稿"关联机制，写入不同存储：

1. **evidence-governance associate**（`POST /api/attachments/{id}/associate` → `attachment_service.associate_with_wp`）：写 **`attachment_working_paper`** 链表（M:N，带 `association_type` evidence/support/confirmation/…、`notes`）。B 抽屉的反查 `get_wp_attachments` 只读这张表。
2. **process-record linkAttachment**（`POST /api/process-record/link-attachment` → `AttachmentLinkService.link_attachment_to_workpaper`）：直接 `UPDATE attachments SET reference_type='working_paper', reference_id=:wp_id`（**1:1 覆盖**，无 association_type，无 M:N）。**此路径关联的附件对 evidence-governance 反查/B 抽屉完全不可见**。
3. **函证附件**（`confirmation_attachments` / `confirmation_attachment_link` 表）：函证回函影像走独立链路（不在本 spec 收敛范围，作为专属证据链保留，仅要求可被统一反查视图纳入呈现）。
4. **检查项级 ItemAttachment**：走 `GET /api/projects/{pid}/attachments?attachment_type=…` 按类型/标题过滤（非稳定关联，靠 title 约定）。

实测 `attachment_working_paper` 与 process-record `reference_id` 两套数据当前均近空/分散 → 各底稿反查口径不一致、"已关联底稿"统计只算其中一套。

### 范围边界

- 收敛 **1（associate 链表）** 与 **2（process-record reference_id）** 为单一权威关联真源；**3（函证）** 仅要求纳入统一反查**视图**（只读），不改其编制链路。
- **4（检查项级 ItemAttachment）**：本 spec **不纳入**统一反查 join（靠 title 过滤、无稳定关联键）；前端来源枚举可预留 `checklist`，Wave 2 不实现该来源。
- 不改附件存储底层、不改附件安全通道（opaque locator / 安全网关）、不改 OCR 识别算法本身。
- 迁移一律 additive + 向后兼容；灰度可回退。

## Glossary

| 术语 | 含义 |
|------|------|
| 权威关联真源 | 收敛后「附件↔底稿」关联的唯一权威存储（本 spec 定为 `attachment_working_paper` M:N 链表） |
| associate 链表 | `attachment_working_paper`（M:N，带 association_type/notes），evidence-governance 关联写入 |
| reference 关联 | `attachments.reference_id/reference_type='working_paper'`（1:1 覆盖），process-record linkAttachment 写入 |
| 反查端点 | `GET /api/working-papers/{wp_id}/attachments`，列出关联到某底稿的附件 |
| 统一反查视图 | 融合 associate 链表 + reference 关联（+ 函证/检查项来源标注）后的单一附件列表 |
| 证据类型声明 | 底稿声明「本底稿应收集哪些类型证据」的元数据（底稿驱动证据收集用） |
| OCR 双轨 | 附件页 OCR（`attachments.ocr_text`/`extract_confirmation_reply`）与底稿页 OCR（`/d4/contract-ocr` 等）两条独立识别路径 |
| stale 失效 | 证据/底稿变更后下游标记为过期（`is_stale`），当前仅在治理中心可见 |

## Requirements

### Requirement 1: 单一权威关联真源（收敛 associate 与 reference 双写）

**User Story:** 作为审计人员，我希望「本底稿关联了哪些附件」有唯一权威答案，不因关联入口不同而看不见彼此的数据。

#### Acceptance Criteria

1. WHEN 通过 process-record `linkAttachment` 关联附件到底稿 THEN 系统 SHALL 同时写入权威关联真源（`attachment_working_paper` 链表），使该关联对反查端点/B 抽屉/evidence-governance 均可见。
2. WHEN 通过 evidence-governance `associate` 关联附件到底稿 THEN 关联 SHALL 写入同一权威真源（保持现状）。
3. WHERE 存量数据仅存在于 `attachments.reference_id/reference_type='working_paper'`（旧 process-record 关联）THE 系统 SHALL 提供幂等回填脚本将其补入权威链表（带备份、可回滚、幂等）。
4. WHEN 反查端点 `get_wp_attachments` 执行 THEN 系统 SHALL 返回权威链表 ∪ 兼容读取 reference 关联（去重），使新旧两套关联都可见。
5. IF 关联真源写入失败 THEN 系统 SHALL fail-open（不阻断原有 process-record/associate 主流程），记录 warning。

### Requirement 2: 统一反查视图（纳入函证/检查项来源标注）

**User Story:** 作为审计人员，我希望在底稿关联附件面板看到该底稿全部相关证据，并知道每份证据来自哪条链路。

#### Acceptance Criteria

1. WHEN 展示底稿关联附件 THEN 每份附件 SHALL 标注来源（关联证据 / 底稿引用 / 函证回函；`checklist` 枚举预留、本 spec 不产出）。
2. WHERE 附件通过函证链路（confirmation_attachment_link）绑定到底稿对应函证 THE 统一反查视图 SHALL 以只读方式纳入呈现（不改函证编制链路）。
3. WHEN 统一反查视图返回 THEN SHALL 使用 envelope `{ items: [...] }`（既有字段保留于 items 行内）并附加 additive `source`/`sources`/`association_type`；既有消费者兼容读取 list 或 `items`（前端已双兼容）。

### Requirement 3: 底稿关联附件面板可解除关联（B 面板闭环）

**User Story:** 作为审计人员，我希望在底稿关联附件面板不仅能看，还能解除错误关联。

#### Acceptance Criteria

1. WHEN 在底稿关联附件面板对某附件执行「解除关联」THEN 系统 SHALL 从权威链表**删除该 (attachment, wp) 链行**（硬删链表行；不删附件本身；无软删列）。
2. IF 附件是通过 reference 关联绑定 THEN 解除 SHALL 同步清除 reference 关联（reference_id/reference_type 置空）。
3. WHERE 当前用户无编辑权限 THE 解除关联入口 SHALL 隐藏且后端拒绝（权限双层）。
4. WHEN 解除关联成功 THEN 面板 SHALL 刷新列表反映变更。

### Requirement 4: 底稿驱动证据收集（声明所需证据 + 缺证据提示）

**User Story:** 作为审计人员，我希望底稿能告诉我「本底稿应收集哪些证据」，并在缺失时提示，而不是被动等我想起来上传。

#### Acceptance Criteria

1. WHERE 某底稿类型定义了证据类型声明（如凭证检查表需记账凭证影像、函证需回函件）THE 系统 SHALL 在底稿关联附件面板展示应收集的证据类型清单。
2. WHEN 某声明的证据类型尚无关联附件 THEN 面板 SHALL 显式提示「缺 XX 证据」（不阻断编制，仅提示）。
3. WHERE 底稿类型未定义证据类型声明 THE 面板 SHALL 正常展示已关联附件，无缺证据提示（不臆造声明）。
4. WHEN 证据类型声明数据缺失或加载失败 THEN 系统 SHALL fail-open 只展示已关联附件。

### Requirement 5: OCR 双轨归一（识别结果回流同一证据链）

**User Story:** 作为审计人员，我希望无论从附件页还是底稿页发起 OCR，识别结果都沉淀到同一份附件证据上，不产生两份割裂的识别结果。

#### Acceptance Criteria

1. WHEN 底稿页对某关联附件发起 OCR（**本 spec 试点：`/d4/contract-ocr` 与 `/f2/contract-ocr`**；其余循环 OCR 列 backlog）THEN 识别文本/字段 SHALL 回流到该附件记录（`ocr_text`/`ocr_fields_cache`），与附件页 OCR 同源。
2. WHERE OCR 抽取的结构化字段用于底稿取数 THE 系统 SHALL 保持既有「人工确认后落库」闸门（`governed=False`/`requires_human_confirmation=True`），不自动落库。
3. WHEN 附件已有 OCR 结果 THEN 底稿页 OCR 入口 SHALL 可复用既有结果（避免重复识别），审计师可选择重新识别。
4. WHERE 附件无对应记录（临时上传未关联）THE OCR 行为 SHALL 保持现状不变（不强制关联）。

### Requirement 6: 失效（stale）提示前置到底稿/复核日常视图

**User Story:** 作为审计人员/复核人，我希望证据或底稿变更导致的失效提示出现在我日常工作的底稿页/复核页，而不是只藏在进阶的证据链治理中心。

#### Acceptance Criteria

1. WHERE 某底稿关联的证据/依赖被标记 stale THE 底稿关联附件面板 SHALL 展示失效提示（只读，指向治理中心查看详情）。
2. WHEN 底稿存在 stale 关联 THEN 提示 SHALL 分级（有明确失效来源 vs 保守全量）呈现，避免噪声。
3. WHERE 无 stale 关联 THE 面板 SHALL 不展示失效提示。
4. WHEN stale 数据加载失败 THEN 系统 SHALL fail-open 不展示提示（不阻断面板）。

### Requirement 7: 零回归与向后兼容

**User Story:** 作为平台维护者，我希望收敛不破坏任何既有关联入口与消费者。

#### Acceptance Criteria

1. WHERE 既有代码调用 evidence-governance associate / process-record linkAttachment / 反查端点 THE 收敛后 SHALL：**签名与既有字段键名兼容**；可见附件集合可增（reference/函证纳入）；associate 幂等去重为 Wave 0 有意行为变更（characterization 已锁）；反查响应可从裸 list 升级为 `{ items }` envelope（消费者已双兼容）。
2. WHEN 收敛写入权威真源 THEN SHALL 为 additive（不删旧存储，reference 关联保留供兼容读取）。
3. WHERE 迁移脚本执行 THE SHALL 幂等（重跑无副作用）+ 带备份表 + 支持回滚。
4. WHEN 各 Requirement 增量落地 THEN SHALL 分波可回退（单波独立可发布）。

### Requirement 8: 属性化可测

**User Story:** 作为平台维护者，我希望收敛与联动的正确性有可测属性守卫。

#### Acceptance Criteria

1. WHEN 编写测试 THEN SHALL 覆盖：双写幂等（P：associate+linkAttachment 同一 (att,wp) 不产生重复权威关联）、反查去重（P：链表∪reference 去重后无重复）、来源标注正确、解除关联幂等、缺证据提示只对有声明的底稿触发、OCR 回流同源、stale fail-open、既有消费者零回归。
