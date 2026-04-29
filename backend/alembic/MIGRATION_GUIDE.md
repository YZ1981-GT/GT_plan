# Alembic 迁移规范

## 当前状态

- 基线：`001_consolidated_baseline`（no-op marker，实际 schema 由 create_all 创建）
- Phase 13-16 各有独立迁移脚本，通过 `a2f355648e85_merge_phase13_to_16` 合并为单头
- 当前 head：`a2f355648e85`

## 新增迁移规则

1. **线性链**：所有新迁移必须基于当前唯一 head，禁止分叉
2. **命名规范**：`{序号}_{简短描述}.py`，如 `002_add_tenant_id.py`
3. **必须包含 downgrade**：每个 upgrade 必须有对应的 downgrade（除基线外）
4. **IF NOT EXISTS**：DDL 语句使用 `IF NOT EXISTS` / `IF EXISTS` 保证幂等
5. **数据迁移分离**：schema 变更和数据迁移分开为两个脚本

## 创建新迁移

```bash
# 自动生成（对比 ORM 模型与数据库差异）
alembic revision --autogenerate -m "描述"

# 手动创建空迁移
alembic revision -m "描述"
```

## 验证流程

```bash
# 检查当前 head
alembic heads

# 升级到最新
alembic upgrade head

# 验证可回滚
alembic downgrade -1
alembic upgrade head
```

## 本地开发初始化

新环境不走迁移链，直接：
```bash
python backend/scripts/_init_tables.py
python backend/scripts/_create_admin.py
alembic stamp head
```
