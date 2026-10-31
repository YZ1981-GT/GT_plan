# 实施计划：adjustment-hall-entry-review-closure

> 以 design.md 为准。标完成须有代码 + 测试证据；关键守卫做磁盘变异（备份放 `tmp_adjustment_hall/mutations/`，注入、确认红在预期处、逐字节还原核对 sha256）。临时产物放 `tmp_adjustment_hall/`。环境做不到的标 `[ ]*` 并写明原因。
>
> 验证口径：全部在「候选树」上跑 —— 临时 worktree = 最新远端 HEAD `6f4c5a54a` + 本 spec 改动（三方合并，0 冲突），与同提交的基线 worktree 逐节点比对。主工作树对 315 个文件是陈旧的（磁盘停在 `9791805c8`），不能当验证树，见 design §10.1。

- [x] 1. 录入规则与编号（需求 1.2、1.3，D3）
  - 新模块 `adjustment_entry_rules.py`；`create_entry` / `update_entry` 接入；`AdjustmentCreate.adjustment_no`；`_next_adjustment_no` 跳过已占用号
  - Verify: `test_adjustment_entry_rules.py` 16 passed；`test_adjustments.py` 32 passed；变异 M1（去掉同行双向拦截）被杀死

- [x] 2. 科目下拉兜底与参考余额（需求 1.1，D3）
  - `get_account_dropdown` 全量标准科目 + 已确认映射的报表项目 + `year` 时审定数；`AccountOption.balance`；路由加 `year` 参数
  - Verify: `test_account_dropdown_lists_all_standard_accounts_with_balance`（无映射的科目也在、按编码排序、有映射带报表项目、带年度有余额、按行次仍只返回已确认映射）；浏览器实测下拉显示余额与报表项目

- [x] 3. 提交复核 / 撤回提交 / 批量复核 / 复核人列表（需求 4.1~4.3、4.6，D1）
  - 状态机开关；`adjustment_review_service.py`；新路由 `adjustment_review.py` 并注册；`/review`、`/revoke-review` 加合并锁
  - Verify: `test_adjustment_review_flow.py` 9 passed（TestClient 真请求）；`test_adjustment_review_permission.py` 18 passed（审计员审批仍 403）

- [x] 4. 站内通知（需求 4.4、4.5，D2）
  - `adjustment_hall_notify.py`；类型常量与 `ALL_NOTIFICATION_TYPES`；提交 / 通过 / 驳回 / 撤回复核与受影响底稿负责人；保存点写入
  - Verify: 接收人用例（排除提交人、批量每人一条、指定非候选复核人 400、操作人即编制人不通知自己、底稿来源不通知底稿负责人）；`test_adjustment_notification_type_sync.py` 2 passed + `notificationTypes.adjustment.spec.ts` 9 passed；pg_only `test_adjustment_hall_notify_pg.py` 在候选树 1 passed、真库无残留；变异 M2 首轮存活（原用例全是编制人≠审批人）⇒ 补「操作人即编制人」用例后被杀死，M7（底稿来源也发影响通知）被杀死

- [x] 5. 导入服务与项目级导入端点（需求 2.1~2.6，D4）
  - `adjustment_import_service.py`；`_import_adjustments` 薄壳；`routers/adjustment_import.py`（preview / import）并注册；旧通用端点项目级鉴权与年度必填；富模板关注事项改写
  - Verify: `test_adjustment_import_service.py` 15 passed；`test_adjustment_ie_characterization.py` 54 passed、`test_adjustment_import_mode.py` 14 passed（既有特征测试按新分组规则更新）；变异 M3（无编号行不再按平衡切分）被杀死

- [x] 6. 底稿推送、列表富化与其余修复（需求 2.7、3、5.4 后端部分、6.3，D5、D6）
  - 推送 outcome 与通知修正；富化修 `StaffMember.name` 并加复核人 / 来源底稿编码 / 来源缺失；导出汇总全量 + 复核状态列；批量删除按分录组；删除协作回写与基线条目；related-workpapers、编辑锁、重分类端点鉴权与 inline-submit 改走服务
  - Verify: `test_adjustment_sync.py` 10、`test_adjustment_list_enrich.py` 3、`test_adjustment_export_summary_roundtrip.py` 19 passed；`test_wp_account_mapping_readers.py` 真 PG 21 passed；`test_lazy_import_resolvability.py` 候选与 HEAD 同样 2 条红，全部是批量建项会话未入库的模块（design §10.2），本 spec 删掉的基线条目无残留
  - 鉴权棘轮：前缀维「仅登录不校项目」HEAD 229 > 基线 227（红）→ 候选 222（绿）

- [x] 7. 前端 API、通知类型、底稿推送提示（需求 3.1、3.3、4.5，D7）
  - `auditPlatformApi.ts` 新函数；`notificationTypes.ts`；`useAdjustmentCentralSync.ts`
  - Verify: `useAdjustmentCentralSync.spec.ts` 26、`queryResultLinks.spec.ts` 23 passed；单区域 vue-tsc 我的文件 0 条

- [x] 8. 大厅页面重构（需求 1、2.5、4、5，D7）
  - 五个新组件（比设计多 `AdjustmentHallTable.vue`，见 design §10.3）+ `useAdjustmentHallActions.ts` + `Adjustments.vue` 改造（1977 → 867 行，白名单条目删除）+ 手册
  - Verify: 新组件与 composable 单测 6 个文件 68 passed（`adjustmentLineRules` 29、`useAdjustmentHallActions` 22、`AdjustmentEntryDialog` 6、`adjustmentQuickTemplates` 5、`AdjustmentReviewDialogs` 4、`AdjustmentImportDialog` 2）；读源码守卫 `audit-context-7-views` 22、`property-year-switching-invariant` 5、`rawEventRecovery` 4、`adjustmentEntryGroupWiring` 4 passed（后者在 HEAD 红、候选树转绿）；ESLint 0 error；行数门 exit 0；变异 M4 / M5 / M6 被杀死

- [x] 9. 验收（需求 7）
  - 后端 32 个相关测试文件：候选 8 failed + 22 errors、HEAD 9 failed + 22 errors，候选新增失败 0（两边都红的清单见 design §10.2）
  - 前端 45 个相关用例文件：候选 5 failed + 1 套件失败、HEAD 6 failed + 1 套件失败，候选新增失败 0，本 spec 的 spec 全绿
  - vue-tsc 单区域 20 个文件（40 GB 堆；8 GB 堆 OOM、「0 错」是假的）：候选与 HEAD 都是同 5 个他人文件 95 条，本 spec 文件 0 条
  - 磁盘变异 7 条全部被杀死且红在预期断言，阴性对照 2 条（只改注释）保持绿，逐字节还原核对一致
  - 【测试】项目 `430e17bd` 浏览器全流程通过（明细见 design §10.4），实测抓到 3 处问题已修
  - 清理：16 张表 2332 行（含二级子表 `adjustment_entries` 22 行）+ 项目 1 + 临时账号 / 人员各 1 + 通知 9 条，事后复核全 0；`logs` 199 行与哈希链 `audit_log_entries` 1 行按约定保留

- [x] 10. 收尾
  - 勾选与验收记录写回本文件；INDEX.md 登记；memory 精简登记；单一提交按约定推送（版本号 + 主要变动，见提交标签）
