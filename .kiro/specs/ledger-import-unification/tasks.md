# 账表导入统一方案 — 实施任务清单

> 每个任务标注预估工时、依赖关系、需求映射；任务完成后标 `[x]` 并跑对应测试验证。

---

## Sprint 0：样本收集与反向工程（第 0 周 / 8 tasks / 外部依赖）

> **为什么独立一个 Sprint**：Sprint 1 要写识别规则，但真实样本没到手写的规则都是凭印象。
> 这个 Sprint 严重依赖业务方/合伙人配合，应和 Sprint 1 并行启动（不阻塞 Sprint 1 骨架搭建，但 Sprint 1 末的识别用例必须用真实样本验证）。

### 样本采集

- [ ] **Task 0-1** 和业务方/合伙人对齐：列出目标 8 家财务软件的代表性客户列表（每家至少 2 个项目） — 4h — 需求 3
- [ ] **Task 0-2** 法务合规：起草样本使用协议 + 脱敏规则（客户名 `[client_N]` / 金额按数量级脱敏 / 员工姓名 `[staff_N]`） — 8h
- [ ] **Task 0-3** 收集原始样本文件（通过 U 盘/内网传输，不走互联网） — 2-5 天（外部依赖）
- [ ] **Task 0-4** 脱敏处理：写一次性脚本 `scripts/anonymize_ledger_sample.py`，用完即删 — 8h

### 反向工程

- [ ] **Task 0-5** 每家软件样本人工分析：表头命名规律、特殊字符、合并表头、辅助核算写法 — 16h — 需求 3
- [ ] **Task 0-6** 输出《财务软件导出格式对照表》（`docs/ledger_export_formats.md`），记录每家的必填列映射、常见坑 — 4h
- [ ] **Task 0-7** 样本入库 `backend/tests/fixtures/ledger_samples/{software}/{scenario}/`，按场景分类（标准/合并表头/大文件/辅助维度复杂/月拆 sheet） — 2h

### 对照与基准

- [ ] **Task 0-8** 用旧 `smart_import_engine.py` 跑全部样本，记录当前识别率基线（作为 v2 对比基准） — 4h

**Sprint 0 小计**：约 48h（跨两周，主要等样本收集）

---

## Sprint 1：识别引擎核心（第 1-2 周 / 20 tasks）

### 模块骨架

- [x] **Task 1** 创建 `backend/app/services/ledger_import/` 目录 + `__init__.py` + 占位文件 — 0.5h
- [x] **Task 2** 新建 `detection_types.py`，定义 9 个 Pydantic schema（`TableType` / `SheetDetection` / `FileDetection` / `LedgerDetectionResult` / `ImportError` 等） — 1h — 需求 1、8
- [x] **Task 3** 新建 `errors.py`，定义 15 个错误码枚举 + `ImportError` 构造工厂 — 1h — 需求 8

### 探测模块

- [x] **Task 4** `detector.py` 实现 `detect_file(content: bytes, filename: str) -> FileDetection`：支持 xlsx / csv / zip，只读前 20 行 — 3h — 需求 1、14、15
- [x] **Task 5** `detector.py` 合并表头识别（连续 2-3 行合并 → 单行表头） — 2h — 需求 15
- [x] **Task 6** `detector.py` 标题行跳过（单行跨表宽度、含"公司"/"年度") — 1h — 需求 15
- [x] **Task 7** `encoding_detector.py` CSV 编码自适应（utf-8-sig / utf-8 / gbk / gb18030 / latin1） — 1h — 需求 14
- [x] **Task 8** `year_detector.py` 年度识别（文件名 → sheet 名 → 元信息 → 内容众数） — 2h — 需求 13

### 识别模块

