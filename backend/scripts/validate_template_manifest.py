#!/usr/bin/env python3
"""校验 template_manifest.json：文件存在、扩展名合法、无 .doc 引用.

Usage:
    python backend/scripts/validate_template_manifest.py
    python backend/scripts/validate_template_manifest.py --strict  # 有 warning 时 exit 1
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许从仓库根或 backend 目录执行
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.template_manifest_loader import TemplateManifestLoader, resolve_template_base_dir


def validate_manifest(*, strict: bool = False) -> int:
    base = resolve_template_base_dir()
    loader = TemplateManifestLoader(base_dir=base)
    warnings = list(loader.validate())

    print(f"manifest version: {loader.version() or '(empty)'}")
    print(f"base dir: {base}")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  - {w}")
        return 1 if strict else 0
    print("OK: no warnings")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate audit report template manifest")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 when any warning is found (CI mode)",
    )
    args = parser.parse_args()
    raise SystemExit(validate_manifest(strict=args.strict))


if __name__ == "__main__":
    main()
