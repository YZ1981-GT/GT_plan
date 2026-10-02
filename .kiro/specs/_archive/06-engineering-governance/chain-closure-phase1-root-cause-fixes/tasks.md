# 实施任务：阶段一四个根因修复

> **实际状态（2026-09-30 收尾）：10/10 完成。**
> 四个根因代码已改完、10 个变异测试全绿、77 个回归零破坏；task 7 真库端到端
> **19/19 判据通过 + 4/4 变异打红 + 测试数据零残留**（`evidence/task7-e2e-real-stack.md`）；
> task 10 的阻塞判据已满足并按 hunk 分离后提交。
>
> 2026-09-28 收盘时的状态（8/10、提交阻塞）见 `evidence/commit-blocked-status.md`，
> 该文件保留为当时的事实记录，**不回填修改**（历史档案 append-only）。

- [x] 1. 冻结修复前红基线（变异证明的分母）
  - 已写 `backend/tests/test_chain_closure_phase1.py`（427 行 / 10 个测试 / 4 组）
  - 实测红基线 = **6 failed / 4 passed**：4 组核心变异全红，4 个反向断言全绿
    （反向断言修复前就该绿，用于证明判据不恒真）
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 2. 修 R3：`on_trial_balance_updated` 传项目真实准则
  - 已照抄同类 `_build_unadjusted_bundle:1604` 的 `ReportConfigService.resolve_applicable_standard` 用法
  - `regenerate_affected` 已增传 `applicable_standard=`
  - 已加重算 0 行时的 `logger.warning`（需求 3.5，静默零变可见）
  - 改动量 +21/-1
  - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [x] 3. 修 R4：stale 级联补标 `financial_report`
  - 已在 `_mark_reports_stale_on_adjustment` 的 AuditReport 段与 DisclosureNote 段之间
    插入 `FinancialReport` update 段（独立 try + `log_stale_degraded`）
  - 既有 `AuditReport` 段保留（测试 `test_stale_cascade_marks_financial_report` 断言它仍被标）
  - 改动量 +27
  - _Requirements: 4.1, 4.2, 4.3_

- [x] 4. 修 R2：report scope 的 page_keys 逐张派生
  - 已删字面量 `"report:*"`，改为 `sorted(k for k in build_preset_index() if k.startswith("report:"))`
  - 预设库不可用时 warning + 不阻断
  - 改动量 +21/-1
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 5. 修 R1：`PARTNER_ROLES` 加 `admin`
  - 已加 `admin`；刻意不放开 `auditor`/`readonly`（`test_auditor_stays_denied` 钉死）
  - 端点级测试 `test_endpoint_level_role_gate` 已写并通过（真发 HTTP，override 内层
    `get_current_user` 绕开依赖工厂 key 不匹配的坑）
  - 🔴 需求 1.1 的判据经实测**改写**：原拟「白名单不得有幽灵角色」，但 `UserRole` 枚举
    实无 `signing_partner`（那是 `project_assignments` 级角色），删它会破坏向前兼容
    ⇒ 判据改立在**可达性**（可达集合须与真库现存角色 {admin, auditor} 有交集）
  - 改动量 +10/-1
  - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 6. 四组变异测试转绿
  - 重跑得 **10 passed**（R3 组 3 + R4 组 1 + R2 组 2 + R1 组 4）
  - 反向断言复核仍成立：`enterprise` 仍 0 行 / `"report:*"` 仍不在预设库 / auditor 仍 403
  - 🔴 过程中修掉 5 个**测试环境**假红（非生产代码问题，已写进测试注释）：
    `sys.modules[__name__] = _impl` 模块替换致 patch 打在重复加载的副本上 ·
    SQLite fixture 须显式 `is_deleted=False` · `:memory:` 须 `StaticPool` ·
    `AuditReport.opinion_type` NOT NULL · monkeypatch 须用模块对象而非点号字符串
  - _Requirements: 5.1, 5.2_

