# 任务清单：公式治理全覆盖收口

> spec：`formula-governance-coverage-closure` · requirements R1~R7 · design §1~§11
> 实施顺序：R1 → R7a → R2 → R3 → R4 → R6 → R5 → 交付。每完成一组立即提交 WIP（多会话并发，未提交改动有被覆盖风险）。

## 1. 越权修复（R1）

- [x] 1.1 `formula_debug.debug_formula` 首句校验请求体项目 readonly；非成员 403 且不取数（R1.1）
- [x] 1.2 `wp_user_formulas` 列表 / 保存 / 恢复预设改用 `authorize_wp_read` / `authorize_wp_edit`（R1.2）—— 勘误：生产本已挂 router 级可见性门，这是第二道（design §2.1）
- [x] 1.3 `validate_formula` 反查底稿项目 + 请求体项目一致性 + 预览用反查项目（R1.3）
- [x] 1.4 `import_data`：带项目校验 readonly；`persist` 需写预设角色；管理员写数据库预设、其余提交候选；切断在线端点对 seed 文件的写入（`upsert_seed_presets` 保留给离线生成脚本）（R1.4 / R1.5）
- [x] 1.5 `reports.consistency_check` 改 `require_project_access("readonly")`；0 条可执行时 `no_result`；前端审核对话框空态；配置公式改真实严格求值（`report_audit_checks.py`）；前端映射透传汇总计数与分类（R1.6）
- [x] 1.6 端点级测试：`tests/formula_settings/test_formula_endpoint_authz.py`（权限世界真实判定链，业务层计数桩：被拦请求 0 次业务调用）+ `test_draft_refresh_endpoint.py` 门禁调用断言；一次性变异（各端点模块里把判定换成放行）4/4 被测出（R1.1~R1.6）
- [x] 1.7 鉴权守卫第三维 `tests/test_project_endpoint_authz_body_carried.py`：额外项目级标识证明链 + 绑定检查、已修钉子（本维 6 个 + 路径维 2 个）、合成样本与真实源码 AST 变异双向；冻结仅登录 93 / 无鉴权 5 / 自鉴权 1。共享基线第一维现算 200（常量 207，未改共享文件，见 design §2.1）（R1.7）
- [x] 1.8 第三维抓到的公式链路端点：一键刷新 / 回滚 / 刷新范围 / 新增自定义预设 / 批量刷新取数 / 附注公式开关补项目级判定；前端一键刷新入口改「合伙人 + 本项目编辑级成员」；范围外发现登记 design §2.2（R1.7 / R1.8）

## 2. 表间审核严格取数（R7a）

- [x] 2.1 新模块 `formula_ref_preload.py`：PREV / AUX 预载与严格缺数报错；AUX 走 `get_active_filter(strict=True)`，读库包保存点；表间审核 `_evaluate` 先按值代入再求值（`enable_prev/aux=False`，不经 report_engine 预载分支）；报表「审核」的配置公式经同一入口自动受益。`report_engine` 改调并删除重复分支 —— 该文件正被另一会话修改，留待其提交后收口（design §3 调整）（R7.1）
- [x] 2.2 更新 `test_user_rules_run…` 断言（AUX 已进支持矩阵，改断言具体原因）；`test_formula_ref_preload.py` 10 例（AUX 缺数 + 另一侧 0、PREV 无上年、前缀聚合与上年缺科目为 0、4 参按名称 / 编码且只取当前数据集、3 参类型合计、三类报因、写法识别不了、`TB_AUX` 不被误认、非严格置 0、上下文缺失）+ `test_report_audit_checks.py`（勾稽 / 合理性真实求值、本项目适配生效）；一次性变异（去掉严格报因 / 回到旧口径）3/3 打红且红在「判成通过」（R7.1）

## 3. 推送规则纳入治理内核（R2）

