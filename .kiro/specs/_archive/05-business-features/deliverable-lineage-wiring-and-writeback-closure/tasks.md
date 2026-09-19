# Implementation Plan: 交付件溯源接线与回填闭环（deliverable-lineage-wiring-and-writeback-closure）

## Overview

把已建成但从未接线的出品物溯源/回填能力接通，并修正三处污染审计留痕的缺陷。**严禁重建**溯源总线 / Stale 传播引擎 / 留痕服务 / 章节状态服务 / 内容控件注入器 —— 它们全部已存在且逻辑正确。本 spec 只做：①补生产调用方 ②补标记清理后的锚点定位纯函数 ③修三处逻辑缺陷 ④入口门控 ⑤两处 additive 迁移。

实施语言：后端 **Python 3.12**（仓库根 `.venv`）；前端 **Vue3 + TypeScript**；数据层 **PostgreSQL 16** 手写迁移（MigrationRunner）。属性测试 **hypothesis**（`max_examples=5`）。

**验收铁律（用户明确要求）**：验收判据必须是「真实生成一份附注交付件后 `/section-states` 返回非空、回填一段文字后 DB 里 `text_content` 真变了」，**不得再用合成 docx 的测试当证据**。合成 docx 测试可保留作单元层，但不构成任务完成判据。

## Task Dependency Graph

```json
{
  "waves": [
    {
      "wave": 1,
      "name": "接线：锚点写入 + 章节状态 + 锚点定位 + 三处修正 + 入口门控",
      "tasks": ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"]
    },
    {
      "wave": 2,
      "name": "留痕正确性：快照继承 + doc_key + 真实编辑人 + 护栏接线",
      "tasks": ["12", "13", "14", "15", "16"]
    },
    {
      "wave": 3,
      "name": "报告正文段落级回填",
      "tasks": ["17", "18", "19", "20"]
    },
    {
      "wave": 4,
      "name": "xlsx 差异告警 + 溯源可视化",
      "tasks": ["21", "22", "23", "24", "25"]
    }
  ]
}
```

依赖说明：

- 任务 1（`scan_anchor_blocks`）是任务 6/7（回填与刷新改走锚点）的物理前置。
- 任务 2（`export_with_meta`）是任务 4（章节状态接线）的前置——不暴露 `kept_codes` 就无处调 `snapshot_on_confirm`。
- 任务 3（V141 迁移）是任务 7（人工编辑检测）的前置。
- 任务 11（真实链路验收）依赖 Wave 1 全部任务。
- 任务 21/22（xlsx 告警）依赖 Wave 2 的任务 12（快照继承）。
- **任务 23（版本链展示 stale 徽标）依赖任务 12** —— 快照继承未落地前，OO 编辑会把 `source_snapshot_refs` 重绑到当前 `tb_hash`，展示出来的 `is_stale` 恒 false，做出来是个会骗人的徽标（原依赖说明把 23~25 整体列为「不依赖 Wave 1，可并行」，对 24/25 成立，对 23 不成立）。
- 任务 24/25（三件套对照 / 溯源入口）不依赖前序波次，可并行。

---

## Tasks

## Wave 1：接线

- [x] 1. `scan_anchor_blocks` 纯函数 + 块定位降级链
  - `section_anchor_utils.py` 新增 `AnchorBlock` dataclass + `scan_anchor_blocks(doc)`：遍历 body 直接子元素，`w:bookmarkStart[@w:name^='sec_']` 开块、同 `w:id` 的 `w:bookmarkEnd` 闭块，区间内只收 `w:p`/`w:tbl`；`section_code_from_anchor` 反解失败跳过 + warning；同 code 重复取首个 + warning；无锚点返 `[]`
  - 新增 `resolve_section_blocks(doc) -> tuple[Literal['anchor','marker','none'], list]`：锚点优先、标记回退、皆无返 `('none', [])`
  - _Requirements: 2.1, 2.2, 2.3, 2.5_ / _Design: 组件 1 + 2_

- [x]* 1.1 `scan_anchor_blocks` 单元 + 属性测试
  - Property 4（写入↔扫描互逆）、Property 5（降级链单调，三种输入均不抛）
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 2. `NoteWordExporter.export_with_meta` + 锚点写入接线
  - 新增 `NoteExportMeta` dataclass（`kept_codes` / `anchor_map` / `rendered_block_hashes` / `variant_key`）与 `export_with_meta`；`export` 改为委托，**签名与返回值不变**
  - 在 step6（`_fill_seq_placeholders`）后、step6.5（内容控件）前插入锚点写入：重新 `scan_section_blocks(doc)` → 过滤 `kept_codes` → 转 `section_anchor_utils.SectionBlock` → `write_section_anchors`
  - 抽 `_normalize_block_text(elements)` 纯函数算 `rendered_block_hashes`（**与 `_detect_user_edits` 共用同一函数，禁各写一份**）
  - programmatic 模式 meta 三项为空，行为与现状一致
  - _Requirements: 1.1, 1.2, 1.3, 1.7, 4.1_ / _Design: 组件 3_

- [x]* 2.1 锚点写入属性测试
  - Property 1（锚点集合 == kept 集合）、Property 2（可见文字逐字不变）
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 3. V141 迁移 + ORM + 契约测试
  - `backend/migrations/V141__deliverable_section_rendered_block_hash.sql`：`ADD COLUMN IF NOT EXISTS rendered_block_hash VARCHAR(64)`；配 `R141` 回滚
  - **🔴 编号从立项时写的 V141 改为 V141**：V141/V142 已被并发 spec `sampling-compliance-closure` 占用（`V141__sampling_registry_batch_binding.sql` / `V142__sampled_vouchers_manual_scope_unique.sql`），按「迁移版本号永不复用」铁律顺延
  - `DeliverableSectionState.rendered_block_hash: Mapped[str | None]`
  - `test_deliverable_section_state_contract` 期望列集 +1
  - _Requirements: 4.1, 12.6_ / _Design: Data Models V141_

- [x] 4. `snapshot_on_confirm` additive 扩展 + 两条生产导出入口接线
  - `snapshot_on_confirm` 加 `anchor_map` / `version_no` / `rendered_block_hashes` 三个 kwarg（默认 None ⇒ 逐字节等价现状）
  - `render_disclosure_notes` 路由：改调 `export_with_meta`，`render_and_store` 后调 `snapshot_on_confirm(...)`，整段 try/except 记 warning 不阻断（需求 1.6）
  - `FullDeliverablesExecutor._run_disclosure_notes`：同款接线
  - _Requirements: 1.4, 1.5, 1.6_ / _Design: 组件 4_

- [x]* 4.1 章节状态落库属性测试
  - Property 3（section_code 集合 == kept_codes 且 anchor_name 一一对应）
  - 已交付 `test_deliverable_section_state_persist.py`（7 例，含 additive kwarg 三态 + fail-open + **反向自检「不接线则表恒空」**）
  - _Requirements: 1.4_

- [x] 5. 内容控件灰度开启 + characterization 去默认值依赖
  - `config.py` `DELIVERABLE_LINEAGE_CONTENT_CONTROL_ENABLED` 默认改 `True`；`.env.example` 补说明
  - `test_deliverable_lineage_characterization.py` 等既有测试改为**显式指定**开关值（monkeypatch），不依赖默认值 → 默认翻转不产生假红
  - 前端 `AUTO_FOLLOW_ENABLED` **保持默认关闭**（连接器未经真实 OO 实测）
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x]* 5.1 内容控件关闭态等价性测试
  - Property 6（关闭时 `sdt` 元素数为 0 且输出等价）
  - _Requirements: 3.1, 3.3, 3.5_

- [x] 6. 回填改走 `resolve_section_blocks` + 零行写入不计成功
  - `_extract_sections_from_docx` 改调 `resolve_section_blocks`；`anchor` 模式下块内不含标记段落，提取逻辑相应简化
  - `_write_text_content` / `_resolve_conflict_and_write` 返回 `rowcount`；0 行 → 计入新增 `failed` 列表 + 留痕，**不更新基线 hash**
  - `WritebackResult` additive 加 `failed: list[WritebackFailure]`
  - 全部章节失败时返回明确失败信息（供前端不出成功 Toast）
  - _Requirements: 2.3, 5.1, 5.2, 5.3, 5.4, 5.5_ / _Design: 组件 6（Wave 1 部分）_

- [x]* 6.1 回填结果分类属性测试
  - Property 9（零行不计成功）、Property 10（五类互斥且完备）
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

- [x] 7. 人工编辑检测修正 + 就地刷新
  - `_detect_user_edits`：改比 `rendered_block_hash`（共用 `_normalize_block_text`）；NULL 时返 False
  - `_insert_refreshed_content` → `_replace_block_content(block, text)`：先 `elements[0].addprevious(new_p)` 逐段插入、再 remove 旧 elements；区间空时 `start_el.addnext(...)` 逆序插入
  - 刷新后重算 `rendered_block_hash` 并随 `clear_section_stale` 落库
  - `refresh_section` / `refresh_all_stale_sections` 改走 `resolve_section_blocks`
  - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_ / _Design: 组件 5_

- [x]* 7.1 人工编辑检测 + 就地刷新属性测试
  - Property 7（三态精确性）、Property 8（刷新保持位置且其余章节不变）
  - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 8. `deliverable_capabilities` 单一真源 + 后端端点门控
  - 新增 `backend/app/services/deliverable_capabilities.py`：`WRITEBACK_SUPPORTED_DOC_TYPES` / `SECTION_REFRESH_SUPPORTED_DOC_TYPES` + `supports_writeback` / `supports_section_refresh`
  - `deliverable_lineage.py` 的 `/writeback` `/refresh-section` `/refresh-stale` 前置校验，不支持返 400 明确错误
  - `DeliverableDTOSchema` additive 加 `supports_writeback` / `supports_section_refresh`，`list_deliverables` 填充
  - _Requirements: 6.1, 6.2, 6.4, 6.5_ / _Design: 组件 7_

