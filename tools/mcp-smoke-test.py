#!/usr/bin/env python3
"""MCP 服务器冒烟测试 — initialize + list_tools + 代表性 tool call。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
NPX = r"C:\Program Files\nodejs\npx.cmd"
PYTHON = sys.executable

# (name, command, args, env, probe_tool, probe_args)
SERVERS: list[tuple[str, str, list[str], dict[str, str] | None, str | None, dict | None]] = [
    (
        "gt-plan",
        PYTHON,
        [str(ROOT / "tools" / "gt-plan-mcp" / "server.py")],
        {"GT_PLAN_ROOT": str(ROOT)},
        "wp_lookup",
        {"wp_code": "H1"},
    ),
    (
        "postgres",
        "docker",
        [
            "run",
            "-i",
            "--rm",
            "-e",
            "DATABASE_URI",
            "crystaldba/postgres-mcp",
            "--access-mode=restricted",
        ],
        {
            "DATABASE_URI": "postgresql://postgres:postgres@host.docker.internal:5432/audit_platform"
        },
        "list_schemas",
        {},
    ),
    (
        "postgres-sql",
        "docker",
        [
            "run",
            "-i",
            "--rm",
            "-e",
            "DATABASE_URI",
            "crystaldba/postgres-mcp",
            "--access-mode=restricted",
        ],
        {
            "DATABASE_URI": "postgresql://postgres:postgres@host.docker.internal:5432/audit_platform"
        },
        "execute_sql",
        {"sql": "SELECT COUNT(*) AS n FROM information_schema.tables WHERE table_schema = 'public'"},
    ),
    (
        "docker-mcp",
        NPX,
        ["-y", "mcp-docker-server"],
        None,
        "list_containers",
        {"all": False},
    ),
    (
        "context7",
        NPX,
        ["-y", "@upstash/context7-mcp"],
        os.environ.get("CONTEXT7_API_KEY")
        and {"CONTEXT7_API_KEY": os.environ["CONTEXT7_API_KEY"]}
        or None,
        "resolve-library-id",
        {"libraryName": "vue", "query": "vue 3"},
    ),
    (
        "github",
        "docker",
        [
            "run",
            "-i",
            "--rm",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "-e",
            "GITHUB_TOOLSETS",
            "ghcr.io/github/github-mcp-server:latest",
        ],
        {
            "GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get(
                "GITHUB_PERSONAL_ACCESS_TOKEN", ""
            ),
            "GITHUB_TOOLSETS": "repos",
        },
        None,  # 无 token 时只测 list_tools
        None,
    ),
    (
        "codegraph",
        NPX,
        [
            "-y",
            "@colbymchenry/codegraph",
            "serve",
            "--mcp",
            "--no-watch",
            "--path",
            str(ROOT),
        ],
        {"NODE_OPTIONS": "--max-old-space-size=512"},
        "codegraph_status",
        {},
    ),
]


async def probe_server(
    name: str,
    command: str,
    args: list[str],
    env: dict[str, str] | None,
    probe_tool: str | None,
    probe_args: dict | None,
) -> dict:
    merged_env = {**os.environ, **(env or {})}
    params = StdioServerParameters(command=command, args=args, env=merged_env)
    result: dict = {"name": name, "ok": False, "tools": [], "probe": None, "error": None}
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_resp = await session.list_tools()
                result["tools"] = [t.name for t in tools_resp.tools]
                result["ok"] = len(result["tools"]) > 0

                if probe_tool and probe_tool in result["tools"]:
                    try:
                        call = await session.call_tool(
                            probe_tool, arguments=probe_args or {}
                        )
                        text_parts = [
                            c.text for c in call.content if hasattr(c, "text") and c.text
                        ]
                        result["probe"] = {
                            "tool": probe_tool,
                            "ok": not call.isError,
                            "preview": (text_parts[0][:300] if text_parts else str(call.content))[:300],
                        }
                    except Exception as exc:  # noqa: BLE001
                        result["probe"] = {"tool": probe_tool, "ok": False, "error": str(exc)}
                elif probe_tool is None:
                    result["probe"] = {"skipped": "no probe configured"}
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


async def main() -> int:
    print("GT_plan MCP smoke test\n" + "=" * 40)
    failed = 0
    for entry in SERVERS:
        name, cmd, args, env, probe_tool, probe_args = entry
        print(f"\n[{name}] starting...")
        res = await probe_server(name, cmd, args, env, probe_tool, probe_args)
        if res["error"]:
            print(f"  FAIL initialize: {res['error']}")
            failed += 1
            continue
        print(f"  tools ({len(res['tools'])}): {', '.join(res['tools'][:8])}{'...' if len(res['tools']) > 8 else ''}")
        if res["probe"]:
            if res["probe"].get("skipped"):
                print(f"  probe: skipped (tools/list only)")
            elif res["probe"].get("ok"):
                print(f"  probe {res['probe']['tool']}: OK")
                preview = res["probe"].get("preview", "")
                if preview:
                    print(f"    preview: {preview[:120]}...")
            else:
                err = res["probe"].get("error") or res["probe"].get("preview")
                print(f"  probe {res['probe'].get('tool')}: WARN — {err}")
                if name == "github" and not os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
                    print("    (GITHUB_PERSONAL_ACCESS_TOKEN 未设置，仅 list_tools 通过即可)")
                else:
                    failed += 1
        if not res["ok"]:
            failed += 1
    print("\n" + "=" * 40)
    if failed:
        print(f"FAILED: {failed} server(s)")
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
