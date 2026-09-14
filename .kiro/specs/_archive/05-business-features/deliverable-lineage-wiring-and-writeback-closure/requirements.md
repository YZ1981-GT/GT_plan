# Requirements Document

## Introduction

交付中心（`DeliverableCenter`）与报表、附注、报告正文三个上游模块的**正向生成链路**已完整可用；但**反向链路**（章节溯源 / stale 增量刷新 / OnlyOffice 回填）在生产环境整条空转。2026-08-04 只读调查实证：

| 缺陷 | 实证位置 | 后果 |
|------|----------|------|
| `write_section_anchors` / `snapshot_on_confirm` 零生产调用方 | `section_anchor_utils.py:72` / `deliverable_section_state_service.py:168`（全仓 `backend/app/**` 只有定义） | `deliverable_section_state` 表恒空 → `/section-states` 返空 → 溯源面板章节下拉空 |
| 交付 docx 无任何定位锚点 | `note_word_exporter.export` step 7 `remove_section_markers` 清掉 `##SECTION:`；内容控件灰度默认 False | `writeback` 的 `scan_section_blocks` 得 `{}` → 「回填到附注模块」永远返回全空且不报错；`refresh_section` 恒走「锚点丢失 skip」 |
| OO 手工保存重新绑定当前 `tb_hash` | `onlyoffice_callback_service.handle_callback` → `deliverable_service.py:364` | 改个错别字即把 stale 与三件套不一致信号洗白，而内容从未按新试算表重算 |
| 回填只写 `DisclosureNote` 且不查 rowcount | `deliverable_writeback_service._write_text_content` | 报告正文 / xlsx 报表也显示「回填」按钮，UPDATE 0 行仍 Toast「已成功回填 N 个章节」 |
| 合规护栏 `_classify_change` 未接主流程 | `deliverable_writeback_service` 第 4a 步硬编码 `kind=TEXT` | `rejected` 恒空、被拒变更留痕（原需求 9.3）从未产生 |
| `_detect_user_edits` 哈希域不匹配 | `sha256(块内纯文本)` vs `sha256(json{section_code,text_content,table_data,audited_amounts})` | 两哈希域不同 ⇒ 永远不等 ⇒ `refresh_section` 恒 `requires_confirm=True` |
| `doc_key` 带时间戳 | `onlyoffice_callback_service.build_editor_config` | 每次请求 config 都是新文档 ⇒ 协同编辑失效、后保存者静默覆盖 |
| OO 编辑版本作者记成交付物创建人 | `deliverable.py` `creator_id = task.created_by` | 版本链与审计日志的操作人失真 |
| `refresh_section` 内容追加到文末 | `_insert_refreshed_content` 用 `doc.add_paragraph`（注释自承认） | 刷新后该章节被挪到文档最后 |

**前序 spec `deliverable-lineage-and-writeback` 22/22 全绿 + 28 条属性测试全绿是假绿** —— 测试自行合成带锚点的 docx 再验证，从不检查生产导出路径是否调用锚点写入。故本 spec 的验收判据一律以**真实生成的交付件 + 真实库**为准，禁止用合成 docx 顶替。

本 spec 分四波收口：Wave 1 接线（让已建成的跑起来）→ Wave 2 留痕正确性 → Wave 3 报告正文回填 → Wave 4 xlsx 差异告警 + 溯源可视化。

**红线（不得触碰）**：正向生成链路（`ReportExcelExporter` / `NoteWordExporter` 可见输出 / `TemplateFillService` / `FullDeliverablesExecutor` 步骤顺序）逐字节零回归；财务报表 xlsx **不做**单元格级双向回写。

## Glossary

| 术语 | 定义 |
|------|------|
| Section_Anchor | 交付 docx 中标识章节区间的隐藏书签，名 = `anchor_name(section_code)`（`八、1` → `sec_八_1`），`bookmarkStart` 在块首标记前、`bookmarkEnd` 在块尾标记后 |
| Anchor_Block | 由一对 `sec_*` 书签界定的 body 级元素区间（`w:p` / `w:tbl`），标记清理后仍可定位 |
| Content_Control | Block 级 `w:sdt`，`Tag = anchor_name(section_code)`，供 OnlyOffice 连接器 `onChangeContentControl` 实现光标跟随溯源 |
| Rendered_Block_Hash | 生成/刷新时写入块内的规范化文字的 sha256，用于精确区分「用户人工编辑」与「上游数据变化」 |
| Snapshot_Ref | `word_export_task.source_snapshot_refs`，含 `tb_hash`，是 stale 与三件套一致性判定的基准 |
| Writeback_Guardrail | 回填合规护栏：表格数字、章节标题一律拒绝写回并留痕，仅叙述性文字允许回填 |
| Cell_Mapping | `audit-report-template-integration` 产出的报表行 ↔ xlsx 单元格显式映射（`cell_mapping.json`） |

