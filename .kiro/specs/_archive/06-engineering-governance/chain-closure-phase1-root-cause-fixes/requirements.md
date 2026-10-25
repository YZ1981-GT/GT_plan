# 需求：四表→公式→底稿→报表→附注 全链条闭环 · 阶段一（四个一行级根因）

## 背景

用户诉求（2026-09-28）：四表库数据入库后自动刷新到试算表未审数 / 底稿明细表与披露表 / 审定表；
项目组确认调整分录后自动推送到底稿审定表与披露表 / 报表审定数 / 试算表审计调整 / 调整分录大厅；
披露表按国企或上市推送到附注科目数据。全部经公式管理模块驱动。**本 spec 只做第一步的四个根因**。

## 实测基线（2026-09-28 真实环境，project `0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49` / 科目 1122）

场地事实：`重药控股安徽有限公司_2025`，`template_type='listed'`、`report_scope='standalone'`、
`audit_period_end IS NULL`；`trial_balance` year=2025 company_code='001' 196 行（48 行非零）；
migration 166 applied / 0 failures / schema_drift critical=0。

逐段实测判定（含变异证明，测后真库已复原）：

| 段 | 判定 | 实测证据 |
|---|---|---|
| ① 四表→试算表未审数 | 绿 | `tb_balance` level1 期末 624025343.06 与 `unadjusted_amount` 逐值相等；子科目 620065140.15+792059.83+3168143.08 闭合 |
| ⑧ 调整分录→TB 审计调整 | 绿 | aje 归零后经 HTTP 审批 t+1.5s 自动恢复 +100000；借/贷方类方向均正确；`audited=未审+aje+rje` 不变式成立 |
| ⑨ →调整分录大厅 | 绿 | summary 0 笔→1 笔、借贷各 100000，列表出现 AJE-018 |
| ②③④ 四表→底稿三表 | 红 | 仅 `workpaper:{cycle}` 一条支路通（D 产 139 单元）；report/note/adjudication 三 scope 全 affected=0 |
| ⑤⑥ 调整→底稿审定/披露 | 红 | 340 份底稿 `parsed_data` 哈希全等，零数值推送 |
| ⑦ →报表审定数 | 红 | 报表停在 2026-07-29 旧快照且 `is_stale=False`（静默陈旧） |
| ⑩ 披露表→附注 | 红 | 335 行仅 28 行同步过，且 28/28 全被标过期 |

## 本 spec 范围：四个一行级根因

### R1 全局刷新门禁在真实环境无人可达
`POST /api/workpapers/draft-refresh` 用 `require_role(["partner","signing_partner"])`，
`deps.py:155` 严格比对 `current_user.role.value`，**admin 无后门**。
实测：全库 61 个活跃用户只有 `auditor`(53) + `admin`(8)，**零 partner/signing_partner**；
admin 调用实测 `HTTP 403 {"code":403,"message":"权限不足"}`。
⇒ 整条自动刷新链在真实环境从未被触发过的第一因。

### R2 report scope 的 page_keys 是永不命中的通配符
`draft_refresh_orchestrator._dispatch_via_coordinator` 内 `page_keys.append("report:*")` 写死，
而预设库实际是 7 个具体键：`report:balance_sheet` / `income_statement` / `cash_flow_statement` /
`equity_statement` / `cash_flow_supplement` / `impairment_provision` / `cross_check`。
实测 `"report:*" in preset_index` → **False**；该 scope `preset_count=0`。
⇒ 锁死 **343 条**报表域预设公式。

### R3 报表增量重算因默认准则参数零命中而恒为空操作
`ReportEngine.regenerate_affected(..., applicable_standard: str = "enterprise")`，
而 `on_trial_balance_updated` 实测**只传 3 个位置参数**（project_id / year / account_codes），
第四参走默认值 `"enterprise"`。
实测 `report_config.applicable_standard` 只有 5 种值：`listed_standalone` / `listed_consolidated` /
`soe_standalone` / `soe_consolidated` / `project:{uuid}` —— **无 `enterprise`**。
`_load_report_configs('enterprise')` 实测 **0 类 / 0 行**（`'listed'` 亦 0 行）
⇒ `affected_codes` 空 ⇒ 零行重算，且**返回成功、无异常、`issues=[]`**（静默零）。
变异证明：传 `'listed_standalone'` → 得 5 类/258 行 → 重算 **9 行** →
`BS-006` 595561117.90→**595661117.90**（+100000）、`IS-001` 895804876.83→**895904876.83**（=审定数）
⇒ 报表引擎本身正确，断点仅在缺参。

