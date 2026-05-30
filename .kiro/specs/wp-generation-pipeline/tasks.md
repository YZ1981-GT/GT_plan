# 实施计划：账→稿生成管线端到端跑通（wp-generation-pipeline）

## 概述

本计划把 design.md 的「诊断驱动」设计转化为增量式、有测试保护、可逐个勾选的编码任务。核心方法论是**先实跑定位、再针对性修复、最后真实数据集成验收**——绝不以「端点存在 + 单测绿」充当验收证据。

任务排序遵循依赖与诊断驱动原则：

1. **基线实跑**（Task 1）：对 df5b8403 跑通现状，把真实状态固化为基线，定位真断点。
2. **核心修复**（Task 2–5）：parsed_data 填充（真断点，最高优先）→ generate_from_codes 改造（失败隔离 + 结构化返回 + 二段创建）→ 幂等与跳过保护 → 前置门禁。
3. **属性测试 / 单元测试**（紧随每个实现，沿用 design 的 Property 1–10）+ Checkpoint（Task 6）。
4. **取数路径与渲染派生验证**（Task 7–8，需求 3 / 4）。
5. **实跑验证脚本 + 真实数据集成验收**（Task 9–11，需求 7，终极验收，不可用单测绿替代）。

环境约定（Windows 铁律）：`python`（非 `python3`）；backend cwd 用 `..\.venv\Scripts\python.exe`；多命令用 `;` 不用 `&&`；PG 容器 `audit-postgres` / 库 `audit_platform`；测试 `python -m pytest backend/tests/... -v --tb=short`。属性测试用 hypothesis，≥100 iter（本地完整验证），注释标注 `# Feature: wp-generation-pipeline, Property N: ...`。

## 任务

- [x] 1. 对 df5b8403 实跑现状基线（诊断驱动起点）
  - 编写一次性诊断脚本 `backend/scripts/_baseline_wp_pipeline.py`（`_` 前缀，用完即删）
  - 调 `WpMappingService(db).recommend_workpapers(df5b8403, 2025, "standalone")` → 打印 wp_codes 数量（预期 ~63）
  - 调 `generate_from_codes` 等价逻辑跑一次 → 打印当前返回（created/skipped）
  - PG 实查 `SELECT count(*) FROM working_paper / wp_index WHERE project_id=...` → 记录真实计数（预期当前 0）
  - 抽查新建 `WorkingPaper.parsed_data` 是否为 NULL（确认真断点 ⑥），抽查 `bound_dataset_id` 是否被设置（确认 ⑦）
  - PG 实查 `trial_balance` 行数 + 是否存在缺 `standard_account_code` 的记录（确认 ② 取数源就绪度）
  - 把以上真实结果写入基线记录（`docs/uat/wp-generation-pipeline-baseline.md`），作为修复前的事实地基
  - _Requirements: 7.1, 7.3, 1.3_

- [x] 2. 实现 parsed_data 填充服务（真断点 ⑥，最高优先）
  - [x] 2.1 新增 `backend/app/services/wp_parsed_data_service.py`
    - 实现纯函数 `_read_xlsx_structure(file_path) -> dict`：openpyxl 读 xlsx 各 sheet → 构建 `{sheet_name: {cells, columns}}`（无 DB、无副作用，便于测试）
    - 实现 async `populate_parsed_data(db, wp, wp_code, wp_name, cycle)`：调 `_read_xlsx_structure(wp.file_path)` → 写 `wp.parsed_data = {"html_data": structure, "wp_code": ..., "generated_at": iso8601}` + `flag_modified(wp, "parsed_data")`
    - 结构对齐 HTML 渲染器消费的 `parsed_data['html_data'][sheet_name]` 形态
    - _Requirements: 2.2_

  - [x]* 2.2 编写 Property 2 属性测试
    - **Property 2: parsed_data 内容填充**
    - 生成随机模板 sheet 结构 → `populate_parsed_data` → 断言 `parsed_data.html_data` 非空且至少含一个 sheet 结构
    - `# Feature: wp-generation-pipeline, Property 2: 对任意新建的 WorkingPaper，其 parsed_data 非空且包含 html_data`
    - **Validates: Requirements 2.2**

  - [x]* 2.3 编写 `_read_xlsx_structure` 单元测试
    - 对一个真实致同模板 xlsx 的解析（具体示例），断言 sheet 名 / cells / 表头单元格被正确读出
    - 覆盖边界：空 workbook、单 sheet、多 sheet
    - _Requirements: 2.2_

