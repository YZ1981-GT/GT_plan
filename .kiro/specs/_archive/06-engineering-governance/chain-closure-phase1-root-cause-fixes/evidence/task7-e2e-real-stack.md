# Task 7 证据：真库端到端全链验证 + 变异证明（2026-09-30）

## 结论

**19/19 判据通过**，四个变异**逐个打红**，测试数据**零残留**。工具已作为正式脚本入库：

| 脚本 | 作用 |
|---|---|
| `backend/scripts/e2e/verify_chain_closure_phase1_real_stack.py` | 真 PG + 进程内真 app 跑一遍全链，自建测试项目、跑完删净 |
| `backend/scripts/e2e/verify_chain_closure_phase1_mutation.py` | 先跑未变异基线（要求全绿），再把四处修复逐个改回坏样子，确认对应判据转红 |

命名与放置沿用仓库既有同类正式工具（`verify_d1_full_book_real_stack.py` /
`verify_d4_full_book_real_stack.py`），不用 `_` 一次性前缀 —— 这条链路以后每次改都要能重跑。
运行期产物（测试项目 id / 判据结果 json）落系统临时目录，仓库内零文件残留。

## 为什么需要这一刀（变异测试之外的增量）

`tests/test_chain_closure_phase1.py` 的 10 个变异测试跑在 SQLite 上，且每组**只驱动单个断点**。
它测不到的三件事：

1. **真库的科目/准则/预设分布** —— SQLite fixture 自己造 `report_config`，两边自洽；
   R3 的分母（`enterprise` 零命中）只在真库成立。
2. **四个根因串起来跑** —— R1 放开门禁 → R2 派生真实预设键 → 审批 → R3 重算 → R4 标 stale 是一条链。
   单点绿 ≠ 链通（合并模块四阶段教训：各阶段 mock 掉相邻阶段，merge 两次咬人）。
3. **真实事件派发** —— `event_bus.publish` 带 debounce，各 handler 自开 session 并 commit。
   SQLite 测试用 `StaticPool` + 直调 handler 绕过了这一层。

## 造数与链路（专用测试项目，需求 5.4）

项目 `_CHAIN_P1_E2E_临时测试项目_2025`（`template_type='listed'` + `report_scope='standalone'`
⇒ 准则解析为 `listed_standalone`）。造 `ledger_datasets`(active) + `tb_balance` 两个**资产**科目
（`1122` 应收账款 1,000,000 / `1002` 银行存款 3,000,000）+ `account_mapping`，随后**调真 service**：

- `TrialBalanceService.full_recalc` → 试算表未审数（链条①，不手造 `trial_balance` 行）
- `ReportEngine.generate_all_reports(..., 'listed_standalone')` → `financial_report` 258 行（旧快照）
- 显式把该项目 `is_stale` 全置 False（R4 的分母）
- AJE：借 `1122` / 贷 `1002` 各 100,000（一借一贷平衡，**同时验 aje 正负两个方向**）
- 经 **HTTP**（`httpx.ASGITransport` + 真 app，只 override `get_current_user`）走
  `POST /api/projects/{pid}/adjustments/{group}/review` 两次：`draft → pending_review → approved`

## 19 条判据实测

### 前置分母（现算，不引用 spec 里的旧值）

| 判据 | 实测 |
|---|---|
| R3 分母 | `report_config`：`listed_standalone` **258** 行 / `enterprise` **0** 行 ⇒ 默认参数零命中才是根因 |
| R1 分母 | 活跃用户按角色 `{admin: 8, auditor: 53}` —— **零 partner** ⇒ 原白名单无人可达 |
| R2 分母 | 预设库 `report:` 键 **7** 个，字面量 `'report:*'` 不在其中 ⇒ 写死即恒不命中 |
| handler 已注册 | `ADJUSTMENT_APPROVED` 订阅者 5 个，含 `_mark_reports_stale_on_adjustment` 与 `handle_adjustment_approved` |

### 链路与四个根因