- [x] **Task 9** `identifier.py` Level 1 — Sheet 名正则识别（5 种表类型） — 1.5h — 需求 2
- [x] **Task 10** `identifier.py` Level 2 — 表头特征匹配（`TABLE_SIGNATURES.key_signals` 为单一真源，定义在 `detection_types.KEY_COLUMNS` + `RECOMMENDED_COLUMNS`，覆盖关键列/次关键列/非关键列三层；对齐 design §4.2 + §27.6） — 3.5h — 需求 2、11
- [x] **Task 11** `identifier.py` Level 3 — 内容样本识别（日期/方向列/金额列数量） — 2h — 需求 2
- [x] **Task 12** `identifier.py` 置信度聚合 + `ConfidenceLevel` 判定（high/medium/low/manual_required） — 1h — 需求 2
- [x] **Task 13** `identifier.py` `detection_evidence` 决策树记录（每级命中/未命中写入结构化字段） — 1h — 需求 2、19

### 适配器

- [x] **Task 14** `adapters/base.py` `BaseAdapter` + `AdapterRegistry` — 1.5h — 需求 3
- [x] **Task 15** `adapters/yonyou.py` 用友适配器（U8/NC/T+ **只定义关键列+次关键列别名**，非关键列走通用模糊匹配；对齐 design §5.2 精简版） — 1.5h — 需求 3
- [x] **Task 16** `adapters/kingdee.py` 金蝶适配器（K3/EAS/Cloud，同上仅关键列+次关键列） — 1.5h — 需求 3
- [x] **Task 17** `adapters/sap.py` + `oracle.py` + `inspur.py` + `newgrand.py`（同上精简策略） — 3h — 需求 3
- [x] **Task 18** `adapters/generic.py` 通用兜底适配器 + Levenshtein 距离模糊匹配 + 子串包含 — 1.5h — 需求 3
- [x] **Task 19** `backend/data/ledger_adapters/*.json` 外置适配器定义（支持 hot reload） — 1.5h — 需求 3

### 单元测试

- [x] **Task 20** `backend/tests/ledger_import/test_detector.py` + `test_identifier.py` 基础用例（每个 Level 至少 2 个用例） — 3h — 需求 1、2

**Sprint 1 小计**：约 32h

---

## Sprint 2：解析与入库（第 2 周 / 18 tasks）

### 解析层

- [x] **Task 21** `parsers/excel_parser.py` 流式按 chunk 生成行数据（50k/chunk） — 2.5h — 需求 5
- [x] **Task 22** `parsers/csv_parser.py` generator 流式读 + 编码自适应 — 1.5h — 需求 5、14
- [x] **Task 23** `parsers/zip_parser.py` ZIP 解压递归，CP437→gbk 文件名修复 — 1.5h — 需求 14

### 辅助维度

- [x] **Task 24** `aux_dimension.py` 6 种格式解析器（JSON / colon / slash / pipe / arrow / code_name） — 3h — 需求 4、16
- [x] **Task 25** `aux_dimension.py` 多维组合（逗号/分号分隔多个维度） — 1h — 需求 16
- [x] **Task 26** 辅助维度列自动识别（列名含"核算项目"/"辅助核算"/"客户"/"供应商") — 2h — 需求 4

### 合并策略

- [x] **Task 27** `merge_strategy.py` 同文件多 sheet 合并（auto/by_month/manual） — 2h — 需求 6
- [x] **Task 28** 去重：按 `(voucher_date, voucher_no, entry_seq)` — 1h — 需求 6

### 列映射

- [x] **Task 29** `column_mapping_service.py` 持久化历史映射（CRUD） — 2h — 需求 9
- [x] **Task 30** `import_column_mapping_history` 表迁移（Alembic） — 0.5h — 需求 9
- [x] **Task 31** 映射复用：新导入时按软件指纹查历史，命中自动填充 — 2h — 需求 9

### 写入层

- [x] **Task 32** `writer.py` `copy_insert` 流式 COPY（复用既有 `fast_writer.py`） — 1.5h — 需求 5
- [x] **Task 32a** Alembic 迁移：四表 `tb_balance`/`tb_ledger`/`tb_aux_balance`/`tb_aux_ledger` 新增 `raw_extra JSONB` 列（nullable） — 1h — 需求 21
- [x] **Task 32b** `writer.py` 支持 `raw_extra` 列：一行中已映射到 standard_field（key 或 recommended）的列不重复存，剩余原样写入 raw_extra；单行上限 8KB，超限截断并生成 `EXTRA_TRUNCATED` warning — 2h — 需求 21
- [x] **Task 32c** 新增端点 `GET /api/projects/{pid}/ledger/raw-extra-fields?year=&table=` 聚合返回 raw_extra 字段分布（按字段名统计 row_count + 3 个样本值） — 1.5h — 需求 21
- [x] **Task 33** 辅助表从主表自动派生（余额表行 → 分流 tb_balance + tb_aux_balance） — 2.5h — 需求 4
- [x] **Task 34** staged → active 原子切换（复用既有 `DatasetService`） — 1.5h — 需求 12

