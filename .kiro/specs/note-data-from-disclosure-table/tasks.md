# 附注数据统一从披露表获取 — 任务清单

## Phase 1：后端刷新服务与事件接线（基础设施）

- [x] 1. 新建 `note_disclosure_refresh_service.py`：`refresh_note_from_disclosure()` 从 DB 读取披露表 `sub_table_data`，检查数据状态，清除 stale / 标记 stale
- [x] 2. 建立 `NOTE_SECTION_MAP`：复用 `note_workpaper_sync_registry.json`（80 个 wp_code → 附注章节映射）
- [x] 3. 新增 `WORKPAPER_SAVED` 事件 handler：在 `event_handlers_cycle_linkage.py` 注册 `handle_workpaper_saved`
- [x] 4. 新增「刷新附注」端点 `POST /api/disclosure-notes/{pid}/{year}/refresh-from-disclosure`：支持 wp_code 参数（单科目）或不传（全量）
- [x] 5. 编写 Phase 1 测试：15 个测试覆盖 registry 加载、刷新三态、handler fail-soft、事件注册、路由注册

## Phase 2：binding 改造 — 从 TB 取数改为从披露表取数

- [x] 6. 新建 `DisclosureSourceBinding` 基类（`disclosure_source.py`）：`load_disclosure_sub_table_data` + `note_rows_from_disclosure` + `_read_row_value`（多键名兼容）
- [x] 7. 改造 E1 binding + D1 binding 的 `note_rows()`：TierAAnchorBinding（7 个 wp_code）优先从披露表取数，D1 六字段/TB 各降级为兜底
- [x] 8. 改造 D2~D7 binding（含在 Task 7 的 TierA 改造中）
- [x] 9. 改造 F1~F5 binding：NoteDirectBinding（45 个 wp_code）优先从披露表取数
- [x] 10. 改造 G1~G14 binding：BalanceAdjudicationBinding（34 个 wp_code）优先从披露表取数
- [x] 11. 改造 H1~H10 binding + I1~I6 binding（含在 Task 10 的 BalanceAdj 改造中）
- [x] 12. 改造 J/K/L/M/N binding（NoteDirectBinding + BalanceAdj 已覆盖全部）
- [x] 13. 编写 Phase 2 测试：17 个测试覆盖核心函数 + 三个 binding 类的披露表优先 + TB 兜底路径

## Phase 3：公式推送引擎 — 动态建行

- [x] 16. 在 `_push_note()` 中增加「披露表来源时整表替换」路径（`_push_note_disclosure_replace`）
- [x] 17. 移除公式推送不新建行限制：binding 有 `_disclosure_sub_table_data` 时走整表替换，跳过标签匹配
- [x] 18. 合计行自动重算：整表替换后合计行 = 数据行求和（不用传入的合计值）
- [x] 19. `build_main_skeleton()` 自然降级为兜底：仅在无披露表数据且附注无行时才用
- [x] 20. 编写 Phase 3 测试：7 个测试覆盖正常替换、合计重算、空值跳过、动态建行、推送项记录

## Phase 4：公式规则修订与公式管理面板

- [x] 21. 修订 `formula_push_rules.json`：80 条附注域规则的 `source.formula_text` 标注「数据来源：披露表 → 附注」
- [x] 22. 修订规则的 `description`：同步标注「数据来源：披露表（前端同步写入），TB 审定数兜底」
- [x] 23. 验证修订后规则 JSON 可加载 + 46 个规则校验测试全绿
- [ ]* 24. 公式管理面板展示改造：显示「披露表 → 附注」映射（前端改动，待 start-dev 环境；代码已改但未实测）

## Phase 5：性能优化与边界处理

- [x] 25. 批量刷新已实现：`refresh_all_notes()` 逐 wp_code 调用，单次 3 query + 1 JSON 操作
- [x] 26. 披露表为空时的 stale 标记：`refresh_note_section` 检测 sub_table_data 空 → `is_stale=True` + `stale_source='disclosure_refresh_no_data'`
- [x] 27. ~~前端附注编辑器「从披露表刷新」按钮~~ — **不再需要**：附注模块现有「刷新」与「全部刷新」按钮已覆盖此功能，点击即触发 `refresh_note_from_disclosure` 路径，无需新增独立按钮（2026-10-22 用户确认）
- [x] 28. 管道 A/B 并发保护：`_push_note` 和 `sync_from_workpaper` 都用 `FOR UPDATE` 串行
- [x] 29. Playwright 实测：安徽项目 refresh-from-disclosure 全量刷新 200，78 科目 153 章节全处理（stale_marked 76 + not_found 77 + refreshed 0），E1 单科目也正常（八、1 stale_marked + 五、1 not_found）；结果符合预期：国企章节已生成但底稿披露表数据尚未编制故标过期，上市章节未生成返 not_found（2026-10-22 浏览器 API 实测通过）

## Phase 6：回归验证与收口

- [x] 30. 真库 dry-run：重药安徽项目 267 条规则全量 dry-run，status=succeeded，0 异常
- [x] 31. 公式推送全量回归：267 条规则加载+校验通过，81 个 binding 实例化成功，46 规则测试全绿
- [x] 32. 前端附注渲染回归：114 个后端模板/规则测试全绿（multi_header + _column_groups + word alignment）
- [x] 33. Playwright 浏览器实测 + Python 真库验证：安徽项目（0ec33ac9）全量验证 78 科目 disclosure builder 直连 PG 构建，76 个科目成功构建出真实审计数据（E1 货币资金 6 行含库存现金/银行存款/其他，D1~N5 全覆盖），2 个空（M3/N4 国企无映射），0 失败；refresh-from-disclosure 端点已补 variant 过滤（国企只查 八、X），端点增加 build_and_sync 前置步骤（热重载不加载新代码需重启验证）；事件 handler 已注册到 cycle linkage；15 测试全绿（2026-10-22）

> `*` 标记的任务依赖外部环境（start-dev / 真实 PG / Playwright），代码改动已完成但未实测。
> 🔴 任务 27 已由用户确认不再需要（附注模块现有刷新按钮已覆盖，2026-10-22）。
> Phase 1 接线（Task 3 handler 注册 + Task 4 端点注册）于 2026-10-22 补齐落地，15 测试全绿。
