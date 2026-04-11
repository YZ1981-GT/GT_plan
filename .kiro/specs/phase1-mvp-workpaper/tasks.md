# 实现计划：第一阶段MVP底稿 — ONLYOFFICE集成+底稿模板引擎+底稿质量自检

## 概述

本实现计划将设计文档中的架构和组件拆解为可执行的编码任务，按照数据库→后端服务→ONLYOFFICE集成→前端页面→测试的顺序递进实现。每个任务构建在前序任务之上。技术栈：Python（FastAPI + SQLAlchemy + openpyxl + Hypothesis）+ TypeScript（Vue 3 + Pinia）+ ONLYOFFICE Document Server。

## 任务

- [x] 1. 数据库迁移：创建8张底稿相关表及索引
  - [x] 1.1 创建 Alembic 迁移脚本，定义 `wp_template` 表（UUID PK、template_code、template_name、audit_cycle、applicable_standard、version_major int default 1、version_minor int default 0、status enum draft/published/deprecated、file_path、description、is_deleted、created_by FK、created_at、updated_at）及复合唯一索引 (template_code, version_major, version_minor)
    - _需求: 10.1_
  - [x] 1.2 创建 `wp_template_meta` 表（UUID PK、template_id FK、range_name、region_type enum formula/manual/ai_fill/conclusion/cross_ref、description、created_at、updated_at）及索引 (template_id)
    - _需求: 10.2_
  - [x] 1.3 创建 `wp_template_set` 表（UUID PK、set_name unique、template_codes jsonb、applicable_audit_type、applicable_standard、description、is_deleted、created_at、updated_at）
    - _需求: 10.3_
  - [x] 1.4 创建 `wp_index` 表（UUID PK、project_id FK、wp_code、wp_name、audit_cycle、assigned_to FK nullable、reviewer FK nullable、status enum not_started/in_progress/draft_complete/review_passed/archived、cross_ref_codes jsonb、is_deleted、created_at、updated_at）及复合唯一索引 (project_id, wp_code)
    - _需求: 10.4_
  - [x] 1.5 创建 `working_paper` 表（UUID PK、project_id FK、wp_index_id FK、file_path、source_type enum template/manual/imported、status enum draft/edit_complete/review_level1_passed/review_level2_passed/archived、assigned_to FK nullable、reviewer FK nullable、file_version int default 1、last_parsed_at nullable、is_deleted、created_by FK、updated_by FK、created_at、updated_at）及复合唯一索引 (project_id, wp_index_id)
    - _需求: 10.5_
  - [x] 1.6 创建 `wp_cross_ref` 表（UUID PK、project_id FK、source_wp_id FK、target_wp_code、cell_reference、created_at、updated_at）及索引 (project_id, source_wp_id)
    - _需求: 10.6_
  - [x] 1.7 创建 `wp_qc_results` 表（UUID PK、working_paper_id FK、check_timestamp、findings jsonb、passed boolean、blocking_count int default 0、warning_count int default 0、info_count int default 0、checked_by FK、created_at）及索引 (working_paper_id)
    - _需求: 10.7_
  - [x] 1.8 创建 `review_records` 表（UUID PK、working_paper_id FK、cell_reference nullable、comment_text text、commenter_id FK、status enum open/replied/resolved、reply_text nullable、replier_id FK nullable、replied_at nullable、resolved_by FK nullable、resolved_at nullable、is_deleted、created_at、updated_at）及索引 (working_paper_id, status)
    - _需求: 10.8_

- [x] 2. 定义 SQLAlchemy ORM 模型与 Pydantic Schema
  - [x] 2.1 在 `backend/app/models/` 下创建 `workpaper_models.py`，定义8张表对应的 SQLAlchemy ORM 模型（WpTemplate、WpTemplateMeta、WpTemplateSet、WpIndex、WorkingPaper、WpCrossRef、WpQcResult、ReviewRecord），包含所有字段、枚举类型、外键关系
    - _需求: 10.1-10.8_
  - [x] 2.2 在 `backend/app/models/` 下创建 `workpaper_schemas.py`，定义所有 API 请求/响应的 Pydantic Schema（TemplateMetadata、TemplateUpload、WPFilter、FormulaRequest、FormulaResult、QCFinding、QCResult、QCSummary、ReviewCommentCreate、ReviewReply、ConflictReport、PrefillReport、WOPIFileInfo 等）
    - _需求: 1.1-9.3_

