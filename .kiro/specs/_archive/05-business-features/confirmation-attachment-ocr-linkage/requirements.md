# Requirements Document

## Introduction

把函证中心从"台账 + 状态机 + 割裂的附件/OCR 零件"升级为**完整回函证据链**：发函件上传 → 回函扫描件上传 → OCR 识别回函金额/日期/主体 → 与账面数比对 → 自动匹配到对应发函记录 → 人工确认后回写台账（回函金额/状态/差异）；且状态点错可撤回（带审计留痕）。

**现状盘点（代码核实，作为改造基线）**：

- 状态机 `confirmation_service._ALLOWED_TRANSITIONS` 严格单向 `pending(待发函)→sent(已发函)→returned(已回函)→matched(相符)/discrepancy(差异)`，`matched/discrepancy` 是终态空集，**无任何反向转换**；点错只能删除整条重建。
- `Confirmation` 表字段：project_id / confirm_type / counterparty / status / wp_id / account_code / book_amount / confirmed_amount / diff_amount / diff_note / created_by + created_at/updated_at。**无发函日期、回函日期、附件关联字段**。
- `Attachment` 表已支持函证附件：`attachment_type='confirmation'` + `reference_type='confirmation_list'` + `reference_id`，含 `ocr_status` / `ocr_text` / `ocr_fields_cache`。
- `AttachmentService.extract_confirmation_reply` 已能从回函 OCR 文本正则抽取回函金额/日期/主体 + 置信度，但恒标 `governed=False` / `requires_human_confirmation=True`（辅助线索，不自动落库），且**不与具体函证记录比对/匹配/回写**。
- `ConfirmationHub.vue` 台账已与编制底稿双向同步（`syncHubFromSummary`），但**附件、OCR、台账三者未挂钩**。

**核心目标**：底座零件（confirmation 表 / attachment confirmation 类型 / extract_confirmation_reply OCR / 台账状态机）已备，本 spec 把它们串成闭环并补齐撤回能力，全程遵守「AI/OCR 结果仅辅助、人工确认后才落库」的审计红线。

**边界（不在本 spec 范围）**：
- 不改 OCR 抽取算法本身（`extract_confirmation_reply` 正则逻辑保持，仅新增比对/匹配/回写编排层）。
- 不改编制底稿 → 台账的 `syncHubFromSummary` 现有同步逻辑（仅在其之上叠加附件/OCR 链）。
- 不改附件的存储/上传底层（Paperless/本地）与安全网关，仅复用 `attachment_type=confirmation` 的 reference 挂载。
- 律师函（A12-1）、诉讼（K5）等**底稿内**的发函/回函小节不动，本 spec 只做**函证中心台账级**的证据链。
- 不引入外部函证平台 API 对接（统一发函/收函）；本期只做所内手工上传 + OCR + 匹配闭环。

## Glossary

| 术语 | 含义 |
|------|------|
| 函证台账 | `confirmations` 表 + `ConfirmationHub.vue`，函证中心统一台账，每条含账面数/回函金额/状态 |
| 发函件 | 寄出的询证函本身（草稿/已签发影像），作为函证已发出的证据 |
| 回函件 | 对方寄回的确认回函扫描件/照片/PDF，作为回函结果的原始影像证据 |
| 附件角色 | 附件相对某笔函证的角色：发函件（outbound）/ 回函件（inbound），用于区分 |
| 状态机 | `_ALLOWED_TRANSITIONS`，pending→sent→returned→matched/discrepancy 单向推进 |
| 撤回 | 把函证状态回退到上一合法状态（如 sent→pending、returned→sent、matched→returned），带审计留痕 |
| OCR 抽取 | `extract_confirmation_reply` 从回函件 OCR 文本抽回函金额/日期/主体 + 置信度（high/medium/low） |
| 账面数 | `Confirmation.book_amount`，发函时登记的账面余额，回函比对基准 |
| 回函金额 | `Confirmation.confirmed_amount`，对方确认的金额（OCR 抽取或人工录入，人工确认后落库） |
| 差异 | `diff_amount = book_amount − confirmed_amount`，非零即"不符" |
| 自动匹配 | 上传的回函件按 对方名称 / 函证编号 / 金额 匹配到台账中的发函记录 |
| 人工匹配队列 | 自动匹配失败或多义时，回函件进入待人工指派的队列 |
| 审计留痕 | 撤回、回填、匹配等关键动作的操作日志（谁、何时、从什么到什么、依据附件） |
| 回函影像 | 台账中直接查看/预览关联回函件原始扫描件 |

