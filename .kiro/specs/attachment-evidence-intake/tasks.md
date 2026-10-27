# 实施计划：证据采集单一入口（attachment-evidence-intake）

> 每个任务是一个可独立测试的交付单元，引用 `需求 X.Y` / `ADR-AEI-NN` / 变异 `#N`（design §6），不复述。
> 通用纪律：后端测试 `..\.venv\Scripts\python.exe -m pytest <文件> -q -p no:playwright`（cwd = `backend`）；前端 `npx vitest run <文件>`（cwd = `audit-platform/frontend`）；一次性脚本、变异备份、截图只放仓库根 `tmp_attachment_spec_b/`；磁盘变异单独一条命令跑、逐字节恢复后 sha256 核对；不碰 design §1 列出的范围；提交前核对暂存区只含本 spec 文件。

- [x] 1. 入口内核（需求 1.2、1.5、1.6，ADR-AEI-01/03/06）
  - 新建 `services/workpaper_evidence_intake.py`（证据类型登记表与缺省规则、上传体量读取、底稿装载、`create_evidence`）；`attachment_service.create_attachment` / `upload_attachment_file` 加 `version_chain`
  - 测试 `test_evidence_types.py`：登记表是 `ATTACHMENT_TYPES` 子集；单一声明缺省、多声明与无声明缺省 `evidence`、端点前缀规则；同名两次入口上传均为版本 1 且无替换信号
  - 记录：29 例绿；变异 #8、#10 红在预期用例（design §8.4）

- [x] 2. 入口上传端点与证据链接接口（需求 1.1、1.3、1.4、3.1–3.6）
  - `routers/wp_evidence.py`、`services/wp_evidence_service.py`；迁移 V213 + R213（实施时现取号）；模型 `cell_ref` 长度
  - 测试 `test_evidence_upload_endpoint.py`、`test_evidence_links_api.py`：整稿 / 行级各自只写对应关联；413 / 422 / 404 / 423；编制人可写、复核人 404；跨项目附件、伪造 `created_by`、跨底稿删除；迁移可重放
  - 记录：SQLite 17 例 + PG 角色矩阵 5 例绿（统一门只在 PG 用例里真跑）；变异 #3、#4、#5 红；迁移落库见任务 11

- [x] 3. OCR 端点先建附件（需求 2，ADR-AEI-05）
  - `intake_ocr_upload`；25 个路由文件改造；删 `provision_wp_linked_attachment` 与旁路目录函数；`is_attachment_linked_to_wp` 认证据链接
  - 测试 `test_ocr_intake.py`：26 个路由参数化（不带 id 建附件、写回、无旁路文件、413 / 423）；他项目 / 未关联 id ⇒ 404 且无识别文本；重识别读已存原件；`d4/contract-ocr` 用在非 D4 底稿时按缺省类型；改写 Spec A `test_side_storage_wp_id.py` 与 E1 / D4 / F2 既有用例
  - 记录：参数化 + 静态守卫全绿；旁路目录守卫排除文档字符串并配双向自检；变异 #1、#2 红

- [x] 4. 统一视图、可见性与旧写端点（需求 3.7、4，ADR-AEI-02/07）
  - 新建 `services/attachment_wp_view.py`（`get_wp_attachments` 委托）；`evidence_link` 来源、`linked_wp_count`；解除整稿关联连带删链接；附件列表 `linked_wp_count`；`wp_visibility/entry_integration._linked_wp_ids`；删 `POST /api/process-record/link-attachment` 与台账条目
  - 测试 `test_wp_attachment_view.py`、`test_visibility_evidence_links.py`；`attachment_service.py` 行数回到白名单以下并下调登记值
  - 记录：`linked_wp_count` 口径与侧栏悬停端点收紧见 design §8.2-1/2；`attachment_service.py` 1309 行（白名单 1391 → 1309）；老用例建表补 `evidence_links`（design §8.3）；变异 #6、#7、#9 红

- [x] 5. 前端入口与行级组件（需求 5.1，ADR-AEI-08）
  - 新建 `workpaperEvidence.ts`、`useWpEvidenceLinks.ts`；改写 `ItemAttachment.vue`
  - vitest：后端真实返回形状下上传后可见、移除走删除链接、多实例一次请求、只读隐藏按钮；`workpaperEvidence` 选项与后端登记表一致
  - 记录：3 个 spec 23 例绿（并发判据挂起响应后再数）；变异 #11、#12 红