- [x] 3. 检查点 — 确保数据库迁移和模型定义正确
  - 运行 `alembic upgrade head` 确认迁移成功，确保所有测试通过，如有问题请询问用户。

- [x] 4. 取数公式引擎（后端核心服务）
  - [x] 4.1 实现 `FormulaEngine` 基础框架：公式类型注册表（FORMULA_TYPES）、`execute` 方法（检查缓存→调用Executor→写入缓存）、`batch_execute` 方法（批量执行，利用Redis pipeline）、`invalidate_cache` 方法（按项目/年度/科目失效缓存）
    - Redis缓存 key=`formula:{project_id}:{year}:{formula_hash}`，TTL=5min
    - _需求: 2.8, 2.9, 2.10_
  - [x] 4.2 实现 `TBExecutor`：从 `trial_balance` 表查询指定科目的指定列值，列名映射（期末余额→audited_amount、未审数→unadjusted_amount、AJE调整→aje_adjustment、RJE调整→rje_adjustment、年初余额→opening_balance）
    - _需求: 2.1, 2.2_
  - [x] 4.3 实现 `WPExecutor`：查询 `working_paper` 表获取 file_path，用 openpyxl 打开文件读取指定单元格值
    - _需求: 2.1, 2.3_
  - [x] 4.4 实现 `AUXExecutor`：从 `tb_aux_balance` 表查询指定科目+辅助维度+维度值的指定列值
    - _需求: 2.1, 2.4_
  - [x] 4.5 实现 `PREVExecutor`：递归调用 FormulaEngine.execute，year 参数减1
    - _需求: 2.1, 2.5_
  - [x] 4.6 实现 `SumTBExecutor`：解析科目范围 "start~end"，SQL SUM 查询范围内所有科目的指定列值
    - _需求: 2.1, 2.6_
  - [x] 4.7 实现公式错误处理：科目不存在、映射缺失、文件不存在等情况返回 FormulaError 对象（code="FORMULA_ERROR", message=描述性消息）
    - _需求: 2.7_
  - [x] 4.8 实现取数公式 API 路由（`backend/app/routers/formula.py`）：POST `/api/formula/execute` 执行单个公式、POST `/api/formula/batch-execute` 批量执行
    - _需求: 2.9_
  - [ ]* 4.9 编写属性测试：取数公式确定性执行
    - **Property 1: 取数公式确定性执行**
    - 使用 Hypothesis 生成随机公式类型+参数，验证连续两次执行返回相同结果
    - **验证: 需求 2.10**
  - [ ]* 4.10 编写属性测试：TB函数取数一致性
    - **Property 2: TB函数取数一致性**
    - 使用 Hypothesis 生成随机科目+列名，验证TB()返回值等于trial_balance表对应值
    - **验证: 需求 2.2**
  - [ ]* 4.11 编写属性测试：SUM_TB范围汇总正确性
    - **Property 3: SUM_TB范围汇总正确性**
    - 使用 Hypothesis 生成随机科目范围，验证SUM_TB()等于范围内所有科目值之和
    - **验证: 需求 2.6**
  - [ ]* 4.12 编写属性测试：PREV函数年度偏移正确性
    - **Property 4: PREV函数年度偏移正确性**
    - 使用 Hypothesis 生成随机公式+年度，验证PREV()等于year-1执行结果
    - **验证: 需求 2.5**
  - [ ]* 4.13 编写属性测试：公式缓存一致性
    - **Property 5: 公式缓存一致性**
    - 使用 Hypothesis 生成随机公式+数据变更，验证缓存命中值等于直接计算值
    - **验证: 需求 2.8**
  - [ ]* 4.14 编写属性测试：公式错误处理正确性
    - **Property 18: 公式错误处理正确性**
    - 使用 Hypothesis 生成随机无效公式参数，验证返回FORMULA_ERROR而非异常
    - **验证: 需求 2.7**