## Requirements

### Requirement 1: 函证状态可撤回（反向转换 + 审计留痕）

**User Story:** 作为审计助理/现场经理，当我把某笔函证状态点错时（例如误点"已发函"或"相符"），我希望能撤回到上一状态，而不必删除整条重建，以免丢失已登记的账面数/附件/回函信息。

#### Acceptance Criteria

1. WHEN 用户对某笔函证请求撤回 THEN 系统 SHALL 允许把状态回退到其在状态机上的**上一合法状态**（sent→pending、returned→sent、matched→returned、discrepancy→returned）。
2. WHEN 撤回终态（matched/discrepancy → returned）THEN 系统 SHALL 允许，使"相符/差异"点错可改判。
3. WHEN 状态为 pending（待发函）时请求撤回 THEN 系统 SHALL 拒绝并提示"已是初始状态，无法再撤回"（不存在 pending 之前的状态）。
4. WHEN 执行撤回 THEN 系统 SHALL 写入审计留痕（操作人、时间、从状态、到状态、撤回原因可选、关联函证），且该留痕不可篡改。
5. WHEN 撤回涉及已回填的回函金额/差异（如 returned→sent 或 matched→returned）THEN 系统 SHALL 在撤回前提示"该操作将影响已登记的回函金额/差异，是否继续"，用户确认后方执行，且留痕记录被清除/保留的字段。
6. WHERE 用户无相应权限 THE 系统 SHALL 拒绝撤回并返回权限错误（权限矩阵见 Requirement 8）。
7. WHEN 撤回成功 THEN 系统 SHALL 复用现有事件机制，使下游（编制底稿摘要卡/勾稽）与台账刷新保持一致（撤回同样是状态变化）。

### Requirement 2: 补齐发函日期 / 回函日期 / 附件角色字段

**User Story:** 作为审计人员，我希望函证台账能记录发函日期、回函日期，并区分发函件与回函件附件，以便完整呈现函证寄发—回收时间线和证据。

#### Acceptance Criteria

1. THE 系统 SHALL 为函证记录提供"发函日期"与"回函日期"，可在台账登记与展示。
2. WHEN 状态推进到 sent（已发函）THEN 系统 SHALL 允许登记/自动带入发函日期；WHEN 推进到 returned（已回函）THEN 系统 SHALL 允许登记/自动带入回函日期。
3. THE 系统 SHALL 支持把一个附件标注为某笔函证的"发函件"或"回函件"角色。
4. WHEN 附件角色为回函件 THEN 系统 SHALL 使其可作为 OCR 识别与比对的来源（Requirement 4）。
5. WHERE 历史函证记录无发函/回函日期与附件角色 THE 系统 SHALL 以空值/默认角色兼容展示，不报错（向后兼容，见 Requirement 9）。

### Requirement 3: 台账记录 ↔ 附件双向挂钩

**User Story:** 作为审计人员，我希望在函证中心台账里直接看到某笔函证挂了哪些发函件/回函件，并能上传、查看、解绑，而不必去独立的附件管理页来回切换。

#### Acceptance Criteria

1. WHEN 在台账某笔函证上上传附件 THEN 系统 SHALL 以 `attachment_type=confirmation` + `reference_type=confirmation_list` + `reference_id=该函证id` 关联，并记录附件角色（发函件/回函件）。
2. WHEN 查看某笔函证 THEN 系统 SHALL 列出其关联的全部发函件与回函件（文件名、上传时间、角色、OCR 状态）。
3. WHEN 用户解除某附件与函证的关联 THEN 系统 SHALL 仅解绑（清 reference）而不物理删除附件，且留痕。
4. WHEN 台账查询函证列表 THEN 系统 SHALL 能高效批量返回每笔的附件计数（发函件数/回函件数），避免逐条 N+1 查询。
5. WHERE 一笔函证有发函件与回函件 THE 系统 SHALL 支持一笔函证挂**多份**回函件，且**每份回函件必须绑定到该函证下具体某一份发函件**（强配对）；无发函件时不得单独挂回函件（须先有发函件），保证"哪封回函对应哪封发函"可追溯。
6. WHEN 一笔函证仅有单份发函件且新增回函件 THEN 系统 SHALL 默认将回函件绑定到该唯一发函件；WHEN 有多份发函件 THEN 系统 SHALL 要求用户指定回函件对应的发函件。