- [x] 9. 前端入口门控 + 修 `hasNoAnchors` 死 prop
  - `DeliverableCenter.vue` 往 `OnlyOfficeEditor` 传 `:doc-type` 与两个能力布尔
  - `OnlyOfficeEditor.vue` 按能力布尔决定是否渲染 `WritebackResultPanel`；`LineagePanel` 刷新按钮同款门控
  - `hasNoAnchors` 由 `LineagePanel` 加载 `/section-states` 的结果回传（`sections.length === 0` ⇒ true），修死 prop；无锚点时显示「本交付件无章节锚点」提示且不渲染空下拉
  - `WritebackResultPanel` 呈现 `failed` 类并在全失败时用 error 提示
  - _Requirements: 6.1, 6.2, 6.3, 5.2, 5.3_

- [x]* 9.1 前端门控与提示守卫
  - Property 11（能力矩阵前后端一致，读后端常量交叉锁死）、Property 12（无锚点提示）
  - _Requirements: 6.1, 6.2, 6.3, 6.5_

- [x] 10. Wave 1 零回归回归 + 反向自检
  - 跑 `test_deliverable_*` / `test_content_control_*` / `test_note_*` 全量；前端 `deliverable` 目录全量
  - Property 24（附注可见段落文字序列不变；报表/报告正文字节不变）
  - Property 25：为任务 6/7 各补一条「复现旧行为则打红」自检（零行写入计入 written / 用 `source_snapshot_hash` 比块文本）
  - _Requirements: 12.4, 12.5_

- [x] 11. **真实链路验收（Wave 1 完成判据，不得用合成 docx 顶替）**
  - 新建只读为主的验证脚本 `backend/scripts/diagnose/verify_deliverable_lineage_live.py`：真实项目生成附注交付件 → 断言 `/section-states` 非空且 `anchor_name` 与 `section_code` 一一对应 → 回填一段文字 → 查 `disclosure_notes.text_content` 真变 → **按快照复原**
  - 浏览器实测（chrome-devtools + postgres 只读）：溯源面板章节下拉非空、点回填后 Toast 与 DB 一致、xlsx 交付件上无回填按钮
  - 实测结论回写本文件 Notes；测试数据复原核实
  - _Requirements: 12.1, 12.2, 12.3_

---

## Wave 2：留痕正确性

- [x] 12. OO 编辑版本继承快照引用
  - `render_and_store` 加 `inherit_snapshot_refs: bool = False`；为 True 时不覆盖 `task.source_snapshot_refs`
  - `handle_callback` 改为读上一版 `source_snapshot_refs` 传入，**不再** `capture_snapshot_refs`
  - _Requirements: 7.1_ / _Design: 组件 8_

- [x]* 12.1 快照继承属性测试
  - Property 13（新版本 refs 与上一版逐字相等；tb_hash 变化后仍判 stale）
  - _Requirements: 7.1_

- [x] 13. `doc_key` 去时间戳 + 与席位 key 同源
  - 新增 `deliverable_doc_key(task_id, version_no)` 纯函数，`build_editor_config` 与 `onlyoffice_config` 席位占用 / `onlyoffice_callback` 席位释放三处共用
  - _Requirements: 7.4, 7.5_

- [x]* 13.1 doc_key 确定性测试
  - Property 15（同输入同输出；席位占用释放同源）
  - _Requirements: 7.4, 7.5_

- [x] 14. callback 取真实编辑人
  - 从回调 body 的 `users` / `actions[].userid` 解析编辑人并校验属于本项目；解析不出记 None + warning，**禁止回退 `task.created_by`**
  - 版本 `created_by` 与审计日志 actor 用解析结果
  - _Requirements: 7.2, 7.3_

- [x]* 14.1 编辑人解析属性测试
  - Property 14（三态：可识别 / 不可识别 / 非本项目；任何情况不得等于 created_by）
  - _Requirements: 7.2, 7.3_

- [x] 15. 合规护栏接入回填主流程
  - 第 4a 步改调 `_classify_change(code, db_text, block_xml)`；`block_xml` 由 `resolve_section_blocks` 的 elements 序列化拼接
  - TABLE / TITLE 拒绝原因文案指向调整分录 / 模板路径；被拒变更进 `rejected` 且留痕
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x]* 15.1 护栏属性测试
  - Property 16（表格数字 / 标题被拒 + 留痕）；含「硬编码 TEXT 则打红」反向自检
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [x] 16. Wave 2 回归 + CI job
  - `governance-checks.yml` 新增 job 挂 Wave 1+2 守卫
  - 已交付两个 job：`deliverable-lineage-wiring-backend`（7 步）/ `deliverable-lineage-wiring-frontend`（4 步）；115 → 117 jobs，YAML 可解析且引用的测试文件全部存在
  - _Requirements: 12.4, 12.5_

---

## Wave 3：报告正文回填

- [x] 17. 报告正文段落锚点写入
  - `TemplateFillService.confirm_report_body` 后写段落锚点（`sec_rb_` 前缀，`section_code` 取模板 section_id）；`snapshot_on_confirm` 接线
  - _Requirements: 9.1_ / _Design: 组件 9_

- [x] 18. 回填适配器抽象 + 报告正文适配器
  - 抽 `WritebackTargetAdapter` 协议（`read_upstream` / `write_upstream`）；附注逻辑抽为 `DisclosureNoteAdapter`（行为逐字不变）
  - 新增 `ReportBodyAdapter` 读写 `AuditReport.report_body_json`
  - `DeliverableWritebackService` 按 `doc_type` 选适配器；`deliverable_capabilities` 加入 `audit_report`
  - _Requirements: 9.2, 9.3, 9.5_

- [x]* 18.1 报告正文回填属性测试
  - Property 17（只写 report_body_json，DisclosureNote 不变）、Property 19（重新生成后保留）
  - _Requirements: 9.2, 9.6_

- [x] 19. 派生段落拒绝回填
  - 按 manifest placeholder 清单判定派生段落，拒绝 + 留痕
  - _Requirements: 9.4_

- [x]* 19.1 派生段落拒绝测试
  - Property 18
  - _Requirements: 9.4_

- [x] 20. Wave 3 真实链路验收
  - 真实项目生成报告正文 → OO 改一段叙述文字 → 回填 → 查 `report_body_json` 真变 → 重新生成确认保留 → 复原
  - _Requirements: 9.6, 12.1, 12.2, 12.3_

---

## Wave 4：xlsx 差异告警 + 溯源可视化

- [x] 21. **V143** 迁移 + `FinancialReportDriftService`
  - 🔴 **编号从 V142 改为 V143**：V142 已被本 spec Wave 2 占用（`V142__deliverable_version_editor_identity.sql`，已应用真实库），按「迁移版本号永不复用」顺延
  - `ADD COLUMN IF NOT EXISTS drift_report JSONB` on `word_export_task_versions` + 配 `R143` 回滚
  - `detect(task_id, version_no)`：按 `cell_mapping.json` 覆盖单元格比对文件值 vs 重算值；映射缺失 fail-open + warning
  - **三态返回**（不是布尔）：映射文件不存在 → `null` 放行；存在但解析失败 → `{"unavailable": reason}` 阻断；比对完成 → `{"diffs": [...]}`
  - _Requirements: 10.2, 10.5, 10.6, 10.7, 10.8, 12.6_ / _Design: 组件 10 + Data Models V143_

- [x] 22. 差异阻断确认 + 前端告警呈现
  - `confirm_deliverable` 前置校验 `drift_report` 非空即拒绝
  - 交付中心呈现具体报表行与差额 + 「请走调整分录」提示
  - Property 20 守卫：全仓不存在 xlsx→trial_balance/report_config/AuditReport 的写入路径
  - _Requirements: 10.1, 10.3, 10.4_

- [x]* 22.1 差异阻断属性测试
  - Property 20、Property 21
  - **反向自检**：把「解析失败」也按 fail-open 放行（旧口径）时守卫必须打红 —— 否则弄坏一个映射文件即可绕过 10.4 阻断
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

- [x] 23. 版本链展示快照与中文化
  - `DeliverableVersionSchema` 加 `source_snapshot_refs` / `edited_by_name` / `is_stale`
  - `DeliverableVersionList.vue`：`created_via` 中文标签映射 + `tb_hash` 短标识 + stale 徽标 + 编辑人
  - _Requirements: 11.1, 11.2_

- [x] 24. 三件套一致性三列对照 + 重新生成入口
  - `check_trio_consistency` 结果扩展为可定位滞后类别；`CompletenessBanner` 改三列对照表 + 「重新生成这一类」
  - _Requirements: 11.3, 11.4_

- [x] 25. 交付件列表溯源入口
  - 每行溯源入口调 `/trace`，呈现「交付件 → 附注章节 → 底稿 → 试算表 → 调整分录」；超时/无匹配显示明确原因
  - _Requirements: 11.5, 11.6_

- [x]* 25.1 溯源展示守卫
  - Property 22、Property 23
  - _Requirements: 11.1, 11.2, 11.3, 11.4_

---

## Notes

- 标 `*` 的子任务为测试/验收类；按用户铁律 optional 任务同样做完。
- **任务 11 / 20 是各波的真实链路验收，禁止用合成 docx 顶替**（前序 spec 22/22 假绿的直接教训）。
- **立项时的缺陷基线（勿重复调查）**：`write_section_anchors` / `snapshot_on_confirm` / `_classify_change` 三者全仓零生产调用方；`note_word_exporter` step7 清标记；内容控件灰度默认 False；`render_and_store` 第 364 行覆盖 `task.source_snapshot_refs`；`doc_key` 含 `int(time.time())`；`_detect_user_edits` 哈希域不匹配；`_insert_refreshed_content` 用 `doc.add_paragraph` 追加到文末。**其中前 5 条已由 Wave 1 修掉**（见下方 Progress Log），仍成立的是：`_classify_change` 零生产调用方（Task 15）、`source_snapshot_refs` 被覆盖（Task 12）、`doc_key` 含时间戳（Task 13）。