- [x] 5. 检查点 — 确保取数公式引擎正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 6. 底稿模板引擎（后端服务 + API）
  - [x] 6.1 实现 `TemplateEngine.upload_template`：保存文件到 `templates/{template_code}/{version}/`，用 openpyxl 解析 Named Ranges 写入 `wp_template_meta`，创建 `wp_template` 记录
    - _需求: 1.1, 1.2, 1.5_
  - [x] 6.2 实现 `TemplateEngine.create_version`：根据 change_type（major/minor）递增版本号，保存新版本文件
    - _需求: 1.3_
  - [x] 6.3 实现 `TemplateEngine.delete_template`：校验无项目引用后执行软删除
    - _需求: 1.4_
  - [x] 6.4 实现模板集管理：`get_template_sets`、创建/编辑模板集，初始化6个内置模板集（标准年审/精简版/上市公司/IPO/国企附注/上市附注）的种子数据
    - _需求: 1.6, 1.7_
  - [x] 6.5 实现 `TemplateEngine.generate_project_workpapers`：遍历模板集→复制文件到项目目录→创建 wp_index 记录→创建 working_paper 记录
    - _需求: 1.8, 6.2, 6.3_
  - [x] 6.6 实现模板 API 路由（`backend/app/routers/wp_template.py`）：POST 上传、GET 列表、GET 详情、POST 新版本、DELETE 删除、GET 模板集列表、GET 模板集详情
    - _需求: 1.1-1.8_
  - [ ]* 6.7 编写属性测试：模板版本不可删除性
    - **Property 14: 模板版本不可删除性**
    - 使用 Hypothesis 生成随机模板+引用关系，验证已引用模板删除被拒绝
    - **验证: 需求 1.4**
  - [ ]* 6.8 编写属性测试：底稿生成完整性
    - **Property 15: 底稿生成完整性**
    - 使用 Hypothesis 生成随机模板集，验证生成的wp_index数=模板数且每个都有working_paper记录
    - **验证: 需求 1.8, 6.2, 6.3**

- [x] 7. 预填充与解析回写服务
  - [x] 7.1 实现 `PrefillService._scan_formulas`：用正则匹配扫描 .xlsx 文件中的取数公式（TB/WP/AUX/PREV/SUM_TB），返回公式单元格列表
    - _需求: 6.4_
  - [x] 7.2 实现 `PrefillService.prefill_workpaper`：打开 .xlsx→扫描公式→批量调用 FormulaEngine.batch_execute→将结果写入单元格（保留公式文本在批注中）→保存文件，单个底稿≤5秒
    - _需求: 6.4, 6.5_
  - [x] 7.3 实现 `ParseService.parse_workpaper`：打开 .xlsx→读取 wp_template_meta 获取区域定义→提取人工填写区域值→提取结论区文本→扫描 WP() 函数更新 wp_cross_ref→更新 last_parsed_at，单个底稿≤3秒
    - _需求: 6.6, 6.7_
  - [x] 7.4 实现 `ParseService.detect_conflicts`：比对上传文件版本号 vs 数据库版本号，版本不匹配时逐单元格比对差异，返回冲突报告
    - _需求: 7.2, 7.3, 7.4_
  - [ ]* 7.5 编写属性测试：预填充-解析往返一致性
    - **Property 8: 预填充-解析往返一致性**
    - 使用 Hypothesis 生成随机底稿+人工填写值，验证预填充后解析回写不影响人工填写区
    - **验证: 需求 7.5**

