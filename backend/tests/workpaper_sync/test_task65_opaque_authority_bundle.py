# -*- coding: utf-8 -*-
r"""Task 65 离线守卫：opaque lane 登记表 ↔ 源码双向锁死、消费门只查不发布、身份参数已收口。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 6 Task 65
点名 Property：**50 / 64 / 69**
点名 AC：2.11 · 3.9 · 5.5 · 6.19 · 12.6 · 12.10

═══ 本文件证什么 ═══

Task 65 的三条正文各有一组判据：

* **「custom 继续以 xlsx artifact 为唯一权威、不调标准 JSON projection writer」**
  → §1 lane 登记表是 custom/opaque 的**唯一可枚举分母**，且与源码 `opaque_entry_id(...)`
  调用点、`commit_bytes(lane_id=...)` 实参三向对齐；§5 记账 room/ack/application 三格
  未接入并指名归属（不写「已接入」的假成功文案）。
* **「每类 custom/opaque entry 必须先发布 approved authority-model definition 与
  non-null approved bundle」** → §3 消费门**结构上**没有发布能力（构造函数不吃
  publisher/artifacts/repository、模块 import 图里没有 `DefinitionPublisher`），
  发布只在 `provision()` 且唯一宿主是那个脚本；§2 三 slot 只能是 registry typed null
  marker，definition child 一律拒。
* **「application key 仍冻结 bundle/authority-model digest」** → §4 `commit_bytes` 的
  签名里已经**没有** `authority_model` 参数（原先它有默认值 `custom_authoritative_ooxml`
  ⇒ 漏传静默落 custom），authority model 改由 lane 单向决定。真库侧的
  「same incoming + 不同 bundle/authority ⇒ 不同 key」在 `_pg.py` 那半。

═══ 每条判据都可被单点 falsify ═══

登记表类判据全部走**可注入**入口（`assert_lane_registry_covers_source(sites=...)` /
`assert_commit_bytes_lane_arguments_match_registry(arguments=...)` /
`assert_lane_self_consistent(lanes=...)`）。不可注入时守卫只能断言「当前这张表通过」，
而那对「判据是否真的存在」毫无信息量 —— 把函数体删空，守卫照样绿。

用法（仓库根）::

    .\.venv\Scripts\python.exe -m pytest \
        backend/tests/workpaper_sync/test_task65_opaque_authority_bundle.py -q
"""
from __future__ import annotations

import ast
import inspect
import sys
from dataclasses import replace
from pathlib import Path

import pytest

_THIS = Path(__file__).resolve()
ROOT = _THIS.parents[3]
BACKEND = ROOT / "backend"

if str(BACKEND) not in sys.path:  # pragma: no cover - import 自举
    sys.path.insert(0, str(BACKEND))

from app.services.workpaper_sync import opaque_entry_gate as OG  # noqa: E402
from app.services.workpaper_sync import writer_migration as WM  # noqa: E402
from app.services.workpaper_sync.models import AuthorityModel, BundleSlot  # noqa: E402

GATE_PATH = BACKEND / "app" / "services" / "workpaper_sync" / "opaque_entry_gate.py"
WM_PATH = BACKEND / "app" / "services" / "workpaper_sync" / "writer_migration.py"
CTX_PATH = BACKEND / "app" / "services" / "custom_workpaper_context.py"
PROVISION_SCRIPT = ROOT / OG.PROVISION_HOST_SCRIPT


def _src(path: Path) -> str:
    """读磁盘真相。

    🔴 用 `Path.read_text` 而不是 `inspect.getsource`：后者读的是 import 时缓存的模块，
    对「刚被并发会话改过的文件」会给出陈旧内容（memory 记录的实测坑）。
    """
    return path.read_text(encoding="utf-8")


def _tree(path: Path) -> ast.Module:
    return ast.parse(_src(path), filename=str(path))


def _find_function(tree: ast.Module, qualname: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """按 `Class.method` 或 `func` 定位定义节点（逐段下钻，不用 grep）。"""
    node: ast.AST = tree
    for part in qualname.split("."):
        found = None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if child.name == part:
                    found = child
                    break
        if found is None:
            raise AssertionError(f"AST 里找不到 {qualname!r}（卡在 {part!r}）")
        node = found
    assert isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)), (
        f"{qualname} 不是函数定义"
    )
    return node


