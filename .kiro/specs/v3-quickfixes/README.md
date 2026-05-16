# v3 Quickfixes（档 2 小型 spec 集合）

**编制人**：合伙人（平台治理）
**日期**：2026-05-16
**关联文档**：`docs/GLOBAL_REFINEMENT_PROPOSAL_v3.md` §6 P0 优先级表
**定位**：v3 P0-1/P0-3/P0-4/P0-5 四件需要 1 页方案、不需要完整三件套的修复任务

---

## 索引

| Quick | v3 ref | 红色度 | 工时 | 状态 |
|-------|--------|-------|-----|------|
| Q1 | P0-1 / F6 | 🔴 阻塞 | 1-2 天 | 待启动 |
| Q2 | P0-3 / F9 | 🔴 真红 | 1 天 | 待启动 |
| Q3 | P0-4 / F10 | 🔴 真红 | 0.5 天 | 待启动 |
| Q4 | P0-5 / F2 | 🔴 临时已修 | 0.5 天 | 待启动 |

---

## Q1 — F6 修复 AJE 创建 MissingGreenlet 500（P0-1）

### 实测复现
```
POST /api/projects/{pid}/adjustments
body: 标准 AdjustmentCreate（line_items + 小写枚举）
→ 500
后端日志：sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
         can't call await_only() here. Was IO attempted in an unexpected place?
位置：result = await svc.create_entry(project_id, data, user.id, batch_mode=batch_mode)
```

### 排查路径（按优先级）
1. **grep 三个事件 handler**：
   - `event_handlers.py` 的 `_notify_adjustment_event_sse` / `_record_tb_change_on_adjustment` / `_mark_reports_stale_on_adjustment`
   - 看是否访问了 `payload.user.xxx` 关系字段
2. **检查 user 对象生命周期**：
   - `require_project_access` 从 Redis 缓存路径回来时 user 已 detached
   - service 层 `await db.refresh(user)` 之前不能访问关系字段
3. **检查 `_publish_adjustment_event` 同步发布**：
   - 如果 handler 内 `db.execute(...)` 但 db 已 commit，会 MissingGreenlet
4. **复现路径**：
   - pytest `backend/tests/test_adjustments.py` 加一个 admin 创建 AJE 的回归测试
   - 真实数据复现：陕西华氏 + AdjustmentCreate（库存现金/银行存款 借贷各 100）

### 修复方案
**最可能的两条路径**（排查后选其一）：

**A. service 层传 user_id 而非 user 对象**：
```python
# adjustments.py POST handler
result = await svc.create_entry(project_id, data, user.id, batch_mode=batch_mode)
# ↑ 已经传 user.id，问题在 service 内部或 handler
```

**B. event_handler 内 lazy load**：
```python
# event_handlers.py
async def _record_tb_change_on_adjustment(payload):
    # 如果有 payload.user.role 这样的访问，会 lazy load
    # 修复：payload 里只放 user_id，handler 内重新 SELECT User
```

### 验收
- `POST /api/projects/{pid}/adjustments` 返回 201
- `pytest backend/tests/test_adjustments.py::test_create_aje_admin` 通过
- 后端日志连续 5 次 POST 无 MissingGreenlet
- 联动测试：创建 AJE → 等 1s → `stale_count` +1 → 删除 → 归 0

### 风险
- 如果根因在 SSE handler，可能要改 event_bus 协议（中风险）
- 如果根因在 user.role.value 之类的 enum lazy load，改 service 一处即可（低风险）

---

## Q2 — F9 EQCR 3 个端点修复（P0-3）

### 实测发现
```
GET /api/eqcr/projects/{pid}/opinions     → 404 Not Found
GET /api/eqcr/projects/{pid}/prior-year   → 404 Not Found
GET /api/eqcr/projects/{pid}/memo         → 405 Method Not Allowed
```

### 端点契约表（核验路径）
| 模块 | 期望 GET | 真实路径（待 grep） | 状态 |
|------|---------|-------------------|------|
| EQCR 意见 | `/api/eqcr/projects/{pid}/opinions` | grep `eqcr/opinions` | 待查 |
| 上年比较 | `/api/eqcr/projects/{pid}/prior-year` | grep `eqcr/prior-year`、`/prior_year`、`/prior-year-data` | 待查 |
| EQCR 备忘录 | `/api/eqcr/projects/{pid}/memo`（GET 读） | 405 说明 path 在但只接受 POST/PATCH | 必须补 GET |

### 修复路径
1. **grep 真实路径**：
   ```bash
   rg "@router\.(get|post|patch).*opinions|prior.year|memo" backend/app/routers/eqcr/
   ```
