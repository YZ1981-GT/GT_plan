"""从 Project.client_name 抽取去重生成 clients 记录，回填 project.client_id [R7-S3-06 Task 31]

用法：
    python scripts/migrate_clients.py

前置条件：
    - 已执行 round7_clients_20260508 迁移（clients 表已建）
    - DATABASE_URL 环境变量已设置

逻辑：
    1. SELECT DISTINCT client_name FROM projects WHERE client_name IS NOT NULL
    2. 对每个 client_name 调用 normalize_client_name() 去重
    3. INSERT INTO clients (name, normalized_name)
    4. UPDATE projects SET client_id = clients.id WHERE normalize(client_name) = clients.normalized_name
"""
import asyncio
import os
import sys

# 确保可以 import backend 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


def normalize_client_name(name: str) -> str:
    """客户名归一化：去空白、全角→半角、去常见后缀"""
    if not name:
        return ''
    # 全角→半角
    result = ''
    for ch in name:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            result += chr(code - 0xFEE0)
        elif code == 0x3000:
            result += ' '
        else:
            result += ch
    # 去空白
    result = result.strip()
    # 去常见后缀
    suffixes = ['有限公司', '股份有限公司', '有限责任公司', '集团', '科技', 'Co.,Ltd', 'Co., Ltd', 'Inc.', 'Ltd.']
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[:-len(suffix)].strip()
    return result


async def main():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print('ERROR: DATABASE_URL 环境变量未设置')
        sys.exit(1)

    engine = create_async_engine(database_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # 1. 获取所有不重复的 client_name
        result = await db.execute(text(
            "SELECT DISTINCT client_name FROM projects WHERE client_name IS NOT NULL AND client_name != ''"
        ))
        client_names = [row[0] for row in result.fetchall()]
        print(f'找到 {len(client_names)} 个不重复客户名')

        # 2. 归一化去重
        seen = {}  # normalized_name → original_name
        for name in client_names:
            normalized = normalize_client_name(name)
            if normalized and normalized not in seen:
                seen[normalized] = name

        print(f'归一化后 {len(seen)} 个唯一客户')

        # 3. 插入 clients 表
        for normalized, original in seen.items():
            await db.execute(text(
                "INSERT INTO clients (name, normalized_name) VALUES (:name, :normalized) ON CONFLICT (normalized_name) DO NOTHING"
            ), {'name': original, 'normalized': normalized})

        await db.commit()
        print(f'已插入 {len(seen)} 条 clients 记录')

        # 4. 回填 project.client_id
        updated = await db.execute(text("""
            UPDATE projects p
            SET client_id = c.id
            FROM clients c
            WHERE p.client_name IS NOT NULL
              AND p.client_id IS NULL
              AND c.normalized_name = (
                -- 简化归一化：去空白（完整归一化在 Python 侧已处理，此处用 trim 近似匹配）
                TRIM(p.client_name)
              )
        """))
        await db.commit()

        # 精确匹配可能遗漏部分（全角/后缀差异），用 Python 补充
        result = await db.execute(text(
            "SELECT id, client_name FROM projects WHERE client_id IS NULL AND client_name IS NOT NULL AND client_name != ''"
        ))
        unmatched = result.fetchall()
        if unmatched:
            print(f'SQL 精确匹配后仍有 {len(unmatched)} 个项目未关联，尝试 Python 归一化匹配...')
            # 获取所有 clients
            clients_result = await db.execute(text("SELECT id, normalized_name FROM clients"))
            clients_map = {row[1]: row[0] for row in clients_result.fetchall()}

            matched_count = 0
            for proj_id, proj_client_name in unmatched:
                normalized = normalize_client_name(proj_client_name)
                if normalized in clients_map:
                    await db.execute(text(
                        "UPDATE projects SET client_id = :cid WHERE id = :pid"
                    ), {'cid': str(clients_map[normalized]), 'pid': str(proj_id)})
                    matched_count += 1

            await db.commit()
            print(f'Python 归一化补充匹配 {matched_count} 个')

        # 最终统计
        result = await db.execute(text("SELECT COUNT(*) FROM projects WHERE client_id IS NOT NULL"))
        linked = result.scalar()
        result = await db.execute(text("SELECT COUNT(*) FROM projects"))
        total = result.scalar()
        print(f'完成：{linked}/{total} 个项目已关联客户主数据')

    await engine.dispose()


if __name__ == '__main__':
    asyncio.run(main())