### R4 报表 stale 级联标错了表
`event_handlers/_impl.py` 的 `_mark_reports_stale_on_adjustment` 更新的是 **`AuditReport`**
（审计报告文本，本项目仅 1 行，实测 `is_stale=1` 确已标），
而财务报表真数据在 **`financial_report`**（本项目 258 行）**从未被标**——
它仅有的 2 行 stale 是 `BS-042`/`BS-053` 历史遗留，与调整分录无关。
⇒ 报表数据过期后用户看不到任何过期提示。

## 需求

### 需求 1：全局刷新入口对现有角色可达（R1）

**用户故事**：作为平台上实际存在的管理员账号，我要能触发全局一键刷新，不被角色门无条件挡死。

#### 验收标准
1. WHEN `admin` 角色调用 `POST /api/workpapers/draft-refresh` THEN 系统 SHALL NOT 返回 403
2. WHEN `auditor` 角色调用同端点 THEN 系统 SHALL 仍返回 403（审计助理无权做全局刷新，不得放开）
3. WHEN `partner` / `signing_partner` 调用 THEN 系统 SHALL 保持原有放行行为（零回归）
4. 门禁判定 SHALL 复用 `deps.require_role`，不新增并行角色判断分支

### 需求 2：report scope 真实套用报表域预设（R2）

**用户故事**：作为触发全局刷新的人，勾选「报表」范围时应真的套用报表预设公式，而不是静默 0 单元。

#### 验收标准
1. WHEN scope=`report` 被分派 THEN 派生的 page_keys SHALL 逐张报表具体化，且每个键 SHALL 能在预设库索引中命中
2. WHEN 预设库含 7 个 `report:` 前缀键 THEN 该 scope 的 `preset_count` SHALL > 0
3. SHALL NOT 出现字面量 `"report:*"` 作为 page_key
4. 派生集合 SHALL 由预设库实际键推导（不写死报表类型清单，预设库增删报表类型时自动跟随）

### 需求 3：报表增量重算使用项目真实准则（R3）

**用户故事**：作为审计人员，调整分录审批通过后报表审定数应自动更新，而不是停在旧快照。

#### 验收标准
1. WHEN `TRIAL_BALANCE_UPDATED` 事件到达 THEN `regenerate_affected` SHALL 收到该项目真实的 `applicable_standard`
2. 准则解析 SHALL 由项目 `template_type` 与 `report_scope` 组合得出（如 listed+standalone → `listed_standalone`）
3. WHEN 项目存在 `project:{uuid}` 专属配置 THEN SHALL 优先使用专属配置
4. WHEN 项目准则无法解析 THEN 系统 SHALL 记 warning 并跳过重算，SHALL NOT 静默返回成功
5. WHEN 解析出的准则在 `report_config` 中零命中 THEN SHALL 记 warning 暴露该事实，SHALL NOT 静默零重算

### 需求 4：报表 stale 标记落到财务报表数据表（R4）

**用户故事**：作为审计人员，调整分录审批后我要能在报表上看到「数据已过期」提示。

#### 验收标准
1. WHEN 调整分录相关事件触发 stale 级联 THEN `financial_report.is_stale` SHALL 被置 True（限该项目该年度）
2. 原有 `AuditReport.is_stale` 标记 SHALL 保留（零回归）
3. WHEN 标记失败 THEN SHALL 经 `log_stale_degraded` 记录，SHALL NOT 静默 pass

### 需求 5：每项修复必须有变异证明（横切）

#### 验收标准
1. 每个根因 SHALL 有一个测试在**修复前会红、修复后转绿**
2. 「零/非零」类判据 SHALL 同时断言反向样本（错误入参仍得 0、正确入参得非 0）
3. SHALL NOT 使用只验接线不验语义的 mock/spy 断言
4. 端到端验证 SHALL 使用专用测试数据，SHALL NOT 污染真实项目

## 非目标（明确排除，留后续 spec）

- 附注载荷权威源下沉后端（109 个 `buildXSyncPayload`）—— 需用户对冲突③拍板
- 大厅→底稿的分录金额回推 —— 与现行「底稿→大厅单向汇聚」方向冲突，需对冲突⑤拍板
- `audited_amount` 单列被 publish-to-tb 与 recalc_audited 争夺 —— 需对冲突①拍板
- 宽表预设两个缺失 MD 文件 —— 需用户提供文件或确认放弃
- note scope 自锁循环（page_keys 依赖 wp_formula）—— 结构性改造，阶段二
- A/B/C 三循环 198 页零预设覆盖 —— 内容工程，阶段二
- 附注国企/上市混推（上市项目含 16 行 soe 章节）—— 与 2026-08-16「降级放行」裁决相关，需拍板
