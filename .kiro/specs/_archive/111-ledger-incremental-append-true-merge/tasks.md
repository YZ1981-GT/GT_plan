# 实施计划：序时账增量追加改为真追加（ledger-incremental-append-true-merge）

> 以 design.md 为准。标完成须有代码 + 测试证据 + 至少一条磁盘变异证明（备份到 `tmp_ledger_append/mutations/`，注入、确认红在预期处、逐字节还原核对 sha256）。环境做不到的标 `[ ]*`。约束同 `voucher-identity-writeback-and-audit-phase/tasks.md` 页头；临时产物放 `tmp_ledger_append/`。依赖：凭证差异报告用 `voucher_identity.py`（该 spec 任务 2），未落地则按其 design §2 先建。

- [x] 1. 合并函数与表归类清单（需求 1、5.2，ADR-LA-02/03/05）
  - 新建 `ledger_dataset_merge.py`：`merge_into_staged`、`DATASET_BOUND_TABLES`、行数守恒检查
  - Files: `backend/app/services/ledger_dataset_merge.py`、`backend/tests/test_ledger_dataset_merge.py`、`backend/tests/test_dataset_bound_tables_classified_pg.py`
  - Verify: 两策略月份集合、整表沿用、基准变化报错、守恒不等阻断；归类守卫与 information_schema 逐一相等。变异：覆盖策略复制重叠月 → 守恒用例红；清单删 `account_chart` → 守卫红
  - 证据（2026-10-29）：`ledger_dataset_merge.py`（459 行）编排，低层跨方言复制与 DTO 分拆为 `_ledger_dataset_merge_copy.py` / `_ledger_dataset_merge_types.py`；`merge_into_staged` 只写 staged、只 flush 不 commit。覆盖策略复制基准未被文件覆盖的月份；跳过策略先删 staged 重叠月再复制全部基准月；NULL 日期按内部 bucket 0 合并且单独回报，不混进 1~12 月。四表逐表执行 `expected = kept_file + copied_base == actual`，不符 `MergeRowCountError`。快照表仅在文件未提供时沿用；一个 `append_inherit` ImportBatch 记录来源；`source_summary.append` 留策略、基准、月份、逐表计数与余额沿用确认
  - 方向覆盖随被继承行重映射：只给真实被复制且有 override 的源行预分配新 id，复制后 `direction_override.record_id` 指向 staged 新行；被覆盖月份的 override 不沿用。客户科目只复制 `source=client`；老项目 dataset_id=NULL 在 active 版本没有专属科目时才迁入 staged。因原唯一索引禁止两个 dataset 同码共存，新增 V215/R215 与 ORM 两个部分唯一索引（dataset 版本 / legacy NULL）；`mapping_service` 改只读 active 版本，避免历史版本同码重复参与映射；失败清理补 `direction_override`
  - 表归类现扫新增第一份 spec 的 `interim_survival_checks`，最终 11 张 dataset_id 表逐一闭合：periodic 2、snapshot 4、not_import_product 5；静态组互斥与真 PG information_schema 双守卫，避免 pg_only 标在模块级把静态守卫一起 skip（首轮变异抓到后修正）
  - 测试：SQLite 8 passed（覆盖 / 跳过、基准不变、快照与 legacy 科目、余额确认、方向覆盖新 id、行数闸门、active 科目映射）；相邻 `test_dataset_import_platform.py` 23 passed；真 PG 4 passed（分区表 INSERT…SELECT、V214→双 dataset 同码→R214、11 表归类，均在【测试】项目外层事务回滚）。变异 t1_m01 覆盖策略把重叠月也复制、t1_m02 去基准 id 比对、t1_m03 清单删 account_chart，三条都在预期节点红并按 sha256 逐字节恢复