- [x] 3.1 `definitions` 加 push 域；`push_settings.py`：`PushStore`、`validate_push_definition`、`effective_push_rules`（R2.1~R2.3 / R2.6）—— 补第五类拒绝「推送取数给不出数」`push_context_errors`（design §4.5）；`_structure` 收而不存、读出按清单补
- [x] 3.2 接线：`get_store` / `validate_definition` / `display_formula` / `rollback` / `dependencies` / `WIRED_DOMAINS` / 审计模块标签（R2.1 / R2.8）；公式目录随 `DOMAINS` 纳入 push 域
- [x] 3.3 引擎读有效规则 + 失效进提示（按规则底稿编码过滤）+ 触发来源 `FORMULA_CONFIG_CHANGED`（选规则按手动口径，记录保留原值）（R2.4 / R2.5）
- [x] 3.4 传播 handler `propagate_push`：按清单反查底稿编码；无规则 / 无年度 / 合并 / 归档跳过；业务不可推记 `not_pushable`（R2.7）
- [x] 3.5 规则列表接口：本项目有效规则（含停用 / 失效）+ 层级、可用操作、本项目版本号、清单原式、失效原因（R2.8）
- [x] 3.6 后端测试 `tests/formula_settings/test_push_settings.py` 13 例（四类拒绝 + 取数上下文、清单内 5 条恒推 0 冻结、叠加 / 失效跳过、写入各层都校验、引擎改写生效 / 停用不推 / 失效不推不回退、新触发来源、传播重推与五类跳过）+ 端点 2 例（层级与操作；旧「30 条」写死改现算）+ 端点鉴权 AST 守卫豁免全局静态端点并反向断言；一次性变异 8/8 打红（去取数校验 / 失效回退预设 / 引擎读静态清单 / 不跳过合并 / 结构落库 / 系统值可停用 / 新触发按原值选规则 / 列表只列 active）。干净 worktree 对比：push + formula_settings + formula_management 全套相对 HEAD 新增失败 0（`test_stats_aggregation` 因目录纳入 push 已改现算）、修好 2 例，其余 37 例 HEAD 同红（R2.2~R2.7）
- [x] 3.7 前端：`formulaPushView.ruleActions` / `ruleStatusText` / `layerTagType` + 触发来源「公式规则变更」；`definitionText` 停用显示与中文算式兜底；推送面板层级列与「本项目适配」列（改写公式 / 本项目停用 / 启用 / 恢复上游）；公式历史模块标签；反向校验面板错误显示；单测 `formulaPushRuleActions.spec.ts` 12 例 + 既有面板 14 例 + 全局设置相关 58 例全绿；单区域 vue-tsc 本次改动 0 错（探针变异 TS2322 证明在检查）（R2.8）

## 4. 校对规则统一目录（R3）

- [ ] 4.1 `formula_check_catalog.py` 登记表 + 加载器；`GET /api/formula-catalog/check-rules`（R3.1 / R3.2）
- [ ] 4.2 登记守卫（规则文件全登记或带理由排除、无失效条目、各来源可加载）（R3.4）
- [ ] 4.3 前端 `FormulaCheckCatalog.vue` + 全局设置页「校对规则目录」页签 + 表间审核面板入口 + 新增规则「从预置选用」；单测（R3.3）

## 5. 零挂载组件处置（R4）

- [ ] 5.1 问题清单 / 提醒面板接入表间审核面板（复用同一次审核响应）（R4.1 / R4.2）
- [ ] 5.2 导入导出下拉接入工具栏；修导入公式包 `POST → PUT` 与请求体；导入按角色门控（R4.1 / R4.2 / R1.8）
- [ ] 5.3 行名对齐弹窗改用行内标签组件，删除重复映射（R4.1）
- [ ] 5.4 删除 `GtDraftStateBadge`（无数据源，登记另立 spec）（R4.1）
- [ ] 5.5 组件挂载守卫（R4.3）

## 6. 底稿可编辑公式补齐函数（R6）

- [ ] 6.1 预载层 `_load_aux` / `_load_report_rows` / `ctx.missing`（R6.5）
- [ ] 6.2 求值器 REPORT 期间代入 + preload→L1 + 缺口报错（R6.1~R6.3）
- [ ] 6.3 函数矩阵 + golden + 前端矩阵同步，对拍测试（R6.4）
- [ ] 6.4 测试：7 个函数各一例 + 各类缺口报错 + ADJ 底稿口径（R6.1~R6.3）

## 7. 真库全链路走查（R5）

- [ ] 7.1 选定 / 准备【测试】项目（需审计年度与已接入推送的底稿则现建）（R5.3）
- [ ] 7.2 走查 design §8 六步，接口与浏览器双证（R5.1 / R5.2）
- [ ] 7.3 清理对账，保留项登记（R5.3）

## 8. 回归与交付（R7）

- [ ] 8.1 全量回归：`formula_settings` / `formula_push` / 鉴权基线 / 矩阵对拍 / 前端 formula 目录；预存失败在干净检出上复现并登记（R7.2）
- [ ] 8.2 干净 worktree 验证要提交的树；提交、推送特性分支、建 PR（合并交用户拍板）（R7.3）
- [ ] 8.3 INDEX.md 登记 + memory 更新（R7.3）
