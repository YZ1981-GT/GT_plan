# 设计：合并自动建树范围外问题收口

## 1. 现状核对（2026-10-27 现算 / 复现）

- 鉴权基线现算：路径维「只校验登录」189（基线 191），前缀维 260（270），请求体维 84（84）。报表页同域只校验登录的端点：`reports.py` 3、`report_line_mapping.py` 10、`report_related_workpapers.py` 1、`report_export.py` 1、`report_mapping.py` 3、`wp_report_analysis.py` 6，共 24。
- `require_operation` 被基线当成项目级（`_PROJECT_LEVEL_TOKENS`），实际只按「系统角色 ∪ 项目职责」判：路径带项目时查不到成员行 ⇒ 项目职责为空 ⇒ 退回系统角色；系统角色 manager / auditor / partner 都有 `wp:edit`、`report:edit`，所以**不是成员也放行**。用到它的端点：调整分录新建 / 底稿同步（路径带项目，写）、归档编排（路径带项目）、报表生成（项目在请求体，取不到 ⇒ 只看系统角色）、签名（请求体）、两处底稿保存（另有底稿门）。现有单测 `test_partner_passes_all` 把「非成员 partner 带项目也放行」写成了期望。这些端点原先挂 `require_project_access("edit")`（含归档守卫），换成它之后归档守卫也丢了：`test_property_archived_invariant`、`test_archived_project_guard::test_adjustments_post_returns_423_for_archived` 在 HEAD 上一直红。请求体维的扫描照搬基线、把只挂它的生成报表记成已隔离。
- 参照复制：服务按 `wizard_state["basic_info"]["data"]["client_name"]` 比名称，而向导把基本信息存在 `wizard_state["steps"]["basic_info"]["data"]`（平铺位置只有 `set_standard` 写过）⇒ 名称从来比不上，结果全靠「随便找一个有已确认映射的其他项目」，且候选不看权限；试算表「参照其他单位」下拉选的是项目 id，却当名称传。试算表导入的列映射「可参照项目」列出全平台项目名与客户名，复制不校验来源；保存 / 复制都是原地改 JSONB 再赋回同一对象 —— 探针复现 ORM 不发 UPDATE，真库 114 个项目 0 个存下过列映射。
- 向导确认：`derive_from_wizard` 同样只读平铺位置 ⇒ 探针复现上市合并项目一确认即被改成国企单户（两列 + 结构化准则 + 平铺副本），合并项目随之按单户重建企业树。真库 114 个项目四处准则声明（结构化 / 两列 / steps / 平铺）0 分叉 —— 现存已确认项目恰好都是国企单户。试算平衡表按报表行次汇总也读平铺位置定行次模板，未确认的上市 / 合并项目一直按国企单户行次出。
- 调整分录状态名：系统字典 / 前端常量 / 调整分录页 = 草稿 · 待复核 · 已批准 · 已驳回；状态机（可解释状态机面板）= 待审批 · 已退回，动作「提交审批」「退回」；底稿侧集中登记 = 已通过。合并抵销分录（前后端）= 草稿 · 待审批 · 已审批 · 已驳回。
- 合并范围表：真库 `consol_scope` 0 行、`companies` 0 行、合并项目 3 个。读它的有：附注正文变量（子公司数 / 清单）、程序表取数 `consol_scope_status`、合并总览范围校对（每棵树都显示「合并范围差异」）、G7 带入（查的是单体项目，另登记）、合并底稿导出（旧模型，无前端入口，另登记）。

## 2. 方案

### ADR-1 报表域：依赖挂到端点上

- 路径带项目的端点把 `Depends(get_current_user)` 换成 `Depends(require_project_access(级别))`：只读 readonly，改动 edit（行次映射的 AI 建议 / 修坏账 / 改 / 确认 / 批量确认 / 删 / 手工 / 参照复制，报表映射保存）。导出（含 POST 导出）按读处理。
- 生成报表：函数体首句 `assert_project_permission(db, user, data.project_id, "edit")`，保留操作矩阵检查。
- 不动的：`audit_report.py`、`report_trace.py` 不在本轮（R7）。

### ADR-2 第二个项目：显式校验、RLS 设回本项目

- 期初核对给了上年项目、参照复制给了来源项目 ⇒ 对它 `assert_project_permission(readonly)`，再 `set_rls_context(本项目)`（门禁会把 RLS 上下文设到被校验的项目，后续还要读写本项目）。
- 候选集合 = `deps.readable_project_ids`：与门禁同口径（admin 不限；其余 = 本人未删除成员行所在项目）。不用 `get_visible_project_ids`：它给 partner 全部项目，门禁不给，列出来的候选一读就 403。
- 行次映射参照复制：请求体 `source_project_id` 与 `source_company_code` 二选一；按名称改比 `projects.client_name`（向导建项目 / 改基本信息时同步写入），取可读项目里最新建的那个；找不到回 `source_found=False`，不再随便找一个。前端试算表弹窗改传项目 id，两个入口都对「找不到」给提示。
- 列映射：可参照项目按可读集合过滤；复制前校验来源；保存 / 复制先 `deepcopy` 向导状态再改。

