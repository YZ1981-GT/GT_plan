# -*- coding: utf-8 -*-
"""Task 19 结构与真实执行守卫：上传 / WOPI / custom writer 迁入统一 revision 域。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 1 Task 19
Requirements: 2.2, 2.11, 9.11, 12.6, 12.7
Properties: **P50**（custom 保持 xlsx 权威且进入统一 representation 协议）/
**P61**（所有 writer 进入唯一 revision 域）

═══ 判据取法：三类，各自可被单点变异 falsify ═══

1. **AST 结构判据**（§一）：逐 writer 断言「没有私有版本计数器」「没有裸 commit」
   「真的接了统一入口」。三条必须成对出现 —— 前两条是否定式（把整段删掉也满足），
   第三条是正面接线。
2. **真实执行判据**（§二、§三）：`opaque_entry_id` 的路径安全、
   `OpaqueAuthorityProvisioner` 对 `projection_contract` 的拒绝、
   `RollbackSourceLocator` 的六条拒绝。这些是**否定式承诺**（「candidate 不可能当
   回滚源」），只能靠注入反例证明。
3. **真库行为判据**：一次上传/PutFile/custom 写入恰一次 revision、custom 的
   `projection_sha256` 恒为 None（Property 50 的核心）、rollback 产生新版本而不改旧行
   —— 在 `test_task19_writer_migration_pg.py`，因为 `_TransactionWitness` 的判据是
   `pg_current_xact_id()`，SQLite 上不可判定（本任务实测：
   `no such function: pg_advisory_xact_lock`）。

═══ 为什么每条拒绝一个异常类型 ═══

Task 18 的变异检验实测到：两条拒绝共用一个 `error_code` 时，短路掉第一个 `if` 会被
第二个接住并抛出**同样的**码，于是第一条判据退化成不可达分支、变异判 GREEN。
`_REFUSALS` 因此逐条钉 `error_code`，而不是只断言「抛了 WriterMigrationError」。
"""
from __future__ import annotations

import ast
import inspect
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest

_REPO = Path(__file__).resolve().parents[3]
_BACKEND = _REPO / "backend"
_APP = _BACKEND / "app"

if str(_BACKEND) not in sys.path:  # pragma: no cover - import 环境自举
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

_CUSTOM_CELLS = _APP / "routers" / "custom_workpaper_cells.py"
_WOPI = _APP / "services" / "wopi_service.py"
_UPLOAD = _APP / "services" / "wp_download_service.py"
_WRITER_MIGRATION = _APP / "services" / "workpaper_sync" / "writer_migration.py"
_CONTENT_MUTATION = _APP / "services" / "workpaper_sync" / "content_mutation.py"
_MIGRATION_SVC = _APP / "services" / "wp_migration_service.py"
_VERSION_TRAIL = _APP / "services" / "version_trail_service.py"
_STORAGE = _APP / "services" / "wp_storage_service.py"
_F2_PLAN = _APP / "routers" / "wp_render_strategies" / "_f2_stocktake_plan_sync.py"
_F2_SUMMARY = _APP / "routers" / "wp_render_strategies" / "_f2_stocktake_summary_sync.py"

#: 迁入统一入口的三条 writer：`(源文件, 函数 qualname, 期望的 ContentSource 常量名)`。
#:
#: 🔴 参数化而不是三段复制：Task 19 之后还有 F2/rollback/历史恢复要接同一条链，新增行
#: 只改这张表。每条 writer 的三个判据（零私有计数器 / 零裸 commit / 真接线）因此逐行
#: 独立报告，而不是被第一条失败遮蔽。
_MIGRATED_WRITERS: tuple[tuple[Path, str, str], ...] = (
    (_CUSTOM_CELLS, "update_custom_cells", "CUSTOM"),
    (_WOPI, "WOPIHostService.put_file", "WOPI"),
    (_UPLOAD, "WpUploadService.upload_file", "UPLOAD"),
    # F2-22 / F2-23：manifest 里 F2 entry 的 `capability=single_onlyoffice`，权威内容是
    # docx 本体，所以走同一条 authoritative-bytes lane（Requirement 12.7 的「迁到统一
    # 协议」；capability 不动，第二套流程留给 Task 60）。
    (_F2_PLAN, "_save_fields", "ONLYOFFICE"),
    (_F2_SUMMARY, "_save_fields", "ONLYOFFICE"),
)

#: 迁入 **projection lane**（`commit_projection` → `stage_html_projection` +
#: `commit_html_projection`）的恢复 writer：`(源文件, qualname, 期望的 ContentSource)`。
#:
#: 与 :data:`_MIGRATED_WRITERS` 分成两张表而不是加一列 lane 标记：两条 lane 的必需步骤
#: 元组是**互斥**的（一条有 representation/entry_pointer 无 current_pointer，另一条反
#: 之），判据也必须各自独立 —— 合成一张表 + 一个开关，就等于给「走错 lane」开了后门。
_PROJECTION_WRITERS: tuple[tuple[Path, str, str], ...] = (
    (_MIGRATION_SVC, "WpMigrationService.rollback", "ROLLBACK"),
    (_VERSION_TRAIL, "VersionTrailService.rollback_to_snapshot", "ROLLBACK"),
)

#: 既不改业务内容、也不再拥有计数器的 writer。
#:
#: `WpStorageService.save_version` 只是把**当前**文件复制进 `.versions/` —— 内容一个
#: 字节没变。它改造前却 `file_version += 1`，于是「版本 7」可能与「版本 6」逐字节相同。
#: 迁移后它不进任何 lane（没有业务内容可提交），只失去自己的计数器。
_NON_MUTATING_WRITERS: tuple[tuple[Path, str, str], ...] = (
    (_STORAGE, "WpStorageService.save_version", ""),
)

#: 两条否定式判据（零私有计数器 / 零裸 commit）的公共分母 —— 三类 writer 全覆盖。
_ALL_MIGRATED_WRITERS: tuple[tuple[Path, str, str], ...] = (
    _MIGRATED_WRITERS + _PROJECTION_WRITERS + _NON_MUTATING_WRITERS
)

#: 私有版本计数器的两个域。出现在**赋值目标**里就是回归（Requirement 2.1）。
_PRIVATE_VERSION_ATTRS = frozenset({"file_version", "content_revision"})


def _ids(rows: tuple[tuple[Path, str, str], ...]) -> list[str]:
    """参数化 id：qualname 唯一时直接用它，重名时才带上模块名。

    🔴 不无条件加模块前缀：`update_custom_cells` / `WOPIHostService.put_file` /
    `WpUploadService.upload_file` 三个 id 已被变异脚本的 `want` 逐字引用，改名会让那
    几条变异静默变成 ANCHOR-MISS（脚本查不到该测试 ⇒ 判据看着还在、实际没人验证它）。
    F2 两条的 qualname 都是 `_save_fields`，只有它们需要区分。
    """
    from collections import Counter

    counts = Counter(qualname for _, qualname, _ in rows)
    return [
        qualname if counts[qualname] == 1 else f"{path.stem}::{qualname}"
        for path, qualname, _ in rows
    ]


# ─── AST 工具（与 task16/task18 守卫同形态，刻意不跨文件 import 私有 helper）───────


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def _iter_functions(tree: ast.AST):
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        prefix, parent = stack.pop()
        for child in ast.iter_child_nodes(parent):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{prefix}{child.name}"
                yield qualname, child
                stack.append((f"{qualname}.", child))
            elif isinstance(child, ast.ClassDef):
                stack.append((f"{prefix}{child.name}.", child))
            else:
                stack.append((prefix, child))


def _find_function(tree: ast.AST, qualname: str) -> ast.AST:
    for name, node in _iter_functions(tree):
        if name == qualname:
            return node
    raise AssertionError(f"AST 里找不到 {qualname}（重命名了？守卫必须跟着改）")


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted(node.value)
    return ""


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)]


def _own_nodes(function: ast.AST):
    """只遍历本函数自己的节点，不含嵌套函数体。

    `put_file` 里有四个嵌套协程（`_auto_parse` / `_auto_fine_extract` / ...），它们是
    **各自独立**的 writer 清册行；把它们的 commit 算到宿主头上会让「宿主没有裸
    commit」这条判据恒红，从而变成一条永远无法通过、也永远无法 falsify 的死判据。
    """
    stack: list[ast.AST] = list(ast.iter_child_nodes(function))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


# ─── authority-model 载体判据（Task 65 之后）────────────────────────────────
#
# 🔴 判据迁移而不是放宽。改造前 `commit_bytes` 收一个**带默认值**的
# `authority_model: AuthorityModel | str = AuthorityModel.custom_authoritative_ooxml`，
# 本文件的判据因此断言「每个调用点都必须显式带上它」——护的是「authority model 不得
# 靠默认值静默漂移」。Task 65 把载体换成必填 `lane_id=` + `opaque_entry_gate` 的 lane
# 登记表（authority model 由登记**单向**决定），那条语义一字未改，只是落点变了：
#
#   ① 签名侧：`lane_id` 必填、无默认值、keyword-only（有默认值就等于可漏传 ⇒ 又能静默漂移）
#   ② 调用点侧：传的必须是**字面量**（运行期变量会让静态判据退化成猜测）
#   ③ 身份侧：该字面量登记的 writer 必须正是**本** writer（不得借用别人的 lane 身份）
#   ④ 否定式：调用点**不得**再长出 `authority_model=`（那是被删掉的可漏可错身份参数）


def _writer_module_dotted(path: Path) -> str:
    """`backend/app/services/x.py` → `app.services.x`（与 lane 登记的 `writer_module` 同形）。"""
    return "app." + path.relative_to(_APP).with_suffix("").as_posix().replace("/", ".")


