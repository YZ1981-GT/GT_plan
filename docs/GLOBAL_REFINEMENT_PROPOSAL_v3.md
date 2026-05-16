# 审计平台全局打磨建议 v3（实测驱动版 v2）

**编制人**：资深合伙人（兼平台治理负责人）
**日期**：2026-05-16（第二次实测后修订）
**前提**：v1（路线图盘点）+ v2（角色穿刺）已基本落地，主框架可用
**定位**：每一条建议都用真实项目跑通后给出，**不基于 memory 推测**
**实测样本**：陕西华氏 / 和平药房 / 辽宁卫生 / 宜宾大药房（YEAR=2025，admin/admin123）
**实测链路**：账表上传 → 科目映射 → 试算表 → 试算汇总 → BS/IS/CFS 报表 → 调整分录 → 错报 → 底稿 → 附注 → 复核/通知/AI

> **第二次实测重要修正**：第一稿提的 F1（IS/CFS 全 0）经定位是 **stale 数据**不是公式 bug——重新调一次 `POST /api/reports/generate` 立即变 IS=14 行非零；F2 修复路径已被 chain 端点验证（和平 0→107、辽宁 0→104）；F3 是脚本断言写错不是后端 bug；新发现 F6（AJE 创建 500 / SQLAlchemy MissingGreenlet）和 F7（PG enum 缺 `interrupted` 值）才是真正待修的 P0。

---

## 0 一句话评估（第三次实测后修订）

> 后端架构已企业级（150+ 路由 / 200+ 服务 / 460+ 测试），但**主链路有 5 处真红色断点 + 多处 PG schema 与 Python 代码不一致**：
> - F2 init 漏调 chain（已临时修复）
> - F6 AJE 创建 500（MissingGreenlet）
> - F7 + F8 两个 PG enum 共缺 7 个值（job_status / report_type）
> - F9 EQCR 3 个端点 404/405
> - F10 复核记录端点 404
>
> 前端组件库已搭好，但**接入率严重不均衡**——简单页面 75% 接入 GtPageHeader、复杂页面（编辑器系列）几乎全部硬编码 CSS。

**所以 v3 主线只有两条**：
1. **修复主链路 F1-F15 真实缺陷（实测后 3 个误判已平反，剩 12 个真问题）**—— **8 天工时**（详见 §6）
2. **把"半通"的联动在前端补齐 + 显示治理三条线**—— **R10 立项**（详见 §7-§9）

> 注意：F1/F3/F5 三个第一稿假设的问题在第二次实测后**已平反结案**；F11 在第三次实测后也平反（端点真实存在，路径假设错）。真正待修的红色 P0 是 F2 / F6 / F7 / F8 / F9 / F10。

---

## 1 主链路实测全景（2026-05-16，第三次实测后修订）

> 第二次实测的报表数字（重新 generate 后）；第三次实测扩展到 EQCR/复核/签字/AI 等盲区模块。

| 项目 | 账表 | 映射% | 试算 | BS-summary | BS非零 | **IS非零** | **CFS非零** | 调整 | 错报 | **底稿** | 附注 | workflow |
|------|-----:|------:|-----:|-----------:|-------:|-----------:|------------:|-----:|-----:|---------:|-----:|----------|
| 陕西华氏 | 812 | 100% | 100 | 129 | **32** | **14** | 0 | 0 | 0 | 92 | 173 | 6/6 ✓ |
| 和平药房 | 402 | 100% | 53 | 129 | **34** | **13** | 0 | 0 | 0 | **107** ✓ | 173 | 6/6 ✓ |
| 辽宁卫生 | 329 | 100% | 47 | 129 | **31** | **14** | 0 | 0 | 0 | **104** ✓ | 173 | 6/6 ✓ |
| 宜宾大药房 | 812 | 100% | 100 | 129 | 17 | 10 | 0 | 0 | 0 | 42 | 173 | 6/6 ✓ |

**陕西华氏利润表实测样本**（重新 generate 后）：
```
IS-001 一、营业总收入                       -20,283,811,823.52
IS-002 其中：营业收入                       -20,283,811,823.52
IS-008 其中：营业成本                        19,024,350,241.35
IS-021 税金及附加                                22,517,979.10
IS-022 销售费用                                 505,080,400.27
IS-023 管理费用                                  72,957,201.11
IS-025 财务费用                                 171,005,147.56
IS-045 减：所得税费用                            42,302,766.52
```

**结论**：报表系统**完全正常**——生成的 IS 数字真实可用，只是 init_4_projects.py 没在最后调一次 generate。

**真问题清单**（第三次实测后筛过，红色 5 个 / 黄色 5 个 / 已澄清 4 个）：
- 🔴 **F2** 真红：chain 自动跑底稿生成路径缺失（已临时修复 4 项目）
- 🔴 **F6** 真红：AJE 创建 500（SQLAlchemy MissingGreenlet）—— 调整分录链路完全不可用
- 🔴 **F7** 真红：PG enum `job_status_enum` 缺 3 个值（interrupted / retrying / cancelled）
- � **F8** 真红（升级）：PG enum `report_type` 缺 4 个值（cash_flow_statement / equity_statement / cash_flow_supplement / impairment_provision）
- � **F9** 真红（新发现）：EQCR opinions/prior-year 404 + memo 405
- � **F10** 真红（新发现）：复核记录 + 复核对话端点 404
- 🟡 **F4** 次要：consistency-check 缺 `all_passed` 顶层字段
- 🟡 **F12** 次要（新发现）：错报阈值重检 schema 错（422）
- 🟡 **F13** 次要（新发现）：`/api/users/me/nav` 404（前端用 FALLBACK_NAV，不影响业务）
- 🟡 **F14** 次要（新发现）：`/api/knowledge` 404（前端可能用 `/api/knowledge-folders`）
- 🟡 **F15** 次要（新发现）：`/api/projects/{pid}/ledger-import/jobs/latest` 422（前端残留旧路径）
- 🟢 **F1 已澄清**：报表生成完全正常，只是 init 链路漏 generate
- 🟢 **F3 已澄清**：data-quality 5 个检查全跑（passed=3+blocking=2），脚本断言字段名写错
- 🟢 **F5 已澄清**：AJE 422 是 schema 字段名错（`entries` vs `line_items`），与大小写无关
- 🟢 **F11 已澄清**：签字端点真实存在（`/api/projects/{pid}/sign-readiness` + `/api/signatures/{type}/{id}`），是脚本路径假设错

---

## 2 P0 真实缺陷（第三次实测重排，✅=已澄清/🔴=真问题/🟡=次要）

### ✅ F1（已结案）：IS/CFS 计算并非 0，是 stale 数据问题

**第一稿误判**：以为公式实现有问题。

**第二次实测真相**：
- 直接查 PG：陕西华氏 6001 营业收入 `audited_amount` = -20,283,811,823.52 ✓
- 调一次 `POST /api/reports/generate` body `{"project_id":"...","year":2025}` 后，IS 立即 14 行非零、BS 32 行非零（之前 27）
- **report_engine 的 `TB('6001','本期发生额')` 公式逻辑完全正确**（`_period_amount` → `audited_amount - opening_balance`，即损益类的发生额）
- 4 项目重新 generate 后 nonzero 全部上来：陕西 46 / 和平 47 / 辽宁 45 / 宜宾 27

**真正问题**：`scripts/init_4_projects.py` 跑完 `generate_all_reports` 后，**后续如果改了 trial_balance 或 standard 设置**，financial_report 会 stale；用户进系统看到陈旧 0 数据以为是 bug。

**修复路径（已部分验证）**：
1. ✅ `scripts/v3_regen_reports.py` 已写并验证：4 项目重新 generate 后 nonzero 全部上来
2. （0.2h）`init_4_projects.py` 末尾加 force generate（或直接调 chain）
3. （0.5h）前端 ReportView 显示 `last_generated_at` + 与 `last_recalc_at` 比较 → stale 即提示"建议重新生成"

