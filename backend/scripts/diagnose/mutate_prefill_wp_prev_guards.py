"""变异检验：逐条施加变异，按**失败测试名集合的差集**判定守卫是否真的打红。

spec: .kiro/specs/prefill-wp-prev-resolution-repair/ Task 15

为什么不看退出码
----------------

baseline 本身可能有红（本 spec 的 Wave 1 守卫就是「先打红」范式）⇒ `rc` 恒为 1，
按 rc 判红绿必得「全部 GREEN = 守卫缺陷」的假结论。正解 = 抓 ``FAILED ...::(name)``
收**集合**，`new_fails = fails_after - fails_baseline` 非空才算 RED。

三态判定
--------

* ``RED``        —— 新增失败非空，守卫有效
* ``GREEN``      —— 变异施加了但无新增失败 = **守卫缺陷**（最需要关注的一种）
* ``ANCHOR-MISS``—— 锚点命中数 != 1，变异**根本没施加**，此时「仍绿」不能作任何结论

安全约束（memory 已登记的踩坑）
------------------------------

* 备份落**磁盘 `.bak`** 而非只在内存 —— 脚本被 Ctrl+C 中断时 ``finally`` 可能来不及跑完，
  只在内存备份会把变异残留在文件里，下一轮又把它当基线（曾实测踩中）
* ``try/finally`` 无条件还原 + **字节级哈希核验**
* 锚点必须**行级唯一**且**单行**（含 ``\n`` 的跨行锚点在 CRLF 工作树必 MISS）
* 一个进程只跑一条变异的施加/还原，避免互相污染
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parent

_ANCHOR_MAP_PY = _BACKEND / "app" / "services" / "prefill_anchor_map.py"
_ENGINE_PY = _BACKEND / "app" / "services" / "prefill_engine.py"

#: 守卫测试集（两个文件一起跑 —— 变异可能只打红其中一个）
_TEST_TARGETS = (
    "backend/tests/test_prefill_wp_prev_resolution.py",
    "backend/tests/test_prefill_anchor_map.py",
)


@dataclass(frozen=True)
class Mutation:
    name: str
    path: Path
    old: str
    new: str
    intent: str


MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        name="M1_read_cells_again",
        path=_ENGINE_PY,
        old="    spec = resolve_anchor(wp_code, sheet_name, cell_ref)",
        new=(
            '    _mut = (wp.parsed_data or {}).get("cells", {}) if False else None\n'
            "    spec = resolve_anchor(wp_code, sheet_name, cell_ref)"
        ),
        intent="改回引用 parsed_data['cells'] ⇒ Property 2 源码守卫必红",
    ),
    Mutation(
        name="M2_wrong_checklist_column",
        path=_ANCHOR_MAP_PY,
        old="                WHERE wp_id = CAST(:wp_id AS uuid)",
        new="                WHERE workpaper_id = CAST(:wp_id AS uuid)",
        intent=(
            "把 checklist_responses 的列名改回不存在的 workpaper_id "
            "⇒ 本轮 P0 的原形态，schema 契约守卫必红"
        ),
    ),
    Mutation(
        name="M3_drop_wp_index_join",
        path=_ANCHOR_MAP_PY,
        old="                JOIN wp_index wi ON wi.id = wp.wp_index_id",
        new="                LEFT JOIN wp_index wi ON wi.id IS NULL",
        intent="去掉 wp_index JOIN ⇒ 底稿定位失效，真实库 HIT 断言必红",
    ),
    Mutation(
        name="M4_drop_order_by",
        path=_ANCHOR_MAP_PY,
        old="                ORDER BY wp.updated_at DESC NULLS LAST, wp.id ASC",
        new="                -- ORDER BY removed by mutation",
        intent="去掉确定性 ORDER BY ⇒ Property 11 源码守卫必红",
    ),
    Mutation(
        name="M5_prev_falls_back_to_current_year",
        path=_ENGINE_PY,
        old='    参数保留完整签名（``_FORMULA_RESOLVERS`` 的统一契约），实参不使用。\n    """\n    return None',
        new=(
            '    参数保留完整签名（``_FORMULA_RESOLVERS`` 的统一契约），实参不使用。\n    """\n'
            "    if len(args) >= 3:\n"
            "        spec = resolve_anchor(args[0], args[1], args[2])\n"
            "        if spec is not None:\n"
            "            res = await read_anchor_value(db, project_id, args[0], spec)\n"
            "            return res.value\n"
            "    return None"
        ),
        intent="让 PREV 回退查本年 ⇒ Property 9 必红（取本年值填上年列是数字级错误）",
    ),
    Mutation(
        name="M6_row_mode_falls_back_to_first_row",
        path=_ANCHOR_MAP_PY,
        old="        # 🔴 未命中**不回退第一行** —— 静默取错行比取不到更坏",
        new=(
            "        _first = dict_rows[0]\n"
            "        _v = _to_decimal(_first.get(spec.column))\n"
            "        if _v is not None:\n"
            "            return AnchorReadResult(AnchorReadStatus.HIT, _v, 'mutated fallback')\n"
            "        # 未命中回退第一行（变异）"
        ),
        intent="ROW 未命中回退第一行 ⇒ Property 8 反向自检必红",
    ),
    # 🔴 M7 的第一版把 D2 的 `endBalance` 改成 `priorAudited` 并期望打红，实测 GREEN，
    # 复查后发现**是变异无效而非守卫缺陷**：`useD2Detail` 是「整行 JSON.stringify」形态
    # ⇒ 其接口声明的 25 个字段（含 priorAudited/currentAudited）全部真落库，
    # 映射到它是**合法**的，守卫不打红才是对的。
    # 有效变异必须挑「显式白名单序列化」形态的 composable —— `useD1BadDebt.
    # serializeNoteTypeRows()` 只写 9 个录入列，`priorAudited`/`currentAudited`
    # 由 recalcRow() 重算、不在其中，正是 spec 要禁的「后端复刻前端派生公式」形态。
    Mutation(
        name="M7_map_to_derived_column",
        path=_ANCHOR_MAP_PY,
        old='        item_id="D1-bd-notetype-rows",\n        column="currentUnadjusted",',
        new='        item_id="D1-bd-notetype-rows",\n        column="currentAudited",',
        intent=(
            "把 D1-bd-notetype-rows 映射改到派生列 currentAudited"
            "（不在 serializeNoteTypeRows 的 9 个白名单字段内）"
            " ⇒ Property 4 持久化列交叉锁死必红"
        ),
    ),
    Mutation(
        name="M8_drop_logger_warning",
        path=_ENGINE_PY,
        old="        _logger.warning(\n            \"WP() 锚点未对齐，返回 None：wp_code=%s sheet=%s cell_ref=%s\"",
        new="        _noop_warn(\n            \"WP() 锚点未对齐，返回 None：wp_code=%s sheet=%s cell_ref=%s\"",
        intent="去掉未对齐时的 logger.warning ⇒ Property 12 必红（静默会伪装成无数据）",
    ),
    Mutation(
        name="M9_add_unaligned_entry",
        path=_ANCHOR_MAP_PY,
        old="UNALIGNED_MAX = 4",
        new="UNALIGNED_MAX = 99",
        intent="把待对齐上限放宽 ⇒ Property 13「只减不增」必红",
    ),
    # ── M10（本轮复盘新增）──────────────────────────────────────────────
    # 复盘发现原 Property 14 守卫写死 `expected = set("EFGHIJKLMN")`，
    # 结构上表达不了 `WP('PL','利润表','净利润')` —— `PL` 是**利润表（报表）**
    # 不是底稿，首字母 `P` 落在字母表外 ⇒ 那 2 条既不在 ANCHOR_MAP、也不在
    # UNALIGNED、也不被任何范围外登记覆盖 = 无人认领的灰区，而 Property 3
    # 只校验 D 循环并集故抓不到。判据已改为「从预设实时派生非 D 目标」。
    Mutation(
        name="M10_drop_non_workpaper_target_registration",
        path=_ANCHOR_MAP_PY,
        old='    "PL": (\n        "利润表（报表，非底稿）',
        new='    "PL_REMOVED_BY_MUTATION": (\n        "利润表（报表，非底稿）',
        intent=(
            "删掉 PL 非底稿目标登记 ==> 灰区重现，"
            "从预设派生的 Property 14 守卫必红（写死字母表的旧判据抓不到）"
        ),
    ),
)