def _registered_lane_for(path: Path, qualname: str) -> Any:
    """按 `(模块, qualname)` 取本 writer 在 lane 登记表里的**唯一**那一条。

    🔴 不在本文件抄第二份 `{writer: lane_id}` 清单：抄一份的话「调用点写了哪个 lane」
    与「登记表说这个 writer 属于哪个 lane」就都只跟本地常量比，两边一起改错不会有人
    发现。这里反查登记表，于是「把 F2-22 的 `lane_id` 改成 F2-23 的」必红。
    """
    from app.services.workpaper_sync import opaque_entry_gate as OG

    module = _writer_module_dotted(path)
    matches = [
        lane
        for lane in OG.OPAQUE_AUTHORITY_LANES
        if lane.writer_module == module and lane.writer_qualname == qualname
    ]
    assert len(matches) == 1, (
        f"{module}::{qualname} 在 opaque lane 登记表里命中 {len(matches)} 条（应为 1）"
        f" —— 已登记的是 {[(l.lane_id, l.writer_ref) for l in OG.OPAQUE_AUTHORITY_LANES]}"
    )
    return matches[0]


def _lane_id_literal(commit: ast.Call, where: str) -> str:
    """取 `commit_bytes(lane_id=...)` 的字面量实参；非字面量/缺失即打红。"""
    found = [kw for kw in commit.keywords if kw.arg == "lane_id"]
    assert len(found) == 1, f"{where}: `commit_bytes` 应恰有一个 `lane_id=` 实参"
    value = found[0].value
    assert isinstance(value, ast.Constant) and isinstance(value.value, str), (
        f"{where}: `lane_id=` 实参是 {ast.unparse(value)!r} 而不是字符串字面量 —— "
        "运行期变量会让「这条写入路径属于哪条 lane」无法被静态判据锁死，而 authority "
        "model 由它单向决定"
    )
    return value.value


def _assert_lane_carries_the_authority_model(
    commit: ast.Call, *, path: Path, qualname: str, expected: Any
) -> str:
    """四条一起断言：签名必填 / 调用点字面量 / lane 属本 writer / authority model 等值。"""
    from app.services.workpaper_sync import opaque_entry_gate as OG
    from app.services.workpaper_sync.writer_migration import AuthoritativeContentWriter

    where = f"{path.name}::{qualname}"
    parameters = inspect.signature(AuthoritativeContentWriter.commit_bytes).parameters
    assert "authority_model" not in parameters, (
        "`commit_bytes` 又收 `authority_model` 了 —— authority model 必须由 lane 登记"
        "单向决定，调用方不得传一个可漏可错的身份参数"
    )
    lane_param = parameters["lane_id"]
    assert lane_param.default is inspect.Parameter.empty, (
        "`lane_id` 有了默认值 —— 那就等于把 authority model 的载体退回「可漏传即静默"
        "落成默认值」的旧形态（原 `authority_model` 参数正是这么出事的）"
    )
    assert lane_param.kind is inspect.Parameter.KEYWORD_ONLY, lane_param.kind

    keywords = {kw.arg for kw in commit.keywords if kw.arg}
    assert "authority_model" not in keywords, (
        f"{where}: 调用点又传 `authority_model=` —— 身份参数已被 Task 65 删除，"
        "重新出现即意味着同一个 entry 有两个可能不一致的 authority model 来源"
    )

    lane_id = _lane_id_literal(commit, where=where)
    lane = _registered_lane_for(path, qualname)
    assert lane_id == lane.lane_id, (
        f"{where}: 调用点传的 lane_id={lane_id!r}，而登记表把这个 writer 登记成 "
        f"{lane.lane_id!r} —— 借用别条 lane 的身份会让 authority model、entry_id 口径与"
        "evidence 分桶一起失真"
    )
    assert OG.authority_model_for_lane(lane_id) is expected, (
        f"{where}: lane {lane_id!r} 解出的 authority model 是 "
        f"{OG.authority_model_for_lane(lane_id).value}，应为 {expected.value}"
    )
    return lane_id


# ═══════════════════════════════════════════════════════════════════════════
# 一、逐 writer：零私有计数器 + 零裸 commit + 真接线
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "path,qualname",
    [(path, qualname) for path, qualname, _ in _ALL_MIGRATED_WRITERS],
    ids=_ids(_ALL_MIGRATED_WRITERS),
)
def test_migrated_writer_owns_no_private_version_counter(path: Path, qualname: str) -> None:
    """**Validates: Requirements 2.1, 2.2**

    Property 61 原文：「writer inventory 中任一生产内容写路径……仍自行使用
    `_version/file_version`……时守卫打红」。

    判据是**赋值节点**（`wp.file_version += 1` / `wp.file_version = n`），不是
    「文件里出现过 file_version」—— 后者被注释、日志键与 `Version` 响应字段满足，
    等于没测。只**读**存量值（快照命名、`check_file_info` 的 `Version`）不红。
    """
    fn = _find_function(_parse(path), qualname)
    offenders: list[str] = []
    for node in _own_nodes(fn):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr in _PRIVATE_VERSION_ATTRS:
                offenders.append(f"{_dotted(target)}@{target.lineno}")
    assert offenders == [], (
        f"{path.name}::{qualname} 又自己推进版本字段: {offenders} —— business content "
        "revision 只由 ContentMutationService 的 CAS 推进（Property 61）"
    )


@pytest.mark.parametrize(
    "path,qualname",
    [(path, qualname) for path, qualname, _ in _ALL_MIGRATED_WRITERS],
    ids=_ids(_ALL_MIGRATED_WRITERS),
)
def test_migrated_writer_owns_no_direct_commit(path: Path, qualname: str) -> None:
    """**Validates: Requirements 2.2**

    「任何绕过入口的 writer SHALL 被清册与 CI 阻断」的落地形态：writer 自己一个
    `db.commit()` 都没有 —— 那笔事务的唯一提交出口在 `ContentMutationService` 里。
    """
    fn = _find_function(_parse(path), qualname)
    direct = [
        f"{_dotted(call.func)}@{call.lineno}"
        for call in _calls(fn)
        if isinstance(call.func, ast.Attribute)
        and call.func.attr == "commit"
        and _dotted(call.func) in ("db.commit", "session.commit", "self.db.commit")
    ]
    assert direct == [], (
        f"{path.name}::{qualname} 自己提交了事务: {direct} —— 业务内容的唯一提交出口是 "
        "ContentMutationService.commit()（Requirement 2.2 / Property 61）"
    )


@pytest.mark.parametrize(
    "path,qualname,source_const",
    _MIGRATED_WRITERS,
    ids=_ids(_MIGRATED_WRITERS),
)
def test_migrated_writer_routes_through_the_unified_entry(
    path: Path, qualname: str, source_const: str
) -> None:
    """**Validates: Requirements 2.2**

    上两条都是否定式的（「没有计数器」「没有裸 commit」），把整个提交删掉也满足。
    这条钉正面接线：装配器与 `commit_bytes` 各恰一次，且 `source` 传的是该 writer
    自己那个 `ContentSource` 常量（不是随手复用别人的域 —— `source` 是 evidence 与
    timeline 的分桶依据）。
    """
    fn = _find_function(_parse(path), qualname)
    build = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "build_content_mutation_service_writer"
    ]
    commit = [
        call
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
    ]
    assert len(build) == 1, f"装配器应恰一处，实得 {build}"
    assert len(commit) == 1, (
        f"commit_bytes 应恰一处，实得 {[c.lineno for c in commit]} —— 两次就是两个 revision"
    )
    keywords = {kw.arg: kw for kw in commit[0].keywords if kw.arg}
    for required in ("project_id", "wp_id", "entry_id", "source", "payload",
                     "expected_revision", "substrate_path", "lane_id"):
        assert required in keywords, f"commit_bytes 缺 {required}：{sorted(keywords)}"
    passed_source = ast.unparse(keywords["source"].value)
    assert source_const in passed_source, (
        f"{qualname} 的 content source 应是 {source_const}，实得 {passed_source}"
    )
    # authority model 的载体判据（原 `authority_model=` 必填 ⇒ 现 `lane_id=` + 登记表）。
    # 期望值不写死在本行，而是**反查登记表**：这样「登记表与调用点一起被改成另一个
    # authority model」仍会被 §4 的逐 lane 判据接住，而本条锁的是「调用点与登记表一致」。
    lane = _registered_lane_for(path, qualname)
    _assert_lane_carries_the_authority_model(
        commit[0], path=path, qualname=qualname, expected=lane.authority_model
    )


def test_the_custom_writer_submits_the_xlsx_body_not_a_json_projection() -> None:
    """**Validates: Requirements 2.11** / Property 50

    Property 50 原文：「custom adapter 的 HTML/OO 修改都落同一权威 xlsx content
    artifact，标准 projection persist 不被调用」。

    判据落在 `payload=` 实参上：它必须是**从 xlsx 本体读回来的字节**，不能是
    `grid`（投影）、`parsed_data`（投影）或任何 JSON 序列化结果。这是「不得被标准
    结构化 JSON projection writer 改写」这条禁令在调用点的可执行形态。
    """
    fn = _find_function(_parse(_CUSTOM_CELLS), "update_custom_cells")
    commit = next(
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
    )
    keywords = {kw.arg: kw for kw in commit.keywords if kw.arg}
    payload_expr = ast.unparse(keywords["payload"].value)
    assert payload_expr == "authoritative_bytes", payload_expr
    for forbidden in ("grid", "parsed_data", "json.dumps", "html_data"):
        assert forbidden not in payload_expr, (
            f"custom 的权威载荷里出现投影产物 {forbidden!r}：{payload_expr} —— "
            "Requirement 2.11 禁止 JSON projection writer 改写 xlsx 本体"
        )
    # 载荷来源必须是 xlsx 本体的 `read_bytes()`，而不是重新序列化的什么东西。
    reads = [
        call.lineno for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "read_bytes"
    ]
    assert len(reads) == 1, f"应恰有一处从 xlsx 本体读回字节，实得 {reads}"
    # authority model 必须是 custom_authoritative_ooxml（Property 50 指名）。Task 65 之后
    # 它不再是调用点的实参：判据落在「本调用点那条 lane 解出来的 authority model」上，
    # 而不是「源码里有没有出现那个枚举名」—— 后者是 grep 式判据，注释里留个名字就能骗过。
    from app.services.workpaper_sync.models import AuthorityModel

    _assert_lane_carries_the_authority_model(
        commit,
        path=_CUSTOM_CELLS,
        qualname="update_custom_cells",
        expected=AuthorityModel.custom_authoritative_ooxml,
    )