| 判据 | 实测 |
|---|---|
| 链条① 四表→试算表未审数 | `1122`=1,000,000.00 / `1002`=3,000,000.00（与 `tb_balance` 期末逐值相等） |
| 报表初稿对齐审定数 | `BS-006`=1,000,000.00 / `BS-002`=3,000,000.00 |
| R4 分母 | `financial_report` **258** 行，`is_stale` 全 False |
| **R1 核心** | admin → **HTTP 200**（修复前实测 403） |
| R1 反向断言 | auditor → **HTTP 403**（防修过头） |
| **R2 核心** | `preset_count=343`，`presetted_pages=7` 个（修复前恒 0 —— 正是 requirements 里「锁死 343 条」那个数） |
| R2 派生键形态 | 命中键全为具体 `report:` 键，异常项 0 |
| 审批 → pending_review / approved | 两次 HTTP 200 |
| 链条⑧ 审批→TB 调整列 | `1122.aje=+100,000.00` / `1002.aje=-100,000.00`（借方类 +，贷记同为借方类 − ⇒ 方向归一正确） |
| 不变式 audited=未审+aje+rje | `1122`: 1,100,000.00 / `1002`: 2,900,000.00 |
| **R3 核心 链条⑦ →报表审定数** | `BS-006` 1,000,000.00 → **1,100,000.00**；`BS-002` 3,000,000.00 → **2,900,000.00** |
| **R4 核心 stale 落到 financial_report** | **258/258** 行 `is_stale=True` |
| 增量重算不波及无关行 | 未引用变更科目的报表行零改动（异常 0 行） |
| 测试数据删净 | 零残留（逐表核验，见下） |

## 变异证明（四处修复逐个改回坏样子）

驱动器先跑**未变异基线**并要求 19/19 全绿 —— 否则脚手架自己坏了（路径改名 / PG 连不上）
会让每个变异都"崩溃"，而崩溃被当作"打红" ⇒ 得到一份全是 ✅ 的假报告。

| 变异 | 改法 | 结果 |
|---|---|---|
| 基线 | 不改 | ✅ 19/19 |
| **R1** | `PARTNER_ROLES` 去掉 `admin` | ✅ 转红 16/18 —— `admin → HTTP 403`（连带 R2 判据也红：403 拿不到 preset 数据，属预期） |
| **R2** | 改回 `page_keys.append("report:*")` | ✅ 转红 17/18 —— `preset_count=0`，`presetted_pages=0` |
| **R3** | `regenerate_affected` 去掉 `applicable_standard=` | ✅ 转红 18/19 —— 两个报表值**一动不动**（1,000,000 / 3,000,000） |
| **R4** | 整段切掉 `FinancialReport` stale | ✅ 转红 18/19 —— 只 **2/258** 行 `is_stale=True` |

🔴 **R4 这一红同时改正了我自己写的一句话**：判据消息原写「修复前 0 行」，变异实测是 **2/258**
（另有一条 `REPORT_ROW_CHANGED` 侧的传播路径会零星标到 2 行）。已把消息改成实测口径，并说明
**判据必须是「全部行被标」而不是「stale > 0」** —— 后者在缺陷态也会绿。

## 清理

`DELETE` 顺序：`adjustment_entries`（经 `adjustment_id` 关联，该表无 `project_id`）→ 现算
`information_schema` 里 public schema 下**所有带 `project_id` 列的基表**逐表删（最多 6 轮，
每表独立事务以规避 PG「首条失败使事务 aborted」）→ `projects`。随后**逐表核验残留**，
再用 PG 现查孤儿行（`trial_balance` / `financial_report` / `draft_refresh_audit` 反查 `projects`）
三项均 0。连跑 6 次（1 次首验 + 1 次复现 + 4 次变异 + 1 次基线）后真库零残留。

## 过程中踩到的两个坑（已写进脚本注释）

1. **`AccountMapping.project_id` 在 ORM 层没声明 `ForeignKey`**（DB 层有
   `account_mapping_project_id_fkey`）⇒ SQLAlchemy 的 unit of work 不知道它依赖 `projects`，
   把 `account_mapping` 的 INSERT 排在 `projects` 之前 ⇒ `ForeignKeyViolationError`。
   同 session 里显式 `flush()` 即可定序。
2. **变异器的多行锚点必须按文件真实换行符拍平**：这四个文件**全是 CRLF**
   （现算 208 / 380 / 2325 / 2300 处 `\r\n`，零 LF-only），首版按 `\n` 写锚点在 R2/R4 上
   **命中 0 次**。现改为拍平成 `\n` 替换、写回还原，并先做**恒等往返自检**（往返不等就拒绝变异）。
   另：变异器恢复原文一律**按原始字节写回**，不用 `git checkout` —— R1/R2/R4 三处修复本身
   尚未提交，`git checkout` 会把修复一起抹掉。