- [x] 3. 改造 generate_from_codes：二段创建 + 失败隔离 + 结构化返回
  - [x] 3.1 在单 wp_code 处理末尾接入 `populate_parsed_data`（在 `fill_workpaper_header` 之后调用，确保读到含表头的 xlsx）
    - 确保每个新建 `WpIndex` 都同步建出 `wp_index_id` 指向它、`file_path` 非空的 `WorkingPaper`
    - _Requirements: 1.1, 1.2, 2.1_

  - [x] 3.2 用 savepoint 实现单条失败隔离
    - 单 wp_code 的全部子步骤（建 index / 建 wp / 绑定 / 表头 / 填充）包在 `async with db.begin_nested():` 内
    - 该条抛异常时仅回滚 savepoint，捕获并 `failures.append({"wp_code": code, "error": str(e)})` + `logger.warning`，循环继续，不破坏整批
    - `populate_parsed_data` 失败计入该条 failures（parsed_data 是核心产物）
    - _Requirements: 6.3, 6.5_

  - [x] 3.3 改造返回为结构化结果
    - 返回 `created` / `skipped` / `failures` + `created_codes` / `skipped_codes` 列表 + 中文 message
    - 函数末尾统一 `await db.commit()` 提交所有成功条目
    - _Requirements: 1.4, 5.5, 6.4_

  - [x]* 3.4 编写 Property 1 属性测试
    - **Property 1: 二段一一对应**
    - 生成随机去重 wp_codes 列表 → 生成 → 断言每个新建 code 恰好一条 WpIndex + 一条 wp_index_id 指向它、file_path 非空的 WorkingPaper，两表同 code 记录数相等
    - **Validates: Requirements 1.1, 1.2, 2.1, 2.5**

  - [x]* 3.5 编写 Property 6 属性测试
    - **Property 6: 返回结构与 DB 实际变化一致**
    - 断言返回含 created/skipped/failures + created_codes/skipped_codes，且与 DB 中 wp_index/working_paper 真实变化一致（新建数==created、跳过数==skipped、失败 code 不出现在新建记录中）
    - **Validates: Requirements 1.4, 5.5, 6.4, 7.5**

  - [x]* 3.6 编写 Property 7 属性测试
    - **Property 7: 单条失败隔离**
    - 在随机位置注入一个必失败的 wp_code（mock 模板写入抛异常）→ 断言该 code 被记录失败原因，其余 code 的 WpIndex/WorkingPaper 仍正常创建
    - **Validates: Requirements 6.3, 6.5**

  - [x]* 3.7 编写 Property 10 属性测试
    - **Property 10: 快照绑定**
    - 构造存在 active `ledger_datasets` 的场景 → 断言新建 WorkingPaper 的 `bound_dataset_id` 等于当前 active dataset id
    - **Validates: Requirements 1.5**

  - [x]* 3.8 编写 savepoint 隔离单元测试
    - 两条 code 一成功一失败 → 断言成功条入库、失败条未入库、整批不回滚
    - _Requirements: 6.3, 6.5_

