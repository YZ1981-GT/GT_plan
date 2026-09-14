# Design Document

## Overview

把交付 docx 的章节锚定从「仅 bookmark」升级为「bookmark + Block Content Control（Tag=`sec_xxx`）并存」，使前端 OnlyOffice **连接器**能通过 `onChangeContentControl` 事件与 `GetCurrentContentControl` 查询实现**真·光标跟随溯源**。全程灰度可控、向后兼容、fail-open 降级到已落地的手动章节溯源。P0 连接器可用性以 live 验证任务门控，验证通过才默认启用。

设计遵循收敛原则：复用现有 `section_code ↔ anchor` 命名规则（`anchorNameFromSectionCode`/`sectionCodeFromAnchor`）、复用现有 `/trace` 链路与 `useDeliverableLineage`、复用现有手动溯源作为降级基线，不新造并行溯源机制。

## Architecture

```
生成侧（后端，灰度 DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED）
  report_body / disclosure_notes 生成器
        │  每节段落范围
        ▼
  content_control_injector.wrap_section(doc, section_code, para_range)
        │  注入 <w:sdt> 块级内容控件，Tag=anchorNameFromSectionCode(section_code)
        │  保留原 bookmark（并存）；空节跳过；逐节 fail-open
        ▼
  交付 docx（含内容控件）───────────────┐
                                        │ 在线编辑
                                        ▼
消费侧（前端 OnlyOfficeEditor，自动跟随启用标志 + P0 验证门控）
  new DocsAPI.DocEditor(...) → editorReady
        │
        ▼
  connector = editorInstance.createConnector()          ← 关键：连接器而非 DocEditor 实例
        │  fail-open：创建失败 → 保留手动溯源
        ├─ attachEvent('onChangeContentControl', cb)     ← 光标切换控件
        └─ 打开面板时 GetCurrentContentControl(cb)        ← 主动查询当前节
        │
        ▼  cb(control) → tag = control.Tag
  tag.startsWith('sec_') ? sectionCodeFromAnchor(tag) : 忽略
        │
        ▼
  LineagePanel.onBookmarkDetected(tag) → useDeliverableLineage.traceFromAnchor
        │  （复用既有链路，不改 /trace）
        ▼
  溯源面板更新：当前章节 / 来源列表 / stale 徽标

  降级链：连接器不可用 / 无 sec_ 控件（旧交付物）→ 手动章节溯源（前置已落地，始终保留）
```

## Components and Interfaces

### 后端

**`content_control_injector.py`（新增，纯 oxml 工具）**
- `wrap_section_in_content_control(body, start_para, end_para, tag: str) -> bool`：把 `start_para..end_para` 段落范围外层包一个块级 `w:sdt`（`w:sdtPr` 含 `w:tag w:val=tag` + `w:alias`），内容移入 `w:sdtContent`。成功返回 True，无法定位/空范围返回 False（不抛）。纯 python-docx/lxml oxml 操作，不改可见内容。
- `wrap_all_sections(doc, section_ranges: list[(section_code, start, end)]) -> int`：批量包裹，逐节 try/except fail-open，返回成功注入数。Tag 由 `anchor_name_from_section_code(section_code)` 生成（后端镜像前端规则，或复用既有生成锚点的服务函数——Task 0 核实真源，避免命名漂移）。
- 幂等：若段落范围已在同 Tag 的 sdt 内则跳过（不嵌套叠加）。

**生成器接入（report_body / disclosure_notes 生成服务）**
- 在**既有 bookmark 注入点**旁，`if settings.DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED:` 追加内容控件注入（bookmark 逻辑不动，二者并存）。
- 章节段落范围复用生成器已知的「每节起止段落」信息（现有 bookmark 注入已依赖它）。

**配置**
- `settings.DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED: bool = False`。

### 前端

**`OnlyOfficeEditor.vue`（改造）**
- 新增自动跟随启用标志（来源：前端常量/环境变量，默认 False，P0 验证通过后置 True）。
- `editorReady` 后：`if (autoFollowEnabled) setupLineageConnector()`。
- `setupLineageConnector()`：
  - `const connector = editorInstance.createConnector()`（try/catch，失败 → `console.warn` + 不启用，手动溯源保留）。
  - `connector.attachEvent('onChangeContentControl', (cc) => onContentControlChange(cc))`。
  - `toggleLineagePanel` 打开时：`connector.executeMethod('GetCurrentContentControl', [], cb)`（或 `callCommand` 等价），主动查一次。
  - `onContentControlChange(cc)`：取 `cc?.Tag`，`startsWith('sec_')` → `lineagePanelRef.value?.onBookmarkDetected(tag)`；否则忽略。
- `onUnmounted`：断开连接器（`connector` 无显式 destroy 则置空引用 + 依赖编辑器销毁）。
- 保留手动溯源输入（前置已落地）不动。