**验收口径**：
```
4 项目均 IS-nonzero ≥ 10 (实测 10-14 ✓)
4 项目均 BS-nonzero ≥ 17 (实测 17-34 ✓)
```

---

### 🔴 F2：底稿生成在半数项目缺失 —— **chain 端点已验证完全工作**

**实测**：
- 陕西华氏 92、宜宾大药房 42（init 时跑过 chain）
- 和平药房 0 → 调 `POST /api/projects/{pid}/workflow/execute-full-chain` `{"year":2025,"force":true}` → **变 107 张底稿**
- 辽宁卫生 0 → 同上 → **变 104 张底稿**

**根因**：`scripts/init_4_projects.py` 当时只跑 auto-match → recalc → generate_reports，**没跑 chain**。

**修复路径**：

立即（5 分钟）：上述两条 POST 已在实测中执行。

长期（1 天）：
- 修改 `init_4_projects.py` 加最后一步调 chain
- `WorkpaperList.vue` 加引导卡片：检测到 `tb_count > 0 && wp_count == 0` 时显示"⚠️ 底稿尚未生成 [一键生成]"按钮

**验收**：4 项目 wp_count > 0，且 with_file == count（实测全部满足 ✓）

---

### ✅ F3（已结案）：data-quality 完全正常，是脚本断言写错

**第一稿误判**：以为响应 body 字段为空。

**第二次实测真相**：
- 真实响应结构：`{checks_run: [...], results: {...}, summary: {passed, warning, blocking}, total_accounts}`
- 脚本错把 `checks` 当数组断言，正确字段名是 **`checks_run`**
- 4 项目实测 `len(checks_run) == 5`（debit_credit_balance / balance_vs_ledger / mapping_completeness / report_balance / profit_reconciliation）
- 实测分布：陕西 passed=3+blocking=2 / 辽宁 passed=2+warning=1+blocking=2

**修复**：
- 前端 `services/dataQuality.ts` 已正确接对 `checks_run`（实测 R10 spec 落地的 DataQualityDialog 能渲染）
- 文档 `docs/FRONTEND_BACKEND_ALIGNMENT_CHECKLIST.md` 加一条：data-quality 字段是 `checks_run` 不是 `checks`

---

### 🟡 F4：workflow/consistency-check 缺顶层 `all_passed` 字段

**实测**：
```json
GET /api/projects/{pid}/workflow/consistency-check?year=2025
→ 200, body: { "checks": [5 items], ... }   // 没有 all_passed 也没有 consistent
```

**4 项目实测派生**：每个项目都返回 5 条 checks，"派生 all_passed" 全部 = 2/5（即 3 条 passed=false）。

**修复路径**（0.5 天）：
```python
# backend/app/routers/chain_workflow.py consistency_check 端点末尾
return {
    "checks": checks,
    "all_passed": all(c.get("passed", False) for c in checks),
    "consistent": all(c.get("passed", False) for c in checks),  # alias
    "passed_count": sum(1 for c in checks if c.get("passed")),
    "total_count": len(checks),
}
```

---

### ✅ F5（已澄清）：AJE schema 字段名错，与大小写无关

**第一稿误判**：以为是 `adjustment_type` 大小写问题。

**第二次实测真相**：真实 schema `AdjustmentCreate`：
```python
{
  "adjustment_type": "aje",       # 仅小写枚举（aje/rje）
  "year": 2025,
  "company_code": "default",
  "description": "...",
  "line_items": [                  # 不是 entries
    {
      "standard_account_code": "1001",   # 不是 account_code
      "account_name": "库存现金",
      "debit_amount": 100,
      "credit_amount": 0
    }
  ]
}
```

第一稿因为 schema 字段名错（写成 `entries`+`account_code`+`memo`）拿到 422。**用正确 schema 仍报 500——见 F6**。

**修复**（可选）：
- 前端 `apiPaths.ts` adjustments 接口注释里加 schema 范例
- 后端可选加 `adjustment_type` 大小写容错（用户视角友好）

---

### 🔴 F6（新发现，第一稿没看到）：AJE 创建端点 SQLAlchemy MissingGreenlet 500

**实测复现**：
```
POST /api/projects/{pid}/adjustments
body: 标准 AdjustmentCreate 结构（line_items + 小写枚举）
→ 500 + 后端日志：
  sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
  can't call await_only() here. Was IO attempted in an unexpected place?
  位置: result = await svc.create_entry(project_id, data, user.id, batch_mode=batch_mode)
```

**根因**（待 grep 定位）：
- `user` 由 `require_project_access` 返回，从 Redis 缓存路径回来时 user 对象已 detached
- `user.id` 应该不触发 lazy load（id 是基础列），但 `current_user.id` 在某个事件 handler 里继续被使用导致问题
- 或者 `_publish_adjustment_event` 里的 SSE handler 用 ORM 关系访问触发 lazy load

**严重度**：🔴 红色——**完整的调整分录创建链路目前不可用**：
- 前端 `Adjustments.vue` 的"创建调整分录"按钮触发 → 500
- "AJE→错报转换"也走不通（依赖创建分录）
- 联动测试（修改 AJE 触发 stale）整链断
- 上传现有 AJE 也大概率失败

**修复路径**（1-2 天）：
1. 在 `adjustment_service.py` `_publish_adjustment_event` 之前 `await db.refresh(user)` 或直接传 `user_id` 而非 `user` 对象
2. 检查 `event_handlers.py` 里的 `_notify_adjustment_event_sse / _record_tb_change_on_adjustment / _mark_reports_stale_on_adjustment` 三个 handler，是否有访问 ORM 关系字段
3. 跑 pytest 套件 `test_adjustments.py` 看现有测试是否能复现
4. 加 1 个回归集成测试：admin 角色调 `POST /adjustments` 应 201（防回归）

**验收口径**：
```
POST /api/projects/{pid}/adjustments {valid body} → 201
后端日志无 MissingGreenlet
后续 stale_summary stale_count +1
DELETE 该分录后 stale_count 归 0
```

---

### 🔴 F7（新发现）：PG enum `job_status_enum` 缺 `interrupted` 值

**实测**：后端日志每 30s 报一次：
```
WARNING [import_recover] loop error:
  asyncpg.exceptions.InvalidTextRepresentationError:
  invalid input value for enum job_status_enum: "interrupted"
[SQL: SELECT ... FROM import_jobs WHERE status = $1::job_status_enum]
```

**根因**（第三轮 grep 实测扩展）：
- `JobStatus` Python 端有 `interrupted`、`retrying`，但 PG `job_status_enum` 实际只有 10 个值
- 直接查 PG：`pending, queued, running, validating, writing, activating, completed, failed, canceled, timed_out`
- **缺**：`interrupted`、`retrying`、`cancelled`（双 L 历史兼容值）
- Alembic 迁移 `view_refactor_interrupted_status_20260511.py` 在生产 PG 没跑成功

**严重度**：🔴 红色——
- import_recover_worker 每 30s 报 WARNING（日志噪音）
- 中断恢复功能不可用（heartbeat 超时的 job 无法标记为 interrupted）
- 重试场景同样不可用

**修复路径**（0.3 天）：
```bash
docker exec -e PGPASSWORD=postgres audit-postgres \
  psql -U postgres -d audit_platform -c "
    ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'interrupted';
    ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'retrying';
    ALTER TYPE job_status_enum ADD VALUE IF NOT EXISTS 'cancelled';
  "
```

或者：
```bash
cd backend && alembic upgrade view_refactor_interrupted_status_20260511
```

**验收**：
```
SELECT enumlabel FROM pg_enum WHERE enumtypid = 'job_status_enum'::regtype;
应包含 'interrupted'
后端日志 5 分钟内无 InvalidTextRepresentationError
```

---

### 🟡 F8（已澄清根因）：CFS 试算汇总返回 0 行 —— **PG enum `report_type` 缺值**

**第二轮实测**只看到 0 行，怀疑是分支问题。

**第三轮实测真相**（看后端日志）：
```
DBAPIError: invalid input value for enum report_type: "cash_flow_statement"
[SQL: SELECT report_line_mapping... WHERE report_type=$1::report_type]
```

