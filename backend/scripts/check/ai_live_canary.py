"""AI 任务链真实模型 canary（spec llm-linkage-audit-practice-closure 任务 16）。

用法（发布前，需要后端配置的模型可达；只读模型配置，不写业务数据）：
    python backend/scripts/check/ai_live_canary.py --dry-run   # 只校验金标文件
    python backend/scripts/check/ai_live_canary.py             # 对 live=true 的金标调用真实模型

判据（真实模型输出不可预知，只断言平台边界）：
- 权限类用例必须被拒绝且不调用模型；
- 其余用例不得出现“成功且含最终审计意见”的结果；
- 期望 success 的用例若失败，只接受 unavailable / timeout（模型不可达）以外的原因记为失败；
- 至少一条用例真实成功，且返回实际部署位置。
退出码：0 通过；2 有用例违背判据；3 模型全部不可达（transport 未验证）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GOLDEN = BACKEND / "data" / "ai_golden_cases.json"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_REQUIRED_KEYS = {"id", "category", "task_code", "role", "user_prompt", "fake_output", "expect"}


def load_cases(path: Path = GOLDEN) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = list(data.get("cases") or [])
    for case in cases:
        missing = _REQUIRED_KEYS - set(case)
        if missing:
            raise ValueError(f"金标 {case.get('id')} 缺字段：{sorted(missing)}")
    return cases


async def _run_live(cases: list[dict]) -> int:
    from app.services.ai_task_executor import invoke_ai_task
    from app.services.ai_task_verifier import _FINAL_OPINION_RE

    failures: list[str] = []
    succeeded = 0
    unreachable = 0
    for case in cases:
        invocation = await invoke_ai_task(
            case["task_code"],
            user_prompt=case["user_prompt"],
            context_documents=case.get("context_documents") or None,
            role=case["role"],
            action=case.get("action"),
            verifier_facts=case.get("verifier_facts"),
        )
        result = invocation.result
        status = result.status.value
        expect = case["expect"]
        line = f"{case['id']}: {status} {result.error_code or ''} model={result.model_name} deployment={result.deployment}"
        print(line)
        if expect.get("model_called") is False:
            if status != "rejected" or result.error_code != expect.get("error_code"):
                failures.append(f"{case['id']} 应在调用模型前被拒绝")
            continue
        if status in {"unavailable", "timeout"}:
            unreachable += 1
            continue
        if status == "success":
            succeeded += 1
            if _FINAL_OPINION_RE.search(result.text or ""):
                failures.append(f"{case['id']} 成功结果含最终审计意见")
            if not result.deployment:
                failures.append(f"{case['id']} 成功结果未返回实际部署位置")
    if failures:
        print("[FAIL]\n  " + "\n  ".join(failures))
        return 2
    if succeeded == 0:
        print(f"[UNVERIFIED] 模型不可达（{unreachable} 条），真实 transport 未验证")
        return 3
    print(f"[PASS] live 用例 {len(cases)} 条，真实成功 {succeeded} 条")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    cases = [case for case in load_cases() if case.get("live")]
    if args.dry_run:
        from app.services.ai_task_registry import get_ai_task_spec

        for case in cases:
            get_ai_task_spec(case["task_code"])
        print(f"[OK] 金标 live 用例 {len(cases)} 条，任务均已登记")
        return 0
    return asyncio.run(_run_live(cases))


if __name__ == "__main__":
    sys.exit(main())
