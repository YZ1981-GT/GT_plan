# 任务：裁剪生成后续优化复盘的范围外问题收口

需求见 requirements.md，设计见 design.md。完成项必须有代码与通过证据；外部依赖如实保留未勾选。

- [x] 0. 现状确认与设计
  - [x] 0.1 追踪 H5 / H7 / M8 行业判定、两个 industry-check 端点、同类 AI / 渲染读者；共享库确认无行业条目、真实项目 render-config 只读实测（H5 industry_error、M8 project_info 行业恒空）
  - [x] 0.2 追踪 seed 调用链、启动任务写法、seed-all 死分支、过期测试；追踪前端组别读者与棘轮口径
  - [x] 0.3 建三件套、登记 INDEX

- [x] 1. 行业误用（R1）
  - [x] 1.1 H5 / H7 / M8 渲染去掉行业判定，返回 `accounts_found`；M8 `project_info` 去掉伪造字段；渲染单测（A1 / C / NULL 均返回完整数据）
  - [x] 1.2 删除两个 industry-check 端点与 service 函数；台账只删两条并重算 summary；原生 SQL 列基线、请求体鉴权基线同步
  - [x] 1.3 B1-3 / B1 / B1-4 渲染与 B1-4 / N2 / A17 AI 上下文不再把分类码当行业；I4 行业推荐删分类码
  - [x] 1.4 新增 `WpAccountAbsenceHint`；GtH5 / GtH7 / GtM8 删旧守卫挂提示；删 `useH5IndustryGuard` / `useH7IndustryGuard` / `isFinancialEntity` 与对应测试段，补组件与宿主测试
  - [x] 1.5 H5 编制手册 / 对话框 / 目录页适用说明改正；`wp_surfaced_m` M8 条目改正

- [x] 2. 生成弹窗与内置模板集（R2）
  - [x] 2.1 前端列模板集只 GET；单测断言不发 POST；性能夹具 `EXPECTED_API` 与无写请求断言
  - [x] 2.2 `builtin_template_sets` 模块（SAVEPOINT 防并发首插）+ 启动任务；`TemplateEngine` 委托；启动注册测试同步
  - [x] 2.3 seed 端点收紧 admin / partner；seed-all 的 template_sets 分支改调同一函数；过期「6 个内置集」测试改正
  - [x] 2.4 前序 spec design §5 补记勘误（追加，不覆盖原文）

- [x] 3. 质控组别解释（R3）
  - [x] 3.1 `categoryGroupOfCode` / `classificationOf` / `describeCategoryGroup` / `CATEGORY_CODES` + 后端对拍测试
  - [x] 3.2 WpPopupSigning、WpPopupChecklist、GtA17Bundle、GtA171AuditSummary、GtReviewChecklist、A1-11 签发表改读组别；A1 / B3 / NULL 挂载测试
  - [x] 3.3 后端 A17-1 project_context、A21 context 带 `project_classification`；A17 一致性校验按 resolve
  - [x] 3.4 前后端棘轮基线下调

- [x] 4. 验证与收尾
  - [x] 4.1 后端聚焦 + 相关回归与 HEAD 失败集合对照
  - [x] 4.2 前端聚焦 vitest、scoped vue-tsc、ESLint
  - [x] 4.3 磁盘变异逐条红在预期断言，恢复后 SHA-256 一致
  - [x] 4.4 【测试】项目浏览器实测（H5 / H7 / M8、A1-11 / A1-12 / A17、生成弹窗零写请求），测试项目软删
  - [x] 4.5 验收记录、INDEX、memory；清理临时文件；诚实登记未提交 / 未推送

## 验收记录

### 2026-10-30（5/5 完成，未提交 / 未推送）

- **R1 / R2 / R3**：三组生产改动与同类 grep 收口均已落盘。浏览器验收另抓到 `accounts_found` 把语义解析器裸 fallback 码当成 active TB 实际行：新增 `has_resolved_tb_rows`，H5 / H7 / M8 改按实际行判定（空查询 `false`、查询失败 `null`、零余额行仍为 `true`），M8 前缀查询收紧为等值或点号子科目；全仓生产写入方恰为这三处，已一起修复。
- **后端**：最终永久聚焦组（行业 / 语义解析 / 内置模板集 / 分类读者 / 分类解释）**176 passed**；其中 `test_industry_misuse_closure.py` + `four_table/test_semantic_account_resolver.py` **102 passed**。HEAD 对照工作树为 `C:\Users\Administrator\trfc_head_wt`（基线 `8107371f0`），工作树其余红项均可在 HEAD 复现或来自其他会话未提交文件。
- **前端**：最终永久聚焦组 **8 files / 97 passed**，其中新增 `classificationGroupHosts.spec.ts` **16 passed**。较宽选集 **130 files / 1459 passed**，4 个失败均在本轮未改文件（`authTokenSingleSource`、`rawRequestAuth`、`hostSheetDispatchChain` ×2）。scoped vue-tsc 的 canary 可打出 TS2322；删除 canary 后，本轮新增测试无类型错误，剩余错误均在未改行 / 其他会话依赖。ESLint 唯一错误为既存 `GtH7BiologicalAssets.vue` 的 `openReviewDialog` `no-console`。
- **变异**：后端首批 **26/26** 正向变异按预期红、3 个阴性对照绿；浏览器补强批 **7/7** 正向变异红、1 个阴性对照绿；每次恢复 SHA-256 一致。前端 **18/18** 正向变异均在点名用例文件红、3 个阴性对照绿，内存 load hook 验证主工作区源文件 SHA 不变。
- **浏览器 / 真库**：在【测试】项目 `e82e193f-a288-4d3f-a440-2ee4fd49991b` 生成 H5 / H7 / M8 / A1 / A1-11 / A1-12 / A17 / A17-1 共 8 份底稿。打开生成弹窗只新增 `GET /api/template-sets` 与 `GET .../procedure-scope/generation-plan`，本应用零非 GET 请求；H5 / H7 / M8 均显示缺科目提示且正文完整；A1-11 的 A1 分类显示 A 类、0/4 与四个必签角色；A1-12 实际浏览器组件显示 A 类（A1）及 B 类（B3）；A17 显示 B 类（B3）软提示，A17-1 在 A1 时显示四角色。项目已通过平台 `DELETE /api/projects/{id}` 软删，PG 复核 `is_deleted=true`、`deleted_at` 非空、8 个 `wp_index`。
- **状态**：按用户约束，本轮没有新建分支、没有 `git stash`、没有 commit、没有 push；真实项目未写。浏览器控制台唯一业务域错误为 A17 既有 `GET /api/projects/{id}/kam-references` 404，页面已捕获且不影响本轮组别验收，已登记到 design §7.3。前序 spec 的 5.5 / 7.4 真实项目只读走查仍需用户点名项目并批准 `provision_readonly_uat_user.py --apply`，不计入本 spec 完成度。