# ═══════════════════════════════════════════════════════════════════════════
# §1 lane 登记表 ↔ 源码三向对齐
# ═══════════════════════════════════════════════════════════════════════════


def test_registry_covers_every_source_call_site() -> None:
    """现实分母：源码里每处 `opaque_entry_id(...)` 都恰好命中一条登记，反之亦然。"""
    coverage = OG.assert_lane_registry_covers_source()
    assert set(coverage) == set(OG.lane_ids())
    for lane_id, hits in coverage.items():
        assert hits, f"lane {lane_id} 没有任何源码调用点"


def test_every_registered_writer_really_exists() -> None:
    """OG-1：登记的 `writer_ref` 能被 import + getattr 取到且可调用。"""
    verified = OG.assert_lane_writers_exist()
    assert len(verified) == len(OG.OPAQUE_AUTHORITY_LANES)
    assert sorted(verified) == sorted(lane.writer_ref for lane in OG.OPAQUE_AUTHORITY_LANES)


def test_commit_bytes_lane_arguments_match_registry() -> None:
    """每处 `commit_bytes(lane_id=...)` 的字面量等于它所在 writer 的登记 lane_id。"""
    mapping = OG.assert_commit_bytes_lane_arguments_match_registry()
    assert len(mapping) == len(OG.OPAQUE_AUTHORITY_LANES), (
        f"commit_bytes 的 lane_id 实参数 {len(mapping)} 与登记 lane 数 "
        f"{len(OG.OPAQUE_AUTHORITY_LANES)} 不等 —— 一条 lane 恰对应一处调用"
    )
    assert sorted(mapping.values()) == sorted(OG.lane_ids())


def test_call_site_discovery_uses_ast_not_grep() -> None:
    """判据必须是 AST：源码里 `opaque_entry_id` 的**字样**远多于真实调用点。

    这条不是形式主义。若改用 grep，`def opaque_entry_id(`、`import opaque_entry_id`、
    docstring 与注释里的每次提及都会进分母 ⇒ 「删掉一个真实调用点、在注释里留个名字」
    也能让分母看起来没变（假绿第②源）。
    """
    sites = OG.discover_opaque_entry_id_call_sites()

    # `writer_migration.py` 是最干净的对照：它含 `opaque_entry_id` 的**定义**、`__all__`
    # 条目与多处 docstring 提及（字样数远大于 1），而真实调用点 **0 个**。grep 式判据
    # 会把它们全算进分母。
    wm_textual = _src(WM_PATH).count("opaque_entry_id")
    wm_sites = [s for s in sites if s.module.endswith("writer_migration")]
    assert wm_textual > 1, f"对照文件的字样数应 >1，实得 {wm_textual}（对照失效）"
    assert not wm_sites, (
        f"`writer_migration` 里只有 `opaque_entry_id` 的定义与提及，不该被算成调用点，"
        f"实得 {[s.line for s in wm_sites]}"
    )

    # 全体：AST 调用点数严格少于全体字样数。
    total_textual = sum(
        _src(path).count("opaque_entry_id")
        for path in (BACKEND / "app").rglob("*.py")
        if "opaque_entry_id" in _src(path)
    )
    assert len(sites) < total_textual, (
        f"AST 调用点 {len(sites)} 应严格少于字样出现次数 {total_textual}（定义处、"
        "import、注释都不是调用点）"
    )


def test_unregistered_call_site_fails_closed() -> None:
    """方向①：新加一条 opaque writer 却没进登记表 ⇒ 打红。"""
    rogue = OG.OpaqueEntryIdCallSite(
        module="app.routers.some_new_opaque_writer",
        relative_path="backend/app/routers/some_new_opaque_writer.py",
        line=42,
        entry_id_source=OG.EntryIdSource.wp_id,
        enclosing_qualname="save_it",
    )
    real = list(OG.discover_opaque_entry_id_call_sites())
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_lane_registry_covers_source([*real, rogue])
    assert "未登记的调用点" in str(exc.value)
    assert "some_new_opaque_writer" in str(exc.value)


def test_registration_without_call_site_fails_closed() -> None:
    """方向②：登记了一条已经消失的 lane ⇒ 打红（与 manifest 的 stale overlay 同款）。"""
    real = [
        s
        for s in OG.discover_opaque_entry_id_call_sites()
        if not s.module.endswith("wopi_service")
    ]
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_lane_registry_covers_source(real)
    assert "无调用点的登记" in str(exc.value)
    assert "wopi_put_file" in str(exc.value)


