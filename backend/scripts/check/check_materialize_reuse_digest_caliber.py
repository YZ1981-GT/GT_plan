# -*- coding: utf-8 -*-
"""CI 门：`digest 口径不一致` 这一类复用未命中必须在 CI 判红（requirements 3.3）。

spec: oo-single-pass-materialize-and-room-leave · Requirement 3.1 / 3.3 · 任务 10

═══ 为什么这条不能只靠 pytest ═══

`backend/tests/workpaper_sync/` 有约 291 条与本 spec 无关的**既存**失败（design 附录 F.9
用 A/B 差分实测过）。在这种分母上，「CI 里 pytest 红了」既不是新信号也不是可归因信号 ——
值班看到的永远是同一片红。requirements 3.3 要的「digest 口径不一致这一类在 CI 里直接判红」
因此需要一个**自己就能红、红了就只可能是这一件事**的门。

本脚本就是那个门。stdlib + backend 依赖，零 DB、零网络、亚秒级，`exit 1` 即违规。

═══ 四段各自证什么 ═══

1. **口径探针（真正的缺陷检测器）** —— 同一业务值的不同 Python 表示必须算出同一个
   `projection_sha256`；语义不同的值必须仍然不同。这一段直接量 2026-09-22 真栈那个缺陷
   （`"value":0` vs `"value":0.0` ⇒ 业务身份复用恒不命中）。把
   `canonical_value_for_digest` 退回裸 `json_safe` ⇒ 本段必红。
2. **缺陷类接线** —— `digest_representation_drift` 必须同时在
   :data:`DEFECT_MISS_REASONS`、指标封闭域与目录里；并且分类器在「payload 逐键全等却
   未命中」这一输入上必须真的返回它。把它从缺陷集合里悄悄摘掉 ⇒ 本段必红。
3. **回落分型完整性** —— `excel_materialize` 里**每一处** `raise SinglePassDeclined`
   都必须能归进 `SinglePassDeclineClass` 的非 `unclassified` 格子，且枚举里不得有已经
   没有 raise 点的僵尸成员。新加一处 decline 而不登记 ⇒ 本段必红。
4. **falsifier 仍在** —— 判据文件里必须还留着驱动缺陷类的那条断言。删掉判据 ⇒ 本段必红。

用法（仓库根）::

    .venv\\Scripts\\python.exe backend/scripts/check/check_materialize_reuse_digest_caliber.py
"""

from __future__ import annotations

import ast
import os
import sys
from decimal import Decimal
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.services.workpaper_sync.adapters.base import (  # noqa: E402
    FieldMode,
    FieldValue,
    Projection,
    ValueType,
)
from app.services.workpaper_sync.content_mutation import (  # noqa: E402
    _projection_payload,
    projection_canonical_digest,
)
from app.services.workpaper_sync.materialize_reuse_verdict import (  # noqa: E402
    DEFECT_MISS_REASONS,
    REUSE_METRIC,
    REUSE_RESULT_DOMAIN,
    SINGLE_PASS_DECLINE_METRIC,
    SINGLE_PASS_DECLINE_DOMAIN,
    ReuseDecision,
    ReuseMissReason,
    SinglePassDeclineClass,
    classify_single_pass_decline,
    verdict_for_miss,
)
from app.services.workpaper_sync.metrics import METRICS_BY_NAME  # noqa: E402

_ENGINE_PY = _BACKEND / "app" / "services" / "workpaper_sync" / "excel_materialize.py"
_GUARD_PY = (
    _BACKEND / "tests" / "workpaper_sync" / "test_materialize_reuse_observability.py"
)