## Requirements

### 需求 1：导出路径写入 Section_Anchor 并落章节状态

**User Story:** 作为审计助理，我希望生成的附注交付件自带章节定位能力，这样溯源面板才能列出章节、刷新与回填才有定位依据。

#### Acceptance Criteria

1. WHEN 附注以 template 模式导出时，THE 系统 SHALL 对每个**保留**章节写入 Section_Anchor，且被裁剪删除的章节 SHALL NOT 写入锚点。
2. THE 锚点写入 SHALL 发生在 `{{seq:}}` 填充之后、标记清理之前，使 `remove_section_markers` 清理后锚点区间恰好覆盖章节内部内容。
3. THE 锚点写入 SHALL NOT 改变文档可见文字与段落顺序。
4. WHEN 附注交付件落库成新版本后，THE 系统 SHALL 为每个保留章节 upsert `deliverable_section_state`，写入 `source_snapshot_hash`、`anchor_name`、`version_no`，并清 `is_stale`。
5. THE 接线 SHALL 覆盖两条生产导出入口：`render_disclosure_notes` 路由与 `FullDeliverablesExecutor._run_disclosure_notes`。
6. WHERE 章节状态落库失败，THE 系统 SHALL 记录 warning 并完成导出（fail-open，不阻断已生成的交付件）。
7. THE `NoteWordExporter.export` 既有签名与返回值 SHALL 保持不变（新能力以 additive 方法暴露），使既有调用方零改动。

### 需求 2：标记清理后的锚点定位能力

**User Story:** 作为系统，我需要在标记已被清理的交付 docx 上定位章节区间，这样回填与刷新才能工作在真实交付件上。

#### Acceptance Criteria

1. THE 系统 SHALL 提供纯函数按 Section_Anchor 扫描 Anchor_Block，返回 `section_code` 与区间内 body 级元素。
2. WHEN 交付 docx 既无标记也无锚点时，THE 扫描 SHALL 返回空列表且不抛异常。
3. THE 回填与刷新 SHALL 优先使用 Anchor_Block 定位，仅当无锚点时回退 `##SECTION:` 标记扫描（兼容存量交付件）。
4. THE 锚点区间 SHALL 在 OnlyOffice 保存往返后仍可被 python-docx 按名定位。
5. WHERE 同一 `section_code` 出现多个锚点，THE 扫描 SHALL 取首个并记录 warning，不得静默合并。

### 需求 3：内容控件灰度开启

**User Story:** 作为审计助理，我希望在 OnlyOffice 里把光标放到某段就能看到它的数据来源。

#### Acceptance Criteria

1. THE 后端内容控件注入 SHALL 默认开启，使交付 docx 每节内部内容包在 `Tag = anchor_name(section_code)` 的 Block Content Control 中。
2. THE 注入 SHALL NOT 改变文档可见文字与段落顺序，且注入失败 SHALL 不阻断导出。
3. THE 开闭标记 SHALL 保留在 body 级，使 `remove_section_markers` 仍能正常清理。
4. THE 前端自动跟随（`AUTO_FOLLOW_ENABLED`）SHALL 保持默认关闭，直至连接器经真实 OnlyOffice 实测通过。
5. THE 既有 characterization 测试 SHALL 显式指定开关值，不依赖默认值，使默认翻转不产生假红。

### 需求 4：人工编辑检测与就地刷新

**User Story:** 作为现场经理，我希望单章节刷新只替换该章节且不误伤我的人工润色。

#### Acceptance Criteria

