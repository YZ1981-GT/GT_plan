"""
check_gitleaks_config.py — 验证 .gitleaks.toml 配置结构完整性

当 gitleaks 二进制不可用时（如本地开发环境），本脚本作为替代验证手段：
1. 解析 .gitleaks.toml（TOML 语法正确性）
2. 断言 extend.useDefault = true（继承默认规则集）
3. 断言 allowlist.paths 包含 .env.example 豁免
4. 断言 allowlist.regexes 包含 .env.example 中的关键占位符

CI 环境中 gitleaks-action 提供自己的二进制做真实拦截；
本脚本仅验证配置结构，确保 allowlist 不被误改。

用法：
    python backend/scripts/check/check_gitleaks_config.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Python 3.11+ 内置 tomllib；3.10 降级 tomli
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        print("❌ 需要 Python 3.11+ 或安装 tomli: pip install tomli")
        sys.exit(1)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]  # backend/scripts/check/file.py → repo root
    config_path = repo_root / ".gitleaks.toml"

    if not config_path.exists():
        print(f"❌ 未找到 {config_path}")
        return 1

    # 1. 解析 TOML
    try:
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
    except Exception as e:
        print(f"❌ .gitleaks.toml 解析失败: {e}")
        return 1

    print("✅ .gitleaks.toml TOML 语法正确")
    errors: list[str] = []

    # 2. extend.useDefault = true
    extend = config.get("extend", {})
    if extend.get("useDefault") is not True:
        errors.append("extend.useDefault 必须为 true（继承默认规则集）")
    else:
        print("✅ extend.useDefault = true")

    # 3. allowlist.paths 包含 .env.example
    allowlist = config.get("allowlist", {})
    paths = allowlist.get("paths", [])
    env_example_covered = any(".env.example" in p or "env\\.example" in p for p in paths)
    if not env_example_covered:
        errors.append("allowlist.paths 缺少 .env.example 豁免")
    else:
        print("✅ allowlist.paths 包含 .env.example 豁免")

    # 4. allowlist.regexes 包含关键占位符
    regexes = allowlist.get("regexes", [])
    regexes_joined = " ".join(regexes)

    required_placeholders = [
        ("change-me-to-a-random-secret", "JWT_SECRET_KEY 占位符"),
        ("postgres:postgres@", "开发 PG 连接占位符"),
        ("admin123", "测试密码占位符"),
        ("not-needed", "通用占位符"),
    ]

    for placeholder, desc in required_placeholders:
        if placeholder in regexes_joined:
            print(f"✅ allowlist.regexes 包含 {desc} ({placeholder})")
        else:
            errors.append(f"allowlist.regexes 缺少 {desc} ({placeholder})")

    # 5. 汇总
    if errors:
        print("\n❌ 验证失败:")
        for err in errors:
            print(f"   - {err}")
        return 1

    print("\n✅ .gitleaks.toml 配置结构验证通过")
    print("   (实际拦截测试由 CI gitleaks-action 执行，本地 hook 在 gitleaks 缺失时优雅降级)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