### 校验层（按列分层）

- [x] **Task 35** `validator.py` Level 1 校验**分层**实现：关键列金额非数/日期非法/值为空 → blocking；次关键列同类问题 → warning + 值置 NULL；非关键列不校验（对齐 design §19.1） — 2.5h — 需求 11
- [x] **Task 36** `validator.py` Level 2 校验（借贷平衡、年度范围、科目存在） — 2.5h — 需求 11
- [x] **Task 37** `validator.py` Level 3 校验（余额期末=序时累计，容差 1 元；辅助与主表科目一致） — 2.5h — 需求 11
- [x] **Task 38** `force_activate` 跳过 L2/L3 校验的审批链 — 1h — 需求 11

**Sprint 2 小计**：约 31h

---

## Sprint 3：编排与 API（第 3 周 / 15 tasks）

### 编排器

- [x] **Task 39** `orchestrator.py` `ImportOrchestrator.detect(files)` — 调用 detector + identifier + adapter — 3h — 需求 1、2、3
- [x] **Task 40** `orchestrator.py` `ImportOrchestrator.submit(upload_token, confirmed_mappings)` — 触发入库 job — 2h — 需求 7
- [x] **Task 41** `orchestrator.py` 断点续传（复用 `import_artifacts`） — 2h — 需求 10

### API

- [x] **Task 42** `routers/ledger_import.py` 新增 `POST /detect` 端点（multipart + 返回 `LedgerDetectionResult`） — 2h — 需求 1、7
- [x] **Task 43** `POST /submit` 端点（接受 `confirmed_mappings`，创建 ImportJob） — 2h — 需求 7
- [x] **Task 44** `GET /jobs/{job_id}/stream` SSE 进度推送 — 2.5h — 需求 18
- [x] **Task 45** `GET /jobs/{job_id}/diagnostics` 诊断详情（支持/管理员） — 1.5h — 需求 19
- [x] **Task 46** `POST /jobs/{job_id}/cancel` 取消作业（触发 staged 数据清理） — 1.5h — 需求 18
- [x] **Task 47** `POST /jobs/{job_id}/retry` 重试失败作业（复用 ImportArtifact） — 1.5h — 需求 10

### Worker 集成

- [x] **Task 48** 修改 `import_job_runner.py` 根据 `feature_flags.is_enabled("ledger_import_v2", project_id)` 决定走 v2 编排器还是旧 `smart_import_engine`；不引入新 `engine` 参数（对齐 design §13） — 2h — 需求 20
- [x] **Task 49** `import_recover_worker.py` 识别 `processing` 超时作业，重置为 `queued` — 1.5h — 需求 10
- [x] **Task 50** `event_bus` 发布 `LEDGER_IMPORT_SUBMITTED` / `LEDGER_DATASET_ACTIVATED` / `LEDGER_DATASET_ROLLED_BACK`（复用 `EventType` 已有枚举，`audit_platform_schemas.py:747`）；新增 `LEDGER_IMPORT_DETECTED` 枚举到 `EventType` — 1.5h — 需求 12

### Feature Flag

- [x] **Task 51** `feature_flags.py._DEFAULT_FLAGS` 新增 `"ledger_import_v2": False`（对齐现有内存字典机制，**不引入 env 变量**） — 0.5h — 需求 20
- [x] **Task 52** 支持项目级 override：在项目设置页提供开关，调 `feature_flags.set_project_flag(pid, "ledger_import_v2", True)` — 1h — 需求 20
- [x] **Task 53** `router_registry.py` §N 注册 v2 router，路径前缀统一 `/api/projects/{project_id}/ledger-import/*`（和现有保持一致）；内部判断 `is_enabled` 决定返回新/旧实现 — 0.5h — 需求 20