---

## Progress Log

### Wave 1 交付核实（2026-08-04，只读核对磁盘，未改代码）

Task 1~9 及其 optional 子项 **均已交付**，判据为「符号存在 + 有生产调用方 + 有对应守卫测试」三条同时成立：

| Task | 交付物（磁盘实证） | 守卫 |
|------|-------------------|------|
| 1 | `section_anchor_utils`：`AnchorBlock` / `scan_anchor_blocks` / `resolve_section_blocks` | `test_section_anchor_scan.py`（18 例，Property 1/4/5 + 3 条反向自检） |
| 2 | `note_word_exporter`：`NoteExportMeta` + `export_with_meta`，锚点写入插在 step6 后 / 内容控件前；`export` 委托保持签名 | `test_note_export_anchor_wiring.py`（8 例，Property 1/2/6 + 2 条反向自检） |
| 3 | **V141**（非原计划 V139，见下条）+ `DeliverableSectionState.rendered_block_hash` + `R141` 回滚 | `test_deliverable_section_state_contract.py`（列集 +1） |
| 4 | `snapshot_on_confirm` 三个 additive kwarg + `persist_note_export_section_states`，**双生产入口已接**：`routers/deliverable.py:717/746` 与 `full_deliverables_executor.py:356/380` | `test_deliverable_section_state_persist.py`（7 例，含 `test_reverse_selfcheck_no_wiring_means_empty_table` —— 直接钉死历史假绿根因） |
| 5 | `config.py` 默认 `True`；characterization 全部改为**显式** `_finalize(doc, flag=...)`，并新增 `test_flag_default_is_true_after_gray_flip` | `test_deliverable_lineage_characterization.py` |
| 6 | `_write_text_content` / `_resolve_conflict_and_write` 返回 rowcount；`WritebackFailure` + `failed` 列表 | `test_deliverable_writeback_rowcount.py`（5 例，Property 9/10 + `test_reverse_selfcheck_old_behavior_would_report_success`） |
| 7 | `block_text_hash` 共用真源；`_replace_block_content` 用 `addprevious` 就地替换；刷新后重算 hash | `test_deliverable_refresh_inplace.py`（7 例，Property 7/8 + `test_reverse_selfcheck_snapshot_hash_as_baseline_always_reports_edits`） |
| 8 | `deliverable_capabilities.py`（含 `WRITEBACK_FORBIDDEN_DOC_TYPES` 防后来者加 `financial_report*`）+ 三端点 400 门控 + DTO 两布尔 | **缺**：见下方欠账 |
| 9 | `OnlyOfficeEditor` / `DeliverableCenter` 传 `docType` + 能力布尔；`hasNoAnchors` 由 `LineagePanel` 回传；`WritebackResultPanel` **五类齐全**（written/rejected/conflicts/skipped/failed + error 提示） | **缺**：见下方欠账 |

**设计偏差（已在正文改正）**：

1. **迁移号 V139 → V141**：`V139__sampling_registry_batch_binding.sql` / `V140__sampled_vouchers_manual_scope_unique.sql` 已被 `sampling-compliance-closure` 占用（该 spec 迁移已应用）。按「迁移版本号永不复用」，Wave 1 实际落 **V141**，Wave 4 顺延 **V142**。design/tasks 均已同步。
2. **纯函数命名**：design 写 `_normalize_block_text`（私有），实现为 `section_anchor_utils.normalize_block_text` + `block_text_hash`（公开）。「导出侧与 `_detect_user_edits` 共用同一真源」的设计意图**已满足**（两侧均 import `block_text_hash`）。→ 写守卫时按实际公开名，按 design 的私有名会 0 命中变空转。

### Wave 1 收口（2026-08-04 本会话，Task 8/9 守卫 + Task 10/11 补齐）

**✅ Wave 1 全部 11 项完成**。本轮补齐前次复核列出的四项欠账中的三项（CI 归 Task 16）：

| 欠账 | 交付 |
|------|------|
| Task 8/9 无守卫（Property 11/12） | 后端 `test_deliverable_capabilities_matrix.py`（15 例）+ 前端 `deliverableCapabilityGating.spec.ts`（10 例） |
| Task 10 Property 24 无用例 | `test_deliverable_lineage_zero_regression.py`（5 例） |
| Task 11 真实链路验收脚本不存在 | `backend/scripts/diagnose/verify_deliverable_lineage_live.py`，真实项目 **12 项全 PASS** |

**Property 11 的落法（跨前后端交叉锁死）**：前端守卫用 `fs.readFileSync` 直读后端 `deliverable_capabilities.py`，正则抽两个 `frozenset` 的成员，与前端消费点比对 —— 能力矩阵一旦前后端分叉即打红。另含三条反向自检：①`financial_report*` 若被加进任一 `SUPPORTED` 集合必红（防后来者"顺手"开 xlsx 回写）②前端 SFC 若出现 `doc_type` 白名单式判断（`docType === 'disclosure_notes'` / `startsWith('financial')` 作条件）必红 —— **但 `writebackUnsupportedTitle` 里的 `startsWith('financial_report')` 是合法例外**（只决定提示文案措辞、不决定能力），守卫按「是否出现在能力布尔的赋值链上」区分 ③`audit_report` 当前必须**不在** `WRITEBACK_SUPPORTED`（Wave 3 落地后该断言会打红，提醒同步改守卫）。

**Property 24 的两档判据（design 需求 12.4 已改为分档，勿再按「全部逐字节等价」写守卫）**：
- **档 1 报表 xlsx / 报告正文（Wave 3 前）= 逐字节等价** —— 判据落成**源码级**断言「`report_excel_exporter.py` / `template_fill_service.py` / `report_body_service.py` 三者均不引用 `write_section_anchors` / `inject_content_controls_for_blocks` / `anchor_name`」。不做「跑两次比字节」是因为 xlsx/docx 内含时间戳与 zip 顺序，字节比对天然不稳定；而「不引用注入符号」是**结构性**保证，比运行时比对更硬。
- **档 2 附注 docx = 可见段落文字序列逐字相等** —— 由 `test_note_export_anchor_wiring.py::test_property_2_*` 覆盖（生产路径 + `w:sdt` 下钻）；本文件另加 `test_anchor_elements_are_invisible` 钉住底层前提（`w:bookmarkStart/End` 零可见文字），并断言锚点确实写进 XML 防上一条空转。
- **反向自检**：断言附注导出器**确实**引用 `write_section_anchors` —— 若锚点接线被回退，「零回归」反而更好达标，此时必须打红。

**Task 11 真实链路验收实测（项目 `a7fc75e5` 陕西华氏医药_2025 / soe / standalone）**：

| 检查项 | 结果 |
|--------|------|
| V141 列 `rendered_block_hash` 已应用 | ✅ |
| 生产导出返回章节元数据 | kept=141 / anchors=141 / hashes=141 / variant=`soe_standalone` |
| 交付 docx 内真有 Section_Anchor 书签 | 扫到 **141 个锚点块** |
| 锚点命名与 section_code 一一对应 | 全部 `anchor_name == anchor_name(section_code)` |
| 交付 docx 已清 `##SECTION:##` 标记 | ✅ 标记扫描为空 ⇒ **旧定位方式恒失效，证明必须走锚点** |
| `/section-states` 返回非空 | **141 行**（改造前全库 **0 行**） |
| 章节状态携带 `rendered_block_hash` | 非空 **141/141** |
| 回填后 `disclosure_notes.text_content` 真的变了 | ✅ 探针文字在新值中；`written` 105 项 / `failed` 3 项 / `conflicts` 0 |
| `written` 与 `failed` 互斥 | ✅ 两桶无交集 |
| 上游无记录的章节落 `failed` 桶 | ✅ `四、优先股_永续债等` / `九、1_或有负债` / `九、2_或有资产` / `九、999` 均 UPDATE 影响 0 行 ⇒ 不计 written（正是 Task 6 要修的假成功） |

**数据已复原并二次核实**：`disclosure_notes[一、1].text_content` 回写原值；新建交付物 `a055b1b5` 及其版本/章节状态已删除；postgres 只读复查 `deliverable_section_state` = **0 行**、`word_export_task` 中 `a055b1b5` = **0 行**。

**本轮实测发现并修掉 1 个真实缺陷**：`get_section_states` 返回的 dict **漏了 `rendered_block_hash`** —— 该列写入正确（`test_deliverable_section_state_persist.py` 已断言落库值），但查询侧不返回 ⇒ 任何经 `/section-states` 消费该基线的下游（前端 stale 展示、未来的批量刷新预检）都拿不到。属「写对了读不出」的单侧缺口，只有真实链路验收会暴露（单测各自断言自己那一侧全绿）。已补返回字段 + docstring 键清单，并在 `test_deliverable_section_state_persist.py` 加 `test_get_section_states_returns_rendered_block_hash`（含反向自检说明）。

**回归**：后端本 spec 作用域 **146 passed / 0 failed**；前端 `deliverable` 目录 **110 passed / 2 failed**（`OnlyOfficeEditor.spec.ts` 的 iframe 两例，已用「只换该文件为 HEAD 版跑同一组」验证为预存在基线）。

**Wave 1 剩余（归后续波次）**：

