"""豁免表有效性与失效检测守卫。

spec: .kiro/specs/e1-variant-recalc-and-mutation-denominator-closure/
Requirements: 5.6, 8.5 · Property 30

## 为什么需要它

豁免机制的失败形态不是「豁免错了一项」，而是**豁免变成永久免责声明** ——
登记时理由成立，spec 归档后没人回来撤销，于是那个脚本永远不入库、永远不迁共享件。
e-cycle spec 的变异 M20 针对的正是同一形态（「白名单混入不存在的 sheet 名 ⇒
白名单成了免责声明」）。

所以本守卫做两件事：
1. **字段有效性** —— 五个必填字段齐全、reason 有实质内容、日期格式合法、路径存在
2. **失效检测** —— 豁免项引用的 spec 目录若已不在 `.kiro/specs/` 一级下（= 已归档），
   即提示该豁免应当撤销

判据落在「spec 目录是否还在 active 区」这个**结构事实**上，不依赖任何人记得回来改表。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
EXEMPTIONS = REPO / "backend/data/mutation_kit_exemptions.json"
SPECS_DIR = REPO / ".kiro/specs"

#: 本 spec 目录名 —— 用作「扫描机制是否有效」的结构判据（见
#: :func:`test_active_spec_scan_is_not_empty`），不用 active spec 的**数量**做判据。
SELF_SPEC = "e1-variant-recalc-and-mutation-denominator-closure"

REQUIRED_FIELDS = ("script", "spec", "reason", "registered_at", "revoke_when")
MIN_REASON_LEN = 10
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load() -> list[dict[str, Any]]:
    """解析失败一律抛（fail-closed）。"""
    data = json.loads(EXEMPTIONS.read_text(encoding="utf-8"))
    return list(data["exemptions"])


def validate_entry(entry: dict[str, Any]) -> list[str]:
    """字段级校验，返回错误列表（抽成纯函数以便反向自检）。"""
    errs: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in entry or entry[f] in (None, ""):
            errs.append(f"缺必填字段 {f}")
    if not errs:
        if len(str(entry["reason"])) < MIN_REASON_LEN:
            errs.append(
                f"reason 少于 {MIN_REASON_LEN} 字（豁免必须说明为什么现在不能动它）"
            )
        if not DATE_RE.match(str(entry["registered_at"])):
            errs.append("registered_at 必须是 YYYY-MM-DD")
        if len(str(entry["revoke_when"])) < MIN_REASON_LEN:
            errs.append("revoke_when 太短（撤销条件必须可判定）")
    return errs


def active_spec_dirs() -> set[str]:
    """`.kiro/specs/` 一级目录名（归档后会移入 `_archive/`，故不在此集合内）。"""
    if not SPECS_DIR.is_dir():
        return set()
    return {
        p.name for p in SPECS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    }


def find_stale(entries: list[dict[str, Any]], active: set[str]) -> list[tuple[str, str]]:
    """失效检测（抽成纯函数）：spec 已不在 active 区的豁免项。"""
    return [
        (str(e["script"]), str(e["spec"]))
        for e in entries
        if str(e.get("spec", "")) not in active
    ]


def test_exemptions_file_exists_and_parses() -> None:
    assert EXEMPTIONS.exists(), f"豁免表缺失：{EXEMPTIONS}"
    entries = load()
    assert isinstance(entries, list), "exemptions 必须是数组"


def test_every_entry_has_valid_fields() -> None:
    problems: list[str] = []
    for i, entry in enumerate(load()):
        errs = validate_entry(entry)
        if errs:
            problems.append(
                "  [%d] %s → %s" % (i, entry.get("script", "(无 script)"), "; ".join(errs))
            )
    assert not problems, "豁免项字段不合规：\n" + "\n".join(problems)


def test_every_entry_script_path_exists() -> None:
    missing = [
        str(e["script"]) for e in load()
        if not (REPO / str(e["script"])).exists()
    ]
    assert not missing, (
        "豁免项指向不存在的脚本（应删除该豁免项）：\n" + "\n".join("  " + m for m in missing)
    )


def test_no_duplicate_script_entries() -> None:
    scripts = [str(e["script"]) for e in load()]
    dups = sorted({s for s in scripts if scripts.count(s) > 1})
    assert not dups, f"同一脚本被登记多次（撤销时容易漏改）：{dups}"


def test_active_spec_scan_is_not_empty() -> None:
    """扫描本身要有产出 —— 扫到 0 个会让失效检测把**所有**豁免都判成失效（假红）。

    🔴 **判据不用「数量 >= N」**：active spec 数随归档进度自然下降，把当时的环境值
    当基线就是 memory 记的「守卫把错值锁死」的镜像形态（这里表现为假红）。本条第一版
    写 `len(active) >= 3`，2026-08-16 实测即被打红 —— 当时 active 区只剩 2 个
    （本 spec + `workpaper-import-export-lifecycle-closure`），而扫描完全正常。

    改用**结构判据**：本 spec 目录若还在磁盘上，就必须能被扫到 —— 扫描路径写错时
    它同样扫不到，故有区分能力；写成条件形式则本 spec 归档后不会留下假红的雷。
    """
    active = active_spec_dirs()
    assert active, "active spec 目录扫到 0 个 ⇒ 扫描路径失效，失效检测会把所有豁免误判为失效"
    if (SPECS_DIR / SELF_SPEC).is_dir():
        assert SELF_SPEC in active, (
            f"本 spec 目录在磁盘上却未被扫到 ⇒ 扫描逻辑失效。实扫：{sorted(active)}"
        )


def test_no_stale_exemption_after_spec_archived() -> None:
    """🔴 失效检测：豁免项的 spec 一旦归档，该豁免就应当撤销。"""
    stale = find_stale(load(), active_spec_dirs())
    assert not stale, (
        "以下豁免项引用的 spec 已不在 `.kiro/specs/` 一级下（= 已归档），"
        "豁免理由随之失效，应当撤销并按 revoke_when 处置：\n"
        + "\n".join("  %s  (spec: %s)" % (s, sp) for s, sp in stale)
    )


# ─── 反向自检：故意写错必失败 ────────────────────────────────────────────────


def test_reverse_selfcheck_missing_field_is_caught() -> None:
    bad = {"script": "x.py", "spec": "y", "reason": "够长的理由文字", "registered_at": "2026-08-15"}
    errs = validate_entry(bad)
    assert any("revoke_when" in e for e in errs), f"缺字段未被报出 ⇒ 校验失效：{errs}"


def test_reverse_selfcheck_short_reason_is_caught() -> None:
    bad = {
        "script": "x.py", "spec": "y", "reason": "太短",
        "registered_at": "2026-08-15", "revoke_when": "spec 归档后撤销该豁免",
    }
    errs = validate_entry(bad)
    assert any("reason" in e for e in errs), f"过短 reason 未被报出 ⇒ 校验失效：{errs}"


def test_reverse_selfcheck_bad_date_is_caught() -> None:
    bad = {
        "script": "x.py", "spec": "y", "reason": "够长的理由文字说明",
        "registered_at": "2026/08/15", "revoke_when": "spec 归档后撤销该豁免",
    }
    errs = validate_entry(bad)
    assert any("registered_at" in e for e in errs), f"坏日期未被报出 ⇒ 校验失效：{errs}"


def test_reverse_selfcheck_valid_entry_passes() -> None:
    """合规项不得被误报（防校验反向失效 —— 恒报错也能让上面三条自检通过）。"""
    good = {
        "script": "backend/scripts/diagnose/mutate_e_cycle_guards.py",
        "spec": "k-cycle-extraction-formula-and-disclosure-closure",
        "reason": "spec 在办，并发会话正在编辑该脚本",
        "registered_at": "2026-08-15",
        "revoke_when": "spec 归档后由接手方迁移共享件",
    }
    assert validate_entry(good) == [], "合规豁免项被误报 ⇒ 校验有假阳性"


def test_reverse_selfcheck_stale_detection_catches_archived_spec() -> None:
    """把 spec 换成一个确定已归档/不存在的名字，失效检测必须报出。"""
    entries = [{
        "script": "backend/scripts/diagnose/mutate_e_cycle_guards.py",
        "spec": "e-cycle-extraction-formula-and-disclosure-completion",  # 2026-08-15 已归档
        "reason": "构造用：该 spec 已归档",
        "registered_at": "2026-08-15",
        "revoke_when": "立即撤销",
    }]
    active = active_spec_dirs()
    assert "e-cycle-extraction-formula-and-disclosure-completion" not in active, (
        "自检前提被破坏：该 spec 应已归档，不应出现在 active 区"
    )
    stale = find_stale(entries, active)
    assert len(stale) == 1, f"已归档 spec 的豁免未被报出 ⇒ 失效检测是装饰，实际={stale}"


def test_reverse_selfcheck_stale_detection_passes_active_spec() -> None:
    """在办 spec 的豁免不得被误报成失效。"""
    active = active_spec_dirs()
    picked = next(iter(sorted(active)))
    entries = [{
        "script": "backend/scripts/diagnose/mutate_e_cycle_guards.py",
        "spec": picked,
        "reason": "构造用：该 spec 在办",
        "registered_at": "2026-08-15",
        "revoke_when": "spec 归档后撤销",
    }]
    assert find_stale(entries, active) == [], f"在办 spec({picked}) 的豁免被误判为失效"