2. **如果端点不存在**（opinions / prior-year）：
   - 在 `backend/app/routers/eqcr/{module}.py` 补 GET endpoint
   - 走 EqcrService 已有方法（`get_opinions_by_domain` 等）
3. **如果 memo 只能 POST**：
   - 补 GET endpoint 返回最新 memo 内容（`Project.wizard_state.eqcr_memo` JSONB）

### 验收
- 3 个端点全部 200
- `EqcrProjectView.vue` 5 Tab 全部能渲染数据
- 关联测试：partner 角色访问 → 200，auditor 访问 → 403

---

## Q3 — F10 复核记录 + 复核对话端点 404（P0-4）

### 实测发现
```
GET /api/projects/{pid}/review-records?year=2025  → 404
GET /api/projects/{pid}/review-conversations      → 404
```

### 排查路径
1. **grep 真实路径**：
   ```bash
   rg "review.records?|review.conversations?" backend/app/routers/ -t py
   ```
2. **可能的真实端点**：
   - `/api/review/records?project_id=...` （非项目子前缀）
   - `/api/projects/{pid}/wp-mapping/review-inbox`（已有，但和 records 不同）
   - 端点真不存在 → 列表数据来自其他 API

### 修复
- 如果路径假设错 → v3 §3 端点速查表补正
- 如果端点真缺 → 在 `backend/app/routers/review_records.py` 补 GET 列表

### 验收
- 两个端点都 200
- `ReviewWorkbench.vue` / `ReviewConversations.vue` 首屏能加载列表

---

## Q4 — F2 chain 自动跑底稿生成 + WP List 引导卡片（P0-5）

### 实测验证
- `POST /api/projects/{pid}/workflow/execute-full-chain` 完全工作（和平 0→107、辽宁 0→104）
- 真问题：`scripts/init_4_projects.py` 漏调 chain，导致新项目"底稿数=0"

### 修复
**A. 后端 init 脚本**：
```python
# scripts/init_4_projects.py 末尾追加
# Step 5: 一键全链路（生成底稿 + 重新 generate 报表，避免 stale）
print(f"  [5] execute-full-chain ...")
async with httpx.AsyncClient(...) as client:
    r = await client.post(
        f"{BASE}/api/projects/{project_id}/workflow/execute-full-chain",
        json={"year": year, "force": True},
        timeout=120,
    )
    r.raise_for_status()
```

**B. 前端引导卡片**：
- `WorkpaperList.vue` 顶部加 v-if 块：当 `tb_count > 0 && wp_count == 0` 时显示
  ```vue
  <el-alert type="warning" :closable="false">
    <span>⚠️ 底稿尚未生成。试算表已就绪但底稿数 = 0。</span>
    <el-button size="small" type="primary" @click="onGenerateChain">
      一键生成底稿
    </el-button>
  </el-alert>
  ```
- `onGenerateChain` 调 `POST /api/projects/{pid}/workflow/execute-full-chain`

**C. CI smoke**（独立 Sprint 任务）：
- `e2e_business_flow_verify.py` 加 layer：所有项目 `wp_count > 0` 才算通过

### 验收
- `init_4_projects.py` 跑完后 4 项目 wp_count > 0
- 真实新项目走完链路自动有底稿
- WorkpaperList 0 底稿场景不再"白板困惑"

---

## 执行顺序（推荐）

按 v3 §6 排序：

```
Day 1  下午：Q1 F6 排查启动（先做 grep + 复现测试）
Day 2  全天：Q1 F6 修复 + 加回归测试
Day 3  上午：Q1 验收 + Q3 F10 启动（端点核验）
Day 3  下午：Q3 F10 修复
Day 4  全天：Q2 F9 修复（3 个端点）
Day 5  上午：Q4 F2 修 init_4_projects 脚本
Day 5  下午：Q4 F2 加 WorkpaperList 引导卡片
```

**执行原则**：
- 每件 Q 完成后立即跑回归测试（不堆到最后一起测）
- F6（Q1）是其他验收的前置——必须最先修
- 修完后立即更新 v3 文档对应 F 状态从 🔴 → ✅

---

## 反模板：什么时候应升级到完整三件套

如果遇到以下情况，停下来从 README 升级到完整三件套：

1. **任何一项需要修改 ≥ 5 个文件**
2. **需要新建后端模型 / Alembic 迁移**
3. **需要前后端协议变更**（schema / 端点路径）
4. **需要跨服务影响**（如改 event_bus 协议影响多个 handler）
5. **工时超过预估 2x**（如 Q1 估 1-2 天但跑了 4 天还没修完）

满足任一条 → 立即停手，写 design.md + tasks.md + requirements.md。