- CI：`governance-checks.yml` 117 个 job 中**无**本 spec 的 job（现有 `sampling-compliance-*` 属另一 spec）→ 由 Task 16 统一挂 Wave 1+2 守卫。
- 浏览器实测（溯源面板章节下拉非空 / xlsx 上无回填按钮）：能力门控与无锚点提示已由前端守卫 10 例 + 后端 15 例交叉锁死，且 `/section-states` 真实返 141 行已由脚本证实；浏览器层留待 Wave 2 收口时与 doc_key/编辑人改动一并实测（避免同一页面测两遍）。

### Wave 2 收口（2026-08-04 本会话，Task 12~16 全部完成）

**✅ Wave 2 全部 5 项完成**（含 optional 子项 12.1 / 13.1 / 14.1 / 15.1）。

| Task | 交付物 | 守卫 |
|------|--------|------|
| 12 | `render_and_store(inherit_snapshot_refs=True)`：继承上一版 `source_snapshot_refs` 且**不覆盖** `task.source_snapshot_refs`；`handle_callback` 删掉 `capture_snapshot_refs` 调用 | `test_deliverable_oo_edit_provenance.py` Property 13（含反向自检 `test_reverse_selfcheck_recapture_would_wash_out_stale`） |
| 13 | 新建 `deliverable_doc_key.py` 单一真源（`deliverable_doc_key` / `parse_deliverable_doc_key` round-trip）；三处共用（config 生成 / 席位占用 / 席位释放） | Property 15 + 源码级「三处都走真源、不得字面量拼接」 |
| 14 | 新建 `onlyoffice_editor_identity.py`（`extract_editor_ids` / `resolve_editor_id`）+ **V142** 迁移两列 `edited_by` / `edited_at` + `_resolve_verified_editor` 项目归属校验 | Property 14（含「任何路径不得回退 `created_by`」源码断言） |
| 15 | 第 4a 步改调 `_classify_change`（块 XML 由 `_last_block_xml` 承载）；拿不到块 XML 时降级为纯文字分类并记 warning | `test_deliverable_writeback_guardrail.py`（8 例，Property 16 + 3 条反向自检） |
| 16 | `governance-checks.yml` 两个 job（backend 8 步 / frontend 2 步），115 → 117 jobs | YAML 可解析 + 引用测试文件全部存在 |

**三处落地时推翻或修正了立项描述**：

1. **`doc_key` 格式沿用席位侧而非编辑器侧** —— design 写 `f"{task.id}_{version.version_no}"`，实际落 `deliverable-{task_id}-{version_no}`（席位侧既有格式）。理由：Redis 里已有的席位 key 因此**逐字不变**（零回归），改变的只有编辑器侧那一个值；反之会让线上所有活跃席位 key 失配。
2. **席位释放改为按 doc_key 释放全部席位**，新增 `release_sessions_by_doc_key(doc_key)`。原设计只说「与 doc_key 同源」，但落地发现**更深的缺陷**：占用发生在 `onlyoffice_config`（用 `current_user.id`）、释放发生在**回调**（无鉴权用户上下文，历史用 `task.created_by` 近似）→ 两把 key 从来不匹配、**席位从未真正释放**，全靠 1h TTL 自愈。且历史释放侧的 `version_no` 取 `body.get("version", 1)` —— 那是 **OO 内部版本号**不是我们的版本号，又一层不匹配。正解是从回调体自带的 `key`（就是我们下发的 doc_key）反解，OO 在最后一个用户断开时才发 status 2/4，故「该文档所有席位一并释放」语义正确。
3. **编辑人需要新列承载** —— 原设计只说「版本 `created_by` 用解析结果」，但 `created_by` 是 **NOT NULL + FK users(id)**，无法表达「未知」。若解析不出就只能塞创建人 = 需求 7.3 直接失效。故加 V142 两列：`edited_by`（NULL=未知）/ `edited_at`，`created_by` 在 OO 路径降级为「回调处理占位」，展示链路一律读 `edited_by`。

**Task 15 的实现选择**：`_classify_change` 需要块 XML，而 `_extract_sections_from_docx` 原本只返回文字。落法是让它**同时**把 `section_code → 块 XML` 存进 `self._last_block_xml`（每次 extract 覆盖式重置，避免跨次回填串味），主流程按 code 取用。不改 extract 的返回签名 ⇒ 既有调用方与测试零改动。拿不到块 XML 时**显式降级 + warning**，属可观测的降级而非静默失效。

**本轮踩坑（已下沉 memory）**：

- **同一天两次踩「读源码/读 SQL 型守卫必须先剥注释」** —— 我在 `onlyoffice_callback_service.py` 的说明注释里写了反例 `int(time.time())`、在 V142 的注释里写了 `ADD COLUMN IF NOT EXISTS` 的说明，两条守卫都把自己的说明文字数成了真实代码。守卫已改为剥注释后再扫（SQL 侧只数非注释行）。
- **`ProjectMember` 类名不存在** —— 平台实际是 `ProjectUser`（表 `project_users`），且带 `SoftDeleteMixin` 必须叠 `is_deleted == false()`。`get_diagnostics` 对错误的类名**零诊断**，只有真实 `import` 才暴露。
- **`WordExportTask` 没有 `year` 列** —— 年度在调用参数里传，不在表上。写 fixture 前必须 `__table__.columns` 实证。
- **`hypothesis` 的 `st.uuids()` 给的是 `UUID` 对象**，`parse_deliverable_doc_key` 返回 `(str, int)` ⇒ 断言要显式 `str(task_id)` 或让 parse 返回 UUID；我选前者（doc_key 本身是字符串域，parse 保持字符串更贴合）。

**回归**：本 spec 作用域 **171 passed / 0 failed**。广域 `-k "onlyoffice or deliverable or writeback or lineage"` 有 59 failed，**全部在 `test_wp_onlyoffice_router.py`（底稿侧 OnlyOffice，非交付中心）**，已用「只把 `onlyoffice_session_limiter.py` / `deliverable_service.py` / `onlyoffice_callback_service.py` / 路由 换成 `git show HEAD:` 版跑同一组」验证 —— 失败集合**逐条相同**（新增 0 / 消失 0）⇒ 预存在基线，与本次改动无关；5 个文件已核实复原。

**V142 已应用到真实库**（`edited_by` / `edited_at` 两列均 nullable=YES，postgres 实证）。

**Wave 2 剩余**：浏览器实测（与 Wave 1 遗留的溯源面板实测合并进 Wave 3 收口时一并做，避免同一页面测三遍）。

### 🔴🔴 Wave 3 开工前的结构性发现（2026-08-04，只读调查，**改变 Wave 3 设计**）

**报告正文有两套并存路径，`report_body_json` 在两者下含义完全不同**，而立项时按 JSON 模式写的需求 9.2 在**默认生效的 Word 模板模式下无落点**：

| | Word 模板模式（**默认生效**） | JSON 模式 |
|---|---|---|
| 入口 | `TemplateFillService.preview_report_body` → `confirm_report_body` | `ReportBodyService.load_body_template` → `render_docx` |
| 开关 | `USE_TEMPLATE_FILL_SERVICE: bool = **True**`（`config.py` 实证） | 上述开关为 False 时 |
| 段落文字存放 | **只在 docx 文件里**；DB 不存 | `report_body_json.sections[].content` |
| `report_body_json` 内容 | 仅 6 个元数据键：`optional_sections` / `guidance_version_path` / `template_version` / `company_subtype` / `template_variant` / `missing_fields` | `{sections: [{section_id, section_name, content, items, section_order}]}` |

**真实库实证（postgres 只读）**：全库唯一一条 `report_body_json`（项目 `0ec33ac9` / 2025）的键集**恰为那 6 个元数据键**，`sections` 键**不存在**（`jsonb_typeof(...->'sections')` 返 `NULL`、长度 0）。

**三条连带推论**：

1. **需求 9.2 当前不可实现** —— `_update_report_body_json` 用 `report.report_body_json = body_json` **整体覆盖**成元数据 dict，任何段落文字都会被下一次 confirm 抹掉。回填「写入对应段落」没有目标字段。
2. **需求 9.6（重新生成后保留人工文字）要求段落文字必须落 DB** —— 只在 docx 里的文字，重新生成必然全丢，这正是立项时用户提出的痛点。故**必须**给 `report_body_json` 增加段落存储，而不是绕过。
3. **顺带发现一处既有缺陷（不在本 spec 范围，已登记）**：`audit_report_service.py:497` 的 KAM 校验读 `body = report.report_body_json or {}` 再取 `sections` —— 在 Word 模板模式下该键恒不存在 ⇒ **结构化主源校验恒空转、永远回退 `paragraphs` 分支**。属报告正文模块的活，本 spec 不改，但 Wave 3 若给 `report_body_json` 补 `sections` 会**顺带让这条校验真正生效**，需一并回归。

**Wave 3 设计调整（已按此推进，与原 design 的差异）**：

- **段落存储改为 additive 键** `report_body_json.sections`（形态对齐 JSON 模式的 `{section_id, section_name, content}`，便于两模式共用读取端与既有 `get_section` / `SECTION_ID_MAP`），**不动**既有 6 个元数据键 ⇒ 既有读取方零回归。
- `confirm_report_body` 在写元数据的同时，从交付 docx 按 `SECTION_ID_MAP` 抽取各段落文字落入 `sections` —— 平台已有 `parse_docx_to_section_ids`（按 `section_name` 在 docx 文本中命中反查 `section_id`）可复用其映射思路。
- 锚点前缀沿用 design 的 `sec_rb_`，`section_code` 取 `SECTION_ID_MAP` 的值（`opinion` / `basis` / `kam` / …），**不用**模板 placeholder 名 —— 后者与附注章节号不是同一命名空间，且 `SECTION_ID_MAP` 已是平台既有真源。
- **派生段落判定（需求 9.4）复用既有 `_is_manual_content`** —— `report_body_service._MANUAL_HINT_RE = r"\[请[^\]]*\]"` 已标记「需人工填写」的内容；其**反面**（不含该标记且由占位符填充产生）即派生段落。签章段 / 责任段等模板固定文字亦不可回填。

