"""spec frozen-contract-read-path 的守卫。

Requirements: R1.1~R1.4（按冻结 slot 读回契约 / 单一实现）· R4.1~R4.3（不制造第二真源）
Properties:  P1（任意 bundle 读回 digest 相等）· P4（能力只有一个实现）

本文件覆盖：
* 任务 2（ADR-FC-002）—— 字节读取与 digest 复核全仓唯一实现，observer 委派。
* 任务 3（ADR-FC-001）—— `FrozenContractReader` 的四类错误分型各自可辨、只按 slot_ref 取。

🔴 纪律（memory 铁律）：判据一律用 **AST / 函数身份**，不用文本 `in` 匹配 ——
注释与 docstring 正反两向都会骗过文本扫描器。
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
SVC = BACKEND / "app" / "services" / "workpaper_sync"
BLOB_MODULE_PY = SVC / "frozen_definition_blob.py"
OBSERVER_PY = SVC / "published_identity_observer.py"
READER_PY = SVC / "frozen_contract_reader.py"


# ═══════════════════════════════════════════════════════════════════════════
# 工具
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


def _read_bytes_call_sites(path: Path) -> list[str]:
    """`X.read_bytes()` 形式调用的所在函数名（AST，忽略注释与字符串）。"""
    tree = _tree(path)
    owners: list[str] = []
    for name, fn in _functions(tree).items():
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "read_bytes"
            ):
                owners.append(name)
    return owners


def _canonical_digest_comparisons(path: Path) -> list[str]:
    """**以 `canonical_digest(...)` 的结果与别处比较**的函数名。

    两种形态都要认（只认第一种会把「先赋值再比」的实现判成没有 digest 复核，
    而那正是本模块的写法）：
    * 直比：``canonical_digest(x) != y``
    * 先赋值再比：``a = canonical_digest(x)`` 之后 ``a != y``（比较的一端是局部名）
    """
    tree = _tree(path)
    owners: list[str] = []
    for name, fn in _functions(tree).items():
        # ① 收集本函数里被赋值为 canonical_digest(...) 的局部名
        digest_locals: set[str] = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name) and call.func.id == "canonical_digest":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            digest_locals.add(target.id)
        hit = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare):
                continue
            for side in (node.left, *node.comparators):
                if (
                    isinstance(side, ast.Call)
                    and isinstance(side.func, ast.Name)
                    and side.func.id == "canonical_digest"
                ):
                    hit = True
                    break
                if isinstance(side, ast.Name) and side.id in digest_locals:
                    hit = True
                    break
            if hit:
                break
        if hit:
            owners.append(name)
    return owners


# ═══════════════════════════════════════════════════════════════════════════
# 任务 2：单一实现（ADR-FC-002 / Property 4）
# ═══════════════════════════════════════════════════════════════════════════


class TestSingleImplementationOfBlobReadAndDigestCheck:
    """字节读取与 digest 复核在仓库里**只有一处**实现。"""

    def test_blob_module_exists(self) -> None:
        assert BLOB_MODULE_PY.is_file(), (
            "frozen_definition_blob.py 不存在 —— 读法必须提取成公共模块（ADR-FC-002），"
            "而不是在 conflict_resolution 侧再抄一份"
        )

    def test_blob_module_is_the_only_read_bytes_site(self) -> None:
        """`read_bytes()` 只出现在公共模块里（本 spec 的读法）。

        分母非空断言：公共模块自己必须有 `read_bytes()` 调用，否则「只有一处」是
        空集恒真 —— 把实现挪走后本判据仍会绿。
        """
        sites = _read_bytes_call_sites(BLOB_MODULE_PY)
        assert sites, "frozen_definition_blob.py 里没有 read_bytes() 调用 ⇒ 本判据分母为空"

        # observer 侧：读 definition payload 的字节必须已委派出去。
        # `_read_bytes` 仍在（读 published representation 的字节，与 definition blob 是两条
        # 不同的读路径），但 `_read_definition_payload` 自己不得再 read_bytes。
        observer_owners = [
            n
            for n in _read_bytes_call_sites(OBSERVER_PY)
            # `_read_bytes` 是 observer 自己的通用字节读取助手（published 侧在用）
            if n not in {"PublishedIdentityObserver._read_bytes"}
        ]
        assert "PublishedIdentityObserver._read_definition_payload" not in observer_owners, (
            "observer 的 _read_definition_payload 又自己 read_bytes 了 —— 读法必须委派给 "
            "frozen_definition_blob（否则两份实现必漂移）"
        )

    def test_canonical_digest_check_has_exactly_one_site(self) -> None:
        """definition payload 的 digest 复核只有一处：公共模块。

        `canonical_digest` 在仓库里另有正当用途（observation_digest / structure_hash），
        所以判据只是「observer 的 `_read_definition_payload` 里不再做 digest 比较」。
        """
        sites = _canonical_digest_comparisons(BLOB_MODULE_PY)
        assert sites, "公共模块里没有 canonical_digest 比较 ⇒ 本判据分母为空"
        assert (
            "PublishedIdentityObserver._read_definition_payload"
            not in _canonical_digest_comparisons(OBSERVER_PY)
        ), (
            "observer 的 _read_definition_payload 又自己比 digest 了 —— "
            "digest 复核必须只有 frozen_definition_blob 一份实现"
        )

    def test_observer_shims_delegate_to_the_shared_functions(self) -> None:
        """两个同名私有方法仍在（3 个调用方 + 5 个测试文件依赖），且**真的委派**。

        判据用函数身份：两个薄壳的 `__code__` 必须与提取前的实现**不同**，且它们的源码里
        （AST）确实引用了公共函数名。这是「不是自己留一份拷贝」的可伪证形态。
        """
        from app.services.workpaper_sync import frozen_definition_blob as BLOB
        from app.services.workpaper_sync import published_identity_observer as OBS

        assert callable(BLOB.read_definition_payload)
        assert callable(BLOB.decode_and_verify_definition_payload)
        assert callable(BLOB.resolve_definition_blob_path)

        delegated = {
            "PublishedIdentityObserver._resolve_definition_blob": "resolve_definition_blob_path",
            "PublishedIdentityObserver._read_definition_payload": (
                "decode_and_verify_definition_payload"
            ),
        }
        tree = _tree(OBSERVER_PY)
        for qualified, target in delegated.items():
            fn = _functions(tree)[qualified]
            referenced = {
                node.id for node in ast.walk(fn) if isinstance(node, ast.Name)
            } | {
                node.attr for node in ast.walk(fn) if isinstance(node, ast.Attribute)
            }
            assert target in referenced, (
                f"{qualified} 没有引用 {target} —— 它很可能又自己留了一份实现"
            )

        # 两个方法在类上真的还在（删名会让 3 个生产调用方与 5 个测试文件一起断）
        assert hasattr(OBS.PublishedIdentityObserver, "_read_definition_payload")
        assert hasattr(OBS.PublishedIdentityObserver, "_resolve_definition_blob")


class TestObserverShimKeepsMonkeypatchSeam:
    """薄壳的接缝语义：`_read_definition_payload` 必须**经由** `_resolve_definition_blob`。

    既有测试与 `publish_time_structure_hash` 都 monkeypatch 后者；若薄壳绕过它直接调公共
    模块，那些用例就在测一条不再是生产路径的分支（假绿）。
    """

    def test_read_payload_calls_resolve_blob(self) -> None:
        tree = _tree(OBSERVER_PY)
        fn = _functions(tree)["PublishedIdentityObserver._read_definition_payload"]
        called_attrs = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "_resolve_definition_blob" in called_attrs, (
            "薄壳没有调用 self._resolve_definition_blob —— monkeypatch 该层的既有用例会失效"
        )

    @pytest.mark.asyncio
    async def test_monkeypatched_resolve_blob_is_actually_used(self, tmp_path) -> None:
        """行为级证明：patch 掉路径层，payload 就来自那个文件。"""
        import json
        import uuid

        from app.services.workpaper_sync import published_identity_observer as OBS
        from app.services.workpaper_sync.definitions import canonical_digest

        payload = {"managed_sheets": []}
        child = type(
            "C", (), {"id": uuid.uuid4(), "sha256": canonical_digest(payload)}
        )()
        observer = OBS.PublishedIdentityObserver(
            session=object(), resolution=object()  # type: ignore[arg-type]
        )
        artifact = tmp_path / "definition.json"
        artifact.write_text(json.dumps(payload), encoding="utf-8")

        async def fake_resolve(*, child, context):  # noqa: ARG001
            return artifact

        observer._resolve_definition_blob = fake_resolve  # type: ignore[method-assign]
        assert await observer._read_definition_payload(child=child, context={}) == payload

        # 反向：篡改文件 ⇒ 必须抛（digest 复核真的在跑，不是「patch 了就什么都不查」）
        artifact.write_text('{"tampered": true}', encoding="utf-8")
        with pytest.raises(OBS.FrozenChildUnusableError):
            await observer._read_definition_payload(child=child, context={})


# ═══════════════════════════════════════════════════════════════════════════
# 任务 3：错误分型各自可辨（R1.3）
# ═══════════════════════════════════════════════════════════════════════════


def _error_codes() -> dict[str, str]:
    """公共模块四类失败的 `error_code`（现取，不写字面量）。"""
    from app.services.workpaper_sync import frozen_definition_blob as BLOB

    names = [
        "FrozenDefinitionBlobError",
        "FrozenDefinitionBlobMissingError",
        "FrozenDefinitionBlobUnreadableError",
        "FrozenDefinitionBlobDigestMismatchError",
    ]
    return {n: getattr(BLOB, n).error_code for n in names}


class TestBlobErrorTyping:
    def test_four_failure_kinds_are_distinguishable(self) -> None:
        """R1.3：数据缺失 / 文件缺失 / digest 不符 必须各自可辨，不得统一报「契约漂移」。"""
        codes = _error_codes()
        assert len(set(codes.values())) == len(codes), (
            f"四类失败共用 error_code ⇒ 用户分不清是数据链断了还是文件丢了: {codes}"
        )

    def test_subtypes_inherit_the_base(self) -> None:
        from app.services.workpaper_sync import frozen_definition_blob as BLOB
        from app.services.workpaper_sync.models import SyncDomainError

        for name in (
            "FrozenDefinitionBlobMissingError",
            "FrozenDefinitionBlobUnreadableError",
            "FrozenDefinitionBlobDigestMismatchError",
        ):
            sub = getattr(BLOB, name)
            assert issubclass(sub, BLOB.FrozenDefinitionBlobError), name
            assert issubclass(sub, SyncDomainError), name

    def test_missing_row_and_missing_file_are_different_types(self) -> None:
        """数据缺失（DB 行没了）与文件缺失（盘上没了）必须是**不同**的类型。

        合并成一种的后果：运维只知道「读不到」，不知道去查数据库还是查存储卷。
        """
        from app.services.workpaper_sync import frozen_definition_blob as BLOB

        assert not issubclass(
            BLOB.FrozenDefinitionBlobMissingError,
            BLOB.FrozenDefinitionBlobUnreadableError,
        )
        assert not issubclass(
            BLOB.FrozenDefinitionBlobUnreadableError,
            BLOB.FrozenDefinitionBlobMissingError,
        )


class TestBlobPathComesFromTheRepositoryNotFromLayoutGuessing:
    """ADR-FC-002 的第二条纪律：**不自拼** `definition_store/{kind}/…` 布局。

    理由：布局是 `ArtifactStorageLayout` 的领地。抄一份的后果不是「多写几行」——
    布局一改，读侧会安静地读到不存在的路径，而所有「读到空」的判据都会假绿。

    判据 = AST：公共模块里解析路径的函数**不得**出现 `definition_store` 字面量，
    且必须调用仓储的 `resolve_relative_path`。
    """

    def test_no_hardcoded_definition_store_layout(self) -> None:
        tree = _tree(BLOB_MODULE_PY)
        fn = _functions(tree)["resolve_definition_blob_path"]
        # 🔴 必须排除 docstring：本函数的 docstring 正好在**解释**「不许自拼
        #    definition_store 布局」，把说明文字当违规会让守卫恒红（memory 铁律：
        #    注释/docstring 正反两向都会骗过扫描器）。
        docstring_nodes: set[int] = set()
        if fn.body and isinstance(fn.body[0], ast.Expr) and isinstance(
            fn.body[0].value, ast.Constant
        ):
            docstring_nodes.add(id(fn.body[0].value))
        literals = {
            node.value
            for node in ast.walk(fn)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_nodes
        }
        offenders = sorted(s for s in literals if "definition_store" in s)
        assert offenders == [], (
            f"resolve_definition_blob_path 里出现自拼布局字面量 {offenders} —— "
            "路径必须由仓储 resolve_relative_path 解析（第二真源禁令）"
        )

    def test_calls_repository_resolve_relative_path(self) -> None:
        tree = _tree(BLOB_MODULE_PY)
        fn = _functions(tree)["resolve_definition_blob_path"]
        attrs = {
            node.func.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "resolve_relative_path" in attrs, (
            "resolve_definition_blob_path 没有调用仓储的 resolve_relative_path"
        )

    def test_relative_path_comes_from_the_artifact_row(self) -> None:
        """`relative_path` 必须取自 DB 行，不得由 child 的 digest / id 拼出来。"""
        tree = _tree(BLOB_MODULE_PY)
        fn = _functions(tree)["resolve_definition_blob_path"]
        attrs = {
            node.attr
            for node in ast.walk(fn)
            if isinstance(node, ast.Attribute)
        }
        assert "relative_path" in attrs, (
            "resolve_definition_blob_path 没有读 artifact row 的 relative_path"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 任务 3：FrozenContractReader（ADR-FC-001 / R1.1~R1.4）
# ═══════════════════════════════════════════════════════════════════════════


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
    return SimpleNamespace(
        bundle_id=uuid.uuid4(),
        slots={BundleSlot.contract: spec},
    )


class TestFrozenContractReaderRefusesToGuess:
    """ADR-FC-001 的两条禁令：不按 logical_id 取最新、不按 contract_id 从磁盘现取。

    判据 = AST：reader 模块里不得出现 `logical_id` 的**排序/最新**查询，
    也不得出现 `load_contract`（那是磁盘 registry alias 的读法）。
    """

    def test_reader_module_exists(self) -> None:
        assert READER_PY.is_file(), "frozen_contract_reader.py 不存在"

    def test_does_not_use_disk_registry_alias_reader(self) -> None:
        """不得 import/调用 `load_contract` —— 那是 registry 当前 alias（本缺陷的成因）。"""
        tree = _tree(READER_PY)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[-1])
        assert "load_contract" not in imported, (
            "reader 从 contracts 里 import 了 load_contract —— 那是按 registry alias 从磁盘"
            "现取，必须只按 bundle 的 slot_ref 读"
        )
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "load_contract" not in called

    def test_does_not_order_by_logical_id(self) -> None:
        """不得按 `logical_id` + 最新版本取（实测同一 logical_id 最多 46 代并存）。"""
        text = READER_PY.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # 找 .order_by( / .limit( 之类：任何「取最新」的形态都不许出现在按 logical_id 的查询上
                pass
        # 结构性判据：reader 的查询必须按主键 id 过滤（不是 logical_id）
        selects = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"where", "filter"}
        ]
        assert selects, "reader 里没有 where 过滤 —— 它可能在扫表"
        src = text
        assert "WorkpaperSyncDefinitionArtifact.id ==" in src, (
            "reader 没有按 definition 主键 id 过滤 —— 必须只按 slot_ref 里的 uuid 取"
        )
        assert "logical_id" not in src.split('"""')[-1], (
            "reader 的代码段里出现了 logical_id（只允许在 docstring 里作为禁令说明）"
        )

    def test_queries_definition_by_primary_key(self) -> None:
        tree = _tree(READER_PY)
        where_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "where"
        ]
        assert where_calls, "没有 where 调用"
        # 至少一处比较的左端是 WorkpaperSyncDefinitionArtifact.id
        found = False
        for call in where_calls:
            for cmp_node in ast.walk(call):
                if isinstance(cmp_node, ast.Compare):
                    left = cmp_node.left
                    if (
                        isinstance(left, ast.Attribute)
                        and left.attr == "id"
                        and isinstance(left.value, ast.Name)
                        and left.value.id == "WorkpaperSyncDefinitionArtifact"
                    ):
                        found = True
        assert found, "reader 没有按 WorkpaperSyncDefinitionArtifact.id 过滤"


