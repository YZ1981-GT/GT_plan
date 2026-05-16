# v3 Quickfixes（档 2 小型 spec 集合）

**编制人**：合伙人（平台治理）
**起草日期**：2026-05-16
**完成日期**：2026-05-16
**关联文档**：`docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §6 P0 优先级表
**关联 commit**：`b4cda44`（v3 全局打磨建议 + Spec A 联动 stale 传播实施完成）
**定位**：v3 P0-1/P0-3/P0-4/P0-5 四件需要 1 页方案、不需要完整三件套的修复任务

---

## 索引

| Quick | v3 ref | 红色度 | 工时（实际）| 状态 |
|-------|--------|-------|------------|------|
| Q1 | P0-1 / F6 | 🔴 阻塞 | 0.4h | ✅ 已完成 |
| Q2 | P0-3 / F9 | 🔴 真红 | 0.3h | ✅ 平反 |
| Q3 | P0-4 / F10 | 🔴 真红 | 0.3h | ✅ 平反 |
| Q4 | P0-5 / F2 | 🔴 临时已修 | 0.5h | ✅ 已完成 |

**总工时**：1.5h（远低于初估 3-4 天）；35× 压缩比的主因 = Q2/Q3 是端点形态被错估（路径假设错），实际后端早已存在；只 Q1/Q4 是真修复。

---

## Q1 — F6 修复 AJE 创建 MissingGreenlet 500（P0-1）✅

### 真根因（实测定位）

`backend/app/deps.py::check_consol_lock` 中：
- 当 PG `projects.consol_lock` 列不存在时，except 分支调 `await db.rollback()`
- rollback 让 session 中**所有已 SELECT 的 ORM 对象（包括 current_user）**全部 expired
- 回到 router 后访问 `user.id` 触发 lazy load → **MissingGreenlet**

排查链路：
```
异常栈最深的 __get__ 行 = 触发 lazy load 的字段
反推 ORM 对象什么时候被 expire
最常见 = 同 session 里有 db.rollback() / db.expire_all()
```

### 修复

`backend/app/deps.py:262`：
```python
# 修复前
try:
    result = await db.execute(sa_text("SELECT consol_lock ..."))
except Exception:
    await db.rollback()  # ← 让外层事务回滚 + 所有对象 expired

# 修复后
try:
    async with db.begin_nested():  # SAVEPOINT
        result = await db.execute(sa_text("SELECT consol_lock ..."))
except Exception:
    pass  # SAVEPOINT 自动回滚，外层事务和已 SELECT 对象状态不受影响
```

### 落地证据
- `backend/app/deps.py:262` `async with db.begin_nested():` 已生效
- 4 项目 AJE 创建端点实测 200（陕西华氏/和平药房/辽宁/宜宾）
- 不影响其他并发查询（SAVEPOINT 隔离）

### 沉淀规约（写入 memory）
- **`async with db.begin_nested()` SAVEPOINT 模式**：可重入子事务；列不存在/SQL 异常只回滚 SAVEPOINT，外层事务和已 SELECT 对象状态不受影响；适用于"探测性查询可能失败但不能影响主流程"
- **session 污染传播链铁律**：任何 `try/except: pass` 包裹的 `db.execute(...)` 都必须在 except 中调 `await db.rollback()` 或走 SAVEPOINT，否则失败查询会让 PG 事务进入 aborted 状态，后续所有查询全部 InFailedSQLTransactionError

---

## Q2 — F9 EQCR 3 个端点修复（P0-3）✅ 平反

### 实测真路径（grep 核验）

v3 第三稿假设的端点路径全部错；后端真实端点早已存在：

| 模块 | v3 假设 | 真实路径 | 文件 |
|------|---------|---------|------|
| EQCR 意见列表 | `/api/eqcr/projects/{pid}/opinions`（统一 GET） | 按 domain 分 5 个 GET：`/materiality` / `/estimates` / `/related-parties` / `/going-concern` / `/opinion-type` + `POST /opinions` 创建 + `PATCH /opinions/{id}` 修改 | `eqcr/opinions.py` |
| 上年比较 | `/api/eqcr/projects/{pid}/prior-year` | `/api/eqcr/projects/{project_id}/prior-year-comparison`（带后缀） | `eqcr/prior_year.py` |
| EQCR 备忘录读 | `/api/eqcr/projects/{pid}/memo` GET | 没有 GET root；用 `GET /api/eqcr/projects/{project_id}/memo/preview` 读 | `eqcr/memo.py` |

### 处理结论

- 后端无需改动（端点全部就位）
- 前端 `apiPaths.ts:eqcr` 实测**全部正确**，零踩雷
- v3 §3 端点速查表已校正引用

### 沉淀规约
- **打磨建议文档铁律补强**：每条端点引用必须 grep `backend/app/routers/**/*.py` 真实文件确认；不能凭印象写

---

## Q3 — F10 复核记录 + 复核对话端点 404（P0-4）✅ 平反

### 实测真路径（grep 核验）

| 模块 | v3 假设 | 真实路径 | 文件 |
|------|---------|---------|------|
| 复核对话列表 | `/api/projects/{pid}/review-conversations` | `/api/review-conversations` 全局 prefix + `?project_id=...` query param | `review_conversations.py:21` |
| 复核记录 | `/api/projects/{pid}/review-records` | **真不存在**；前端 grep 零引用 | — |

### 处理结论

- `review-conversations` 是全局 prefix + query param（v3 假设错），后端无改动
- 前端 `apiPaths.ts:reviewConversations.projectList` 修一处错路径（`/api/projects/{pid}/review-conversations` → `/api/review-conversations?project_id={pid}`）
- `review-records` 前端零引用，不补端点（YAGNI）

### 落地证据
- commit `b4cda44` 已修 apiPaths.ts
- ReviewWorkbench / ReviewConversations 首屏可加载（已无 404）

---

## Q4 — F2 chain 自动跑底稿生成 + WP List 引导卡片（P0-5）✅

### 真问题

- `POST /api/projects/{pid}/workflow/execute-full-chain` 端点完全工作（实测和平 0→107、辽宁 0→104）
- 真问题：`scripts/init_4_projects.py` 漏调 chain，导致新项目"试算/报表都有，底稿数=0"，用户进系统看到空白困惑

### 修复

**A. 后端 `backend/scripts/init_4_projects.py`** 末尾追加 step 5：
```python
# Step 5: 一键全链路（生成底稿 + 重新 generate 报表，避免 stale）
from app.services.chain_orchestrator import ChainOrchestrator
async with AsyncSessionLocal() as db:
    orchestrator = ChainOrchestrator(db)
    chain_result = await orchestrator.execute_full_chain(
        project_id=project_id, year=year, triggered_by=None, force=True,
    )