**Wave 1 的零回归守卫会因 Task 17 打红，这是预期信号**：`test_deliverable_lineage_zero_regression.py::test_report_body_not_yet_injected` 断言 `template_fill_service.py` 不引用注入符号；Task 17 接锚点后必须把它改为「可见段落文字序列逐字相等」档（需求 12.4 档 2），**不得直接删除**。

### Wave 3 Task 17 已交付（2026-08-04 本会话）

**新建 `backend/app/services/report_body_section_blocks.py`**（报告正文段落定位器，纯函数）+ 接线 `confirm_report_body` + 守卫 `test_report_body_section_blocks.py`（21 例）。

**两条源模板实证事实（判据依据，逐字读 4 份致同模板 + 1 份真实交付件得出）**：

1. **中文序号会漂移** —— 「管理层和治理层对财务报表的责任」在 `模板D-无保留意见-简版` 是 **`三、`**、在 `模板A-无保留意见-简版` 是 **`五、`**（A 版多了「关键审计事项」「其他信息」两节）。故**只能按序号后的名称匹配**，把序号当 section 标识必错。守卫用同一章节的两种序号形态做参数化断言钉死。
2. **docx 标题不带「段」字** —— `SECTION_ID_MAP` 键是 `审计意见段`，模板写 `一、审计意见`。故 `SECTION_NAME_TO_ID` 由 `SECTION_ID_MAP` **派生**（去尾字「段」）而非另抄，守卫断言两者条数与值域一致。**顺带说明既有 `ReportBodyService.parse_docx_to_section_ids` 只在 JSON 模式成立**（它用带「段」的 `section_name` 去 docx 文本里找），对 Word 模板模式的交付件恒不命中。

**真实文件端到端实证（不是合成 docx）**：4 份源模板 + 1 份真实交付件 `audit_report_v13.docx`，扫出章节数分别 4 / 6 / 5 / 3 / 4，`section_id` 全在 `SECTION_ID_MAP` 值域内、无重复、每节都有正文；写锚点后 `可见段落文字序列逐字相等 = True`，锚点可反向扫回。

**🔴 落地时发现并修掉一个真缺陷：报告正文锚点与附注**撞命名空间**。** `write_section_anchors` 原本固定用附注命名器 `anchor_name`（`sec_{code}`），报告正文的 `section_id` 是 `opinion` / `cpa_responsibility` 这类英文标识 → 写出 `sec_opinion`。而附注回填的 `scan_anchor_blocks` 按 `sec_` 前缀收锚点、用 `section_code_from_anchor` 反解 —— **实测它会看见 4 个块，并把 `cpa_responsibility` 反解成伪章节码 `cpa、responsibility`**（正则把首个 `_` 还原成 `、`）⇒ 附注回填会拿报告正文的文字去 `disclosure_notes` 找章节。修法（两处 additive）：

- `write_section_anchors(..., namer=None)` 可注入命名器，默认仍是 `anchor_name`（既有调用方零改动）；
- `section_anchor_utils` 新增 `FOREIGN_ANCHOR_PREFIXES = ("sec_rb_",)`，`scan_anchor_blocks` 跳过这些前缀。`report_body_section_blocks` 在 **import 期 `assert`** 自己的前缀已登记（交叉锁死，不给漂移留窗口）。
- 守卫含**反向自检**：用默认命名器写时附注扫描**必须**能看见（证明隔离不是空转）。

**`report_body_json` 增 additive 键 `sections`**（`[{section_id, section_name, content, section_order}]`，形态对齐 JSON 模式便于两模式共用读取端）；**不动**既有 6 个元数据键。`_update_report_body_json(sections=None)` 时**保留上一版 sections 不清空** —— 否则一次扫描失败就把已回填的人工文字抹掉。

**章节状态落库**：新增 `persist_report_body_section_states`（与附注侧 `persist_note_export_section_states` 并列、共用底层 `snapshot_on_confirm`），fail-open。已在 docstring 写明：报告正文章节的 `source_snapshot_hash` 走的是「空 note + 无科目」的确定性哈希（`compute_source_snapshot_hash` 按 `disclosure_notes`+`trial_balance` 算），**这不是缺陷** —— 报告正文的 stale 判定靠 doc 级 `tb_hash` 第一道闸，真正承载「生成时写了什么」的是 `rendered_block_hash`。

**章节文字口径排除标题** —— 标题是模板固定文字且序号会漂移，纳入会让「换模板变体」被误判成人工编辑。守卫逐模板断言 `heading not in section.text()`。

**Wave 1 留的预期信号已按计划兑现**：`test_report_body_not_yet_injected` 被替换为三条新断言（真实模板可见文字序列不变 / 附注扫描看不见报告正文锚点 + 反向自检 / Task 17 接线正向断言），**不是删掉**。

**回归**：`test_report_body_section_blocks.py` 21 passed · `test_deliverable_lineage_zero_regression.py` 7 passed（原 5，替换 1 增 3）· 附注锚点相关 6 文件 67 passed。广域 `-k "template_fill or report_body or section_anchor or deliverable_lineage or deliverable_section or writeback"` = **64 failed / 757 passed**，64 个失败集中在 **10 个文件、全部 `git status` 干净且零引用本波次任何符号**（`test_{e,f,j,k}_cycle_audit_determination_writeback`：底稿审定表回写 `trial_balance` 的 schema 注册；`test_report_body_validate`：源模板缺 `{{firm_name}}` token —— 实测模板 A 里确实写成了 `{{firm_name}`（少一个右括号）的源模板笔误）⇒ 预存在基线。

**🔴 判归属的方法教训**：本轮先用「把改过的共享文件换成 `git show HEAD:` 版跑同一组」，但 **HEAD 侧 pytest 在收集阶段就崩了**（Wave 3 回退了 `section_anchor_utils`，而 Wave 1/2 新增的测试文件依赖它的新符号）→ 失败集合为空、比对无效且极易被误读成「全是我造成的」。**波次间存在依赖时该方法不适用**，改用「失败测试文件是否引用本次改动的符号 + 是否 `git status` 干净」判定，并逐个看真实报错内容。

### Wave 3 Task 18 / 19 已交付（2026-08-04 本会话，19/25）

**新建 `backend/app/services/writeback_target_adapters.py`**（`WritebackTargetAdapter` 协议 + `DisclosureNoteAdapter` + `ReportBodyAdapter` + `ADAPTER_BY_DOC_TYPE` + `get_writeback_adapter`）+ 主流程五处上游读写全部改走适配器 + 守卫 `test_writeback_target_adapters.py`（17 例）。

**为什么必须抽这层**：`DisclosureNote` 原本硬编码在回填主流程的**五个位置**（提取 / 读上游 / 写上游 / 冲突检测读上游 / 裁决写上游），于是报告正文交付件点回填也去写 `disclosure_notes` —— 其章节标识是 `opinion` 这类英文标识、与附注章节号不是同一命名空间 ⇒ UPDATE 恒 0 行；Wave 1 之前 rowcount 还没检查 ⇒ **静默报「回填成功 N 个章节」**。抽完后主流程零 `DisclosureNote` 引用（守卫源码级钉死，含 import 也不许留）。

**零回归手法**：`__init__` 默认 `DisclosureNoteAdapter`，使**直接调用** `_write_text_content` 的既有测试零改动（抽层前它就是硬编码附注）；`_resolve_adapter` 读不到 `doc_type` 时也回退附注适配器（真正门控在端点层的 400）。附注侧的 `is_deleted == false()` 过滤与 rowcount 语义逐字保留。

**能力矩阵扩到 `audit_report`**：`WRITEBACK_SUPPORTED_DOC_TYPES` 加 `audit_report`（**只加回填、不加章节刷新** —— 刷新需按上游重算章节内容再就地替换，而报告正文内容来自 Word 模板占位符填充，重算等于重新生成整份）。守卫断言「适配器表 ≡ 能力矩阵」，防「矩阵开了但没适配器 ⇒ 端点放行、`get_writeback_adapter` 返 None ⇒ 回填静默返空」。Wave 1 写的两条守卫因此正确打红并已更新期望值（`audit_report` 从 `(False, False)` 改 `(True, False)`、删掉「尚未上线」文案断言）。

**Task 19 派生段落判定 = `DERIVED_REPORT_BODY_SECTIONS`**（`mgmt_responsibility` / `cpa_responsibility` / `signature`），判据来自源模板逐字核对：前两段是**准则规定的标准表述**，A/B/C/D 四份模板逐字相同、只有 `{{company_short_name}}` 一个占位符，改它等于偏离准则用语；`signature` 由 `firm_name`/`report_number`/`report_date` 占位符填充，是数据派生结果。**刻意不含** `opinion`/`basis`/`kam`/`emphasis`/`other_info`/`other_matter`/三个 `*_basis` —— 它们本就是人工撰写、正是回填价值所在；守卫用**反面断言**钉死（若有人把 `kam` 加进派生集合，报告正文回填等于全废）。

**🔴🔴 落地时踩到一个「内存对象看着对、DB 列没写进去」的真坑（本轮最有价值的发现）**：`ReportBodyAdapter.write_upstream` 首版写成「就地改 `sections[idx]["content"]` + 整体重赋值 `report.report_body_json = {**body, "sections": sections}`」。实测（真实 SQLite 往返）：

- `read_upstream` 返回**新值** ✅（走 identity map 读内存对象）
- 而 `SELECT report_body_json` 的**列真值仍是旧值** ❌

