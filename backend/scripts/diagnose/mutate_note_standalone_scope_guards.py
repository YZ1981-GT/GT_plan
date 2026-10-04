"""变异检验：把本轮每处修复逐一回退，守卫**必须**打红。

用法（仓库根）：
    python backend/scripts/diagnose/mutate_note_standalone_scope_guards.py

每条变异：备份原始字节 → 改文件 → 跑指定测试 → 断言 rc != 0 → 按原始字节恢复。
任何一条"改坏了还绿"或"锚点没命中（= 没真正变异）"都汇总为存活，脚本以非零退出。

🔴 两个踩过的坑，写死在这里：
  · 本仓 `core.autocrlf=true` ⇒ **.py / .json 磁盘上都是 CRLF**，按 `\\n` 写锚点必 0 命中。
    故文本类变异统一在 LF 归一后的副本上做（恢复时写回原始字节，不留行尾 churn）。
  · 章节标题不能凭记忆写（soe 七 是「合并范围的变化」不是「企业合并及合并财务报表」，
    listed 十六 是「母公司财务报表主要项目注释」不是「公司财务报表主要项目注释」）
    ⇒ 种子 scope 类变异改走 JSON 按 `section_number` 定位，不碰标题。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
# 🔴 用 `sys.executable` 而不是写死 `.venv/Scripts/python.exe`：后者是 Windows 专有路径，
#    在 CI（ubuntu-latest）上不存在 ⇒ `subprocess.run` 抛 FileNotFoundError、脚本以
#    traceback 退出 ⇒ 这个门禁在 CI 上**永远红**（不是恒绿，但同样是永假门禁：
#    红成常态就没人看）。下面还显式断言解释器存在，把失败原因说清楚而不是堆栈。
PY = Path(sys.executable)

SCOPE_TEST = "tests/test_note_standalone_consolidated_only_scope.py"
J_TEST = "tests/workpaper_sync/test_task52_j_cycle_migration.py"
ROW_TEST = "tests/test_disclosure_row_level_merge.py"
TRIM_TEST = "tests/procedure_trim/test_task23_zero_regression.py"

CATALOG = BACKEND / "app" / "services" / "note_section_catalog.py"
SYNC = BACKEND / "app" / "services" / "wp_disclosure_sync_service.py"
ENGINE = BACKEND / "app" / "services" / "disclosure_engine.py"
SOE_TPL = BACKEND / "data" / "note_template_soe.json"
LISTED_TPL = BACKEND / "data" / "note_template_listed.json"
J_SLICE = BACKEND / "data" / "workpaper_sync_j_cycle_manifest_slice.json"
CONTENT_UTILS = BACKEND / "app" / "services" / "note_content_utils.py"
J_TEST_FILE = BACKEND / "tests" / "workpaper_sync" / "test_task52_j_cycle_migration.py"
ROW_TEST_FILE = BACKEND / "tests" / "test_disclosure_row_level_merge.py"


@dataclass
class Mutation:
    mid: str
    what: str
    tests: list[str]
    path: Path | None = None
    old: str = ""
    new: str = ""
    count: int = 1
    node: str | None = None
    extra: list[tuple[Path, str, str]] = field(default_factory=list)
    # 种子 scope 回退：(文件, section_number, 新 scope)
    scope_patch: tuple[Path, str, str] | None = None
    # 追加式变异：往文件尾部加一行
    append_to: Path | None = None
    append_text: str = ""


MUTATIONS: list[Mutation] = [
    Mutation("M1", "种子回退：soe 十二（母公司章）改回 scope=both", [SCOPE_TEST],
             scope_patch=(SOE_TPL, "十二", "both")),
    Mutation("M2", "种子回退：soe 七（合并范围的变化）改回 scope=both", [SCOPE_TEST],
             scope_patch=(SOE_TPL, "七", "both")),
    Mutation("M3", "种子回退：listed 十六（母公司章）改回 scope=both", [SCOPE_TEST],
             scope_patch=(LISTED_TPL, "十六", "both")),
    Mutation(
        "M4", "判据变体兜底改成归一（未知变体按 soe 判）⇒ listed/custom 被国企口径误杀",
        [SCOPE_TEST], path=CATALOG,
        old='variant = (template_type or "").strip().lower()\n'
            '    if variant not in ("soe", "listed"):\n'
            "        return True",
        new="variant = normalize_template_type(template_type)\n"
            "    if False:\n"
            "        return True",
    ),
    Mutation(
        "M5", "读侧：去掉目录树的口径过滤", [SCOPE_TEST], path=ENGINE,
        old="        template_type, report_scope = await self._project_scope_columns(project_id)\n"
            "        if template_type is not None:",
        new="        template_type, report_scope = await self._project_scope_columns(project_id)\n"
            "        if False:",
    ),
    Mutation(
        "M6", "读侧 fail-open 反转：解析不出口径时当成 soe/standalone 过滤",
        [SCOPE_TEST], path=ENGINE,
        old="        if not isinstance(template_type, str):\n            return None, None",
        new='        if not isinstance(template_type, str):\n            return "soe", "standalone"',
        node=f"{SCOPE_TEST}::TestNotesTreeFiltersByProjectScope",
    ),
    Mutation(
        "M7", "写侧（workpaper）：口径守卫挪到软删复活**之后**（存量清理会被复活）",
        [SCOPE_TEST], path=SYNC,
        old="    if note is None and _section_blocked_for_project(\n"
            "        section_id, project_template_type, project_report_scope\n"
            "    ):\n"
            "        logger.info(\n"
            '            "wp_disclosure_sync: skip %s for project=%s (not applicable to project "\n'
            '            "report scope %s/%s)",\n'
            "            section_id, project_id, project_template_type, project_report_scope,\n"
            "        )\n"
            "        return _scope_skip_result(section_id, now)\n\n"
            "    # 软删行复活：唯一索引",
        new="    # 软删行复活：唯一索引",
        extra=[(
            SYNC,
            "    created = False\n    blocked_by_manual_override = False\n",
            "    created = False\n    blocked_by_manual_override = False\n"
            "    if note is None and _section_blocked_for_project(\n"
            "        section_id, project_template_type, project_report_scope\n"
            "    ):\n"
            "        return _scope_skip_result(section_id, now)\n",
        )],
    ),
    Mutation(
        "M8", "写侧（workpaper）：整条口径守卫失效", [SCOPE_TEST], path=SYNC,
        old="    if note is None and _section_blocked_for_project(",
        new="    if False and _section_blocked_for_project(",
    ),
    Mutation(
        "M9", "写侧（html）：整条口径守卫失效", [SCOPE_TEST], path=SYNC,
        old="            if _section_blocked_for_project(\n"
            "                section_id, project_template_type, project_report_scope\n"
            "            ):",
        new="            if False and _section_blocked_for_project(\n"
            "                section_id, project_template_type, project_report_scope\n"
            "            ):",
    ),
    Mutation(
        "M10", "守卫改按 v2 准则取变体（真库有项目 template_type=listed 而 v2=soe）",
        [SCOPE_TEST], path=SYNC,
        old="        project_report_scope,\n    ) = await _resolve_project_sync_facts(db, project_id)",
        new="        project_report_scope,\n    ) = await _resolve_project_sync_facts(db, project_id)\n"
            "    project_template_type = (project_standard or {}).get('entity_type')\n"
            "    project_report_scope = (project_standard or {}).get('scope')",
        node=f"{SCOPE_TEST}::TestSyncFromWorkpaperRespectsScope",
    ),
    Mutation(
        "M11", "J slice 锚点回退到位移前的 #L469",
        [f"{J_TEST}::TestHtmlCounterpartIsSourceBacked::test_second_write_path_sites_are_all_real"],
        path=J_SLICE,
        old="j1/inspection/J1TabGeneralCheck.vue#L480",
        new="j1/inspection/J1TabGeneralCheck.vue#L469",
        count=3,
    ),
    Mutation(
        "M12", "守卫回退成「只扣已删的 J 贡献」（跨循环假红重现）",
        [f"{J_TEST}::TestOrphanDualModeInventory::"
         "test_shared_base_consumer_counts_are_recomputed_both_ways"],
        path=J_TEST_FILE,
        old='expected_narrow = shared["statement_position_consumers"] - len(deleted_sites)',
        new='expected_narrow = shared["statement_position_consumers"] - len(deleted_j_sites)',
    ),
    Mutation(
        "M13", "J slice 的消费边清单删一条（分母自检必须抓住）",
        [f"{J_TEST}::TestOrphanDualModeInventory::"
         "test_shared_base_consumer_counts_are_recomputed_both_ways"],
        path=J_SLICE,
        old='        "audit-platform/frontend/src/components/workpaper/composables/'
            'useN2DualMode.ts#L2",\n',
        new="",
    ),
    Mutation(
        "M14", "行级合并用例回退成陈旧的 BS-037",
        [f"{ROW_TEST}::TestTableLevelTotalRowSurvives"], path=ROW_TEST_FILE,
        old='(VARIANT_SOE, "八、91", "资产负债表中的列报项目和相关信息", "BS-050", "合计")',
        new='(VARIANT_SOE, "八、91", "资产负债表中的列报项目和相关信息", "BS-037", "合计")',
    ),
    Mutation(
        "M15", "既有附注链路 import 联动模块（加法式前提被破坏）",
        [f"{TRIM_TEST}::TestNoteChainUnchanged::"
         "test_existing_chain_never_imports_linkage_module"],
        append_to=CONTENT_UTILS,
        append_text="\nfrom app.services.procedure_trim_note_linkage import (  # noqa: F401\n"
                    "    apply_note_linkage,\n)\n",
    ),
]

# 🔴 唯一 deselect：该判据比的是「工作树 vs HEAD 字节相等」，本轮确实改了
# `disclosure_engine.py`（已在该测试类的文档串里如实登记）⇒ 未提交前必红、一提交就自愈。
# 把它算进基线会让整个检验无法起跑。它守的东西由同类新判据
# `test_existing_chain_never_imports_linkage_module` 接住（与提交时点无关），
# 后者正是 M15 的目标 ⇒ 这里 deselect 不产生盲区。
DESELECT = (
    f"{TRIM_TEST}::TestNoteChainUnchanged::"
    "test_existing_chain_file_bytes_equal_head[backend/app/services/disclosure_engine.py]"
)
BASELINE = [SCOPE_TEST, ROW_TEST, TRIM_TEST]


def run(targets: list[str]) -> int:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", *targets, "-q", "--tb=no",
            "-p", "no:cacheprovider", "--no-header", "--deselect", DESELECT,
        ],
        cwd=str(BACKEND), capture_output=True, env=env,
    )
    return proc.returncode


def apply_text(path: Path, old: str, new: str, want: int) -> str | None:
    """在 LF 归一副本上替换；命中数不符返回错误说明。"""
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    hits = text.count(old)
    if hits != want:
        return f"锚点命中 {hits} 次（期望 {want}）"
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    return None


def apply_scope(path: Path, section_number: str, new_scope: str) -> str | None:
    data = json.loads(path.read_bytes().decode("utf-8"))
    found = [s for s in data.get("sections", []) if s.get("section_number") == section_number]
    if len(found) != 1:
        return f"section_number={section_number!r} 命中 {len(found)} 条（期望 1）"
    if found[0].get("scope") == new_scope:
        return f"section_number={section_number!r} 的 scope 本来就是 {new_scope}（变异无效）"
    found[0]["scope"] = new_scope
    path.write_bytes(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return None


def main() -> int:
    if not PY.exists():
        print(f"🔴 解释器不存在：{PY} —— 变异检验无从起跑（不是判据失败）")
        return 2
    print("=== 基线（未变异）必须全绿 ===")
    rc = run(BASELINE)
    print(f"  baseline rc={rc}")
    if rc != 0:
        print("🔴 基线就不绿 —— 变异检验无意义，先修基线")
        return 2

    survived: list[str] = []
    for m in MUTATIONS:
        touched = [p for p in (m.path, m.append_to) if p is not None]
        touched += [p for p, _, _ in m.extra]
        if m.scope_patch:
            touched.append(m.scope_patch[0])
        backups = {p: p.read_bytes() for p in set(touched)}
        try:
            err: str | None = None
            if m.scope_patch:
                err = apply_scope(*m.scope_patch)
            elif m.append_to is not None:
                data = m.append_to.read_bytes()
                m.append_to.write_bytes(data + m.append_text.encode("utf-8"))
            else:
                assert m.path is not None
                err = apply_text(m.path, m.old, m.new, m.count)
                if err is None:
                    for p, old, new in m.extra:
                        err = apply_text(p, old, new, 1)
                        if err:
                            break
            if err:
                print(f"{m.mid} SKIP   {err}: {m.what}")
                survived.append(f"{m.mid}（{err}，未真正变异）")
                continue
            code = run([m.node] if m.node else m.tests)
            print(f"{m.mid} {'KILLED' if code else '🔴 SURVIVED'} rc={code}  {m.what}")
            if code == 0:
                survived.append(f"{m.mid}: {m.what}")
        finally:
            for p, data in backups.items():
                p.write_bytes(data)

    print("\n=== 恢复后基线复跑（证明恢复干净）===")
    rc = run(BASELINE)
    print(f"  baseline rc={rc}")
    if rc != 0:
        print("🔴 恢复不干净")
        return 2
    if survived:
        print("\n🔴 以下变异存活（守卫假绿）：")
        for s in survived:
            print("  -", s)
        return 1
    print(f"\n✅ {len(MUTATIONS)} 条变异全部被杀")
    return 0


if __name__ == "__main__":
    sys.exit(main())
