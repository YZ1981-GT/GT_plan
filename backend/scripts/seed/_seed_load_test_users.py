"""批量创建压测用户 seed 脚本（pg-pooling-and-load-test spec Task 10）。

用法:
  # 创建 100 个测试用户（默认）
  python backend/scripts/seed/_seed_load_test_users.py

  # 创建 6000 个
  python backend/scripts/seed/_seed_load_test_users.py --count 6000

  # 清理所有 loadtest_* 用户
  python backend/scripts/seed/_seed_load_test_users.py --cleanup

说明:
  - 用户名格式: loadtest_0001 ~ loadtest_NNNN
  - 密码统一: loadtest123
  - 角色: auditor
  - 关联项目: df5b8403（首汽租车_2025）
  - `_` 前缀 = 一次性脚本，用完即删

Validates: Requirements 4.4
"""

from __future__ import annotations

import argparse
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from sqlalchemy import create_engine, text

from app.core.security import hash_password

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/audit_platform",
).replace("+asyncpg", "+psycopg2")

# 目标项目 ID
TARGET_PROJECT_ID = "df5b8403-0000-0000-0000-000000000000"
# 密码统一
PASSWORD = "loadtest123"
# 用户名前缀
PREFIX = "loadtest_"


def seed_users(count: int) -> None:
    """批量创建 N 个测试用户并关联到目标项目。"""
    engine = create_engine(DB_URL)
    hashed = hash_password(PASSWORD)

    with engine.connect() as conn:
        # 检查目标项目是否存在（使用 LIKE 前缀匹配，因为实际 UUID 可能是短格式存储）
        project = conn.execute(
            text("SELECT id FROM projects WHERE id::text LIKE :prefix"),
            {"prefix": "df5b8403%"},
        ).fetchone()

        if not project:
            print("⚠️  目标项目 df5b8403 不存在，跳过项目关联（用户仍会创建）")
            project_id = None
        else:
            project_id = project[0]
            print(f"✅ 目标项目: {project_id}")

        created = 0
        skipped = 0

        for i in range(1, count + 1):
            username = f"{PREFIX}{i:04d}"
            email = f"{username}@loadtest.local"

            # 检查是否已存在
            exists = conn.execute(
                text("SELECT id FROM users WHERE username = :u"),
                {"u": username},
            ).fetchone()

            if exists:
                skipped += 1
                continue

            uid = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO users (id, username, email, hashed_password, role, is_active, is_deleted) "
                    "VALUES (:id, :u, :e, :p, :r, true, false)"
                ),
                {
                    "id": uid,
                    "u": username,
                    "e": email,
                    "p": hashed,
                    "r": "auditor",
                },
            )

            # 关联到项目（project_assignments 表）
            if project_id:
                # 检查 project_assignments 表是否存在
                try:
                    conn.execute(
                        text(
                            "INSERT INTO project_assignments (id, project_id, user_id, role) "
                            "VALUES (:id, :pid, :uid, :role) "
                            "ON CONFLICT DO NOTHING"
                        ),
                        {
                            "id": uuid.uuid4(),
                            "pid": project_id,
                            "uid": uid,
                            "role": "auditor",
                        },
                    )
                except Exception:
                    pass  # 表不存在或结构不匹配则跳过

            created += 1

            if created % 500 == 0:
                conn.commit()
                print(f"  ... 已创建 {created}/{count}")

        conn.commit()

    engine.dispose()
    print(f"\n完成: 创建 {created} 个用户, 跳过 {skipped} 个已存在用户")
    if project_id:
        print(f"已关联到项目: {project_id}")
    print(f"登录凭据: {PREFIX}0001 ~ {PREFIX}{count:04d} / {PASSWORD}")


def cleanup_users() -> None:
    """删除所有 loadtest_* 用户及其项目关联。"""
    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        # 先删关联
        try:
            deleted_assignments = conn.execute(
                text(
                    "DELETE FROM project_assignments WHERE user_id IN "
                    "(SELECT id FROM users WHERE username LIKE :prefix)"
                ),
                {"prefix": f"{PREFIX}%"},
            ).rowcount
            print(f"删除项目关联: {deleted_assignments} 条")
        except Exception as e:
            print(f"删除项目关联跳过: {e}")

        # 删用户
        deleted_users = conn.execute(
            text("DELETE FROM users WHERE username LIKE :prefix"),
            {"prefix": f"{PREFIX}%"},
        ).rowcount

        conn.commit()

    engine.dispose()
    print(f"删除用户: {deleted_users} 个")


def main() -> None:
    parser = argparse.ArgumentParser(description="批量创建/清理压测用户")
    parser.add_argument("--count", type=int, default=100, help="创建用户数（默认 100）")
    parser.add_argument("--cleanup", action="store_true", help="清理所有 loadtest_* 用户")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_users()
    else:
        seed_users(args.count)


if __name__ == "__main__":
    main()