def test_the_custom_writer_translates_the_revision_conflict_narrowly() -> None:
    """**Validates: Requirements 5.12**

    CAS 冲突必须变成 409（用户可行动），而不是被 `except Exception` 吞掉。判据：
    包住 `commit_bytes` 的那个 `try` **只**捕获 `RevisionConflictError`。
    """
    fn = _find_function(_parse(_CUSTOM_CELLS), "update_custom_cells")
    found = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try) or not node.handlers:
            continue
        if not any(
            isinstance(inner, ast.Call)
            and _dotted(inner.func).rsplit(".", 1)[-1] == "commit_bytes"
            for statement in node.body
            for inner in ast.walk(statement)
        ):
            continue
        found = True
        caught = {
            _dotted(handler.type) if handler.type is not None else "<bare>"
            for handler in node.handlers
        }
        assert caught == {"RevisionConflictError"}, (
            f"只许捕获 RevisionConflictError，实得 {sorted(caught)} —— 宽泛 except 会把"
            "「artifact 发布失败」「事务分裂」一起吞成 409，用户看到的原因是错的"
        )
    assert found, "commit_bytes 没有被 RevisionConflictError 的 try 包住"


def test_the_wopi_audit_log_is_written_before_the_only_commit_outlet() -> None:
    """**Validates: Requirements 13.1**

    `commit_bytes` 是这笔事务的**唯一**提交出口。写在它之后的 `db.add(log)` 会落到
    下一个事务，而 WOPI router 不一定再提交一次 ⇒ 审计日志静默丢失。

    判据是行号次序，不是「有没有审计日志」：后者改成 `logger.info` 也满足。
    """
    fn = _find_function(_parse(_WOPI), "WOPIHostService.put_file")
    log_adds = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func) == "db.add"
    ]
    commits = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
    ]
    assert log_adds, "put_file 的审计留痕不见了"
    assert commits, "put_file 没有接统一提交入口"
    assert max(log_adds) < min(commits), (
        f"审计日志(行 {log_adds}) 必须早于唯一提交出口(行 {commits})：写在之后会落到"
        "下一个事务，而 router 不一定再提交 ⇒ 静默丢失（Requirement 13.1）"
    )


def test_the_wopi_snapshot_name_follows_the_counter_that_actually_moves() -> None:
    """**Validates: Requirements 2.1**

    迁移后 `file_version` 在 WOPI 路径上**不再前进**。`.versions` 快照名若继续用它，
    `{stem}_v1.xlsx` 会被每次保存覆盖 —— 备份看着在、实际只剩最后一份。

    判据：快照名的 f-string 里引用的是 `pre_save_revision`（本次保存前的 content
    revision），且**没有** `wp.file_version`。
    """
    fn = _find_function(_parse(_WOPI), "WOPIHostService.put_file")
    snapshot_exprs: list[str] = []
    for node in _own_nodes(fn):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "snapshot_name"
            for target in node.targets
        ):
            continue
        snapshot_exprs.append(ast.unparse(node.value))
    assert snapshot_exprs, "put_file 的 .versions 快照命名不见了"
    for expr in snapshot_exprs:
        assert "pre_save_revision" in expr, (
            f"快照名必须绑在真正在动的计数器上，实得 {expr}"
        )
        assert "file_version" not in expr, (
            f"快照名还在用已冻结的 file_version，会互相覆盖：{expr}"
        )


def test_the_upload_conflict_check_compares_the_business_revision() -> None:
    """**Validates: Requirements 2.1**

    上一批判据都是「不再写」。单有它们不够：把整段乐观锁删掉也满足。这条钉正面形态
    —— 上传的版本冲突早检查必须比 `content_revision`，不是 `file_version`
    （后者同时被 storage 快照与另一条 upload 路径推进，跨域比较必然造假冲突）。
    """
    fn = _find_function(_parse(_UPLOAD), "WpUploadService.upload_file")
    sources: list[str] = []
    for node in _own_nodes(fn):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "server_content_revision"
            for target in targets
        ):
            continue
        assert node.value is not None
        sources.append(ast.unparse(node.value))
    assert len(sources) == 1, (
        f"upload_file 应恰有一处 server_content_revision 赋值，实得 {sources}"
    )
    assert "content_revision" in sources[0], sources[0]
    assert "file_version" not in sources[0], sources[0]


# ═══════════════════════════════════════════════════════════════════════════
# 二、装配层：entry_id 路径安全 + authority model 封闭
# ═══════════════════════════════════════════════════════════════════════════


def test_opaque_entry_id_is_a_safe_single_path_segment() -> None:
    """**Validates: Requirements 9.6**

    `entry_id` 被 `CanonicalArtifactLayout.representation_dir()` 原样当**目录名**用。
    `:` 在 Windows 上不可创建（本任务实测 WinError 267），`/` 与 `..` 是目录穿越。

    🔴 这条是**注入式**判据：拿带 `/`、`..`、`:` 的 wp_code 去构造，输出必须仍是单个
    安全片段。把归一那行删掉即红。
    """
    from app.services.workpaper_sync.writer_migration import (
        OPAQUE_ENTRY_PREFIX,
        opaque_entry_id,
    )

    wp_id = uuid.uuid4()
    assert ":" not in OPAQUE_ENTRY_PREFIX, (
        "前缀不得含 ':' —— 它会成为路径片段，Windows 上不可创建"
    )
    assert opaque_entry_id(wp_code="D2-1", wp_id=wp_id) == f"{OPAQUE_ENTRY_PREFIX}D2-1"
    for hostile in ("../../etc", "a/b", "a\\b", "x:y", "..", "  ", None, ""):
        entry = opaque_entry_id(wp_code=hostile, wp_id=wp_id)
        assert entry.startswith(OPAQUE_ENTRY_PREFIX), entry
        for forbidden in ("/", "\\", ":", ".."):
            assert forbidden not in entry, (
                f"wp_code={hostile!r} 产出了不安全片段 {entry!r}（含 {forbidden!r}）"
            )
        assert Path(entry).name == entry, f"{entry!r} 不是单个路径片段"
    # V151 的列宽是 VARCHAR(200)
    assert len(opaque_entry_id(wp_code="X" * 500, wp_id=wp_id)) <= 200


@pytest.mark.asyncio
async def test_projection_contract_cannot_use_the_opaque_assembly() -> None:
    """**Validates: Requirements 2.3, 3.3**

    opaque 装配跳过了 materialize → roundtrip 等值 → 未管理区域比对三步。让
    `projection_contract` 走它等于让标准结构化底稿绕过 Property 65 的等值判据。

    这是**否定式承诺**，只能靠注入反例证明：拿 `projection_contract` 去 `provision(...)`
    必须抛，且抛的是**它自己**那条码。

    🔴 Task 65 把 `ensure()`（查不到就发布）拆成 `resolve()`（只查，业务写路径用）与
    `provision()`（查+发布，唯一宿主是那个 fix 脚本）。这条判据跟到 `provision()` 上 ——
    它是现在唯一还会接 `authority_model` 参数、因而唯一还能被喂进 `projection_contract`
    的入口。判据形态一字未改：**真调一次**、必抛、异常类型与 `error_code` 都不放宽。
    """
    from app.services.workpaper_sync.models import AuthorityModel
    from app.services.workpaper_sync.writer_migration import (
        OPAQUE_AUTHORITY_MODELS,
        OpaqueAuthorityProvisioner,
        ProjectionAuthorityNotAllowedError,
    )

    assert AuthorityModel.projection_contract not in OPAQUE_AUTHORITY_MODELS
    assert set(OPAQUE_AUTHORITY_MODELS) == {
        AuthorityModel.custom_authoritative_ooxml,
        AuthorityModel.opaque_single_onlyoffice,
    }

    provisioner = OpaqueAuthorityProvisioner(
        session=None, repository=None, artifacts=None, resolution=None
    )
    assert not hasattr(OpaqueAuthorityProvisioner, "ensure"), (
        "`ensure()` 又回来了 —— 它是「写路径查不到就顺手给自己发证」的旧入口，"
        "而本条判据只挂在 `provision()` 上：留着 `ensure()` 就等于留了一条不被本判据"
        "覆盖的旁路"
    )
    with pytest.raises(ProjectionAuthorityNotAllowedError) as exc:
        await provisioner.provision(
            project_id=uuid.uuid4(),
            wp_id=uuid.uuid4(),
            authority_model=AuthorityModel.projection_contract,
        )
    assert exc.value.error_code == "projection_authority_requires_full_protocol"


def test_the_opaque_bundle_uses_registry_markers_and_never_an_empty_hash() -> None:
    """**Validates: Requirements 2.3**

    Requirement 2.3 原文：custom/opaque「必须使用明确 authority model 与适用 child 的
    版本化 typed null marker，不得以 SQL NULL、空串或全零 hash 代替」。

    判据逐 slot 落在 registry marker 的真实 digest 上 —— 不是「非空就行」。
    """
    from app.services.workpaper_sync.definitions import TYPED_NULL_MARKERS
    from app.services.workpaper_sync.models import BundleSlot, is_digest
    from app.services.workpaper_sync.writer_migration import _marker_slots

    slots = _marker_slots()
    assert set(slots) == set(BundleSlot), sorted(s.value for s in slots)
    for slot, spec in slots.items():
        marker = TYPED_NULL_MARKERS[spec.slot_type]
        assert marker.slot is slot, f"{slot.value} 用了 {marker.slot.value} 的 marker"
        assert spec.slot_digest == marker.slot_digest
        assert is_digest(spec.slot_digest), spec.slot_digest
        assert spec.slot_digest != "0" * 64, "全零 hash 是伪身份"
        assert spec.slot_type != "definition", (
            f"{slot.value} 冒充了 approved definition —— opaque authority model 的三个 "
            "child 只能是 registry 版本化 typed null marker"
        )