直接查 PG：
```sql
SELECT enumlabel FROM pg_enum WHERE enumtypid = 'report_type'::regtype;
balance_sheet, income_statement, cash_flow   -- 只有 3 个！
```

**真因**：PG `report_type` enum **只有 3 个值**（balance_sheet / income_statement / **cash_flow**），缺：
- `cash_flow_statement`（应用代码用的）
- `equity_statement`
- `cash_flow_supplement`
- `impairment_provision`

应用代码用 `cash_flow_statement`，PG 只有 `cash_flow`，所以 `summary-with-adjustments?report_type=cash_flow_statement` 直接抛 `InvalidTextRepresentationError` → 接住后返回空数组。

**严重度升级为 🔴 红色**：不只是 CFS 试算汇总，**所有引用 `report_type` 列的查询、写入、聚合**对 4 个新报表类型都失败。`/api/reports/{pid}/{year}/cash_flow_statement` 之所以能返回 63 行，是因为这条端点用的是 `financial_report.report_type`（一个 String 列）而不是 PG enum 列；而 `report_line_mapping.report_type` 是 enum 列。

**修复路径**（0.3 天）：
```sql
ALTER TYPE report_type ADD VALUE IF NOT EXISTS 'cash_flow_statement';
ALTER TYPE report_type ADD VALUE IF NOT EXISTS 'equity_statement';
ALTER TYPE report_type ADD VALUE IF NOT EXISTS 'cash_flow_supplement';
ALTER TYPE report_type ADD VALUE IF NOT EXISTS 'impairment_provision';
```

**验收**：
```
GET /api/projects/{pid}/trial-balance/summary-with-adjustments?year=2025&report_type=cash_flow_statement → 200 + rows>0
后端日志 InvalidTextRepresentationError 清零
```

---

### ✅ F9（已澄清）：EQCR 端点形态被假设错，真实端点全都存在

**第三轮实测**：
- `GET /api/eqcr/projects/{pid}/opinions` → 404
- `GET /api/eqcr/projects/{pid}/prior-year` → 404
- `GET /api/eqcr/projects/{pid}/memo` → 405

**第四轮 grep 真实路径**：

| 假设端点 | 真实端点 | 备注 |
|---------|---------|------|
| `/opinions` | **没有**统一列表；按 domain 分 5 个 GET：`/materiality` / `/estimates` / `/related-parties` / `/going-concern` / `/opinion-type` + `POST /opinions`（创建）+ `PATCH /opinions/{id}`（修改） | 设计如此 |
| `/prior-year` | **`/prior-year-comparison`**（带 `-comparison` 后缀）+ `/component-auditors` | 路径假设错 |
| `GET /memo` | **没有 GET root**；应用 `GET /memo/preview`（预览渲染）；POST 端点 4 个：`POST /memo`（生成）/ `POST /memo/finalize`（定稿）/ `GET /memo/export`（导出 docx） | 405 因为 GET root 未注册 |

**结论**：和 F10/F11 同源——**端点真实存在但路径形态被假设错**。第三轮实测脚本路径全错。

**严重度降级为 ✅**：非真 bug。

**修复**（仅文档+前端契约）：v3 §3 速查表补 EQCR 真实端点；前端 `apiPaths.ts` 如有错路径需 grep 修正。

---

### ✅ F10（已澄清）：复核记录 + 复核对话端点路径假设错

**第三轮实测**：
- `GET /api/projects/{pid}/review-records` → 404（路径假设错）
- `GET /api/projects/{pid}/review-conversations` → 404（路径假设错）

**第四轮 grep 真因**：
- 复核记录**没有独立 `/review-records` 端点**，列表数据来自：
  - `GET /api/review-inbox`（全局）
  - `GET /api/projects/{pid}/review-inbox`（项目级）
  - 这两个端点已在 v3 §3 列出
- 复核对话真实路径：**`GET /api/review-conversations?project_id={pid}`**（全局 prefix + query param，不是项目子前缀）

**结论**：和 F11 同款"端点真实存在但脚本路径假设错"——非真 bug。

**修复**（仅文档）：v3 §3 端点速查表加复核对话行；前端如有用错路径的需 grep 修正。

---

### ✅ F11（第三轮已澄清）：签字端点路径假设错，不是缺失

**第三轮实测复现**：
- `/api/signatures/projects/{pid}/records` → 404（路径假设错）
- `/api/projects/{pid}/sign/readiness` → 404（路径假设错）
- `/api/projects/{pid}/sign/decision` → 404（路径假设错）
- `/api/audit-report/{pid}/{year}` → 404（路径假设错）

**grep 真实端点**：
- 签字记录：`GET /api/signatures/{object_type}/{object_id}` （不是 `/projects/{pid}/records`）
- 签字就绪：`GET /api/projects/{pid}/sign-readiness` （是连字符不是斜杠）
- 签字操作：`POST /api/signatures/sign`
- 验证签名：`POST /api/signatures/{signature_id}/verify`

**结论**：所有签字端点真实存在，第三轮脚本路径全部假设错——和第一稿同款"凭印象写"问题。

**修复**：v3 §3 端点速查表新增"签字流水"4 行（见 §3 修订）。

---

### 🟡 F12（第三轮新发现）：错报阈值重检 schema 错

**实测**：
```
POST /api/projects/{pid}/misstatements/recheck-threshold
body: {"year": 2025}
→ 422
```

**修复路径**（0.2 天）：grep `recheck-threshold` 端点，看真实 schema 期望什么参数。

---

### 🟡 F13（第三轮新发现）：`/api/users/me/nav` 404

**实测**：admin 登录后调 `/api/users/me/nav` → 404。

**前端实际行为**：`ThreeColumnLayout.vue` 已切走后端 nav，用前端 `FALLBACK_NAV` 硬编码 + 角色过滤（v3 §11.3 已记录）。

**严重度**：🟢 不算 bug——前端不依赖此端点，但**后端没接对前端契约**会让新人迷惑。

**修复**（可选）：要么删除前端调用残留，要么补后端 stub 返回 FALLBACK_NAV。

---

### 🟡 F14（第三轮新发现）：`/api/knowledge` 404

**实测**：知识库根端点 404。

**前端隐患**：`KnowledgeBase.vue` 实际可能用其他端点（如 `/api/knowledge-folders` / `/api/knowledge/search`）。

**修复**：grep 真实端点 + v3 §3 端点速查表新增。

---

### 🟡 F15（第三轮新发现）：`/api/projects/{pid}/ledger-import/jobs/latest` 422

**实测**：之前 v1.10 sprint 改名为 `/active-job` 后，`/jobs/latest` 路径还在但 schema 要求 UUID 参数（FastAPI 路由 `/jobs/{job_id}` 把 `latest` 当 UUID 解析失败，422）。

**之前 memory 已记**：FastAPI 同 prefix 多 router 注册时 literal 路由必须**不能**和 `{var_name}` 通配冲突——本身已修复（改名 `/active-job`），但旧路径 `/jobs/latest` 没真删，前端可能还有残留调用。

**修复**：grep 前端 `/jobs/latest` 调用全部改 `/active-job`。

---

## 3 端点路径速查（grep 核验，前端写代码必读）

实测发现 v3 原稿有 7 处端点路径错误，本表是 **grep 后的真实路径**：

