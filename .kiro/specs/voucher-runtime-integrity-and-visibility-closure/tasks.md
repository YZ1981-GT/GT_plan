# 凭证运行完整性与可见性收口 — 任务

## 批次 1：鉴权缺口修复（R1 + R2 + R3）

- [x] 1. R1 单笔挂凭 `working_paper_id` 归属校验
  - 文件：`backend/app/routers/voucher_links.py` `sample_voucher()`
  - 在 `_resolve_voucher_key` 之前插入 `_project_workpapers()` 校验
  - `working_paper_id` 非空且不在项目中 → 422 `WP_NOT_IN_PROJECT`
  - `working_paper_id=None` → 跳过（允许无底稿挂凭）
  - AC：别的项目底稿 → 422；已删除底稿 → 422；本项目底稿 → 正常创建；不传 → 正常创建

- [x] 2. R1 单笔挂凭 `sampling_record_id` 归属校验
  - 文件：`backend/app/routers/voucher_links.py` `sample_voucher()`
  - 查 `SamplingRecord` 表验证 `project_id` 匹配且 `is_deleted=false`
  - AC：别的项目 sr → 422 `SAMPLING_RECORD_NOT_IN_PROJECT`；已软删 sr → 422；不传 → 正常创建

- [x] 3. R2 `/voucher-links/query` 底稿可见性过滤
  - 文件：`backend/app/routers/voucher_links.py` `query_voucher_links()`
  - 在 return 之前收集所有非 None 的 `working_paper_id`，调用 `_visible_wp_ids()` 过滤
  - `wp_id=None` 的记录保留（旧登记无底稿）
  - AC：不可见底稿的记录被排除；`wp_missing` 标记逻辑不变；无底稿记录始终可见

- [x] 4. R3 `/sampled-vouchers` 列表底稿可见性过滤
  - 文件：`backend/app/routers/voucher_links.py` `list_sampled_vouchers()`
  - 仅在 `working_paper_id` 参数为 None 时启用（未指定底稿 = 项目级概览）
  - 指定 `working_paper_id` 时不额外过滤（底稿自取）
  - AC：项目级列表排除不可见底稿记录；指定 wp 时不过滤；`wp_id=None` 始终可见

## 批次 2：投影 SAVEPOINT 加固（R4）

- [x] 5. `register_sampling_batch` 加 SAVEPOINT
  - 文件：`backend/app/services/sampling_registry_service.py`
  - try 内加 `async with db.begin_nested():`
  - except 改为 `except Exception as exc`，warning 包含 `type(exc).__name__` 和 `exc`
  - AC：投影 SQL 失败不污染主事务；主流程 commit 正常；warning 日志含异常类名

- [x] 6. `register_sampled_vouchers` 加 SAVEPOINT
  - 同上模式
  - AC：同上

- [x] 7. `undo_sampling_registration` 加 SAVEPOINT
  - 同上模式
  - AC：撤销投影失败不阻断审计师的撤销主操作

- [x] 8. `update_sampling_record_evaluation` 加 SAVEPOINT
  - 同上模式
  - AC：评价投影失败不阻断评价保存

## 批次 3：D2 合并口径对齐（R5）

- [x] 9. `mergeVoucherRows` 改用 `voucherNo + voucherDate` 联合去重
  - 文件：`audit-platform/frontend/src/components/workpaper/composables/useD2VoucherCheckEnhanced.ts`
  - 去重键从 `r.voucherNo` 改为 `` `${r.voucherNo}|${r.voucherDate || ''}` ``
  - 保留「已有行 check1~check5 不覆盖」语义
  - 重编号逻辑不变
  - AC：同号不同日 → 两行都保留；同号同日 → 只保留第一行

## 批次 4：存量数据治理（R6）

- [x] 10. 编写旧身份治理脚本
  - 文件：`backend/scripts/fix/fix_sampled_voucher_legacy_identity.py`
  - 查 `sampled_vouchers` 中三列有空值且未软删的行
  - 按 `(project_id, year, voucher_no)` 回查 active `tb_ledger`
  - 唯一匹配 → `auto_resolve`；多匹配 → `ambiguous`；零匹配 → `no_match`
  - `working_paper_id=NULL` → `legacy_orphan`（note 追加标记）
  - 支持 `--dry-run`（默认）/ `--apply` / `--project-id`
  - 输出 JSON 报告
  - AC：`--dry-run` 不改库；`--apply` 前要求确认；报告含 before/after 值