### AI 兜底识别（可选，Level 5，仅关键列）

> **可选**：开启 `feature_flags["ledger_import_ai_fallback"]` 后，规则 Level 1-3 对**关键列**识别失败（置信度 < 80）时调用 LLM 精准识别。
> 次关键列不触发 AI（置信度 < 50 时直接 NULL + warning，非关键列直接进 raw_extra）。
> 详见 design.md §22；默认关闭，需求稳定后再启用。

- [ ] **Task 53a** `feature_flags.py._DEFAULT_FLAGS` 新增 `"ledger_import_ai_fallback": False` — 0.25h — 需求 2
- [ ] **Task 53b** `ledger_import/ai_identifier.py` 实现两个精准 prompt：(A) 表类型仍不确定时、(B) 关键列未匹配时；每次调用只针对 1 个关键列问"在列表中选对应的列名"；集成 `export_mask_service.mask_context` 脱敏；每次调用 token < 500 — 3h — 需求 2
- [ ] **Task 53c** AI 结果置信度封顶 60（永远不超过规则 Level 2），写入 `detection_evidence.ai_fallback`；单项目每日上限 20 次（Redis 计数器） — 1.5h — 需求 2
- [ ] **Task 53d** `test_ai_identifier.py` mock LLM 响应的单测（真实调用放 Sprint 5） — 1.5h

**Sprint 3 小计**：约 30h（含 AI 兜底 6.25h）

---

## Sprint 4：前端与错误反馈（第 3-4 周 / 18 tasks）

### 组件骨架

- [x] **Task 54** `components/ledger-import/LedgerImportDialog.vue` 总容器（步骤切换） — 2h — 需求 7
- [x] **Task 55** `UploadStep.vue` 多文件拖拽上传 + 分 chunk 5MB 上传 — 2.5h — 需求 10
- [x] **Task 56** `DetectionPreview.vue` 预检结果表格（sheet 列表 + 置信度 badge + 预览 + **关键列覆盖率徽标**"5/5 关键列已识别" / "3/5 关键列缺失") — 3.5h — 需求 7
- [x] **Task 57** `ColumnMappingEditor.vue` 三区分层（🔴关键列强制确认 / 🟡次关键列折叠可审阅 / ⚪非关键列折叠进 raw_extra 提示）+ 列映射拖拽编辑 + 下拉选择；未填关键列时 submit 按钮 disabled — 4h — 需求 2、7、21
- [x] **Task 58** `ImportProgress.vue` SSE 订阅 + 四段式进度条 — 2h — 需求 18
- [x] **Task 59** `ErrorDialog.vue` 分级错误弹窗（fatal/blocking/warning 三色，按 `column_tier` 分组筛选；对齐 design §10） — 2.5h — 需求 8
- [x] **Task 60** `DiagnosticPanel.vue` 诊断详情折叠面板 — 1.5h — 需求 19

### 服务层

- [x] **Task 61** `services/ledgerImportV2Api.ts` — detect/submit/stream/cancel/retry/diagnostics — 2h — 需求 7、18、19
- [x] **Task 62** `apiPaths.ts` 新增 `ledger.v2.*` 路径常量 — 0.5h — 需求 7
- [x] **Task 63** `composables/useLedgerImport.ts` 状态管理（文件/预检/映射/进度/错误） — 2h — 需求 7

### UI 交互细节

- [x] **Task 64** 置信度 badge（绿/黄/红）+ tooltip 解释 — 1h — 需求 2
- [x] **Task 65** 预检表格虚拟滚动（element-plus `el-table-v2`） — 1h — 需求 17
- [x] **Task 66** 预检结果缓存 sessionStorage（刷新恢复） — 1h — 需求 17
- [x] **Task 67** 年度冲突警告弹窗（文件年度 vs 项目审计期） — 1h — 需求 13
- [x] **Task 68** 断点续传 UI：分片上传进度 + 暂停/恢复 + 已上传分片状态持久化 localStorage — 3h — 需求 10
- [x] **Task 69** "从其他项目导入映射"入口 + 选择器 — 1.5h — 需求 9
- [x] **Task 70** 导入历史页面展示 adapter_used + detection_evidence 入口 — 1h — 需求 19
- [x] **Task 70a** 列映射 diff UI（绿/蓝/黄/灰 4 色，对齐 design §21.3） — 2h — 需求 9
- [x] **Task 70b** 识别决策树可读化面板（把 `detection_evidence` JSON 翻译成人类可读的日志行） — 2h — 需求 19