def test_entry_id_source_drift_fails_closed() -> None:
    """方向③：把 `wp_code=ctx.wp_code` 改成 `wp_code=None` ⇒ 打红。

    这条判据护的是 entry_id 命名空间：`wp_code=None` 让 `opaque_entry_id` 退回
    `str(wp_id)`，同一份权威文件会落到另一个 entry 下，rollback 与 evidence 查不到
    对方的行。
    """
    drifted = [
        replace(site, entry_id_source=OG.EntryIdSource.wp_id)
        if site.module.endswith("custom_workpaper_cells")
        else site
        for site in OG.discover_opaque_entry_id_call_sites()
    ]
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_lane_registry_covers_source(drifted)
    message = str(exc.value)
    assert "实参形态漂移" in message
    assert "custom_cells" in message and "wp_code" in message


def test_wrong_lane_id_argument_fails_closed() -> None:
    """把 custom 的 `lane_id="custom_cells"` 改成另一条 lane ⇒ 打红。

    这一改会把 custom 底稿的 authority model 从 `custom_authoritative_ooxml` 静默换成
    `opaque_single_onlyoffice`，evidence 分桶与 `application_key` 一起失真。
    """
    tampered = [
        replace(arg, lane_id="wopi_put_file")
        if arg.module.endswith("custom_workpaper_cells")
        else arg
        for arg in OG.discover_commit_bytes_lane_arguments()
    ]
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_commit_bytes_lane_arguments_match_registry(tampered)
    assert "lane_id 不符" in str(exc.value)


def _synth_call(snippet: str) -> ast.Call:
    return next(node for node in ast.walk(ast.parse(snippet)) if isinstance(node, ast.Call))


def test_non_literal_lane_id_is_rejected_by_discovery() -> None:
    """`lane_id=some_var` 必须被拒 —— 运行期变量会让静态判据退化成猜测。

    🔴 判据是**行为**（喂合成 AST 节点给生产那份 `lane_id_argument_of`），不是
    「源码里有没有那句错误文案」。首版写成后者，变异检验实测判 GREEN（M06）：把
    `if not (isinstance(arg, ast.Constant) ...)` 改成 `if False:` 不动任何字符串，
    grep 式守卫照样绿 —— 那正是本 spec 记录的假绿第②源，我自己踩了一次。
    """
    call = _synth_call("await writer.commit_bytes(lane_id=some_lane, payload=b'x')")
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.lane_id_argument_of(call, where="synthetic:1")
    assert "字面量" in str(exc.value)

    # 反向自检：字面量必须通过，否则上面那条红得没有信息量。
    ok = _synth_call('await writer.commit_bytes(lane_id="custom_cells", payload=b"x")')
    assert OG.lane_id_argument_of(ok, where="synthetic:2") == "custom_cells"

    # 非字符串字面量（数字）同样拒：`isinstance(arg.value, str)` 那半也要可 falsify。
    numeric = _synth_call("await writer.commit_bytes(lane_id=7, payload=b'x')")
    with pytest.raises(OG.OpaqueLaneRegistryDriftError):
        OG.lane_id_argument_of(numeric, where="synthetic:3")


def test_missing_lane_id_argument_fails_closed() -> None:
    """`commit_bytes(...)` 漏掉 `lane_id=` ⇒ 打红（它是必填 keyword）。"""
    call = _synth_call("await writer.commit_bytes(payload=b'x', document_type='xlsx')")
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.lane_id_argument_of(call, where="synthetic:4")
    assert "缺 `lane_id=` 实参" in str(exc.value)

    signature = inspect.signature(WM.AuthoritativeContentWriter.commit_bytes)
    lane = signature.parameters["lane_id"]
    assert lane.default is inspect.Parameter.empty, (
        "`lane_id` 不得有默认值 —— 有默认值就等于把「这条写入路径属于哪条 lane」变成"
        "可以漏传的东西，而 authority model 由它单向决定"
    )
    assert lane.kind is inspect.Parameter.KEYWORD_ONLY


# ═══════════════════════════════════════════════════════════════════════════
# §2 lane 登记自洽 + 三 slot 只能是 typed null marker
# ═══════════════════════════════════════════════════════════════════════════


def test_registry_is_self_consistent() -> None:
    OG.assert_lane_self_consistent()


