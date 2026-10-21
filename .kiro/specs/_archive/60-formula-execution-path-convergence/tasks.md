# 任务清单：公式执行路径收敛

> spec：`formula-execution-path-convergence` · requirements R1~R5 · design §1~§8

## Phase 1 统一预载层 + L1 handler 实装（R1, R2）

- [x] 1. `FormulaContext` 扩展 `ledger_data` / `ledger_detail_data` / `ledger_count_data` / `tb_aux_data` 四个新字段
- [x] 2~6. `formula_preloader.py`：`preload()` + `_scan_refs()` + `_load_tb/_load_adj/_load_ledger/_load_ledger_count/_load_tb_aux/_load_wp/_load_note` · 证据：20/20 扫描正确
- [x] 7. L1 handler 实装：`_handle_ledger/_handle_ledger_detail/_handle_tb_aux/_handle_count_ledger` 从 ctx 新字段取值（不再返回 0） · 证据：混合公式 `TB+LEDGER=150` 正确
- [x] 8. `test_formula_preloader.py` 19 passed（scan_refs 12 + L1 handler 7）

## Phase 2 prefill_engine 收敛（R3）

- [x] 9. `prefill_workpaper_real`：执行循环改为先 `preload()` 再逐格 `fe_execute(formula_text, ctx)` · 证据：255 passed 零回归
- [x] 10. `resolve_extended_formula`：内部改为 `preload([formula]) → execute`（保留签名兼容）
- [x] 11. 旧 resolver 保留但不再被主路径调用：`_FORMULA_RESOLVERS` 仅供 `_SUPPORTED_TYPES` 派生，8 个 `_resolve_*` 函数仅作为兼容参考
- [x] 12. `_parse_period_range` 保留在 prefill_engine（preloader 延迟 import）；`_parse_args` / `scan_formulas` / `FormulaCell` 保留
- [x] 13. ADJ 口径守卫 `test_adj_origin_scope.py` 2 passed：底稿路径 `frozenset()` + 报表路径含 `workpaper`
- [x] 14. `wp_user_formulas.py` 修正 `_FORMULA_RE` → `_get_formula_re()` 引用

## Phase 3 守卫与验收（R5）

- [x] 15. `test_production_wiring.py` 扩展：新增 `preload` 到 WIRED_FUNCTIONS（20→21）
- [x] 16. 回归：formula_settings **258 passed / 0 failed**
- [ ]* 17. 开发服务实测：需 start-dev 全量重启
- [x] 18. 提交（本提交）

## 提交文件清单

**新增**
- `backend/app/services/formula_preloader.py`
- `backend/tests/formula_settings/test_formula_preloader.py`
- `backend/tests/formula_settings/test_adj_origin_scope.py`

**修改**
- `backend/app/services/formula_engine.py`（FormulaContext 4 新字段 + 4 handler 实装）
- `backend/app/services/prefill_engine.py`（prefill_workpaper_real 改走 preload→L1 + resolve_extended_formula 改走 preload）
- `backend/app/routers/wp_user_formulas.py`（_FORMULA_RE → _get_formula_re 引用修正）
- `backend/tests/formula_settings/test_production_wiring.py`（+preload 到 WIRED_FUNCTIONS）
- `.kiro/specs/formula-execution-path-convergence/tasks.md`（完成证据）