**两层坑叠加**：①未声明 `MutableDict` 的 JSON/JSONB 列，就地改嵌套对象不被标脏；②即便随后整体重赋值，由于 `body` 就是 ORM 持有的那个 dict、其嵌套元素已被就地改过，**新值与工作单元记录的旧值 `==` 相等** ⇒ 判「无净变更」⇒ 不发 UPDATE。正解 = **深拷贝构造新 sections**（`[{**sec, "content": new_text} if i == idx else dict(sec) ...]`）。

**这个坑还暴露了我自己守卫的判据不足**：首版反向自检只源码级断言「有整体重赋值 `= {**body`」—— **源码断言通过而 DB 没写进去**。已改为**查 DB 列真值**（绕过 identity map 用 `sa.select(AuditReport.report_body_json)`）+ 源码级断言「不得出现就地改嵌套 dict 的写法」。→ **凡 JSONB 嵌套写入，守卫判据必须是列真值，不能是 ORM 对象、更不能只是源码形态。**

**其他 rowcount 语义**（与附注侧对齐）：`sections` 数组不存在（该版本生成于 Task 17 接线之前）⇒ 返 0 且**不凭空创建数组**；`sections` 里找不到该 `section_id` ⇒ 返 0 且**不新增元素**（如实落 `failed` 让用户重新生成）；同值写入 ⇒ 返 1（与 SQL UPDATE 同值 rowcount=1 对齐）。

**Property 17 已按「只写 report_body_json、DisclosureNote 不变」端到端验证**：同一 session 里同时放一条附注记录，写完报告正文后断言附注 `text_content` 逐字未变、且 `report_body_json` 的既有元数据键（`template_version` / `optional_sections`）未被抹掉。