def test_the_authority_payload_carries_no_self_identity() -> None:
    """**Validates: Requirements 6.1**

    definition semantic payload 禁止内嵌自身 UUID/hash：内嵌了就意味着同一语义在不同
    环境算出不同 digest，bundle 无法跨环境复现（Task 13 的 canonicalizer 承诺）。
    """
    from app.services.workpaper_sync.models import AuthorityModel
    from app.services.workpaper_sync.writer_migration import _authority_payload

    for model in AuthorityModel:
        payload = _authority_payload(model)
        assert payload["authority_model"] == model.value
        assert set(payload) == {"schema_version", "authority_model"}, sorted(payload)
        flat = repr(payload)
        for forbidden in ("sha256", "digest", "uuid", "_id"):
            assert forbidden not in flat, f"{model.value} payload 内嵌了自身身份: {flat}"


def test_the_adapter_build_digest_is_stable_and_never_all_zero() -> None:
    """**Validates: Requirements 2.3**

    `working_paper_content_representation.adapter_build_digest` 是 NOT NULL 且必须是
    合法 digest。opaque 路径没有真 adapter，但**不得**填全零 hash（伪身份）。
    """
    from app.services.workpaper_sync.models import is_digest
    from app.services.workpaper_sync.writer_migration import _adapter_build_digest

    first = _adapter_build_digest("opaque.authoritative.v1")
    assert first == _adapter_build_digest("opaque.authoritative.v1"), "必须稳定可复现"
    assert first != _adapter_build_digest("opaque.authoritative.v2"), "改版本必须换身份"
    assert is_digest(first) and first != "0" * 64


def test_the_assembly_layer_cannot_express_a_per_entry_contract() -> None:
    """**Validates: Requirements 2.11**

    `_assert_authority_shape` 会拒绝「opaque authority model + per-entry contract」。
    但那是**运行时**判据；这条更强：装配层根本没有透传 contract 的入口，于是
    「custom 转 JSON 三方 projection」在**构造上**不可表达。

    判据：`commit_bytes` 里 `contract=` 恒为字面 `None`，且它不是形参。
    """
    fn = _find_function(
        _parse(_WRITER_MIGRATION), "AuthoritativeContentWriter.commit_bytes"
    )
    signature_args = {
        arg.arg for arg in list(fn.args.args) + list(fn.args.kwonlyargs)  # type: ignore[attr-defined]
    }
    assert "contract" not in signature_args, (
        f"commit_bytes 多出了 contract 形参: {sorted(signature_args)} —— "
        "opaque 装配不得能表达 per-entry contract（Requirement 2.11）"
    )
    plans = [
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "ContentCommitPlan"
    ]
    assert len(plans) == 1, f"应恰构造一个 ContentCommitPlan，实得 {len(plans)}"
    contract_kw = {kw.arg: kw for kw in plans[0].keywords if kw.arg}.get("contract")
    assert contract_kw is not None, "ContentCommitPlan 必须显式传 contract=None"
    assert isinstance(contract_kw.value, ast.Constant) and contract_kw.value.value is None, (
        f"contract 必须是字面 None，实得 {ast.unparse(contract_kw.value)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 三、rollback 源定位：六条拒绝各自可 falsify
# ═══════════════════════════════════════════════════════════════════════════


#: 非法 resource key → 期望的拒绝码。numeric revision 是 Requirement 10.6 点名的形态。
_BAD_RESOURCE_KEYS = (
    1,
    0,
    -3,
    True,
    "1",
    "revision-1",
    "",
    "   ",
    "not-a-uuid",
)


@pytest.mark.parametrize("bad_key", _BAD_RESOURCE_KEYS, ids=[repr(k) for k in _BAD_RESOURCE_KEYS])
def test_numeric_revision_is_refused_as_a_rollback_resource_key(bad_key) -> None:
    """**Validates: Requirements 10.6**

    「numeric `revision` 只用于显示与乐观锁，禁止作为全局 scope `resource_id` 或
    rollback route key」。两个 wp 都可以有 revision=1，拿它当 key 会回滚到别人的版本。

    🔴 判据必须在**任何数据库查询之前**成立，所以这里直接测纯函数
    `_coerce_version_id` —— 它不碰 session。把归一那步挪到查库之后，这条仍然过，
    但 `test_the_resource_key_check_runs_before_any_database_read` 会红（两条判据配对）。
    """
    from app.services.workpaper_sync.writer_migration import (
        NumericRevisionIsNotAResourceKeyError,
        RollbackSourceLocator,
    )

    with pytest.raises(NumericRevisionIsNotAResourceKeyError) as exc:
        RollbackSourceLocator._coerce_version_id(bad_key)
    assert exc.value.error_code == "numeric_revision_is_not_a_resource_key"


def test_a_real_uuid_resource_key_is_accepted() -> None:
    """正面锚：上一条只证明「某些 key 被拒」，把归一改成恒抛也满足它。"""
    from app.services.workpaper_sync.writer_migration import RollbackSourceLocator

    version_id = uuid.uuid4()
    assert RollbackSourceLocator._coerce_version_id(version_id) is version_id
    assert RollbackSourceLocator._coerce_version_id(str(version_id)) == version_id
    assert RollbackSourceLocator._coerce_version_id(f"  {version_id}  ") == version_id


def test_the_resource_key_check_runs_before_any_database_read() -> None:
    """**Validates: Requirements 10.6**

    次序即语义：先查库再判 key 形态，等于「已经按 numeric revision 查过一遍」——
    第一个匹配到的行就会被当成源，那是跨 scope 数据泄露，不只是参数校验问题。
    """
    fn = _find_function(_parse(_WRITER_MIGRATION), "RollbackSourceLocator.locate")
    coerce_lines = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "_coerce_version_id"
    ]
    execute_lines = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "execute"
    ]
    assert len(coerce_lines) == 1, f"resource key 归一应恰一处，实得 {coerce_lines}"
    assert execute_lines, "locate 必须真查库（否则它没在定位任何东西）"
    assert coerce_lines[0] < min(execute_lines), (
        f"resource key 判据(行 {coerce_lines[0]}) 必须早于第一次查库(行 {min(execute_lines)})"
    )


def test_every_rollback_refusal_has_its_own_error_code() -> None:
    """**Validates: Requirements 5.12**

    Task 18 实测过一条真实缺陷：两条拒绝共用一个 `error_code` 时，短路掉第一个 `if`
    会被第二个接住并抛出同样的码，于是第一条判据退化成不可达分支、变异判 GREEN。

    这条把「每条拒绝一个码」钉成结构事实，而不是靠人记得。
    """
    from app.services.workpaper_sync import writer_migration as W

    refusals = {
        W.ProjectionAuthorityNotAllowedError: "projection_authority_requires_full_protocol",
        W.NumericRevisionIsNotAResourceKeyError: "numeric_revision_is_not_a_resource_key",
        W.RollbackSourceNotFoundError: "rollback_source_not_found",
        W.RollbackSourceScopeMismatchError: "rollback_source_scope_mismatch",
        W.RollbackSourceIncomingError: "rollback_source_is_incoming",
        W.RollbackSourceCandidateError: "rollback_source_is_candidate",
        W.RollbackSourceNotPublishedError: "rollback_source_not_published",
    }
    for exc_type, expected in refusals.items():
        assert exc_type.error_code == expected, (
            f"{exc_type.__name__} 的 error_code 是 {exc_type.error_code!r}，期望 {expected!r}"
        )
    codes = [exc.error_code for exc in refusals]
    assert len(set(codes)) == len(codes), (
        f"拒绝码有重复: {codes} —— 共用一个码会让其中一条判据变成不可达分支"
    )
    # 每条都必须是 WriterMigrationError 的子类（调用方按域分支处理，不按字符串比对）。
    for exc_type in refusals:
        assert issubclass(exc_type, W.WriterMigrationError), exc_type


def test_the_semantic_refusals_are_checked_before_the_state_refusal() -> None:
    """**Validates: Requirements 5.6, 6.18**

    candidate 与 incoming 是**语义**禁令（这类 artifact 永远不能当源）；
    「不是 published canonical」是**状态**禁令（这一个碰巧还没发布/已 orphan）。

    反过来排会让语义禁令被状态禁令遮蔽成不可达分支：一个 candidate artifact 通常
    state 也不是 published，于是先判状态就永远走不到 candidate 那条。
    """
    fn = _find_function(
        _parse(_WRITER_MIGRATION),
        "RollbackSourceLocator._assert_artifact_publishable",
    )
    order: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Raise) and node.exc is not None:
            name = _dotted(node.exc).rsplit(".", 1)[-1]
            if name.startswith("RollbackSource"):
                order.append(name)
    assert "RollbackSourceCandidateError" in order, order
    assert "RollbackSourceIncomingError" in order, order
    assert "RollbackSourceNotPublishedError" in order, order
    assert order.index("RollbackSourceCandidateError") < order.index(
        "RollbackSourceNotPublishedError"
    ), f"candidate（语义）必须先于 not-published（状态）判定，实得顺序 {order}"
    assert order.index("RollbackSourceIncomingError") < order.index(
        "RollbackSourceNotPublishedError"
    ), f"incoming（语义）必须先于 not-published（状态）判定，实得顺序 {order}"