```

**B. 前端 `audit-platform/frontend/src/views/WorkpaperList.vue`**：
- 添加"暂无底稿"引导卡片（v-if `tb_count > 0 && wp_count == 0`）
- "🚀 一键生成底稿+附注" 按钮调 `POST /api/projects/{pid}/workflow/execute-full-chain` body `{year, force: true}` timeout 120s
- 加载状态 + 完成 toast + 自动刷新底稿树

### 落地证据
- `init_4_projects.py:121-125` `orchestrator.execute_full_chain` 已生效
- `WorkpaperList.vue:77-92` 引导卡片 + `:945-948` `onGenerateChain` 函数全部就位
- 4 项目重建后 wp_count 全部 > 0（陕西 92 / 和平 107 / 辽宁 104 / 宜宾 42）

---

## 跨项目沉淀（写入 conventions / memory）

### 端点形态错估反模式（Q2/Q3 教训）

3 处端点路径都是按"猜测的资源命名"假设的，实际后端有不同形态：

1. **EQCR opinions 没有"统一 GET 列表"**——是按 domain 分 5 个细粒度 GET
2. **review-conversations 是全局 prefix + query param**——不是项目子前缀
3. **memo 没有 GET root**——用 `/memo/preview` 读

**铁律**：v3+ 文档里每条 `GET /api/...` 引用必须在脚注或括号里附"已 grep 核验位置 `routers/xxx.py:line`"，否则按未核验对待。

### 工时压缩比 35× 主因（Q1-Q4 复盘）

```
原计划：3-4 天
实际：1.5h
压缩比：~35×

主因：
- Q2/Q3 假设错（路径形态被错估）→ 平反 0.6h
- Q1 真根因定位精准（SAVEPOINT 模式直击）→ 0.4h
- Q4 后端早已就绪（chain 端点工作），只是脚本漏调用 → 0.5h
```

下次起 spec 前先做"真根因 grep"探查 1 小时，可能省去 80% 工时。

### 档 2 小型 spec 反模板更新

如果遇到以下情况，**升级到完整三件套**：
1. 任何一项需要修改 ≥ 5 个文件
2. 需要新建后端模型 / Alembic 迁移
3. 需要前后端协议变更（schema / 端点路径）
4. 需要跨服务影响（如改 event_bus 协议）
5. 工时超过预估 2x

**新增**：
6. **真根因排查需要 ≥ 4h**（如 Q1 排查只 0.4h，但若超 4h 应停手起完整 spec）
7. **涉及核心业务流程**（如 AJE 创建链路属于跨 6 个 service 调用，本次只是单点修复，但若问题扩散到 service 层应升级）

---

## 收尾状态

- ✅ 4 件 Q 全部完成或平反
- ✅ 后端代码改动：1 处（`deps.py` SAVEPOINT）+ 1 处（`init_4_projects.py` chain step）
- ✅ 前端代码改动：1 处（`apiPaths.ts` reviewConversations 路径）+ 1 处（`WorkpaperList.vue` 引导卡片）
- ✅ 实测验证：4 项目 AJE 200 / chain 端点 200 / 端点速查表平反 6 处
- ✅ 已并入 commit `b4cda44` 推送到 `origin/feature/e2e-business-flow`

下一步：v3 §16 自我复盘记录的 R10 两个 spec（`v3-r10-linkage-and-tokens` + `v3-r10-editor-resilience`）独立立项实施，3-4 周后启动。