- [x] 8. 检查点 — 确保模板引擎、预填充、解析回写正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 9. WOPI Host服务（ONLYOFFICE集成后端）
  - [x] 9.1 实现 `WOPIHostService` 核心方法：`check_file_info`（返回文件元数据）、`get_file`（返回文件二进制）、`put_file`（写入文件+递增版本号+更新时间戳）
    - _需求: 3.1, 3.7_
  - [x] 9.2 实现 WOPI 锁管理：`lock`（Redis排他锁 key=`wopi:lock:{file_id}` TTL=30min）、`unlock`（校验lock_id→删除锁）、`refresh_lock`（校验lock_id→重置TTL），不同lock_id的Lock请求返回409
    - _需求: 3.3_
  - [x] 9.3 实现 WOPI 访问令牌：`generate_access_token`（JWT含user_id+project_id+file_id+过期时间）、`validate_access_token`（校验JWT有效性和权限）
    - _需求: 3.2_
  - [x] 9.4 实现 WOPI API 路由（`backend/app/routers/wopi.py`）：GET `/wopi/files/{file_id}` CheckFileInfo、GET `/wopi/files/{file_id}/contents` GetFile、POST `/wopi/files/{file_id}/contents` PutFile、POST `/wopi/files/{file_id}` Lock/Unlock/RefreshLock（通过 X-WOPI-Override 头区分）
    - _需求: 3.1_
  - [ ]* 9.5 编写属性测试：WOPI文件版本单调递增
    - **Property 6: WOPI文件版本单调递增**
    - 使用 Hypothesis 生成随机PutFile序列，验证file_version严格单调递增
    - **验证: 需求 3.7**
  - [ ]* 9.6 编写属性测试：WOPI锁互斥性
    - **Property 7: WOPI锁互斥性**
    - 使用 Hypothesis 生成随机Lock/Unlock序列，验证同一时刻最多一个有效锁
    - **验证: 需求 3.3**

- [x] 10. 底稿管理服务（CRUD + 离线编辑 + 状态管理）
  - [x] 10.1 实现 `WorkingPaperService.list_workpapers`（按循环/状态/编制人筛选）、`get_workpaper`（详情含索引+文件+QC状态）
    - _需求: 6.1_
  - [x] 10.2 实现 `WorkingPaperService.download_for_offline`：执行预填充→返回文件+当前file_version
    - _需求: 7.1_
  - [x] 10.3 实现 `WorkingPaperService.upload_offline_edit`：冲突检测→无冲突则替换文件+解析回写+递增版本→有冲突则返回冲突报告
    - _需求: 7.2, 7.3, 7.4, 7.5_
  - [x] 10.4 实现 `WorkingPaperService.update_status` 和 `assign_workpaper`
    - _需求: 6.1_
  - [x] 10.5 实现底稿管理 API 路由（`backend/app/routers/working_paper.py`）：GET 列表、GET 详情、POST generate（从模板集生成）、GET download、POST upload、PUT status、PUT assign、POST prefill、POST parse、GET wp-index、GET wp-cross-refs
    - _需求: 6.1-7.5_
  - [ ]* 10.6 编写属性测试：离线编辑版本冲突检测
    - **Property 9: 离线编辑版本冲突检测**
    - 使用 Hypothesis 生成随机版本号对，验证版本不匹配时检测到冲突
    - **验证: 需求 7.2, 7.3, 7.4**