- [x] 7. 造测试项目端到端跑通全链（2026-09-30 补做）
  - 工具已作为**正式脚本**入库（沿用仓库既有 `verify_*_real_stack.py` 惯例，非 `_` 一次性前缀
    —— 这条链路以后每次改都要能重跑）：
    `backend/scripts/e2e/verify_chain_closure_phase1_real_stack.py`（真 PG + `httpx.ASGITransport`
    进程内真 app，自建测试项目跑完删净）+ `..._mutation.py`（先跑未变异基线要求全绿，
    再把四处修复逐个改回坏样子）。运行期产物落系统临时目录，仓库内零文件残留
  - **19/19 判据通过**：链条① 四表→试算表未审数 · R1 admin HTTP **200** / auditor 仍 **403** ·
    R2 `preset_count=343`（正是需求里「锁死 343 条」那个数）· 链条⑧ TB 调整列 `1122 +100000` /
    `1002 -100000`（方向归一正确）· **R3** `BS-006` 1,000,000→**1,100,000**、`BS-002`
    3,000,000→**2,900,000** · **R4** `is_stale` **258/258** · 增量重算不波及无关行
  - **变异 4/4 打红**：R1→admin 403 · R2→`preset_count=0` · R3→两报表值一动不动 ·
    R4→只 **2/258**
  - 🔴 变异**改正了我自己写的一句话**：R4 判据消息原写「修复前 0 行」，实测是 **2/258**
    （另有一条 `REPORT_ROW_CHANGED` 侧传播路径会零星标到 2 行）⇒ 判据必须是「**全部**行被标」，
    写成 `stale > 0` 在缺陷态也会绿。已按实测口径改消息
  - 清理：`adjustment_entries`（经 `adjustment_id`）→ 现算 public schema 下所有带 `project_id`
    的基表逐表删（每表独立事务）→ `projects`；逐表核验 + PG 现查孤儿行三项均 0。
    连跑 6 次（首验 / 复现 / 4 次变异 / 基线）真库零残留
  - 踩坑见 `evidence/task7-e2e-real-stack.md`：`AccountMapping.project_id` ORM 层无
    `ForeignKey` 致 INSERT 排序错 · 四个目标文件全 CRLF 使变异器多行锚点命中 0 次
  - _Requirements: 5.4_

- [x] 8. 回归确认零破坏
  - `test_report_engine.py` / `test_trial_balance.py` / `test_event_bus.py` /
    `test_adjustment_sync.py` + 本 spec 测试 = **77 passed，0 failed**
  - 未出现需要 `git stash` 区分的红项
  - _Requirements: 全部_

- [x] 9. 清理与登记
  - 探针零残留：12 个 `_chainp_*.py` + `_r4p_diag.py` + `_wl_check.py` / `_wl_add.py` /
    `_idx_reg.py` 全删；`_p1~_p9.log` / `_reg.log` / `_r4run.log` / `_chain_*.txt` /
    `_chain_e2e_ids.json` / `_commit_msg.txt` 全删
  - `.kiro/specs/INDEX.md` 登记行**已入库**（被并发会话 commit `78b9c1ee5` 一并带走并推送）
  - 「删 seed 脚本 / 测试项目数据删净」两项**不适用**（task 7 未执行，未造测试项目）
  - **2026-09-30 补**：task 7 补做后这两项重新适用，处置如下 ——
    「测试项目数据删净」由端到端脚本自带清理保证（逐表核验 + PG 现查孤儿行三项均 0，连跑
    6 次零残留）；「删 seed 脚本」**不照字面执行** —— 造数与清理已内聚进正式工具
    `verify_chain_closure_phase1_real_stack.py`（仓库既有同类正式脚本先例：
    `verify_d1_full_book_real_stack.py` / `verify_d4_full_book_real_stack.py`），
    不是散落的一次性 seed；一次性辅助 `backend/scripts/ops/_stage_r4_only.py`（按 hunk
    暂存 R4 用）用完即删，做法已写进 task 10
  - 🔴 已撤销 `file_size_whitelist.txt` 的登记：baseline 2261 含他人 15 行属虚高，
    违反该表「baseline 必须填当前真实行数」规则；重新提交时须**现算**再登记

- [x] 10. 提交与推送（2026-09-30 阻塞已解除）
  - **解除判据已满足**：`formula_engine.py` 与 `report_engine.py` 现算均已 clean ——
    R3 那处修复（`report_engine.py` 的 `resolve_applicable_standard` + 零重算 warning）
    已随并发 lane 的批次进 HEAD，现读确认在位
  - 🔴 **但换了一处混入**：`_impl.py` 的工作树 diff 涨到 **+226/-0**，其中只有 27 行是 R4，
    其余是并发 lane 在 `_auto_map_on_dataset_activated` 上的未提交改动 ⇒ **按 hunk 分离**：
    取 HEAD 版 + 在 `# 标记附注 stale` 之前原样插入工作树那 27 行 → `git add` →
    立刻按备份字节还原工作树。index 得 **+27/-0 且零 `auto_map` 行**（已断言）
  - **暂存树自洽已实测**：把 index 版 `_impl.py` 临时落盘后跑本 spec 测试 **10 passed**，
    再按字节还原 ⇒ 提交出去的组合单独可用（不靠工作树里别人的改动）
  - 行数门禁：`check_file_size.py --staged` 现算**通过**（exit 0），
    `file_size_whitelist.txt` **无需登记**（index 版 `_impl.py` 2116 行 < 工作树 2301 行，
    正是该门禁改用 `--staged` 的设计意图：不把别人的膨胀记到本轮账上）
  - 另两个生产文件 diff 逐条复核为纯本轮改动：`draft_refresh.py` +10/-1 ·
    `draft_refresh_orchestrator.py` +21/-1
  - `.kiro/specs/INDEX.md` 本 spec 那一行同样**按 hunk 单独暂存**（该文件另有并发 lane
    未提交的新行，不代提）