### ADR-3 `require_operation`：归档守卫 + 成员校验（单点）

依赖拿到 `project_id`（路径 / 查询）时：① 会改数据的操作先判已归档（与 `assert_project_permission` 同一次序：归档最先，任何人都是 423；`project:view`、`archive:manage` 除外 —— 归档编排要对已归档项目幂等重入）；② 操作矩阵；③ `assert_project_permission(readonly)`（成员行、RLS 上下文；admin 例外）。取不到项目的端点不变；项目在请求体的端点（报表生成）在函数体显式校验（ADR-1），请求体维扫描不再把它算项目级。不另加「操作 → 最低级别」映射（readonly 成员仍按系统角色拿操作，记入 R7 观察）。

### ADR-4 状态名以系统字典为准

系统字典是可治理的单一来源：调整分录状态机的状态名、动作名改成字典与调整分录页的用语；底稿侧标签由前端常量派生；抵销分录（另一业务对象）保留审批用语，只要求「已驳回」一致。守卫：后端比状态机与字典；前端比集中登记标签与常量、常量与后端字典（直读 `system_dicts.py`，同 `h0DictConsumption.spec.ts` 做法）。

### ADR-5 合并范围成员 = 企业树，总览提示树版本

- 新建 `consol_scope_members.tree_subsidiaries(db, project_id)`：取 `consol_tree_service.build_tree` 里 `entity_kinds == subsidiary` 的企业（逻辑原在 `scope_diff_service._tree_members`），按树序去重。
- 附注变量：合并项目按企业树给 `subsidiary_count / subsidiaries / has_consolidation`，`ownership_ratio` 取合并范围表同代码属性行；非合并项目照旧 0 / 空。程序表取数同口径计数。
- 合并总览：对每棵树的合并根项目读树版本预览（`scope-confirmation/preview`，readonly），`structural_change` 为真时显示「企业树有变化」，点开 `ConsolScopeConfigDialog`（已有：差异、手动记录）。拖拽改上级后重读。读失败静默。
- 删除 `consol_scope_diff.py`、`scope_diff_service.py` 及其测试（调用方只有总览）；鉴权台账 / 清单、入口覆盖台账（`wp_bound_entry_coverage.json` 两条，汇总只做减法）与域边界债务基线（该条边）随之更新。合并范围表与其 CRUD 保留（G7 联动写持股比例等属性）。
- 域边界：附注正文变量读企业树是「附注 → 合并」方向，域边界检查器记为新违规（清单只允许合并依赖附注）。该检查在 HEAD 已有 290 条未登记违规、其中 6 条同向，CI 一直红；改成合并域登记回调或回到同步一张读模型表都比现状复杂，本 spec 保留直接读取、不改基线，登记在 R7。

### ADR-6 向导基本信息：steps 优先、平铺兜底

`standard_unification_service.wizard_basic_info_data`：先取 `steps.basic_info.data`，空则取平铺 `basic_info.data`。`derive_from_wizard` 与模板填充的报表口径回退改用它；试算平衡表汇总改走报表页的 `ReportConfigService.resolve_applicable_standard`（项目两列）。`set_standard` 写平铺副本的做法不动（准则切换后 steps 仍是旧值、自定义模板的 `template_type=custom` 也在 steps 里，改写它要另行设计，R7）。

## 3. 验证

- 后端：权限世界（`tests/authz_world.py`）真发请求 —— 24 个端点 × 非成员 403 且生产门禁执行过、edit 端点只读成员 403；每个文件至少一个端点按级别放行（业务 service 打桩）；端点级别按定级表核对；生成报表、期初核对上年项目、两类参照复制、列映射落库各一组；`require_operation` 单测改写 + 调整分录 / 归档编排端点非成员 403、已归档 423；`readable_project_ids` 与门禁逐身份一致；状态名守卫；附注变量 / 程序表取数用企业树（SQLite 建树）；向导确认保持准则、汇总按项目准则取行次；删除的路由不存在。
- 前端：集中登记标签、字典直读守卫；总览树版本提示（有 / 无结构变化、读失败、打开弹窗、拖拽后重读）；不再请求 `/scope-diff`；参照复制传项目 id 与「找不到」提示。
- 回归：后端合并 / 鉴权 / 报表 / 向导相关与 HEAD 失败集合逐条比；前端合并 / 视图 / 工作底稿相关 spec；单区域 vue-tsc；行数门；磁盘变异每条新判据；浏览器实测总览提示与报表页（成员可看、非成员 403 由接口测试覆盖）。

## 4. 验收记录（2026-10-27）

候选树 = HEAD 干净检出 + 本 spec 改动块（两个文件与并发会话的改动三方合并、只带本 spec 的块），与 HEAD 干净检出逐条比。验收期间 HEAD 由 `709b21275` 前移两次到 `934e68f4c`（程序链批 4、模板对拍第三批、推送后残留缺陷收口；与本 spec 重叠的只有 INDEX / memory 与 `trial_balance_service.py`、`useAdjustmentCentralSync.ts` 两个代码文件，这两个按新 HEAD 三方合并、改动块逐行核对只剩本 spec 的），每次都把候选树挪到新 HEAD 后重跑回归、清册、台账、vue-tsc，下面是最终 HEAD 上的数。