def test_the_rollback_source_digest_is_verified_against_the_disk() -> None:
    """**Validates: Requirements 2.4, 9.7**

    DB 说的 sha256 与磁盘实际内容不符 ⇒ 内容寻址的不可变承诺已破。把它当回滚源等于
    把损坏内容发布成新版本。

    判据落在**真实执行**上：造一个 digest 不符的 artifact，必须抛。
    """
    import hashlib
    import tempfile

    from app.services.workpaper_sync.artifacts import CanonicalArtifactRepository
    from app.services.workpaper_sync.writer_migration import (
        RollbackSourceLocator,
        RollbackSourceNotPublishedError,
    )

    class _Artifact:
        def __init__(self, relative_path: str, sha256: str) -> None:
            self.id = uuid.uuid4()
            self.relative_path = relative_path
            self.sha256 = sha256

    with tempfile.TemporaryDirectory() as root:
        base = Path(root)
        # `resolve_relative_path` 以 `base_root` 为基准（不是 `base_root/storage`）。
        target = base / "payload.bin"
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = b"real-bytes"
        target.write_bytes(payload)
        artifacts = CanonicalArtifactRepository(base)
        locator = RollbackSourceLocator(session=None, artifacts=artifacts)

        good = _Artifact("payload.bin", hashlib.sha256(payload).hexdigest())
        assert locator._read_verified_bytes(good) == payload

        bad = _Artifact("payload.bin", hashlib.sha256(b"other").hexdigest())
        with pytest.raises(RollbackSourceNotPublishedError) as exc:
            locator._read_verified_bytes(bad)
        assert exc.value.error_code == "rollback_source_not_published"

        zeroed = _Artifact("payload.bin", "0" * 64)
        with pytest.raises(RollbackSourceNotPublishedError):
            locator._read_verified_bytes(zeroed)


def test_the_restore_lane_produces_a_new_version_from_the_located_source() -> None:
    """**Validates: Requirements 8.9, 9.11**

    rollback 是 forward-only 的：它把旧内容作为**新** content version + **新**
    published representation 发布出来，旧行一个字节都不动。

    判据落在接线形态上：`commit_restore` 必须先 `locate(...)`、再用
    `located.payload` 与 `parent_version_id=located.version_id` 调 `commit_bytes`，
    且 `source` 是 `rollback`、`reason` 是 `rollback`。任一项被改都红。
    """
    fn = _find_function(
        _parse(_WRITER_MIGRATION), "AuthoritativeContentWriter.commit_restore"
    )
    locates = [
        call.lineno for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "locate"
    ]
    commits = [
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
    ]
    assert len(locates) == 1, f"应恰定位一次，实得 {locates}"
    assert len(commits) == 1, f"应恰提交一次，实得 {[c.lineno for c in commits]}"
    assert locates[0] < commits[0].lineno, "必须先定位合法源，再提交"
    keywords = {kw.arg: ast.unparse(kw.value) for kw in commits[0].keywords if kw.arg}
    assert keywords["payload"] == "located.payload", keywords["payload"]
    assert keywords["parent_version_id"] == "located.version_id", (
        f"新版本必须挂在被回滚到的那个版本下（可审计的 forward-only 链），"
        f"实得 {keywords['parent_version_id']}"
    )
    assert "rollback" in keywords["source"], keywords["source"]
    assert keywords["reason"] == "'rollback'", keywords["reason"]
    # 反向锚：restore 不得自己动 pointer / revision。
    for forbidden in (
        "set_current_content_version",
        "set_entry_pointer",
        "bump_content_revision",
    ):
        assert not [
            call for call in _calls(fn)
            if _dotted(call.func).rsplit(".", 1)[-1] == forbidden
        ], f"commit_restore 不得直接调 {forbidden}（那是统一入口的活）"


def test_the_assembly_layer_owns_no_commit_and_no_revision_write() -> None:
    """**Validates: Requirements 2.2** / Property 61

    `AuthoritativeContentWriter` 是装配层：它不写行、不 commit、不递增计数器。
    否则「writer 只有一次 await」这条承诺就被搬到了装配层里，等于换了个地方违规。
    """
    tree = _parse(_WRITER_MIGRATION)
    offenders: list[str] = []
    for qualname, fn in _iter_functions(tree):
        if not qualname.startswith("AuthoritativeContentWriter."):
            continue
        for call in _calls(fn):
            leaf = _dotted(call.func).rsplit(".", 1)[-1]
            if leaf in ("commit", "bump_content_revision", "set_current_content_version"):
                # `self._mutation.commit(...)` 是统一入口本身，不算 writer 自己提交。
                if _dotted(call.func) == "self._mutation.commit":
                    continue
                offenders.append(f"{qualname}:{_dotted(call.func)}@{call.lineno}")
        for node in ast.walk(fn):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and target.attr in _PRIVATE_VERSION_ATTRS
                ):
                    offenders.append(f"{qualname}:{_dotted(target)}@{target.lineno}")
    assert offenders == [], f"装配层自己提交/递增了: {offenders}"


def test_the_orm_declares_the_v151_content_revision_columns() -> None:
    """**Validates: Requirements 2.1**

    V151 用 `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` 加了 `content_revision` 与
    `current_content_version_id`，但 ORM 侧一直没声明 —— 于是任何用
    `Base.metadata.create_all` 建库的环境里这两列**根本不存在**，读它的代码报
    `no such column: content_revision`（本任务实测）。

    🔴 `current_content_version_id` 刻意不声明 ForeignKey：目标表定义在
    `workpaper_sync_models`，并非所有 `create_all` 场景都会 import 它，声明 FK 会让
    那些场景在建表阶段 `NoReferencedTableError`。真正的 FK 约束由 V151 在数据库侧持有。
    """
    from app.models.workpaper_models import WorkingPaper

    columns = WorkingPaper.__table__.c
    assert "content_revision" in columns, sorted(columns.keys())
    assert "current_content_version_id" in columns, sorted(columns.keys())
    assert columns["content_revision"].nullable is False
    assert columns["current_content_version_id"].foreign_keys == set(), (
        "current_content_version_id 不得声明 ORM 级 ForeignKey"
    )


def test_the_content_source_vocabulary_matches_the_migration() -> None:
    """**Validates: Requirements 2.3**

    `ContentSource` 是 `ck_wpcv_source` 的 Python 侧镜像。两边一漂移，构造点放行的值
    会在 DB CHECK 上炸成一个看不出来源的 `IntegrityError`。

    判据从 **V152 迁移文件本身**解析出词表，不是抄一份常量 —— 抄的那份改不动 DB。
    """
    import re

    from app.services.workpaper_sync.content_mutation import (
        ContentMutationError,
        ContentSource,
        _ALLOWED_SOURCES,
    )

    migration = (
        _BACKEND / "migrations" / "V152__workpaper_content_version_upload_wopi_source.sql"
    ).read_text(encoding="utf-8")
    body = migration.split("ADD CONSTRAINT ck_wpcv_source", 1)[1]
    body = body.split(")", 1)[0] if ")" in body else body
    from_sql = set(re.findall(r"'([a-z_]+)'", body))
    assert from_sql == set(_ALLOWED_SOURCES), (
        f"Python 词表 {sorted(_ALLOWED_SOURCES)} 与 V152 的 {sorted(from_sql)} 不一致"
    )
    for value in ("upload", "wopi"):
        assert ContentSource(value) == value
    with pytest.raises(ContentMutationError):
        ContentSource("offline_upload")


# ═══════════════════════════════════════════════════════════════════════════
# 五、projection lane：模板迁移回滚 + 历史快照回滚
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "path,qualname,source_const",
    _PROJECTION_WRITERS,
    ids=_ids(_PROJECTION_WRITERS),
)
def test_projection_writer_routes_through_the_unified_entry(
    path: Path, qualname: str, source_const: str
) -> None:
    """**Validates: Requirements 2.2, 9.11** / Property 61

    与 `test_migrated_writer_routes_through_the_unified_entry` 同形，但钉的是**另一条
    lane** 的入口 `commit_projection`：装配器与提交各恰一次。

    「恰一次」不是洁癖：两次 `commit_projection` 就是两次 CAS、两个 content version，
    一次回滚在 timeline 上变成两次内容变更，且第二次的 `expected_revision` 必然过期。

    `source` 必须是 `ROLLBACK` —— 这条 lane 改造前把 `source` 写死成 `html`
    （见 `test_the_projection_lane_records_the_real_source`），于是一次回滚在 evidence
    与 timeline 里长得和一次用户编辑一模一样（Requirement 2.3 点名 `source` 必须落库）。
    """
    fn = _find_function(_parse(path), qualname)
    build = [
        call.lineno
        for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "build_content_mutation_service_writer"
    ]
    commit = [
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_projection"
    ]
    assert len(build) == 1, f"{qualname} 的装配器应恰一处，实得 {build}"
    assert len(commit) == 1, (
        f"{qualname} 的 commit_projection 应恰一处，实得 {[c.lineno for c in commit]}"
        " —— 两次就是两个 revision"
    )
    keywords = {kw.arg: kw for kw in commit[0].keywords if kw.arg}
    for required in (
        "project_id", "wp_id", "entry_id", "capability", "html_data",
        "expected_revision", "source",
    ):
        assert required in keywords, f"{qualname} 的 commit_projection 缺 {required}：{sorted(keywords)}"
    assert source_const in ast.unparse(keywords["source"].value), (
        f"{qualname} 的 content source 应是 {source_const}，"
        f"实得 {ast.unparse(keywords['source'].value)}"
    )
    # entry_id 必须由 html-only lane 的**同一个**构造器产出：换一个（或自己拼字符串）
    # 会让同一底稿的 HTML save 与恢复落到两个 scope 下，content version 链就断成两条。
    assert "html_only_entry_id" in ast.unparse(keywords["entry_id"].value), (
        f"{qualname} 的 entry_id 必须走 html_only_entry_id：{ast.unparse(keywords['entry_id'].value)}"
    )


