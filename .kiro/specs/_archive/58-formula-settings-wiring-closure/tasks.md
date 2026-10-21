# 任务清单：公式设置接线收口与 stash 事故抢救

> spec：`formula-settings-wiring-closure` · requirements R1~R5 · design §1~§4

## Phase 1 事故抢救（R1、R2）

- [x] 1. 悬空 stash 打本地救援标签 `rescue/2026-10-21-*`（8 个），防 gc
- [x] 2. 恢复 19:50 那批 18 个文件，修 HEAD 导入失败（提交 9eaf41500；与悬空 stash 4cbd8029d 逐文件一致）
- [x] 3. 恢复 17:56 那批公式域 91 个文件 + 三方合并 3 处冲突裁决（提交 41c380e63）
- [x] 4. 外键目标表登记、2 份旧测试按新契约改写、行数门抢救登记（同 41c380e63）
- [x] 5. 判据：`tests/formula_settings` 146 passed；107 个相关测试文件对照 HEAD 干净检出新增失败 0、修复 8；前端公式域 72 文件 715 passed / 3 skipped

## Phase 2 并发会话缺陷（R3）

- [x] 6. 表间审核历史：`cross_check_history.py` + router 改按真实列读取 + 年度过滤 + `issues_retained` 诚实标记 · 证据：`test_wiring_closure_endpoints.py::TestCrossCheckHistory` 2 passed
- [x] 7. 依赖查询：`dependencies.py` 按有效定义取公式、精确匹配、科目下游、`begin_nested` 保存点隔离 + `unavailable_domains` · 证据：`TestDependencies` 7 passed + `TestUpstreamRefs` 4 + `TestReferences` 3
- [x] 8. 推送覆盖率：`coverage.py` 按真实编码分母（剔除程序表 + 不适用）· 证据：`TestCoverageCompute` 6 passed
- [x] 9. 编辑器函数清单：`formulaSyntaxParser.ts` 9→16 函数对齐 `formula_grammar.FORMULA_ARITY` / `formula_engine._REGISTRY`（+SUM_TB/PREV/ABS/ROUND/MAX/MIN/IF）· 证据：`formulaSyntaxParser.spec.ts` 38 passed
- [x] 10. `FormulaManagerDialog.vue` 4680→4502 行：提取 `CrossCheckHistoryPanel` / `FormulaDependencyPanel` / `PushCoverageCard` 至 `panels/` · 证据：formula 域前端 47 文件 536 passed；whitelist 4502

## Phase 3 守卫与验证（R4、R5）

- [x] 11. 生产调用方守卫 `test_production_wiring.py`：14 个接线函数 AST 扫描 + `WIRED_DOMAINS` 全覆盖 · 证据：15 passed
- [x] 12. 回归：`formula_settings` 189 passed；`formula_settings + formula_management + formula_runtime` 961 passed / 0 failed / 4 skipped；前端 536 passed / 3 skipped · 无新增失败
- [x] 13. 开发服务实测 · 证据：coverage 200（81/81 + excluded 8）；history 200（2 runs / 258 executed / 2 issues）；dependencies BS-002 200（3 upstream TB / 2 downstream report）；NOT-EXIST 404 FORMULA_DEPENDENCY_TARGET_NOT_FOUND
- [x] 14. 提交（本 spec 文件清单见下）

## 提交文件清单

**新增**（本 spec 产物）
- `backend/app/services/formula_management/cross_check_history.py`
- `backend/app/services/formula_push/coverage.py`
- `backend/app/services/formula_settings/dependencies.py`
- `backend/tests/formula_settings/test_wiring_closure_endpoints.py`
- `backend/tests/formula_settings/test_production_wiring.py`
- `audit-platform/frontend/src/components/formula/panels/CrossCheckHistoryPanel.vue`
- `audit-platform/frontend/src/components/formula/panels/FormulaDependencyPanel.vue`
- `audit-platform/frontend/src/components/formula/panels/PushCoverageCard.vue`
- `.kiro/specs/formula-settings-wiring-closure/` （三件套）

**修改**
- `backend/app/routers/formula_logic_check.py`（history 端点改走 service）
- `backend/app/routers/formula_push.py`（coverage 端点改走 service + 登录鉴权）
- `backend/app/routers/formula_settings.py`（dependencies 端点改走 service）
- `backend/scripts/file_size_whitelist.txt`（+4502 行 FormulaManagerDialog）
- `audit-platform/frontend/src/components/formula/FormulaManagerDialog.vue`（提取面板 4680→4502）
- `audit-platform/frontend/src/composables/formula/formulaSyntaxParser.ts`（函数列表 9→16）
- `audit-platform/frontend/src/composables/formula/__tests__/formulaSyntaxParser.spec.ts`（+6 新函数用例）

## 待用户决定

- 17:56 stash 余下约 250 个非公式文件（A-cycle hosts / AI chat / note template data 等）
- `DisclosureEditor.vue` 已恢复到工作树但 3312 > hard cap 3281，属合并附注会话