- 后端回归：224 个相关测试文件（含新 HEAD 三个提交改过的 22 个测试文件；候选另有本 spec 新增的 5 个、删掉的 1 个），HEAD 60 failed + 1 error / 候选 53 failed + 1 error，候选新增 0；候选修好 7 条（归档守卫 2、鉴权清单 `--check` / 两次生成一致 4、路径维基线等值 1）。前两个 HEAD 上同口径（205 / 218 个文件）也都是新增 0、修好同样 7 条。
- 前端回归：159 个相关 spec（含新 HEAD 碰到的布局 / 项目 store / apiProxy 在途共享），HEAD 3 failed / 候选 4 failed；多出的 1 条是 `guidanceBar` 属性测试，按失败种子（934068840）在 HEAD 重放同红（反例 `"! "`：测试里 `text()` 去掉了尾随空格），与本 spec 无关。
- 单区域 vue-tsc（改动的 6 个前端文件 + 4 个 spec 及其 import 闭包）：HEAD 0 / 候选 0；在 HEAD 树的 `.ts` 与 `.vue` 各埋一个类型错误，两处都报 TS2322（证明在查），跑完逐字节还原。
- 磁盘变异：在候选树逐条改 → 跑对应测试 → 逐字节还原并核对 sha256，47 条全部打红（报表域依赖 5、请求体 / 第二个项目 / 候选 15、`require_operation` 8、向导读法 4、状态名 3、合并范围 / 总览 8、前端参照复制 4）。首轮「成员不去重」存活：夹具里没有下级合并的企业，树里每个企业只有一个节点；补了下级合并企业（合并户 / 差额户 / 母公司户同一企业代码）的用例后打红。附注变量的保存点在 SQLite 上测不出（异常不会让事务中止），改测「失败不回滚调用方会话」。
- 行数门（只量暂存内容）：报表行次映射服务在 HEAD 已 889 行（上限 800、未登记白名单），本 spec 改的参照复制两个函数原样拆到 `report_line_mapping_reference_copy.py`，服务按原名导出（761 行，路由与测试照旧按服务模块属性调用）；鉴权基线测试 885 行超白名单 821 +5%，`require_operation` 口径前提搬到 `test_require_operation_token_tier.py`（基线测试回到 837 行）。暂存树自洽两道门 exit 0。
- 入口覆盖台账 `check_drift()`：HEAD 与候选逐条相同（删的两个路由与台账两条一起去掉）；两份鉴权清册 `--check` 均 0。
- 浏览器（开发服务器、admin）：合并总览只为有合并根项目的两棵树静默读预览、不再请求 `/scope-diff`（已 404）；真库三棵合并树都没有结构变化，提示用页面脚本把其中一棵的预览响应改成有变化来看 —— 只该树显示「⚠️ 企业树有变化」，点开即该根项目的「企业树版本」弹窗（已记录 v1、「当前树结构已变化」），控制台无错误。报表页（【测试】公式同步甲 2025）正常取数。试算表「映射规则 → 参照其他单位」选【测试】公式同步乙：请求体 `{"source_project_id": …}`，回 `copied_count 0 / source_found true`，提示「已复制 0 条映射」、弹窗关闭并重读；来源下拉此前列出本项目，已改为不列（选了只会 400；改后复测下拉 25 项、不含本项目）。向导「报表行次映射」步骤没有挂载点，只有 vitest 覆盖。

HEAD 已红、与本 spec 无关（两棵树同红，不改）：

- 后端：`test_account_chart_service` 18（夹具没给基本信息必填的企业代码 / 简称）、`test_phase8` 报表缓存 5（缓存方法签名加了参数）、`test_note_edit_gate_endpoints` 覆盖集 4（并发会话新增两个附注端点未登记配方）、`test_workpaper_writer_inventory` 4（裁决表指向源码已删的两个方法）、`test_auto_data_resolvers` 3、`test_consol_note_formulas` 种子计数 2、`test_lazy_import_resolvability` 2（新增 3 处不可解析的函数内 import，含 `ai_content` 引不存在的 `consol_lock_service`）、调整分录源码断言 / 转错报 3、`test_multi_standard_notes`（模板库缺 Q 前缀）、`test_report_equity_is_net_profit`、`test_report_models`（报表类型新增两个成员）。
- 前端：`composables.spec` 附注映射预设、`TbComparison.pbt` 导出列、`adjustmentIeContract` K13-3。
- 真库观察：上市两版资产负债表 `report_config` 中 BS-016~018 与 BS-013~015 同名重复（报表页这三行各出现两次）；合并总览打开时 `GET /api/projects/tree?scope=consolidated` 有两次，另一次是布局判定要不要显示「合并」菜单（`ThreeColumnLayout.vue`），不是本 spec 引入。