def _collect_failed(out: str) -> set[str]:
    """从 pytest 输出抓失败测试名集合。

    🔴 只认 ``FAILED path::Class::test`` 行 —— 输出会按控制台宽度折行，
    故用非贪婪匹配到行尾并取最后一段 ``::`` 之后的名字。
    """
    names: set[str] = set()
    for m in re.finditer(r"^(?:FAILED|ERROR)\s+(\S+)", out, re.M):
        names.add(m.group(1).split("::")[-1])
    # 收集阶段崩溃（import 期 assert）也算红，但要能区分
    if "errors during collection" in out or "Interrupted" in out:
        names.add("<collection-error>")
    return names


def _run_tests() -> tuple[set[str], str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *_TEST_TARGETS, "-q", "--tb=no", "-rf",
         "--continue-on-collection-errors"],
        cwd=str(_REPO),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return _collect_failed(out), out


def main() -> int:
    lines: list[str] = []
    baseline_fails, base_out = _run_tests()
    lines.append(f"BASELINE failed={sorted(baseline_fails) or '[]'}")
    m = re.search(r"(\d+) passed", base_out)
    lines.append(f"BASELINE passed={m.group(1) if m else '?'}")
    lines.append("")

    verdicts: list[tuple[str, str]] = []
    for mut in MUTATIONS:
        src = mut.path.read_text(encoding="utf-8")
        orig_hash = hashlib.sha256(src.encode("utf-8")).hexdigest()
        hits = src.count(mut.old)
        if hits != 1:
            verdicts.append((mut.name, f"ANCHOR-MISS (hits={hits})"))
            lines.append(f"[{mut.name}] ANCHOR-MISS hits={hits} -- 变异未施加，结论无效")
            lines.append(f"    intent: {mut.intent}")
            lines.append("")
            continue

        bak = mut.path.with_suffix(mut.path.suffix + ".bak")
        bak.write_bytes(mut.path.read_bytes())
        try:
            mut.path.write_text(src.replace(mut.old, mut.new, 1), encoding="utf-8")
            fails, _ = _run_tests()
            new_fails = fails - baseline_fails
            resolved = baseline_fails - fails
            if new_fails:
                verdict = f"RED (+{sorted(new_fails)})"
            elif resolved:
                verdict = f"GREEN-but-resolved({sorted(resolved)}) -- 需人工判读"
            else:
                verdict = "GREEN <<< 守卫缺陷：该变异未被任何断言抓住"
            verdicts.append((mut.name, verdict))
            lines.append(f"[{mut.name}] {verdict}")
            lines.append(f"    intent: {mut.intent}")
            lines.append("")
        finally:
            mut.path.write_bytes(bak.read_bytes())
            bak.unlink(missing_ok=True)
            back_hash = hashlib.sha256(
                mut.path.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            assert back_hash == orig_hash, (
                f"{mut.name} 还原后哈希不符！{mut.path} 可能残留变异，请 git diff 检查。"
            )

    lines.append("=" * 70)
    reds = sum(1 for _, v in verdicts if v.startswith("RED"))
    greens = [n for n, v in verdicts if v.startswith("GREEN <<<")]
    misses = [n for n, v in verdicts if v.startswith("ANCHOR-MISS")]
    lines.append(f"RED={reds}/{len(MUTATIONS)}  GREEN(缺陷)={greens}  ANCHOR-MISS={misses}")

    out_path = Path(__file__).resolve().parent / "mutate_prefill_wp_prev_guards.txt"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[OK] {out_path}")
    print(f"RED={reds}/{len(MUTATIONS)} GREEN={len(greens)} MISS={len(misses)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
