# 任务清单：公式治理全覆盖收口

> spec：`formula-governance-coverage-closure` · requirements R1~R7 · design §1~§11
> 实施顺序：R1 → R7a → R2 → R3 → R4 → R6 → R5 → 交付。每完成一组立即提交 WIP（多会话并发，未提交改动有被覆盖风险）。

## 1. 越权修复（R1）

- [ ] 1.1 `formula_debug.debug_formula` 首句校验请求体项目 readonly；非成员 403 且不取数（R1.1）
- [ ] 1.2 `wp_user_formulas` 列表 / 保存 / 恢复预设改用 `authorize_wp_read` / `authorize_wp_edit`（R1.2）
- [ ] 1.3 `validate_formula` 反查底稿项目 + 请求体项目一致性 + 预览用反查项目（R1.3）
- [ ] 1.4 `import_data`：带项目校验 readonly；`persist` 需写预设角色；管理员写数据库预设、其余提交候选；删除 seed 文件写入与死代码 `upsert_seed_presets`（R1.4 / R1.5）
- [ ] 1.5 `reports.consistency_check` 改 `require_project_access("readonly")`；0 条可执行时 `no_result`；前端审核对话框空态（R1.6）
- [ ] 1.6 端点级测试：7 个端点 × 非成员 403（断言未触达数据）/ 成员 / 管理员（R1.1~R1.6）
- [ ] 1.7 鉴权守卫第三维（对象 / 请求体型）+ 已修钉子 + 双向变异；重算并下调既有基线（R1.7）

## 2. 表间审核严格取数（R7a）

- [ ] 2.1 新模块 `formula_ref_preload.py`：PREV / AUX 预载与严格缺数报错；AUX 走 `get_active_filter`；`report_engine` 改调并删除重复分支（R7.1）
- [ ] 2.2 更新 `test_user_rules_run…` 断言；新增「AUX 缺数 + 另一侧 0」「PREV 无上年数据」两例；变异去掉严格报错必红（R7.1）

## 3. 推送规则纳入治理内核（R2）

- [ ] 3.1 `definitions` 加 push 域；`push_settings.py`：`PushStore`、`validate_push_definition`、`effective_push_rules`（R2.1~R2.3 / R2.6）
- [ ] 3.2 接线：`get_store` / `validate_definition` / `display_formula` / `rollback` / `dependencies` / `WIRED_DOMAINS`（R2.1 / R2.8）
- [ ] 3.3 引擎读有效规则 + 失效进提示 + 触发来源 `FORMULA_CONFIG_CHANGED`（R2.4 / R2.5）
- [ ] 3.4 传播 handler `propagate_push`（R2.7）
- [ ] 3.5 规则列表接口返回层级与可用操作（R2.8）
- [ ] 3.6 后端测试：预设、四类拒绝、有效叠加、失效跳过、引擎改写生效 / 停用不推、传播（R2.2~R2.7）
- [ ] 3.7 前端：`formulaPushView.ruleActions` + 触发来源标签 + `definitionText` 停用；推送面板层级列与操作；全局设置页空表达式显示中文算式；单测（R2.8）

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
