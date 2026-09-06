# -*- coding: utf-8 -*-
"""BP-30：`representation.structure_hash` 只能有**一种**语义。

═══ 这组判据为什么存在（2026-09-06 实测）═══════════════════════════════════════

修复前，这一列被两条路径写成了两个**不可比**的量：

* 首版发布路径（`ContentMutationService._stage_and_verify` ← `excel_materialize`）
  写 ``normalized_structure_hash(整份 xlsx 字节)`` —— **文件字节**摘要；
* 请求时刻的 `published_identity_observer.recompute_structure_hash`（与
  ``ExcelEntryFinalizeGate`` 同构）算「契约 + **受管结构坐标**」的 canonical digest。

实证（三个 pilot 全部成立）：冻结值 == 字节摘要，而 observer 一重算就抛
``ObservedIdentityDriftError``「受管结构已漂移」—— 刚发布、artifact 刚写的 entry 也判
漂移，因为两个量本来就不可比。后果：adapter 组装必失败 ⇒
``capability_counts.bidirectional`` 在结构上永不可能 > 0。

⇒ 方案 A：发布时刻改用 `compute_structure_hash_from_artifact`，与请求时刻共用同一个
公式与同一批实测原语。

═══ 判据形态（为什么不是「查字符串存在」）═════════════════════════════════════

本仓库反复踩过「grep 式守卫」：改成 ``if False:`` / 删调用 / 改名残留都仍绿。所以：

* **同构**这件事用**真实 pilot 的 spec 与 payload 逐键比对**来证（不是比字符串）；
* **接线**这件事用 AST 证明「宿主真的传了 anchors」且「commit 路径真的调了新函数」；
* **两个 lane 分开**这件事用 AST 证明 opaque 路径没被顺手改掉。
"""

from __future__ import annotations

import ast
import hashlib
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

OBSERVER_PATH = _BACKEND / "app/services/workpaper_sync/published_identity_observer.py"
#: BP-30 的发布时刻伴生模块（三个函数从观测器抽出来的地方 —— 观测器已在行数门禁
#: whitelist 上，而门禁语义是「打磨应让文件变小不变大」，故抽伴生模块）。
PUBLISH_HASH_PATH = _BACKEND / "app/services/workpaper_sync/publish_time_structure_hash.py"
MUTATION_PATH = _BACKEND / "app/services/workpaper_sync/content_mutation.py"
HOST_PATH = _BACKEND / "app/services/workpaper_sync/projection_first_publication.py"

#: 四个 projection lane pilot 的 provider 模块。
PILOT_MODULES: tuple[tuple[str, str], ...] = (
    ("app.services.workpaper_sync.pilot_h1_grouped_dynamic", "H1"),
    ("app.services.workpaper_sync.pilot_d2_large_json", "D2"),
    ("app.services.workpaper_sync.pilot_g7_two_level_dynamic", "G7"),
    ("app.services.workpaper_sync.pilot_simple_checklist", "B60"),
)


def _strip_docstrings(source: str) -> str:
    """剥 docstring 后再做「某写法是否真存在」的判断。

    🔴 首行留一个保持原缩进的空串字面量、其余行清空：整段清空会让「体内只有
    docstring」的类/函数变成空体 ⇒ `ast.parse` 报 IndentationError，于是所有依赖本
    函数的判据都在「解析失败」上打红（BP-26 那轮实测踩过，5 条同时假红）。
    行数保持不变，报出的行号才与磁盘一致。
    """
    tree = ast.parse(source)
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        body = getattr(node, "body", None) or []
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
            and first.lineno is not None
            and first.end_lineno is not None
        ):
            spans.append((first.lineno, first.end_lineno))
    lines = source.splitlines()
    for start, end in spans:
        raw = lines[start - 1]
        indent = raw[: len(raw) - len(raw.lstrip())]
        lines[start - 1] = f'{indent}""'
        for idx in range(start, min(end, len(lines))):
            lines[idx] = ""
    return "\n".join(lines)


def _function_node(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"源码里没有名为 {name} 的函数")


