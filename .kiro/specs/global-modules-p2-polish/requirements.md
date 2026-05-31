# 需求文档：global-modules-p2-polish（全局模块 P2/P3 体验与性能增强）

> 关联调研：#[[file:docs/proposals/global-modules-status-and-improvement-2026-05-31.md]]（§九 P2-9~13 + §二十四 覆盖度对照）
> 工作流：Design-First（从 design.md 派生反推）
> 设计：#[[file:.kiro/specs/global-modules-p2-polish/design.md]]
> **前置**：A~F 六个核心 spec 落地后启动；本 spec 实现文档改进项 100% 覆盖（外部依赖 diff 去 mock 除外）

## 引言

A~F 六 spec 覆盖文档全部 P0+P1 核心。本 spec 收口剩余 P2 体验性能 + P3 项，让盘点文档改进项 100% 落地。这些项非地基、不卡外部、增量提升体验/性能，互相独立可分批。

## 需求

### 需求 1：地址库 Redis 二级缓存

**用户故事**：作为系统，我希望地址库缓存多 worker 共享、重启不丢，避免每 worker 冷启动各自全量重建。

#### 验收标准

1. WHEN `get_domain`/`get_all` 取数 THEN 先查 Redis（key 同 _slot_key `project:year:template_type:domain`），命中反序列化返回
2. WHEN Redis 未命中 THEN 走 DB 构建后回写 Redis（TTL 对齐现有按域 TTL）
3. WHEN `invalidate`/`invalidate_all` THEN 内存 _slots 与 Redis key 同步失效
4. IF Redis L2 命中 THEN 结果与 DB 构建一致

### 需求 2：地址有效性校验接入公式保存流

**用户故事**：作为审计师，我保存含悬空引用的公式时系统拒绝，避免存入无效引用。

#### 验收标准

1. WHEN 公式保存端点（report_config update / 公式管理保存）THEN 保存前调 `validate_formula_refs`
2. IF 公式含悬空引用 THEN 拒绝保存并返校验错误
3. WHEN 与 spec A 配合 THEN A 在内核层校验语法+地址，本项在保存流强制拦截（互补）

### 需求 3：公式变更时间线 UI + 一键回滚

**用户故事**：作为审计师，我希望在公式管理看到某公式的变更历史并能一键回滚。

#### 验收标准

1. WHEN FormulaManagerDialog 打开 THEN 有"历史"Tab 查 formula.changed 留痕（spec A 的 GET 端点）展示时间线
2. WHEN 点一键回滚 THEN 写回 old_formula（复用时光机 / spec A 留痕）
3. IF spec A 未完成 THEN 本需求阻塞（依赖哈希链 formula.changed）

### 需求 4：高级查询 Redis 缓存 + 流式导出

**用户故事**：作为系统，我希望高频查询走缓存减 DB 压力，大结果集导出不爆内存。

#### 验收标准

1. WHEN 高频相同查询（dashboard 卡片）THEN 结果加 Redis 短 TTL 缓存（query hash 为 key）
2. WHEN query_builder 导出大结果集 THEN 流式/分页构建 Excel（避免 openpyxl 全量内存峰值）
3. WHEN 性能增强 THEN 不动白名单安全模型（③高级查询 🟢 保持）
4. IF 流式导出 THEN 内容与全量导出一致

### 需求 5：枚举字典扩展核心业务枚举

**用户故事**：作为管理员，我希望 EliminationEntryType / 审计循环代号 / 风险等级等高频业务枚举也能在字典中治理 label/color。

#### 验收标准

1. WHEN 扩展 `_DICTS` THEN 纳入 EliminationEntryType / 审计循环代号 A~N / 风险等级
2. WHEN 业务枚举进字典 THEN value 仍硬编码锁死（仅 label/color 可治理，写 value 返 405）
3. WHEN 与 spec F 配合 THEN 同 system_dicts.py 文件不冲突（F 修注释，本项扩内容）

### 需求 6：note_template DB 化 + enum 入 D6 + content_text

**用户故事**：作为开发者，我希望 note_template 大文件按章节存储避免冲突，enum_dict_overrides 入 D6，知识文件 content_text 有内容。

#### 验收标准

1. WHEN note_template DB 化 THEN 按章节拆分存 DB（复用 section_id 主键），_load_templates 改读 DB（JSON 作种子+降级）
2. WHEN enum_dict_overrides THEN 写 V0XX 迁移入 D6（三层一致，不再靠 create_all）
3. WHEN 知识文件导入 PDF/docx THEN 复用 OCR/MinerU 全文识别（`mineru_service.recognize_for_ocr` 返回 `{"text": 完整文本}` / `unified_ocr_service.recognize`）提取 content_text（保障 spec B 向量索引有内容）
4. IF note_template DB 化改动面大 THEN 实施前评估 ROI（与 §五 registry↔JSON 边界一并考虑）

### 非功能需求

- **NFR-1 非地基增量**：不动 P0+P1 已建的单源/联动架构
- **NFR-2 互不依赖**：6 需求可分批落地（仅需求 3 依赖 spec A）
- **NFR-3 安全不退化**：高级查询白名单模型保持
- **NFR-4 枚举锁死**：扩展业务枚举 value 不可改

## 正确性属性（PBT 守护）

- **P1 缓存一致**：地址库 Redis L2 与 DB 构建结果一致；invalidate 后 Redis+内存同步失效
- **P2 校验拦截**：含悬空引用的公式保存被拒
- **P3 枚举锁死**：扩展进 _DICTS 的业务枚举 value 不可改（仅 label/color）
- **P4 流式导出等价**：大结果集流式导出内容与全量导出一致