1. THE 系统 SHALL 记录 Rendered_Block_Hash（生成/刷新时写入块内文字的规范化 sha256）。
2. WHEN 块内文字的规范化 sha256 等于 Rendered_Block_Hash 时，THE 系统 SHALL 判定无人工编辑并直接刷新。
3. WHEN 二者不等时，THE 系统 SHALL 返回 `requires_confirm=True` 并列出待确认章节，不写入任何内容。
4. WHERE Rendered_Block_Hash 缺失（存量交付件），THE 系统 SHALL 判定无人工编辑（fail-open，与引入前行为一致）。
5. THE 刷新后内容 SHALL 插入在原章节的**原位置**（锚点区间内），不得追加到文档末尾。
6. THE 刷新 SHALL 保留该章节的 Section_Anchor 与 Content_Control 可定位性。
7. THE 刷新成功后 SHALL 更新该章节的 `source_snapshot_hash`、Rendered_Block_Hash 并清 `is_stale`。

### 需求 5：回填写入必须真实生效

**User Story:** 作为审计助理，我不希望系统告诉我「已成功回填」而数据库里什么都没变。

#### Acceptance Criteria

1. WHEN 回填写入影响 0 行时，THE 系统 SHALL NOT 将该章节计入 `written`，SHALL 计入失败清单并给出可读原因。
2. THE 回填响应 SHALL 区分 `written` / `rejected` / `conflicts` / `skipped` / `failed` 五类，前端 SHALL 分别呈现。
3. WHEN 全部章节均写入失败时，THE 系统 SHALL 返回明确失败提示而非成功 Toast。
4. THE 冲突裁决写回 SHALL 同样校验影响行数，0 行时不更新基线 hash。
5. THE 回填 SHALL 在写入前后经 `TraceEventService` 留痕（含 before/after 与 content_hash），且留痕失败不阻断主业务。

### 需求 6：回填与刷新入口按交付件类型门控

**User Story:** 作为审计助理，我不希望在财务报表 xlsx 上看到「回填到附注模块」按钮。

#### Acceptance Criteria

1. THE 回填面板 SHALL 仅对支持回填的 `doc_type` 渲染，其余类型不渲染入口。
2. THE 刷新按钮 SHALL 仅对支持章节刷新的 `doc_type` 渲染。
3. WHEN 交付件无任何章节状态时，THE 溯源面板 SHALL 显示「本交付件无章节锚点」提示，而非空白下拉。
4. THE 后端回填端点 SHALL 对不支持的 `doc_type` 返回明确错误，不依赖前端门控。
5. THE 门控 SHALL 由单一真源声明支持矩阵，前后端共同引用，禁止各写一份。

### 需求 7：OO 编辑版本的留痕正确性

**User Story:** 作为质量控制复核合伙人，我需要版本链如实反映「谁在什么时候基于哪份数据做了什么」。

#### Acceptance Criteria

1. WHEN OnlyOffice 回调保存产生新版本时，THE 系统 SHALL 继承上一版的 Snapshot_Ref，SHALL NOT 重新捕获当前 `tb_hash`。
2. THE OO 编辑版本 SHALL 记录实际编辑人与编辑时间，SHALL NOT 用交付物创建人近似。
3. WHERE 回调未携带可识别的编辑人，THE 系统 SHALL 如实记为未知并写 warning，不得伪装成创建人。
4. THE 文档标识（`doc_key`）SHALL 由 `task_id` 与 `version_no` 确定性派生，SHALL NOT 含时间戳。
5. THE 编辑席位计数 key SHALL 与 `doc_key` 同源，使占用与释放成对。
6. THE 版本链查询 SHALL 返回 `created_via`、绑定 `tb_hash`、编辑人，供前端展示。

### 需求 8：合规护栏接入主流程

**User Story:** 作为业务合伙人，我要求任何被拒绝的回填变更都有留痕，便于事后审计。

#### Acceptance Criteria

1. THE 回填主流程 SHALL 调用护栏分类，SHALL NOT 硬编码为纯文字变更。
2. WHEN 变更落在表格数字上时，THE 系统 SHALL 拒绝写回并留痕，且拒绝原因 SHALL 指向调整分录路径。
3. WHEN 变更落在章节标题上时，THE 系统 SHALL 拒绝写回并留痕。
4. THE 被拒变更 SHALL 出现在响应的 `rejected` 中并带可读原因。
5. THE 护栏判定 SHALL 按块内 XML 结构定位，SHALL NOT 用正则猜测。

### 需求 9：报告正文段落级回填

**User Story:** 作为业务合伙人，我在 Word 里润色的审计意见与关键审计事项，不应在下次重新生成报告正文时全部丢失。

#### Acceptance Criteria