### 无障碍与多语言

- [x] **Task 71** 所有按钮 aria-label + 键盘 tab 可达 — 1h

**Sprint 4 小计**：约 35h

---

## Sprint 5：测试与验收（第 5-6 周 / 12 tasks）

> **前置**：Sprint 0 的 Task 0-3 到 0-7 必须完成，本 Sprint 测试用例直接复用 `fixtures/ledger_samples/` 的真实样本。

### 识别引擎通用化重构（v2.1，对齐 design §28）

> **驱动**：真实样本验证暴露的结构性问题，必须在测试前修复。

- [x] **Task 74a** 合并表头通用算法重写：替换 `_detect_header_row`，基于"行间值多样性"判断表头边界（标题行 = unique_value_count ≤ 2；表头行 = fill_ratio ≥ 0.5 且 unique_value_count ≥ 3；支持 2+ 行标题 + 2 行合并表头） — 3h — 需求 15、design §28.2
- [x] **Task 74b** L2+L3 并行联合打分：重构 `identify()` 使 L1/L2/L3 始终并行执行，按权重（0.2/0.5/0.3）加权聚合最终置信度；权重从 `matching_config` 读取 — 3h — 需求 2、design §28.1
- [x] **Task 74c** 列内容验证器：新增 `content_validators.py`，实现 `validate_column_content(values, validator_type)` 返回 0-1 匹配度；支持 date/numeric/code 三种验证器；集成到 `_match_header` 后的置信度计算（header_conf × 0.7 + content_conf × 0.3） — 3h — 需求 2、design §28.4
- [x] **Task 74d** 识别规则 JSON 外置：创建 `backend/data/ledger_recognition_rules.json`，将 `SHEET_NAME_PATTERNS` + `TABLE_SIGNATURES` + `matching_config` 抽离为声明式配置；`identifier.py` 启动时加载 JSON，支持 hot-reload — 3h — 需求 3、design §28.3

### 测试集构建

- [ ] **Task 72** ~~（已迁移到 Sprint 0 Task 0-3 ~ 0-7）真实样本收集~~（Sprint 0 完成）— 此 task 删除
- [ ] **Task 73** ~~样本存放位置~~（Sprint 0 Task 0-7 已完成）— 此 task 删除
- [x] **Task 74** 构造异常样本：合并表头 / 空 sheet / 超大 CSV（100 万行）/ 编码混乱 / 列错位 — 8h — 需求 5、14、15

### 单元测试

- [x] **Task 75** `test_identifier.py` 3 级识别全路径覆盖（基于真实样本 + 异常样本）；**断言**：关键列识别率 ≥ 85%、次关键列识别率 ≥ 70%、非关键列应入 raw_extra — 4.5h
- [x] **Task 75a** `test_raw_extra.py` 验证 raw_extra 写入：关键/次关键已映射列不重复存、非关键列原样保留、超 8KB 截断 — 1.5h — 需求 21
- [x] **Task 76** `test_aux_dimension.py` 6 种格式 + 属性测试（Hypothesis） — 3h — 需求 16
- [x] **Task 77** `test_validator.py` 3 级校验全分支 — 4h — 需求 11
- [x] **Task 78** `test_adapters/*` 8 家适配器各自至少 3 用例 — 6h — 需求 3

### 集成测试

- [ ] **Task 79** `test_ledger_import_e2e.py` 端到端：detect → confirm → submit → stream → dataset active — 4h
- [ ] **Task 80** 大文件性能测试（100 万行 → 1GB），构造样本 + 跑 + 调优，断言耗时 < 10 分钟 + 内存峰值 < 2GB — 8h — 需求 5
- [ ] **Task 81** 并发测试：5 个导入作业同时运行，断言无数据交叉污染 — 3h