- [x] 11. 检查点 — 确保WOPI Host、底稿管理、离线编辑正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 12. 底稿质量自检引擎
  - [x] 12.1 实现 `QCEngine` 基础框架：QCRule 抽象基类（severity、rule_id、check方法）、QCContext（工作簿+元数据+项目数据+公式引擎）、QCEngine.check 方法（加载底稿→执行所有规则→汇总结果→存储到 wp_qc_results）
    - _需求: 8.1, 8.2, 8.4_
  - [x] 12.2 实现阻断级规则（3条）：
    - `ConclusionNotEmptyRule`（Rule 1）：检查 Named Range `WP_CONCLUSION` 是否为空
    - `AIFillConfirmedRule`（Rule 2）：检查 AI 填充区（紫色底色+批注"AI填充"）是否全部确认
    - `FormulaConsistencyRule`（Rule 3）：比对公式单元格当前值与 FormulaEngine 实时计算结果，差异>0.01则报告
    - _需求: 8.1 Rules 1-3_
  - [x] 12.3 实现警告级规则（8条）：
    - `ManualInputCompleteRule`（Rule 4）：检查人工填写区空白项
    - `SubtotalAccuracyRule`（Rule 5）：检查内部合计数
    - `CrossRefConsistencyRule`（Rule 6）：检查交叉索引引用一致性
    - `IndexRegistrationRule`（Rule 7）：检查底稿编号在索引表中登记
    - `CrossRefExistsRule`（Rule 8）：检查引用底稿是否存在
    - `AuditProcedureStatusRule`（Rule 9）：检查关联审计程序执行状态
    - `SamplingCompletenessRule`（Rule 10）：检查抽样记录完整性
    - `AdjustmentRecordedRule`（Rule 11）：检查需调整事项是否已录入
    - _需求: 8.1 Rules 4-11_
  - [x] 12.4 实现提示级规则（1条）：
    - `PreparationDateRule`（Rule 12）：检查编制日期是否在进场日~报告日范围内
    - _需求: 8.1 Rule 12_
  - [x] 12.5 实现 `QCEngine.get_project_summary`：项目级QC汇总（total_workpapers、passed_qc、has_blocking、not_started、pass_rate）
    - _需求: 9.1_
  - [x] 12.6 实现质量自检 API 路由（`backend/app/routers/qc.py`）：POST qc-check 执行自检、GET qc-results 获取结果、GET qc-summary 项目级汇总
    - _需求: 8.1-9.3_
  - [ ]* 12.7 编写属性测试：QC阻断规则阻止提交
    - **Property 10: QC阻断规则阻止提交**
    - 使用 Hypothesis 生成随机底稿+QC结果，验证有阻断finding时不允许提交复核
    - **验证: 需求 8.3**
  - [ ]* 12.8 编写属性测试：QC结论区检查正确性
    - **Property 11: QC结论区检查正确性**
    - 使用 Hypothesis 生成随机结论区内容（含空/空白/有内容），验证Rule 1判断正确
    - **验证: 需求 8.1 Rule 1**
  - [ ]* 12.9 编写属性测试：QC公式一致性检查正确性
    - **Property 12: QC公式一致性检查正确性**
    - 使用 Hypothesis 生成随机公式值+偏差，验证差异>0.01时报告阻断finding
    - **验证: 需求 8.1 Rule 3**
  - [ ]* 12.10 编写属性测试：QC交叉索引检查正确性
    - **Property 13: QC交叉索引检查正确性**
    - 使用 Hypothesis 生成随机WP引用+索引，验证引用不存在时报告警告finding
    - **验证: 需求 8.1 Rule 8**
  - [ ]* 12.11 编写属性测试：项目级QC汇总一致性
    - **Property 16: 项目级QC汇总一致性**
    - 使用 Hypothesis 生成随机项目底稿集，验证汇总数据计算正确
    - **验证: 需求 9.1**

- [x] 13. 检查点 — 确保质量自检引擎正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 14. 复核批注服务
  - [x] 14.1 实现复核批注 CRUD：添加复核意见（写入 review_records，status=open）、回复意见（status→replied，记录 reply_text+replier_id+replied_at）、标记已解决（status→resolved，记录 resolved_by+resolved_at）
    - _需求: 5.2, 5.3, 5.4_
  - [x] 14.2 实现复核批注 API 路由（`backend/app/routers/wp_review.py`）：GET 列表、POST 添加、PUT reply、PUT resolve
    - _需求: 5.1-5.5_
  - [ ]* 14.3 编写属性测试：复核意见状态机合法转换
    - **Property 17: 复核意见状态机合法转换**
    - 使用 Hypothesis 生成随机状态转换序列，验证只允许合法路径
    - **验证: 需求 5.2, 5.3, 5.4**

- [x] 15. 事件联动：数据变更触发公式缓存失效
  - [x] 15.1 在 EventBus 中注册新的事件处理器：
    - ADJUSTMENT_CREATED/UPDATED/DELETED → FormulaEngine.invalidate_cache（失效涉及科目的公式缓存）
    - DATA_IMPORTED → FormulaEngine.invalidate_cache（失效全部公式缓存）
    - MAPPING_CHANGED → FormulaEngine.invalidate_cache（失效涉及科目的公式缓存）
    - _需求: 2.8, 4.5_

