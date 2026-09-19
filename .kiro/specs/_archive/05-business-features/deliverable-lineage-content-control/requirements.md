# Requirements Document

## Introduction

交付模块（`DeliverableCenter` → `OnlyOfficeEditor`）在线编辑审计报告正文/附注 docx 时，右侧「数据溯源」面板（`LineagePanel`）依赖把光标所在章节解析成 `section_code` 后调 `/trace` 端点查数据来源。当前实现存在两个根本问题：

1. **「溯源当前章节」按钮原本是坏的（真 bug，已在前置改动中降级修复）**：`OnlyOfficeEditor` 曾调 `editorInstance.executeMethod('GetAllBookmarks', …)`，但 `executeMethod` **不是 DocEditor 实例的方法**——它属于 `editorInstance.createConnector()` 返回的连接器对象；每次点击必抛 `TypeError` 被 `try/catch` 吞掉，从未成功溯源。且即便修好 API，代码取 `bookmarks[0]`（注释自认「简化 MVP」）拿的是文档**第一个** `sec_` 书签，不是光标所在节，语义误导。

2. **无法可靠得知「光标所在章节」**：OnlyOffice 的 **bookmark** 没有「光标落在哪个书签内」的查询 API，因此无论用什么方式都无法用 bookmark 做到「跟随光标溯源」。

**前置已落地（本 spec 的降级基线，不在本 spec 范围内重做）**：已把坏按钮降级为 `LineagePanel` 内的**手动章节号溯源输入**（审计师输入/选择章节号如「五、1」即调 `/trace`，不依赖任何 OnlyOffice 连接器，必然可用），并合并了冗余的两个溯源按钮、修正了误导提示、删除了死 prop。

**本 spec 目标**：把交付 docx 生成时每节内容包成 **Block Content Control（内容控件，Tag=`sec_{section_code}`）**，前端用 OnlyOffice **连接器**的 `onChangeContentControl` 事件 + `GetCurrentContentControl` 查询实现**真·光标跟随溯源**——审计师点文档某节，右侧溯源面板自动更新该节的数据来源与 stale 状态。连接器 API 在本部署的可用性不确定（OnlyOffice headless 降级 + 事件是否真触发未知），因此必须包含 **P0 连接器方案的 live 验证任务**：验证通过才默认启用自动跟随，否则平滑回退到已落地的手动章节输入。

**零回归红线**：
- 灰度开关默认关闭时，生成的 docx 与当前逐字节等价（不插入内容控件）。
- 旧交付物（无内容控件）在线编辑时，自动跟随静默降级到手动章节输入，不报错。
- 不改 `/trace`、`refresh-section`、`refresh-stale`、`writeback` 端点契约与 `useDeliverableLineage` 溯源查询逻辑；不改附注/报表业务生成内容，仅在章节边界注入内容控件包裹。

## Glossary

| 术语 | 含义 |
|------|------|
| 交付 docx | 审计报告正文 / 附注等在交付中心在线编辑的 Word 文档 |
| 章节 (section) | 交付 docx 中一个可溯源单元，标识为 `section_code`（如「五、1」「八、1」） |
| section_code | 章节业务编码，`/trace` 端点的查询键 |
| 锚点名 (anchor) | `section_code` 规范化后的技术标识，形如 `sec_五_1`（现有 `anchorNameFromSectionCode` 规则） |
| Bookmark | Word 书签，现有章节锚定方式；OnlyOffice 无「光标在哪个书签」查询能力 |
| Content Control (内容控件, SDT) | Word 结构化文档标签块（`w:sdt`），可带 `Tag`；OnlyOffice 连接器可查「当前光标所在内容控件」并在切换时触发事件 |
| Block Content Control | 包裹一个或多个整段落的块级内容控件（区别于行内控件） |
| 连接器 (Connector) | `editorInstance.createConnector()` 返回的对象，提供 `executeMethod` / `callCommand` / `attachEvent`；DocEditor 实例本身**没有**这些方法 |
| onChangeContentControl | 连接器事件：光标进入/离开/切换内容控件时触发，回调携带当前控件信息 |
| GetCurrentContentControl | 连接器方法：主动查询当前光标所在内容控件（返回 InternalId / Tag） |
| 真·光标跟随溯源 | 光标移动到某节 → 溯源面板自动更新为该节数据来源，无需手动点击 |
| 手动章节溯源 | 前置已落地的降级方式：审计师在面板输入/选择章节号触发 `/trace`，不依赖连接器 |
| 灰度开关 | `DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED`（后端生成侧）+ 前端自动跟随启用标志，默认关，零回归 |

## Requirements

### Requirement 1: 交付 docx 章节内容控件化

**User Story:** 作为审计报告出品的技术实现，我需要生成的交付 docx 每节内容被包成带 Tag 的块级内容控件，以便前端连接器能识别光标所在章节。

#### Acceptance Criteria

1. WHEN 灰度开关开启且生成审计报告正文/附注 docx THEN 系统 SHALL 对每个已有 `section_code` 的章节，用一个 Block Content Control 包裹该节的段落范围，`Tag` = `anchorNameFromSectionCode(section_code)`（与现有 bookmark 锚点命名规则一致）。
2. WHEN 章节被内容控件包裹 THEN 系统 SHALL **保留**该节原有 bookmark（内容控件与 bookmark 并存），使旧溯源路径与新路径都可用。
3. WHEN 章节内容为空或无法定位段落范围 THEN 系统 SHALL 跳过该节的内容控件注入（不产生空控件、不报错），并记录 debug 日志。
4. WHEN 内容控件被注入 THEN 系统 SHALL NOT 改变章节的可见文本、样式、编号与段落顺序（仅在段落范围外层加 `w:sdt` 包裹）。
5. WHEN 内容控件 Tag 生成 THEN 系统 SHALL 保证 `sectionCodeFromAnchor(Tag)` 能还原回原 `section_code`（双向一致）。