**fixture 踩坑两处（真实 NOT NULL 约束驱动）**：`audit_report` 的 NOT NULL 无默认列恰为 `project_id`/`year`/**`opinion_type`**；`disclosure_notes.section_title` 也是 NOT NULL。漏了会以 `IntegrityError` 在 flush 时炸（不是断言失败，容易误判成实现问题）。

**回归**：本 spec 作用域 **227 passed / 0 failed**（17 个文件）。CI 后端 job 加挂 Wave 3 一步，`deliverable-lineage-wiring-backend` 现 9 步；YAML 可解析、引用测试文件全部存在。

**Wave 3 剩 Task 20**（报告正文真实链路验收：真实项目生成报告正文 → OO 改一段叙述文字 → 回填 → 查 `report_body_json` 真变 → 重新生成确认保留 → 复原）。

### Wave 3 收口（2026-08-04 本会话，Task 20 真实链路验收 18/18 全 PASS）

**✅ Wave 3 全部 4 项完成（Task 17/18/19/20），spec 进度 20/25。**

新建 `backend/scripts/diagnose/verify_report_body_writeback_live.py`（默认 dry-run，`--apply` 真实写库并**自动按快照复原**）。**在真实库 + 真实交付 docx 上跑生产代码路径**，非合成 docx（本 spec 铁律）。

**实测对象**：项目 `0ec33ac9`（重药控股安徽有限公司_2025）/ 交付件 `98369004`（`doc_type=audit_report`，`status=generated` 非终态）/ 版本 v13 的真实 docx。

| 检查项 | 结果 |
|--------|------|
| 真实交付 docx 扫出章节 | **4 个**：`opinion` / `basis` / `mgmt_responsibility` / `cpa_responsibility` |
| 写入 `sec_rb_*` 段落锚点 | 4 个，全部 `sec_rb_` 前缀 |
| 可见段落文字序列逐字不变（需求 12.4 档 2） | ✅ **103 段**逐字相等 |
| 锚点确实写进 XML | ✅（防上一条空转） |
| 附注回填的扫描器看不见报告正文锚点 | ✅ `scan_anchor_blocks -> 0`（命名空间隔离生效） |
| `/section-states` 非空且锚点一一对应 | 落库 4 段、查得 4 段，`anchor_name == report_body_anchor_name(section_code)` |
| 章节状态携带 `rendered_block_hash` | 非空 **4/4** |
| 生产 `writeback` 分桶正确 | `written=['opinion']` / `failed=['mgmt_responsibility']` |
| **`report_body_json.sections` 的 DB 列真值确实变了** | ✅ 探针文字在 `opinion` 段中（绕过 identity map 直查列值） |
| 派生段落被拒（需求 9.4） | ✅ `mgmt_responsibility` 未被写入探针，日志明确「属派生/模板固定段落，拒绝回填」 |
| **附注 `disclosure_notes` 逐字未被触碰（需求 9.2 SHALL NOT）** | ✅ **322 条附注全部未变** |
| `sections=None` 时保留上一版人工文字（需求 9.6） | ✅ 未提供 sections 时不清空已回填内容 |
| 复原核实 | `report_body_json` 回到原 6 键、本次新增 4 行章节状态已删除（残留 0） |

**postgres 独立复核复原**（脚本自检之外的第二重证据）：`report_body_json` 键集恰为原 6 个且 `? 'sections'` = **False**；`deliverable_section_state` 全表 **0 行**。

**🔴 脚本首版踩的坑（值得记住）**：`word_export_task_versions.file_path` 存的是**相对 `backend/` 的相对路径**（形如 `storage\deliverables\...`，Windows 反斜杠）。按当前工作目录 `Path(file_path).exists()` 在仓库根下必落空 → 首版报「无 audit_report 交付件或版本文件缺失」，**而真实文件是存在的**。已抽 `_resolve_file()` 依次尝试 CWD / `BACKEND_ROOT` / 仓库根。→ 凡从 DB 读文件路径的诊断脚本，都要先确认它是相对哪个根。

**日志层面额外确认了两条设计意图生效**：
- `writeback: 章节 mgmt_responsibility 无块 XML，护栏降级为纯文字分类` —— 报告正文走 `_extract_sections_for` 的非附注分支，护栏按设计降级且**留了 warning**（可观测降级，不是静默失效）。
- `写入影响 0 行（上游报告正文无对应记录）` —— 错误文案已用适配器的 `upstream_label` 拼出「报告正文」而非硬编码「disclosure_notes」。

**Wave 3 剩余（不阻塞）**：`confirm_report_body` 的真实 preview→confirm 往返未测（需要两阶段 preview session，本次以「对真实交付 docx 跑 Task 17 的定位器 + 直接落 sections/章节状态」等价覆盖了 confirm 之后的全部下游链路）；浏览器实测留待 Wave 4 收口时与溯源可视化一并做。

---

### Wave 4 开工前的编号更正

**`drift_report` 迁移必须用 V143，不是 tasks.md Task 21 正文写的 V142** —— V142 已被本 spec **Wave 2** 占用（`V142__deliverable_version_editor_identity.sql`，已应用真实库）。按「迁移版本号永不复用」铁律顺延。本 spec 迁移编号最终为：Wave 1 = **V141**（`rendered_block_hash`）、Wave 2 = **V142**（`edited_by`/`edited_at`）、Wave 4 = **V143**（`drift_report`）。

### Wave 4 Task 21 已交付 + Task 22 后端部分（2026-08-04 本会话，21/25）

产出：**V143 迁移**（`word_export_task_versions.drift_report` JSONB，已应用真实库）+ ORM 列 + 新建 `backend/app/services/financial_report_drift_service.py` + `confirm_deliverable` 前置闸 `_assert_no_report_drift` + 守卫 `test_financial_report_drift.py`（**30 例**）。

**三态判定收敛在 `should_block_confirm`（唯一入口）**：`None`/`{}`（未检测/未配映射）放行 · `{"unavailable": …}`（配置损坏）**fail-closed 阻断** · `{"diffs": [...]}` 非空阻断、**空数组放行**。守卫含两条反向自检：①朴素判据 `if drift_report:` 会把 `{"diffs": []}`（已比对且一致）误判成有差异 ⇒ 配了映射的报表永远确认不了 ②解析失败若 fail-open 放行，弄坏一个配置文件即可绕过需求 10.4 的阻断。

**🔴🔴 真实库实测暴露两个会让本任务变成「死代码 + 误指控」的缺陷（都已修）**：

1. **变体键真源不是 `word_export_task.template_type`** —— 实测全库 **14 个财务报表交付件版本的该字段全部为 NULL** ⇒ 变体键恒为空串 ⇒ `_load_variant_mapping("")` 返 None ⇒ **`detect()` 恒返回 None、检测从不真正运行**（典型的「additive 注入即死代码」）。正解 = 与 `ReportExcelExporter.export` **同口径**：`f"{Project.template_type}_{Project.report_scope}"`（缺省 `soe`/`standalone`）。`cell_mapping.json` 的合法变体键实测只有四个：`listed_consolidated` / `listed_standalone` / `soe_consolidated` / `soe_standalone`。修好后 detect 真跑：**比对 292 个映射格**。

2. **差异不可直接归因为「手工改动」** —— 修好变体键后，真实项目 `0ec33ac9` 报表 v8（**非 stale**，`bound_tb_hash` 与 task 级一致）报出 **22 处差异**，逐个看是**系统性错位**：`应付票据 balance_sheet!C9` 的文件值 20,209,198.18 恰是**应收票据**的余额 ⇒ 属「Cell_Mapping 坐标与该模板变体实际布局不一致」的**配置问题**。在审计平台里把这种情况说成「有人改了报表数字」是**误指控，比不告警更坏**。
   → 文案改为**中性归因**：只陈述「N 处数字与按试算表重算的结果不一致」+ 列出三种可能原因（①上游已变更→重新生成 ②确有手工改动→走调整分录 ③映射与模板布局不一致→配置问题）；另给 `detect()` 加 `stale` 标记（比对版本绑定的 `tb_hash` 与 task 级）作**归因线索而非阻断判据** —— 差异 + stale ⇒ 更可能是上游变更后未重新生成。守卫 `test_block_reason_is_neutral_not_an_accusation` 断言文案不得出现「手工改动共」这类断言式措辞。

**其余落地细节**：
- `_load_report_data` 签名必须实证 —— `(project_id, year, report_types, *, mode)` 三个位置参数缺一不可；首版按 `(project_id, mode=…)` 调用直接抛 `missing 2 required positional arguments`，被 fail-closed 包成「检测不可用」⇒ **会把所有报表版本都误判成阻断**。
- `word_export_task` **无 year 列** → 年度从该项目 `financial_report` 的 `max(year)` 取（那正是 exporter 写入时用的年度）；取不到判「检测不可用」而非静默放行。
- 只比对映射显式声明的 `current`/`prior` 两列（需求 10.7）；公式格 / 文字格 / 空格 / 重算值缺失一律跳过；容差 `0.005` 元（半分 —— 人改数字至少改到分，比它小的只可能是浮点噪声）；带千分符的字符串也能比（人工改动常留字符串）。
- **Property 20（xlsx 无回写通道）**：守卫源码级断言差异服务全文不含对 `TrialBalance`/`AuditReport`/`DisclosureNote` 的 UPDATE/INSERT，且能力矩阵永久禁止 `financial_report*` 回填。

**🔴 迁移里的 `COMMENT ... IS '…:标识符…'` 只能用 `exec_driver_sql` 执行** —— SQLAlchemy `text()` 会把字符串字面量里的 `:原因` 当 bind parameter，实测直接报 `A value is required for bind parameter '原因'`。**MigrationRunner 生产路径已用 `exec_driver_sql`**（其源码注释就写着这条坑），所以迁移本身没问题，是我的临时应用脚本用错了 API。守卫 `test_migration_comment_avoids_text_bind_pitfall` 钉住该前提（并断言本迁移确实含该模式，防空转）。

**回归**：本 spec 作用域 **257 passed / 0 failed**（18 文件）。

**Task 22 剩余（前端）**：交付中心呈现具体报表行与差额 + 「请走调整分录」提示；`detect()` 的调用时机（OO callback 保存 xlsx 后异步触发）与结果落库尚未接线 —— 当前 `drift_report` 列恒为 NULL ⇒ 闸门恒放行（**这正是「additive 列 + 未接线 = 死列」的形态，必须在 Task 22 收口**）。

### Wave 4 收口（2026-08-05 本会话，Task 22~25 全部完成，**25/25**）

**✅ 全部 25 项完成**（Wave 1 11 项 + Wave 2 5 项 + Wave 3 4 项 + Wave 4 5 项）。

#### 22 差异检测接线 + 前端告警

**🔴 接线是本任务的实质**：Task 21 交付的 `FinancialReportDriftService` 当时**零生产调用方** ⇒ `drift_report` 列恒 NULL ⇒ `confirm_deliverable` 的闸门恒放行 —— 典型的「additive 列/服务 + 未接线 = 死代码」（平台已登记多例）。本轮补：

- `OnlyOfficeCallbackService.detect_and_store_report_drift(task, version, baseline_version_no)`：`handle_callback` 保存后调用，`financial_report*` 才跑，结果落 `version.drift_report` 并 flush；检测失败 fail-open（保存已成功，抛出会让 OnlyOffice 认为保存失败并重试）。
- **`None` 照实写 `None` 不写 `{}`** —— 两者虽都放行，但 `{}` 语义是「已检测且无差异」，会让后来者以为检测跑过了。
- `DeliverableVersionSchema` additive 加 `drift_report` / `drift_blocked` / `drift_reason`（`drift_blocked` 由 `should_block_confirm` **唯一入口**判定，前端不得自己写 `if drift_report:`）。
- 前端新建 `DeliverableDriftAlert.vue`（逐行差额表 + 归因 tag + 三种可能原因）+ `deliverableLineageLabels.ts`（标签/可见性判定单一真源），挂在交付中心版本链之上、只对**最新版**告警。

**🔴 关键设计判断：差异检测只挂 OO 保存路径，不挂生成路径。** 报表 xlsx 由 `ReportExcelExporter` 按试算表重算值写出，生成路径天然一致；文件能与重算值分叉的唯一途径就是有人在 OO 里改单元格（`_document_type` 对 `.xlsx` 返 `cell`、`_editor_mode` 对非终态返 `edit`、交付中心编辑入口不按 doc_type 拦 ⇒ 这条路径**真实可达**）。反过来若挂生成路径，`cell_mapping.json` 坐标与模板变体布局不一致时（真实库项目 `0ec33ac9` 报表 v8 实测 22 处系统性错位）刚生成的报表就会被阻断 confirmed —— 把配置问题变成业务阻塞。守卫 `test_detect_not_wired_into_generate_path` 断言全 `backend/app/**` 里 `FinancialReportDriftService` 的引用点**只有** OO 回调，且 `deliverable_service` 只许引用 `should_block_confirm`。

**新增基线归因（回答「差异能不能归因为手工改动」这一问题的数据层解法）**：`detect(..., baseline_version_no=)` 对**被编辑的上一版**跑同一套比对，两侧都存在的差异标 `pre_existing=True`，并给出 `pre_existing_count` / `introduced_count`。`_attribute` 新增 `pre_existing` 结论且**优先于 `manual_edit`** —— 否则「映射坐标错位（既存差异）+ 恰好有人做过在线编辑」会被判成「有人改了报表数字」= 误指控。基线读不到时返 `None` ⇒ **一个标记都不打**（把「基线未知」显示成「本次引入」同样是误指控）。

#### 23 版本链展示快照与中文化

`DeliverableService.get_version_chain_view()` 补三类只能在后端算的字段，路由改走它：

- `bound_tb_hash` + **`is_stale` 三态**（True/False/**None**）—— 任一侧 hash 缺失返 None。退化成布尔会让历史版本（无绑定）一律显示成「与上游一致」= 骗人；守卫含反向自检复现朴素 `bound != task_hash` 的两种错法。
- `edited_by_name` 只来自 V142 的 `edited_by`；`created_by` 在 OO 路径只是回调处理占位（NOT NULL 列无法表达"未知"），拿它当编辑人会让所有在线编辑版本都显示成交付物创建人。解析不出如实显示「编辑人未知」。
- `DeliverableVersionList.vue`：`created_via` 中文标签 + 快照短标识（tooltip 给完整 hash）+ stale/差异徽标 + 编辑人。

**守卫抓出一个真实遗漏**：`created_via` 的**跨前后端交叉锁死**（扫后端全部 `created_via="…"` 实参逐个要求前端有标签）直接打红 —— 后端还会产出 `refresh_stale`（批量刷新全部过期章节，`refresh_all_stale_sections`），我最初只登记了 4 种。这条守卫今后能拦住「后端加来源、前端显示裸英文」。

#### 24 三件套三列对照

后端 `check_trio_consistency` 的 `lagging` / `majority_tb_hash` / `ambiguous` 与 `CompletenessBanner` 三列对照在本波次前序轮次已交付，本轮补 **Property 23 守卫** `test_trio_consistency_lagging.py`（10 例）：严格多数时精确点名滞后类别（三个 doc_type 参数化）；**三类各不相同 / 两类平票 ⇒ `ambiguous=True` 且 `lagging` 必须为空** —— 硬指一类会让审计师重新生成**错的**那一类，比不提示更坏；present < 2 时不判不一致（刚开工不该常亮红）；`tb_hashes` 必须含全部三个键（缺键会让三列对照少一列）。前端另加守卫：三件套中文名与后端 `_TRIO_LABEL` **逐字比对**、前端不得自己数多数、「重新生成这一类」必须复用既有生成通路（自己发 `api.post` 会绕过 `guardGenerate` 权限校验）。

#### 25 列表行级溯源

新建 `DeliverableTraceDrawer.vue`：列表「更多 ▾ → 数据溯源」直接进入，先取 `/section-states` 章节清单再调 `/trace`，**不需要先打开在线编辑器**（`LineagePanel` 依赖 OO 书签跟随光标，是编辑态的主路径；复核态的主路径是列表）。

- **trace 请求与错误处理复用 `useDeliverableLineage`**（504 超时的明确文案已在里面），抽屉自己只调 `section-states`；守卫断言抽屉里不得出现第二份 `/trace` 请求（否则超时文案要写两份、改一处另一处不红）。
- 链条阶段**固定顺序**「附注章节 → 底稿 → 试算表/序时账 → 调整分录 → 其他来源」（需求 11.5），按 `source_type` 归入，**不按 contracts 出现顺序排**；守卫按 `label:` 在源码中的出现位置逐个校验递增。
- 需求 11.6 三处「不得空白」：章节清单为空 → 说明锚点在生成时写入、该交付件可能生成于能力上线前；清单加载失败 → 显示原因；某阶段无匹配 → 显示该阶段专属 `emptyHint`。

#### 回归

- 后端本 spec 作用域 **284 passed / 0 failed**（20 文件）。
- 前端 `src/components/deliverable` **139 passed / 2 failed** —— 2 例是 `OnlyOfficeEditor.spec.ts` 的 iframe 断言，**预存在基线**（该测试文件 `git status` 干净、Wave 1 已用「只换该文件为 HEAD 版跑同一组」验证过）。
- 新增前端守卫 `deliverableLineageDisplay.spec.ts` **29 passed**。
- 8 个前端改动文件 Vite transform 全 **200**。
- CI：`deliverable-lineage-wiring-backend` 12 → **14 步**、`-frontend` 4 → **5 步**；YAML 可解析（117 jobs）且引用的测试文件全部存在。

#### 本轮踩坑（已下沉 memory）

1. **`read_file` 对本会话/并发会话刚改过的文件会返回陈旧内容** —— 我按它返回的版本写 `str_replace` 直接失配（磁盘上 `_attribute` 已存在而返回的版本里没有）。判磁盘真相一律 `python -c "open(p,encoding='utf-8').read()"`。
2. **源码级守卫用裸 `in` 匹配模型名会被同前缀符号骗** —— `'FinancialReport' in src` 被 `FinancialReportDriftService` 命中，Property 20 假红。改 `\bFinancialReport\b` 词边界 + 反向自检（断言差异服务名确实在源码里，证明不是整段为空）。
3. **`User` 的 NOT NULL 无默认列 = `username`/`email`/`hashed_password`/`role`**，列名是 **`hashed_password`** 不是 `password_hash`；写错以 `TypeError: invalid keyword argument` 在**构造时**炸（不是断言失败，容易误判成实现问题）。
4. **测试里读源码前先剥注释**（第三次踩）—— `detect_and_store_report_drift` 的 docstring 大段解释「为什么不挂生成路径」，不剥注释会让 `test_detect_not_wired_into_generate_path` 假红。

#### 剩余（不阻塞验收，需另行安排）

- **浏览器实测**：Wave 1/2/3/4 均未做浏览器层实测（后端真实链路验收已在 Wave 1 的 12/12、Wave 3 的 18/18 完成；Wave 4 的差异检测已在真实库跑过 detect 并比对 292 个映射格）。剩下的是 UI 层肉眼确认：版本链徽标 / 差异告警表 / 三列对照 / 溯源抽屉链条。
- **commit**：本 spec 全部改动尚未提交。
- **Cell_Mapping 坐标错位（真实库项目 `0ec33ac9` 报表 v8 的 22 处系统性错位，如 `应付票据 balance_sheet!C9` 取到应收票据余额）是配置问题，不属本 spec** —— 差异检测已把它诚实报出来并中性归因，修配置需另立工作项（归 `audit-report-template-integration` 侧）。

### Wave 4 修正：差异检测映射保真（2026-08-05 本会话，**推翻上一轮的归因**）

上一轮把真实库那 22 处差异归因为「Cell_Mapping 坐标与模板变体布局不一致的配置问题」并推给 `audit-report-template-integration` 侧 —— **判断错了。那是本服务自身的映射解析缺陷。** 本轮修掉。

#### 根因（逐格实证，不是推断）

`ReportExcelExporter._fill_template` 的填充口径是「**逐 sheet** 扫内联 `{{row:CODE:current|prior}}` 占位符，该 sheet 没有内联占位符才回退 `cell_mapping.json` 坐标」。而资产负债表在**四个变体里都拆成「主表 + 续表」两个 sheet**（`_resolve_sheets` 对 alias 为列表时返回全部匹配），偏偏 `cell_mapping.json` 里主表与续表的 row_code **共用同一个 `sheet` 键 `balance_sheet`、坐标还重叠**：

| | 主表 | 续表 |
|---|---|---|
| soe `C6` | `BS-002 货币资金` | `BS-055 短期借款` |
| soe `C11` | `BS-007 应收票据` | `BS-060 应付票据` |
| soe `C12` | `BS-008 应收账款` | `BS-061 应付账款` |

exporter 靠逐 sheet 扫占位符区分，填的是对的；而 `read_sheet_values` 按 `sheet_aliases` **只取第一个匹配 sheet**（`next((wb[n] for n in candidates ...))`）⇒ 续表的 **49 个** row_code 全去主表取值 ⇒ 报出「应付票据拿到应收票据余额」。真实库项目 `0ec33ac9` 报 22 处 = 这 49 处里两侧都有重算值的那部分。

**判据来源**：openpyxl 直读四份真实模板，逐条比对「JSON 的 `row_name`」与「模板同行 A 列文字」，`soe_standalone` 报 **49 处不符**，且不符项恰为 `BS-055` 起的续表行。

#### 修法

映射解析改为与 exporter 同源，新增三件：

- `CellSpec(sheet, row_code, row_name, period, coord)` —— `sheet` 存**交付件真实 sheet 名**（`1,2-资产负债表(企财01表）续`），不再是 JSON 的 `sheet` 键。
- `resolve_expected_cell_specs(template_key)` —— **复用** exporter 自己的 `_load_template` 与 `_resolve_sheets`（都不用 db，抄一份等于给漂移留口子），逐 sheet 走 `scan_worksheet_row_placeholders`（内联为权威），无内联才回退该 sheet 的 JSON 条目。
- `read_values_for_sheets(xlsx, sheet_titles)` 取代 `read_sheet_values` —— 按真实 sheet 名取值，**旧函数已删**（守卫钉死不得复活，防两份口径并存）。

`compare_cells` 保留为 **JSON 口径薄壳**（既有 30 例守卫在用），内部转 `CellSpec` 后委托 `compare_cell_specs` ⇒ **比对逻辑只有一份**。

**刻意保住需求 10.6**：JSON 解析失败仍 fail-closed（`_load_variant_mapping` 抛 `DriftUnavailable` 直接上传）。一度想改成「JSON 坏了就只用内联占位符」，随即撤回 —— 那样只需弄坏配置文件，「无内联占位符的 sheet」就会静默退出比对面 = 正是 10.6 要堵的后门。

#### 真实库验收（修复的判据，不是单测）

| 对象 | 修复前 | 修复后 |
|---|---|---|
| `0ec33ac9` 报表 v8（listed_standalone） | 22 处「系统性错位」 | **5 处**，`checked=292` |
| `2aa00f57` 报表 v2（soe_standalone） | 成片假差异 | **`checked=452` / `diffs=0` 完全一致** |
| 四变体映射解析 | 主表续表共用键 | 同一 `(sheet, 坐标)` 撞多个 row_code = **0** |

剩下 5 处**逐格核对确认是真差异**：五个 row_code 的 `row_name` 与模板同行 A 列**逐字一致**（`BS-045 交易性金融负债 @ 资产负债表续!C7`、`BS-048 应付账款 @ C10`、`BS-049 预收款项 @ C11`、`BS-054 其中：应付利息 @ C16`、`BS-070 递延所得税负债 @ C32`），零多坐标、零撞码；`stale=True` / `attribution=upstream_changed` 也吻合（上游在生成后变过）。这正是检测器该报的。

#### 真实库跑 detect 时暴露的第二个真 bug（已修）

`_attribute` 里 `db_updated > ver.created_at` 抛 **`TypeError: can't compare offset-naive and offset-aware datetimes`**（`financial_report.updated_at` 是 naive、`WordExportTaskVersion.created_at` 侧为 aware），而该比较**在 `try` 之外** ⇒ 异常冒泡出 `detect()` ⇒ 被 `detect_and_store_report_drift` 的 `except Exception` 吞成 warning ⇒ **`drift_report` 又变恒 None、整个检测重新变死**。这是「fail-open 把 bug 伪装成无数据」的同族，**只有真实库能暴露**（单测的 fixture 时间戳同源，不混用）。修法 = 抽 `_as_utc` / `_is_later` 做时区归一，守卫含「裸比较确实会抛」的反向自检。

另把「无法确定报表年度」的文案改准确 —— 真实库该分支命中的是「交付件文件在、但项目里一条 `financial_report` 都没有」（`44925324` / `df5b8403` 的 v2~v4），这种报表数字来源不可追溯，阻断进 confirmed 是审计上正确的，文案改为指向「请先重新生成报表」。

#### 守卫

新建 `backend/tests/test_financial_report_drift_mapping.py`（**24 例**），判据全落在**真实模板文件**上（这个缺陷的成因正是「真实模板拆了主表续表」，合成 fixture 测不出来）：

- 同一 `(sheet, 坐标)` 不得对应多个 row_code（错位的直接判据）× 四变体
- 主表/续表必须是不同 sheet 名 × 四变体
- 每个 spec 的 `row_name` 与模板同行 A 列一致（语义判据，`checked > 50` 防空转）× 四变体
- **反向自检**：复现旧口径（按 JSON `sheet` 键）**必须**撞码，并具体钉住 `(balance_sheet, C6) ⊇ {BS-002, BS-055}` —— 若哪天 JSON 分了键，这条会提醒把自检改成正向断言而不是删掉
- `read_sheet_values` 必须已删除；`detect()` 源码级必须走 specs 三件套
- JSON 解析失败仍 fail-closed；未配变体返 None 不抛
- 薄壳与 `compare_cell_specs` 结果一致；同坐标不同 sheet 各取各值
- `_is_later` 时区三态 + 「裸 `>` 确实抛」自检
- 行名归一只去空白与行业适用性标记 `△▲※*`（实测 `IS-027` 是 JSON 带 `△`、模板不带），配 `test_label_norm_still_catches_real_misalignment` 钉住「归一化没宽到放过真错位」

**变异检验**：把 `CellSpec(sheet=ws.title)` 退回 `sheet=report_type`（复现旧口径）⇒ **12 例精确打红**（三条核心断言 × 四变体），源码已 `finally` 还原并独立探针核验零残留。

#### 回归

- 本 spec 作用域 **308 passed / 0 failed**（21 文件，原 284 + 新 24）。
- `-k "cell_mapping or report_excel or financial_report or report_export"` **123 passed / 1 skipped** —— 复用了 exporter 私有方法（只读），导出侧零回归。
- CI backend job 14 → **15 步**（新增映射保真 + exporter 回归两步；YAML 117 jobs 可解析、引用文件全在）。

#### 遗留更正

上一轮写的「22 处映射错位属配置问题，归 `audit-report-template-integration` 侧另立工作项」**作废** —— 它是本服务的缺陷且已修完。真实库现存的 5 处是真差异，由检测器如实报出并中性归因，不需要另立工作项。