- [x] 16. ONLYOFFICE自定义取数函数插件
  - [x] 16.1 开发 ONLYOFFICE 插件项目骨架：`plugin/audit-formula/` 目录，包含 `config.json`（插件配置）、`index.html`（插件入口）、`code.js`（插件逻辑），通过 `AddCustomFunction` API 注册 TB/WP/AUX/PREV/SUM_TB 五个自定义函数
    - _需求: 4.1_
  - [x] 16.2 实现插件中的异步 API 调用逻辑：每个自定义函数内部通过 `fetch` 调用后端 `/api/formula/execute`，将返回值填入单元格；错误时显示 `#REF!` 并在 tooltip 中显示错误消息
    - _需求: 4.2, 4.3, 4.4_

- [x] 17. ONLYOFFICE复核批注插件
  - [x] 17.1 开发 ONLYOFFICE 侧边栏插件 `plugin/audit-review/`：显示复核意见列表（按创建时间排序），未解决意见珊瑚橙左边框（`#FF5149`），已回复意见水鸭蓝左边框（`#0094B3`）
    - _需求: 5.1, 5.5_
  - [x] 17.2 实现插件中的复核操作：添加意见（调用 POST API）、回复意见（调用 PUT reply API）、标记已解决（调用 PUT resolve API），操作后刷新列表
    - _需求: 5.2, 5.3, 5.4_

- [x] 18. 前端页面：底稿列表与索引
  - [x] 18.1 实现底稿列表页面 `WorkpaperList.vue`：左侧底稿索引树（按审计循环分组：B类→C类→D-N类），每个节点显示编号+名称+状态标签+编制人头像；右侧底稿详情面板（基本信息+操作按钮）
    - _需求: 6.1_
  - [x] 18.2 实现顶部筛选栏（按循环、状态、编制人筛选）和底稿操作按钮（在线编辑/下载/上传/自检/提交复核）
    - _需求: 6.1, 8.3_

- [x] 19. 前端页面：ONLYOFFICE编辑器集成
  - [x] 19.1 实现 ONLYOFFICE 编辑器页面 `WorkpaperEditor.vue`：全屏布局，通过 iframe 嵌入 ONLYOFFICE Editor，传入 WOPI discovery URL 和 access token；顶部工具栏（底稿编号+名称+状态+保存指示器+返回按钮）；底部状态栏（编制人+复核人+版本号）
    - _需求: 3.5, 3.6_
  - [x] 19.2 实现 ONLYOFFICE 不可用时的降级逻辑：检测 ONLYOFFICE 服务状态，不可用时显示"下载编辑"按钮替代 iframe
    - _需求: 3.8_

- [x] 20. 前端页面：质量自检与模板管理
  - [x] 20.1 实现质量自检结果弹窗/侧边栏 `QCResultPanel.vue`：按严重级别分组（阻断红色/警告黄色/提示灰色），每条finding显示规则编号+描述+单元格引用+期望值/实际值；底部提交复核按钮（有阻断时禁用）
    - _需求: 8.2, 8.3_
  - [x] 20.2 实现项目级QC汇总卡片 `QCSummaryCard.vue`：显示底稿总数、已通过自检、存在阻断问题、未编制、自检通过率；支持点击钻取到底稿列表
    - _需求: 9.1, 9.2, 9.3_
  - [x] 20.3 实现模板管理页面 `TemplateManager.vue`：模板列表（编号+名称+循环+版本+状态+操作）、模板集管理（名称+模板数+适用类型+操作）
    - _需求: 1.1-1.7_

- [x] 21. 前端集成与路由注册
  - [x] 21.1 在 Vue Router 中注册所有新页面路由（底稿列表、ONLYOFFICE编辑器、模板管理），在 `main.py` 中注册所有新 API 路由模块（formula、wp_template、working_paper、wopi、qc、wp_review）
    - _需求: 1.1-9.3_
  - [x] 21.2 实现前端 API 服务层 `workpaperApi.ts`：封装所有后端 API 调用（模板管理、取数公式、WOPI、底稿管理、质量自检、复核批注）
    - _需求: 1.1-9.3_

- [x] 22. 检查点 — 确保前端页面和集成正常
  - 确保所有测试通过，如有问题请询问用户。