#: 同一业务值的不同 Python 表示。两侧算出的 projection digest **必须**相同。
#:
#: 真栈那一对（`0` int vs `0.0` float）在第一行；其余是同族的其它表示
#: （`Decimal` 尾随零、指数形态、字符串小数）—— 它们都真实出现在生产的两条派生路径上：
#: HTML store 走 JSON（int/float），Excel extract 走 openpyxl（int/float/str），
#: merge 与审定回写走 `Decimal`。
_EQUIVALENT_PAIRS: tuple[tuple[ValueType, object, object], ...] = (
    (ValueType.amount, 0, 0.0),
    (ValueType.amount, 0.0, Decimal("0.00")),
    (ValueType.amount, Decimal("0"), Decimal("-0")),
    (ValueType.amount, 1234.5, Decimal("1234.50")),
    (ValueType.amount, 100, "100.00"),
    (ValueType.integer, 0, 0.0),
    (ValueType.integer, 7, 7.000),
    (ValueType.rate, "0.0325", Decimal("0.03250")),
    (ValueType.ratio, "0.6180", Decimal("0.618000")),
    # 🔴 `boolean` 的 `int 1` vs `bool True`：**真库 D4 上今天就在发生**（任务 10 实测，
    # design 附录 H.2）。instrumented 模板里那 4 个 `undisclosed_rp_rows/*` 格反读成
    # `int 1`，materialize 写成 `boolean_literal` 后再反读成 `bool True`。既有的值级判据
    # （`test_projection_digest_is_representation_stable.py`）只覆盖了 boolean 的**反向**
    # （True 不得折成数字 1），这一折叠方向从来没有判据 —— 而它是 D4 复用能命中的必要条件。
    (ValueType.boolean, 1, True),
    (ValueType.boolean, 0, False),
)

#: 语义**不同**的值对：digest 必须仍然不同。少了这一组，「把一切折叠成常量」也能让
#: 上面那组全绿 —— 那样本门就从「口径一致」退化成「口径恒等」。
_DISTINCT_PAIRS: tuple[tuple[ValueType, object, object], ...] = (
    (ValueType.amount, 0, None),
    (ValueType.amount, 0, 1),
    (ValueType.amount, "0.01", "0.02"),
    (ValueType.integer, 0, None),
    (ValueType.text, "", "0"),
    (ValueType.boolean, True, False),
)


def _projection_of(value: object, value_type: ValueType) -> Projection:
    return Projection(
        contract_id="caliber.probe",
        semantic_version="1.0.0",
        document_type="xlsx",
        values={
            "t/r1/f": FieldValue(
                stable_key="t/r1/f",
                value=value,
                value_type=value_type,
                mode=FieldMode.editable,
                row_key="r1",
            )
        },
        row_keys={"t": ("r1",)},
    )


def _digest(value: object, value_type: ValueType) -> str:
    return projection_canonical_digest(_projection_of(value, value_type))


def _check_digest_caliber() -> list[str]:
    """① 口径探针。"""
    problems: list[str] = []
    for value_type, left, right in _EQUIVALENT_PAIRS:
        left_digest, right_digest = _digest(left, value_type), _digest(right, value_type)
        if left_digest != right_digest:
            problems.append(
                f"[口径分叉] {value_type.value}: {left!r} 与 {right!r} 是同一个业务值，"
                f"却算出两个 projection digest（{left_digest[:12]}… vs {right_digest[:12]}…）"
                " ⇒ materialize 的业务身份复用对这类值**恒不命中**，每次切「在线编辑」"
                "都全量重物化（真栈实测 30s+）。"
                "修法住 projection_digest_value.canonical_value_for_digest()"
            )
    for value_type, left, right in _DISTINCT_PAIRS:
        if _digest(left, value_type) == _digest(right, value_type):
            problems.append(
                f"[口径过折叠] {value_type.value}: {left!r} 与 {right!r} 语义不同，"
                "却算出同一个 digest ⇒ 改了内容也会被判成「没改」，用户的修改会被静默丢弃"
            )
    return problems