### Requirement 4: 回函扫描件 OCR 识别与账面数比对

**User Story:** 作为审计人员，我上传回函扫描件后，希望系统自动 OCR 识别回函金额/日期/主体，并与该笔函证的账面数比对给出相符/不符及差异，作为我判断的辅助线索。

#### Acceptance Criteria

1. WHEN 上传回函件并触发识别 THEN 系统 SHALL 调用现有 `extract_confirmation_reply` 抽取回函金额、回函日期、回函主体及置信度（high/medium/low）。
2. WHEN 抽取出回函金额且该函证有账面数 THEN 系统 SHALL 计算 `diff = book_amount − 抽取回函金额` 并给出相符（diff≈0，含容差）/ 不符（diff≠0）判定。
3. WHEN 抽取出回函主体名称 THEN 系统 SHALL 与函证 `counterparty` 比对，名称不一致时给出预警提示（可能寄错/盖章主体不符）。
4. THE 系统 SHALL 把 OCR 抽取结果与比对结论标记为"AI 辅助 · 待人工确认"（`governed=False`/`requires_human_confirmation=True`），在人工确认前**不得**自动写入台账的正式 confirmed_amount/status。
5. WHERE OCR 文本为空或置信度为 low THE 系统 SHALL 如实呈现低置信度，提示需人工逐份核对原始影像，不产生误导性"相符"结论。
6. WHEN 判定相符/不符 THEN 系统 SHALL 用金额容差，**默认 ±0.01 元**（绝对值），`|book_amount − confirmed_amount| ≤ 容差` 判相符，否则不符；容差口径可配置，缺省即 ±0.01 元。

### Requirement 5: OCR 结果人工确认后一键回填台账

**User Story:** 作为审计人员，核对完 OCR 识别的回函金额/日期无误后，我希望一键把它们回填到该笔函证台账（回函金额、回函日期、差异、状态），不用手工重敲。

#### Acceptance Criteria

1. WHEN 用户对某回函件的 OCR 抽取结果点"确认回填" THEN 系统 SHALL 把回函金额写入 `confirmed_amount`、回函日期写入回函日期字段，并计算 `diff_amount`。
2. WHEN 回填后差异为零（含容差）THEN 系统 SHALL 建议状态置为 matched（相符）；WHEN 差异非零 THEN 建议置为 discrepancy（差异），最终状态由用户确认。
3. THE 系统 SHALL 仅在用户显式确认后回填，OCR 结果本身绝不自动落库（呼应 Requirement 4.4）。
4. WHEN 回填成功 THEN 系统 SHALL 记录审计留痕（依据哪个回函件、OCR 原值、人工是否修正、最终落库值）。
5. WHEN 用户在回填前修正了 OCR 抽取的金额/日期 THEN 系统 SHALL 以人工修正值落库，并在留痕中同时保留 OCR 原值与人工修正值。
6. WHERE 该函证已被撤回或状态回退 THE 回填动作 SHALL 与状态机一致（不允许对已锁定/不匹配状态强行回填，给出提示）。

### Requirement 6: 回函自动匹配发函记录 + 人工匹配队列

**User Story:** 作为审计人员，当我批量上传一堆回函扫描件时，希望系统按对方名称/函证编号/金额自动匹配到台账中对应的发函记录，匹配不上的进人工队列，让我逐个指派。

#### Acceptance Criteria

1. WHEN 上传回函件并请求自动匹配 THEN 系统 SHALL 用 OCR 抽取的回函主体名称、金额（及可选函证编号）与台账中 status∈{sent, returned} 的发函记录匹配。
2. WHEN 唯一命中一条发函记录 THEN 系统 SHALL 把回函件挂到该函证（角色=回函件）并按 Requirement 3.6 绑定到其发函件（单份发函件自动绑定、多份要求指定），标记为待确认回填（不自动落库）。
3. WHEN 匹配到多条候选（多义）THEN 系统 SHALL 不自动挂载，列出候选供人工选择。
4. WHEN 匹配失败（无命中）THEN 系统 SHALL 把回函件放入人工匹配队列，供用户手工指派到某笔函证。
5. THE 系统 SHALL 对匹配采用可解释的键（名称精确/模糊 + 金额容差 + 编号），并在结果中标注命中依据与置信度。
6. WHEN 人工从队列指派回函件到某函证 THEN 系统 SHALL 完成挂载并记录留痕（原为自动匹配失败，人工指派）。

