# 实施计划：global-modules-p2-polish（全局模块 P2/P3 体验与性能增强）

> 设计：#[[file:.kiro/specs/global-modules-p2-polish/design.md]]
> 需求：#[[file:.kiro/specs/global-modules-p2-polish/requirements.md]]
> 工作流：Design-First | ~5 人天 | **A~F 落地后启动**（需求3 依赖 spec A）
> 铁律：不动 P0+P1 单源/联动架构；高级查询安全模型不退化；枚举 value 锁死

## 阶段 1 — 地址库缓存 + 校验接线（~1.5 天）

- [x] 1. 地址库 Redis 二级缓存
  - get_domain/get_all 先查 Redis（key=_slot_key），命中反序列化；未命中 DB 构建后回写（TTL 对齐按域）
  - invalidate/invalidate_all 同步删 Redis key（内存 _slots=L1，Redis=L2）
  - _需求: 1.1, 1.2, 1.3_ _属性: P1_

- [x] 2. 地址有效性校验接入公式保存流
  - 公式保存端点（report_config update / 公式管理保存）保存前调 validate_formula_refs
  - 含悬空引用拒绝保存 + 返校验错误
  - _需求: 2.1, 2.2, 2.3_ _属性: P2_

- [x] 3. 阶段 1 PBT
  - P1 缓存一致（Redis L2 == DB 构建 + invalidate 同步）+ P2 校验拦截
  - hypothesis max_examples 10~15
  - _需求: 1.4, 2.2_ _属性: P1, P2_

## 阶段 2 — 公式时间线 UI + 枚举扩展（~1 天）

- [x] 4. 公式变更时间线 UI + 一键回滚（依赖 spec A）
  - FormulaManagerDialog 加"历史"Tab 查 formula.changed 留痕（spec A GET 端点）展示时间线
  - 一键回滚写回 old_formula（复用时光机）
  - **前置确认 spec A 阶段3 已完成**（哈希链 formula.changed）
  - _需求: 3.1, 3.2, 3.3_

- [x] 5. 枚举字典扩展核心业务枚举
  - _DICTS 纳入 EliminationEntryType / 审计循环代号 A~N / 风险等级
  - value 硬编码锁死（写 value 返 405）+ 仅 label/color 可治理
  - 与 spec F 的 F4（修注释）协调同文件不冲突
  - _需求: 5.1, 5.2, 5.3_ _属性: P3_

## 阶段 3 — 高级查询缓存 + 流式导出（~1.5 天）

- [x] 6. 高级查询结果 Redis 缓存
  - 高频相同查询（dashboard 卡片）结果加 Redis 短 TTL（query hash 为 key）
  - 不动白名单安全模型
  - _需求: 4.1, 4.3_

- [x] 7. query_builder 大结果集流式导出
  - 流式/分页构建 Excel（避免 openpyxl 全量内存峰值）
  - 流式导出内容与全量一致
  - _需求: 4.2, 4.4_ _属性: P4_

## 阶段 4 — note_template DB 化 + enum 入 D6 + content_text（~1 天）

- [x] 8. enum_dict_overrides 入 D6
  - V0XX 迁移（+R0XX 回滚，IF NOT EXISTS 幂等）+ ORM 三层一致
  - 不再靠 create_all
  - _需求: 6.2_

- [x] 9. content_text 填充保障
  - 知识文件导入 PDF/docx 复用 OCR/MinerU 全文识别（`mineru_service.recognize_for_ocr` 返 `{"text":全文}`，非 wp_document_recognizer 结构化字段）提取 content_text
  - 保障 spec B 向量索引有内容
  - _需求: 6.3_

- [x]* 10. note_template DB 化（评估后，改动面大）— **暂缓**
  - **前置评估 ROI**：按章节拆分存 DB（复用 section_id），_load_templates 改读 DB（JSON 种子+降级）
  - 与 §五 registry↔JSON 边界一并考虑；评估不值得则标"暂缓"不强做
  - **评估结论：暂缓**（ROI 不足，详见 `backend/docs/NOTE_TEMPLATE_DB_EVALUATION.md`）
  - _需求: 6.1, 6.4_

- [x] 11. 收尾
  - 全部 P2 落地后既有测试零回归 + app import OK
  - 更新 INDEX.md + memory + 文档 §二十四 标 P2 批次完成
  - 各项分批 commit（git status 确认无其他 staged）
  - _需求: 1.1, 4.1, 5.1, 6.2_ _属性: P1, P2, P3, P4_