- [x] 4. 幂等与跳过保护
  - [x] 4.1 确认/强化去重跳过逻辑
    - 已存在对应 `WpIndex` 的 wp_code 被跳过并计入 `skipped` + `skipped_codes`
    - 跳过时保留该底稿已有 `parsed_data` 与 `bound_dataset_id` 不变（不重写）
    - _Requirements: 5.1, 5.4_

  - [x]* 4.2 编写 Property 4 属性测试
    - **Property 4: 幂等——重复生成计数不变**
    - 同一项目以相同列表连续执行两次 → 断言 working_paper / wp_index 计数与首次一致，已存在 code 第二次被计入 skipped
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [x]* 4.3 编写 Property 5 属性测试
    - **Property 5: 跳过不破坏已有数据**
    - 对被跳过的已存在底稿，断言 parsed_data 与 bound_dataset_id 调用前后保持不变
    - **Validates: Requirements 5.4**

  - [x]* 4.4 编写幂等去重边界单元测试
    - 覆盖：空列表、单元素列表、全部已存在的列表
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 5. 前置门禁（语义纠正版）+ 端点接入
  - [x] 5.1 在 `PrerequisiteChecker` 新增 `_check_generate_from_codes_prerequisites`
    - 检查 `trial_balance > 0` 行（与推荐链数据源一致），无数据返回 `{ok: False, message(中文), prerequisite_action: "recalc"}`
    - 在 `check()` 的 checks 字典注册 `"generate_from_codes"` 分支
    - _Requirements: 6.1, 6.2_

  - [x] 5.2 端点接入门禁
    - `generate_from_codes` 开头调 `PrerequisiteChecker().check(db, project_id, year, "generate_from_codes")`
    - 不通过抛 `HTTPException(status_code=422, detail=check)`（明确 422，非 400 / 非 500）
    - _Requirements: 6.1, 6.2_

  - [x]* 5.3 编写 Property 8 属性测试
    - **Property 8: 前置门禁拦截返回 422 + 中文诊断**
    - 构造无 trial_balance 数据场景 → 断言返回 HTTP 422 + 列出未满足前置项的中文 detail（非通用错误 / 非 500）
    - **Validates: Requirements 6.1, 6.2**

  - [x]* 5.4 编写门禁分支注册单元测试
    - 断言 `check(..., "generate_from_codes")` 正确路由到新分支（而非误用 generate_workpapers 的 template_set 检查）
    - _Requirements: 6.1, 6.2_

- [x] 6. Checkpoint - 核心修复测试全绿
  - 运行 `python -m pytest backend/tests/... -v --tb=short`，确保 Task 2–5 的单元测试与属性测试全部通过，有疑问询问用户。

- [x] 7. 标准科目取数路径澄清与验证（需求 4）
  - [x] 7.1 在代码与文档中断言取数走 `trial_balance.standard_account_code`
    - 确认 `recommend_workpapers` / `get_prefill_data` 经 `TrialBalance.standard_account_code.in_(codes)` 取数，而非 `tb_balance.account_code`
    - 在 design 取数路径章节落实断言点（区分 TB_Balance 仅 account_code vs Trial_Balance 含 standard_account_code）
    - _Requirements: 4.1, 4.2_

  - [x]* 7.2 编写 Property 9 属性测试
    - **Property 9: 标准科目取数走 Trial_Balance**
    - 生成随机 trial_balance 数据集 → 取数 → 断言命中的均为 `trial_balance.standard_account_code`，取数结果 code 是 `standard_account_code` 的子集
    - **Validates: Requirements 4.2**

- [x] 8. 底稿渲染派生验证（需求 3）
  - [x] 8.1 实现/接入派生检查
    - 对已生成底稿经 `get_classification(wp_code, project_id)` + `derive_component_type` 派生 componentType
    - 缺 `workpaper_sheet_classification` 记录时按 wp_code 前缀 fallback 派生，并在诊断信息中标注缺分类数据（需求 3.5）
    - _Requirements: 3.2, 3.3, 3.5_

  - [x]* 8.2 编写 Property 3 属性测试
    - **Property 3: componentType 按分类正确派生**
    - 生成随机 wp_code（覆盖 D 类 / B 目录 / 缺分类三类）→ 断言 D 类派生为非 univer 的 HTML componentType、B 目录派生 `b-index`、缺分类按前缀 fallback 不返回空白/错误
    - **Validates: Requirements 3.2, 3.3, 3.5**