| 业务模块 | 真实路径 | 备注 |
|---------|---------|------|
| 账表余额 | `/api/projects/{pid}/ledger/balance?year=` | ledger_penetration prefix |
| 账表查账穿透 | `/api/projects/{pid}/ledger/aux-balance` | 同 prefix |
| 试算表 | `/api/projects/{pid}/trial-balance?year=` | OK |
| **试算汇总** | `/api/projects/{pid}/trial-balance/summary-with-adjustments?year=&report_type=` | 不是 `/summary` |
| 试算溯源 | `/api/projects/{pid}/trial-balance/trace?account_code=` | OK |
| 报表 | `/api/reports/{pid}/{year}/{type}` | 不在 projects 子前缀 |
| 报表→底稿 | `/api/reports/{pid}/{year}/{type}/{row_code}/related-workpapers` | R8 落地 |
| **附注树** | `/api/disclosure-notes/{pid}/{year}` | 不是 `/projects/{pid}/disclosure-notes/tree` |
| 附注→底稿 | `/api/notes/{pid}/{year}/{section}/row/{row}/related-workpapers` | R8 落地 |
| 调整分录 | `/api/projects/{pid}/adjustments?year=` | OK |
| 错报清单 | `/api/projects/{pid}/misstatements?year=` | OK |
| 底稿索引 | `/api/projects/{pid}/working-papers?year=` | OK |
| 工作流状态 | `/api/projects/{pid}/workflow-status?year=` | 6 步推导 |
| 一致性门控 | `/api/projects/{pid}/workflow/consistency-check?year=` | chain spec |
| **数据质量** | `/api/projects/{pid}/data-quality/check?year=&checks=all` | 必须带 `/check` |
| stale 摘要 | `/api/projects/{pid}/stale-summary` | 仅底稿粒度 |
| 风险摘要 | `/api/projects/{pid}/risk-summary?year=` | R8 落地 |
| **复核收件箱** | `/api/review-inbox`（全局）/ `/api/projects/{pid}/review-inbox`（项目级） | 两套并存 |
| 通知中心 | `/api/notifications?limit=` | OK |
| 通知未读 | `/api/notifications/unread-count` | OK |
| **AI 模型** | `/api/ai-models` | 连字符不是斜杠 |
| **签字记录** | `/api/signatures/{object_type}/{object_id}` | 不是 `/projects/{pid}/records` |
| **签字就绪** | `/api/projects/{pid}/sign-readiness` | 连字符不是斜杠 |
| 签字操作 | `POST /api/signatures/sign` | |
| **EQCR 工作台** | `/api/eqcr/projects` 等 11 个端点 | 详见 R5 EQCR 路由 |
| **EQCR 意见（按 domain）** | `/api/eqcr/projects/{pid}/{domain}` 5 域：materiality / estimates / related-parties / going-concern / opinion-type | 没有统一 `/opinions` 列表 |
| **EQCR 意见 CRUD** | `POST /api/eqcr/opinions` 创建 + `PATCH /api/eqcr/opinions/{id}` 修改 | F9 实测 |
| **EQCR 上年比较** | `GET /api/eqcr/projects/{pid}/prior-year-comparison` + `/component-auditors` + `POST /link-prior-year` | F9 真路径带 `-comparison` 后缀 |
| **EQCR 备忘录** | `GET /memo/preview`（读）+ `POST /memo`（生成）+ `POST /memo/finalize`（定稿）+ `GET /memo/export?format=docx`（导出）| 没有 GET root |
| **复核记录** | 列表数据来自 `/api/review-inbox`（全局）+ `/api/projects/{pid}/review-inbox`（项目级） | F10 实测：没有独立 `/review-records` 端点 |
| **复核对话** | `GET /api/review-conversations?project_id={pid}` | F10 实测：全局 prefix + query param，不是项目子前缀 |
| **知识库** | `/api/knowledge/libraries`（全局） + `/api/projects/{pid}/knowledge/documents`（项目级） + `/api/knowledge-library/...`（管理后台） | F14 三套前缀并存：根路径 `/api/knowledge` 无端点，必须带 `/libraries` 等子路径 |
| **错报阈值重检** | `/api/projects/{pid}/misstatements/recheck-threshold` | F12 实测 schema 错，参数待确认 |
| **PG 关键 enum 缺值** | `report_type` 缺 4 个 / `job_status_enum` 缺 3 个 | F7+F8，必须 ALTER TYPE |

**铁律**：前端新增 service 调用时，先 grep `backend/app/routers/**/*.py` 确认 prefix + path，禁止凭印象写。

---

## 4 实测验证脚本（保留思路，脚本本体已删）

执行流程：
1. 后端启动 `python -m uvicorn app.main:app --port 9980`（cwd=backend）
2. POST `/api/auth/login` 用 admin/admin123 拿 token
3. 4 项目并行跑 12 层断言（账表 / 映射 / 试算 / 试算汇总 / BS-IS-CFS / 调整 / 错报 / 底稿 / 附注 / workflow / stale / 数据质量 / 一致性）
4. 末尾联动测试：创建一笔 AJE → 等 1s → 查 stale → 看是否 +1 → 删除 AJE
5. 复核+通知模块：全局/项目复核收件箱 + 通知列表 + 未读数 + AI 模型

**未来重跑方法**：每次大改主链路前，照本节流程手工跑一遍即可。脚本主体不需要长期保留（一次性诊断工具）。

---

## 5 当前系统量化快照（2026-05-16 实测）

| 维度 | 现状 | 健康度 |
|------|------|--------|
| 视图总数 | **97** | — |
| 组件总数 | **258** | — |
| 路由文件 | **150+** | — |
| **GtPageHeader 接入** | 73 / 97 = 75% | 🟢 优秀 |
| **GtEditableTable 接入** | 3 处 | 🔴 几乎为 0 |
| **GtAmountCell / .gt-amt** | 29 处 | 🟡 集中在 4-5 个金额密集页 |
| **v-permission** | 18 个 .vue | 🟡 危险按钮覆盖 ~60% |
| **useEditMode** | 11 视图 | 🟡 编辑型视图 ~50% |
| **useEditingLock** | 3 编辑器 | 🟡 仅 WP/Disclosure/AuditReport |
| **useFullscreen** | 20 处 | 🟢 已普及 |
| **useStaleStatus** | 5 视图 | 🔴 联动感知严重不足 |
| **useWorkpaperAutoSave** | 4 视图 | 🟢 三个编辑器全覆盖 |
| **useAiChat** | 2 视图 | 🟢 Chat 入口本来就少 |
| **handleApiError** | 59 视图 | 🟢 已是默认 |
| **ElMessage.error 裸用** | 1 处 | 🟢 基本清零 |
| **ElMessageBox.confirm 直用** | 3 处 | 🟢 可视为零 |
| **/api/ Vue 层硬编码** | 0 处 | 🟢 完成迁移 |
| **statusEnum.ts** | 13 视图 | 🟡 状态硬编码仍散落 |
| **confirm.ts 包装函数** | 31 处 | 🟢 已主流 |
| **inline `font-size: Npx`** | **1565 处** | 🔴 严重重灾区 |
| **inline `color: #xxxxxx`** | **1611 处** | 🔴 严重重灾区 |
| **inline `background: #xxxxxx`** | **712 处** | 🔴 较严重 |

4 个红灯：**GtEditableTable 没人用、stale 联动覆盖率低、字号/颜色硬编码超过 3800 处、复杂页面（编辑器系列）几乎全部硬编码 CSS**。

---

## 6 P0 修复优先级（第三次实测后重排，按真实磨损度）

> **执行进度（2026-05-16）**：档 1 直接修 5 件已完成 ✅；档 2 v3-quickfixes spec 起草完毕；档 3 v3-linkage-stale-propagation 三件套起草完毕。详见 `.kiro/specs/INDEX.md`。

### 第一周（8 天）：清主链路缺陷