### UAT（真实业务验收）

- [ ] **Task 82** 业务人员 UAT：用真实项目文件（至少覆盖 Sprint 0 的 8 家软件）跑一遍，记录**关键列识别率** / 人工干预次数 / 耗时 / raw_extra 保留完整性；达标标准：**关键列**自动识别率 ≥ 85%，次关键列识别率不作硬要求但要有覆盖数据；单列修正补齐率 ≥ 95% — 16h — 需求 3
- [ ] **Task 83** 修复 UAT 发现的 bug + 优化识别规则（预期 2-3 轮迭代） — 预留 24h

### 文档与发布

- [ ] **Task 84** (可选) 撰写 `docs/ledger_import_v2_guide.md` 用户使用手册 — 2h；**用户偏好**：本仓库不主动建 md，仅当业务方明确要求时补 — skip by default
- [ ] **Task 85** (可选) 撰写 `docs/ledger_import_v2_architecture.md` 技术架构文档 — 1.5h；同上 — skip by default
- [ ] **Task 86** 灰度发布计划 + 回滚预案（写入 README.md 最后一章，不单独建 md） — 1h — 需求 20



**Sprint 5 小计**：约 38h（含迭代预留）

---

## 总计工时

| Sprint | 任务数 | 预估工时 |
|--------|--------|----------|
| Sprint 0：样本收集 | 8 | 48h（跨两周，主要外部依赖） |
| Sprint 1：识别引擎（关键列单一真源） | 20 | 30h（精简适配器省 2h） |
| Sprint 2：解析入库 + raw_extra + 分层校验 | 21 | 36h（+3 任务，raw_extra 迁移/写入/端点 +4.5h） |
| Sprint 3：编排 API + AI 精准兜底 | 19 | 28h（AI 范围收窄省 2h） |
| Sprint 4：前端三区 UX + diff + 决策树 | 20 | 37h（Task 56/57/59 深化 +2h） |
| Sprint 5：测试发布（含 raw_extra 测试） | 13 | 78h（+Task 75a） |
| **总计** | **101** | **257h（约 6-7 周全职，含 Sprint 0 外部依赖等待）** |

> **v3 调整**：聚焦"关键列硬、非关键列软"策略后：
> - 识别/适配器精简 2h（非关键列走通用模糊匹配，不用每家维护）
> - AI 兜底范围收窄省 2h（只对关键列精准问，token 降 80%）
> - 新增 raw_extra 相关任务 +6h（Task 32a/32b/32c + 75a）
> - 前端三区布局深化 +2h（Task 56/57/59 都增加关键列徽标）
> - UAT 指标更明确（只验关键列识别率）

## 关键依赖

- **Sprint 0 是外部阻塞依赖**（样本收集需要 2-5 天与业务方协调），必须在 Sprint 1 启动前或并行启动
- **Sprint 2 依赖 Sprint 1**（识别结果是解析的输入）
- **Sprint 3 依赖 Sprint 2**（编排器调用解析和校验）
- **Sprint 4 依赖 Sprint 3**（前端对接 API）
- **Sprint 5 的真实 UAT 需要 Sprint 0 的真实样本**（必须前置完成）

## 每周里程碑

