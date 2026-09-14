# Implementation Plan

## Overview

把交付 docx 章节从「仅 bookmark」升级为「bookmark + Block Content Control（Tag=`sec_xxx`）并存」，前端用 OnlyOffice 连接器 `onChangeContentControl` + `GetCurrentContentControl` 做真·光标跟随溯源。全程灰度可控、向后兼容、fail-open 降级到已落地的手动章节溯源。**P0 连接器 live 验证是启用自动跟随的前置门**——未验证通过则默认保持手动溯源，绝不伪造启用。

前置降级基线（已在本 spec 外落地，不重做）：坏按钮已降级为 `LineagePanel` 手动章节号溯源输入；两溯源按钮已合并；死 prop 已删。

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 0, "tasks": ["1"], "description": "核实命名真源 + 灰度开关 + 零回归基线" },
    { "wave": 1, "tasks": ["2", "2.1"], "description": "后端内容控件注入器 + 属性测试" },
    { "wave": 2, "tasks": ["3", "3.1"], "description": "生成器接入（灰度）+ 字节等价/并存测试" },
    { "wave": 3, "tasks": ["4", "4.1"], "description": "前端连接器自动跟随 + mock 单测" },
    { "wave": 4, "tasks": ["5"], "description": "门控默认关闭 + 降级链回归" },
    { "wave": 5, "tasks": ["6"], "description": "P0 连接器 live 验证（启用前置门）" }
  ]
}
```

## Tasks

- [x] 1. 核实命名真源 + 灰度开关 + 零回归基线
  - ✅ 命名真源 = `backend/app/services/section_anchor_utils.anchor_name`（`八、1`→`sec_八_1`，规则与前端 `anchorNameFromSectionCode` 逐字符镜像一致），**无需新造**；契约测试 `tests/test_section_anchor_contract.py` 锁定后端==前端规则 + 单顿号 round-trip（Property 1）。
  - ✅ 章节起止范围真源 = `word_doc_utils.scan_section_blocks(doc)`→`SectionBlock(section_code, open_el, close_el, elements)`（`##SECTION:code##…##/SECTION:code##` 标记块），note 导出器 step6→step7 之间可用；持久化在 confirm 时经 `DeliverableSectionStateService.snapshot_on_confirm(kept_codes)`（section 状态供 `/section-states`）。**发现**：文档化的 `write_section_anchors`（sec_ bookmark 写入）实际零调用（历史遗留），故内容控件即新锚定机制。
  - ✅ 加 `settings.DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED: bool = False`（`backend/app/core/config.py`，Settings 类，默认 False）。
  - ✅ characterization 基线 = `tests/test_deliverable_lineage_characterization.py`（对「灰度关闭时收尾生成的 docx」冻结**确定性结构指纹**快照 `BASELINE_FLAG_OFF`：body 级 [(kind,text)]+有序 bookmark 名+有序 sdt Tag，不比 zip 字节 → 无时间戳/随机字节 flaky；含开关缺省=False、关闭态==冻结基线且零 w:sdt、快照可重现确定、关闭路径==引入前纯 `remove_section_markers` 结构等价[Property 3]、开启态唯一差异=sec_ 内容控件包裹[可见文本/bookmark 不变] 5 测）。守卫仍是纯 `if flag:`（关闭时代码路径不执行），基线测试冻结其零回归结构供 Task 3.1 Property 3 对比。
  - _Requirements: 1.1, 1.5, 6.1, 6.3_

- [x] 2. 后端内容控件注入器 `content_control_injector.py`
  - ✅ `wrap_block_range(body, open_el, close_el, tag)`：把 body 级 [open..close] 范围外层包块级 `w:sdt`（`w:sdtPr` 含 alias+tag+id，内容依序移入 `w:sdtContent`），不改可见文本/样式/顺序；无法定位/反转/None/已包裹 → False 不抛。
  - ✅ `inject_content_controls_for_blocks(doc, blocks)`：对 `scan_section_blocks` 每块**只包内部内容**（`elements[1:-1]`，开闭标记留 body 级供 remove_section_markers 清理），逐节 fail-open；Tag 用 `anchor_name`；幂等（已在同 Tag sdt 内跳过）。`wrap_all_sections` 保留（inclusive 包裹变体）。
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.3, 2.4_

- [x] 2.1 注入器属性/单测
  - ✅ `tests/test_content_control_injector.py`（Property 1 Tag、Property 4 fail-open+内容不变、Property 5 幂等，6 测）。
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 2.3, 2.4_

- [x] 3. 生成器接入（灰度）+ 保留 bookmark 并存
  - ✅ `note_word_exporter.export` step6（seq 填充）后、step7（remove_section_markers）前，`if settings.DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED:` 追加 `inject_content_controls_for_blocks(doc, scan_section_blocks(doc))`（try/except 不阻断导出）；note bookmark（`note_section_xxx`）随内容移入 sdtContent 不被破坏（并存）。
  - **范围说明**：`sec_`/顿号章节码是**附注（disclosure notes）** 锚定目标（trace 示例 `八、1` 均为附注节），故接入 note 导出器＝真实 lineage 目标；审计报告正文（report_body）走 `report_body_json`/OPT 结构（非 `##SECTION##` 块），如需正文级 lineage 属独立设计，不在本 sec_ 机制内强接。
  - _Requirements: 1.1, 1.2, 2.1_

