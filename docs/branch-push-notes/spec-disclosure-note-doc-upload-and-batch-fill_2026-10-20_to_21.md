# 分支推送说明：`spec/disclosure-note-doc-upload-and-batch-fill`

> 整理范围：该分支 **2026-10-20 ~ 2026-10-21** 期间推送的 10 个 commit（`f949c5abc` ~ `020cad2c5`，含 1 个 merge）。
> 用途：让协作者快速了解这段时间分支里改了什么、按主题分类、各自的测试与迁移情况。
> 说明口径：按每个 commit 的**实际改动文件**（`git diff-tree --name-status`）归类，不只看 commit message。

分支当前顶端：`020cad2c5`（= `origin/spec/disclosure-note-doc-upload-and-batch-fill`，本地已同步）。

---

## 一、时间线总览

| commit | 时间 | 主题 | 一句话 |
|---|---|---|---|
| `f949c5abc` | 10-20 13:14 | DSH 子进程 + 知识库扫描件 OCR 本机优先 | DSH 走子进程 + 环回端点；扫描件后台 OCR；46 个预存失败用例逐例收口 |
| `71d0c04b5` | 10-20 17:04 | DSH 转发路由前缀 | 前缀写成字面量，鉴权基线扫描器可解析 |
| `0900957dc` | 10-20 19:46 | 审阅提示词 + OCR 字段 | 提示词覆盖率 / 科目级降级改取致同 2025 编码表；OCR 字段清单按实际用途定稿 |
| `a0033df40` | 10-20 23:48 | M7/M9 缺失 service + 惰性 import 守卫 | 补齐 8 端点缺失的 service；lazy import 守卫不再跳过整模块缺失 |
| `2bb730366` | 10-20 | 归档 | M7/M9 spec 归档到 `_archive/52` |
| `5283f3a67` | 10-21 | 文档 | DSH 端点策略放宽（本机不可用时用服务器 qwen3.8） |
| `8bfe70c1d` | 10-21 | 归档 | dsh-kb-ocr / preexisting-test-failures 两个 spec 归档到 `_archive/53`、`_archive/54` |
| `be04d555a` | 10-21 16:44 | 合并附注页请求安全 CP-05 | ConsolNoteTab 请求安全与身份校验，补齐 6 行为域（50/50 绿） |
| `dae1129f5` | 10-21 17:55 | 凭证抽样 reconcile | reconcile 改用余额表发生额 + 预览内就地放行 + G7 语法修复 |
| `020cad2c5` | 10-21 18:15 | 公式全局设置 | 公式全局设置 / 项目适配 / 一处改全处生效 + 公式模板（35/36） |

---

## 二、按主题分类

### A. DSH（审计数据助手子进程）+ 知识库 OCR 本机优先 — `f949c5abc` / `71d0c04b5` / `5283f3a67`
- **DSH 子进程化**：新增 `services/ai_chat/dsh_process.py`、`dsh_protocol.py`、`dsh_cordis_policy.py`、`dsh_model_bridge.py`、`dsh_smoke.py`；转发端点 `routers/dsh_model_forward.py`（子进程不拿 Key，走平台环回端点 `/api/ai-chat/dsh-llm/v1`，只收本机 + 带代理头即拒）。
- **知识库扫描件后台 OCR**：新增 `services/knowledge_ocr_service.py`、`workers/knowledge_ocr_worker.py`、迁移 `V198/R198__knowledge_documents_background_ocr.sql`（新增 `ocr_status/attempts/error/due_at` + SKIP LOCKED 租约）；上传请求内不再 OCR。
- **LLM 本机优先路由联动**：`llm_runtime.py`、`llm_endpoint_policy.py`、`model_route_status.py`、`remote_ocr_runtime.py`、`unified_ocr_service.py` 等调整。
- **DSH 端点前缀修复**（`71d0c04b5`）：`dsh_model_forward.py` 前缀改字面量，让鉴权基线扫描器可解析。
- 迁移：**V198 / R198**。
- 测试：`test_knowledge_background_ocr(.py/_pg.py)`、`test_dsh_model_bridge.py`、`test_dsh_protocol_vendor.py`、`test_audit_data_mcp_envelope.py` 等。

### B. 46 个预存失败用例逐例收口（随 `f949c5abc` 一并推送）
- 生产缺陷修复横跨：`core/startup_registry.py` 单一启动编排、`api/health.py` 启动报告、`wp_visibility/visibility_query.py`（SQLite UUID 兼容）、`wopi_service.py`（put_file 被拒后还原磁盘）等。
- 测试：`test_startup_registry.py`、`test_visibility_query_sqlite_compat.py`、`test_wopi_put_file_rollback.py`、`test_working_paper_list_api_pg.py`、`test_schema_drift_detector.py` 等。
- 归档：`8bfe70c1d` 把 `dsh-kb-ocr-local-first-routing` / `preexisting-test-failures-closure` 两个 spec 移入 `_archive/53`、`_archive/54`。

