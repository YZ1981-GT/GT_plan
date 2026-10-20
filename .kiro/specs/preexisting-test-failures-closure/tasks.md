# 任务：46 个预存失败用例逐一收口

- [x] 1. 逐组定根因（现象原文 / 根因 / 判定 / 修法）
  - 现象取自干净 HEAD 检出跑同一批文件；判定按「生产缺陷 / 测试过时 / 测试不封闭」
  - _需求：1.1_
  - 证据：design §0 总表 + §1.1~§1.12，12 组共 46 例（另 3 例 `test_dsh_discovery_task27` 已在 dsh-kb-ocr-local-first-routing Task 2 修复）

- [x] 2. 测试过时 / 不封闭的五组（G2 / G3 / G4 / G8 / G9）与 G5、G6
  - 按现行设计改精确断言，写明让它过时的提交；G5 打桩改到导入期绑定名，G8 补无令牌 403，G6 补空登记表与规则集钉死
  - _需求：1.2、1.3_
  - 证据：`test_index_source` 22 / `test_ai_content_structured` / `test_task4_run_contract` 93 / `test_archive_deprecated` 4 / `test_g1_classification` 28 / `test_g7_sub_integration` 18 / `test_qc_rule_definitions_loader` 5 全绿；无 `>=` / 跳过 / xfail

- [x] 3. G7 resolver 附加键透传（生产缺陷）
  - `_RESOLVER_PASSTHROUGH_KEYS` 白名单透传 step_status / link / detail；补 `TestRegisteredResolverPassthrough`
  - _需求：1.2、2.1_
  - 证据：`test_a16_sign_status_check_auto.py` 6 passed

- [x] 4. G10 extract_fields 合并（生产缺陷）
  - 规则优先，LLM 只补被请求且缺失的字段；用例钉死字段、来源顺序、提示词与未请求字段被丢弃
  - _需求：1.2、3.1_
  - 证据：`test_ocr_service.py` 22 passed，`test_ocr_fields.py` 同跑通过；字段清单列入 design §3 待确认

- [x] 5. G11 启动编排单一来源（生产缺陷）
  - registry 补齐 3 个 handler 注册 + 后台预热；worker 清单收成一份；lifespan 执行 `run_startup_tasks`；main.py 删 14 个重复辅助函数并移出行数白名单；health 输出 `startup`
  - 跟随改动：`test_formula_push_triggers` / `test_sync_registration_prewarm` / `test_schema_drift_detector`（移除 strict xfail）/ `probe_platform_baseline.py` / 4 处 docstring
  - _需求：1.2、2.1_
  - 证据：`test_startup_registry.py` 24 passed（新增 6 条守卫，worker 清单与里程碑两条加严）；事件总线订阅改前改后 139 = 139 逐项相等；worktree 第二实例与共享开发后端热重载后 `startup` 均 37 项、0 失败；预热日志与改前一致（29 个 adapter / 暖 11 个 / 失败 0 个）

- [x] 6. G12 覆盖率口径（生产缺陷，口径待确认）
  - 四个字段统一按 wp_code 前缀；扫描全部单字母目录（与 `load_prompt` 同一规则）
  - _需求：1.2、3.1_
  - 证据：`test_review_prompt_integration.py` 9 passed（恒等式 + A/B/C 入统计 + 夹具目录单测）；现值 142 / 141 / `["S1 (审计方案)"]`；review prompt 相邻 6 个文件 60 passed / 1 skipped（既有的「无 f0 登记」跳过）

- [x] 7. G1 WOPI 质控复核 15 例
  - (a) SQLite UUID 绑定改 `REPLACE(:x, '-', '')`，查回的 id 统一成 UUID；新增 `test_visibility_query_sqlite_compat.py`
  - (b) `_make_qc_ready` / `qc_ready_wp` 夹具 + 裸底稿恰好四条阻断 + 四项各缺一项恰好对应一条
  - (c) 列表用例迁到 `test_working_paper_list_api_pg.py`（真库事务回滚）
  - (d) put_file 被拒后还原磁盘（生产缺陷）；用例迁到 `test_wopi_put_file_rollback.py`（tmp 存储 + 发布 lane bundle）
  - 清理旧用例留下的 8 个 `backend/<uuid>/` 目录
  - _需求：1.2、1.3、2.1_
  - 证据：`test_wopi_working_paper_qc_review.py` 56 passed / 8 xfailed（既有非严格 xfail）；`test_wopi_put_file_rollback.py` 2、`test_visibility_query_sqlite_compat.py` 2 passed；列表真库 1 passed；真库探针成功路径 revision 0→1、被拒后磁盘还原；残留目录逐个核对后删除、重跑不再产生；`procedure_delegation_visibility` 真库 47 passed

- [x] 8. 变异证明
  - 每条生产修复与新守卫磁盘注入（验证 worktree），逐字节恢复并校验 sha256；判杀要求红在预期用例
  - _需求：2.2_
  - 证据：35/35 全部打红（首轮 32/34，两条存活 —— `extract_fields` 的「未请求字段」与可见集 UUID 归一 —— 各补一条用例后重跑全杀）；变异前同批测试基线全绿

- [x] 9. 回归与相邻测试
  - 12 个目标文件 + 4 个新文件全绿；相邻文件确认无新增失败
  - _需求：2.3_
  - 证据：目标集 311 passed / 1 skipped（真库用例，另行真库跑过）/ 6 xfailed / 2 xpassed（WOPI 锁用例随运行顺序 XPASS，见 design §2 #6）；相邻 15 个文件 343 passed，失败的 3 例是 `test_auto_data_resolvers` 干净 HEAD 既有（design §2 #1）；DSH / 知识库相关 717 passed；`ruff --select F,E9` 对全部改动文件与 HEAD 对比新增 0 条
  - 提交前干净检出（临时索引建出的提交检出到验证 worktree）复跑：后端 435 passed + DSH / 知识库 769 passed + 真库 50 passed + 前端 vitest 98 passed；pre-commit 行数门对 3 个触碰前已超 800 行且未登记的文件（`test_task4_run_contract` / `test_task31_phase_c_gate` / `mutate_dsh_agent_panel_guards`）按惯例登记白名单（理由 + 拆分方向），`review_prompt.py` 撤回仅有的 docstring 改动不再触碰

- [x] 10. 待确认事项与范围外发现如实登记
  - _需求：3.1、2.1_
  - 证据：design §2（8 项，含 main.py 三个无鉴权 `/api/_debug/a51-*` 端点）、§3（覆盖率口径、OCR 字段清单）