### Requirement 2: 生成向后兼容与幂等

**User Story:** 作为已有交付物的持有者，我需要老版本交付物在线编辑不受影响，重新生成才获得内容控件能力。

#### Acceptance Criteria

1. WHEN 灰度开关关闭 THEN 系统 SHALL NOT 注入任何内容控件，且生成的 docx 与开关引入前逐字节等价。
2. WHEN 打开一个在灰度开启前生成的旧交付物（无内容控件） THEN 前端 SHALL 静默降级为手动章节溯源，不报错、不弹错误提示。
3. WHEN 同一交付物重复生成 THEN 内容控件注入 SHALL 幂等（同输入产同结构，不叠加嵌套控件）。
4. WHEN 内容控件注入过程中任一节失败 THEN 系统 SHALL 对该节 fail-open（跳过注入保留原段落），不影响其余章节与整体生成成功。

### Requirement 3: 前端连接器建立与光标跟随溯源

**User Story:** 作为审计师，我希望在线编辑报告时，光标移动到某一节，右侧溯源面板自动显示该节的数据来源，无需手动操作。

#### Acceptance Criteria

1. WHEN 编辑器就绪且自动跟随启用 THEN `OnlyOfficeEditor` SHALL 通过 `editorInstance.createConnector()` 建立连接器（而非在 DocEditor 实例上直接调 `executeMethod`）。
2. WHEN 连接器建立成功 THEN 系统 SHALL 用 `attachEvent('onChangeContentControl', …)` 监听光标所在内容控件变化。
3. WHEN 光标切换到 Tag 以 `sec_` 开头的内容控件 THEN 系统 SHALL 解析 `section_code` 并调用 `LineagePanel` 触发该节溯源（更新当前章节、来源列表、stale 徽标）。
4. WHEN 光标处于 Tag 非 `sec_` 前缀或无 Tag 的控件/正文 THEN 系统 SHALL NOT 触发溯源（忽略，不清空已有结果或按产品定义处理为空态）。
5. WHEN 编辑器关闭或组件卸载 THEN 系统 SHALL 解绑连接器事件监听，无内存泄漏。

### Requirement 4: 主动查询当前章节

**User Story:** 作为审计师，打开溯源面板时我希望立即看到光标当前所在节的溯源，而不是等我移动光标才触发。

#### Acceptance Criteria

1. WHEN 用户打开溯源面板且自动跟随启用 THEN 系统 SHALL 主动调用连接器查询当前光标所在内容控件（`GetCurrentContentControl` 或等价能力）并触发一次溯源。
2. WHEN 主动查询返回的控件 Tag 以 `sec_` 开头 THEN 系统 SHALL 触发该节溯源。
3. WHEN 主动查询无结果或不支持 THEN 系统 SHALL 回退到手动章节溯源提示，不报错。

### Requirement 5: 降级链与手动溯源共存

**User Story:** 作为审计师，无论 OnlyOffice 连接器是否可用，我都要能溯源任意章节。

#### Acceptance Criteria

1. WHEN 连接器创建失败或不可用 THEN 系统 SHALL fail-open：不阻断编辑器加载，保留已落地的手动章节溯源输入可用。
2. WHEN 文档无任何 `sec_` 内容控件（旧交付物） THEN 自动跟随 SHALL 无操作，手动章节溯源仍可用。
3. WHEN 自动跟随启用且工作正常 THEN 手动章节溯源输入 SHALL 仍然保留（作为兜底与主动指定章节的入口），二者不互斥。

### Requirement 6: 灰度开关与零回归

**User Story:** 作为平台维护者，我需要该能力可灰度、可回退，默认不改变现有行为。

#### Acceptance Criteria

1. WHEN 后端灰度开关 `DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED` 缺省 THEN 其值 SHALL 为 False（不注入内容控件）。
2. WHEN 前端自动跟随启用标志缺省或 P0 live 验证未通过 THEN 前端 SHALL 默认不启用自动跟随（仅手动溯源），不调用连接器自动逻辑。
3. WHEN 开关关闭 THEN 生成链路、`/trace` 链路、编辑器加载链路 SHALL 与本 spec 引入前行为一致。

### Requirement 7: P0 连接器方案 live 验证

**User Story:** 作为负责交付的工程师，我不能再上线一个未经真实验证的溯源按钮，必须先证明 OnlyOffice 连接器在本部署真的能拿到内容控件 Tag。

#### Acceptance Criteria

1. WHEN 执行 P0 验证任务 THEN 系统 SHALL 在真实全栈（OnlyOffice 服务 + 后端 + 前端）打开一个含 `sec_` 内容控件的交付物，验证 `createConnector()` 成功、`onChangeContentControl` 在光标切换时触发、回调能取到 `sec_` 前缀 Tag。
2. WHEN P0 验证通过 THEN 方可将前端自动跟随启用标志默认置为开启。
3. IF P0 验证在当前环境无法完成（headless 降级、连接器事件不触发等） THEN 系统 SHALL 保持自动跟随默认关闭 + 手动溯源可用，并如实记录验证结论，不得伪造通过、不得默认启用未验证路径。

### Requirement 8: 正确性属性可测

**User Story:** 作为质量负责人，我需要关键正确性以属性/单测锁定，防止回归。

#### Acceptance Criteria

1. WHEN 实现完成 THEN 系统 SHALL 提供覆盖设计 Correctness Properties 的单测/属性测试（Tag↔section_code 双向一致、灰度关闭逐字节等价、并存不冲突、旧交付物降级、fail-open、光标切换更新、非 sec_ 忽略、事件解绑）。