- [x] 2. 两条导入链接入与提交参数（需求 1.1、1.5、2.1、2.2，ADR-LA-04）
  - `options.append = {strategy, base_dataset_id}`：两个提交入口写入、runner 透传；`execute_pipeline` 与 `smart_import_streaming` 激活前调用合并；MergeReport 写 staged `source_summary`
  - v2 提交删掉 `apply_incremental` 分支；`/ledger/smart-import` 增 `append_strategy`（`ledger_penetration.py` 净增 0 行）
  - Files: `ledger_import/pipeline.py`、`smart_import_engine.py`、`import_job_runner.py`、`ledger_import_application_service.py`、`ledger_import/orchestrator.py`、`routers/ledger_import_v2.py`、`routers/ledger_penetration.py`
  - Verify: 两条链各一例：追加后 staged 含继承月份、`source_summary` 记录完整；基准在提交后被别的导入替换 → 报错不激活。变异：去掉激活前基准断言 → 用例红
  - 证据（2026-10-29）：`freeze_append_options` 是两个提交入口冻结 active id 的单一实现；旧 `/ledger/smart-import` 用 Form 传 `append_strategy / balance_carry_confirmed`，v2 `SubmitRequest` 保留兼容 `incremental / overlap_strategy / file_periods` 但不再信任客户端月份做删除。两个入口都把 `{strategy, base_dataset_id, balance_carry_confirmed, no_base}` 写 `ImportJob.options.append`，无 active 时留 `no_base=true` 并按首次普通导入；runner 向 v2 / 旧引擎各透传一次
  - 两个生产引擎都在文件写完、激活前调用同一 `merge_into_staged`，并把实际四表行数交 DatasetService 守恒门；`DatasetService.activate(expected_active_dataset_id=...)` 在激活事务里对 active 行加锁后二次核对，提交后基准变化会失败且不切版本。v2 / 旧链真实 SQLite 小账各一例：v2 文件月份 1/2/3/12 + 基准 4 月 → 新 active 五个月；旧 CSV 12 月 + 基准 1 月 → 新 active 两个月，基准行不改；两链都回 append / voucher_diff 并写 source_summary
  - 智能导入映射缺陷按同一链路根因纳入：新 `ledger_import_mapping_contract.py` 把 v2 列表、旧界面 `{文件/工作表: mappings}` 与全局列映射统一；application service 入库前规范化，v2 / 旧引擎都经 `resolve_sheet_mapping` 读取。修前用户确认「凭证字」会被丢弃并退自动映射；现 6 个契约测试与旧链真 CSV 证明确认映射实际控制入库
  - 顺带修真链测试抓到的 `fast_writer` SQLite UUID 口径：无类型 Core insert 原把 UUID 写成带连字符字符串，UUID(as_uuid=True) 查询绑 32 位 hex，文件行写了却查不到；统一写 `UUID.hex`。Task 1~4 单元组 37 passed；两引擎 e2e 3 passed（含合并后完整数据集再校验，阻塞即清 staged、base 保持 active）。变异 t2_m01 去 v2 runner 透传、t2_m02 退回旧 mapping、t2_m03 去激活二次锁、t2_m04 UUID 改回带连字符，均在预期行为节点红并恢复

- [x] 3. 删除导入前删行、余额表沿用闸门（需求 2.3、3）
  - `/ledger-data/incremental/apply` 返回 410；删除 `apply_incremental`（删前 grep 调用方，保留 `compute_incremental_diff`）；`/incremental/detect` 增「将继承月份」
  - 激活闸门：余额表沿用且序时账新增月份 → L2 警告需确认留痕
  - Files: `routers/ledger_data.py`、`ledger_data_service.py`、激活评估（`ledger_import/validator.py` 或旧链对应处）
  - Verify: 410 端点测试；闸门未确认不激活、确认后留痕。变异：闸门判断取反 → 用例红
  - 证据（2026-10-29）：全仓调用方收口后删除 `ledger_data_service.apply_incremental` 与导出；v2 submit 不再在 active 上预删。兼容端点 `/incremental/apply` 保留 URL 但固定返回 410 `INCREMENTAL_APPLY_RETIRED`，挂项目 edit 门；detect 挂 readonly 门并按策略回 `new / inherited / skipped_file / overwritten` 四组月份，月份非 1~12 或空集合 422
  - 余额确认是独立 `balance_carry_confirmed`，不复用会放开其他校验错误的 `force_activate`：序时账出现基准没有的新月份且 tb_balance / tb_aux_balance 至少一张沿用时，未确认抛 `BalanceCarryConfirmationRequired`，确认值与实际 `balance_confirmation_required` 一并留在 source_summary。v2 追加在合并后重新跑 `run_dataset_business_validation`，测试在该回调内逐月反读已合并 staged，证明校验看到完整账套而非只看上传文件；阻塞时清理 staged，基准仍 active
  - 数据概览顺带修复同根可见性：period 分布原只按项目 / 年度扫所有非删行，会把 active + superseded 多版本叠加；现按 active dataset_id 查询，并在 `summary.datasets[year].source_summary` 返回合并 / 差异报告供数据管理页查看。变异 t3_m01 反转余额确认判断、t3_m02 把退役端点改 200，均精确打红并恢复