def _check_defect_class_wiring() -> list[str]:
    """② 缺陷类接线（集合 / 封闭域 / 目录 / 分类器实际输出）。"""
    problems: list[str] = []
    drift = ReuseMissReason.digest_representation_drift
    if drift not in DEFECT_MISS_REASONS:
        problems.append(
            f"[缺陷类被降级] {drift.value} 不在 DEFECT_MISS_REASONS 里 —— "
            "requirements 3.3 明说它「属于缺陷，应当在 CI 里直接判红而不是默默走全量」"
        )
    for metric, domain in (
        (REUSE_METRIC, REUSE_RESULT_DOMAIN),
        (SINGLE_PASS_DECLINE_METRIC, SINGLE_PASS_DECLINE_DOMAIN),
    ):
        definition = METRICS_BY_NAME.get(metric)
        if definition is None:
            problems.append(
                f"[指标未注册] {metric} 不在 METRIC_CATALOG —— requirements 3.1 要求复用判定"
                "落进既有 workpaper_sync_* 家族，而不是只写日志"
            )
        elif tuple(definition.result_domain) != tuple(domain):
            problems.append(
                f"[封闭域漂移] {metric} 目录里的 result_domain "
                f"{list(definition.result_domain)} 与 materialize_reuse_verdict 的 "
                f"{list(domain)} 不一致 —— 两份域就是两个真源"
            )
    expected = f"miss_{drift.value}"
    if expected not in REUSE_RESULT_DOMAIN:
        problems.append(f"[封闭域缺格] {expected} 不在 {REUSE_METRIC} 的 result_domain 里")

    # 分类器实测：payload 逐键全等（含表示差异）却未命中 ⇒ 必须判成缺陷类。
    # 刻意让两侧 payload 的 value 表示**不同**（int 0 vs 字符串 "0.00"）：那正是口径分叉时
    # 落盘字节的真实形态。业务比较面若被换成 digest 口径的那一套，这一条立刻不是 drift。
    base = _projection_payload(_projection_of(0, ValueType.amount))
    incoming = _projection_payload(_projection_of(0, ValueType.amount))
    base["values"]["t/r1/f"]["value"] = 0
    incoming["values"]["t/r1/f"]["value"] = "0.00"
    verdict = verdict_for_miss(
        base_payload=base, incoming_payload=incoming, base_version_matched=False
    )
    if verdict.miss_reason is not drift or not verdict.is_defect:
        problems.append(
            "[分类器失灵] 业务内容逐键全等（0 vs \"0.00\" 是同一个金额零）却未命中时，"
            f"分类器给出 {verdict.metric_result}（is_defect={verdict.is_defect}），"
            f"而不是 miss_{drift.value} —— requirements 3.3 的第三类因此不可达，"
            "那条验收标准会退化成空话"
        )
    # 反向自检：真改了内容必须判 content_changed（否则上一条可被「恒判 drift」满足）。
    changed = _projection_payload(_projection_of(1, ValueType.amount))
    changed_verdict = verdict_for_miss(
        base_payload=base, incoming_payload=changed, base_version_matched=False
    )
    if changed_verdict.miss_reason is not ReuseMissReason.content_changed:
        problems.append(
            "[分类器失灵·反向] 内容真变了（0 → 1）却没判 content_changed，实得 "
            f"{changed_verdict.metric_result} —— 「恒判缺陷类」会把正常的全量物化全报成缺陷"
        )
    if changed_verdict.decision is not ReuseDecision.miss:
        problems.append("[分类器失灵] verdict_for_miss 返回了非 miss 的 decision")
    return problems