def test_instrumentation_required_true_fails_closed() -> None:
    """AC 6.19：无显式 contract 的 custom/user-upload 文件不得被强行 instrumentation。"""
    bad = [replace(OG.OPAQUE_AUTHORITY_LANES[0], instrumentation_required=True)]
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_lane_self_consistent(bad)
    assert "instrumentation_required=True" in str(exc.value)
    assert "6.19" in str(exc.value)


def test_html_counterpart_and_authority_model_are_cross_locked() -> None:
    """design §「authority model 由有没有 HTML 对端决定」必须是可执行判据。

    没有这条时 `has_html_counterpart` 就只是一列注释，改了不会有任何后果。
    """
    custom = next(
        lane for lane in OG.OPAQUE_AUTHORITY_LANES if lane.lane_id == "custom_cells"
    )
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_lane_self_consistent([replace(custom, has_html_counterpart=False)])
    assert "has_html_counterpart" in str(exc.value)
    upload = next(
        lane for lane in OG.OPAQUE_AUTHORITY_LANES if lane.lane_id == "offline_upload"
    )
    with pytest.raises(OG.OpaqueLaneRegistryDriftError):
        OG.assert_lane_self_consistent([replace(upload, has_html_counterpart=True)])


def test_projection_contract_lane_is_rejected() -> None:
    """OG-2：`projection_contract` 不得登记为 opaque lane（两条通道 slot 规则相反）。"""
    bad = replace(
        OG.OPAQUE_AUTHORITY_LANES[0],
        authority_model=AuthorityModel.projection_contract,
    )
    with pytest.raises(OG.OpaqueAuthorityModelNotOpaqueError) as exc:
        OG.assert_lane_self_consistent([bad])
    assert "projection" in str(exc.value)


def test_duplicate_lane_id_is_rejected() -> None:
    first = OG.OPAQUE_AUTHORITY_LANES[0]
    with pytest.raises(OG.OpaqueLaneRegistryDriftError) as exc:
        OG.assert_lane_self_consistent([first, first])
    assert "lane_id 重复" in str(exc.value)


def _marker_slots() -> dict[BundleSlot, object]:
    from app.services.workpaper_sync.definitions import marker_slot_spec

    return {slot: marker_slot_spec(slot) for slot in BundleSlot}


def test_marker_slots_pass_and_definition_slot_is_rejected() -> None:
    """OG-4：三 slot 全 marker 通过；任一 slot 是 `definition` 即拒。

    `models.validate_bundle_slot` 对 `definition` 是**放行**的（它不知道调用方在哪条
    通道），所以这条拒绝必须由本模块补 —— 委派过去就没有任何单点能锁住它。
    """
    from app.services.workpaper_sync.definitions import definition_slot_spec

    good = _marker_slots()
    OG.assert_slots_are_typed_null_markers(good, where="test")  # type: ignore[arg-type]

    for slot in BundleSlot:
        tampered = dict(good)
        tampered[slot] = definition_slot_spec(
            slot,
            definition_id=__import__("uuid").UUID(int=7),
            definition_sha256="a" * 64,
        )
        with pytest.raises(OG.OpaqueSlotNotTypedNullMarkerError) as exc:
            OG.assert_slots_are_typed_null_markers(tampered, where="test")  # type: ignore[arg-type]
        assert "definition" in str(exc.value)
        assert "6.19" in str(exc.value) or "2.3" in str(exc.value)


def test_forged_marker_digest_is_rejected() -> None:
    """伪造 typed null digest ⇒ 拒（registry 是 marker 的唯一来源）。"""
    from app.services.workpaper_sync.models import BundleSlotSpec

    good = _marker_slots()
    tampered = dict(good)
    real = good[BundleSlot.contract]
    tampered[BundleSlot.contract] = BundleSlotSpec(
        BundleSlot.contract,
        real.slot_type,  # type: ignore[union-attr]
        real.slot_ref,  # type: ignore[union-attr]
        "b" * 64,
    )
    with pytest.raises(OG.OpaqueSlotNotTypedNullMarkerError) as exc:
        OG.assert_slots_are_typed_null_markers(tampered, where="test")  # type: ignore[arg-type]
    assert "registry" in str(exc.value)