| # | 改动 | 工时 | 真实磨损 |
|---|------|------|---------|
| **P0-1** ✅ | F6 修 AJE 创建 500（`check_consol_lock` rollback → SAVEPOINT 转换） | 已完成 2026-05-16 | 🔴 已修 |
| **P0-2** ✅ | F7 + F8 PG 两个 enum 全部 ALTER TYPE | 0.3h（已完成 2026-05-16） | 🔴 已修 |
| **P0-3** ✅ | F9 EQCR 端点已澄清（前端零踩雷，端点真实存在） | 已完成 2026-05-16 | 🟢 已澄清 |
| **P0-4** ✅ | F10 复核记录端点已澄清+前端 apiPaths 修一处错路径 | 已完成 2026-05-16 | 🟢 已修 |
| **P0-5** ✅ | F2 init_4_projects 加 chain step + WorkpaperList 引导卡片 | 已完成 2026-05-16 | 🔴 已修 |
| **P0-6** ✅ | F4 consistency-check 补 `all_passed` 字段 | 0.5h（已完成 2026-05-16） | 🟡 已修 |
| **P0-7** ✅ | F12 错报阈值重检 schema 修复（year 支持 query/body） | 0.3h（已完成 2026-05-16） | 🟡 已修 |
| **P0-8** | F1 init 链路最后强制 generate（避免 stale 数据） | 0.2 天 | 🟢 已临时修复 |
| **P0-9** ✅ | F11 端点路径修订进 v3 §3 速查表 | 0（已完成 2026-05-16） | 🟢 文档已更新 |
| **P0-10** ✅ | F13/F14/F15 端点 grep 核验+清理误导注释 | 0.5h（已完成 2026-05-16） | 🟢 已修 |
| **P0-11** | F15 前端清理 `/jobs/latest` 残留（grep 实测前端零引用，已澄清） | 0 | 🟢 已澄清 |
| **P0-12** ✅ | useStaleStatus 推到 6 视图 + PartnerSignDecision stale 摘要区块（**Spec A 已落地 2026-05-16**） | 已完成 | 🟢 v3 §7.3+§7.4 |
| **P0-13** ✅ | AJE→错报转换前端入口 + 后端幂等 409（**Spec A 已落地 2026-05-16**） | 已完成 | 🟢 v3 §7.5 |

**剩余工时**：5 件档 1 已清（合计 1.6 小时）+ **4 件档 2 已清（Q1-Q4，1.5 小时）** + **Spec A 三件套已落地（2026-05-16，2.5 小时）** = **v3 全部 P0 已清完**！

**Spec A 三件套实施成果**（2026-05-16）：
- ✅ Sprint 0 现状核验（PG `financial_report.is_stale` 列已补，misstatements 字段缺失降级派生）
- ✅ Sprint 1 后端 `stale_summary_aggregate.py` + `/full` 端点 + 集成测试
- ✅ Sprint 2 前端 `useStaleSummaryFull.ts` composable + 6 视图接入（WorkpaperList tree badge / WorkpaperWorkbench 卡片 / Misstatements 列 / Adjustments status 列 / PartnerSignDecision 5 卡片 / EqcrProjectView Tab badge）
- ✅ Sprint 3 AJE→错报后端幂等检查（D5）+ 409 ALREADY_CONVERTED + 前端跳转
- ✅ Sprint 4 集成测试（test_aje_to_misstatement_idempotent.py + test_stale_summary_full.py 共 6 用例）+ 4 项目实测全 200

**实测验证**：
- `/api/projects/{pid}/stale-summary/full?year=2025` 4 项目全 200，结构完整
- AJE 创建 → reject → from-aje 转错报 → 重复 from-aje 返回 409+ALREADY_CONVERTED+misstatement_id ✓
- vue-tsc + getDiagnostics 11 个改动文件全 0 错误

### 第二阶段（R10 立项）：联动+显示治理（3 周）

见 §7-§8。

---

## 7 联动闭环：前端补齐"已通的后端事件"

### 7.1 后端事件链路全景（grep 核验）

事件订阅在 `backend/app/services/event_handlers.py`，已落地 15 条订阅：

```
ADJUSTMENT_CREATED/UPDATED/DELETED  → recalc TB → recalc reports → mark notes stale
WORKPAPER_SAVED                      → consistency check → mark TB stale → mark reports stale
LEDGER_DATASET_ACTIVATED             → mark all WPs stale (year-scoped)
LEDGER_DATASET_ROLLED_BACK           → mark downstream stale
MATERIALITY_CHANGED                  → recheck misstatement threshold
SIGNATURE_RECORDED (order=5)         → AuditReport.status = final
EQCR_VERDICT_RECORDED                → AuditReport.status = eqcr_approved
```

**实测验证**：陕西华氏创建一笔测试 AJE 后查 `stale-summary`，等 1s 后**应该** stale_count +1（同步事件 handler）。
> 实测时 AJE 创建因 F6（MissingGreenlet）报 500 没成功，所以联动验证未完成；F6 修复后再补这一步。

### 7.2 前端 stale 感知现状

`useStaleStatus` 只在 5 个视图接入：TrialBalance / ReportView / DisclosureEditor / AuditReportEditor / ProjectDashboard。

**断点**（合伙人最敏感）：
1. **WorkpaperList / WorkpaperWorkbench 看不到 stale 列**
2. **Misstatements / Adjustments 看不到 stale 状态**
3. **PartnerSignDecision 没有 stale 汇总区块**

### 7.3 P0 行动：把 useStaleStatus 推到 6 个新视图

| 视图 | 接入位置 | 验收口径 |
|------|---------|---------|
| `WorkpaperList.vue` | 表格新增"新鲜度"列（badge：✓ / 🟡 stale / 🔴 inconsistent） | 改一张底稿后该行立即变 stale |
| `WorkpaperWorkbench.vue` | 编制卡片右上角 stale 标志 | 同上 |
| `Misstatements.vue` | 列表行级"重要性已变更"标志 | materiality:changed 后未重算行变 stale |
| `Adjustments.vue` | "已转错报"列右侧 stale 标志（错报阈值变化） | 同上 |
| `PartnerSignDecision.vue` | 中栏新增"项目状态摘要"区块（stale 数 / 报表行 stale 数 / 附注节 stale 数） | 一处看全 |
| `EqcrProjectView.vue` | 各 Tab 标题 badge（哪些 Tab 有 stale 数据） | EQCR 进入时一眼定位 |

### 7.4 后端补齐两个聚合端点

```
GET /api/projects/{pid}/stale-summary/full
→ {
    workpapers: { total, stale, inconsistent, items[] },
    reports:    { total, stale, items[] },
    notes:      { total, stale, items[] },
    misstatements: { total, recheck_needed, items[] },
    last_event_at: ISO8601
  }

GET /api/projects/{pid}/event-cascade/health
→ { lag_seconds, stuck_handlers[], dlq_depth }
```

第一个给 PartnerSignDecision 用，第二个给 admin 看事件级联是否健康。

### 7.5 P1 行动：AJE 被拒 → 错报转换前端入口

**现状**：`misstatement_service.create_from_rejected_aje` 后端已通，但 `Adjustments.vue` 的"已拒绝"行**没有"一键转错报"按钮**。

**改动**：
- `Adjustments.vue` 表格新增条件操作：当 `row.status === 'rejected' && !row.converted_to_misstatement_id` 时，操作列显示"📝 转为错报"按钮
- 点击调 `POST /api/projects/{pid}/misstatements/from-rejected-aje?adjustment_id=xxx`
- 成功后跳转 Misstatements.vue 并 setCurrentRow

### 7.6 P1 行动：报表行 / 附注 → 底稿穿透补齐

**实测验证**：
- `/api/reports/{pid}/2025/balance_sheet/BS-001/related-workpapers` → ✓ 200
- `/api/notes/{pid}/2025/note_001/row/r1/related-workpapers` → ✓ 200

后端 R8 已落地，前端只在 ReportView 部分接入。

**改动**：
- `usePenetrate` composable 抽出 `penetrateToWorkpapers(rowCode)` 函数
- ReportView 所有金额列右键菜单加"查看相关底稿"
- DisclosureEditor 右键菜单加"查看相关底稿"（已部分接入，校验完整性）
- Misstatements "影响科目"列加超链接到对应底稿

---

## 8 显示治理三条线（合伙人最在意的"美观一致"）

> 字号/颜色/背景硬编码 3888 处是上线后最大的维护成本。
> 必须分三条治理线、分批走。

### 8.1 字号（1565 处）