def _reason_probe(node: ast.AST) -> str | None:
    """把一处 `raise SinglePassDeclined(<expr>)` 的原因表达式还原成可分型的探针串。

    三种形态覆盖生产现有的全部写法；看不懂的形态返回 `None`（⇒ 判红而不是放过，
    与 design 附录 D.3 / G.5 的 AST 检查器同一条纪律：检查器看不懂的写法不能算通过）。
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id.endswith("_decline_reason"):
            from app.services.workpaper_sync import excel_materialize as EM

            builder = getattr(EM, node.func.id, None)
            if callable(builder):
                try:
                    return str(builder(["probe!A1 被 x 写且 payload 不同"]))
                except Exception:  # noqa: BLE001 - 探针失败即判红
                    return None
    return None


def _check_decline_classification() -> list[str]:
    """③ 回落分型完整性（AST 逐 raise 点对账）。"""
    problems: list[str] = []
    tree = ast.parse(_ENGINE_PY.read_text(encoding="utf-8"))
    sites: list[tuple[int, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise) or node.exc is None:
            continue
        exc = node.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            if exc.func.id == "SinglePassDeclined" and exc.args:
                sites.append((node.lineno, exc.args[0]))
    if not sites:
        problems.append(
            f"[检查器空转] {_ENGINE_PY.name} 里找不到任何 raise SinglePassDeclined —— "
            "要么单趟回落被删了（那需要重定本门的目标），要么检查器认不出新写法"
        )
    seen: set[SinglePassDeclineClass] = set()
    for lineno, arg in sites:
        probe = _reason_probe(arg)
        if probe is None:
            problems.append(
                f"[分型不可判] {_ENGINE_PY.name}:{lineno} 的 decline 原因表达式本检查器"
                "认不出来 —— 认不出就不能算通过（否则新写法会静默落进 unclassified）"
            )
            continue
        member = classify_single_pass_decline(probe)
        if member is SinglePassDeclineClass.unclassified:
            problems.append(
                f"[分型缺登记] {_ENGINE_PY.name}:{lineno} 的 decline 原因 {probe[:48]!r} "
                "落进 unclassified —— requirements 3.3 要统计回落原因，"
                "请在 SinglePassDeclineClass 与 _DECLINE_MARKERS 里登记它"
            )
            continue
        seen.add(member)
    zombies = sorted(
        member.value
        for member in SinglePassDeclineClass
        if member is not SinglePassDeclineClass.unclassified and member not in seen
    )
    if zombies:
        problems.append(
            f"[僵尸分型] SinglePassDeclineClass 里这些成员已经没有对应的 raise 点：{zombies}"
            " —— 封闭域里留一个永不发生的值会让「回落原因统计」读起来像有覆盖"
        )
    return problems


def _check_falsifier_is_still_there() -> list[str]:
    """④ 判据仍在（删掉 falsifier 等于这一类重新变成静默）。"""
    if not _GUARD_PY.exists():
        return [
            f"[判据缺失] {_GUARD_PY.name} 不存在 —— requirements 3.2 的「连续两次必命中」"
            "守卫与 3.3 的缺陷类反证都住在那里"
        ]
    source = _GUARD_PY.read_text(encoding="utf-8")
    problems: list[str] = []
    for needle, why in (
        (
            "digest_representation_drift",
            "缺陷类的定向反证",
        ),
        (
            "ReuseDecision.hit",
            "requirements 3.2 的「第二次必须命中复用」",
        ),
    ):
        if needle not in source:
            problems.append(
                f"[判据被摘] {_GUARD_PY.name} 里已经没有 {needle!r} —— {why} 不见了"
            )
    return problems


def main() -> int:
    segments = (
        ("① projection digest 口径探针", _check_digest_caliber),
        ("② 缺陷类接线", _check_defect_class_wiring),
        ("③ 单趟回落分型完整性", _check_decline_classification),
        ("④ falsifier 仍在", _check_falsifier_is_still_there),
    )
    total: list[str] = []
    for title, run in segments:
        problems = run()
        mark = "OK" if not problems else f"FAIL({len(problems)})"
        print(f"[{mark}] {title}")
        for problem in problems:
            print(f"    - {problem}")
        total.extend(problems)
    if total:
        print(
            f"\n检测到违规 {len(total)} 条 —— requirements 3.3 要求 digest 口径不一致这一类"
            "在 CI 直接判红。"
        )
        return 1
    print(
        f"\n全部通过：{len(_EQUIVALENT_PAIRS)} 组等价表示 digest 全同、"
        f"{len(_DISTINCT_PAIRS)} 组异义值 digest 全异；缺陷类接线完整；"
        f"回落分型 {len(SINGLE_PASS_DECLINE_DOMAIN) - 1} 类逐一对上 raise 点。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