### C. 审阅提示词 + OCR 字段清单 — `0900957dc`
- `review_prompt_service.py`：提示词覆盖率、科目级降级改取**致同 2025 编码表**。
- 新增 `services/ocr_document_fields.py` + `ocr_rule_engine.py` / `ocr_service_v2.py`：OCR 字段清单按实际用途定稿。
- 测试：`test_ocr_document_fields.py`、`test_review_prompt_authoritative_workpapers.py`。

### D. M7 专项储备 / M9 其他综合收益 — 缺失 service 补齐 + 惰性 import 守卫 — `a0033df40` / `2bb730366`
- 8 个端点此前惰性 import 的 service 全仓不存在（一调即 `ModuleNotFoundError`）。新增共用内核 `services/m_detail_sheet_io.py` + `m7_special_reserve_service.py` + `m9_other_comprehensive_income_service.py`；`_f2_import_export.py` 两路径改裸 SQL。
- 守卫 `test_lazy_import_resolvability.py` 删「import 失败即静默跳过」分支，改三分（缺目标模块 / 其他失败走源码静态判定）。
- 测试：`test_m7_m9_equity_detail_io(.py/_pg.py)`、`test_f2_1_import_export_pg.py`、`m9-detail-import-refresh.spec.ts`。
- 归档：`2bb730366` → `_archive/52`。

### E. 合并附注页请求安全与身份校验 CP-05 — `be04d555a`
- `components/consolidation/ConsolNoteTab.vue` + `composables/consolRequestGuard.ts` + `composables/useCellComments.ts` + `services/consolidationApi.ts`：脏状态门控、并发 latest-wins、AbortController 取消、身份校验、A-B-A 保护。
- 顺带修生产 bug：`onUnmounted` 的 `autoSync.cancelPending()` 未定义导致每次卸载 `ReferenceError`。
- 诊断文档：`docs/proposals/consol-note-tab-spec-stale-vs-phase5-2026-10-20.md`。

### F. 凭证抽样 reconcile 取数源修复 — `dae1129f5`
- `routers/voucher_sampling.py` + 新增 `services/sampling_population_reconcile.py`：reconcile 改用**余额表发生额**。
- 前端 `voucher-sampling/` 组件 + `composables/samplingPopulationReconcile.ts`：预览内就地放行 + G7 语法修复。
- 测试：`test_sampling_population_reconcile(.py/_pg.py)` 等。

### G. 公式全局设置 / 项目适配 / 一处改全处生效 + 公式模板 — `020cad2c5`（分支当前顶端）
- 新增后端包 `services/formula_settings/`（约 30 个模块：engine / sync / publish / propagation / effective / templates / tb_detail / cross_check / rollback 等）+ 路由 `formula_settings.py` / `formula_templates.py` / `tb_detail_formulas.py`；模型 `formula_setting_models.py`。
- 迁移：**V199 / R199__formula_global_settings_and_templates.sql**。
- 前端：新增 `views/FormulaGlobalSettings.vue` + `components/formula/settings/` 一整套对话框组件 + `composables/formula/useFormulaSettings.ts`。
- 取数层四读者改为「本项目行公式空 = 本项目停用，不退回准则行」；`fill_all_formulas` 改经同步内核；表间审核落库 rule_id 改 `user:` + sha1。
- 测试：`backend/tests/formula_settings/`（约 14 个文件）+ 前端 `components/formula/settings/__tests__/`。

---

## 三、迁移与门禁提示（协作者拉取后注意）

- **新增运行时迁移**：`V198`（知识库后台 OCR）、`V199`（公式全局设置）。开发服务器热重载**不跑迁移**，拉取后需全量重启 `start-dev.bat`，或手动 `MigrationRunner(...).run_pending()` 落库。
- **行数门白名单**有多次追加（`backend/scripts/file_size_whitelist.txt`）：`FormulaManagerDialog.vue` 已超阈值并登记；`semantic_account_resolver.py` / `consol_elimination_sheet_service.py` 按真实行数登记。
- **归档目录变化**：`_archive/52`（M7/M9）、`_archive/53`（dsh-kb-ocr）、`_archive/54`（preexisting-test-failures）。引用旧 `.kiro/specs/<name>/` 路径的脚本需改指归档路径。

---

## 四、重要澄清

- 以上 10 个 commit 均由其他协作会话推送。**本会话（AI 采纳 / 转存笔记第二轮复盘修复）的改动尚未提交、未推送**，不在上述任何 commit 内。该部分的未提交文件清单见 `.kiro/specs/ai-chat-adopt-and-note-target-picker/design.md` §6.5 / §6.6.4。