1. THE 报告正文交付件 SHALL 在生成时写入段落级锚点，锚点标识由模板 section/placeholder 标识派生。
2. WHEN 回填报告正文时，THE 系统 SHALL 写入 `AuditReport.report_body_json` 的对应段落，SHALL NOT 写入 `DisclosureNote`。
3. THE 报告正文回填 SHALL 复用既有三方比对冲突框架（出品物值 / 上游值 / 生成时基线）。
4. THE 系统 SHALL 拒绝回填由数据派生的段落（金额、日期、主体名称等占位符填充结果）并留痕。
5. WHEN 报告正文处于终态时，THE 回填 SHALL 被拒绝。
6. THE 回填后重新生成报告正文 SHALL 保留已回填的人工文字。

### 需求 10：xlsx 报表手工改动差异告警

**User Story:** 作为质量控制复核合伙人，我需要知道有人在报表 xlsx 里手工改了数字。

#### Acceptance Criteria

1. THE 系统 SHALL NOT 提供财务报表 xlsx 的单元格级回写能力。
2. WHEN OO 保存产生 xlsx 新版本时，THE 系统 SHALL 按 Cell_Mapping 覆盖的单元格比对文件值与按试算表重算值。
3. WHEN 存在不一致时，THE 系统 SHALL 在交付中心以告警呈现具体报表行与差额，并提示走调整分录。
4. WHEN 存在不一致时，THE 该版本 SHALL NOT 进入 `confirmed` 状态。
5. WHERE Cell_Mapping **文件不存在**（该报表类型确实未配映射），THE 系统 SHALL 记录 warning 并放行（fail-open），不得阻断交付。
6. WHERE Cell_Mapping **文件存在但解析失败**（配置损坏），THE 系统 SHALL 判定为检测不可用并**拒绝该版本进入 `confirmed`**，提示修复映射配置 —— 不得以 fail-open 放行，否则只需弄坏一个配置文件即可绕过需求 10.4 的阻断。
7. THE 比对 SHALL 只覆盖 Cell_Mapping 显式声明的单元格，文字性单元格不参与数字比对。
8. THE `drift_report` SHALL 区分三态：`null`（未检测/映射缺失，放行）、`{"unavailable": reason}`（解析失败，阻断）、`{"diffs": [...]}`（差异清单，非空即阻断）。

### 需求 11：溯源可视化

**User Story:** 作为审计助理，我希望在交付中心直接看到每一版绑定的数据快照与上游链条。

#### Acceptance Criteria

1. THE 版本链 SHALL 以中文展示 `created_via`（生成 / 在线编辑 / 章节刷新 / 回填），禁止裸英文值。
2. THE 版本链 SHALL 展示该版绑定的 `tb_hash` 短标识、编辑人与 stale 徽标。
3. THE 三件套一致性 SHALL 以三列对照呈现各自绑定的 `tb_hash`，并指出滞后的类别。
4. WHEN 某类滞后时，THE 系统 SHALL 提供直接重新生成该类的入口。
5. THE 交付件列表每行 SHALL 提供溯源入口，展示「交付件 → 附注章节 → 底稿 → 试算表 → 调整分录」链条。
6. WHERE 溯源查询超时或无匹配，THE 前端 SHALL 显示明确原因，不得空白。

### 需求 12：真实链路验收与零回归

**User Story:** 作为用户，我要求「已完成」意味着真实环境里链路真的通了。

#### Acceptance Criteria

1. THE 验收 SHALL 以真实生成的附注交付件为对象，`/section-states` 返回非空且 `anchor_name` 与 `section_code` 一一对应。
2. THE 验收 SHALL 在真实库上回填一段文字后确认 `disclosure_notes.text_content` 真实变化，并在验收后复原测试数据。
3. THE 验收 SHALL NOT 以合成 docx 的单元测试顶替真实链路验证。
4. THE 正向生成链路 SHALL 零回归，判据按是否注入不可见元素分两档：
   - 报表 xlsx SHALL 与改动前**逐字节等价**（本 spec 不往 xlsx 注入任何元素）。
   - 附注 docx 与报告正文 docx SHALL 保持**可见段落文字序列逐字相等**（二者均注入锚点，报告正文自 Wave 3 起注入，故逐字节等价不成立；须显式验证可见内容不变、且锚点/控件为不可见元素）。
5. THE 每处修复 SHALL 配反向自检：复现旧行为时守卫必须打红。
6. THE 迁移 SHALL 幂等（`IF NOT EXISTS`）并配三层一致契约测试（DDL + ORM + service）。