# ═══════════════════════════════════════════════════════════════════════════
# 1. 两条锚点来源必须同值（本修复的核心正确性前提）
# ═══════════════════════════════════════════════════════════════════════════


class TestBp30AnchorsAgreeAcrossMoments:
    """发布时刻的 spec 投影 与 请求时刻的冻结 payload 必须给出**同一组**锚点。

    不同值 ⇒ 两个时刻算出的 `structure_hash` 又不可比 ⇒ BP-30 换个位置复发。
    这条用**真实 pilot** 的 `instrumentation_spec()` 与真正会被发布的
    `build_instrumentation_payload(...)` 产出做逐键比对，不比字符串。
    """

    @pytest.mark.parametrize("module_name,label", PILOT_MODULES)
    def test_spec_projection_equals_frozen_payload_anchors(
        self, module_name: str, label: str
    ) -> None:
        from app.services.workpaper_sync import publish_time_structure_hash as obs
        from app.services.workpaper_sync.excel_instrumentation import (
            build_instrumentation_payload,
        )

        module = __import__(module_name, fromlist=["instrumentation_spec"])
        spec = module.instrumentation_spec()
        gate = module.excel_carrier_gate()
        # `is_digest` 拒绝全零，用真实 sha256 占位（本判据不关心 digest 取值）。
        digest = hashlib.sha256(f"bp30-{label}".encode()).hexdigest()

        publish_side = obs.anchors_from_instrumentation_spec(spec)
        request_side = obs.frozen_anchors_from_instrumentation(
            build_instrumentation_payload(
                spec=spec,
                template_definition_sha256=digest,
                template_sha256=digest,
                gate=gate,
            )
        )
        assert request_side is not None, (
            f"{label}: 冻结 payload 提不出锚点 —— 请求时刻无从反读受管结构"
        )
        assert publish_side == request_side, (
            f"{label}: 两个时刻的锚点不同值\n"
            f"  发布时刻(spec 投影)   = {publish_side}\n"
            f"  请求时刻(冻结 payload) = {request_side}\n"
            "⇒ 两处算出的 structure_hash 不可比，BP-30 复发"
        )

    def test_the_denominator_is_all_four_pilots(self) -> None:
        """🔴 分母：参数化必须覆盖全部四个 pilot。

        少一个就可能出现「只有被测的那三个同值」，而漏掉的那个在生产上恒漂移。
        """
        assert len(PILOT_MODULES) == 4, (
            f"只声明了 {len(PILOT_MODULES)} 个 pilot —— projection lane 现有四个 entry"
        )

    def test_metadata_sheet_is_not_a_second_literal(self) -> None:
        """`metadata_sheet` 必须 import 真源常量，不得在投影函数里写死第二份。

        它同时被 `excel_instrumentation` 写进工作簿、被 `excel_entry_gate` 从业务枚举
        里排除、被契约的 `identity_carriers` 声明 —— 抄第四份的话，改名时三处会红、
        这里静默不红。
        """
        stripped = _strip_docstrings(PUBLISH_HASH_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "anchors_from_instrumentation_spec")
        text = ast.unparse(node)
        assert "GT_SYNC_SHEET_NAME" in text, (
            "投影函数没有引用 `GT_SYNC_SHEET_NAME` 真源常量"
        )
        assert '"_GT_SYNC"' not in text and "'_GT_SYNC'" not in text, (
            "投影函数里写死了 `_GT_SYNC` 字面量 —— 那是第二真源"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 发布时刻与请求时刻共用同一个公式
# ═══════════════════════════════════════════════════════════════════════════


class TestBp30PublishAndRequestShareOneFormula:
    """`compute_structure_hash_from_artifact` 必须**委派**给 `recompute_structure_hash`。

    各写一份 canonical_digest 表达式 = 把「两种语义」换成「两份实现」，迟早再漂一次。
    """

    def test_publish_side_delegates_to_the_shared_formula(self) -> None:
        stripped = _strip_docstrings(PUBLISH_HASH_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "compute_structure_hash_from_artifact")
        text = ast.unparse(node)
        assert "recompute_structure_hash" in text, (
            "发布时刻函数没有调用 `recompute_structure_hash` —— 公式被抄了第二份"
        )
        assert "canonical_digest" not in text, (
            "发布时刻函数自己拼 `canonical_digest` —— 公式必须只有一处"
        )

    def test_publish_side_reuses_the_observer_primitives(self) -> None:
        """实测原语也必须复用，而不是另写一套采集。"""
        stripped = _strip_docstrings(PUBLISH_HASH_PATH.read_text(encoding="utf-8"))
        text = ast.unparse(_function_node(stripped, "compute_structure_hash_from_artifact"))
        for primitive in (
            "structure_fingerprint",
            "identity_inventory",
            "observe_structure_inventory",
            "parse_identity_inventory",
        ):
            assert primitive in text, (
                f"发布时刻函数没有复用观测器原语 {primitive!r} —— 采集口径会与请求时刻分叉"
            )

    def test_it_does_not_fall_back_to_a_byte_digest(self) -> None:
        """🔴 失败不得回退成字节摘要。

        回退会让「同构」这条承诺在出错时静默失效，而调用方拿到的仍是一个看起来正常
        的 64 位 hex —— 那正是本 spec 最贵的 fail-open 形态。
        """
        stripped = _strip_docstrings(PUBLISH_HASH_PATH.read_text(encoding="utf-8"))
        text = ast.unparse(_function_node(stripped, "compute_structure_hash_from_artifact"))
        assert "normalized_structure_hash" not in text, (
            "发布时刻函数里出现了 `normalized_structure_hash` —— 那是被本修复取代的旧语义"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 3. 接线：宿主真的传了，commit 真的用了
# ═══════════════════════════════════════════════════════════════════════════


    def test_publish_module_does_not_copy_the_formula(self) -> None:
        """🔴 抽伴生模块的目的是分**职责**，不是分**真源**。

        `recompute_structure_hash`（那个 canonical digest 公式）必须仍只有观测器一份，
        伴生模块只能 import 它。复制一份就等于把 BP-30 的「两种语义」换成「两份实现」，
        迟早再漂一次 —— 而那时两处都「看起来对」。
        """
        publish_src = PUBLISH_HASH_PATH.read_text(encoding="utf-8")
        observer_src = OBSERVER_PATH.read_text(encoding="utf-8")

        # 公式定义只能在观测器里
        assert "def recompute_structure_hash" in observer_src, (
            "`recompute_structure_hash` 不在观测器里了 —— 真源位置变了，需人工复核"
        )
        assert "def recompute_structure_hash" not in publish_src, (
            "伴生模块自己定义了 `recompute_structure_hash` —— 公式被复制成第二份"
        )
        # schema version 常量同理
        assert "STRUCTURE_HASH_SCHEMA_VERSION" not in _strip_docstrings(publish_src), (
            "伴生模块出现了 `STRUCTURE_HASH_SCHEMA_VERSION` —— 那个常量的真源在观测器"
        )
        # 且伴生模块确实从观测器 import 了公式与实测原语
        stripped = _strip_docstrings(publish_src)
        imported: set[str] = set()
        for node in ast.walk(ast.parse(stripped)):
            if isinstance(node, ast.ImportFrom) and node.module and (
                "published_identity_observer" in node.module
            ):
                imported.update(alias.name for alias in node.names)
        for required in (
            "recompute_structure_hash",
            "observe_structure_inventory",
            "parse_identity_inventory",
        ):
            assert required in imported, (
                f"伴生模块没从观测器 import `{required}` —— 它要么自己抄了一份，"
                f"要么走了别的实现。实测 import 到: {sorted(imported)}"
            )


class TestBp30IsActuallyWired:
    """假绿第①源的专项判据：新能力必须有**真实消费方**。

    本 spec 实测过「门恒关 ⇒ 门后整段代码等于没写」这种形态（BP-29），所以这里逐层
    钉死：宿主传参 → plan 带字段 → commit 路径调用。
    """

    def test_first_publication_host_passes_structure_anchors(self) -> None:
        stripped = _strip_docstrings(HOST_PATH.read_text(encoding="utf-8"))
        found = False
        for node in ast.walk(ast.parse(stripped)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name != "ContentCommitPlan":
                continue
            kwargs = {kw.arg for kw in node.keywords if kw.arg}
            assert "structure_anchors" in kwargs, (
                f"首版发布宿主构造 ContentCommitPlan 时没传 `structure_anchors`"
                f"（L{node.lineno}）⇒ commit 会回落字节摘要口径，BP-30 未生效"
            )
            found = True
        assert found, "宿主里找不到 ContentCommitPlan 构造点 —— 判据分母为空"

    def test_projection_commit_calls_the_new_hash(self) -> None:
        stripped = _strip_docstrings(MUTATION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "_projection_structure_hash")
        text = ast.unparse(node)
        assert "compute_structure_hash_from_artifact" in text, (
            "`_projection_structure_hash` 没有调用发布时刻的新公式"
        )
        stage = ast.unparse(_function_node(stripped, "_stage_and_verify"))
        assert "_projection_structure_hash" in stage, (
            "`_stage_and_verify` 没有调用 `_projection_structure_hash` —— "
            "新方法成了死代码（假绿第①源）"
        )

    def test_fence_and_representation_get_the_same_value(self) -> None:
        """🔴 fence 校验的与落库的必须是**同一个**值。

        两处各算一次（或一处新一处旧）= 校验了一份、落库了另一份，而报告读起来正常。
        判据形态：`_stage_and_verify` 里 `structure_hash=` 的实参只能是那个局部变量。
        """
        stripped = _strip_docstrings(MUTATION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "_stage_and_verify")
        values: list[str] = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                for kw in sub.keywords:
                    if kw.arg == "structure_hash":
                        values.append(ast.unparse(kw.value))
        assert len(values) >= 2, (
            f"`_stage_and_verify` 里只找到 {len(values)} 处 `structure_hash=` 实参"
            "（应至少 2 处：fence + _StagedContent）—— 判据分母不成立"
        )
        assert set(values) == {"structure_hash"}, (
            f"fence 与 representation 收到的不是同一个局部变量: {sorted(set(values))} —— "
            "两处不同就等于校验了一份、落库了另一份"
        )

    def test_opaque_lane_is_untouched(self) -> None:
        """opaque/custom lane **不得**被顺手改成新语义。

        它没有 per-entry contract，用权威文件自身 digest 作结构身份是 Requirement 6.19
        的设计（既不得强行 instrumentation，也不得留空 hash）。

        🔴 判据必须同时禁**内层公式名**与**外层包装名**，且「用自身 digest」这条要看
        `structure_hash=` 那个**关键字实参**本身，不是「函数体里出现过 sha256」——
        变异检验实测：把 `structure_hash=published.sha256` 换成
        `self._projection_structure_hash(...)` 时，首版判据判 GREEN，因为
        ① 被禁的只有内层名 ② 函数体别处仍有 `staged.sha256` 让第二条断言恒真。
        """
        stripped = _strip_docstrings(MUTATION_PATH.read_text(encoding="utf-8"))
        node = _function_node(stripped, "_stage_authoritative")
        text = ast.unparse(node)
        for banned in (
            "compute_structure_hash_from_artifact",
            "_projection_structure_hash",
        ):
            assert banned not in text, (
                f"opaque lane 出现了 {banned} —— 它没有 contract，走受管结构语义必然抛；"
                "Requirement 6.19 要求用权威文件自身 digest"
            )
        # 逐个 `structure_hash=` 关键字实参：取值只能是自身 digest 形态。
        assigned: list[str] = []
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            for kw in call.keywords:
                if kw.arg == "structure_hash":
                    assigned.append(ast.unparse(kw.value))
        assert assigned, (
            "`_stage_authoritative` 里找不到任何 `structure_hash=` 实参 —— "
            "判据的分母不成立（函数形态变了，需人工复核）"
        )
        for value in assigned:
            assert value.endswith(".sha256"), (
                f"opaque lane 的 structure_hash 实参是 {value!r} —— "
                "必须是权威文件自身 digest（`*.sha256`）"
            )
