# 需求文档：序时账增量追加改为真追加（ledger-incremental-append-true-merge）

## 概述

问题来源：`.agents/tasks/voucher-module-assessment-2026-10-27.md` 第五节 Y3。用户 2026-10-27 拍板：增量追加直接修成真追加。

预审导入 1~11 月、年审追加 12 月是常见做法。现在「数据管理 → 增量追加」走普通导入：新建 staged 数据集只含上传文件的月份，激活后旧版本整体被替换，追加 12 月后 1~11 月不可见；提示语却说「系统将自动检测并只追加新月份」。

目标：追加导入后，新版本 = 上一版本中未被覆盖的月份 + 本次文件的月份；旧版本不被修改，可回滚；用户导入后能看到与上一版本相比哪些凭证变了。

关联：凭证差异报告用 `voucher-identity-writeback-and-audit-phase` 阶段 A 的凭证键（`backend/app/services/voucher_identity.py`）；本 spec 若先实施，按该 spec design §2 建立同一文件。

铁律：

1. 追加不修改、不删除上一版本的任何行；失败时上一版本照常可用。
2. 两条导入链（旧智能导入 `smart_import_streaming`、v2 管线 `execute_pipeline`）用同一个合并函数，不各写一套。
3. 凡带 `dataset_id` 的导入产物表都要有归类（按月合并 / 整表沿用 / 非导入产物），新增表未归类即守卫打红。
4. 真库 PG 端到端测试与【测试】项目浏览器实测验收。

## 现状事实

| 编号 | 事实（2026-10-27 现读） | 位置 |
|---|---|---|
| F1 | 每次导入 `create_staged` 新建数据集，激活时旧 active 整体 superseded；四表可见性只认 active 数据集 | `dataset_service.py`、`dataset_query.get_active_filter` |
| F2 | 两条导入链都没有继承旧版本月份的逻辑；`ledger_import_v2.submit` 收到 `incremental` 但不传给 `ImportOrchestrator.submit` | `ledger_import/pipeline.py`、`smart_import_engine.py`、`routers/ledger_import_v2.py` |
| F3 | `apply_incremental(overwrite)` 在导入前删 active 数据集的重叠月份行；导入失败时这些月份已经没了 | `ledger_data_service.py` |
| F4 | 序时账页「增量追加」打开普通导入弹窗，走 `/ledger/smart-import`，不带任何追加参数 | `LedgerPenetration.vue` `onIncrementalUpload` |
| F5 | 带 `dataset_id` 的表：`tb_balance`、`tb_aux_balance`、`tb_ledger`、`tb_aux_ledger`、`account_chart`（客户科目表按 active 数据集读取）、`direction_override`，另有 `activation_records`、`sampling_records`、`workpaper_row_name_mapping_target`、`_sign_migration_backup` | information_schema |
| F6 | 现有测试只测月份差集纯函数 `compute_incremental_diff` | `tests/ledger_import/test_incremental_apply.py` |
| F7 | 26 个 superseded 版本里 16 个已清空行，旧版本行在激活后不长期保留 | `ledger_datasets` / `tb_ledger` |

## 需求 1：真追加的合并语义

1. 追加导入新建 staged 数据集，写入本次文件数据后、激活前，从「提交时的 active 数据集」（基准版本）复制本次文件未覆盖的月份。
2. 按月合并的表（序时账、辅助明细账）：月份按凭证日期取月。策略「覆盖」：文件有的月份用文件数据，其余月份复制基准版本；策略「跳过」：基准版本已有的月份保留基准数据（删去 staged 里这些月份的行），文件里新增的月份用文件数据。
3. 整表沿用的表（科目余额表、辅助余额表、客户科目表、方向覆盖）：本次文件含该表则用文件的；不含则复制基准版本，并记录「沿用上一版本」。
4. 复制的行生成新行 id，保留原有业务字段与 `raw_extra`；记一条来源为「追加继承」的导入批次，供溯源。
5. 激活时基准版本若已不是 active（期间有别的导入激活），合并作废并报错「基准版本已变化，请重新追加」，不激活。
6. 新版本 `source_summary` 记录：导入方式 = 追加、策略、基准版本、文件月份、继承月份、各表沿用情况。

## 需求 2：两条导入链与入口

1. `smart_import_streaming` 与 `execute_pipeline` 在激活前调用同一合并函数；追加参数经导入作业 `options` 传递。
2. 序时账页「增量追加」与账套导入页 / 导入弹窗都能带上追加参数提交；提交时记下基准版本。
3. 删除导入前删行的做法：`/ledger-data/incremental/apply` 不再删除数据（返回 410 与中文说明），v2 提交不再调用 `apply_incremental`；数据管理弹窗去掉「执行清理」按钮，「检测差异」只做预览。
4. 提示语如实：追加前显示「已有月份 / 文件月份（预估）/ 将继承的月份 / 将被覆盖或跳过的月份」；导入完成显示实际合并结果。

## 需求 3：余额表与序时账一致性提示

1. 余额表沿用上一版本而序时账新增了月份时，导入完成与数据管理页显示「余额表未随本次追加更新，试算表仍为上一版本口径」，并在激活前要求勾选确认（与现有强制继续同一机制，留痕）。
2. 现有导入校验（序时账发生额与余额表核对等）对合并后的完整数据集运行。

## 需求 4：与上一版本的凭证差异报告

1. 每次导入（追加或整年重导）激活前，若存在上一 active 版本，按凭证键比对两版本：新增凭证、删除凭证、分录有变化的凭证，按月给出张数与金额，各类列至多 20 个样例。
2. 差异报告写入新版本 `source_summary`，导入完成弹窗与数据管理页可查看；生成失败不阻断导入，界面写明「差异报告未生成」及原因。
3. 和平药房规模（序时账 114.7 万行、辅助明细账约 273 万行）下合并与差异报告的耗时写入验收记录。

## 需求 5：回滚与可见性

1. 追加后的版本可回滚到基准版本，回滚后数据与追加前逐行一致（行数与金额合计）。
2. 激活记录 `activation_records` 的前后行数照常记录，追加不造成行数「静默减少」：每张按月合并的表，新版本行数必须等于「基准版本行数 − 被覆盖或丢弃的基准月份行数 + 保留的文件行数」，不符即阻断激活。

## 需求 6：验收

1. 真库 PG 端到端测试（回滚事务或【测试】项目内）：导入 1~11 月 → 追加 12 月（覆盖 / 跳过各一）→ 12 个月全部可见、余额表沿用提示、差异报告正确 → 回滚到 1~11 月。
2. 守卫：枚举全部带 `dataset_id` 的表，每张都必须在归类清单里；清单有失效条目也打红。
3. 每条守卫有磁盘变异证明。
4. 【测试】项目浏览器实测序时账页「增量追加」全流程，清理走平台路径并对账。