- [x] 23. 抽样记录管理
  - [x] 23.1 创建 Alembic 迁移脚本，定义 `sampling_config` 表（UUID PK、project_id FK、config_name varchar、sampling_type enum statistical/non_statistical、sampling_method enum mus/attribute/random/systematic/stratified、applicable_scenario enum control_test/substantive_test、confidence_level numeric(5,4) nullable、expected_deviation_rate numeric(5,4) nullable、tolerable_deviation_rate numeric(5,4) nullable、tolerable_misstatement numeric(20,2) nullable、population_amount numeric(20,2) nullable、population_count int nullable、calculated_sample_size int nullable、is_deleted boolean default false、created_at、updated_at、created_by FK）及复合索引 (project_id, sampling_method)
    - _需求: 12.1_
  - [x] 23.2 创建 `sampling_records` 表（UUID PK、project_id FK、working_paper_id FK nullable、sampling_config_id FK nullable、sampling_purpose text、population_description text、population_total_amount numeric(20,2) nullable、population_total_count int nullable、sample_size int、sampling_method_description text、deviations_found int nullable、misstatements_found numeric(20,2) nullable、projected_misstatement numeric(20,2) nullable、upper_misstatement_limit numeric(20,2) nullable、conclusion text nullable、is_deleted boolean default false、created_at、updated_at、created_by FK）及复合索引 (project_id, working_paper_id)
    - _需求: 12.2_
  - [x] 23.3 在 `workpaper_models.py` 中新增 `SamplingConfig` 和 `SamplingRecord` ORM 模型，在 `workpaper_schemas.py` 中新增 `SamplingConfigCreate`、`SamplingRecordCreate`、`MUSEvaluation` Pydantic Schema
    - _需求: 11.1-11.6, 12.1-12.2_
  - [x] 23.4 实现 `SamplingService`：`create_config`（创建抽样配置+自动计算样本量）、`calculate_sample_size`（属性抽样/MUS/随机抽样公式）、`create_record`（创建抽样记录关联底稿）、`calculate_mus_evaluation`（MUS评价：projected_misstatement+upper_misstatement_limit）、`check_completeness`（检查底稿关联抽样记录完整性，供QC Rule 10调用）
    - _需求: 11.1-11.6_
  - [x] 23.5 实现抽样管理 API 路由（`backend/app/routers/sampling.py`）：GET/POST/PUT sampling-configs、POST calculate、GET/POST/PUT sampling-records、POST mus-evaluate
    - _需求: 11.1-11.6_
  - [x] 23.6 实现前端抽样管理面板：抽样配置表单（方法选择+参数输入+自动计算样本量）、抽样记录列表（关联底稿+总体描述+样本量+结果+结论）、MUS评价结果展示
    - _需求: 11.1-11.4_
  - [ ]* 23.7 编写属性测试：抽样样本量计算正确性
    - **Property 19: 抽样样本量计算正确性**
    - 使用 Hypothesis 生成随机抽样参数，验证样本量计算符合标准公式
    - **验证: 需求 11.2**
  - [ ]* 23.8 编写属性测试：抽样记录完整性校验
    - **Property 20: 抽样记录完整性校验**
    - 使用 Hypothesis 生成随机抽样记录（含完整/不完整），验证QC Rule 10判断正确
    - **验证: 需求 11.5**
  - [ ]* 23.9 编写属性测试：MUS错报推断计算正确性
    - **Property 21: MUS错报推断计算正确性**
    - 使用 Hypothesis 生成随机MUS抽样结果（含错报金额和污染因子），验证projected_misstatement和upper_misstatement_limit按MUS评价公式正确计算
    - **验证: 需求 11.4**

- [x] 24. 最终检查点 — 全量测试通过
  - 运行全部单元测试和属性测试，确保所有测试通过。如有问题请询问用户。

## 备注

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP 交付
- 每个任务引用了具体的需求编号，确保需求全覆盖
- 检查点任务确保增量验证，及时发现问题
- 属性测试验证通用正确性属性，单元测试验证具体示例和边界条件
- 所有21个正确性属性均已分配到对应的属性测试任务中（含新增的Property 19-21）
- ONLYOFFICE插件开发（任务16-17）建议在WOPI Host服务（任务9）完成后进行，需要先确保后端API可用
- 建议开发前做1-2周WOPI集成POC验证，确认ONLYOFFICE自定义函数的异步API调用机制可行
