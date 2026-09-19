# 设计文档：底稿模块大文件拆分（P0 / pass3）

## 概述

3 个超标文件按各自最自然的内聚边界拆分，全部降到 ≤800 行。核心原则：**结构搬运、零行为变更、对外入口不变**。每个文件采用与其性质匹配的拆分手法。

## 影响面（codegraph + grep 实测）

- `auto_data_resolvers`：对外仅暴露 `resolve_auto_data_source`/`get_registered_sources`/`_REGISTRY`。调用方 1 处（`procedure_table_auto_service`）+ ~10 个测试文件按 source 名断言注册。**⚠ `test_k_cycle_special_procedures.py` 用 `inspect.getsource(auto_data_resolvers)` 检查源码文本** → 拆分后该测试需改为查子模块或查 registry（在 tasks 中处理）。
- `WorkpaperFillService`：无生产调用方被 codegraph 捕获（动态实例化），grep 见 `wp_ai.py` 等 router + 3 个测试文件直接 `service._method()` 访问私有方法 → **必须保持方法仍挂在 `WorkpaperFillService` 实例上**（mixin 继承，非拆成独立函数）。
- `working_paper.py`：FastAPI router，端点经 `router_registry/workpaper.py` 注册。拆分须保持 (path, method) 全集不变。

## 拆分方案

### 1. `auto_data_resolvers.py` → 注册表 + 域子包

建立 `backend/app/services/auto_data_resolvers/` 包（同名模块转包，导入路径 `app.services.auto_data_resolvers` 不变）：

```
auto_data_resolvers/
  __init__.py          # 主文件：auto_resolver 装饰器、_REGISTRY、resolve_auto_data_source、
                       #          get_registered_sources、失败计数器；末尾 import 全部 _*.py 触发注册
  _adjustments.py      # adj_aje/rje/passed/consol、misstatement_summary/eval、materiality、tb_check
  _consol.py           # consol_scope/elim/trade/tb、cf
  _control_b.py        # b2/b3/b19/b15/b22/b23/b50、control_test_result、itgc、entity_control_list
  _cycle.py            # b23_for_cycle、risk_for_cycle、je_filter、internal_audit_reliance、
                       #          confirmation_summary、accounting_estimate_b51、cycle_audited_amounts
  _completion.py       # review_progress、sign_status、a21/a22/a23、wp/ctrl/sub_completion、ar_done、
                       #          archive、a16_recommend/sign、related_party*、ctrl_deficiency
  _tax_income.py       # ledger_detail、income_total、temp_diff、income_tax、revenue_s20、eps、
                       #          non_recurring
```

- `auto_resolver` 装饰器与 `_REGISTRY` 定义在 `__init__.py`；子模块 `from . import auto_resolver` 后用 `@auto_resolver("name")` 注册——**source 名逐字不变**。
- `__init__.py` 末尾 `from . import _adjustments, _consol, ...` 触发全部装饰器执行（registry 完整）。
- 公共 helper（如 `_resolve_sign_status` 被多个 resolver 复用）放 `_completion.py` 或新建 `_shared.py`，按实际引用就近放置。
- 主 `__init__.py` 目标 ≤300 行；各子模块 200~400 行。

### 2. `working_paper.py` → 主 router + 功能域子 router

保留主文件核心（list/get/download/upload/CRUD），拆出 3~4 个子 router 到 `backend/app/routers/`：

```
working_paper.py          # 主：list/get/download(_pack)/file_info/upload/update_parsed_data/status
                          #     + 共享请求模型（或移 schemas）
wp_editor_router.py       # 在线编辑：online_edit_session/univer_data(get/save)/onlyoffice_config/
                          #     prefill/parse/export_pdf/sign_status + _prefill_word_template +
                          #     _push_representation_letter_date helper
wp_review_router.py       # 复核+分配：assign_workpaper/submit_review/update_review_status/
                          #     _send_reassignment_notifications(随 assign 唯一调用方同模块)/
                          #     _push? (见下) /复核相关
wp_batch_router.py        # 批量+看板：kanban/batch_assign/batch_submit/batch_export/edit_time
wp_relation_router.py     # 关系：list_wp_index/cross_refs/cross_links/relation_graph/sync_procedure_status
```

> **复盘修正**：`assign_workpaper` 归入 `wp_review_router`（与其唯一调用的 helper `_send_reassignment_notifications` 同模块，避免主文件→子 router 反向依赖）。`_push_representation_letter_date` 随 `update_sign_status` 入 editor_router；`_prefill_word_template` 随 `get_wp_onlyoffice_config` 入 editor_router。已 grep 确认三 helper 各仅一个调用方，随调用方迁移无跨模块依赖。
- 共享请求模型（`UploadRequest`/`StatusUpdateRequest`/`AssignRequest`/`ReviewStatusRequest`）移到 `backend/app/schemas/`（或保留主文件 import）；私有 helper 随其唯一用例迁移。
- 端点 (path, method) 全集不变 → 由 PBT/registry 测试保证。
- 主文件目标 ≤800；子 router 各 200~500 行。

### 3. `workpaper_fill_service.py` → Mixin 组合

`WorkpaperFillService` 方法被测试直接以 `service._xxx()` 访问 → 用 **mixin 继承**保持方法挂在实例上、对外零变更：

```
workpaper_fill_service.py        # class WorkpaperFillService(FillTaskMixin, AnalyticalReviewMixin,
                                 #   DataGenMixin, NoteDraftMixin, ReviewPromptMixin): __init__ + 组装
wp_fill/_fill_task.py            # FillTaskMixin: create/execute_fill_task、_fill_*、_build_*_prompt、
                                 #   _parse_ai_response、get_task、get_fill_result、list_tasks
wp_fill/_analytical_review.py    # AnalyticalReviewMixin: generate_analytical_review、_get_trial_balance、
                                 #   _get_large_transactions、_get_top_aux_balances、prompt、fallback、confidence
wp_fill/_data_gen.py             # DataGenMixin: generate_workpaper_data、_generate_tb_analytical/inventory/
                                 #   confirmation/other_data、fallback_tb
wp_fill/_note_draft.py           # NoteDraftMixin: generate_note_draft、_get_section_accounts、
                                 #   _get_financial_report_data、_get_trial_balance_data、prompt、fallback
wp_fill/_review_prompt.py        # ReviewPromptMixin: review_workpaper_with_prompt、load_review_prompt、
                                 #   _base_review_prompt、check_pending_confirmations
```

- 每个 mixin 是普通 class，方法签名（含 `self`）不变；主 class 多继承组合。
- `self.db`/`self.ai_service` 等实例属性在 `__init__` 设置，mixin 内照常 `self.db` 访问。
- 主文件目标 ≤200；各 mixin 200~450 行。

## 守卫与验证

- 复用 silent-cleanup 的 `check_file_size.py` 思路：新增/复用测试断言这 3 文件 ≤800。
- registry 不变性：`get_registered_sources()` 拆分前后 set 相等（可加快照断言）。
- 端点不变性：基于 `app.routes` 的 (path, method) 集合断言（沿用 pass2 Property 8 思路）。
- 全量：冒烟 1096 + auto_data 28 + workpaper_fill 测试 + silent 守卫 + router registry。
- codegraph 核对 import 无循环、无遗漏调用点。

## 不做的事

- 不动 pass2 已达标文件（render_config/classification/template/strategies/xlsx/docx）。
- 不改任何端点路径、resolver source 名、SQL、AI prompt 文本。
- 不为追求更小行数制造碎片；每文件 ≤800 即停。
- 不删除/合并任何 resolver 或端点。
