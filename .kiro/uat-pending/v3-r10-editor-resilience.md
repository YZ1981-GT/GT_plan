# UAT Pending: Spec C — Editor Resilience

**Spec ID**：`v3-r10-editor-resilience`
**实施完成日期**：2026-05-16
**Commit**：`a04f2b5` + `99b3570`(G3 修复)
**SLA**：P1 → 14 天内（≤ 2026-05-30）
**当前状态**：5/10 ✓ pass + 5/10 ○ pending-uat

---

## 待真人执行清单

| # | 验收项 | 责任人 | 截止日期 | 状态 |
|---|--------|--------|---------|------|
| 3 | 4 worker 心跳每 30s 写入 Redis | DevOps | 2026-05-23 | ○ pending |
| 5 | DegradedBanner 三档切换（手动 kill 后端验证） | 测试 | 2026-05-23 | ○ pending |
| 6 | LedgerDataManager 清理账套必须二次确认 | 审计助理 | 2026-05-23 | ○ pending |
| 7 | EqcrMemoEditor 定稿必须二次确认 | EQCR 合伙人 | 2026-05-23 | ○ pending |
| 8 | 5 个签字组件全部经过 confirmSign | 各角色用户 | 2026-05-23 | ○ pending |

## 执行指引

### UAT-3 worker 心跳真实验证（DevOps）

```bash
# 启动后端
start-dev.bat
# 等 60s 后检查 Redis
redis-cli get worker_heartbeat:sla_worker
redis-cli get worker_heartbeat:import_recover_worker
redis-cli get worker_heartbeat:outbox_replay_worker
redis-cli get worker_heartbeat:import_worker
# 4 个 key 都应有 JSON value 且 TTL 接近 60s
```

### UAT-5 DegradedBanner 三档切换（测试）

```bash
# 1. 启动前后端
# 2. 打开浏览器，进入项目页面
# 3. 终止后端进程 (Ctrl+C in start-dev.bat 后端窗口)
# 4. 30 秒内顶栏应显示 🔴 "部分功能暂时不可用"
# 5. 重启后端，30 秒内 🔴 消失，恢复正常
```

### UAT-6 LedgerDataManager 二次确认（审计助理）

```bash
# 1. 进入"账表数据管理"页面
# 2. 点击"清空账套数据"按钮
# 3. 应弹出 confirmDangerous 对话框，要求输入项目完整名称
# 4. 输错项目名 → 不能确认；输对 → 才能继续
```

### UAT-7 EqcrMemoEditor 定稿二次确认（EQCR 合伙人）

```bash
# 1. 进入 EQCR 工作台 → 备忘录 Tab
# 2. 编辑备忘录 → 点击"定稿"
# 3. 应弹出 confirmDangerous 对话框，警告"定稿后不可修改"
# 4. 取消 → 不变；确认 → 状态变 finalized
```

### UAT-8 5 签字组件 confirmSign（各角色）

```
- 一级复核（auditor）：SignatureLevel1.vue 签字 → confirmSign 弹框
- 二级复核（manager）：SignatureLevel2.vue 签字 → confirmSign 弹框
- 合伙人（partner）：PartnerSignDecision.vue 签字 → confirmSign 弹框
- EQCR（eqcr）：EqcrApproval.vue 批准 → confirmSign 弹框
- 归档（admin/partner）：ArchiveSignature.vue 签字 → confirmSign 弹框
```

## 上线门槛

- ≥ 8 项 ✓ pass
- 关键项 1 / 2 / 5 / 6 / 7 / 8 必须 pass（已 1/2 pass，余 5/6/7/8 待验）

## 联系人

- DevOps：（待补）
- 测试：（待补）
- 审计助理：（待补）
- EQCR 合伙人：（待补）