- [x] 3.1 字节等价 + 并存测试
  - ✅ `tests/test_content_control_injection_integration.py`：注入后开闭标记仍 body 级→remove_section_markers 正常清理、sdt+内容存活、可见文本/顺序不变（Property 4）、note_section bookmark 并存不破坏（Property 2）、空节跳过；灰度关闭跳过注入＝零回归（Property 3，守卫为纯 if）。
  - _Requirements: 1.2, 2.1, 6.1, 6.3_

- [x] 4. 前端连接器自动跟随（`OnlyOfficeEditor.vue` + `useLineageAutoFollow.ts`）
  - ✅ 新建 `useLineageAutoFollow.ts`：`AUTO_FOLLOW_ENABLED`（默认 False，env `VITE_DELIVERABLE_LINEAGE_AUTOFOLLOW='true'` 显式开启，P0 验证后）+ 纯函数 `extractControlTag`/`isSectionTag` + `createLineageAutoFollow(editorInstance, onSectionTag)`（fail-open：无/抛 createConnector → noop；`attachEvent('onChangeContentControl')`；`queryCurrent` 走 `executeMethod('GetCurrentContentControl')`；`dispose` 解绑）。
  - ✅ `OnlyOfficeEditor.vue`：editorReady 后 `if (AUTO_FOLLOW_ENABLED) lineageFollow = createLineageAutoFollow(editorInstance, tag => lineagePanelRef.onBookmarkDetected(tag))`；`toggleLineagePanel` 打开时 `lineageFollow.queryCurrent()`；cleanup/onUnmounted `dispose()`。手动溯源输入保留不动。
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 5.1, 5.3_

- [x] 4.1 前端 mock 单测
  - ✅ `__tests__/useLineageAutoFollow.spec.ts`（9 测）：Property 8（sec_ 触发）、Property 9（非 sec_/无 Tag 忽略）、Property 7（无/抛 createConnector fail-open）、Property 10（dispose 解绑）、queryCurrent + Tag 多形态提取。全绿。
  - _Requirements: 3.2, 3.3, 3.4, 3.5, 5.1, 5.3_

- [x] 5. 门控默认关闭 + 降级链回归
  - ✅ Property 11：后端 `DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED` 缺省 False（config）；前端 `AUTO_FOLLOW_ENABLED` 缺省 False（未验证不调连接器自动逻辑）。Property 6/7：连接器 fail-open + 手动章节溯源始终保留可用。
  - ✅ 回归：`/trace`、refresh-section/stale、writeback、`useDeliverableLineage` 均未改；LineagePanel + refresh 既有测试 + useLineageAutoFollow 共 32 测全绿；OnlyOfficeEditor 2 项 iframe 失败经 git stash 验证为**预存在**（测试已移除的 iframe-src 设计，与本 spec 无关）。
  - _Requirements: 2.2, 5.2, 6.1, 6.2, 7.2, 7.3_

- [ ]* 6. P0 连接器 live 验证（启用自动跟随的前置门）— **诚实留待（env-gated）**
  - **现状（R7.3 触发）**：OnlyOffice headless 降级 + 该交付编辑器被并发会话 SSE 反复抢占（memory 记录），当前环境无法可靠 live 验证 `onChangeContentControl` 事件真触发/回调 Tag 形状 → **保持前端自动跟随默认关闭（AUTO_FOLLOW_ENABLED=False）+ 手动章节溯源可用**，不伪造通过、不默认启用未验证路径（R7.3 合规）。
  - **待执行（有稳定全栈时）**：开灰度生成含 `sec_` 内容控件交付物 → 在线编辑 → 验证 `createConnector()`/`onChangeContentControl`/Tag/面板随光标更新；通过后置 `VITE_DELIVERABLE_LINEAGE_AUTOFOLLOW='true'`（R7.2）。
  - _Requirements: 7.1, 7.2, 7.3_

## Notes

- **零回归红线**：灰度关闭 docx 字节等价；旧交付物在线编辑降级手动不报错；不改 `/trace`/refresh/writeback 契约与 `useDeliverableLineage`。
- **命名单一真源**：Tag 命名必须复用/对齐现有 `section_code ↔ anchor` 规则（Task 1 核实），前后端契约测试锁定，杜绝漂移。
- **不赌 OnlyOffice 连接器**：Task 4 前端单测全用 mock connector（不依赖真实 OnlyOffice）；真实可用性由 Task 6 live 验证门控，验证前默认关闭、手动溯源始终兜底。
- **无 DB 迁移**：内容控件内嵌 docx，灰度走 settings。
- python-docx 无原生内容控件 API，`w:sdt` 需 oxml/lxml 手工构造（Task 2）。