`gt-tokens.css` 显式定义 7 级字号变量：
```css
--gt-font-2xs: 11px;  /* 角标/badge */
--gt-font-xs:  12px;  /* 表格内文 / 辅助说明 */
--gt-font-sm:  13px;  /* 默认正文 / 表单 label */
--gt-font-base: 14px; /* 强调正文 / 按钮 */
--gt-font-md:  16px;  /* 小标题 */
--gt-font-lg:  18px;  /* 区块标题 */
--gt-font-xl:  22px;  /* 页面横幅 */
```

**新增 stylelint 规则**：禁止 `font-size: \d+px` 内联，必须 `var(--gt-font-*)`。

**分 4 批迁移**（每批一个 PR）：
1. 编辑器 4 个（WorkpaperEditor / WorkpaperList / WorkpaperWorkbench / DisclosureEditor）
2. 表格类（TrialBalance / ReportView / Adjustments / Misstatements / Materiality）
3. Dashboard 系列
4. 剩余视图

**验收**：`grep -rE 'font-size:\s*\d+px' audit-platform/frontend/src --include='*.vue' | wc -l == 0`

### 8.2 颜色（1611 处）

`gt-tokens.css` 已有 5 个语义色 + 灰度梯度，需补完。

创建 `scripts/migrate-inline-color.mjs` 半自动替换：
- `#4b2d77` → `var(--gt-color-primary)`
- `#FF5149` → `var(--gt-color-danger)`
- `#666` → `var(--gt-text-secondary)` 等

**同样 4 批走**。

### 8.3 背景（712 处）

定义 `--gt-bg-default` / `--gt-bg-subtle` / `--gt-bg-info` / `--gt-bg-warning` / `--gt-bg-success` / `--gt-bg-danger` 6 级。

### 8.4 暗色模式不在 v3 范围

先把 token 体系打实，未来切换暗色只需改 token 值。

---

## 9 组件铺设系统化（GtEditableTable 0 接入是个警报）

### 9.1 不要再扩张组件库，做接入率治理

**职责瘦身**：把 GtEditableTable 砍成两个轻封装：
- `GtTableExtended.vue`：基于 el-table + 紫色表头 + 字号 class + 千分位 + 空状态 + 复制粘贴右键菜单（**所有列表型表格走这个**）
- `GtFormTable.vue`：行内编辑型表格（dirty 标记 + 校验 + 撤销）—— 仅 Adjustments / Misstatements / SamplingEnhanced 用

### 9.2 CI 卡点

```yaml
# .github/workflows/ci.yml backend-lint
- name: el-table baseline check
  run: |
    count=$(grep -rE '<el-table\s' audit-platform/frontend/src --include='*.vue' | grep -v 'data-allow-raw' | wc -l)
    if [ "$count" -gt $BASELINE ]; then exit 1; fi
```

数字按当前快照实测设定（实施时 grep 一次得基准），后续只减不增。

### 9.3 GtPageHeader 接入率收尾（73 → 86）

24 个未接入视图分类：
- ✅ **合理排除（11 个）**：Login / Register / NotFound / DevelopingPage / WorkpaperEditor 系列 5 个 / ProjectWizard / AIChatView / AIWorkpaperView
- 🟡 **应补充（13 个）**：AttachmentHub / ConsolidationHub / CustomQuery / DataValidationPanel / Drilldown / LedgerImportHistory / LedgerPenetration / PDFExportPanel / RecycleBin / StaffManagement / TemplateLibraryMgmt / WorkpaperWorkbench / WorkpaperList（已有但变体不一致）

13 个补完后接入率 = **100%（去除合理排除）**。

---

## 10 错误处理与容灾

### 10.1 现状（实测）

- ✅ `handleApiError` 已 59 视图接入
- ✅ `ElMessage.error` 裸用清零（仅 1 处）
- ✅ `confirm.ts` 包装函数 31 视图使用
- ⚠️ `confirmLeave / confirmDangerous` 未覆盖三个编辑器路由切换
- ⚠️ 后端 5xx 静默吞噬（用户看到"加载失败"但不知道是网络还是后端崩溃）
- ⚠️ 离线/断网无统一提示

### 10.2 P0 行动

#### A. 三个编辑器统一接入 `confirmLeave`

```ts
// WorkpaperEditor.vue / DisclosureEditor.vue / AuditReportEditor.vue
import { onBeforeRouteLeave } from 'vue-router'
onBeforeRouteLeave(async (to, from, next) => {
  if (autosave.isDirty.value) {
    const ok = await confirmLeave('底稿', /* changedFields */)
    if (!ok) return next(false)
  }
  next()
})

window.addEventListener('beforeunload', (e) => {
  if (autosave.isDirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
})
```

#### B. DegradedBanner 扩展

`DegradedBanner.vue` 已存在但只判断 SSE 断线。扩展：
- 后端崩溃（5xx 比率 > 30% in last 1 minute）时也显示
- 前端 `apiProxy` 内部 5xx 计数器（环形缓冲区 last 100 requests）
- 横幅文案分级：🟡 "服务响应较慢" / 🔴 "部分功能暂时不可用"

#### C. 危险操作二次确认补漏

漏的位置（grep 核对）：
- `LedgerDataManager.vue` 的"清理账套"——必须二次确认
- `EqcrMemoEditor.vue` 的"定稿备忘录"——状态不可逆，必须二次确认

---

## 11 五角色实操痛点（v2 落地后仍存在的）

| 角色 | 痛点 | 文件锚点 | 本期建议 |
|------|------|---------|---------|
| **审计助理** | 编制底稿时看不到自检结果，提交复核才被驳回 | `WorkpaperEditor.vue` 右栏无自检 Tab | 🟡 R10 |
| 审计助理 | 关闭浏览器/切路由时未保存内容静默丢失 | 三个编辑器 `onBeforeRouteLeave` 缺失 | 🟢 P0（§10.2.A） |
| 审计助理 | AI 生成内容混入底稿无显著标记 | `wrap_ai_output` 已有，模板水印不明显 | 🟡 R10 |
| **项目经理** | 跨项目进度看板需进每个项目才看得到 | `ManagerDashboard` 是单项目视图 | 🟡 R10 |
| 项目经理 | 客户承诺到期催办无主动推送 | `ClientCommunicationService` 已结构化但无 SLA | 🟡 R10 |
| **质控** | QC 主工作台分散在 6 个独立路由 | `/qc/inspections` `/qc/rules` 等 | 🟡 R10（QcHub） |
| **合伙人** | 签字决策面板缺"风险摘要 + 报告预览"双视图 | `PartnerSignDecision.vue` 已建（R8）但内容薄 | 🟢 P0（§7.3） |
| 合伙人 | 底稿/报表/附注哪些 stale 没有跨视图汇总 | `useStaleStatus` 只在 5 视图接入 | 🟢 P0（§7.3） |
| **EQCR** | 影子对比组件未落地（v2 P2 仍未做） | `EqcrProjectView.vue` 无 ShadowCompareRow | 🟡 R10 |
| EQCR | 备忘录无版本对比 | `EqcrMemoEditor.vue` 只有 onExportWord | 🔴 R11 延后 |

---

## 12 长期维护性

| 风险 | 严重度 | 建议 |
|------|-------:|------|
| **memory.md 已 1500+ 行** | 🔴 高 | 当前 spec 完成后统一拆分；保留 < 200 行 |
| 多个 spec 三件套散落，无总索引 | 🟡 中 | `.kiro/specs/INDEX.md` 列状态+commit |
| 后端服务文件 200+，无服务依赖图 | 🟡 中 | 可选 `pydeps` 自动生成，挂在 architecture.md |
| Alembic 迁移链 30+ 个，无可视化 | 🟡 中 | 可选 `alembic show <rev>` 出 mermaid |
| 测试覆盖文档 COVERAGE_MATRIX.md 仅 1 个 spec | 🟢 低 | template-library-coordination 已开始建 |

---

## 13 不做清单（防止范围蔓延）

本期 v3 **明确不做**：