- [x] 11. 在共享库上执行 `--dry-run` 验证
  - 对照真实库 32 行 live 数据（30 引擎 + 2 手工）
  - 确认 auto_resolve / ambiguous / no_match / legacy_orphan 分类正确
  - AC：干跑报告与预期一致（30 行中无歧义的自动补全、有歧义的标出、1 行 orphan 标出）
  - `[ ]*` 真实库执行需用户放行
  - 完成（2026-11-03，由 `voucher-workflow-linkage-lineage-closure` 任务 1 执行，只读）：`tmp_voucher_closure/legacy_dry_run.json`
    32 行 = auto_resolve 31 / ambiguous 0 / no_match 0 / legacy_orphan 1，`applied=false`；引擎行按回填日志的分录 id 定位
    （`basis=filled_unit_ids`），登记科目同时由 1001 更正为分录实际科目 1002。`--apply` 仍待用户放行
  - `--apply`（2026-11-04 用户放行「按建议来，之后推送」，共享库 `audit_platform`）：执行前复跑干跑，与 11-03 报告逐行一致；
    32 行 `row_to_json` 备份与回退 SQL 在 `tmp_voucher_closure/backups/sampled_vouchers_legacy_20261104_161552*`；
    执行结果 31 行补全凭证字 / 主体（其中 30 行补日期、30 行引擎登记科目 1001 → 1002），1 行孤儿 note 加 `[legacy_orphan]`；
    逐行核对改动只落在这五列、与报告 after / account_fix 一致；复跑干跑只剩孤儿 1 行（`legacy_dry_run_after_apply.json`）

## 批次 5：守卫测试与变异（R7）

- [x] 12. 归属校验测试
  - 文件：`backend/tests/test_voucher_links_ownership.py`
  - 7 个用例覆盖 R1 正反两面（design §7.1）
  - AC：全绿；变异（删归属校验块）→ 对应用例打红

- [x] 13. 可见性过滤测试
  - 文件：`backend/tests/test_voucher_links_visibility.py`
  - 6 个用例覆盖 R2/R3（design §7.2）
  - AC：全绿；变异（删可见性过滤块）→ 对应用例打红

- [x] 14. D2 合并口径测试
  - 文件：`audit-platform/frontend/src/components/workpaper/composables/__tests__/mergeVoucherRows.spec.ts`
  - 3 个确定性用例 + 2 个 PBT 用例（design §7.4）
  - AC：全绿；`max_examples=5`

- [x] 15. 变异检测
  - 对 4 个靶点逐个做磁盘变异（design §7.3 变异表）
  - AC：每个变异至少让 1 个测试打红；变异后逐字节恢复
  - 完成（2026-11-04，并入 `voucher-workflow-linkage-lineage-closure` 任务 19）：4 个靶点（`prior_*`）全部打红、sha256 逐字节还原，
    报告 `tmp_voucher_closure/mutations/report.md`；R4 保存点原无用例，补 `test_sampling_projection_savepoint_pg.py`（真 PG 回滚事务注入除零 + 反向对照）

## 批次 6：收尾

- [ ] 16. 浏览器实测
  - 单笔挂凭传别的项目底稿 → 422（开发工具 Network）
  - `/voucher-links/query` 结果不含不可见底稿
  - D2 Excel 导入同号不同日的凭证 → 两行
  - `[ ]*` 需开发服务运行
  - 2026-11-04 在隔离临时库（`voucher-workflow-linkage-lineage-closure` design §13 / §15）实测：前两项真实 HTTP 通过 ——
    单笔挂凭传和平药房_2025 的底稿 → 422 `WP_NOT_IN_PROJECT`；凭证 0075 的链接 admin 看到 E1 / E1-7 / 无底稿三条，
    本项目只读成员 `e2e_reader` 只看到无底稿那条。第三项**无法验收**：D2 凭证检查「导入导出」调用的
    `POST /api/workpapers/{wp}/d2/vc-import-data`（以及 `vc-export-template` / `vc-export-data`）后端不存在，走查 s11 两次导入都是 404，
    `mergeVoucherRows` 目前没有可达的调用路径（其单测已改写为真正执行的 PBT）。留 `[ ]*`，待补端点后再验
  - 2026-11-04 用户定：三个端点另立 spec `d2-voucher-check-import-export-endpoints`（只写三件套），第三项随该 spec 的浏览器实测验收

- [x] 17. 提交与推送
  - 暂存本 spec 改动的全部文件
  - 暂存树自洽检查
  - 推送（`push_version.py`）
  - 完成（2026-11-04）：随 `voucher-workflow-linkage-lineage-closure` 任务 21 一并提交推送（同一批提交，验证记录见该任务）

## 勘误（2026-11-04，由 `voucher-workflow-linkage-lineage-closure` 收口时补记，原记录不改）

- 任务 14 标 `[x]` 时，2 个 PBT 用例用的是 fast-check 4 已删除的 `fc.char` / `fc.stringOf`，从未真正执行（文件级报错被当成全绿）；
  已改写为小值域 + 逐行模型（`mergeVoucherRows.spec.ts`），并在变异 `merge_rows_date` 下确认打红。
- 本 spec 剩余收尾（任务 11 / 15 / 16 / 17）并入 `voucher-workflow-linkage-lineage-closure`，随它一起提交推送。