#: 每条 projection writer 的 `html_data=` 实参里**必须**出现的那个来源变量。
#:
#: 🔴 这张表存在的原因是一次实测到的守卫缺陷（本任务变异 M33）：把
#: `html_data={"checklist_responses": data_json or []}` 换成 `html_data={}` 时，
#: 「接线判据」照样绿 —— 它只断言 `html_data` 这个**关键字在不在**，从不看里面是什么。
#: 后果是恢复动作提交一个空载荷：content version 的 projection digest 与实际落库的内容
#: 无关，任何两次回滚算出同一个 hash，历史读取再也分不出版本。
_PROJECTION_PAYLOAD_SOURCES: dict[str, str] = {
    "WpMigrationService.rollback": "snapshot_data",
    "VersionTrailService.rollback_to_snapshot": "data_json",
}


@pytest.mark.parametrize(
    "path,qualname",
    [(path, qualname) for path, qualname, _ in _PROJECTION_WRITERS],
    ids=_ids(_PROJECTION_WRITERS),
)
def test_the_projection_payload_comes_from_the_restored_snapshot(
    path: Path, qualname: str
) -> None:
    """**Validates: Requirements 2.3, 9.11**

    提交给统一入口的载荷必须**是从快照读出来的那份内容**，不是空字典、不是别的变量。
    这条与「接线判据」成对：接线判据钉「有没有交出去」，这条钉「交出去的是什么」。
    """
    fn = _find_function(_parse(path), qualname)
    commit = next(
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_projection"
    )
    payload_expr = next(
        ast.unparse(kw.value) for kw in commit.keywords if kw.arg == "html_data"
    )
    expected = _PROJECTION_PAYLOAD_SOURCES[qualname]
    assert expected in payload_expr, (
        f"{qualname} 提交的载荷里没有恢复来源 {expected!r}：{payload_expr} —— 空载荷或错"
        "变量会让 content version 的 projection digest 与实际落库内容无关"
    )
    assert payload_expr not in ("{}", "None"), payload_expr


@pytest.mark.parametrize(
    "path,qualname",
    [(path, qualname) for path, qualname, _ in _PROJECTION_WRITERS],
    ids=_ids(_PROJECTION_WRITERS),
)
def test_the_projection_lane_capability_is_declared_at_the_call_site(
    path: Path, qualname: str
) -> None:
    """**Validates: Requirements 2.11, 3.1**

    走错 lane 被拒两次，两次来源互相独立：声明侧（`HtmlOnlyCommitPlan.__post_init__`
    看 `capability`）与数据库事实侧（`commit_html_projection` 查该 entry 是否已有
    representation pointer）。

    🔴 这条守的是**声明侧那道拒绝仍然可达**。把 `capability` 写死在装配层
    （`commit_projection` 内部）会让它对所有调用方恒为 `single_html` —— 判据还在，
    但永远走不到，正是 Task 18 实测到的「不可达分支」缺陷形态。

    所以：每个 writer 在**自己的调用点**声明 capability，而装配层里不得出现任何
    `Capability.*` 字面量。
    """
    fn = _find_function(_parse(path), qualname)
    commit = next(
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_projection"
    )
    declared = {
        ast.unparse(kw.value) for kw in commit.keywords if kw.arg == "capability"
    }
    assert declared == {"Capability.single_html"}, (
        f"{qualname} 必须在调用点显式声明 capability，实得 {declared}"
    )

    facade = _find_function(
        _parse(_WRITER_MIGRATION), "AuthoritativeContentWriter.commit_projection"
    )
    hardcoded = [
        f"{_dotted(node)}@{node.lineno}"
        for node in ast.walk(facade)
        if isinstance(node, ast.Attribute) and _dotted(node).startswith("Capability.")
    ]
    assert hardcoded == [], (
        f"装配层写死了 capability: {hardcoded} —— 声明侧那道拒绝会对所有调用方变成"
        "不可达分支"
    )


def test_the_projection_lane_records_the_real_source() -> None:
    """**Validates: Requirements 2.3**

    改造前 `commit_html_projection` 把 `source` 写死成 `html`：对 `wp_html_save` 是对
    的，对两条恢复 writer 是错的 —— 它们写的是同一种载荷、来源却是 `rollback`。
    `source` 是 evidence 与 timeline 的分桶依据。

    三条判据成组，缺一即可假绿：

    1. **默认值仍是 `html`** —— 否则 `wp_html_save` 的行为被这次改动悄悄改掉；
    2. **plan 真能携带 `rollback`** 且构造点校验封闭词表；
    3. **content version 与 outbox payload 都读 `plan.source`**（不是各读一处 ——
       两处不同源就会出现「版本行说 rollback、事件说 html」）。
    """
    from app.services.workpaper_sync.content_mutation import (
        HTML,
        ROLLBACK,
        ContentMutationError,
        HtmlOnlyCommitPlan,
    )
    from app.services.workpaper_sync.entry_profile import Capability

    common = dict(
        project_id=uuid.uuid4(),
        wp_id=uuid.uuid4(),
        entry_id="html-only:D2-1",
        expected_revision=3,
        capability=Capability.single_html,
        sheet_name="审定表D2-1",
        schema_version="v2025-R5",
    )
    assert HtmlOnlyCommitPlan(**common).source == HTML, "默认来源必须仍是 html"
    assert HtmlOnlyCommitPlan(**common, source=ROLLBACK).source == ROLLBACK
    # 字符串也要被归一并校验（迁移期调用方会传字符串过来）
    assert HtmlOnlyCommitPlan(**common, source="rollback").source == ROLLBACK
    with pytest.raises(ContentMutationError):
        HtmlOnlyCommitPlan(**common, source="restore")

    tree = _parse(_CONTENT_MUTATION)
    lane = _find_function(tree, "ContentMutationService.commit_html_projection")
    version_calls = [
        call for call in _calls(lane)
        if _dotted(call.func).rsplit(".", 1)[-1] == "create_content_version"
    ]
    assert len(version_calls) == 1, f"应恰一处 create_content_version，实得 {version_calls}"
    source_expr = {
        ast.unparse(kw.value) for kw in version_calls[0].keywords if kw.arg == "source"
    }
    assert source_expr == {"str(plan.source)"}, (
        f"content version 的 source 必须来自 plan，实得 {source_expr}"
    )

    payload_fn = _find_function(tree, "ContentMutationService._html_only_event_payload")
    payload_sources = [
        ast.unparse(node.values[list(node.keys).index(key)])
        for node in ast.walk(payload_fn)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and key.value == "source"
    ]
    assert payload_sources == ["str(plan.source)"], (
        f"outbox payload 的 source 必须与 content version 同源，实得 {payload_sources}"
    )


def test_the_restore_writers_share_one_sheet_scope_marker() -> None:
    """**Validates: Requirements 2.3**

    `sheet_name` 进 canonical 载荷、进内容寻址 digest。一次「整份恢复」不针对某个
    sheet，随手填第一个 sheet 名会让 digest 谎报作用域；两条 writer 各填一个不同的
    记号则会让同一份内容在两条路径下算出两个 digest。

    因此：唯一声明处 + 一个显式 scope 记号，且它**不是**某个真实 sheet 名。
    """
    from app.services.workpaper_sync.writer_migration import (
        RESTORE_SCHEMA_VERSION_FALLBACK,
        RESTORE_SHEET_SCOPE,
    )

    assert RESTORE_SHEET_SCOPE.startswith("<") and RESTORE_SHEET_SCOPE.endswith(">"), (
        f"{RESTORE_SHEET_SCOPE!r} 看起来像一个真实 sheet 名 —— scope 记号必须一眼可辨"
    )
    assert RESTORE_SHEET_SCOPE.strip(), "V151 的 ck_* 约束不接受空串"
    assert "legacy" in RESTORE_SCHEMA_VERSION_FALLBACK, (
        "历史快照没有 schema 版本列，兜底值必须自陈其来源，不能冒充当前 schema"
    )
    facade = _find_function(
        _parse(_WRITER_MIGRATION), "AuthoritativeContentWriter.commit_projection"
    )
    defaults = {
        ast.unparse(node)
        for node in (facade.args.kw_defaults or [])
        if node is not None
    }
    assert "RESTORE_SHEET_SCOPE" in defaults, (
        f"commit_projection 的 sheet_name 默认值必须引用唯一声明，实得 {sorted(defaults)}"
    )


# ─── 真实执行：模板迁移回滚（characterization + migrated behaviour）──────────


class _StubRow:
    def __init__(self, **fields: Any) -> None:
        self.__dict__.update(fields)


class _StubResult:
    """`execute()` 的返回值替身：只实现被生产代码真正调用的三个方法。"""

    def __init__(self, row: Any = None, scalar: Any = None) -> None:
        self._row = row
        self._scalar = scalar

    def first(self) -> Any:
        return self._row

    def scalar_one_or_none(self) -> Any:
        return self._scalar

    def mappings(self) -> "_StubResult":
        return self


class _RecordingSession:
    """按调用顺序回放结果、并记录每条 SQL 与每次事务动作的 session 替身。

    🔴 它**不模拟事务**。用它做的判据只有两类：「执行了哪些语句、按什么顺序」与
    「有没有自己 commit」。「恰一次 revision」「同事务」这类判据必须在真库上验
    （`_TransactionWitness` 的 `pg_current_xact_id()` 在替身上不可判定），本文件不假装
    验证它们。
    """

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)
        self.statements: list[str] = []
        self.actions: list[str] = []
        self.added: list[Any] = []

    async def execute(self, statement: Any, params: Any = None) -> Any:
        self.statements.append(" ".join(str(getattr(statement, "text", statement)).split()))
        return self._results.pop(0) if self._results else _StubResult()

    async def flush(self) -> None:
        self.actions.append("flush")

    async def commit(self) -> None:  # pragma: no cover - 断言它从不被调用
        self.actions.append("commit")

    def add(self, obj: Any) -> None:
        self.added.append(obj)


