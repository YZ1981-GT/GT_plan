# 设计文档：公式设置接线收口与 stash 事故抢救

> spec：`formula-settings-wiring-closure` · 需求见 requirements.md（R1~R5）

## 1. 事故还原（证据链）

| 时间 | reflog / 对象 | 影响 |
|---|---|---|
| 17:56:04 | `git stash push -m temp-for-push-reconcile` → 悬空 112bfabec | 收走 386 个文件的未提交改动（多会话），之后未 `pop` |
| 18:04~18:15 | checkout 新分支提交 d852c0895，回原分支 cherry-pick 为 020cad2c5 | 只带上未跟踪新文件与少量改动；接线改动留在 stash 里 |
| 19:50:05 | `git stash` → 悬空 4cbd8029d | 再收走 29 个文件（含 19:20 前后补写的 FormulaSupportViolation 简化版） |
| 19:52 / 19:57 / 20:09 | 其他会话提交 | 未包含被收走的改动 |

判据：`git fsck --no-reflogs` 列出的悬空 commit 消息即 stash 消息；`git diff <stash>^1 <stash>` 即当时工作树改动。编辑器本地历史（`%APPDATA%\Kiro\User\History`）可独立复核 19:50 那批（20/20 一致）。

## 2. 恢复规则

- 分类（脚本按文件逐个判定）：`wt`（工作树已等于 stash）/ `committed`（HEAD 已等于 stash）/ `lost`（HEAD 仍等于 stash 基线）/ `diverged`（之后又有提交）。
- `lost`：写 stash 版本（删除则删除），BOM / 换行跟随当前工作树；只写工作树不碰暂存区。
- `diverged`：`git merge-file`（ours=HEAD，base=stash^1，theirs=stash），冲突逐个裁决。
- 范围：本 spec 只恢复公式域（路径白名单见抢救脚本）；其余交用户决定（tasks 收尾清单）。

### 2.1 冲突裁决

| 文件 | 裁决 | 理由 |
|---|---|---|
| `function_support_matrix.py` | 取 stash | 原实现含 `support_issues` / `require_function_support`，19:50 版是丢失后补写的简化版；调用方两者都兼容 |
| `projectCacheKey.ts` | 取 stash | 原实现带泛型、按 Promise 身份清在途；补写版类型更窄 |
| `formula_logic_check.py` | 取 HEAD | stash 侧无改动，HEAD 多出的历史接口保留后按 R3.1 修 |

### 2.2 恢复后补的修正

- `consol_note_mapping_models.py`：恢复出的 `promoted_to_template_id` 外键指向 V200 规则模板表，只加载本模块时目标表不在 MetaData ⇒ 模块末尾显式导入模板模型（无导入环）。
- 旧测试按新契约改写：附注公式往返（原假会话测不到差量写 + 物化，改 SQLite 真 ORM，PBT `max_examples=5`）；`wp_formula` P12 第二次保存带 `expected_version`（CAS）。
- 行数门：`wp_formula.py`（HEAD 已 1412 超基线未登记）与 `draft_refresh_service.py`（HEAD 1926 历史大文件未登记）按恢复后真实行数登记并写明拆分方向；不在事故恢复里重写已测过的事务代码。

## 3. 并发会话 4 处缺陷（R3）

| 缺陷 | 改法 |
|---|---|
| 表间审核历史 500 | `DraftRefreshAudit.operated_at` 排序 + `year` 过滤；结果行读 `left_amount` / `right_amount` / `difference` |
| 依赖查询 500 / 误匹配 | 报表地址经 `effective_slots(report)` 取本项目有效公式；精确匹配 slot；下游用反向索引 + 报表公式文本里的 `TB('code'` 精确扫描；`depth` 未实现则不收 |
| 覆盖率恒 100% | 分母取致同 2025 编码表 D~N 实质性循环的主编码集合，分子取已登记推送的主编码；A/B/C/S 单列「不需推送」 |
| 编辑器误报未知函数 | 函数清单与后端一致：TB/SUM_TB/ROW/SUM_ROW/REPORT/NOTE/WP/PREV/AUX/ADJ/ABS/ROUND/MAX/MIN/IF + 附注 PRIOR/AGING；参数个数按后端 |

`FormulaManagerDialog.vue` 超门：把 ux 新增的「执行历史」「依赖关系」「推送覆盖率」三块抽成独立组件，主文件只留接线。

## 4. 守卫（R4）

`tests/formula_settings/test_production_wiring.py`：AST 扫 `backend/app`（不含测试），断言下列执行层入口各有至少一个生产调用方，并对扫描器做内存变异（删掉调用后必须报缺）：

- `cross_check_rules.run_user_rules`（报表勾稽执行）
- `wp_effective.init_prefill_overrides` / `overlay_prefill_formulas`（底稿预填）
- `consol_note_settings.effective_formulas`（合并附注填数）
- `note_settings.save_section` / `materialize`（附注保存与传播）
- `rollback.rollback_from_log`（公式历史回滚）
- `custom_presets.upsert`（自定义预设写库）
- `report_config_baseline` 路由调用 `publish_events`

并断言 `WIRED_DOMAINS` 中每个域都有对应入口被调用。
