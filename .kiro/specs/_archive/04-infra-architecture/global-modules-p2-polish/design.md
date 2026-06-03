# 设计文档：global-modules-p2-polish（全局模块 P2/P3 体验与性能增强）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§九 P2-9~13 + 各模块 P2/P3 + §二十四 覆盖度对照）
> 定位：6 个核心 spec（A~F）落地后的体验/性能批次，把文档**所有未纳入的 P2/P3 项**收进来，实现文档 100% 覆盖
> 工作流：Design-First（HLD + LLD）

---

## 一、概述（Overview）

A~F 六个 spec 覆盖了文档全部 P0+P1 核心（单源/联动/澄清/关键功能）。本 spec 收口剩余 **P2 体验性能 + P3** 项（§二十四对照表"未纳入"区，外部依赖 diff 去 mock 除外），实现盘点文档改进项 100% 落地。

这些项的共性：**非地基、不卡外部、增量提升体验/性能**，互相独立可分批。统一放一个 spec 避免散落多个微 spec。

收口 7 项（实证锚点已核对）：
1. 地址库 Redis 二级缓存（§九 P2-9 / §一 P2）
2. 地址有效性校验接入公式保存流（§一 P2，validate_formula_refs 已实现需接线）
3. 公式变更时间线 UI + 一键回滚（§九 P2-10，复用时光机 + A 的哈希链留痕）
4. 高级查询结果 Redis 缓存 + 大结果集流式导出（§九 P2-11 / §三 P2/P3）
5. note_template 大文件按章节 DB 化（§九 P2-12 / §六 P2）
6. 枚举字典扩展核心业务枚举（§九 P2-13 / §四 P2）
7. enum_dict_overrides 入 D6 + content_text 填充保障（§四 P3 / §七 P2）

**前置依赖**：第 3 项依赖 spec A（公式审计哈希链 formula.changed）；第 6/7 项与 spec F（枚举注释 + 懒建表）同模块但不冲突。建议 A~F 落地后启动。

---

## 二、各项设计（代码实证锚点）

### P2-1：地址库 Redis 二级缓存

**现状**：`AddressRegistryService`（`address_registry.py`）用模块级单例 `_slots: dict[str, _CacheSlot]` 内存缓存（key=`project:year:template_type:domain`，按域 TTL + LRU 500 槽）。重启丢缓存，多 worker 各建一份。

**方案**：`get_domain`/`get_all` 取数前先查 Redis（key 同 _slot_key），命中则反序列化 AddressEntry；未命中走 DB 构建后回写 Redis（TTL 对齐现有按域 TTL）。`invalidate`/`invalidate_all` 同步删 Redis key。内存 _slots 保留为 L1、Redis 为 L2（冷启动/多 worker 共享）。

### P2-2：地址有效性校验接入公式保存流

**现状**：`validate_formula_refs(db, project_id, year, formula, template_type)` 已实现（`address_registry.py`）+ 有 router `/invalidate` 同款入口，但公式**编辑保存时未强制调用**。

**方案**：公式保存端点（report_config update / 公式管理保存）保存前调 `validate_formula_refs`，存悬空引用则拒绝（返校验错误）。与 spec A 需求 7.5「内核 validate_formula 接 address_registry」呼应——A 在内核层校验语法+地址，本项在保存流强制拦截。

### P2-3：公式变更时间线 UI + 一键回滚

**现状**：spec A 已把公式变更留痕收口哈希链（formula.changed）；时光机 `time_machine_service`（RFC 6902 jsonpatch）已有。但前端公式管理无"历史 Tab + 回滚"。

**方案**：FormulaManagerDialog 加"历史"Tab，查 formula.changed 留痕（spec A 的 GET 端点）展示时间线；一键回滚复用时光机 / 写回 old_formula。**依赖 spec A 完成**。

### P2-4：高级查询 Redis 缓存 + 流式导出

**现状**：`custom_query.py`（业务视图）+ `query_builder.py`（白名单 DSL，openpyxl 全量导出）。

**方案**：①高频相同查询（dashboard 卡片）结果加 Redis 短 TTL 缓存（query hash 为 key）②query_builder 大结果集 Excel 改流式/分页构建（避免 openpyxl 全量内存峰值）。③高级查询本就最健康 🟢，仅性能增强不动安全模型。

### P2-5：note_template 大文件按章节 DB 化

**现状**：`disclosure_engine._load_templates` 按 template_type 从 `note_template_{soe,listed}.json`（540KB/919KB）整文件加载；disclosure_notes 表已有 section 粒度；section_id 已重构。

**方案**：note_template 按章节拆分存 DB（复用 section_id 主键），`_load_templates` 改读 DB（JSON 作种子导入 + 降级）。避免整文件重写冲突（多人协作）。**注**：改动面较大，需评估是否值得（与 §五 registry↔JSON 边界一并考虑）。

### P2-6：枚举字典扩展核心业务枚举

**现状**：`_DICTS`（system_dicts.py）10 类状态枚举；`EliminationEntryType`（consolidation_models.py）/ 审计循环代号 A~N / ReviewStatusEnum 等散在 model。

**方案**：把高频展示业务枚举（EliminationEntryType / 审计循环代号 / 风险等级）纳入 `_DICTS`（value 仍硬编码锁死，仅 label/color 可治理）。与 spec F 的 F4（修 _DICTS 注释）同文件不冲突。

### P2-7：enum_dict_overrides 入 D6 + content_text 填充

**现状**：enum_dict_overrides 表疑似靠 create_all（§四 P3）；KnowledgeDocument.content_text 填充率未知（§七 P2，PDF/docx 是否提取）。

**方案**：①enum_dict_overrides 写 V0XX 迁移入 D6（三层一致）②知识文件导入 PDF/docx 复用 **OCR/MinerU 全文识别**（`mineru_service.recognize_for_ocr` 返回 `{"text": 完整文本}`，非 `wp_document_recognizer`——后者是 LLM 结构化字段提取 DocType.VOUCHER 等，不产 content_text 全文）提取 content_text（保障 spec B 的向量索引有内容）。

---

## 三、实施阶段（~5 人天，A~F 后启动）

- 阶段 1（~1.5 天）：P2-1 地址库 Redis 缓存 + P2-2 校验接保存流
- 阶段 2（~1 天）：P2-3 公式时间线 UI（依赖 A）+ P2-6 枚举扩展（与 F 协调）
- 阶段 3（~1.5 天）：P2-4 高级查询缓存 + 流式导出
- 阶段 4（~1 天）：P2-5 note_template DB 化（评估后）+ P2-7 enum_dict 入 D6 + content_text

---

## 四、正确性属性（PBT 守护）

- **P1 缓存一致**：地址库 Redis L2 与 DB 构建结果一致；invalidate 后 Redis+内存同步失效
- **P2 校验拦截**：含悬空引用的公式保存被拒（validate_formula_refs 返非空）
- **P3 枚举锁死**：扩展进 _DICTS 的业务枚举 value 不可改（仅 label/color）
- **P4 流式导出等价**：大结果集流式导出内容与全量导出一致（仅内存峰值降低）