def test_missing_slot_is_rejected() -> None:
    good = _marker_slots()
    for slot in BundleSlot:
        tampered = {k: v for k, v in good.items() if k is not slot}
        with pytest.raises(OG.OpaqueSlotNotTypedNullMarkerError) as exc:
            OG.assert_slots_are_typed_null_markers(tampered, where="test")  # type: ignore[arg-type]
        assert slot.value in str(exc.value)


# ═══════════════════════════════════════════════════════════════════════════
# §3 消费门结构上没有发布能力；发布只有一个宿主
# ═══════════════════════════════════════════════════════════════════════════


def test_gate_constructor_cannot_publish() -> None:
    """`OpaqueEntryGate` 只吃 session —— 没有 publisher / artifacts / repository。

    判据落在**构造签名**上而不是「源码里没出现 publish 这个词」：后者是 grep 式判据，
    改个变量名就绿了。
    """
    params = list(inspect.signature(OG.OpaqueEntryGate.__init__).parameters)
    assert params == ["self", "session"], (
        f"gate 构造参数应只有 session，实得 {params} —— 拿到 publisher/artifacts/"
        "repository 就意味着「消费路径顺手 approve 自己要用的 bundle」在装配层可表达"
    )


def test_gate_module_does_not_import_publishing_machinery() -> None:
    """import 图判据：gate 模块不引入任何发布器。"""
    tree = _tree(GATE_PATH)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    forbidden = {
        "DefinitionPublisher",
        "CanonicalArtifactRepository",
        "WorkpaperSyncRepository",
        "ContentMutationService",
    }
    leaked = sorted(forbidden & imported)
    assert not leaked, f"gate 模块 import 了发布/写入面: {leaked}"


def test_provisioner_split_resolve_and_provision() -> None:
    """`ensure()` 必须已消失，`resolve()` / `provision()` 必须存在。

    保留 `ensure()` 会留下一条「查不到就发布」的旧路径 —— 那正是 AC 6.19 要消灭的形态；
    而它一旦还在，任何调用点都可以绕过 gate。
    """
    assert hasattr(WM.OpaqueAuthorityProvisioner, "resolve")
    assert hasattr(WM.OpaqueAuthorityProvisioner, "provision")
    assert not hasattr(WM.OpaqueAuthorityProvisioner, "ensure"), (
        "`OpaqueAuthorityProvisioner.ensure()` 仍在 —— 它是「写路径顺手 approve」的旧入口，"
        "死代码必须删除而不是留着"
    )
    resolve_params = list(
        inspect.signature(WM.OpaqueAuthorityProvisioner.resolve).parameters
    )
    assert resolve_params == ["self", "lane_id"], (
        f"`resolve()` 参数应只有 lane_id，实得 {resolve_params} —— 收 project_id/wp_id "
        "意味着它还惦记着发布（那两个参数只有 `publish_definition_blob` 需要）"
    )


def test_commit_bytes_calls_resolve_not_provision() -> None:
    """AST 判据：`commit_bytes` 里对 provisioner 的调用只能是 `resolve`。"""
    node = _find_function(_tree(WM_PATH), "AuthoritativeContentWriter.commit_bytes")
    called: list[str] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "_provisioner"
        ):
            called.append(func.attr)
    assert called == ["resolve"], (
        f"`commit_bytes` 对 provisioner 的调用实为 {called} —— 业务写入路径只能 resolve；"
        "调 provision 就是「写路径自己给自己发证」"
    )


def test_commit_bytes_no_longer_takes_authority_model() -> None:
    """收口判据：`commit_bytes` / `commit_restore` 签名里都没有 `authority_model`。

    原签名是 `authority_model: AuthorityModel | str = AuthorityModel.custom_authoritative_ooxml`
    —— 一个**带默认值的身份参数**。user-upload 的 opaque 文件漏传即静默落成 custom，
    四层静态检查都查不出。
    """
    for method in ("commit_bytes", "commit_restore"):
        params = inspect.signature(
            getattr(WM.AuthoritativeContentWriter, method)
        ).parameters
        assert "authority_model" not in params, (
            f"`{method}` 仍收 `authority_model` —— authority model 必须由 lane 登记"
            "单向决定，调用方不得传一个可漏可错的身份参数"
        )
        assert "lane_id" in params, f"`{method}` 缺 `lane_id`"
        assert params["lane_id"].default is inspect.Parameter.empty