- [x] 4. 凭证差异报告（需求 4，ADR-LA-06）
  - 新建 `ledger_dataset_voucher_diff.py`，两条链激活前调用（追加与整年重导都生成），fail-open 记原因
  - Files: `backend/app/services/ledger_dataset_voucher_diff.py`、`backend/tests/test_ledger_dataset_voucher_diff.py`
  - Verify: 新增 / 删除 / 变化三类与按月汇总；同日同号不同凭证字不误判。变异：签名去掉金额 → 变化用例红
  - 证据（2026-10-29）：新服务按完整 VoucherKey（年度、主体、日期、凭证字、号）聚合；分录签名只含科目、借贷栏、带符号两位金额及重复次数，不因摘要变化误报。新增 / 删除 / 分录变化按月回张数、涉及金额、净变动；每类样例稳定排序最多 20 条；同日同号 FY / ZZ 分开。PostgreSQL 用 MATERIALIZED CTE 在库内聚合 base/new/diff，一次查询只回最多 36 组汇总 + 60 个样例，不把明细拉进 Python；SQLite 走等价算法
  - `build_and_store_voucher_diff` 对追加与整年重导都取 staged.previous_dataset_id；两条引擎在激活前调用并写 `source_summary.voucher_diff`，失败只回 `status=failed + reason`、不阻断导入，完成回执透传。SQLite 4 passed、真 PG 回滚事务 1 passed、两条引擎 e2e 都断言报告已生成；t4_m01 从分录签名去掉金额后「同科目金额变化」漏报，行为测试红并恢复

- [x] 5. 前端入口与提示（需求 2.2~2.4、1.6、3.1、4.2）
  - 数据管理弹窗去「执行清理」、预览四类月份、带策略进入上传；序时账页与导入页提交带 `append_strategy`；完成页显示合并结果、余额表沿用提示、差异报告
  - Files: `LedgerDataManager.vue`、`LedgerPenetration.vue`、`useLedgerImport.ts`、`ImportCompletionSummary.vue`、`services/ledgerImportV2Api.ts`
  - Verify: 组件单测（预览与提交参数）；ESLint；单区域 vue-tsc
  - 证据（2026-10-29）：数据管理弹窗删「执行清理」与旧 `incrementalApply` apiPath，只做 readonly detect；展示新增 / 继承 / 跳过文件 / 文件替代四组月份，上传事件传 `{year,strategy,filePeriods}`。序时账页进入追加模式后明确提示「当前账套成功前不改动」，预览必须勾选余额沿用确认，旧 smart-import Form 经 `appendFormFields` 发策略与确认。独立 v2 页面支持 `?mode=append&strategy=...`，通用 Dialog 支持 appendStrategy prop；两者未确认不提交并在 JSON 体发相同字段
  - 新 `ledgerAppendResult.ts` 是请求整形 / 月份 / 差异显示单一来源；`LedgerAppendResultPanel.vue` 展示策略、文件/继承/跳过/替代月份、四类快照沿用、余额口径警告和新增/删除/变化凭证三卡。旧完成页 `ImportCompletionSummary` 与 v2 `ImportProgress` 都挂该面板；后者从 SSE `result` 或 GET `result_summary` 取数据。数据管理「当前账套」也从 summary.source_summary 查看同一报告；差异生成失败明确显示原因，不伪装成 0 差异
  - 生产上实际导入逻辑仍在 `LedgerPenetration.vue`；`useLedgerImport.ts` 现扫 0 调用方，只改其过期可见文案，不把未接线副本当交付。顺带给 ColumnMappingEditor 三个模板回调补准确 `MappingRow` 类型，使本区域 vue-tsc 从 3 个既有隐式 any 到 0；LedgerImportPage 4 个既有 stylelint 字面量改令牌/合法 special 注释
  - 验证：`ledgerAppendFlow.spec.ts` 7 passed，单区域 vue-tsc 0，新增文件 ESLint 0、相关文件 ESLint 0 error，相关样式 stylelint 0，IDE diagnostics 0。变异 t5_m01 丢 Form 追加字段、t5_m02 emit 退回只传年度、t5_m03 去 v2 完成面板、t5_m04 吞差异失败原因，4 条全部在预期测试红并逐字节恢复