class TestFrozenContractReaderErrorTyping:
    """R1.3：六类失败各自可辨（不得统一报「契约漂移」）。"""

    def test_all_error_codes_are_distinct(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        names = [
            "FrozenContractReaderError",
            "FrozenContractSlotNotDefinitionError",
            "FrozenContractDefinitionMissingError",
            "FrozenContractNotApprovedError",
            "FrozenContractBlobUnreadableError",
            "FrozenContractDigestDriftError",
            "FrozenContractUnparsableError",
        ]
        codes = {n: getattr(R, n).error_code for n in names}
        assert len(set(codes.values())) == len(codes), (
            f"错误码有重复 ⇒ 用户分不清是数据链断了、文件丢了、还是契约演化不兼容: {codes}"
        )

    def test_none_is_not_reported_as_contract_drift(self) -> None:
        """「契约漂移」这个词只能属于 digest 不符那一类。"""
        from app.services.workpaper_sync import frozen_contract_reader as R

        assert "drift" in R.FrozenContractDigestDriftError.error_code
        for name in (
            "FrozenContractSlotNotDefinitionError",
            "FrozenContractDefinitionMissingError",
            "FrozenContractNotApprovedError",
            "FrozenContractBlobUnreadableError",
            "FrozenContractUnparsableError",
        ):
            assert "drift" not in getattr(R, name).error_code, (
                f"{name} 的 error_code 也含 drift —— 会把不同成因碾成同一类"
            )

    def test_subtypes_inherit_reader_base(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R
        from app.services.workpaper_sync.models import SyncDomainError

        for name in (
            "FrozenContractSlotNotDefinitionError",
            "FrozenContractDefinitionMissingError",
            "FrozenContractNotApprovedError",
            "FrozenContractBlobUnreadableError",
            "FrozenContractDigestDriftError",
            "FrozenContractUnparsableError",
        ):
            sub = getattr(R, name)
            assert issubclass(sub, R.FrozenContractReaderError), name
            assert issubclass(sub, SyncDomainError), name


class TestFrozenContractReaderSlotHandling:
    """typed null marker 必须给出**可辨的答案**，不是空对象也不是崩溃。"""

    @pytest.mark.asyncio
    async def test_typed_null_marker_is_a_typed_refusal(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        reader = R.FrozenContractReader(session=object(), artifacts=object())
        bundle = _bundle(slot_type="contract:none:v1", ref="marker:contract:none:v1")
        with pytest.raises(R.FrozenContractSlotNotDefinitionError) as caught:
            await reader.read(bundle=bundle)
        assert "typed null marker" in str(caught.value)
        assert caught.value.diagnostics.get("slot_type") == "contract:none:v1"

    @pytest.mark.asyncio
    async def test_malformed_definition_ref_is_refused(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        reader = R.FrozenContractReader(session=object(), artifacts=object())
        bundle = _bundle(ref="definition:not-a-uuid")
        with pytest.raises(R.FrozenContractSlotNotDefinitionError):
            await reader.read(bundle=bundle)

    @pytest.mark.asyncio
    async def test_missing_slots_mapping_is_refused(self) -> None:
        from types import SimpleNamespace

        from app.services.workpaper_sync import frozen_contract_reader as R

        reader = R.FrozenContractReader(session=object(), artifacts=object())
        with pytest.raises(R.FrozenContractSlotNotDefinitionError):
            await reader.read(bundle=SimpleNamespace(bundle_id=uuid.uuid4()))


class TestFrozenContractReaderDefinitionRowChecks:
    """definition 行缺失 / kind 不对 / 非 approved 三类必须分开。"""

    class _Session:
        def __init__(self, row: object) -> None:
            self._row = row

        async def execute(self, *_a, **_kw):
            row = self._row

            class _R:
                def scalar_one_or_none(self_inner):
                    return row

            return _R()

    @staticmethod
    def _child(*, kind: str = "contract", state: str = "approved"):
        from types import SimpleNamespace

        return SimpleNamespace(
            id=uuid.uuid4(),
            kind=kind,
            state=state,
            sha256="a" * 64,
            blob_artifact_id=uuid.uuid4(),
            semantic_version="1.0.0",
            logical_id="d4.revenue_detail",
        )

    @pytest.mark.asyncio
    async def test_missing_row_is_its_own_error(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        reader = R.FrozenContractReader(
            session=self._Session(None), artifacts=object()
        )
        with pytest.raises(R.FrozenContractDefinitionMissingError):
            await reader.read(bundle=_bundle())

    @pytest.mark.asyncio
    async def test_wrong_kind_is_reported_as_missing_contract_child(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        reader = R.FrozenContractReader(
            session=self._Session(self._child(kind="template")), artifacts=object()
        )
        with pytest.raises(R.FrozenContractDefinitionMissingError) as caught:
            await reader.read(bundle=_bundle())
        assert "kind" in str(caught.value)

    @pytest.mark.asyncio
    async def test_not_approved_is_its_own_error(self) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        reader = R.FrozenContractReader(
            session=self._Session(self._child(state="draft")), artifacts=object()
        )
        with pytest.raises(R.FrozenContractNotApprovedError) as caught:
            await reader.read(bundle=_bundle())
        assert caught.value.diagnostics.get("state") == "draft"


class TestFrozenContractReaderBlobFailuresAreMapped:
    """公共模块的四类 blob 失败必须**逐类**映射到 reader 自己的类型（不合并）。"""

    @staticmethod
    def _reader_with_row(monkeypatch, exc: Exception):
        from app.services.workpaper_sync import frozen_contract_reader as R

        child = TestFrozenContractReaderDefinitionRowChecks._child()

        async def fake_read_payload(**_kw):
            raise exc

        monkeypatch.setattr(R, "read_definition_payload", fake_read_payload)
        reader = R.FrozenContractReader(
            session=TestFrozenContractReaderDefinitionRowChecks._Session(child),
            artifacts=object(),
        )
        return reader

    @pytest.mark.asyncio
    async def test_blob_missing_maps_to_unreadable(self, monkeypatch) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R
        from app.services.workpaper_sync import frozen_definition_blob as BLOB

        reader = self._reader_with_row(
            monkeypatch,
            BLOB.FrozenDefinitionBlobMissingError(
                "blob row 不存在", diagnostics={"definition_id": "x"}
            ),
        )
        with pytest.raises(R.FrozenContractBlobUnreadableError):
            await reader.read(bundle=_bundle())

    @pytest.mark.asyncio
    async def test_blob_unreadable_maps_to_unreadable(self, monkeypatch) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R
        from app.services.workpaper_sync import frozen_definition_blob as BLOB

        reader = self._reader_with_row(
            monkeypatch,
            BLOB.FrozenDefinitionBlobUnreadableError(
                "磁盘读不到", diagnostics={"path": "/x"}
            ),
        )
        with pytest.raises(R.FrozenContractBlobUnreadableError):
            await reader.read(bundle=_bundle())

    @pytest.mark.asyncio
    async def test_digest_mismatch_maps_to_drift(self, monkeypatch) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R
        from app.services.workpaper_sync import frozen_definition_blob as BLOB

        reader = self._reader_with_row(
            monkeypatch,
            BLOB.FrozenDefinitionBlobDigestMismatchError(
                "digest 不符", diagnostics={"frozen_sha256": "a"}
            ),
        )
        with pytest.raises(R.FrozenContractDigestDriftError):
            await reader.read(bundle=_bundle())

    @pytest.mark.asyncio
    async def test_decode_failure_maps_to_unparsable(self, monkeypatch) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R
        from app.services.workpaper_sync import frozen_definition_blob as BLOB

        reader = self._reader_with_row(
            monkeypatch,
            BLOB.FrozenDefinitionBlobError("不是合法 JSON", diagnostics={}),
        )
        with pytest.raises(R.FrozenContractUnparsableError):
            await reader.read(bundle=_bundle())


class TestFrozenContractReaderParsesAndCrossChecks:
    """payload 能读回时的两道 digest 对账都必须真的跑。"""

    @staticmethod
    def _reader(monkeypatch, payload: dict, slot_digest: str):
        from app.services.workpaper_sync import frozen_contract_reader as R

        child = TestFrozenContractReaderDefinitionRowChecks._child()

        async def fake_read_payload(**_kw):
            return payload

        monkeypatch.setattr(R, "read_definition_payload", fake_read_payload)
        reader = R.FrozenContractReader(
            session=TestFrozenContractReaderDefinitionRowChecks._Session(child),
            artifacts=object(),
        )
        return reader, child

    @pytest.mark.asyncio
    async def test_parse_failure_is_its_own_error(self, monkeypatch) -> None:
        from app.services.workpaper_sync import frozen_contract_reader as R

        reader, _ = self._reader(monkeypatch, {"not": "a contract"}, "a" * 64)
        with pytest.raises(R.FrozenContractUnparsableError) as caught:
            await reader.read(bundle=_bundle(digest="a" * 64))
        assert "parse_error" in caught.value.diagnostics

    @pytest.mark.asyncio
    async def test_slot_digest_mismatch_after_parse_is_drift(self, monkeypatch) -> None:
        """解析成功但 canonical digest ≠ slot digest ⇒ drift（不是 unparsable）。

        这是「definition 行与 bundle 不同步」这一类缺陷的唯一可见处。
        """
        import json

        from app.services.workpaper_sync import frozen_contract_reader as R

        real = _real_contract_payload()
        reader, _ = self._reader(monkeypatch, json.loads(json.dumps(real)), "b" * 64)
        with pytest.raises(R.FrozenContractDigestDriftError) as caught:
            await reader.read(bundle=_bundle(digest="b" * 64))
        assert caught.value.diagnostics.get("slot_digest") == "b" * 64
        assert "contract_canonical_sha256" in caught.value.diagnostics


def _real_contract_payload() -> dict:
    """取一份**真实**的 per-entry 契约 payload（避免手搓字段）。

    🔴 必须排除示例/候选契约：目录里有 `example.candidate*` 之类**故意不合法**的夹具，
    拿它们当「真实契约」会让 digest 对账那条判据永远走不到（先被 parse 拒掉）。
    """
    import json

    contracts_dir = BACKEND / "data" / "workpaper_sync_contracts"
    candidates = sorted(contracts_dir.glob("*.json"), key=lambda p: p.stat().st_size)
    for path in candidates:
        if "example" in path.name or "candidate" in path.name:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        # 身份必须与文件名一致（这是目录里真实契约的定义）
        if payload.get("contract_id") != path.stem:
            continue
        return payload
    raise AssertionError(f"{contracts_dir} 里没有可用的真实契约 payload —— 本判据无分母")