| 周 | 完成 | 交付物 |
|---|-----|--------|
| 第 0 周（并行） | Sprint 0 启动（外部依赖） | 样本采集需求已和业务方对齐，合规/脱敏规则确认 |
| 第 1 周末 | Sprint 1 骨架 + Sprint 0 Task 0-3/0-4（样本到位） | 识别引擎模块骨架 + 初版适配器（基于 1-2 家样本） |
| 第 2 周末 | Sprint 1 完成 + Sprint 0 Task 0-5/0-6 | 8 家适配器骨架完成，识别率基线记录 |
| 第 3 周末 | Sprint 2 | 命令行可解析 1GB 序时账入库成功 |
| 第 4 周末 | Sprint 3 | API 可通过 curl 触发完整导入 + AI 兜底（若启用） |
| 第 5 周末 | Sprint 4 | 前端可视化导入，4-5 家真实样本通过识别 |
| 第 6 周末 | Sprint 5 Part 1（单测/集成/性能） | 测试覆盖率 ≥ 80%，大文件 < 10 分钟 |
| 第 7 周（UAT 迭代） | Sprint 5 Part 2（UAT + 调优） | 8 家样本识别率 ≥ 85%，业务方签字验收 |

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| **真实样本难收集**（法务/客户意愿） | 高 | 阻断 Sprint 1 识别规则的实证基础 | Sprint 0 提前 2 周启动；法务脱敏协议模板化；先用合作紧密的 2-3 个项目起步 |
| 样本脱敏工作量大 | 中 | 工期延长 | Task 0-4 脚本化（用完即删，符合用户偏好），跑一次处理所有样本 |
| 大文件 OOM | 中 | 中 | Task 80 强制跑性能测试；`LEDGER_IMPORT_FULL_MODE_MAX_FILE_MB` 兜底；Sprint 2 末期先跑 100 万行早发现 |
| 识别率不达标 | 中 | 高 | 适配器机制可随时扩展；AI 兜底（Task 53a-d）作为第二道保险；Sprint 5 Task 83 预留 24h 迭代 |
| 前后端联调卡顿 | 中 | 中 | Sprint 3 末做 API demo；Sprint 4 第 1 天联调 `/detect`，问题早发现 |
| 新旧引擎并存复杂度 | 低 | 中 | feature flag + 灰度发布，项目级 override 可快速回退单项目 |
| 适配器打分冲突 | 低 | 低 | design §26 已列为已知问题；tie-breaker 规则（文件名权重 > 列名权重）在 Sprint 1 Task 14 中落实 |
| AI 兜底成本/延迟 | 低 | 低 | 封顶置信度 60 + 每日每项目 20 次上限 + 脱敏；可选功能默认关闭 |


---

## Sprint 6：账表导入全链路深度修复（第 7 周 / 20 tasks / 对齐 2026-05-08 复盘）

> **驱动**：9 家真实样本验证发现 v2 引擎在"识别 → 转换 → 写入 → 事务 → 运维"五层都有真实 bug 或架构债。Sprint 6 聚焦 P0-P1 项目，目标 Worker 端到端真实入库跑通并回归稳定。

### 架构清洁（死代码+边界模糊）

- [ ] **Task S6-1** 删除 `aux_derivation.py` 死代码（职责已在 converter 完成，`_execute_v2` 未调用）；同步更新 `ledger_import/__init__.py` 不再导出 — 0.5h
- [ ] **Task S6-2** `_clear_project_year_tables` 迁移到 `writer.py` 新增 `clear_project_year(db, project_id, year)` 函数；`_execute_v2` 改调新函数 — 1h
- [ ] **Task S6-3** `_execute_v2` 全量迁移到 `ledger_import/orchestrator.py` 新增 `execute_job(job_id, ...)` 入口；`import_job_runner._execute_v2` 薄包装只保留分支跳转 — 3h

### 运维可观测性 + 容灾

- [ ] **Task S6-4** `_execute_v2` 最外层 try/except 兜底：即使 import/DB 初始化失败也要写 `error_message` + `result_summary['phase']='bootstrap'` 到 job 表；释放 ImportQueueService.lock — 1h
- [ ] **Task S6-5** 各 Phase 入口加 `logger.info("ImportJob {} phase={} ...")` 结构化日志，便于失败时通过日志快速定位卡在哪一步 — 0.5h

### 转换层修复

- [ ] **Task S6-6** `prepare_rows_with_raw_extra` 多列映射到同一 std_field 时，被丢弃的列值进入 `raw_extra["_discarded_mappings"][std_field] = [{header, value}]`，不再静默丢失 — 1.5h
- [ ] **Task S6-7** 空值策略统一：`_insert_aux_balance` / `_insert_aux_ledger` 中 `aux_code`/`aux_name` 空串改为 NULL；converter 返回 `None` 而非 `""`；更新模型字段 default/nullable 校验；补 test — 1.5h
- [ ] **Task S6-8** 辅助维度类型重名：`tb_aux_balance` / `tb_aux_ledger` 新增 `aux_dimensions_raw` 已有列的穿透查询支持按 `(account_code, aux_type, aux_code)` 三元组定位，避免"税率"在客户/项目下混淆；补端点 `GET /api/projects/{pid}/ledger/aux-ledger/by-triplet` — 2h