- [x] 6. 端到端验收（需求 5.1、6）
  - `test_ledger_append_e2e_pg.py`：导入 1~11 月 → 追加 12 月（覆盖 / 跳过）→ 12 个月可见 → 回滚后逐表行数与金额一致；和平药房规模耗时记录（design §3）
  - 【测试】项目浏览器全流程，清理对账；变异记录汇总；干净 worktree 跑要提交的树；INDEX.md 登记
  - 证据（2026-10-29）：后端本 spec 套件 64 passed / 7 skipped（含 SQLite、真 PG、两引擎 E2E、V215、映射、凭证差异和数据集激活回滚）；`test_ledger_append_wiring.py` 12 passed。重跑磁盘变异 16 条：t1_m01~m03、t2_m01~m04、t3_m01~m02、t4_m01~m03、t5_m01~m04 全部在预期断言红并逐字节恢复 SHA256。`t4_m02` 证明 PG 签名必须含金额，`t4_m03` 证明差异 fail-open 必须使用 SAVEPOINT。
  - 真 PG 性能：和平药房 active 1,147,414 条序时账、2,732,674 条辅助明细账，按月 `INSERT … SELECT` 合并 1,307.94 秒、凭证差异 54.59 秒，事务回滚后 staged 残留 0；相对未分月复制 1,781.04 秒快约 26.6%，但仍约 21.8 分钟，未达到 5 分钟阈值，已如实记录在 `tmp_ledger_append/out/real_performance.json`。
  - 浏览器实测（私有 9983/3032）：【测试】序时账真追加走查项目导入基准 1~11 月后，数据管理→增量追加识别新增 12 月/重叠 11 月，选择 overwrite、上传 4 行文件、确认余额表沿用；完成页显示继承 1~10 月、11 月文件替代、余额表沿用提示、凭证差异新增 1/删除 0/变化 1。真 PG 对账新 active `505c52db`：12 月、每月两行；11 月借/贷各 1110，12 月各 1200，基准 `8e629fe1` 保持 22 行及 11 月各 110。通过 UI 回滚后 active 恢复 `8e629fe1`、仅 1~11 月且金额逐月恢复。截图：`tmp_ledger_append/shots/browser_incremental_preview_overwrite.png`、`browser_incremental_append_complete.png`、`browser_incremental_append_rollback.png`。
  - 浏览器首轮发现完成 ImportJob 后 queue batch 未提交、导致 batch 留 `processing`；根因是两个 runner 成功路径在独立 `status_db` 调用 `complete_job` 后没有 commit。两处补 `await status_db.commit()`；超时分支先提交 staged 的失败状态，避免随后 `fail_job` 的 rollback 吞掉。AST 守卫钉住两条成功路径都在 `complete_job` 后提交。修复后新作业/批次均为 `completed`、record_count=26、Redis `import_lock:active_set` 无该项目成员。
  - 测试项目经平台 `DELETE /api/projects/{id}` 软删除（200）；详情 404、项目列表无该 id 与同名前缀项目，数据库项目行 `is_deleted=true`、`deleted_at` 与删除人保留，未直接删库。
  - 终检：追加前端流程 `ledgerAppendFlow.spec.ts` 7 passed；局部 `vue-tsc` 0 error；相关 ESLint 0 error（35 条既有规则 warning）；相关 Stylelint 0；本 spec 文件清单行数门 0；`git diff --check` 0。类型检查曾真实发现弹窗自定义 `ConfirmedMapping` 与全局 DTO 的 `aux_dimension_columns` 可空性漂移、三个模板 change 参数隐式 any、抽样写接口可传空年度；已统一导入全局 DTO、改 `$event` 事件参数、空年度直接阻止写请求。Stylelint 再发现同文件已有 `word-break: break-word` 与 12px 字面量；改为 `overflow-wrap: anywhere` 和 `--gt-font-size-xs`，保持 12px 视觉令牌口径。