**`LineagePanel.vue`（微调）**
- 已暴露 `onBookmarkDetected(anchorName)`（现成，复用）——连接器回调经父组件调它触发溯源。
- `hasNoAnchors`/`setNoAnchors` 保留：文档无 `sec_` 控件时标记降级（自动跟随无操作，手动仍可用）。

**`useDeliverableLineage.ts`（不改）**
- `traceFromAnchor` / `sectionCodeFromAnchor` / `anchorNameFromSectionCode` 复用。

### 契约守卫
- 生成侧：灰度关闭时 docx 字节等价（快照/结构对比测试）。
- 命名一致：后端 `anchor_name_from_section_code` 与前端 `anchorNameFromSectionCode` 对同一 `section_code` 产同一 Tag（契约测试锁定）。

## Data Models

无新增 DB 表 / 迁移。内容控件是 docx 内嵌结构（`w:sdt`），随交付物文件存储。灰度开关走 `settings`。

## Correctness Properties

### Property 1: Tag 与 section_code 双向一致
对任意合法 `section_code`，`sectionCodeFromAnchor(anchorNameFromSectionCode(section_code)) == section_code`；注入的内容控件 Tag 必满足该 round-trip。
**Validates: Requirements 1.1, 1.5**

### Property 2: 内容控件与 bookmark 并存不冲突
同一节同时有 bookmark 与内容控件时，两条锚点解析出的 `section_code` 相同；新增内容控件不移除/破坏既有 bookmark。
**Validates: Requirements 1.2**

### Property 3: 灰度关闭逐字节等价
`DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED=False` 时，生成的 docx 与未引入本能力时逐字节等价（不含任何新增 `w:sdt`）。
**Validates: Requirements 2.1, 6.1, 6.3**

### Property 4: 空节/失败 fail-open 不破坏内容
空章节或范围无法定位时跳过注入且不报错；任一节注入异常不影响其余节与整体生成；注入前后章节可见文本/样式/段落顺序不变。
**Validates: Requirements 1.3, 1.4, 2.4**

### Property 5: 注入幂等
对同一输入重复注入不产生嵌套/重复的同 Tag 内容控件。
**Validates: Requirements 2.3**

### Property 6: 旧交付物降级
无 `sec_` 内容控件的交付物在线编辑时，自动跟随无操作、不报错，手动章节溯源可用。
**Validates: Requirements 2.2, 5.2**

### Property 7: 连接器 fail-open
`createConnector()` 抛错/返回不可用时，编辑器正常加载，手动章节溯源保留可用，不阻断。
**Validates: Requirements 5.1, 5.3**

### Property 8: 光标切换更新章节
光标切入 Tag 为 `sec_X` 的内容控件时，溯源面板当前章节更新为 `X` 对应 `section_code` 并触发该节溯源。
**Validates: Requirements 3.2, 3.3, 4.1, 4.2**

### Property 9: 非 sec_ 控件忽略
光标处于非 `sec_` 前缀或无 Tag 的控件/正文时，不触发溯源、不误更新章节。
**Validates: Requirements 3.4**

### Property 10: 事件解绑无泄漏
组件卸载/编辑器关闭后，连接器事件监听被解绑，无残留回调。
**Validates: Requirements 3.5**

### Property 11: 灰度/验证门控默认关闭
后端开关缺省 False；前端自动跟随在标志缺省或 P0 未验证时默认关闭，不调用连接器自动逻辑。
**Validates: Requirements 6.1, 6.2, 7.2, 7.3**

## Error Handling

- 后端注入：逐节 `try/except`，失败跳过该节保留原段落 + `logger.debug`；整体生成不因注入失败而失败。
- 前端连接器：`createConnector`/`attachEvent`/`executeMethod` 全部 `try/catch`，任一失败 → `console.warn` + 回退手动溯源，不弹错误 Toast、不阻断编辑器。
- 主动查询无结果：静默回退手动溯源提示。
- P0 验证不通过：保持默认关闭 + 手动可用，如实记录，不伪造。

## Testing Strategy

- **后端单测/属性**：`content_control_injector` 的 wrap/round-trip/幂等/空节 fail-open/灰度字节等价（Property 1–5）；命名一致契约测试（后端 Tag == 前端锚点规则）。
- **前端单测**：`onContentControlChange` 的 `sec_` 解析与忽略分支（Property 8/9）、连接器 fail-open（Property 7）、事件解绑（Property 10）、门控默认关闭（Property 11）——用 mock connector（`createConnector` 返回可控 stub），不依赖真实 OnlyOffice。
- **P0 live 验证（Playwright/全栈）**：真实 OnlyOffice 打开含 `sec_` 内容控件的交付物，验证 `createConnector` 成功 + `onChangeContentControl` 触发 + 回调取到 Tag（Requirement 7）。**这是启用自动跟随的前置门。**