### 识别层修复

- [ ] **Task S6-9** 和平物流余额表识别：`identifier.identify` L1 命中且 `score ≥ 85` 时锁定 table_type，L2 只用于列映射不投票；加到 `ledger_recognition_rules.json.matching_config.l1_lock_threshold` — 2h
- [ ] **Task S6-10** 真实样本 `和平物流25加工账-药品批发.xlsx` 补 smoke test，断言余额表识别为 balance — 0.5h

### 解析层修复

- [ ] **Task S6-11** `iter_excel_rows` 和 `iter_excel_rows_from_path` 合并底层：提取 `_iter_excel_from_workbook(wb, ...)` 共用函数，两个入口各自 load_workbook 后调用同一逻辑 — 1.5h
- [ ] **Task S6-12** xlsx 合并单元格 forward-fill 可选策略：`iter_excel_rows_from_path(..., forward_fill_cols=[0, 1])` 支持指定列向下填充；辅助明细账 account_code 场景专用 — 2h

### 写入层事务边界

- [ ] **Task S6-13** `_execute_v2` 走 staged 模式：创建 `LedgerDataset(status='staging')` → 4 张表 insert 时 `dataset_id=staging_id` → 全部成功后 `activate_dataset()` 原子切换 → 失败时 `DatasetService.mark_failed_for_job` — 3h
- [ ] **Task S6-14** `rebuild_aux_balance_summary` 加 dataset_id 过滤（只汇总本次 staging，不污染历史激活数据） — 1h

### Incremental 追加

- [ ] **Task S6-15** `ledger_data_service.apply_incremental(project_id, year, new_file_periods)` 真正的"按期间追加"：只删 overlap 期间，插入 new 期间；走 staged 模式 — 3h
- [ ] **Task S6-16** `routers/ledger_data.py` 新增 `POST /incremental/apply` 端点 + 前端 `LedgerDataManager.vue` 增量追加 Tab 打通 — 1.5h

### 端到端验证

- [ ] **Task S6-17** `backend/tests/ledger_import/test_execute_v2_e2e.py` 集成测试：直接调 `ImportJobRunner.run_job()` 路径，mock upload_bundle 为 YG36 真实文件副本，断言 PG 四张表行数均 > 0 + tb_aux_ledger.aux_type 有"金融机构"/"客户"/"税率" — 3h
- [ ] **Task S6-18** CI 加 v2 smoke step：pytest 只跑 test_execute_v2_e2e，fail 则整个 pipeline red — 0.5h

### 测试补齐

- [ ] **Task S6-19** `test_prepare_rows_discarded.py` 覆盖 Task S6-6 的丢弃列保留逻辑 — 1h
- [ ] **Task S6-20** `test_aux_triplet_penetration.py` 覆盖 Task S6-8 的三元组查询 — 1h

**Sprint 6 小计**：约 30h（核心 2 周）

---

## Sprint 7：UX + 运维可观测（后续规划，本轮不做）

- [ ] `ledger_data_service.delete` 改软删除 + 回收站
- [ ] `LedgerDataManager.vue` 挂载到项目设置页/数据管理页
- [ ] 前端识别失败时允许手动改 table_type
- [ ] raw_extra GIN 索引支持查询
- [ ] 进度条改走 `import_jobs` 表轮询（替换内存态 ImportQueueService）
- [ ] L2/L3 容差按金额量级动态
- [ ] force_activate 审批链落地
- [ ] 识别准确率 metric 仪表盘（Metabase）
- [ ] 大文件性能基准 CI 门禁（内存 < 2GB / 耗时 < 10min）
- [ ] adapter 机制取舍（删或改纯别名包）