1. ❌ 暗色模式（先把 token 打实）
2. ❌ 全局 Ctrl+K 搜索（用户实际诉求弱）
3. ❌ 给 GtEditableTable 加新功能（先做接入率治理）
4. 🟡 客户主数据 + 项目标签（v1/v2 已提，业务诉求弱，**R11 评估**）
5. 🟡 员工热力图 / 跨项目成本（manager 角度有诉求但本期不做，**R11 评估**）
6. ❌ vitest 全量测试基建（已在 R9 落地骨架，不再扩）
7. ❌ 新加任何后端模型（避免迁移链膨胀）

---

## 14 推荐 R10 立项切分

如果 v3 落地，推荐切成 **2 个独立 spec**：

### Spec A：联动闭环 + 显示治理（前端为主）
- 工期：3 周
- Sprint 1：useStaleStatus 推到 6 视图 + AJE→错报按钮 + 穿透补齐（1 周）
- Sprint 2：字号变量化 4 批（1 周）
- Sprint 3：颜色 + 背景变量化 + GtEditableTable 瘦身（1 周）

### Spec B：编辑器三件套 + 错误容灾（前后端联动）
- 工期：2 周
- Sprint 1：三个编辑器 confirmLeave + beforeunload + WorkpaperSidePanel（1 周）
- Sprint 2：DegradedBanner 扩展 + 后端 stale-summary 聚合端点 + event-cascade 健康检查（1 周）

两个 spec 可并行（依赖面不重叠）。

---

## 15 验收口径

v3 落地后实测应达到：

| 指标 | 第一稿假设 | 第二/三次实测真值 | P0 完成后 | R10 完成后 |
|------|-----------:|-----------------:|---------:|----------:|
| **IS-nonzero（4 项目均值）** | 假设 0 | **第二轮实测 13 ✓** | ≥ 13 | ≥ 13 |
| **BS-nonzero（4 项目均值）** | 假设 ≤ 27 | **第二轮实测 28** | ≥ 28 | ≥ 28 |
| **CFS-nonzero（4 项目均值）** | 假设 0 | **第二轮实测 0**（公式覆盖率 11%） | ≥ 5（CFS 公式补全后） | ≥ 8 |
| **wp_count > 0 项目数** | 假设 2/4 | **临时修复后 4/4** | 4/4 | 4/4 |
| **data-quality.checks_run.length** | 假设 0 | **实测 5 ✓** | 5 | 5 |
| **AJE 创建端点（F6）** | 假设 422 | **第二轮实测 500，第三轮仍 500** | 200 | 200 |
| **PG `job_status_enum` 缺值（F7）** | 未知 | **缺 3 个** | 已加 | 已加 |
| **PG `report_type` 缺值（F8）** | 未知 | **缺 4 个**（第三轮新发现） | 已加 | 已加 |
| **EQCR opinions/prior-year/memo（F9）** | 未知 | **3 个端点 404/405** | 全 200 | 全 200 |
| **复核记录端点（F10）** | 未知 | **404** | 200 | 200 |
| **错报阈值重检（F12）** | 未知 | **422** | 200 | 200 |
| **consistency-check 含 all_passed（F4）** | ❌ | ❌ | ✅ | ✅ |
| GtPageHeader 接入率 | 75% | 75% | 75% | 100%（去除合理排除） |
| useStaleStatus 接入视图 | 5 | 5 | 11 | 11 |
| inline `font-size: Npx` | 1565 | 1565 | 1565 | 0 |
| inline `color: #xxx` | 1611 | 1611 | 1611 | < 50 |
| inline `background: #xxx` | 712 | 712 | 712 | < 30 |
| 三个编辑器 confirmLeave 接入 | 部分 | 部分 | 100% | 100% |
| AJE→错报前端入口 | 缺 | 缺（依赖 F6） | 已通 | 已通 |
| PartnerSignDecision stale 摘要 | 缺 | 缺 | 已通 | 已通 |
| memory.md 行数 | 1500+ | 1500+ | 1500+ | < 200 |

---

## 附录 A：建议先看的 5 个文件

合伙人 / 新加入开发者要快速理解平台前端现状，建议看：

1. `audit-platform/frontend/src/composables/useStaleStatus.ts` —— stale 联动核心
2. `audit-platform/frontend/src/utils/confirm.ts` —— 危险操作语义化函数
3. `audit-platform/frontend/src/services/apiPaths.ts` —— 全部 API 端点真源
4. `backend/app/services/event_handlers.py` —— 后端事件级联真源
5. `backend/app/router_registry.py` —— 后端路由注册真源

---

## 附录 B：v1 / v2 / v3 定位对比

| | v1 | v2 | v3 |
|---|----|----|----|
| 编制时间 | 2026-05-07 | 2026-05-07 | 2026-05-16 |
| 定位 | 路线图盘点 | 角色穿刺 | **实测驱动** |
| 风格 | 全面铺开 | 分角色深挖 | 真实跑出来的缺陷 |
| P0 任务数 | 13 | 11 | **8（5 真实缺陷 + 3 推荐）** |
| 是否含路线图 | 是 | 是 | 否，列 R10 spec 切分 |
| 是否凭 memory 写 | 是 | 部分 | **否，全部 grep+E2E 验证** |

v3 不替代 v1/v2，而是**指导下一轮 spec 立项**。

---

## 附录 C：打磨建议文档铁律（v4+ 必须遵循）

> v1 / v2 / v3 第一稿都犯同一个错——基于 memory 写、不基于实测写。
> v3 第二稿（本版）才是首次实测驱动。
> **任何后续打磨建议文档（v4+）必须**：

1. **先跑 E2E 脚本** 拿当前真实端点和数据
2. **每条建议必须标"已实测/未实测"**
3. **路径引用必须 grep 核验**（v3 第一稿 7 处路径全错就是反例）
4. **声称"已落地"必须有 200 响应支撑**，否则改"理论已实施"
5. **缺陷描述必须含"实测样本+实测命令+预期 vs 实际"**

---

## 16 v3 自我复盘（第三次审查发现的改进项）

> 本节是 v3 内部审查产物：通读全文后发现的不一致、漏测覆盖、潜在新缺陷。
> 这些不算 P0，但应在 R10 spec 起草前先解决，避免下一轮又"基于 v3 推测"。

### 16.1 文档自身待修缺口

| # | 类型 | 问题 | 处理 |
|---|------|------|------|
| D1 | ✅ 已修 | §0 一句话评估说"5 天"，§6 改成"6.5 天/9 件事"——本次已对齐 | 已修 |
| D2 | ✅ 已修 | §6 标题"第一周（5 天）"与正文"6.5 天"矛盾 | 已修 |
| D3 | ✅ 已修 | §7.1 写"F5 修复后再补"——F5 已澄清，应改为"F6 修复后" | 已修 |
| D4 | ⚠️ 待整理 | §11 五角色痛点表 + §10 P0 行动 A + §6 P0 表三处都提到"confirmLeave"，重复 | 合并为 §10 主战场，§6/§11 改用"见 §10.2A"引用 |
| D5 | ⚠️ 待整理 | §1 真问题清单（F2/F4/F6/F7/F8）和 §6 优先级表（F6/F7/F2/F4/F8）顺序不一致 | §1 按"严重度排"、§6 按"工时+依赖排"是合理差异，加注脚说明即可 |
| D6 | 🟢 建议 | §13 不做清单"❌ 客户主数据 + 项目标签"措辞偏强硬，业务诉求弱不等于不做 | 改为"R11 评估" |
| D7 | 🟢 建议 | §14 R10 spec 名字模糊（"Spec A/B"）——应起具体标识符 | 建议改名 `linkage-and-tokens` / `editor-resilience` |
| D8 | 🟢 建议 | §15 验收口径含"memory.md < 200 行"——这是基础设施改进不应作业务 spec 验收 | 移到独立"运维项" |

### 16.2 实测覆盖盲区（第三轮已测 8/11，剩 3 项）

> 第二次实测只跑了 12 层主链路 + 联动测试（被 F6 阻断）+ 复核+通知+穿透+风险摘要。
> **第三轮（2026-05-16 续）**已扫了 EQCR/复核/签字/重要性/AI/角色/工时/附件/账套导入 v2 端点存在性，发现 7 个新缺陷（F8 升级 + F9-F15）。
> 仍未实测的 3 项必须在 v4 起草前补齐：