@pytest.fixture()
def _captured_projection_commits(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """拦下 `commit_projection`，只记参数不真发布 artifact。

    真发布会往 canonical artifact 库写文件（`BACKEND_ROOT/storage/...`）。本文件的判据
    是「writer 交给统一入口的是什么」，不需要也不应该动真实存储目录。
    """
    from app.services.workpaper_sync.writer_migration import AuthoritativeContentWriter

    captured: list[dict[str, Any]] = []

    async def _capture(self: Any, **kwargs: Any) -> Any:
        captured.append(kwargs)
        return _StubRow(
            revision=int(kwargs["expected_revision"]) + 1,
            content_version_id=uuid.uuid4(),
        )

    async def _no_publish(self: Any, receipt: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr(AuthoritativeContentWriter, "commit_projection", _capture)
    monkeypatch.setattr(AuthoritativeContentWriter, "publish_committed_events", _no_publish)
    return captured


@pytest.mark.asyncio
async def test_the_template_rollback_still_restores_the_snapshot_payload(
    _captured_projection_commits: list[dict[str, Any]],
) -> None:
    """**Validates: Requirements 2.2, 9.11**

    **characterization**：迁移后这条路径仍然做原来那件事 —— 读快照、把
    `working_paper.parsed_data` 整份写回、返回 True。判据落在实际执行的 SQL 上（顺序
    与语句形态），不是「函数还在」。

    **migrated behaviour**：它自己不再 commit，并且把恢复内容交给统一入口，
    `source=rollback`、`capability=single_html`、`expected_revision` 取的是**本次回滚前**
    的 business revision。
    """
    from app.services.workpaper_sync.content_mutation import ROLLBACK
    from app.services.workpaper_sync.entry_profile import Capability
    from app.services.wp_migration_service import WpMigrationService

    wp_id, snapshot_id, project_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    snapshot = {"html_data": {"S1": {"cells": {"A1": "1"}}}, "schema_version": "v2025-R5"}
    session = _RecordingSession([
        _StubResult(row=_StubRow(parsed_data_snapshot=snapshot)),   # 快照
        _StubResult(row=_StubRow(project_id=project_id, wp_code="D2-1")),  # scope
        _StubResult(scalar=7),                                      # 当前 revision
        _StubResult(),                                              # UPDATE parsed_data
    ])

    assert await WpMigrationService(session).rollback(wp_id, snapshot_id) is True

    joined = " || ".join(session.statements)
    assert "FROM wp_migration_snapshots" in joined, joined
    assert "UPDATE working_paper SET parsed_data" in joined, joined
    update_at = next(
        i for i, sql in enumerate(session.statements)
        if sql.startswith("UPDATE working_paper SET parsed_data")
    )
    revision_reads = [
        i for i, sql in enumerate(session.statements) if "content_revision" in sql
    ]
    assert revision_reads, session.statements
    # 🔴 断言 **max**，不是第一次：只看第一次读取的话，「写完之后再读一次覆盖掉」这种
    #    注入会通过 —— 而那正是「读自己刚写的那一版当期望值、乐观锁恒真」的形态。
    assert max(revision_reads) < update_at, (
        "expected_revision 必须在写内容**之前**读取，且之后不得再读一次覆盖：写完再读会把"
        f"自己刚写的那一版当成期望值，乐观锁恒真（实得 revision@{revision_reads} "
        f"update@{update_at}）"
    )
    assert "commit" not in session.actions, (
        f"回滚不得自己提交事务，实得 {session.actions}"
    )

    assert len(_captured_projection_commits) == 1, _captured_projection_commits
    call = _captured_projection_commits[0]
    assert call["source"] is ROLLBACK
    assert call["capability"] is Capability.single_html
    assert call["expected_revision"] == 7, "必须是回滚前的 revision"
    assert call["html_data"] == snapshot["html_data"]
    assert call["entry_id"] == "html-only:D2-1", call["entry_id"]
    assert call["schema_version"] == "v2025-R5"


@pytest.mark.asyncio
async def test_the_template_rollback_refuses_a_workpaper_that_no_longer_exists(
    _captured_projection_commits: list[dict[str, Any]],
) -> None:
    """**Validates: Requirements 2.2**

    快照存在但底稿已删除时，`project_id` 无从取得。此时必须**什么都不提交**并返回
    False，而不是拿一个凑出来的 scope 去建 content version —— scope 一错，这份内容就
    落到别的项目底下（V151 的 scope index 按 project 分区）。

    这条与上一条成对：上一条证明成功路径真的提交，这条证明失败路径**零提交**。
    没有它，「返回 False」可以由一个提交完再返回 False 的实现满足。
    """
    from app.services.wp_migration_service import WpMigrationService

    session = _RecordingSession([
        _StubResult(row=_StubRow(parsed_data_snapshot={"html_data": {}})),
        _StubResult(row=None),  # 底稿不存在
    ])
    assert await WpMigrationService(session).rollback(uuid.uuid4(), uuid.uuid4()) is False
    assert _captured_projection_commits == []
    assert session.actions == [], f"失败路径不该动事务，实得 {session.actions}"
    assert not any(
        sql.startswith("UPDATE working_paper") for sql in session.statements
    ), session.statements


def test_the_version_trail_rollback_commits_after_its_snapshot_row() -> None:
    """**Validates: Requirements 13.1**

    `commit_projection` 是这笔事务的**唯一**提交出口。`rollback` 快照行
    （`db.add(rollback_snapshot)`）写在它之后就会落到下一个事务，而 router 不一定再提交
    一次 ⇒ 「回滚到哪个版本」的审计记录静默丢失。

    判据是行号次序 + 正面锚点（快照行必须存在）：只断言次序时，把 `db.add` 整段删掉也
    满足（Task 19 的 WOPI 审计日志判据同理由）。
    """
    fn = _find_function(_parse(_VERSION_TRAIL), "VersionTrailService.rollback_to_snapshot")
    adds = [call.lineno for call in _calls(fn) if _dotted(call.func) == "db.add"]
    commits = [
        call.lineno for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_projection"
    ]
    assert adds, "rollback 快照行不见了"
    assert commits, "没有接统一提交入口"
    assert max(adds) < min(commits), (
        f"rollback 快照行(行 {adds}) 必须早于唯一提交出口(行 {commits})"
    )


def test_the_version_trail_rollback_keeps_delete_before_insert() -> None:
    """**Validates: Requirements 2.2**

    **characterization**：整份 `checklist_responses` 的「先删后插」次序是这条路径的原有
    语义（快照即全量）。次序反了就是「插入撞主键 / 插完又被删空」，而这两种都不会被
    「有没有接统一入口」那类判据发现。

    同时钉住：删除与插入都在唯一提交出口**之前** —— 之后就落到另一笔事务，回滚会变成
    「内容已删、新内容未写」的半成品。
    """
    fn = _find_function(_parse(_VERSION_TRAIL), "VersionTrailService.rollback_to_snapshot")
    deletes: list[int] = []
    inserts: list[int] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        text = ast.unparse(node)
        if "DELETE FROM checklist_responses" in text:
            deletes.append(node.lineno)
        if "INSERT INTO checklist_responses" in text:
            inserts.append(node.lineno)
    commits = [
        call.lineno for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_projection"
    ]
    assert deletes and inserts, f"删/插语句不见了: delete={deletes} insert={inserts}"
    assert min(deletes) < min(inserts), (
        f"必须先删后插，实得 delete@{deletes} insert@{inserts}"
    )
    assert max(inserts) < min(commits), (
        f"内容写入必须早于唯一提交出口，实得 insert@{inserts} commit@{commits}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 六、F2 半闭环：版本域统一，能力与第二套流程都保留
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("path", [_F2_PLAN, _F2_SUMMARY], ids=["F2-22", "F2-23"])
def test_the_f2_writer_submits_the_docx_body_not_the_fields_json(path: Path) -> None:
    """**Validates: Requirements 2.11, 12.7** / Property 50

    F2 entry 的 `capability=single_onlyoffice`（manifest 事实）⇒ 权威内容是 **docx 本体**，
    `checklist_responses` 里那份 fields JSON 是派生视图。

    判据落在 `payload=` 实参：必须是从 docx 读回来的字节，绝不能是 `json.dumps(fields)`
    或 `payload`（本函数里那个变量名正好是 fields 的 JSON 串 —— 混用它就是把派生视图
    当权威内容提交，正是 Requirement 2.11 禁止的形态）。
    """
    fn = _find_function(_parse(path), "_save_fields")
    commit = next(
        call for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
    )
    keywords = {kw.arg: kw for kw in commit.keywords if kw.arg}
    payload_expr = ast.unparse(keywords["payload"].value)
    assert payload_expr == "docx_path.read_bytes()", payload_expr
    for forbidden in ("json.dumps", "fields", "remark"):
        assert forbidden not in payload_expr, (
            f"F2 的权威载荷里出现派生视图 {forbidden!r}：{payload_expr}"
        )
    assert ast.unparse(keywords["document_type"].value) == "'docx'"
    # F2 两条 lane 的 authority model 仍是 `opaque_single_onlyoffice`（纯 OO 入口、无 HTML
    # 对端）。Task 65 之后它由 `lane_id=` 经登记表单向决定 ⇒ 判据迁到那条载体上，并额外
    # 要求「这条 lane 登记的 writer 正是本模块」：F2-22 借用 F2-23 的 lane 会被打红。
    from app.services.workpaper_sync.models import AuthorityModel

    _assert_lane_carries_the_authority_model(
        commit,
        path=path,
        qualname="_save_fields",
        expected=AuthorityModel.opaque_single_onlyoffice,
    )


@pytest.mark.parametrize("path", [_F2_PLAN, _F2_SUMMARY], ids=["F2-22", "F2-23"])
def test_the_f2_fields_row_is_written_before_the_only_commit_outlet(path: Path) -> None:
    """**Validates: Requirements 12.7, 13.1**

    **characterization**：fields 的 `INSERT ... ON CONFLICT` upsert 仍在（这是 F2 结构化
    视图的唯一写入点，删了 UI 就读不到用户在 Word 里改的内容）。

    **migrated behaviour**：它排在唯一提交出口之前 —— 写在之后就落到下一笔事务，
    「docx 已发布成新版本、结构化视图还是旧的」这种分叉正是本 spec 要消灭的形态。
    """
    fn = _find_function(_parse(path), "_save_fields")
    upserts = [
        node.lineno for node in ast.walk(fn)
        if isinstance(node, ast.Call) and "INSERT INTO checklist_responses" in ast.unparse(node)
    ]
    commits = [
        call.lineno for call in _calls(fn)
        if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
    ]
    assert upserts, "F2 的 fields upsert 不见了"
    assert commits, "F2 没有接统一提交入口"
    assert max(upserts) < min(commits), (
        f"fields upsert(行 {upserts}) 必须早于唯一提交出口(行 {commits})"
    )


def test_the_two_f2_sheets_do_not_share_one_entry_scope() -> None:
    """**Validates: Requirements 2.3, 9.11**

    F2-22（监盘计划）与 F2-23（监盘小结）是同一个底稿的**两份不同 docx**。共用一个
    `entry_id` 会让两者互相顶掉对方的 entry pointer 与 representation generation ——
    从此按 F2-22 的历史版本下载，拿到的是 F2-23 的文件。

    这是**真实执行**判据：两个模块的 `_SHEET_CODE` 不同，且把它们喂给同一个
    `opaque_entry_id` 后产出两个不同、仍然路径安全的片段。
    """
    from app.routers.wp_render_strategies import (
        _f2_stocktake_plan_sync as plan_mod,
        _f2_stocktake_summary_sync as summary_mod,
    )
    from app.services.workpaper_sync.writer_migration import opaque_entry_id

    assert plan_mod._SHEET_CODE != summary_mod._SHEET_CODE
    wp_id, wp_code = uuid.uuid4(), "F2-2"
    entries = {
        opaque_entry_id(wp_code=f"{wp_code}#{mod._SHEET_CODE}", wp_id=wp_id)
        for mod in (plan_mod, summary_mod)
    }
    assert len(entries) == 2, f"两张表落到了同一个 entry scope: {entries}"
    for entry in entries:
        assert Path(entry).name == entry, f"{entry!r} 不是单个路径片段"
        for forbidden in ("/", "\\", ":", ".."):
            assert forbidden not in entry, entry
    # sheet code 必须真的出现在 entry 里 —— 否则「带上 sheet code」这句话没有落点
    assert any(plan_mod._SHEET_CODE in entry for entry in entries), entries

    # docx 缓存文件名与 entry_id 取自**同一个**常量：两处各写一遍字面量时，改了一处
    # 就会「发布的是 F2-22 的字节、entry 记成 F2-23」。
    for module_path, mod in ((_F2_PLAN, plan_mod), (_F2_SUMMARY, summary_mod)):
        source = module_path.read_text(encoding="utf-8")
        assert f'"{mod._SHEET_CODE}.docx"' not in source, (
            f"{module_path.name} 里还有硬编码的 docx 文件名字面量"
        )

    # 🔴 以上都只证明「构造器**能**产出两个不同 entry」。writer 有没有真的把 sheet code
    #    带进去，是另一件事 —— 本任务变异 M36 实测到：把 `_save_fields` 里的
    #    `entry_id=opaque_entry_id(wp_code=f"{wp_code}#{_SHEET_CODE}", ...)` 换成
    #    `wp_code=wp_code`（丢掉 sheet code）时，上面那些断言全绿。所以必须落到**调用点**。
    for module_path in (_F2_PLAN, _F2_SUMMARY):
        fn = _find_function(_parse(module_path), "_save_fields")
        commit = next(
            call for call in _calls(fn)
            if _dotted(call.func).rsplit(".", 1)[-1] == "commit_bytes"
        )
        entry_expr = next(
            ast.unparse(kw.value) for kw in commit.keywords if kw.arg == "entry_id"
        )
        assert "_SHEET_CODE" in entry_expr, (
            f"{module_path.name}::_save_fields 的 entry_id 没带 sheet code：{entry_expr}"
            " —— 两张表会落到同一个 entry scope 并互相顶掉对方的 representation"
        )
        assert "opaque_entry_id" in entry_expr, entry_expr


@pytest.mark.parametrize(
    "path,qualname",
    [
        (_F2_PLAN, "f2_st_plan_sync_from_oo"),
        (_F2_SUMMARY, "f2_st_summary_sync_from_oo"),
    ],
    ids=["F2-22", "F2-23"],
)
def test_the_f2_conflict_is_translated_before_the_broad_catch(
    path: Path, qualname: str
) -> None:
    """**Validates: Requirements 5.12**

    F2 端点原本用一条 `except Exception` 把落库失败一律报成 500。迁移后
    `RevisionConflictError`（并发保存）成了可能路径，被那条宽捕获吞掉时用户看到
    「结构化落库失败」而不是「请重新打开再同步」—— 原因是错的，也无法自助恢复。

    🔴 判据是**顺序**：`RevisionConflictError` 必须排在 `Exception` 之前。Python 按序
    匹配，写在后面等于不存在。宽捕获本身是这条端点的既有形态（Task 60 删第二套流程时
    收口），本判据不要求现在删掉它 —— 但要求它不再遮蔽冲突。
    """
    fn = _find_function(_parse(path), qualname)
    checked = 0
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        if not any(
            isinstance(inner, ast.Call)
            and _dotted(inner.func).rsplit(".", 1)[-1] == "_save_fields"
            for statement in node.body
            for inner in ast.walk(statement)
        ):
            continue
        checked += 1
        caught = [
            _dotted(handler.type) if handler.type is not None else "<bare>"
            for handler in node.handlers
        ]
        assert "RevisionConflictError" in caught, (
            f"{qualname} 没有把并发冲突翻译成 409，实得 {caught}"
        )
        if "Exception" in caught:
            assert caught.index("RevisionConflictError") < caught.index("Exception"), (
                f"{qualname} 的窄捕获排在宽捕获之后 = 永远走不到：{caught}"
            )
        raises = [
            ast.unparse(inner)
            for handler in node.handlers
            if _dotted(handler.type or ast.Constant(None)) == "RevisionConflictError"
            for inner in ast.walk(handler)
            if isinstance(inner, ast.Call) and _dotted(inner.func) == "HTTPException"
        ]
        assert any("409" in text for text in raises), (
            f"{qualname} 的冲突分支必须回 409，实得 {raises}"
        )
    assert checked == 1, f"{qualname} 里包住 _save_fields 的 try 应恰一处，实得 {checked}"


# ═══════════════════════════════════════════════════════════════════════════
# 七、`.versions` 快照：不再发明版本号
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_the_storage_snapshot_no_longer_invents_a_version(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    """**Validates: Requirements 2.1** / Property 61

    `save_version` 只把**当前**文件复制进 `.versions/` —— 内容一个字节没变。它改造前
    却 `file_version += 1`，造成两件事：

    1. **伪版本**：「版本 7」可能与「版本 6」逐字节相同；
    2. **四方争抢同一个计数器**（WOPI / 离线上传 / structure 保存 / 本方法），快照名与
       版本号的对应关系随之不确定。

    **characterization**：仍然复制出快照文件、仍然回传 `version_file` 与
    `total_versions`。
    **migrated behaviour**：快照名跟随真正在动的 `content_revision`；`file_version`
    一个字节不动；不 flush、不 commit（它不再是 content writer）。

    真实执行（不是 AST）：路径必须落在允许的 legacy 根内，否则 `resolve_wp_file` 会判
    `path_rejected` —— 所以工作目录建在仓库根下的 `tmp_*`（已进 .gitignore），用完删。
    """
    from app.services.wp_storage_service import WpStorageService

    work = Path(tempfile.mkdtemp(prefix="tmp_task19_savever_", dir=str(_REPO)))
    try:
        target = work / "D2-1.xlsx"
        target.write_bytes(b"PK\x03\x04-current-body")
        wp = _StubRow(
            file_path=str(target), file_version=11, content_revision=4,
        )
        session = _RecordingSession([_StubResult(scalar=wp)])

        result = await WpStorageService(session).save_version(uuid.uuid4())

        assert "error" not in result, result
        snapshot = Path(result["version_file"])
        assert snapshot.is_file(), snapshot
        assert snapshot.read_bytes() == b"PK\x03\x04-current-body", "快照内容必须是当前文件"
        assert snapshot.parent == target.parent / ".versions" / "D2-1"
        assert snapshot.name.startswith("v4_"), (
            f"快照名必须跟随 content_revision(4)，实得 {snapshot.name}"
        )
        assert not snapshot.name.startswith("v11_"), (
            f"快照名还绑在已冻结的 file_version(11) 上：{snapshot.name}"
        )
        assert wp.file_version == 11, "备份动作不得推进 file_version"
        assert wp.content_revision == 4, "备份动作不得推进 content_revision"
        assert session.actions == [], (
            f"备份不改业务内容，不该 flush/commit，实得 {session.actions}"
        )
        assert result["content_revision"] == 4
        assert result["snapshot_of_revision"] == 4
        assert "new_version" not in result, (
            "备份动作不产生新版本，回传 `new_version` 会让调用方以为版本前进了"
        )
        # characterization（**不是**期望值）：`total_versions` 在复制之后才 listdir，
        # 再 `+1`，因此对第一份快照回 2 —— 它多报一个。这是本任务**之前**就有的既有
        # 形态，且没有任何消费方（`/save-version` 无前端调用方）。Task 19 的边界是版本
        # 域，不顺手改它的返回值语义；改动只能连同一个明确的调用方一起做，否则就是无
        # 证据的行为变更。此处逐字钉住现状，将来真要修时这条会红，提醒同批更新调用方。
        assert result["total_versions"] == 2
    finally:
        shutil.rmtree(work, ignore_errors=True)
