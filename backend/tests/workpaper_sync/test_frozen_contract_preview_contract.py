"""spec frozen-contract-read-path 的任务 5~6 守卫：preview 默认取冻结契约。

Requirements: R2.1~R2.4 · R4.1~R4.3
Properties:  P2（冻结旧契约的 operation 预览成功且如实标注）
             P4（`contract_source` 只作标注，不得门控按钮）

本文件从 `test_frozen_contract_read_path.py` 拆出（行数门 800）：那边保留读路径
本体（任务 2~4 的单一实现 / 错误分型 / Property 1），这边是消费方
（`ConflictResolutionService.preview` 该用哪份契约、前端怎么标注）。

🔴 纪律（memory 铁律）：判据一律用 **AST**，不用文本 `in` 匹配 ——
注释与 docstring 正反两向都会骗过文本扫描器。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SVC = BACKEND / "app" / "services" / "workpaper_sync"


# ═══════════════════════════════════════════════════════════════════════════
# 与主文件共用的最小辅助（刻意各一份：跨文件 import 测试辅助会让两边的
# 「最小上下文」耦合，改一处必须读另一处 —— 那正好抵消拆分的收益）
# ═══════════════════════════════════════════════════════════════════════════


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """顶层函数与类的直接方法，键用 `Class.method` / `func`。"""
    out: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[f"{node.name}.{sub.name}"] = sub
    return out


def _bundle(*, slot_type: str = "definition", ref: str | None = None, digest: str = "a" * 64):
    """最小 bundle 替身：只提供 reader 真正读的两个字段。"""
    from types import SimpleNamespace

    from app.services.workpaper_sync.models import BundleSlot

    spec = SimpleNamespace(
        slot=BundleSlot.contract,
        slot_type=slot_type,
        slot_ref=ref or f"definition:{uuid.uuid4()}",
        slot_digest=digest,
        is_definition=(slot_type == "definition"),
    )
    return SimpleNamespace(bundle_id=uuid.uuid4(), slots={BundleSlot.contract: spec})


def _real_contract_payload() -> dict:
    """取一份**真实**的 per-entry 契约 payload（避免手搓字段）。"""
    import json

    contracts_dir = BACKEND / "data" / "workpaper_sync_contracts"
    for path in sorted(contracts_dir.glob("*.json"), key=lambda p: p.stat().st_size):
        if "example" in path.name or "candidate" in path.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("contract_id") == path.stem:
            return payload
    raise AssertionError(f"{contracts_dir} 里没有可用的真实契约 payload")


# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# 任务 5：preview 默认取冻结契约（ADR-FC-003 / R2.1~R2.4）
# ═══════════════════════════════════════════════════════════════════════════

PREVIEW_CONTRACT_PY = SVC / "conflict_preview_contract.py"


class TestPreviewContractResolutionModule:
    """`resolve_preview_contract` 的三条分支必须各自可辨。"""

    def test_module_exists(self) -> None:
        assert PREVIEW_CONTRACT_PY.is_file(), (
            "conflict_preview_contract.py 不存在 —— 「该用哪份契约」必须收在一处"
        )

    def test_source_labels_are_the_two_fixed_literals(self) -> None:
        from app.services.workpaper_sync import conflict_preview_contract as P

        assert P.FROZEN_CONTRACT_SOURCE_LABEL == "frozen"
        assert P.EXPLICIT_CONTRACT_SOURCE_LABEL == "explicit"
        assert P.FROZEN_CONTRACT_SOURCE_LABEL != P.EXPLICIT_CONTRACT_SOURCE_LABEL

    def test_unavailable_error_is_not_reported_as_digest_drift(self) -> None:
        """「冻结契约读不回来」不得复用 `frozen_contract_digest_drift`。

        两者处置完全不同：drift = 调用方传错了契约（改调用方）；
        unavailable = 该 operation 的契约本身读不回来（查数据链 / 存储卷）。
        """
        from app.services.workpaper_sync import conflict_preview_contract as P

        assert P.PreviewContractUnavailableError.error_code != "frozen_contract_digest_drift"
        assert "drift" not in P.PreviewContractUnavailableError.error_code


class TestExplicitContractStillRunsTheOriginalCriterion:
    """R2.2：显式传入这条路**一个字不放宽**。"""

    @pytest.mark.asyncio
    async def test_mismatched_explicit_contract_still_raises_the_original_error(self) -> None:
        from app.services.workpaper_sync import conflict_preview_contract as P
        from app.services.workpaper_sync.conflict_resolution import (
            FrozenContractDriftError,
            assert_frozen_contract_matches_bundle,
        )

        class _Contract:
            canonical_sha256 = "a" * 64

        with pytest.raises(FrozenContractDriftError) as caught:
            await P.resolve_preview_contract(
                session=object(),
                artifacts=object(),
                bundle=_bundle(digest="b" * 64),
                provided=_Contract(),  # type: ignore[arg-type]
                assert_matches_bundle=assert_frozen_contract_matches_bundle,
                where="unit",
            )
        # 原判据的 error_code 必须原样保留
        assert caught.value.error_code == "frozen_contract_digest_drift"

    @pytest.mark.asyncio
    async def test_matching_explicit_contract_is_used_with_source_explicit(self) -> None:
        from app.services.workpaper_sync import conflict_preview_contract as P
        from app.services.workpaper_sync.conflict_resolution import (
            assert_frozen_contract_matches_bundle,
        )

        digest = "c" * 64

        class _Contract:
            canonical_sha256 = digest
            contract_id = "d4.revenue_detail"
            semantic_version = "1.2.0"

        resolved = await P.resolve_preview_contract(
            session=object(),
            artifacts=object(),
            bundle=_bundle(digest=digest),
            provided=_Contract(),  # type: ignore[arg-type]
            assert_matches_bundle=assert_frozen_contract_matches_bundle,
            where="unit",
        )
        assert resolved.source == "explicit"
        assert resolved.is_frozen is False
        assert resolved.provided_digest == digest
        # 显式传入时**不得**去读冻结契约（否则会多一次 IO 且可能失败）
        assert resolved.definition_id is None


class TestOmittedContractReadsTheFrozenOne:
    """R2.1：省略 ⇒ 读冻结那份（本 spec 新增的唯一行为）。"""

    @pytest.mark.asyncio
    async def test_omitted_contract_goes_through_the_reader(self, monkeypatch) -> None:
        import json

        from app.services.workpaper_sync import conflict_preview_contract as P
        from app.services.workpaper_sync import frozen_contract_reader as R
        from app.services.workpaper_sync.contracts import parse_contract
        from app.services.workpaper_sync.definitions import canonical_digest

        payload = _real_contract_payload()
        contract = parse_contract(payload)
        digest = contract.canonical_sha256
        definition_id = uuid.uuid4()

        async def fake_read(self, *, bundle):  # noqa: ARG001
            return R.FrozenContractSnapshot(
                contract=contract,
                slot_digest=digest,
                definition_id=definition_id,
                semantic_version="1.2.0",
            )

        monkeypatch.setattr(R.FrozenContractReader, "read", fake_read)

        resolved = await P.resolve_preview_contract(
            session=object(),
            artifacts=object(),
            bundle=_bundle(digest=digest),
            provided=None,
            assert_matches_bundle=lambda **_kw: pytest.fail(
                "省略 contract 时不得调用原判据（那是显式传入那条路的判据）"
            ),
            where="unit",
        )
        assert resolved.source == "frozen"
        assert resolved.is_frozen is True
        assert resolved.frozen_digest == digest
        assert resolved.definition_id == definition_id
        assert resolved.contract.canonical_sha256 == canonical_digest(json.loads(
            json.dumps(payload)
        ))

    @pytest.mark.asyncio
    async def test_reader_failure_becomes_unavailable_not_drift(self, monkeypatch) -> None:
        from app.services.workpaper_sync import conflict_preview_contract as P
        from app.services.workpaper_sync import frozen_contract_reader as R

        async def boom(self, *, bundle):  # noqa: ARG001
            raise R.FrozenContractBlobUnreadableError(
                "磁盘文件不在", diagnostics={"path": "/x"}
            )

        monkeypatch.setattr(R.FrozenContractReader, "read", boom)

        with pytest.raises(P.PreviewContractUnavailableError) as caught:
            await P.resolve_preview_contract(
                session=object(),
                artifacts=object(),
                bundle=_bundle(digest="a" * 64),
                provided=None,
                assert_matches_bundle=lambda **_kw: None,
                where="unit",
            )
        # 原始成因必须带出来（R1.3：不得碾成一句「契约漂移」）
        assert caught.value.diagnostics.get("path") == "/x"


class TestContractSourceFields:
    """响应字段的单一来源（两处调用必须给出同一组键名）。"""

    def test_frozen_source_fields(self) -> None:
        from app.services.workpaper_sync import conflict_preview_contract as P

        class _C:
            canonical_sha256 = "a" * 64

        fields = P.contract_source_fields(
            P.PreviewContractResolution(
                contract=_C(),  # type: ignore[arg-type]
                source="frozen",
                frozen_digest="a" * 64,
                definition_id=uuid.uuid4(),
            )
        )
        assert fields["contract_source"] == "frozen"
        assert fields["frozen_digest"] == "a" * 64
        assert "contract_definition_id" in fields
        assert "provided_digest" not in fields

    def test_explicit_source_fields(self) -> None:
        from app.services.workpaper_sync import conflict_preview_contract as P

        class _C:
            canonical_sha256 = "b" * 64

        fields = P.contract_source_fields(
            P.PreviewContractResolution(
                contract=_C(),  # type: ignore[arg-type]
                source="explicit",
                frozen_digest="a" * 64,
                provided_digest="b" * 64,
            )
        )
        assert fields["contract_source"] == "explicit"
        assert fields["provided_digest"] == "b" * 64
        assert "contract_definition_id" not in fields


class TestConflictPreviewCarriesContractSource:
    """`ConflictPreview` 必须真的把来源带进响应（不是只在服务层算出来）。"""

    def test_preview_dataclass_has_contract_source_field(self) -> None:
        from app.services.workpaper_sync.conflict_resolution import ConflictPreview

        names = {f.name for f in __import__("dataclasses").fields(ConflictPreview)}
        assert "contract_source" in names, (
            "ConflictPreview 没有 contract_source 字段 ⇒ 前端拿不到「这是历史契约」"
        )

    def test_as_dict_merges_the_source_fields(self) -> None:
        """AST：`as_dict` 必须把 `contract_source` 展开进响应字典。

        用 AST 而不是文本匹配：`**dict(self.contract_source)` 这种写法在
        字符串里看不出来（memory 铁律：注释/docstring 会骗过文本扫描器）。
        """
        tree = _tree(SVC / "conflict_resolution.py")
        fn = _functions(tree)["ConflictPreview.as_dict"]
        # 🔴 `**dict(x)` 在 AST 里是 `Dict(keys=[..., None, ...], values=[..., Call, ...])`：
        # 展开项的 key 是 `None`，**不是** `ast.keyword`（那是函数调用 f(**kw) 的形态）。
        # 判据要认 `keys` 里的 `None` 槽位，否则会漏掉全部 `**` 展开。
        merged = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if key is not None:
                    continue
                if "contract_source" in ast.unparse(value):
                    merged = True
        assert merged, (
            "as_dict 没有把 contract_source 展开进响应 —— 前端永远看不到来源标注"
        )


class TestContractSourceIsNotUsedAsACapabilityGate:
    """R2.3 / design §4：`contract_source` **只作标注**，不得门控按钮可用性。

    判据 = 前端源码：
    * `contractSource` 不得出现在 **能力门控属性** 的值里（`:disabled` /
      `:readonly` / `v-bind:disabled`）；
    * `contractSource` 也不得出现在 `v-show` / `:class` 这类**控件可见性/状态**上
      （那是把标注变成了「看起来不能点」）；
    * 🔴 **允许** 它出现在标注元素自身的 `v-if`（横幅需要「只在历史契约时显示」）。
      把这条也禁掉等于禁止实现该需求 —— 判据要精确到「门控的是不是控件」。
    """

    FRONTEND_DIR = (
        BACKEND.parent / "audit-platform" / "frontend" / "src"
        / "components" / "workpaper" / "sync"
    )

    #: 明令禁止的门控属性（值里出现 contractSource 即违规）
    FORBIDDEN_GATES: tuple[str, ...] = (
        ":disabled=",
        "v-bind:disabled=",
        ":readonly=",
        "v-bind:readonly=",
        "v-show=",
        ":class=",
    )

    def test_frontend_dir_exists(self) -> None:
        assert self.FRONTEND_DIR.is_dir(), f"前端 sync 目录不存在: {self.FRONTEND_DIR}"

    def test_contract_source_is_not_a_control_gate(self) -> None:
        offenders: list[str] = []
        for path in sorted(self.FRONTEND_DIR.rglob("*.vue")):
            text = path.read_text(encoding="utf-8")
            if "contractSource" not in text and "contract_source" not in text:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if "contractSource" not in line and "contract_source" not in line:
                    continue
                stripped = line.strip()
                if any(token in stripped for token in self.FORBIDDEN_GATES):
                    offenders.append(f"{path.name}:{lineno}: {stripped[:120]}")
        assert offenders == [], (
            "contract_source 被用作控件能力门控（它只作标注，门控会让历史 operation"
            "无法继续）：\n" + "\n".join(offenders)
        )

    def test_the_notice_banner_actually_exists(self) -> None:
        """反向断言：标注**真的显示出来了**。

        只做「不许门控」的否定判据会让「一行都不写」也全绿 ——
        那样需求（如实标注历史契约）根本没实现。
        """
        dialog = self.FRONTEND_DIR / "WorkpaperSyncConflictDialog.vue"
        assert dialog.is_file(), f"冲突面板不存在: {dialog}"
        text = dialog.read_text(encoding="utf-8")
        assert "wp-sync-conflict-frozen-contract-notice" in text, (
            "冲突面板里没有「历史契约」横幅（data-testid 缺失）—— 需求未实现"
        )
        assert "WP_SYNC_FROZEN_CONTRACT_NOTICE" in text, (
            "横幅没有用统一文案常量 —— 文案会各处漂"
        )
