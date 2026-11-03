# 任务：归档与 A 类证据（attachment-archive-and-a-class-evidence）

勾选规则：代码 + 测试通过 + 证据（命令 / 结果摘要）齐全才勾；外部依赖未实测如实标注。
后端用例在 `backend/tests/attachment_archive_evidence/`（下称 `AE/`），命令 `python -m pytest -p no:playwright <文件>`（cwd `backend`）。

- [x] 1. 签字件证据类型与精确匹配声明键（需求 7）
  - `signed`「签字件」加入 `ATTACHMENT_TYPES` / `EVIDENCE_TYPES` / 前端 `EVIDENCE_TYPE_OPTIONS`，三处守卫互钉
  - `resolve_requirements_for_wp_code` 支持 `=编码` 精确键且优先；`_comment` 补写法；声明 10 条（design §9）
  - 证据：`AE/test_signed_and_exact_keys.py` 全过；变异 E8 / E9 红

- [x] 2. 证据声明统一评估与 QC-17（需求 6）
  - `attachment_wp_view._collect_items` 抽出；`evaluate_wp_evidence_requirements(db, wp_id)`（含函证拆分）
  - `qc_rule_attachment_sufficiency.py` 承接 QC-17；`qc_engine.py` 改导入（974 → 959，白名单按真实行数改小）
  - 证据：`AE/test_qc17_evidence.py`、`test_wopi_working_paper_qc_review.py` 全过（后者的整引擎用例改为 B1-1 无声明不出 QC-17，文件在行数门上、净减 1 行）；变异 E7 / E23 / E46 红

- [x] 3. 归档清单 `archive_inventory`（需求 1.1、1.2、5.1）
  - 底稿文件六种判定、现行附件（版本取代、本地 / Paperless）、交付件、孤儿文件；底稿名去首尾空白（走查补）
  - 证据：`AE/test_archive_inventory_and_package.py` 7 例全过；变异 E20 / E21 / E22 / E44 红

- [x] 4. 归档包 `archive_package_builder`（需求 1）
  - zip 布局、数据快照、章节生成器（抛错失败 / 空跳过）、manifest、`.part` 改名、失败不留文件
  - 证据：同上文件；变异 E1 / E2 / E19 红；走查下载的包 11 项、manifest 逐项 sha256 复算一致

- [x] 5. 编排改造（需求 2）
  - 步骤 `gate → package → push_to_cloud → lock → purge_local`；进度换新字典；锁定；`output_url` / `manifest_hash` / 完整性记录
  - `CloudStorageService.upload_archive_package`（失败抛、缺依赖库报错）；删 `_persist_integrity_hashes` / `_set_project_retention`
  - 证据：`test_archive_orchestrator.py` 11 例、`AE/test_cloud_upload_archive_package.py` 全过；变异 E3 / E4 / E26~E29 红

- [x] 6. 归档包下载端点（需求 1.4）
  - `GET /api/projects/{pid}/archive/jobs/{job_id}/package`：readonly、跨项目 404、未成功 404、文件缺 / 指纹不符 409
  - 证据：`AE/test_archive_router.py`（TestClient 真发请求）全过；变异 E14~E16 红；走查下载 200

- [x] 7. 旧端点下线与归档路由鉴权（需求 3、2.5）
  - 删 3 个旧路由函数、`WpStorageService.archive_project`、`ProjectArchiveService`，grep 0 调用方
  - 证据：`test_archive_deprecated.py` 全过；变异 E5 红

- [x] 8. 二次密码确认后端（需求 4.1）
  - 证据：`AE/test_password_confirm_status.py`（403 / 423 / 令牌一次性）全过；变异 E6 红；走查输错 403 不登出

- [x] 9. 归档完整性检查 5 类（需求 5）
  - `archive_completeness_evidence.py`；Literal 与阻断集；`missing_files` 查询失败不放行；类别中文名后端一张表、与前端互钉（走查补）
  - 证据：`AE/test_completeness_evidence.py`、`test_archive_completeness_report.py` 全过；变异 E17 / E18 / E45 红；走查 10 类中文

- [x] 10. 回收站彻底删除删物理文件（需求 9）
  - 证据：`AE/test_purge_physical_files.py` 全过；变异 E12 / E13 红；走查回执 `file_cleanup.deleted=1`、磁盘文件消失

- [x] 11. A30 电子底稿归档检查表（需求 8）
  - `checklist_index_parser.py`（真模板解析）、`checklist_template_loader.py` 三入口改调；建议端点
  - 证据：`AE/test_a30_index_checklist.py` 全过（真模板 203 项 / 15 节 / 必备 51）；变异 E10 / E11 / E24 / E25 红

- [x] 12. 前端：二次确认与签字（需求 4.2~4.4）
  - `utils/passwordConfirm.ts`；对话框 `_silent` 与 403 分支；`signDocument(params, token)`，`PartnerSignDecision` / `PartnerDashboard` 改造（`SignatureBlock` 未改，design §14-1）
  - 证据：`passwordConfirm.spec.ts`、`PasswordConfirmDialog.spec.ts`、`confirmationTokenCallers.spec.ts` 全过；变异 V1 / V2 / V8 / V9 红，V3 等价

- [x] 13. 前端：归档向导与 A30 建议（需求 4.3、4.4、5.3、8.2、8.3）
  - 向导令牌、`resp.id`、下载、中文类别 / 失败步骤（共用标签表）、超时；`NativeLoadBearerGuard` 休眠登记删除
  - `useArchiveChecklistSuggest` + `GtChecklistTable` 按钮（只填空项、冲突提示、只读隐藏）
  - 证据：`ArchiveWizardConfirm.spec.ts`、`useArchiveChecklistSuggest.spec.ts`、`GtChecklistTableA30.spec.ts` 全过；单区域 vue-tsc 0 新增（注入 TS2322 可报出）；变异 V4~V7 / V10 / V11 红

- [x] 14. 变异与回归
  - 证据：65 条磁盘变异（design §13 结果）；相关后端用例在本地线提交树与基线 worktree 复跑对比、远端线候选树复跑 Spec E 用例；前端相关 21 个 spec 在候选树 116 过 / 4 红，4 红在基线 worktree 同红（`large_component_guard` GtAuditSheet 行数、`WorkpaperListShell` 角色 Tab）

- [x] 15. 浏览器走查（design §13 走查项）
  - 证据：design §13 结果段（远端线候选树 + 独立无头浏览器，【测试】归档与A类走查_2025）；清理对账 design §14-9

- [x] 16. 走查补修（需求 2.6、2.7、8.4，ADR-AE-13 / 14）
  - 门禁同口径（`archive_gate.py`）；解除归档逆操作（`restore_after_unarchive` + `ArchivedBanner` 横幅内完成）；核对表结论白名单、适用性落库与只读不弹、批量标记选项；测试隔离（截住 outbox 写入）
  - 证据：`AE/test_archive_gate.py`、`AE/test_unarchive_restores_lock.py`、`test_unarchive.py`、`useChecklistApplicability.spec.ts`、`ArchivedBanner.spec.ts` 全过；变异 E30~E43 / V12~V19 红；走查门禁失败页、解除后底稿恢复「编制中」

- [x] 17. 文档与提交
  - design §14 实施差异、INDEX、memory、评估文档第十一节；行数门 / gitleaks / U+FFFD / 自洽检查；本地线与远端线各提交一份，远端推送带版本标签