- [x] 6. 前端面板（需求 4.3、4.5、5.2、5.3）
  - 底稿附件抽屉、来源标签、侧栏附件页签、侧栏证据页签、附件管理页统计
  - vitest：抽屉缺省预选第一类未满足声明、「上传此类证据」带类型、行级证据显示位置；侧栏附件页签读统一视图
  - 记录：抽屉 16 例、侧栏附件页签 3 例、证据页签 4 例绿

- [x] 7. 底稿内上传点改走入口（需求 5.4、5.5、5.6）
  - design §4 表中各文件；删 `linkAttachment` 包装与路径；新守卫 `LegacyUploadCallersGuard.spec.ts`
  - 受影响既有用例按新调用改写；单区域 vue-tsc 只查改动文件并配一条类型错误变异
  - 记录：21 处上传点迁移（C 类把附件 id 交给识别）；`uploadAndAssociateToWorkpaper` 无调用方删除；vue-tsc 36 个文件本清单 0 新错（10 条均为既有：抽屉两个 script 块重复导入图标 8 条、C22 `flushPending` 索引 2 条），探针文件 3 条 TS2322 证明在查；变异 #14 红

- [x] 8. Spec A 遗留（需求 6）
  - 扩展名白名单与 `ACCEPT_TYPES` 加音视频；原生加载守卫按 `<template>` 块取模板 + 自检样例，新扫出的逐条处理并登记
  - 记录：新扫出 1 处 `D2VcCardView.vue` 缩略图 `att.thumbnailUrl`（字段无写入方，登记 dormant）；`GtB212Evaluation` 步骤附件改已鉴权下载；变异 #13 红

- [x] 9. 变异证明（需求 7.3）
  - design §6 的 14 条逐条跑，记录红在哪条断言、恢复后 sha256
  - 记录：14 条全红在预期用例，逐字节恢复 sha256 一致（独立变异 worktree，不碰共享开发服务；design §8.4）

- [x] 10. 全仓守卫与棘轮
  - 鉴权三维守卫、行数门、lazy import、函数全局名棘轮、底稿关联波次与可见性隔离既有用例、`scripts/fix/resync_data_line_anchors.py --check`；扩大回归在纯 HEAD 上逐条复现失败
  - 记录：守卫两边失败集合相同、基线常量不变、吞异常 69 = 69；扩大回归本地线 494 个文件只多 8 条（7 条 SQLite 缺表已修、1 条 PBT 既有缺陷），远端线 500 个文件只多 1 条（单独重跑两边全过，顺序相关）；前端 vitest 92 / 92 与抽屉 + 入口 38 / 38（两条线）；vue-tsc 剩 2 条既有（design §8.6）

- [x] 11. 共享库迁移与走查（需求 7.4）
  - `MigrationRunner(...).run_pending()` 应用 V213；私有实例 + 【测试】项目：OCR 建附件、行级上传与移除、抽屉选类型后声明满足、侧栏两个页签；数据走平台路径清理并逐表对账
  - 记录：V213 已落共享库（核对列长、三个索引、两条外键）；本地线 HEAD 打不开带程序表的底稿（引用只在远端线的模块），走查改在远端线候选树（= 要推送的树）的私有前后端上做；五项全部通过，另发现并修了附件管理「关联到底稿」恒 404 与抽屉空态 / 图标可读名（design §8.2-7/8，修后浏览器复验）；清理后 5 张表对账为 0（design §8.5，截图 `evidence/` 6 张）

- [x] 12. 收尾
  - 评估报告勘误节追加；`.kiro/specs/INDEX.md` 登记；按工作区规则提交并推送（fetch 先行、只暂存本 spec 文件，两条分支线同 Spec A 做法）
  - 记录：评估报告 §九；INDEX 登记两行、记忆两行；本地线用私有索引从 HEAD 起只放本 spec 文件与改动块（白名单 / INDEX / 记忆按 HEAD 版加本 spec 行）提交；远端线在候选树上提交，`push_version.py` 打版本号并附主要变动后推送，`git ls-remote` 核对
