# 设计：`{pid}` 项目接口鉴权覆盖

## 1 现状（2026-10-31 现算，探针在仓库外，用完即删）

| 路由文件 | `{pid}` 端点 | 现有鉴权 | 档位 |
|---|---|---|---|
| procedure_trim / procedure_delegations / procedure_reconcile / procedure_delivery / workpaper_leads | 22 | `require_project_delegator_pid` | 项目级（前缀匹配已认） |
| version_trail | 5 | `enforce_wp_gate(…, project_id=pid)` | 对象级（底稿门，跨项目 404；PG 用例 `test_task9_core_route_gate.py`） |
| procedure_review | 3 | 读：`enforce_task_gate`；写：`_load_task`（任务须属于路径项目，跨项目 404）+ `resolve_conversation_access`（非参与者 403） | 对象级 |
| sampling_phase | 5 | `authorize_wp_read` / `_authorize_survival`，底稿须属于路径项目 | 对象级 |
| voucher_sampling | 6 | 提取 / 评价 / 撤销走 `_authorize_and_validate_*` / `_authorize_undo`，覆盖率 `assert_project_permission`；**历史、对比仅登录** | 4 对象级 + 2 仅登录 |
| cutoff_sampling | 4 | **仅登录**（不看底稿、不看项目） | 仅登录 |
| review_prompt | 3 | **无** | 无鉴权 |

`review_prompt.py` 另 4 个非项目路径端点同样无鉴权：`POST /api/workpapers/{wp_id}/review`、`PATCH /api/review-findings/{finding_id}/status`、`GET /api/review-prompts/coverage`、`GET /api/review-prompts/metrics`（后两个无前端调用方）。

## 2 修法

### 2.1 review_prompt
- 批量复核：`Depends(require_project_access("review"))`（逐张调大模型、写复核结果；复核类动作与 `batch-review-pass` 同受众、按项目级别定级）。进度、导出：`require_project_access("readonly")`。
- 单底稿 AI 复核：先 `authorize_wp_read`（底稿不存在 404、非成员 403，返回底稿所属项目），再 `assert_project_permission(…, "review")`，与批量同级；放在读底稿、调模型之前。
- 复核发现状态更新：先按 id 取该发现所属项目（`ai_content.content_type = 'review_finding'`，不存在 404），再 `assert_project_permission(…, "review")`，同一会话里更新并提交。
- 覆盖率、调用指标：`get_current_user`（全局只读诊断，不含项目数据）。

### 2.2 抽样
- 截止测试：本文件加 `_authorize_cutoff_wp(db, user, pid, wp_id, *, edit)`：`authorize_wp_edit` / `authorize_wp_read` 取底稿所属项目，不等于路径项目 403（同 `sampling_phase._authorize_survival`）。提取 / 回填 / 撤销 edit，历史 read；放在 `try` 之外（403 / 404 不被吞成 400 / 500）。
- 抽凭历史：同口径 read。抽凭对比：两条记录都须 `project_id == pid`（否则按不存在 404，与 `_authorize_undo` 一致），再对记录所在底稿 `authorize_wp_read`。

### 2.3 扫描口径（`test_project_endpoint_authorization_baseline.py`）
- `_has_project_segment(path)`：含 `{project_id}`，或匹配 `/projects/{任意名}`。三个维度（`_scan_unauthorized` / `_scan_identity_only` / `_scan_prefixed_source`）与分母都用它；前缀维排除条件同步（`var == "router"` 且装饰器路径本身已带项目段的归上两维）。
- 项目级 token 补：`enforce_wp_gate` / `enforce_task_gate`（底稿门 / 任务门，带路径项目；可伪证：两个函数都把 `project_id` 交给 `resolve_wp_binding_and_access`、拒绝即抛）、`resolve_conversation_access`（可伪证：引用它的端点同时 `_load_task` 绑定路径项目并在访问级别不足时 403；行为证据 `test_procedure_review_service.py` 无关用户 → none）、抽样四个本地鉴权辅助函数 `_authorize_survival` / `_authorize_and_validate_extract` / `_authorize_and_validate_evaluation` / `_authorize_undo` 与新增 `_authorize_cutoff_wp`（可伪证：定义处调 `authorize_wp_edit` / `authorize_wp_read`，并把结果与 `pid` 比较后 403）。
- 自检：`{pid}` 无鉴权样本判 none、`{pid}` 带项目级样本判 project、前缀 `/api/projects` + 装饰器 `/{pid}/…` 归前缀维。

### 2.4 台账
- `wp_bound_entry_coverage.json` 里 `review_workpaper` 由 `unmigrated` 改为 `native_authz`（与 `coverage_guard.classify_unmigrated` 的推导一致，test_ids 带本 spec 端点用例）；`check_drift` 改前改后对比，除这一条外无新增。
- 两个仅登录棘轮按新口径重算：新纳入的 `{pid}` 端点修完全部是项目级，常量不变或下调。

## 3 测试
- `backend/tests/test_pid_path_authz_endpoints.py`（SQLite + 真实依赖链，覆盖内层 `get_current_user` / `get_db`，不 override 鉴权工厂）：review_prompt 7 个、截止 4 个、抽凭历史 / 对比，各测 未登录 401、非成员 403、成员放行（成员放行时下游服务打桩，只验门禁之后才进下游）；跨项目底稿 / 记录 403 或 404。
- `test_review_prompt_integration.py` 既有用例按新鉴权补身份（不放宽门禁）。
- 变异：逐个摘掉新加的鉴权调用，对应用例打红；扫描口径改回字面量 `{project_id}`，`{pid}` 自检打红。

## 4 范围外（登记不改）
- 复核发现 id：批量 / 单张复核返回给前端的 finding id 是解析时随机生成的，落库 `ai_content` 用另一个随机 id ⇒ 前端「改发现状态」恒 404（与鉴权无关，需定 id 口径）。
- `enforce_wp_gate` 迁移：单底稿 AI 复核仍不走底稿门（读族 `ai_read` 只有 GET、写族 `ai_generate` 不含复核人），本 spec 用项目级鉴权，台账记 `native_authz`。