- [x] 9. 实跑验证脚本 `verify_wp_generation_pipeline.py`（需求 7，核心验收工具）
  - [x] 9.1 实现脚本骨架（无 `_` 前缀，正式可重复工具）
    - 位置 `backend/scripts/verify_wp_generation_pipeline.py`，用法 `..\.venv\Scripts\python.exe scripts/verify_wp_generation_pipeline.py --project df5b8403 --year 2025 [--report]`
    - 步骤：recommend → precheck → generate → count（PG 实查 working_paper / wp_index）→ assert → idempotent（再跑一次断言计数不变）
    - _Requirements: 7.3_

  - [x] 9.2 实现断言与诊断输出
    - 断言 working_paper > 0 / wp_index == working_paper 计数一致 / parsed_data 非空 / 返回 created·skipped 与 DB 真实计数一致
    - 诊断输出：缺失 WorkingPaper 的 wp_code（需求 2.3）、parsed_data 为空的 wp_code（需求 2.4）、trial_balance 缺 standard_account_code 的科目（需求 4.5）
    - `--report` 输出 markdown 报告到 `docs/uat/`
    - _Requirements: 2.3, 2.4, 4.5, 7.5_

- [x] 10. 真实数据集成验收：对 df5b8403 实跑（终极验收，不可用单测绿替代）
  - [x] 10.1 端到端实跑 `verify_wp_generation_pipeline.py` 并断言通过
    - 断言 `working_paper` 计数 > 0（需求 1.3 / 7.4）
    - 断言 `wp_index` 计数 == `working_paper` 计数（需求 2.5 / 7.5）
    - 断言返回 created / skipped 与 DB 真实计数一致（需求 7.5）
    - 断言至少 1 张 D 类 + 1 张 B 目录底稿存在、parsed_data 非空、componentType 派生正确（需求 3.4 / 7.4）
    - 二次调用断言计数不变（幂等，需求 5.2 / 5.3）
    - 断言取数结果与 trial_balance 对应标准科目余额一致（需求 4.4）
    - 三层一致校验：DB（`docker exec audit-postgres psql -d audit_platform`）+ ORM（`WorkingPaper.parsed_data`）+ service（返回统计）三者对账一致
    - 把实跑产出的真实结果归档到 `docs/uat/`（替换 Task 1 的基线，记录修复后状态）
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 1.3, 2.5, 3.4, 4.4, 5.2, 5.3_

- [x] 11. Final Checkpoint - 全量验证
  - 运行完整单元/属性测试 + `verify_wp_generation_pipeline.py` 实跑，确保链路在 df5b8403 上端到端跑出正确结果，有疑问询问用户。
  - 清理 Task 1 的一次性诊断脚本 `_baseline_wp_pipeline.py`。

## 说明

- 标 `*` 的子任务为可选（属性测试 / 单元测试），可为快速 MVP 跳过；顶层任务与核心实现子任务不带 `*`，必须实现。
- 每个属性测试对应 design 的单一 Correctness Property（Property 1–10），注释标注 Property 编号 + 验证的需求条款，hypothesis ≥100 iter（本地完整验证）。
- Task 1 基线实跑是诊断驱动的起点：先把 df5b8403 的真实现状固化，再据此修复。
- Task 10 真实数据集成验收是本 spec 的终极验收证据，端点存在性 grep 与单测绿**不构成**充分验收（需求 7.2）。
- 本计划仅含编码 / 测试 / 验证类任务，不含部署、用户培训、性能压测等非编码活动。
