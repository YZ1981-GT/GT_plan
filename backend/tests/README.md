# 后端测试说明

## 运行测试

```bash
# 全量测试
python -m pytest backend/tests/ -v --tb=short

# 单个文件
python -m pytest backend/tests/test_signature_prerequisite.py -v

# 属性测试（hypothesis）
python -m pytest backend/tests/test_audit_log_hash_chain_property.py -v
python -m pytest backend/tests/test_production_readiness_properties.py -v
```

## 预存失败（与当前 spec 无关）

以下测试在 SQLite 环境下预期失败，不影响 CI 判定：

- `test_adjustments.py` — 23 个测试因 SQLite 不支持 `pg_advisory_xact_lock`
- `test_misstatements.py` — 2 个测试因 UnadjustedMisstatement 缺 soft_delete mixin
- `test_e2e_chain*` — 同样 `pg_advisory_xact_lock` 问题

## 测试盲点清单（Round 2+ 补充目标）

以下场景当前缺少自动化测试覆盖，需在后续迭代中补充：

### 并发/竞态

- 哈希链 race condition：多 worker 同时写同一 project_id 的审计日志（PG advisory lock 已加，但缺集成测试验证）
- 签字并发：两个用户同时对同一报告签字（prerequisite 校验 + 状态机联动的并发安全性）
- gate_eval_id 过期窗口竞争：5 分钟 TTL 边界时刻的签字请求

### Worker 故障恢复

- Redis 宕机 → 恢复：audit_log_writer_worker 降级队列切换 + 恢复后数据完整性
- 进程重启 asyncio.Queue 丢失：降级队列中未消费的日志条目丢失场景
- SLA worker / outbox_replay_worker 异常退出后的自动恢复

### 更多 PBT（属性测试）

- Gate 规则顺序无关性：同一组规则以任意顺序执行，最终 decision 相同
- Readiness 聚合交换律：groups 内 findings 顺序不影响 ready 判定
- Retention 时间边界：archived_at + 3652d 精确到秒的边界条件
- 签字状态机幂等性：重复签字请求不产生副作用
- 归档 section_progress 断点续传：任意步骤失败后 retry 从正确位置恢复
