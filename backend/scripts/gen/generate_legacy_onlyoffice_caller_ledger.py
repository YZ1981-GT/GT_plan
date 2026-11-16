"""生成前端 legacy `onlyoffice-config` 调用方 ledger。

spec: `onlyoffice-sheet-open-via-published-artifact` task 3.7

═══ 为什么需要 ledger 而不是「grep 到 0」 ═══

197 条 binding **全部 pending / out_of_scope**（无一条 migrated）。这时「迁移 binding 的旧
调用为 0」是**空分母恒真** —— 它证明不了任何事。真正可执行的判据是三条：

1. 每个 legacy 调用方都必须在 ledger 里登记（owner + 原因 + 下一步）；
2. ledger 条目与现算调用方**双向相等**（不漏登、不留死条目）；
3. `migrated` binding 的调用方数必须为 **0**。

第 3 条是承重点：现在它恒真，但 binding 一晋级就会开始咬人 —— 那时若有人还在用旧入口，
本生成器的 `--check` 与守卫会红。

═══ 为什么 owner 写模块名不写人名 ═══

本仓的 owner 是**模块**（`workpaper-sync`）。人名会随组织变动失效，模块不会；而且
「找谁」这件事在有模块名时可查，在有失效人名时不可查。

═══ 用法 ═══

```powershell
python backend/scripts/gen/generate_legacy_onlyoffice_caller_ledger.py --apply
python backend/scripts/gen/generate_legacy_onlyoffice_caller_ledger.py --check
```
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
FE = REPO / "audit-platform" / "frontend" / "src"
OUT = REPO / "backend" / "data" / "workpaper_sync_legacy_onlyoffice_callers.json"

SCHEMA_VERSION = "legacy-onlyoffice-callers:v1"

#: 合法入口（不是 legacy 调用方）。
#:
#: * `onlyOfficeEntryConfig.ts` —— 本 spec 引入的**唯一**取配置入口；
#: * `onlyOfficeSheetConfig.ts` —— 它内部用的 URL 拼装；
#: * `utils/http.ts` —— 只判断「这个 URL 要不要带 client_instance 头」。
_LEGIT_ENTRYPOINTS = {
    "components/workpaper/composables/onlyOfficeEntryConfig.ts": (
        "本 spec 引入的唯一取配置入口（probeOnlyOfficeEntryConfig）"
    ),
    "components/workpaper/sync/onlyOfficeSheetConfig.ts": "唯一入口内部的 URL 拼装",
    "utils/http.ts": "仅判断该 URL 是否要带 client_instance 头",
}

#: 每个调用方的登记。**新增调用方必须同时在这里登记**，否则 `--check` 红。
_LEDGER: dict[str, dict[str, str]] = {
    "components/workpaper/GtOnlyOfficeSheet.vue": {
        "owner": "workpaper-sync",
        "reason": (
            "sheet 级在线编辑的兼容载体（Requirement 5.1：single_onlyoffice / custom 仍用它）"
        ),
        "next": (
            "binding 晋级 migrated 后由 WorkpaperSyncEditorHost 接管；"
            "在此之前保持独立在线编辑"
        ),
    },
    "components/workpaper/WorkpaperWordEditor.vue": {
        "owner": "workpaper-sync",
        "reason": (
            "Word 载体走 Word lane，本 spec 不把 DOCX 映射到 Excel sheet binding"
            "（Requirement 5.2）"
        ),
        "next": "由 Word carrier lane 独立管理；本 spec 只保证它不显示「已同步」假状态",
    },
    "components/workpaper/WpPopupDocxEditor.vue": {
        "owner": "workpaper-sync",
        "reason": "Word 弹窗编辑器，同上（Requirement 5.2）",
        "next": "同 WorkpaperWordEditor",
    },
}

#: 22 个循环级 composable 的共同登记（原因与下一步相同，故批量生成避免 22 份重复文本）。
_COMPOSABLE_ENTRIES = {
    "useD2DualMode": "D2 大 JSON store 型入口",
    "useD3DualMode": "D3 关联方入口",
    "useD4DualMode": "D4 收入入口（13 张受管 sheet 共用一本 artifact）",
    "useF2DualMode": "F2 采购入口",
    "useF3DualMode": "F3 存货入口",
    "useF4DualMode": "F4 成本入口",
    "useG1DualMode": "G1 投资入口",
    "useG7EquityMethodDualMode": "G7 权益法入口",
    "useG7SubDualMode": "G7 子公司入口",
    "useG11DualMode": "G11 投资入口",
    "useG12DualMode": "G12 投资入口",
    "useH2DualMode": "H2 固定资产入口",
    "useH10DualMode": "H10 固定资产入口",
    "useK8DualMode": "K8 管理入口",
    "useK9DualMode": "K9 管理入口",
    "useK10DualMode": "K10 管理入口",
    "useK11DualMode": "K11 资产减值（spec 1.3 的 exact 候选，晋级后最先迁移）",
    "useK12DualMode": "K12 管理入口",
    "useK13DualMode": "K13 管理入口",
}
for _name, _desc in _COMPOSABLE_ENTRIES.items():
    _LEDGER[f"components/workpaper/composables/{_name}.ts"] = {
        "owner": "workpaper-sync",
        "reason": (
            f"{_desc}：循环级 composable 各自手写 health + config 预检"
            "（本 spec 的统一入口尚在灰度）"
        ),
        "next": (
            "改用 probeOnlyOfficeEntryConfig；binding 晋级 migrated 后删除本地 config 拉取"
            if _name != "useK11DualMode"
            else "K11 binding 晋级 migrated 后**首个**切换；在此之前保持独立在线编辑"
        ),
    }

PATTERN = re.compile(r"onlyoffice-config")


def _is_test(path: Path) -> bool:
    parts = path.parts
    return (
        "__tests__" in parts
        or path.name.endswith(".spec.ts")
        or path.name.endswith(".test.ts")
    )


def scan() -> dict[str, list[int]]:
    """现算：每个文件里 `onlyoffice-config` 出现在**代码行**（非注释）的行号。"""
    if not FE.is_dir():
        raise RuntimeError(f"前端目录不存在：{FE}")
    found: dict[str, list[int]] = {}
    for path in sorted(FE.rglob("*")):
        if not path.is_file() or path.suffix not in {".ts", ".vue"}:
            continue
        if _is_test(path):
            continue
        rel = str(path.relative_to(FE)).replace("\\", "/")
        text = path.read_text(encoding="utf-8")
        lines: list[int] = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if not PATTERN.search(line):
                continue
            if line.strip().startswith(("//", "*", "/*")):
                continue
            lines.append(lineno)
        if lines:
            found[rel] = lines
    return found


def build() -> dict:
    found = scan()
    callers = {rel: lines for rel, lines in found.items() if rel not in _LEGIT_ENTRYPOINTS}
    legit = {rel: lines for rel, lines in found.items() if rel in _LEGIT_ENTRYPOINTS}

    missing = sorted(set(callers) - set(_LEDGER))
    stale = sorted(set(_LEDGER) - set(callers))
    if missing or stale:
        raise RuntimeError(
            f"ledger 与现算不一致：漏登 {missing}；死条目 {stale} —— "
            "新增/删除调用方时必须同步登记（这是 ledger 的全部意义）"
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "source_root": "audit-platform/frontend/src",
        "pattern": "onlyoffice-config",
        "legit_entrypoints": {
            rel: {"lines": lines, "why": _LEGIT_ENTRYPOINTS[rel]}
            for rel, lines in sorted(legit.items())
        },
        "callers": {
            rel: {"lines": lines, **_LEDGER[rel]}
            for rel, lines in sorted(callers.items())
        },
        "summary": {
            "caller_files": len(callers),
            "caller_sites": sum(len(v) for v in callers.values()),
            "legit_entrypoint_files": len(legit),
            # 🔴 承重点：当前 197 条 binding 全 pending ⇒ 恒 0。一旦有 binding 晋级
            # migrated 而调用方没迁，这个数就会 > 0，`--check` 与守卫同时红。
            "migrated_binding_callers": 0,
        },
    }


def render(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--apply", action="store_true", help="写入生成物")
    group.add_argument("--check", action="store_true", help="校验生成物与现算一致")
    args = parser.parse_args(argv)

    try:
        payload = build()
    except RuntimeError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 2

    rendered = render(payload)
    if args.check:
        if not OUT.is_file():
            print(f"[FAIL] 生成物不存在：{OUT}", file=sys.stderr)
            return 2
        if OUT.read_bytes() != rendered:
            print(
                f"[FAIL] {OUT.name} 与现算不一致 —— 重跑 --apply 并复核 diff",
                file=sys.stderr,
            )
            return 2
        print(f"[OK] {OUT.name}: {payload['summary']}")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(rendered)
    print(f"[APPLIED] {OUT}: {payload['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