### Requirement 7: 台账查看原始回函影像

**User Story:** 作为审计人员/复核人，我希望在函证中心台账直接预览/下载某笔函证的原始回函影像，作为复核证据，而不用去别处找文件。

#### Acceptance Criteria

1. WHEN 在台账某笔函证上点查看回函影像 THEN 系统 SHALL 提供关联回函件的预览/下载入口（复用现有附件预览/下载能力）。
2. WHEN 一笔函证有多个回函件 THEN 系统 SHALL 全部列出并可分别预览。
3. WHERE 附件经安全网关脱敏（opaque locator）THE 预览/下载 SHALL 复用现有安全通道，不泄露原始存储路径。
4. WHEN 用户无查看权限 THEN 系统 SHALL 拒绝并提示（与附件模块既有权限一致）。

### Requirement 8: 权限与审计留痕

**User Story:** 作为质控/复核人，我希望撤回、回填、匹配指派等改变审计结论的动作受权限约束且全程留痕，保证证据链可追溯、责任可界定。

#### Acceptance Criteria

1. THE 系统 SHALL 允许审计助理/现场经理执行上传附件、OCR 识别、请求自动匹配、请求回填等操作。
2. WHERE 撤回终态（matched/discrepancy → returned）或回填改变最终结论 THE 系统 SHALL 至少要求现场经理及以上权限（撤回相邻非终态可放宽，具体分层在 design 定并保持与平台权限矩阵一致）。
3. THE 系统 SHALL 对撤回、回填、匹配指派、附件解绑等关键动作写入不可篡改的审计留痕（操作人、时间、动作、前后值、依据附件 id）。
4. WHEN 任何留痕写入失败 THEN 系统 SHALL 不因留痕失败而阻断主动作，但须记录告警（best-effort，不静默丢失）。
5. THE 审计留痕 SHALL 可供复核视图/追溯查询。

### Requirement 9: 零回归与向后兼容

**User Story:** 作为平台维护者，我希望本次改造不破坏现有函证台账、编制底稿同步、附件模块的既有行为。

#### Acceptance Criteria

1. WHEN 未使用新功能（不挂附件/不 OCR/不撤回）THEN 现有创建/编辑/删除/单向状态推进/批量同步/统计端点行为 SHALL 逐字节等价。
2. WHERE 历史函证记录无发函/回函日期、无附件角色、无关联回函件 THE 台账 SHALL 正常展示（空值/默认），不报错。
3. THE 现有 `syncHubFromSummary`（编制底稿 → 台账）与 `apply_confirmation_result`（回函下游 stale 传播）SHALL 保持行为不变；新增撤回同样应触发一致的下游刷新。
4. THE `extract_confirmation_reply` OCR 抽取算法 SHALL 不变，本 spec 仅在其上叠加比对/匹配/回填编排层。
5. WHERE 需要数据库结构变更（新增字段/审计留痕表）THE 变更 SHALL 为 additive（新增可空字段/新表），不改既有列语义，且迁移幂等（information_schema 守护）。
6. THE 新增迁移版本号 SHALL 在实现时以 `migration_status`/磁盘最高号复核后确定，避免与并发 spec 冲突。

### Requirement 10: 正确性属性（可测）

**User Story:** 作为开发者，我希望核心规则以属性化测试锁定，防止回归。

#### Acceptance Criteria

1. THE 撤回 SHALL 满足：允许回退到任一更早合法状态（含一步退到底至 pending），回退目标必须严格早于当前状态，pending 不可再撤回，前进/同级方向不属撤回。
2. THE 差异计算 SHALL 满足：`diff = book_amount − confirmed_amount`，容差内判相符、容差外判不符，任一侧缺失不产生虚假相符。
3. THE 回填 SHALL 满足：非用户确认不落库；人工修正值优先于 OCR 原值；留痕同时保留 OCR 原值与最终值。
4. THE 自动匹配 SHALL 满足：唯一命中才自动挂载，多义/无命中不自动落库；匹配键与命中依据可解释。
5. THE 向后兼容 SHALL 满足：新增字段/表为 additive；未用新功能时既有端点结果不变（characterization 基线锁定）。
6. THE 权限 SHALL 满足：低权限执行受限动作被拒，动作全程留痕。
