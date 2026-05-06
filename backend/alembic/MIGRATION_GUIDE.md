# Alembic 迁移规范

## 当前状态

- 基线：`001_consolidated_baseline`（no-op marker，实际 schema 由 `create_all` 创建）
- Phase 13-16 各有独立迁移脚本，通过 `a2f355648e85_merge_phase13_to_16` 合并为单头
- 当前 head：`phase17_005_import_event_consumptions`（Phase 17 导入事件一次性消费）
- **SQLAlchemy 元数据中共 152 张表**（≥ 需求 9.2 要求的 144 张），全部由 `Base.metadata.create_all()` 创建

## 架构决策（ADR-schema-bootstrap）

本项目采用"Baseline + Incremental"双轨模式，**不走 Alembic 全量 autogenerate 链**：

1. **基线创建**：`_init_tables.py` 使用 `Base.metadata.create_all()` 一次性建所有 152 张表
   - 优点：新库部署 < 10 秒，不需逐条执行 36 个历史迁移
   - 优点：模型与 schema 始终一致，不会出现 autogenerate 漏表
   - 代价：放弃了完整的 schema 变更历史链
2. **增量变更**：schema 变更后用 Alembic `autogenerate` 生成补丁迁移（如 phase17_xxx.py）
3. **版本标记**：`alembic stamp head` 让 Alembic 知道当前基线状态

## 表数量核对（需求 9.2）

```bash
# 从元数据查表数（需先扫描所有模型模块）
python -c "
import importlib, pkgutil
from app import models
for _, m, _ in pkgutil.iter_modules(models.__path__, models.__name__ + '.'):
    try: importlib.import_module(m)
    except Exception: pass
from app.models import Base
print(len(Base.metadata.tables))
"
# 预期输出：152（≥ 144）

# 建表后对数据库实测核对
python -c "
import asyncio
from sqlalchemy import text
from app.core.database import async_session
async def check():
    async with async_session() as db:
        r = await db.execute(text(
            \"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'\"
        ))
        print(r.scalar())
asyncio.run(check())
"
```

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