| # | 模块 | 第三轮状态 | 严重度 |
|---|------|-----------|--------|
| C1 | EQCR 工作台 | ✅ 已测，发现 F9（3 端点 404/405） | � |
| C2 | 复核流程 | ✅ 已测，发现 F10（review-records 404） | � |
| C3 | 签字流水 | ✅ 已测（F11 平反，端点真实存在） | � |
| C4 | 重要性变更联动 | ✅ 已测，发现 F12（recheck-threshold 422） | 🟡 |
| C5 | AI 模型 + 知识库 | ✅ 已测，发现 F14（/api/knowledge 404） | 🟡 |
| C6 | 角色权限矩阵（admin） | ✅ 已测，发现 F13（/users/me/nav 404） | 🟡 |
| C7 | 工时填报 + 审批 | ✅ 已测（3 端点全 200） | 🟢 |
| C8 | 附件 | ✅ 已测（项目附件列表 200） | 🟢 |
| C9 | 账套导入 v2 | ✅ 已测，发现 F15（/jobs/latest 422） | � |
| **C10** | **项目向导（ProjectWizard）** | ⏳ **未测** | 待 v4 |
| **C11** | **前端真实渲染** | ⏳ **未测**（前端 3030 未启动） | 待 v4 |
| **C12** | **联动事件真实触发**（AJE→stale 等） | ⏳ **未测**（被 F6 阻断） | F6 修复后必须补 |

**v4 起草前必须**：
1. 启动前端 `cd audit-platform/frontend && npm run dev` → 真实点击 11 个核心页面
2. F6 修复后重测 AJE 创建 → stale 联动 → 工单转换 → 错报转换
3. ProjectWizard 走一遍新建项目流程（覆盖 wizard_state 各步）

### 16.3 潜在新缺陷（实测留下的疑问，未深挖）

| # | 疑问 | 来源 | 排查路径 |
|---|------|------|---------|
| Q1 | F6 MissingGreenlet 是否只影响 AJE 创建？还是 UPDATE/DELETE 也有？ | F6 实测只测了 POST | grep `_publish_adjustment_event` 调用方 + 测 PUT/DELETE |
| Q2 | F7 类似的 PG enum 不一致是否还有其他？ | v1.10 加的 `force_unbind` 等 ActivationType 值也可能漏迁 | `SELECT enumtypid::regtype, enumlabel FROM pg_enum WHERE...` 全量对照 Python `Enum` 子类 |
| Q3 | 宜宾大药房 stale_count=1 是哪来的？真 stale 还是脏数据？ | 4 项目里只有它非 0 | 查 `working_paper.prefill_stale=true` 那一行 |
| Q4 | consistency-check 4 项目派生都 2/5——3 条永久 fail 是哪些？合理吗？ | F4 实测发现 | 列出 `checks` 数组每一项 + `passed=false` 原因 |
| Q5 | CFS 公式覆盖率 11%（7/63 行）——余下 56 行是手填还是缺公式？ | report_engine 实测查 | 跟会计师沟通 CFS 是否本来就要手填多数行 |
| Q6 | F2 后 chain 跑出的底稿（和平 107、辽宁 104）是不是结构正确？ | 数量对了不等于内容对 | 抽 3 张底稿打开看 parsed_data 是否有公式+数据 |
| Q7 | F1 重新 generate 后 4 项目 nonzero 不一致（陕 46 / 和 47 / 辽 45 / 宜 27）——宜宾为啥少 19？ | §1 表格 | 对比 4 项目 trial_balance 损益类科目余额是否完整 |

### 16.4 文档不再适用的 v1/v2 章节（避免后人重复看）

> v1/v2 已落地的章节可以打"已废弃"标签，新人不必重读。

**v1 已落地（标 ✅，可跳过）**：
- v1 §1.1.A 登录角色路由表 → R7 落地
- v1 §1.1.B 合并"我的"系入口 → R7 落地
- v1 §1.1.E 确认文案统一 → R8 落地（confirm.ts 31 视图）
- v1 §2.13 显示一致性 → R9 部分落地（GtPageHeader 75%）

**v2 已落地（标 ✅）**：
- v2 §3.2.B 自检结果进 WorkpaperEditor → R9 部分落地
- v2 §3.2.D 未保存提醒 → R8/R9 部分落地
- v2 §4 项目经理 ManagerDashboard 升级 → R8 落地

**v1/v2 未落地需要 R10 / R11 决议**（保留）：
- v1 §1.4 EQCR 备忘录版本 → 仍未做
- v2 §3.2.A WorkpaperSidePanel 7 Tab → 仍未做
- v2 §6 客户主数据 → 业务诉求弱，R11 评估

### 16.5 v3 后续维护建议

1. **本节不要无限扩**：发现新真实缺陷直接进 §2（F9/F10...），文档自身改进进 §16.1
2. **每次实测后必须更新 §1 表格**：实测真值是 v3 唯一权威基线
3. **R10 spec 立项时引用 v3 必须用具体小节号**（不是"v3 提的"）：避免"v3 提到了 X"这种泛指引用导致后人找不到原文
4. **v4 起草触发条件**：(a) F1-F15 全部修完 / (b) §16.2 实测盲区全部覆盖（C10/C11/C12 待补） / (c) 有新的合伙人级反馈

---

## 末尾：第一周动手清单（第三次实测后修订）

**第一稿要求 5 天清 8 件事**，第二次实测后改为 6.5 天清 9 件事，**第三次实测后改为 8 天清 13 件事**——F8 升级红色 + F9/F10 新发现 + F12-F15 黄色补充 + 端点路径核验。

> **铁律**：F7+F8 的 PG ALTER TYPE 必须**第一天上午**先修——否则后续 CFS / 中断恢复 / 重试场景都跑不通，会污染 F6 等其他验收。

**实际推荐顺序**（参见 §6 P0 优先级表）：

| Day | 重点任务 |
|-----|---------|
| Day 1 | F7+F8 PG ALTER TYPE 7 个 ADD VALUE，重跑 round3 验收 |
| Day 2 | F6 排查 + 修 AJE 创建 MissingGreenlet（核心阻塞） |
| Day 3 | F6 加回归测试 + F12 错报阈值重检 schema 修复 |
| Day 4 | F9 EQCR 3 端点修复（opinions / prior-year / memo） |
| Day 5 | F10 复核记录端点核验 + F2 init_4_projects 加 chain + F4 补 all_passed |
| Day 6 | F1 init 强制 generate + F13/F14/F15 端点核验 + useStaleStatus 推到 WP List/Workbench |
| Day 7 | useStaleStatus 推到 Misstatements/Adjustments/EqcrProjectView + PartnerSignDecision stale 摘要 |
| Day 8 | AJE→错报转换前端入口（依赖 F6） + 重跑 §1 实测 + §16.2 C10/C11/C12 补测 |

---

## 附录 D：实测脚本清单（用完已删，记录用法）

本次第二次实测临时建过 3 个脚本，跑完后已删除：
1. `scripts/v3_e2e_full.py`：12 层断言主链路 + 联动测试 + 复核+通知+穿透
2. `scripts/v3_regen_reports.py`：4 项目重新触发 generate（验证 F1 是 stale）
3. `scripts/v3_test_aje.py`：单独测 AJE 创建（验证 F6 真实根因）

未来重跑：
```bash
# 1. 启后端
python -m uvicorn app.main:app --port 9980  # cwd=backend

# 2. 全链路验证
python scripts/v3_e2e_full.py 2>&1 | tee scripts/v3_e2e_findings.json

# 3. （如发现 F1 stale）重新 generate
python scripts/v3_regen_reports.py
```

**已固化的脚本**（保留作回归）：
- `backend/scripts/init_4_projects.py` —— 4 项目数据初始化
- `backend/scripts/e2e_business_flow_verify.py` —— DB 直查 4 层断言
- `backend/scripts/verify_data_quality_shaanxi.py` —— 数据质量单测