def test_provision_has_exactly_one_host() -> None:
    """`provision()` 的调用点只允许出现在唯一宿主脚本里。

    与 Task 76 的 M18 同款判据：provisioner 若没有任何消费宿主，它就是一段谁都不跑的
    代码；若有第二个宿主，「先发布」这条门就有第二条入口。
    """
    assert PROVISION_SCRIPT.is_file(), (
        f"登记的唯一宿主脚本不存在: {OG.PROVISION_HOST_SCRIPT} —— fail-closed 的错误消息"
        "会给出一句假指引"
    )
    hosts: list[str] = []
    for path in sorted((BACKEND / "app").rglob("*.py")) + sorted(
        (BACKEND / "scripts").rglob("*.py")
    ):
        source = _src(path)
        if ".provision(" not in source:
            continue
        for node in ast.walk(ast.parse(source, filename=str(path))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "provision"
            ):
                hosts.append(path.relative_to(ROOT).as_posix())
    assert sorted(set(hosts)) == [OG.PROVISION_HOST_SCRIPT], (
        f"`provision()` 的宿主实为 {sorted(set(hosts))}，应只有 {OG.PROVISION_HOST_SCRIPT}"
    )


def test_provision_script_consumes_the_production_gate() -> None:
    """`--check` / `--apply` 的判据必须跑生产那份 gate，不许脚本自己抄一段查询。

    抄一段的后果是「脚本说 OK 但业务请求仍然 500」。
    """
    source = _src(PROVISION_SCRIPT)
    assert "OpaqueEntryGate(session=" in source
    assert "resolve_approved_bundle(lane_id=" in source
    tree = ast.parse(source, filename=str(PROVISION_SCRIPT))
    probe = _find_function(tree, "probe_gate")
    calls = [
        node.func.attr
        for node in ast.walk(probe)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "resolve_approved_bundle" in calls


def test_provision_targets_derive_from_registry_not_a_second_list() -> None:
    """provision 目标由登记表现算，脚本里不得有第二份 authority model 清单。"""
    source = _src(PROVISION_SCRIPT)
    tree = ast.parse(source, filename=str(PROVISION_SCRIPT))
    node = _find_function(tree, "resolve_targets")

    # 🔴 判据是「函数体内有对这三个 guard 的 **Call**」，不是「名字出现在源码段里」。
    #    首版用 `assert guard in body`，变异检验实测判 GREEN（M19）：把
    #    `assert_lane_registry_covers_source()` 这行换成 `pass` 之后，函数体里那句
    #    `from ... import (assert_lane_registry_covers_source, ...)` 让名字仍然在 ——
    #    grep 式判据看不出调用已经没了。
    called = {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }
    for guard in (
        "assert_lane_registry_covers_source",
        "assert_lane_writers_exist",
        "assert_commit_bytes_lane_arguments_match_registry",
    ):
        assert guard in called, (
            f"`resolve_targets` 没有**调用** {guard} —— 发布前置判据被摘掉后，"
            "会给一个「登记表已与源码脱钩」的库发布出没有消费方的 bundle"
        )

    # 遍历登记表这一条同样落在 AST 上（`for lane in OPAQUE_AUTHORITY_LANES`）。
    iterated = {
        child.iter.id
        for child in ast.walk(node)
        if isinstance(child, ast.For) and isinstance(child.iter, ast.Name)
    }
    assert "OPAQUE_AUTHORITY_LANES" in iterated, (
        "`resolve_targets` 必须遍历 lane 登记表 —— 抄一份清单意味着新登记一条 lane 不会"
        "自动进 provision 目标，gate 侧会永远 fail closed 而运维不知道该发布什么"
    )


# ═══════════════════════════════════════════════════════════════════════════
# §4 evidence 侧：opaque lane 的 authority model 真源与场景替换
# ═══════════════════════════════════════════════════════════════════════════


def test_every_lane_authority_model_is_a_substituting_one() -> None:
    """Property 69：每条 lane 的 authority model 都在允许字段级替换的枚举里。

    这条把 lane 登记与 `evidence.SUBSTITUTING_AUTHORITY_MODELS` 锁在一起：登记一个不在
    替换枚举里的 authority model，会让 `derive_required_scenarios` 对该 lane 要求字段级
    merge/conflict 两场景 —— 而 opaque lane 没有字段，那两场景结构性不可满足。
    """
    from app.services.workpaper_sync.evidence import SUBSTITUTING_AUTHORITY_MODELS

    for lane in OG.OPAQUE_AUTHORITY_LANES:
        assert lane.authority_model in SUBSTITUTING_AUTHORITY_MODELS, (
            f"lane {lane.lane_id} 的 authority model {lane.authority_model.value} 不在 "
            f"SUBSTITUTING_AUTHORITY_MODELS 内"
        )


def test_authority_model_for_lane_is_the_single_source() -> None:
    """authority model 只能由 lane 登记决定；未登记 lane 一律拒。"""
    for lane in OG.OPAQUE_AUTHORITY_LANES:
        assert OG.authority_model_for_lane(lane.lane_id) is lane.authority_model
    with pytest.raises(OG.OpaqueLaneNotRegisteredError):
        OG.authority_model_for_lane("no_such_lane")


def test_lanes_for_authority_model_partitions_the_registry() -> None:
    """按 authority model 分桶必须是**划分**（不重不漏）。"""
    total = 0
    for model in {lane.authority_model for lane in OG.OPAQUE_AUTHORITY_LANES}:
        total += len(OG.lanes_for_authority_model(model))
    assert total == len(OG.OPAQUE_AUTHORITY_LANES)


# ═══════════════════════════════════════════════════════════════════════════
# §5 诚实记账：未接入的三格必须登记归属，不得写成已接入
# ═══════════════════════════════════════════════════════════════════════════


def test_custom_lane_room_debt_is_registered_not_claimed_done() -> None:
    debt = OG.CUSTOM_LANE_ROOM_DEBT
    assert debt["lane_id"] == "custom_cells"
    assert set(debt["missing_facilities"]) == {
        "unified_room",
        "durable_forcesave_ack",
        "content_application",
    }
    assert debt["verification_status"] == "UNVERIFIABLE"
    assert debt["adjudication_owner_task"] == "71", (
        "归属必须指向真正把守那条门的任务（Task 71 的 multi_resolver）"
    )
    assert "deferred" in debt["blocking_reason"]


def test_entry_id_namespace_split_is_recorded_with_measured_cost() -> None:
    """entry_id 命名空间分叉必须记成**已知事实 + 实测代价**，而不是隐身。"""
    note = OG.ENTRY_ID_NAMESPACE_SPLIT_NOTE
    lanes_in_note = (
        set(note["lanes_using_wp_code"])
        | set(note["lanes_using_wp_code_with_sheet"])
        | set(note["lanes_using_wp_id"])
    )
    assert lanes_in_note == set(OG.lane_ids()), (
        "分叉登记必须覆盖全部 lane —— 漏一条就等于对那条 lane 的 entry_id 口径没有记账"
    )
    for lane in OG.OPAQUE_AUTHORITY_LANES:
        bucket = {
            OG.EntryIdSource.wp_code: "lanes_using_wp_code",
            OG.EntryIdSource.wp_code_with_sheet: "lanes_using_wp_code_with_sheet",
            OG.EntryIdSource.wp_id: "lanes_using_wp_id",
        }[lane.entry_id_source]
        assert lane.lane_id in note[bucket], (
            f"lane {lane.lane_id} 的 entry_id_source={lane.entry_id_source.value} "
            f"与分叉登记的分桶 {bucket} 不符"
        )
    assert note["adjudication_owner_task"] == "67"


# ═══════════════════════════════════════════════════════════════════════════
# §6 死代码：`resolve_is_custom_sync` 只能定义一次
# ═══════════════════════════════════════════════════════════════════════════


def test_resolve_is_custom_sync_is_defined_exactly_once() -> None:
    """AST 计数取代 grep 式守卫。

    改造前 `custom_workpaper_context.py` 里这个函数被定义了**两次**（后者覆盖前者 ⇒
    前者是死代码）。既有守卫
    `test_custom_workpaper_oo_file_resolution.py::assert "def resolve_is_custom_sync(" in code`
    是 grep 式判据，**无法区分定义了一次还是两次** —— 本 spec 记录的假绿第②源。
    """
    tree = _tree(CTX_PATH)
    names = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert names.count("resolve_is_custom_sync") == 1, (
        f"`resolve_is_custom_sync` 定义了 {names.count('resolve_is_custom_sync')} 次 —— "
        "重复定义里靠前的那份是永远不会被调用的死代码"
    )
    duplicated = sorted({n for n in names if names.count(n) > 1})
    assert not duplicated, f"`{CTX_PATH.name}` 里有重复函数定义: {duplicated}"
