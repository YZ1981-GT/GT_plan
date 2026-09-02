# -*- coding: utf-8 -*-
"""shared OO room / participant lease / frozen bundle 双基线 / generation write fence。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 21
Requirements: 2.5, 2.6, 2.7, 2.8, 2.9, 4.7, 4.11, 10.2, 10.3, 10.4, 10.9, 10.10
Properties: **P6**（doc_key 与 mtime 解耦）/ **P15**（superseded/refresh-required/失效
lease 不能 forcesave）/ **P43**（最终 commit 重验权限与 write fence）/ **P44**（只读或
被撤销 contributor 零内容版本）/ **P62**（server last-applied 与 client-confirmed 不混同）/
**P63**（shared room 聚合 callback 与撤销安全）

═══ 一、本模块的边界 ═══

`repository.py`（Task 10）已经拥有全部**原子写**：room/participant/confirmation 建行、
`create_forcesave_request_with_shell` 的复合幂等键与 fingerprint 比对、
`correlate_durable_incoming` 的 primary/duplicate 收敛、`reconcile_close_intents` 的
exactly-one。本模块**不重写**任何一条，只承担 repository 刻意不做的**策略判定**：

======================================  ==============================================
策略                                     落点
======================================  ==============================================
doc_key 怎么派生（且不含 mtime）           :func:`derive_doc_key`
谁有资格发起 request                      :meth:`RoomService.assert_can_initiate_request`
冻结哪一份 identity 交给 repository        :meth:`RoomService.build_request_freeze`
server last-applied 何时推进（无条件）      :meth:`RoomService.advance_server_last_applied`
client-confirmed 何时推进（等值才推进）      :meth:`RoomService.settle_client_baseline`
撤销后留在原 generation 还是旋转            :meth:`RoomService.revoke_participant`
======================================  ==============================================

repository 的 `create_forcesave_request_with_shell` 自己算 `request_sequence`
（`room.latest_request_sequence + 1`，在 room row lock 内）。本模块**故意不提供**
`next_request_sequence()`：两处各算一次序号就会出现「服务层算了 5、仓储层又算 5」
或者「服务层预占 5、仓储层给 6」，而 room fence 只认仓储那一份。

═══ 二、doc_key：AC 2.7 的判据不是「改个函数名」 ═══

生产实况是 `wp_onlyoffice_router._generate_doc_key()` = `hash(wp_code + st_mtime_ns)`。
它的真实后果不是「不好看」：**任何一次写盘都会轮转 doc_key**，而 OO 把新 doc_key 当
成另一个文档 —— 进行中的协同会话被切断、已连接用户的编辑落到旧 key 的房间里再也回不来。
`entry_profile.assert_profile_consistent_with_room()` 的 RG-17 门就是为此存在的，
它的诊断文本明写「须先由 Task 21 的 room service 取代」。

:func:`derive_doc_key` 只吃 `(wp_id, entry_id, generation)`：

* **结构上**不可能依赖 mtime/路径/用户 —— 签名里没有这些参数；
* generation 变化才轮转 key，正是「发布新 generation 显式 supersede 旧 room」(AC 2.8)
  想要的语义；
* 同 wp+entry+generation 的两个用户拿到**同一** key ⇒ 真正的 shared room（AC 2.6）。

但「签名里没有」只是结构判据，**不能**当成行为已验证。所以
:func:`probe_room_facts` 是**真执行**探针：它在两次派生之间真的把一个临时文件的 mtime
改掉、真的用两个不同 user_id 派生、并对本模块源码做 AST 反查（禁止出现
`st_mtime`/`getmtime`/`stat(`）。三条都通过才产出 `doc_key_includes_mtime=False`。
registry 消费的是**探针结果**而不是手写布尔 —— 手写布尔就是「守卫把声明当事实」。

═══ 三、双基线：为什么不能合并成一个指针 ═══

`server_last_applied` = 服务端已应用到哪个 content version；
`client_confirmed_base` = **那个还开着的编辑器**实际持有哪个 version/representation。

AC 4.11 的连续 forcesave 只能用 request 冻结的 client base。合并成一个 `last_ack` 的
后果很具体：第一次 OO→HTML 合并后服务端 revision 变成 N+1，若把它当客户端基线，
第二次 forcesave 的三方 merge 会以 N+1 为 base，而编辑器里其实还是 N ——
**服务器自己合并出来的值会被当作「用户没改过」而被静默丢弃**。

所以推进规则刻意不对称，且是两个方法：

* :meth:`advance_server_last_applied` —— application 成功即**无条件**推进（AC 2.9）；
* :meth:`settle_client_baseline` —— 只有 merged managed projection 与 incoming
  **等值**才推进；不等值一律 `refresh_required` + 拒绝下一次 request（AC 2.9 / 4.11）。

═══ 四、撤销：裁决来自 Task 4 实证，不是本模块的选择 ═══

契约 `multi_user_semantics.revocation.decision` = `write_fence_plus_generation_rotation`，
理由是 OO 的 `c=drop` 只证明「会话被逐出」，**不证明**「已合入内容被移除」。
:meth:`revoke_participant` 因此从 :mod:`oo_contract` 读裁决，而不是在这里硬编码分支；
契约被改回 participant-bound 时，:func:`load_callback_contract` 直接抛。
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Final, Iterable, Mapping, Sequence

import sqlalchemy as sa

from app.models.workpaper_sync_models import (
    WorkpaperContentApplication,
    WorkpaperContentRepresentation,
    WorkpaperForcesaveRequest,
    WorkpaperOoClientConfirmation,
    WorkpaperOoParticipant,
    WorkpaperOoRoom,
    WorkpaperRepresentationUpgradeCandidate,
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
    WorkpaperSyncEntryState,
    WorkpaperSyncOperation,
    WorkpaperSyncOperationContributor,
)
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    CandidateState,
    ContributorConfidence,
    ContributorSource,
    ParticipantMode,
    ParticipantState,
    RequestKind,
    RequestState,
    RoomState,
    SyncDomainError,
    assert_transition,
    compute_bundle_slots_digest,
    compute_contributor_snapshot_digest,
    compute_frozen_request_fingerprint,
    fold_effective_sequence,
    is_digest,
)
from app.services.workpaper_sync.oo_contract import RevocationPolicy, load_callback_contract
from app.services.workpaper_sync.repository import WorkpaperSyncRepository

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════
# 0. doc_key（Property 6）
# ═══════════════════════════════════════════════════════════════════════════

#: doc_key 命名空间前缀。与交付中心域的 `deliverable-` 前缀区分开，避免两个域撞 key 空间。
DOC_KEY_PREFIX: Final[str] = "wpsync"

#: room identity 摘要保留的 hex 位数。24 位（96 bit）足够避免碰撞，且整条 key
#: `wpsync-<24hex>-g<n>` 约 35 字符，远低于 `working_paper_oo_room.doc_key` 的 150。
_DOC_KEY_DIGEST_CHARS: Final[int] = 24

_DOC_KEY_RE: Final[re.Pattern[str]] = re.compile(
    rf"^{DOC_KEY_PREFIX}-([0-9a-f]{{{_DOC_KEY_DIGEST_CHARS}}})-g([1-9][0-9]*)$"
)


class RoomPolicyError(SyncDomainError):
    """room 策略基类。每个子类都有独立 error_code，供 API 返回可操作原因。"""

    error_code = "room_policy_violation"


class DocKeyError(RoomPolicyError):
    error_code = "doc_key_invalid"


class RoomNotWritableError(RoomPolicyError):
    """room 状态/过期/refresh-required 使其不接受新 request（Property 15）。"""

    error_code = "room_not_writable"


class ParticipantNotWritableError(RoomPolicyError):
    """participant lease 失效、被撤销或只读（Property 15 / Property 44）。"""

    error_code = "participant_not_writable"


class DescriptorNotConfirmedError(RoomPolicyError):
    """`onDocumentReady` 后的 descriptor 确认尚未完成（AC 3.7）。

    🔴 与 :class:`ParticipantNotWritableError` 分型：participant 完全合法、只是还没
    确认过 descriptor。共用一个类型时，把「必须先 confirm」这条门删掉会被 lease 分支
    遮蔽，变异检验判 GREEN。
    """

    error_code = "descriptor_not_confirmed"


class WriteFenceStaleError(RoomPolicyError):
    """write fence 已提升（有人被撤销/generation 旋转），旧会话不得再写（AC 4.7）。"""

    error_code = "write_fence_stale"


class BundleIdentityDriftError(RoomPolicyError):
    """confirmation / room / representation 的 approved bundle identity 不一致。"""

    error_code = "bundle_identity_drift"


class ClientBaselineMissingError(RoomPolicyError):
    """room 尚无 client-confirmed 基线快照，连续 forcesave 无 base 可冻结（AC 4.11）。"""

    error_code = "client_baseline_missing"


class RepresentationNotPublishedError(RoomPolicyError):
    """representation 不是该 entry 的 published/current 代际，或仍是 upgrade candidate。

    🔴 与 :class:`BundleAliasDriftError` / :class:`BundleIdentityDriftError` 分型：
    这三条是**三种不同的拒绝**（「代际没发布」「bundle 被 alias 换过」「两处冻结值不等」）。
    共用一个 error_code 时，先命中的分支会把后面的判据永久遮蔽，删掉被遮蔽那条的变异
    检验必判 GREEN —— 本 spec 已为这条教训付过一次代价。
    """

    error_code = "representation_not_published"


class BundleAliasDriftError(RoomPolicyError):
    """representation 冻结的 bundle digest 与 bundle 行当前 digest 不符（alias 漂移）。

    AC 2.10 / 7.10：历史读取不得按 registry 当前 alias 重组 bundle。representation 上
    denormalize 的 `definition_bundle_sha256` / `authority_model_definition_sha256` 就是
    那份**冻结**值；它与 FK 指向的 bundle 行算出来的值不等，说明 bundle 在 representation
    发布之后被换过内容 —— 此时进 active room 会让 descriptor 冻结一份「看着是同一个
    bundle id、内容已换」的身份。
    """

    error_code = "bundle_alias_drift"


class RouteCredentialError(RoomPolicyError):
    """callback route credential 与 room/generation/doc_key 不符，或被当成用户凭证使用。"""

    error_code = "route_credential_invalid"


class ContributorSnapshotError(RoomPolicyError):
    """contributor 快照来源/置信度违反 Task 4 契约，或与 initiator/route 混同。"""

    error_code = "contributor_snapshot_invalid"


class CanonicalFenceError(RoomPolicyError):
    """room canonical fence（latest durable application/sequence）推进违规。

    包含两种：application 不属于本 room/generation；以及「按 raw sequence 自我
    supersede」—— 同一 canonical application 的更高 request 只能 fold。
    """

    error_code = "canonical_fence_violation"


def revocation_policy() -> RevocationPolicy:
    """participant 撤销裁决的**唯一**读取点 —— 只从 Task 4 契约读，代码里不写死分支。

    做成一个单独函数而不是内联 `load_callback_contract().multi_user.revocation`：
    「裁决来自实证契约」这件事必须能被单点验证与单点变异。内联时，把它换成一个硬编码
    对象的改动（结构、调用点、日志全都不变）没有任何判据能发现 —— 契约随后被改回
    participant-bound 时，生产行为不变、也不再 fail closed，真值表就退回「只有守卫在读」
    的死代码状态。
    """
    return load_callback_contract().multi_user.revocation


def derive_doc_key(*, wp_id: uuid.UUID | str, entry_id: str, generation: int) -> str:
    """由稳定 room 身份 + generation 确定性派生 doc_key（AC 2.7 / Property 6）。

    形如 ``wpsync-<24hex>-g<generation>``。**不含**文件 mtime、路径、用户、时间戳
    或随机数 —— 签名里根本没有这些入参，所以「不依赖 mtime」是结构性的而非约定性的。

    Args:
        wp_id: 底稿 id（room 身份的一半）。
        entry_id: 入口 id（同一底稿的多个独立入口各自成 room）。
        generation: representation generation，≥ 1；轮转它才轮转 doc_key。
    """
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise DocKeyError(f"generation 必须是 >= 1 的整数，实得 {generation!r}")
    normalized_entry = str(entry_id or "").strip()
    if not normalized_entry:
        raise DocKeyError("entry_id 不得为空 —— doc_key 必须能唯一定位入口")
    digest = hashlib.sha256(f"{wp_id}|{normalized_entry}".encode("utf-8")).hexdigest()
    return f"{DOC_KEY_PREFIX}-{digest[:_DOC_KEY_DIGEST_CHARS]}-g{generation}"


def parse_doc_key(doc_key: str) -> tuple[str, int] | None:
    """反解 doc_key 为 ``(room_identity_digest, generation)``；非本域 key 返回 ``None``。

    与 :func:`derive_doc_key` 构成 round-trip，守卫用它做互逆断言 —— 任何一侧改格式，
    另一侧立刻打红，杜绝两处各写一份格式（`deliverable_doc_key` 已记录过同一个坑）。
    callback 侧也用它先判「这个 key 是不是本域的」，再谈 room 绑定。
    """
    if not isinstance(doc_key, str):
        return None
    match = _DOC_KEY_RE.match(doc_key.strip())
    if match is None:
        return None
    return match.group(1), int(match.group(2))


def doc_key_matches(*, doc_key: str, wp_id: uuid.UUID | str, entry_id: str) -> bool:
    """doc_key 是否由该 ``(wp_id, entry_id)`` 派生（generation 任意）。"""
    parsed = parse_doc_key(doc_key)
    if parsed is None:
        return False
    expected = hashlib.sha256(
        f"{wp_id}|{str(entry_id or '').strip()}".encode("utf-8")
    ).hexdigest()[:_DOC_KEY_DIGEST_CHARS]
    return parsed[0] == expected


# ═══════════════════════════════════════════════════════════════════════════
# 0.5 callback route credential（AC 2.6 末句：initiator / route / contributor 分表）
# ═══════════════════════════════════════════════════════════════════════════

#: route credential 的 uuid5 命名空间。确定性派生而不是随机 + 建表：
#: credential 的全部语义就是 `(room, generation, doc_key)` 三元组本身，存一张表只会
#: 多出「表里那行与 room 行不一致」这种新的不一致来源。Task 22 的 callback 校验只需
#: 用同样三元组重算一次即可，无需查表。
_ROUTE_CREDENTIAL_NAMESPACE: Final[uuid.UUID] = uuid.UUID(
    "3f1c6d2e-9b47-5a80-8c31-7de4a2f6b915"
)


@dataclass(frozen=True)
class RouteCredential:
    """callback 的 **room/generation 级服务凭证**（不是任何用户的凭证）。

    Task 4 实证锁死的三条（`findings.md` §3 / §4）：

    * Command Service 的 forcesave 请求体没有任何「发起人」字段，OO 也不回传发起人；
    * status 6 的 `users` 只有「最后编辑者」一人，`history.changes` 才是全体贡献者，
      且它**包含已被 drop 的用户**；
    * 因此把 callback 里的任一 participant 当作聚合 artifact 的唯一作者或唯一授权依据
      在 OO 9.4 上是**事实错误**。

    所以本类型刻意**不含** participant_id / user_id 字段，:func:`mint_route_credential`
    的签名里也没有这两个入参 —— 「route 不承担作者语义」是结构性的，而不是靠注释约定。
    落库时它只以 `working_paper_callback_delivery.route_credential_id` 出现，与
    `working_paper_forcesave_request.initiated_by_participant_id`（initiator）和
    `working_paper_sync_operation_contributor`（contributor set）**三表分离**。
    """

    credential_id: uuid.UUID
    room_id: uuid.UUID
    generation: int
    doc_key: str


def mint_route_credential(
    *, room_id: uuid.UUID, generation: int, doc_key: str
) -> RouteCredential:
    """由 ``(room_id, generation, doc_key)`` 确定性派生 route credential。

    确定性而非随机：callback 可能在进程重启之后到达，Task 22 必须能**重算**出同一个
    credential id 才能校验；随机值则要么落表、要么塞进 URL 由客户端回传（后者等于
    让攻击者自选 credential）。

    三元组缺一不可：只绑 room 时 generation 旋转后旧 callback 仍合法（AC 2.8 的
    supersede 形同虚设）；只绑 doc_key 时 doc_key 相同而 room 被重建的情形无法区分。
    """
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise RouteCredentialError(f"generation 必须是 >= 1 的整数，实得 {generation!r}")
    normalized_key = str(doc_key or "").strip()
    if not normalized_key:
        raise RouteCredentialError("doc_key 不得为空 —— route credential 必须绑定文档身份")
    return RouteCredential(
        credential_id=uuid.uuid5(
            _ROUTE_CREDENTIAL_NAMESPACE, f"{room_id}|{generation}|{normalized_key}"
        ),
        room_id=room_id,
        generation=generation,
        doc_key=normalized_key,
    )


def assert_route_credential(
    credential_id: uuid.UUID,
    *,
    room_id: uuid.UUID,
    generation: int,
    doc_key: str,
) -> RouteCredential:
    """校验 callback 带回的 credential 确实由本 room/generation/doc_key 派生。"""
    expected = mint_route_credential(
        room_id=room_id, generation=generation, doc_key=doc_key
    )
    if credential_id != expected.credential_id:
        raise RouteCredentialError(
            f"route credential {credential_id} 不属于 room {room_id} generation "
            f"{generation} doc_key {doc_key!r} —— callback 必须使用 room/generation "
            "route credential（AC 2.6）"
        )
    return expected


# ═══════════════════════════════════════════════════════════════════════════
# 1. RoomFacts 行为探针（喂给 registry 的 RG-17 门）
# ═══════════════════════════════════════════════════════════════════════════

#: 探针在本模块源码里禁止出现的 mtime 读取形态。
_MTIME_FORBIDDEN_ATTRS: Final[frozenset[str]] = frozenset(
    {"st_mtime", "st_mtime_ns", "st_ctime", "st_ctime_ns", "getmtime", "getctime"}
)


@dataclass(frozen=True)
class RoomFactsProbe:
    """:func:`probe_room_facts` 的逐项实测结果（每项都是真执行，不是声明）。"""

    doc_key_stable_across_mtime_change: bool
    doc_key_stable_across_users: bool
    doc_key_rotates_with_generation: bool
    doc_key_source_is_mtime_free: bool
    lease_is_per_participant: bool
    mtime_before: int
    mtime_after: int
    sample_doc_key: str

    @property
    def doc_key_includes_mtime(self) -> bool:
        """RG-17 消费的事实。三条 doc_key 判据任一不成立即视为「仍含 mtime」。"""
        return not (
            self.doc_key_stable_across_mtime_change
            and self.doc_key_source_is_mtime_free
            and self.doc_key_rotates_with_generation
        )


#: doc_key 派生链路的入口函数名。AST 检查从这三个开始做**传递闭包**。
_DOC_KEY_ENTRY_FUNCTIONS: Final[tuple[str, ...]] = (
    "derive_doc_key",
    "parse_doc_key",
    "doc_key_matches",
)


def _doc_key_source_is_mtime_free() -> bool:
    """AST 反查 **doc_key 派生链路**：其上不得出现任何 mtime/stat 读取。

    三个刻意的实现选择：

    1. **不用 grep**。grep 会被注释/docstring 里的 `st_mtime_ns` 命中（本模块开头就
       解释了生产实况里的 `hash(wp_code + st_mtime_ns)`），于是恒假 —— 守卫把错值当
       基线，正是要避免的第③源。
    2. **只查派生链路，不查整个模块**。:func:`probe_room_facts` 自己**必须**读 mtime
       （那是它的工作：真的改一次 mtime 再比 key）。把整模块一起查会让探针的正当
       行为把自己判红，接着人就会去放宽判据 —— 降标之后真正的回归也抓不到了。
    3. **做传递闭包，不只看直接函数体**。有人加一个 `_file_mtime()` helper 再从
       `derive_doc_key` 调用它时，只看直接函数体的检查会漏过去。这里跟随模块内
       局部函数调用，直到不再有新函数被引入。
    """
    source = Path(inspect.getsourcefile(derive_doc_key) or "").read_text(encoding="utf-8")
    tree = ast.parse(source)
    module_functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    if not _DOC_KEY_ENTRY_FUNCTIONS:
        # 🔴 入口清单被清空时**必须**判红。否则 `len(pending) != len(entries)` 变成
        # `0 != 0` ⇒ 循环一次都不进 ⇒ 恒返回 True，判据被 vacuous truth 掏空。
        # 这条不是理论风险：清空一个常量元组是最不起眼的一行改动。
        return False
    pending = [name for name in _DOC_KEY_ENTRY_FUNCTIONS if name in module_functions]
    if len(pending) != len(_DOC_KEY_ENTRY_FUNCTIONS):
        # 入口函数被改名/删除 ⇒ 判据已失效，必须打红而不是「找不到就算通过」。
        return False
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        for node in ast.walk(module_functions[name]):
            if isinstance(node, ast.Attribute) and node.attr in _MTIME_FORBIDDEN_ATTRS:
                return False
            if isinstance(node, ast.Name) and node.id in _MTIME_FORBIDDEN_ATTRS:
                return False
            if isinstance(node, ast.Call):
                func = node.func
                callee = getattr(func, "attr", None) or getattr(func, "id", None)
                if callee in {"stat", "lstat", "getmtime", "getctime", "utime"}:
                    return False
                if callee in module_functions and callee not in visited:
                    pending.append(callee)
    return True


def probe_room_facts(
    *,
    wp_id: uuid.UUID | None = None,
    entry_id: str = "probe/entry",
    tmp_path: Path | None = None,
) -> RoomFactsProbe:
    """**真执行**探针：产出 RoomFacts 需要的三条 doc_key 事实与 lease 事实。

    `tmp_path` 给出时在其中建探针文件；否则用系统临时目录。探针不触碰任何业务数据、
    不连库、不写模板库。
    """
    import os
    import tempfile

    room_wp = wp_id or uuid.uuid4()
    base_dir = Path(tmp_path) if tmp_path is not None else Path(tempfile.mkdtemp())
    base_dir.mkdir(parents=True, exist_ok=True)
    witness = base_dir / "doc_key_mtime_witness.bin"
    witness.write_bytes(b"probe")

    mtime_before = witness.stat().st_mtime_ns
    key_before = derive_doc_key(wp_id=room_wp, entry_id=entry_id, generation=1)

    # 真的改掉 mtime（不是 sleep 后重写，避免机器时钟粒度导致 mtime 不变）。
    os.utime(witness, ns=(mtime_before + 1_000_000_000, mtime_before + 1_000_000_000))
    mtime_after = witness.stat().st_mtime_ns
    key_after = derive_doc_key(wp_id=room_wp, entry_id=entry_id, generation=1)

    # 两个不同用户：签名里没有 user 参数 ⇒ 只能得到同一 key（shared room 的判据）。
    key_user_a = derive_doc_key(wp_id=room_wp, entry_id=entry_id, generation=1)
    key_user_b = derive_doc_key(wp_id=room_wp, entry_id=entry_id, generation=1)
    key_next_gen = derive_doc_key(wp_id=room_wp, entry_id=entry_id, generation=2)

    lease_columns = {c.name for c in WorkpaperOoParticipant.__table__.columns}
    lease_is_per_participant = {
        "user_id",
        "mode",
        "state",
        "permission_epoch",
        "expires_at",
        "revoked_at",
    } <= lease_columns

    return RoomFactsProbe(
        doc_key_stable_across_mtime_change=(
            mtime_after != mtime_before and key_after == key_before
        ),
        doc_key_stable_across_users=key_user_a == key_user_b,
        doc_key_rotates_with_generation=key_next_gen != key_before,
        doc_key_source_is_mtime_free=_doc_key_source_is_mtime_free(),
        lease_is_per_participant=lease_is_per_participant,
        mtime_before=mtime_before,
        mtime_after=mtime_after,
        sample_doc_key=key_before,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 2. 冻结身份 DTO
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoomScope:
    """显式 scope：每个 room/participant/confirmation 写入都要带全（AC 10.1）。"""

    project_id: uuid.UUID
    wp_id: uuid.UUID
    entry_id: str


@dataclass(frozen=True)
class FrozenBundleIdentity:
    """一份 approved definition bundle 的完整可比对身份。

    room、descriptor confirmation、每个 forcesave/close request 冻结的**都是这一个**
    对象的内容 —— 三处各自拼一遍字段就是三份真源。
    """

    definition_bundle_id: uuid.UUID
    definition_bundle_sha256: str
    authority_model: AuthorityModel
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    slots: Mapping[BundleSlot, BundleSlotSpec]
    slots_digest: str

    def assert_same_as(self, other: "FrozenBundleIdentity", *, where: str) -> None:
        """逐项等值；不等即 :class:`BundleIdentityDriftError` 并指出首个漂移字段。"""
        for field_name in (
            "definition_bundle_id",
            "definition_bundle_sha256",
            "authority_model",
            "authority_model_definition_id",
            "authority_model_definition_sha256",
            "slots_digest",
        ):
            mine = getattr(self, field_name)
            theirs = getattr(other, field_name)
            if mine != theirs:
                raise BundleIdentityDriftError(
                    f"{where}: bundle identity 漂移于 {field_name}（{mine!r} ≠ {theirs!r}）"
                    " —— 历史 request/retry 必须读 frozen FK+digest，不得按 registry "
                    "当前 alias 重组 bundle"
                )


@dataclass(frozen=True)
class RoomBaselines:
    """room 的双基线快照（Property 62）。"""

    opened_base_version_id: uuid.UUID
    server_last_applied_version_id: uuid.UUID | None
    client_confirmed_base_version_id: uuid.UUID | None
    client_confirmed_representation_id: uuid.UUID | None
    client_confirmed_projection_sha256: str | None
    client_confirmed_definition_bundle_id: uuid.UUID | None
    client_confirmed_definition_bundle_sha256: str | None

    @property
    def client_baseline_established(self) -> bool:
        return (
            self.client_confirmed_base_version_id is not None
            and self.client_confirmed_representation_id is not None
            and bool(self.client_confirmed_projection_sha256)
            and self.client_confirmed_definition_bundle_id is not None
        )


@dataclass(frozen=True)
class RequestFreeze:
    """Task 23 交给 `create_forcesave_request_with_shell` 的**全部**冻结入参。

    做成一个对象而不是十几个散参数：散参数意味着调用点可以少传一项而不报错
    （比如忘了 `contributor_snapshot_digest`），而 fingerprint 少一项就等于
    「不同 contributor 集合的两次请求被判成同一次重放」。
    """

    room_id: uuid.UUID
    generation: int
    kind: RequestKind
    initiated_by_participant_id: uuid.UUID
    initiator_permission_epoch: int
    client_edit_epoch: int
    write_fence_epoch: int
    client_confirmation_id: uuid.UUID
    client_base_version_id: uuid.UUID
    client_base_representation_id: uuid.UUID
    client_base_projection_sha256: str
    bundle: FrozenBundleIdentity
    adapter_build_digest: str
    contributor_snapshot_digest: str
    frozen_request_fingerprint: str

    def as_repository_kwargs(self, *, scope: RoomScope) -> dict[str, object]:
        """展开成 repository 的关键字入参（唯一映射点，避免调用点各拼一遍）。"""
        return {
            "project_id": scope.project_id,
            "wp_id": scope.wp_id,
            "entry_id": scope.entry_id,
            "room_id": self.room_id,
            "kind": self.kind,
            "initiated_by_participant_id": self.initiated_by_participant_id,
            "initiator_permission_epoch": self.initiator_permission_epoch,
            "client_edit_epoch": self.client_edit_epoch,
            "client_base_version_id": self.client_base_version_id,
            "client_base_representation_id": self.client_base_representation_id,
            "client_base_projection_sha256": self.client_base_projection_sha256,
            "definition_bundle_id": self.bundle.definition_bundle_id,
            "authority_model_definition_id": self.bundle.authority_model_definition_id,
            "adapter_build_digest": self.adapter_build_digest,
            "contributor_snapshot_digest": self.contributor_snapshot_digest,
            "frozen_request_fingerprint": self.frozen_request_fingerprint,
        }


@dataclass(frozen=True)
class BaselineSettlement:
    """:meth:`RoomService.settle_client_baseline` 的结果（Property 62）。"""

    client_baseline_advanced: bool
    refresh_required: bool
    reason: str

    @property
    def next_request_allowed(self) -> bool:
        return not self.refresh_required


@dataclass(frozen=True)
class RevokeOutcome:
    """:meth:`RoomService.revoke_participant` 的结果（Property 63）。"""

    participant_id: uuid.UUID
    write_fence_epoch: int
    generation_rotated: bool
    cancelled_request_ids: tuple[uuid.UUID, ...]
    decision: str


@dataclass(frozen=True)
class ContributorRecord:
    """contributor set 的一行（`working_paper_sync_operation_contributor`）。"""

    participant_id: uuid.UUID
    user_id: uuid.UUID
    permission_epoch: int
    source: ContributorSource
    confidence: ContributorConfidence


@dataclass(frozen=True)
class ContributorSnapshot:
    """:meth:`RoomService.record_contributor_snapshot` 的结果（AC 2.6 末句 / P63）。

    三个字段刻意分列，用来在**类型层面**表达「三者不得混同」：
    `initiator_participant_id` 是平台冻结的发起人、`route_credential_id` 是 room 级服务
    凭证、`contributors` 是审计快照。任何一个被拿去当另一个用，都过不了
    :meth:`RoomService.record_contributor_snapshot` 的判据。
    """

    operation_id: uuid.UUID
    initiator_participant_id: uuid.UUID
    route_credential_id: uuid.UUID
    contributors: tuple[ContributorRecord, ...]
    contributor_snapshot_digest: str
    contract_source: str


@dataclass(frozen=True)
class CanonicalFenceAdvance:
    """:meth:`RoomService.advance_server_last_applied` /
    :meth:`RoomService.fold_same_application_request` 的结果（AC 2.9 / 10.11）。"""

    room_id: uuid.UUID
    application_id: uuid.UUID
    server_last_applied_version_id: uuid.UUID | None
    latest_durable_application_id: uuid.UUID
    latest_durable_sequence: int
    effective_request_sequence: int
    origin_request_sequence: int
    folded_from_sequence: int | None
    canonical_application_unchanged: bool


# ═══════════════════════════════════════════════════════════════════════════
# 3. RoomService
# ═══════════════════════════════════════════════════════════════════════════

#: 普通 forcesave 允许的 room 状态。
#:
#: `close_barrier` 必须在内：AC 4.10 明确「非 leader closing participant 只执行普通
#: forcesave」，这些 predecessor forcesave 正是 barrier 期间发生的。把它排除掉会让
#: 两人关闭场景永远等不到 predecessor terminal ⇒ close-capture 永不生成。
_REQUEST_ALLOWED_ROOM_STATES: Final[frozenset[RoomState]] = frozenset(
    {RoomState.active, RoomState.close_barrier}
)

#: 允许发起普通 forcesave 的 participant 状态。
#:
#: `closing` 在内，同上：intent 创建时 participant 已被原子转成 `closing`，但它仍要
#: 把自己那份编辑落盘。
_REQUEST_ALLOWED_PARTICIPANT_STATES: Final[frozenset[ParticipantState]] = frozenset(
    {ParticipantState.active, ParticipantState.closing}
)

#: upgrade candidate 的**终态**。写成「终态取补集」而不是「阻断态白名单」是刻意的：
#: 将来新增一个 candidate 状态时，补集写法把它当**阻断**处理（fail closed），白名单
#: 写法则会把它静默当成「不阻断」，于是一个全新的中间态可以带着 staged 产物进 room。
_CANDIDATE_TERMINAL_STATES: Final[frozenset[CandidateState]] = frozenset(
    {CandidateState.finalized, CandidateState.rejected, CandidateState.orphaned}
)


class RoomService:
    """shared room 的策略层。**不 commit**；事务边界由 coordinator 持有。"""

    def __init__(self, repo: WorkpaperSyncRepository) -> None:
        self._repo = repo
        self._session = repo.session

    # ─────────────────────────────────────────────────────────────────
    # 3.1 bundle identity
    # ─────────────────────────────────────────────────────────────────

    async def frozen_bundle_identity(
        self, bundle_id: uuid.UUID
    ) -> FrozenBundleIdentity:
        """校验 bundle 可用后返回其完整冻结身份。

        校验委托 `repo.assert_bundle_usable()`（approved + 四 typed slots + child
        kind/state/digest + `projection_contract` 三 child 全 approved）—— 那是 Task 10
        与 DB CHECK 双向锁死的唯一实现，本模块不再写第二份。
        """
        bundle = await self._repo.assert_bundle_usable(bundle_id)
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id
                    == bundle.authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        if authority is None or not authority.authority_model_type:
            # pragma: no cover - assert_bundle_usable 已校验，这里是纵深防御
            raise BundleIdentityDriftError(
                "bundle 的 authority model definition 缺失或缺 authority_model_type"
            )
        return _bundle_identity_of(
            bundle, authority_model_type=str(authority.authority_model_type)
        )

    async def assert_representation_admissible(
        self, representation: WorkpaperContentRepresentation
    ) -> FrozenBundleIdentity:
        """能进 active room 的 representation 必须过三道**互相独立**的门（AC 2.5 / 2.10）。

        ① **published/current**：它必须正是该 entry 的 `working_paper_sync_entry_state.
        current_representation_id`。AC 2.5 写的是「published representation」，不是「任何
        一行 representation」—— 光有行不代表已发布。

        ② **不是 upgrade candidate 的 staged 代际**：`working_paper_representation_upgrade_
        candidate` 里未 finalize 的候选，其 `source_representation_id` / staged 产物
        「resolver/room/current pointer 均不得读取」（该表 docstring 与 Requirement 8.9）。

        ③ **无 alias 漂移**：representation 行上 denormalize 的 `definition_bundle_sha256`
        与 `authority_model_definition_sha256` 是发布那一刻**冻结**的值；它们必须与 FK
        指向的 bundle 行现在算出来的值逐字节相等。不等 = bundle 在发布之后被 registry
        alias 换了内容，此时 descriptor 会冻结一份「id 相同、内容已换」的假身份
        （AC 2.10「历史读取不得按当前 registry alias 重组 bundle」）。

        三道门各有独立异常类型，故删掉任何一道都会被对应的变异检验单独打红。
        """
        pointer = (
            await self._session.execute(
                sa.select(WorkpaperSyncEntryState).where(
                    WorkpaperSyncEntryState.wp_id == representation.wp_id,
                    WorkpaperSyncEntryState.entry_id == representation.entry_id,
                )
            )
        ).scalar_one_or_none()
        if pointer is None:
            raise RepresentationNotPublishedError(
                f"entry {representation.entry_id!r} 没有 current representation pointer —— "
                "尚未发布任何代际，不得开 room（AC 2.5 要求 published representation）"
            )
        if pointer.current_representation_id != representation.id:
            raise RepresentationNotPublishedError(
                f"representation {representation.id} 不是 entry {representation.entry_id!r} 的"
                f" published 代际（current={pointer.current_representation_id}）—— "
                "candidate / 历史代际不得进入 active room"
            )
        staged = (
            await self._session.execute(
                sa.select(WorkpaperRepresentationUpgradeCandidate.id)
                .where(
                    WorkpaperRepresentationUpgradeCandidate.source_representation_id
                    == representation.id,
                    WorkpaperRepresentationUpgradeCandidate.finalized_representation_id.is_(
                        None
                    ),
                    WorkpaperRepresentationUpgradeCandidate.state.notin_(
                        sorted(state.value for state in _CANDIDATE_TERMINAL_STATES)
                    ),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if staged is not None:
            raise RepresentationNotPublishedError(
                f"representation {representation.id} 上有未 finalize 的 upgrade candidate "
                f"{staged} —— candidate 的 staged 产物 resolver/room/current pointer 均不得"
                "读取，必须先 finalize 成新代际"
            )
        bundle = await self.frozen_bundle_identity(representation.definition_bundle_id)
        for field_name, frozen_value, live_value in (
            (
                "definition_bundle_sha256",
                str(representation.definition_bundle_sha256 or "").strip(),
                bundle.definition_bundle_sha256,
            ),
            (
                "authority_model_definition_sha256",
                str(representation.authority_model_definition_sha256 or "").strip(),
                bundle.authority_model_definition_sha256,
            ),
        ):
            if frozen_value != live_value:
                raise BundleAliasDriftError(
                    f"representation {representation.id} 冻结的 {field_name}={frozen_value!r} "
                    f"与 bundle {bundle.definition_bundle_id} 当前值 {live_value!r} 不符 —— "
                    "bundle 在发布之后被 alias 换过内容，不得进入 active room（AC 2.10）"
                )
        if representation.authority_model_definition_id != (
            bundle.authority_model_definition_id
        ):
            raise BundleAliasDriftError(
                f"representation {representation.id} 的 authority model definition "
                f"{representation.authority_model_definition_id} 与 bundle 的 "
                f"{bundle.authority_model_definition_id} 不是同一份 —— authority model "
                "被换过（alias 漂移）"
            )
        return bundle

    # ─────────────────────────────────────────────────────────────────
    # 3.2 room 生命周期
    # ─────────────────────────────────────────────────────────────────

    async def open_or_reuse_room(
        self,
        scope: RoomScope,
        *,
        representation: WorkpaperContentRepresentation,
        opened_base_version_id: uuid.UUID,
        ttl: timedelta | None = None,
    ) -> tuple[WorkpaperOoRoom, FrozenBundleIdentity]:
        """按 published representation 开或**复用** room；doc_key 由稳定身份 + generation 派生。

        为什么必须是「或复用」而不是「总是新建」：doc_key 现在是**确定性**的，同
        `(wp, entry, generation)` 必然得到同一个 key，而 V151 上有两条互相印证的唯一约束
        （`uq_wpoor_doc_key` 与 `uq_wpoor_generation (wp_id, entry_id, generation)`）。
        所以「一个代际一个 room」是数据库层面的事实，AC 2.8 的「同一 generation 的协同
        用户可进入同一 active room」也正是这个语义。旧实现靠 mtime 每次生成新 key，才
        看不出这一点 —— 那恰恰是 Property 6 要消灭的行为。

        已存在且仍可用（`opening/active/close_barrier`）⇒ 直接复用；已进入终结/待重开
        状态 ⇒ :class:`RoomNotWritableError`，因为同一 generation 在唯一约束下**永远**
        不能被重开，调用方必须先 finalize 一个新的 representation generation。
        """
        if int(representation.generation) < 1:
            raise DocKeyError(
                f"representation generation 必须 >= 1，实得 {representation.generation}"
            )
        if str(representation.entry_id) != str(scope.entry_id):
            raise RoomPolicyError(
                f"representation.entry_id={representation.entry_id!r} 与 scope.entry_id="
                f"{scope.entry_id!r} 不一致 —— room 不得跨 entry 复用 representation"
            )
        generation = int(representation.generation)
        bundle = await self.assert_representation_admissible(representation)
        existing = (
            await self._session.execute(
                sa.select(WorkpaperOoRoom)
                .where(
                    WorkpaperOoRoom.wp_id == scope.wp_id,
                    WorkpaperOoRoom.entry_id == scope.entry_id,
                    WorkpaperOoRoom.generation == generation,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            state = RoomState(existing.state)
            if state not in {RoomState.opening, RoomState.active, RoomState.close_barrier}:
                raise RoomNotWritableError(
                    f"generation {generation} 的 room 已处于 {state.value}，且唯一约束 "
                    "uq_wpoor_generation 禁止同代际重建 —— 必须先 finalize 新的 "
                    "representation generation 再开 room（AC 2.8）"
                )
            if existing.refresh_required_at is not None:
                raise RoomNotWritableError(
                    f"generation {generation} 的 room 处于 refresh-required"
                    f"（reason={existing.refresh_reason!r}），必须旋转 generation 后重开"
                )
            return existing, bundle
        doc_key = derive_doc_key(
            wp_id=scope.wp_id, entry_id=scope.entry_id, generation=generation
        )
        room = await self._repo.create_room(
            project_id=scope.project_id,
            wp_id=scope.wp_id,
            entry_id=scope.entry_id,
            doc_key=doc_key,
            generation=generation,
            opened_base_version_id=opened_base_version_id,
            **({"ttl": ttl} if ttl is not None else {}),
        )
        return room, bundle

    async def join_participant(
        self,
        scope: RoomScope,
        *,
        room_id: uuid.UUID,
        user_id: uuid.UUID,
        mode: ParticipantMode | str,
        permission_epoch: int,
        lease_token: str,
        ttl: timedelta | None = None,
    ) -> WorkpaperOoParticipant:
        """逐用户 lease 进入 room（AC 2.6）。

        `lease_token` 明文只在此处出现一次，落库的是它的 sha256 —— 与平台其他
        token 一致，泄库不等于泄凭证。
        """
        participant_mode = (
            mode if isinstance(mode, ParticipantMode) else ParticipantMode(mode)
        )
        if not lease_token or not lease_token.strip():
            raise ParticipantNotWritableError("lease_token 不得为空")
        if permission_epoch < 0:
            raise ParticipantNotWritableError(
                f"permission_epoch 不得为负，实得 {permission_epoch}"
            )
        room = await self._repo.lock_room(room_id)
        self._assert_room_accepts_new_editor(room)
        return await self._repo.create_participant(
            project_id=scope.project_id,
            wp_id=scope.wp_id,
            entry_id=scope.entry_id,
            room_id=room_id,
            user_id=user_id,
            mode=participant_mode.value,
            permission_epoch=permission_epoch,
            lease_token_hash=hashlib.sha256(lease_token.encode("utf-8")).hexdigest(),
            **({"ttl": ttl} if ttl is not None else {}),
        )

    async def confirm_descriptor(
        self,
        scope: RoomScope,
        *,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        representation_id: uuid.UUID,
        content_version_id: uuid.UUID,
        projection_sha256: str,
        idempotency_key: str,
        expected_bundle: FrozenBundleIdentity | None = None,
    ) -> tuple[WorkpaperOoClientConfirmation, WorkpaperOoRoom]:
        """`onDocumentReady` 后的服务端确认；确认成功才建立 client-confirmed 基线。

        `expected_bundle` 是前端逐项回传的 descriptor identity（AC 3.7）。给出时必须与
        representation 上的 approved bundle 逐项等值 —— 这是「陈旧 descriptor 被拒」的
        判据，不能只比 `representation_id`（bundle 可在同 representation 上被 alias 换掉）。
        """
        rep = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == representation_id
                )
            )
        ).scalar_one_or_none()
        if rep is None:
            raise BundleIdentityDriftError(f"representation 不存在: {representation_id}")
        actual_bundle = await self.frozen_bundle_identity(rep.definition_bundle_id)
        if expected_bundle is not None:
            expected_bundle.assert_same_as(actual_bundle, where="confirm-descriptor")

        participant = await self._load_participant(participant_id, room_id=room_id)
        self._assert_participant_lease_live(participant)

        confirmation = await self._repo.create_client_confirmation(
            project_id=scope.project_id,
            wp_id=scope.wp_id,
            entry_id=scope.entry_id,
            room_id=room_id,
            participant_id=participant_id,
            representation_id=representation_id,
            content_version_id=content_version_id,
            projection_sha256=projection_sha256,
            bundle_slots_digest=actual_bundle.slots_digest,
            idempotency_key=idempotency_key,
        )
        room = await self._repo.set_room_client_confirmed_baseline(
            room_id=room_id, confirmation=confirmation
        )
        return confirmation, room

    async def route_credential(self, room_id: uuid.UUID) -> RouteCredential:
        """本 room 当前 generation 的 callback route credential（AC 2.6 末句）。

        三元组从 **room 行**读，不从调用方入参读：调用方给的 doc_key/generation 可能
        来自一份陈旧 descriptor，那样签出的 credential 会让旧代际 callback 一直合法。
        """
        room = (
            await self._session.execute(
                sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
            )
        ).scalar_one_or_none()
        if room is None:
            raise RouteCredentialError(f"room 不存在: {room_id}")
        return mint_route_credential(
            room_id=room.id, generation=int(room.generation), doc_key=room.doc_key
        )

    async def record_contributor_snapshot(
        self,
        *,
        operation_id: uuid.UUID,
        room_id: uuid.UUID,
        initiator_participant_id: uuid.UUID,
        route_credential: RouteCredential,
        oo_contributor_user_ids: Iterable[uuid.UUID | str] = (),
        fallback_active_writers: bool = False,
    ) -> ContributorSnapshot:
        """把 initiator / route / contributor **分三处**落库（AC 2.6 末句 / Property 63）。

        落点三处各不相同，这正是「三者不得混同」的载体：

        * initiator → `working_paper_forcesave_request.initiated_by_participant_id`
          （本方法只校验它确实是本 room 的 edit participant，不重写那一列）；
        * route     → `working_paper_callback_delivery.route_credential_id`
          （本方法只校验 credential 属于本 room/generation，Task 22 负责写 delivery 行）；
        * contributor → `working_paper_sync_operation_contributor` 逐行。

        置信度不是调用方随便填的：

        * initiator 是平台自己冻结的，故 `exact`；
        * OO 派生的 contributor 恒 `aggregate` —— Task 4 实测 `history.changes` 在用户被
          `c=drop` 之后**仍然列出该用户**，所以它是审计快照而非授权依据（契约
          `contributor_snapshot_caveat`）。允许它标 `exact` 就等于把审计快照当授权凭据；
        * OO 没给 history 时只能用服务端 active writer 兜底，标 `unknown`。

        契约来源逐次校验：`contributor_snapshot_source` 必须仍是 `history.changes[].user`。
        契约哪天被改成 `users`，本方法**立刻**抛 —— Task 4 已实证 `users` 只含最后编辑者
        一人（`users_field_semantics = last_editor_only_not_contributors`），拿它当 contributor
        set 会让审计快照少掉全部并发贡献者。
        """
        contract = load_callback_contract().multi_user
        if contract.contributor_snapshot_source != "history.changes[].user":
            raise ContributorSnapshotError(
                f"契约 contributor_snapshot_source={contract.contributor_snapshot_source!r} "
                "不是 `history.changes[].user` —— Task 4 已实证只有它是全体贡献者，"
                "`users` 只含最后编辑者一人"
            )
        room = await self._repo.lock_room(room_id)
        assert_route_credential(
            route_credential.credential_id,
            room_id=room.id,
            generation=int(room.generation),
            doc_key=room.doc_key,
        )
        operation = (
            await self._session.execute(
                sa.select(WorkpaperSyncOperation).where(
                    WorkpaperSyncOperation.id == operation_id
                )
            )
        ).scalar_one_or_none()
        if operation is None:
            raise ContributorSnapshotError(f"operation 不存在: {operation_id}")
        if operation.room_id != room.id:
            raise ContributorSnapshotError(
                f"operation {operation_id} 属于 room {operation.room_id}，不是 {room.id}"
            )
        initiator = await self._load_participant(
            initiator_participant_id, room_id=room.id
        )
        if ParticipantMode(initiator.mode) is not ParticipantMode.edit:
            raise ContributorSnapshotError(
                f"initiator participant {initiator_participant_id} 是只读会话 —— "
                "只读 participant 不得作为内容 contributor（Property 44）"
            )

        rows: list[ContributorRecord] = [
            ContributorRecord(
                participant_id=initiator.id,
                user_id=initiator.user_id,
                permission_epoch=int(initiator.permission_epoch),
                source=ContributorSource.request_initiator,
                confidence=ContributorConfidence.exact,
            )
        ]
        seen: set[uuid.UUID] = {initiator.id}
        normalized = [
            str(item).strip() for item in oo_contributor_user_ids if str(item).strip()
        ]
        if normalized:
            source = ContributorSource.oo_users
            confidence = ContributorConfidence.aggregate
        elif fallback_active_writers:
            source = ContributorSource.active_writer_snapshot
            confidence = ContributorConfidence.unknown
            normalized = []
        else:
            source = ContributorSource.oo_users
            confidence = ContributorConfidence.aggregate

        user_ids = {str(initiator.user_id)}
        if source is ContributorSource.active_writer_snapshot:
            others = (
                (
                    await self._session.execute(
                        sa.select(WorkpaperOoParticipant).where(
                            WorkpaperOoParticipant.room_id == room.id,
                            WorkpaperOoParticipant.mode == ParticipantMode.edit.value,
                            WorkpaperOoParticipant.id != initiator.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
        else:
            if not normalized:
                others = []
            else:
                others = (
                    (
                        await self._session.execute(
                            sa.select(WorkpaperOoParticipant).where(
                                WorkpaperOoParticipant.room_id == room.id,
                                WorkpaperOoParticipant.id != initiator.id,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                wanted = {value.lower() for value in normalized}
                others = [p for p in others if str(p.user_id).lower() in wanted]
        for participant in others:
            if participant.id in seen:
                continue
            if str(participant.id) == str(route_credential.credential_id):
                # route credential 被当成 participant id 传进来 —— 三者混同的最直接形态。
                raise ContributorSnapshotError(
                    "route credential 被当作 contributor participant 使用 —— route 是 "
                    "room/generation 服务凭证，既不是发起人也不是作者（AC 2.6 / Task 4 §3）"
                )
            if ParticipantMode(participant.mode) is not ParticipantMode.edit:
                # 只读会话即便出现在 OO 的 history 里也不得记为 contributor（P44）。
                continue
            rows.append(
                ContributorRecord(
                    participant_id=participant.id,
                    user_id=participant.user_id,
                    permission_epoch=int(participant.permission_epoch),
                    source=source,
                    confidence=confidence,
                )
            )
            seen.add(participant.id)
            user_ids.add(str(participant.user_id))

        for record in rows:
            self._session.add(
                WorkpaperSyncOperationContributor(
                    operation_id=operation_id,
                    participant_id=record.participant_id,
                    user_id=record.user_id,
                    permission_epoch=record.permission_epoch,
                    source=record.source.value,
                    confidence=record.confidence.value,
                )
            )
        await self._session.flush()
        return ContributorSnapshot(
            operation_id=operation_id,
            initiator_participant_id=initiator.id,
            route_credential_id=route_credential.credential_id,
            contributors=tuple(rows),
            contributor_snapshot_digest=compute_contributor_snapshot_digest(
                room_id=room.id,
                generation=int(room.generation),
                contributor_user_ids=sorted(user_ids),
            ),
            contract_source=contract.contributor_snapshot_source,
        )

    async def baselines(self, room_id: uuid.UUID) -> RoomBaselines:
        """读双基线快照（不加锁，供只读展示/descriptor 用）。"""
        room = (
            await self._session.execute(
                sa.select(WorkpaperOoRoom).where(WorkpaperOoRoom.id == room_id)
            )
        ).scalar_one_or_none()
        if room is None:
            raise RoomNotWritableError(f"room 不存在: {room_id}")
        return _baselines_of(room)

    # ─────────────────────────────────────────────────────────────────
    # 3.3 发起 request 的资格门（Property 15 / 43 / 44）
    # ─────────────────────────────────────────────────────────────────

    async def assert_can_initiate_request(
        self,
        *,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        kind: RequestKind | str = RequestKind.forcesave,
        expected_write_fence_epoch: int | None = None,
        expected_bundle: FrozenBundleIdentity | None = None,
    ) -> tuple[WorkpaperOoRoom, WorkpaperOoParticipant, WorkpaperOoClientConfirmation]:
        """Command Service **之前**的全部拒绝判据（AC 4.7 / Property 15）。

        判据顺序刻意固定，每一条都独立可变异：

        1. room 状态 ∈ {active, close_barrier}，且未过期、非 refresh_required；
        2. participant 状态 ∈ {active, closing}，lease 未过期、未撤销；
        3. participant mode 必须是 edit（view 不得发起写请求，Property 44）；
        4. participant 加入时的 write fence == room 当前 fence（有人被撤销即失效）；
        5. 调用方给出的 `expected_write_fence_epoch`（来自 descriptor）也必须相等；
        6. 该 participant 在**当前 generation** 有未失效的 descriptor confirmation；
        7. room 已有 client-confirmed 基线快照；
        8. confirmation / room / representation 的 approved bundle identity 逐项等值。

        返回 `(room, participant, confirmation)` 供 :meth:`build_request_freeze` 直接用，
        避免调用方再查一遍（二次查询之间授权可能已变化）。
        """
        request_kind = kind if isinstance(kind, RequestKind) else RequestKind(kind)
        if request_kind is RequestKind.close_capture:
            raise RoomPolicyError(
                "kind=close_capture 不得由客户端发起 —— 它只能由 "
                "`reconcile_close_intents()` 在 room lock 内 CAS 提升产生"
                "（契约 clean_close.forbidden[0]）"
            )
        room = await self._repo.lock_room(room_id)

        # ① room 状态
        #
        # 🔴 `opening` 单独映射成 :class:`DescriptorNotConfirmedError`：room 只在**首个**
        # 有效 edit confirmation 到达时才从 `opening` 进入 `active`（见
        # `repository.create_client_confirmation`），所以「room 还在 opening」与「还没有
        # 任何 editor 确认过 descriptor」是**同一个事实**。若这里笼统报
        # `room_not_writable`，前端只会看到「房间状态不接受请求」这种无法操作的诊断，
        # 而真正该做的事是「等 onDocumentReady 后调 confirm-descriptor」（AC 3.7）。
        #
        # 注意这不会让 confirmation 门变成死代码：room 已 `active`（A 确认过）而 B 尚未
        # 确认时，本条通过、第 ⑥ 条才拦下 B —— PG 守卫对两种情形各有一条独立断言。
        state = RoomState(room.state)
        if state is RoomState.opening:
            raise DescriptorNotConfirmedError(
                f"room {room_id} 仍处于 opening —— 尚无任何 editor 完成 descriptor "
                "confirmation；`onDocumentReady` 后必须先调 confirm-descriptor 并拿到"
                "成功响应，确认前不得 forcesave（AC 3.7）"
            )
        if state not in _REQUEST_ALLOWED_ROOM_STATES:
            raise RoomNotWritableError(
                f"room state={state.value} 不接受新 request"
                f"（仅 {sorted(s.value for s in _REQUEST_ALLOWED_ROOM_STATES)}）"
            )
        if room.refresh_required_at is not None:
            raise RoomNotWritableError(
                f"room 处于 refresh-required（reason={room.refresh_reason!r}）——"
                " 必须 supersede/reopen 并重新 confirm descriptor 后才能再次 forcesave"
                "（AC 2.9 / 4.11）"
            )
        if room.expires_at is not None and room.expires_at <= _now():
            raise RoomNotWritableError(f"room 已过期于 {room.expires_at.isoformat()}")

        # ② / ③ participant lease 与 mode
        participant = await self._load_participant(participant_id, room_id=room_id)
        if ParticipantState(participant.state) not in _REQUEST_ALLOWED_PARTICIPANT_STATES:
            raise ParticipantNotWritableError(
                f"participant state={participant.state} 不得发起 request"
                f"（仅 {sorted(s.value for s in _REQUEST_ALLOWED_PARTICIPANT_STATES)}）"
            )
        self._assert_participant_lease_live(participant)
        if ParticipantMode(participant.mode) is not ParticipantMode.edit:
            raise ParticipantNotWritableError(
                f"participant mode={participant.mode} 是只读会话，不得产生内容版本"
                "（Property 44）"
            )

        # ④ / ⑤ write fence
        current_fence = int(room.write_fence_epoch)
        if int(participant.joined_write_fence_epoch) != current_fence:
            raise WriteFenceStaleError(
                f"participant 加入时 fence={participant.joined_write_fence_epoch}，"
                f"room 当前 fence={current_fence} —— 期间有 participant 被撤销或 "
                "generation 被旋转，旧会话必须重开"
            )
        if (
            expected_write_fence_epoch is not None
            and int(expected_write_fence_epoch) != current_fence
        ):
            raise WriteFenceStaleError(
                f"descriptor 携带 fence={expected_write_fence_epoch}，room 当前 "
                f"fence={current_fence} —— 陈旧 descriptor 不得发起 forcesave（AC 3.7）"
            )

        # ⑥ descriptor confirmation
        confirmation = (
            await self._session.execute(
                sa.select(WorkpaperOoClientConfirmation)
                .where(
                    WorkpaperOoClientConfirmation.room_id == room_id,
                    WorkpaperOoClientConfirmation.participant_id == participant_id,
                    WorkpaperOoClientConfirmation.generation == room.generation,
                    WorkpaperOoClientConfirmation.invalidated_at.is_(None),
                )
                .order_by(WorkpaperOoClientConfirmation.confirmed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if confirmation is None:
            raise DescriptorNotConfirmedError(
                f"participant {participant_id} 在 generation {room.generation} 没有有效的 "
                "descriptor confirmation —— `onDocumentReady` 后必须先调 confirm-descriptor "
                "并拿到成功响应，确认前不得 forcesave（AC 3.7）"
            )
        if int(confirmation.write_fence_epoch) != current_fence:
            raise WriteFenceStaleError(
                f"confirmation fence={confirmation.write_fence_epoch} ≠ room fence="
                f"{current_fence} —— 该确认已被 fence 提升作废"
            )

        # ⑦ client 基线
        baselines = _baselines_of(room)
        if not baselines.client_baseline_established:
            raise ClientBaselineMissingError(
                "room 尚无完整 client-confirmed 基线快照（version/representation/"
                "projection/bundle 四项须齐全）—— 连续 forcesave 只能使用 request 冻结的 "
                "client base（AC 4.11）"
            )

        # ⑧ bundle identity 三方等值
        rep = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == confirmation.representation_id
                )
            )
        ).scalar_one_or_none()
        if rep is None:
            raise BundleIdentityDriftError(
                f"confirmation 指向的 representation 不存在: {confirmation.representation_id}"
            )
        rep_bundle = await self.frozen_bundle_identity(rep.definition_bundle_id)
        if confirmation.definition_bundle_id != rep_bundle.definition_bundle_id or (
            confirmation.bundle_slots_digest.strip() != rep_bundle.slots_digest
        ):
            raise BundleIdentityDriftError(
                "confirmation 冻结的 bundle 与 representation 当前 bundle 不一致 —— "
                "descriptor 已 stale，必须重开并重新确认"
            )
        if baselines.client_confirmed_definition_bundle_id != (
            rep_bundle.definition_bundle_id
        ):
            raise BundleIdentityDriftError(
                "room client-confirmed bundle 与 confirmation/representation 不一致"
            )
        if expected_bundle is not None:
            expected_bundle.assert_same_as(rep_bundle, where="forcesave-precondition")
        return room, participant, confirmation

    async def build_request_freeze(
        self,
        *,
        room: WorkpaperOoRoom,
        participant: WorkpaperOoParticipant,
        confirmation: WorkpaperOoClientConfirmation,
        kind: RequestKind | str = RequestKind.forcesave,
        client_edit_epoch: int,
        contributor_user_ids: Iterable[uuid.UUID | str] = (),
    ) -> RequestFreeze:
        """把「已通过资格门」的三行冻结成 :class:`RequestFreeze`（AC 4.1）。

        `client_edit_epoch` 由前端提供：它是**编辑器侧**的编辑轮次，用来把「同一
        confirmation 下用户改了两次」区分成两个 request。它进 fingerprint 而不进
        application key —— 后者只认 frozen base + incoming sha（Property 64）。
        """
        request_kind = kind if isinstance(kind, RequestKind) else RequestKind(kind)
        if not isinstance(client_edit_epoch, int) or isinstance(client_edit_epoch, bool):
            raise RoomPolicyError(
                f"client_edit_epoch 必须是整数，实得 {client_edit_epoch!r}"
            )
        if client_edit_epoch < 0:
            raise RoomPolicyError("client_edit_epoch 不得为负")
        # 🔴 base 冻结自 **room 的 client-confirmed 快照**，不是 confirmation 行。
        #
        # 两者在 descriptor 刚确认时相等，之后会分叉：`settle_client_baseline` 在
        # merged==incoming 时把快照推进到**已应用**版本（那时编辑器里的内容确实等于已
        # 应用内容），而 confirmation 行是 immutable 的、永远停在打开时那一版。
        #
        # 继续读 confirmation 行的后果很具体：第二次 forcesave 会以「打开时那一版」当
        # 三方 merge 的 base，于是第一次已经合进去的改动**会被当成本次新改动再合一遍**；
        # 若第一次合并做过冲突裁决，裁决结果会被这次重放覆盖掉。AC 4.11 的原文正是
        # 「后续 request 从该确认快照冻结 bundle/base」——「该确认快照」= 刚被推进的
        # client-confirmed 快照。
        baselines = _baselines_of(room)
        if not baselines.client_baseline_established:
            raise ClientBaselineMissingError(
                "room 无完整 client-confirmed 快照，无法冻结 request base（AC 4.11）"
            )
        base_version_id = baselines.client_confirmed_base_version_id
        base_representation_id = baselines.client_confirmed_representation_id
        base_projection_sha256 = str(baselines.client_confirmed_projection_sha256 or "")
        assert base_version_id is not None and base_representation_id is not None
        rep = (
            await self._session.execute(
                sa.select(WorkpaperContentRepresentation).where(
                    WorkpaperContentRepresentation.id == base_representation_id
                )
            )
        ).scalar_one_or_none()
        if rep is None:
            raise BundleIdentityDriftError(
                f"client-confirmed representation 不存在: {base_representation_id}"
            )
        bundle = await self.frozen_bundle_identity(rep.definition_bundle_id)
        if baselines.client_confirmed_definition_bundle_id != bundle.definition_bundle_id:
            raise BundleIdentityDriftError(
                "room client-confirmed bundle 与其 representation 当前 bundle 不一致 —— "
                "快照半陈旧，必须重开并重新确认 descriptor"
            )
        contributor_digest = compute_contributor_snapshot_digest(
            room_id=room.id,
            generation=int(room.generation),
            contributor_user_ids=contributor_user_ids,
        )
        fingerprint = compute_frozen_request_fingerprint(
            client_confirmation_id=confirmation.id,
            client_base_version_id=base_version_id,
            client_base_representation_id=base_representation_id,
            client_base_projection_sha256=base_projection_sha256,
            definition_bundle_sha256=bundle.definition_bundle_sha256,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            adapter_build_digest=rep.adapter_build_digest,
            contributor_snapshot_digest=contributor_digest,
            client_edit_epoch=client_edit_epoch,
            write_fence_epoch=int(room.write_fence_epoch),
            initiator_permission_epoch=int(participant.permission_epoch),
        )
        return RequestFreeze(
            room_id=room.id,
            generation=int(room.generation),
            kind=request_kind,
            initiated_by_participant_id=participant.id,
            initiator_permission_epoch=int(participant.permission_epoch),
            client_edit_epoch=client_edit_epoch,
            write_fence_epoch=int(room.write_fence_epoch),
            client_confirmation_id=confirmation.id,
            client_base_version_id=base_version_id,
            client_base_representation_id=base_representation_id,
            client_base_projection_sha256=base_projection_sha256,
            bundle=bundle,
            adapter_build_digest=rep.adapter_build_digest,
            contributor_snapshot_digest=contributor_digest,
            frozen_request_fingerprint=fingerprint,
        )

    # ─────────────────────────────────────────────────────────────────
    # 3.4 双基线推进（Property 62）
    # ─────────────────────────────────────────────────────────────────

    async def advance_server_last_applied(
        self,
        *,
        room_id: uuid.UUID,
        content_version_id: uuid.UUID,
        application_id: uuid.UUID,
    ) -> CanonicalFenceAdvance:
        """application 成功即**无条件**推进 server last-applied + canonical fence（AC 2.9）。

        「无条件」只修饰 `last_applied_version_id`：服务端已经把 merged 结果落成了
        content version，这个指针必须如实反映它，没有任何「等值」前置条件。是否让
        **编辑器**跟上是另一个决定，见 :meth:`settle_client_baseline`。

        同一次调用里还要把 room 的 `latest_durable_application_id/latest_durable_sequence`
        指向这个 application —— AC 10.11 要求 same-application fold 与 room latest-durable
        application/sequence **在同一 room lock 事务中原子决定**。拆成两个调用点就会出现
        「server 已推进、canonical fence 还指着上一个 application」的中间态，而 Task 27 的
        resolve 正是**先比 canonical application identity、再比 effective sequence**，
        读到那个中间态会把一次合法 resolve 判成 stale。

        `application_id` 是必填参数（而不是可选的「顺便更新」）：可选参数意味着调用方
        可以只推进 server 指针而让 canonical fence 静默落后，那正是上面那个中间态。
        """
        room = await self._repo.lock_room(room_id)
        app = await self._load_application(application_id, room=room)
        room.last_applied_version_id = content_version_id
        advance = await self._advance_canonical_fence_locked(
            room, app, incoming_request_sequence=None
        )
        room.updated_at = _now()
        await self._session.flush()
        return advance

    async def fold_same_application_request(
        self,
        *,
        room_id: uuid.UUID,
        application_id: uuid.UUID,
        request_sequence: int,
    ) -> CanonicalFenceAdvance:
        """同 application key 的**较高** request：只 fold，不 supersede（AC 10.11 / P36）。

        规则（三条都必须同时成立，缺一条就是一个具体的线上故障）：

        1. `effective_request_sequence = GREATEST(existing, incoming)` —— 单调提升，
           `origin_request_sequence` 永不改动（它是 application 的不可变身份成分）；
        2. room 的 canonical fence **仍然指向同一个 application**；
        3. **不得**按 raw sequence 自我 supersede。

        第 3 条不是理论洁癖：resolve 的顺序是「先比 canonical application identity，
        再比 effective sequence」。若较高 raw sequence 触发 `supersede(old=app, new=app)`，
        这个 application 会把自己标成 `superseded`，于是**用户刚提交的 resolve 会被自己
        的 fold 判成 stale**，前端表现为「反复 409、永远保存不上」，而两侧数据都没错。
        `models.assert_supersede` 里禁 self-supersede 的那一条就是这条判据的下半段。
        """
        if not isinstance(request_sequence, int) or isinstance(request_sequence, bool):
            raise CanonicalFenceError(
                f"request_sequence 必须是整数，实得 {request_sequence!r}"
            )
        room = await self._repo.lock_room(room_id)
        app = await self._load_application(application_id, room=room)
        advance = await self._advance_canonical_fence_locked(
            room, app, incoming_request_sequence=request_sequence
        )
        room.updated_at = _now()
        await self._session.flush()
        return advance

    async def _advance_canonical_fence_locked(
        self,
        room: WorkpaperOoRoom,
        app: WorkpaperContentApplication,
        *,
        incoming_request_sequence: int | None,
    ) -> CanonicalFenceAdvance:
        """room lock 内的 fence 推进（唯一实现；两个公开方法都走它）。

        room 侧那三行算术（canonical application 指针、`latest_durable_sequence`、
        `latest_request_sequence` 追平）**委派**给 `repo.advance_room_durable_fence()`
        而不是在这里再写一遍：两份实现必然漂移，而 room fence 只认仓储那一份。
        本方法只承担 repository 刻意不做的**策略判定** —— fold 多少、能不能 fold。
        """
        previous_effective = int(app.effective_request_sequence)
        folded = previous_effective
        if incoming_request_sequence is not None:
            folded = fold_effective_sequence(previous_effective, incoming_request_sequence)
            if folded != previous_effective:
                app.effective_request_sequence = folded
        # 🔴 self-supersede 的显式拒绝点。`fold_effective_sequence` 只保证「不回退」，
        # 它不知道调用方接下来会不会拿这个更高的 sequence 去 supersede 同一个
        # application；这里在 fence 推进的同一处把它拒掉，因为只有这里同时看得见
        # 「canonical fence 指向谁」与「被 fold 的是谁」。
        if app.superseded_by_application_id is not None and (
            app.superseded_by_application_id == app.id
        ):
            raise CanonicalFenceError(
                f"application {app.id} 自我 supersede —— 同 canonical application 的更高 "
                "request 只 fold，不得 supersede 自己（Property 36）"
            )
        canonical_unchanged = room.latest_durable_application_id == app.id
        await self._repo.advance_room_durable_fence(
            room=room, application_id=app.id, effective_request_sequence=folded
        )
        return CanonicalFenceAdvance(
            room_id=room.id,
            application_id=app.id,
            server_last_applied_version_id=room.last_applied_version_id,
            latest_durable_application_id=room.latest_durable_application_id or app.id,
            latest_durable_sequence=int(room.latest_durable_sequence),
            effective_request_sequence=int(app.effective_request_sequence),
            origin_request_sequence=int(app.origin_request_sequence),
            folded_from_sequence=(
                previous_effective if folded != previous_effective else None
            ),
            canonical_application_unchanged=canonical_unchanged,
        )

    async def _load_application(
        self, application_id: uuid.UUID, *, room: WorkpaperOoRoom
    ) -> WorkpaperContentApplication:
        """取 application 并校验它属于**本 room**。

        跨 room 的 application 被拿来推 fence，等价于「用别的文档的 durable 事实给本
        房间放行」。

        🔴 **这里刻意没有第二道 `app.generation == room.generation` 检查**，因为它是
        provably dead code：V151 把三样东西都锁成 immutable —— room 的 `generation`
        （`wpsync_check_room_immutable`）、application 的 `room_id` 与 `generation`
        （`wpsync_check_application_immutable`）。而 application 的 generation 是
        `correlate_durable_incoming` 在 room row lock 内从 `req.generation`（= 该 room
        当时的 generation）复制来的。三条合起来 ⇒ `app.room_id == room.id` 成立时
        `app.generation == room.generation` 必然成立。

        加了那道检查的实际后果不是「更安全」而是**更不安全**：它永远不可能被触发，于是
        「删掉它」这件事在变异检验里判 GREEN（首轮 M64 实测如此），下一个人会以为守卫
        有缺陷而去放宽判据。DB 侧那条不变量由
        `test_application_room_and_generation_are_db_immutable` 正面钉住 —— 哪天它被解锁，
        那条守卫打红，这道检查就必须补回来。
        """
        app = (
            await self._session.execute(
                sa.select(WorkpaperContentApplication)
                .where(WorkpaperContentApplication.id == application_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if app is None:
            raise CanonicalFenceError(f"application 不存在: {application_id}")
        if app.room_id != room.id:
            raise CanonicalFenceError(
                f"application {application_id} 属于 room {app.room_id}，不是 {room.id}"
            )
        return app

    async def settle_client_baseline(
        self,
        *,
        room_id: uuid.UUID,
        merged_projection_sha256: str,
        incoming_projection_sha256: str,
        applied_content_version_id: uuid.UUID,
        applied_representation_id: uuid.UUID,
        bundle: FrozenBundleIdentity,
    ) -> BaselineSettlement:
        """只有 merged 与 incoming **等值**才推进 client-confirmed（AC 2.9 / 4.11）。

        不等值时：room 落 `refresh_required`（记 reason），拒绝下一次 request，等
        supersede/reopen 后由新 generation 的 descriptor confirmation 重建基线。
        这条门防的是「live OO 拿旧 incoming 把服务器合并值回退掉」。
        """
        if not is_digest(merged_projection_sha256) or not is_digest(
            incoming_projection_sha256
        ):
            raise RoomPolicyError(
                "merged/incoming projection sha256 必须是非空非全零 digest —— "
                "缺一侧时不得默认「等值」"
            )
        room = await self._repo.lock_room(room_id)
        if merged_projection_sha256.strip() != incoming_projection_sha256.strip():
            await self._mark_refresh_required_locked(
                room, reason="merged_projection_differs_from_incoming"
            )
            return BaselineSettlement(
                client_baseline_advanced=False,
                refresh_required=True,
                reason="merged_projection_differs_from_incoming",
            )
        room.client_confirmed_base_version_id = applied_content_version_id
        room.client_confirmed_representation_id = applied_representation_id
        room.client_confirmed_definition_bundle_id = bundle.definition_bundle_id
        room.client_confirmed_definition_bundle_sha256 = bundle.definition_bundle_sha256
        room.client_confirmed_projection_sha256 = merged_projection_sha256.strip()
        room.updated_at = _now()
        await self._session.flush()
        return BaselineSettlement(
            client_baseline_advanced=True,
            refresh_required=False,
            reason="merged_equals_incoming",
        )

    async def mark_refresh_required(
        self, *, room_id: uuid.UUID, reason: str
    ) -> WorkpaperOoRoom:
        """显式把 room 置 refresh-required（供 coordinator 在其他失败分支调用）。"""
        room = await self._repo.lock_room(room_id)
        await self._mark_refresh_required_locked(room, reason=reason)
        return room

    # ─────────────────────────────────────────────────────────────────
    # 3.5 撤销与 generation 旋转（Property 63）
    # ─────────────────────────────────────────────────────────────────

    async def revoke_participant(
        self,
        *,
        room_id: uuid.UUID,
        participant_id: uuid.UUID,
        oo_drop_confirmed: bool,
    ) -> RevokeOutcome:
        """撤销一个 participant，并按 Task 4 裁决决定是否旋转 generation。

        裁决从契约读（`multi_user_semantics.revocation.decision`），不在这里写死分支。
        实证结论是 OO 的 `c=drop` 只证明「会话被逐出、后续写入被阻断」，**不证明**
        「已合入内容被移除」⇒ 所以即便 drop 成功，只要该 participant 是 **写** 会话，
        仍必须提升 write fence 并旋转 generation；`oo_drop_confirmed` 只决定要不要
        额外记录取证时间戳，不放宽 fence。

        只读（view）participant 撤销不污染内容，故不旋转 generation。
        """
        policy = revocation_policy()
        room = await self._repo.lock_room(room_id)
        participant = await self._load_participant(participant_id, room_id=room_id)

        assert_transition("participant", participant.state, ParticipantState.revoked)
        participant.state = ParticipantState.revoked.value
        participant.revoked_at = _now()
        if oo_drop_confirmed:
            participant.oo_drop_confirmed_at = _now()
        participant.updated_at = _now()
        await self._session.flush()

        was_writer = ParticipantMode(participant.mode) is ParticipantMode.edit
        if not was_writer:
            return RevokeOutcome(
                participant_id=participant_id,
                write_fence_epoch=int(room.write_fence_epoch),
                generation_rotated=False,
                cancelled_request_ids=(),
                decision="view_participant_no_fence_change",
            )
        if not policy.requires_generation_rotation:  # pragma: no cover - 契约已 fail closed
            raise RoomPolicyError(
                f"撤销裁决 {policy.decision!r} 不是 write_fence_plus_generation_rotation"
            )

        cancelled = await self._cancel_outstanding_requests_locked(room)
        room.write_fence_epoch = int(room.write_fence_epoch) + 1
        await self._mark_refresh_required_locked(
            room, reason="writer_revoked_generation_superseded"
        )
        logger.warning(
            "room %s: writer participant %s 被撤销 ⇒ fence→%s、取消 %d 个 outstanding "
            "request、generation %s 待 supersede（OO drop 取证=%s，但 drop 不证明内容已移除）",
            room_id,
            participant_id,
            room.write_fence_epoch,
            len(cancelled),
            room.generation,
            oo_drop_confirmed,
        )
        return RevokeOutcome(
            participant_id=participant_id,
            write_fence_epoch=int(room.write_fence_epoch),
            generation_rotated=True,
            cancelled_request_ids=cancelled,
            decision=policy.decision,
        )

    async def supersede_room(
        self, *, room_id: uuid.UUID, reason: str
    ) -> WorkpaperOoRoom:
        """把 room 落 `superseded` 终态（新 generation 由 :meth:`open_room` 建）。

        `ROOM_EDGES` 允许 `opening/active/close_barrier/closing/refresh_required/
        recovery_required → superseded`，所以这里不需要「先绕道 refresh_required」的
        补偿逻辑；不合法的起点（已 `superseded`/`closed`）由 `assert_transition` 拒绝。
        """
        room = await self._repo.lock_room(room_id)
        assert_transition("room", room.state, RoomState.superseded)
        room.state = RoomState.superseded.value
        room.superseded_at = _now()
        room.refresh_reason = reason
        room.updated_at = _now()
        await self._session.flush()
        return room

    # ─────────────────────────────────────────────────────────────────
    # 3.6 内部
    # ─────────────────────────────────────────────────────────────────

    async def _load_participant(
        self, participant_id: uuid.UUID, *, room_id: uuid.UUID
    ) -> WorkpaperOoParticipant:
        participant = (
            await self._session.execute(
                sa.select(WorkpaperOoParticipant)
                .where(WorkpaperOoParticipant.id == participant_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if participant is None:
            raise ParticipantNotWritableError(f"participant 不存在: {participant_id}")
        if participant.room_id != room_id:
            # 跨 room 使用同一 participant id：与「不存在」同样处理，不泄露对象归属。
            raise ParticipantNotWritableError(f"participant 不存在: {participant_id}")
        return participant

    def _assert_participant_lease_live(
        self, participant: WorkpaperOoParticipant
    ) -> None:
        if participant.revoked_at is not None:
            raise ParticipantNotWritableError(
                f"participant 已于 {participant.revoked_at.isoformat()} 被撤销"
            )
        if participant.left_at is not None:
            raise ParticipantNotWritableError("participant 已离开 room")
        if participant.expires_at is not None and participant.expires_at <= _now():
            raise ParticipantNotWritableError(
                f"participant lease 已过期于 {participant.expires_at.isoformat()}"
            )

    def _assert_room_accepts_new_editor(self, room: WorkpaperOoRoom) -> None:
        """close barrier 之后不得再有新 editor 加入该 generation（AC 4.10）。"""
        state = RoomState(room.state)
        if state not in {RoomState.opening, RoomState.active}:
            raise RoomNotWritableError(
                f"room state={state.value} 不再接受新 editor 加入"
                "（close barrier 冻结后必须等新 generation）"
            )
        if room.close_leader_intent_id is not None or int(room.close_barrier_epoch) > 0:
            raise RoomNotWritableError(
                "room 已进入 close barrier —— 该 generation 不再接受新 editor"
            )
        if room.refresh_required_at is not None:
            raise RoomNotWritableError(
                f"room 处于 refresh-required（reason={room.refresh_reason!r}）"
            )

    async def _mark_refresh_required_locked(
        self, room: WorkpaperOoRoom, *, reason: str
    ) -> None:
        if not reason or not reason.strip():
            raise RoomPolicyError("refresh-required 必须带可诊断 reason")
        if room.refresh_required_at is None:
            assert_transition("room", room.state, RoomState.refresh_required)
            room.state = RoomState.refresh_required.value
            room.refresh_required_at = _now()
        room.refresh_reason = reason.strip()[:60]
        room.updated_at = _now()
        await self._session.flush()

    async def _cancel_outstanding_requests_locked(
        self, room: WorkpaperOoRoom
    ) -> tuple[uuid.UUID, ...]:
        """把该 generation 内尚未终结的 request 落 `superseded`（AC 4.7）。"""
        # 未终结 = 还可能收到 callback 的四态。`correlated` 也在内：incoming 已 durable
        # 但内容尚未应用，撤销后必须阻止它继续走 apply（AC 4.7），保留 incoming 供 recovery。
        open_states = [
            RequestState.frozen.value,
            RequestState.pending.value,
            RequestState.accepted.value,
            RequestState.correlated.value,
        ]
        rows = (
            (
                await self._session.execute(
                    sa.select(WorkpaperForcesaveRequest)
                    .where(
                        WorkpaperForcesaveRequest.room_id == room.id,
                        WorkpaperForcesaveRequest.generation == room.generation,
                        WorkpaperForcesaveRequest.state.in_(open_states),
                    )
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )
        cancelled: list[uuid.UUID] = []
        for row in rows:
            assert_transition("request", row.state, RequestState.superseded)
            row.state = RequestState.superseded.value
            cancelled.append(row.id)
        if cancelled:
            await self._session.flush()
        return tuple(cancelled)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 纯投影 helper（无 IO，便于单测）
# ═══════════════════════════════════════════════════════════════════════════


def _baselines_of(room: WorkpaperOoRoom) -> RoomBaselines:
    return RoomBaselines(
        opened_base_version_id=room.opened_base_version_id,
        server_last_applied_version_id=room.last_applied_version_id,
        client_confirmed_base_version_id=room.client_confirmed_base_version_id,
        client_confirmed_representation_id=room.client_confirmed_representation_id,
        client_confirmed_projection_sha256=room.client_confirmed_projection_sha256,
        client_confirmed_definition_bundle_id=room.client_confirmed_definition_bundle_id,
        client_confirmed_definition_bundle_sha256=(
            room.client_confirmed_definition_bundle_sha256
        ),
    )


def _bundle_identity_of(
    bundle: WorkpaperSyncDefinitionBundle, *, authority_model_type: str
) -> FrozenBundleIdentity:
    slots = {
        BundleSlot.template: BundleSlotSpec(
            BundleSlot.template,
            bundle.template_slot_type,
            bundle.template_slot_ref,
            bundle.template_slot_digest,
        ),
        BundleSlot.instrumentation: BundleSlotSpec(
            BundleSlot.instrumentation,
            bundle.instrumentation_slot_type,
            bundle.instrumentation_slot_ref,
            bundle.instrumentation_slot_digest,
        ),
        BundleSlot.contract: BundleSlotSpec(
            BundleSlot.contract,
            bundle.contract_slot_type,
            bundle.contract_slot_ref,
            bundle.contract_slot_digest,
        ),
    }
    authority = AuthorityModel(authority_model_type)
    return FrozenBundleIdentity(
        definition_bundle_id=bundle.id,
        definition_bundle_sha256=bundle.canonical_payload_sha256,
        authority_model=authority,
        authority_model_definition_id=bundle.authority_model_definition_id,
        authority_model_definition_sha256=bundle.authority_model_definition_sha256,
        slots=slots,
        slots_digest=compute_bundle_slots_digest(
            authority_model=authority,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256,
            slots=slots,
        ),
    )


__all__ = [
    "DOC_KEY_PREFIX",
    "RoomPolicyError",
    "DocKeyError",
    "RoomNotWritableError",
    "ParticipantNotWritableError",
    "DescriptorNotConfirmedError",
    "WriteFenceStaleError",
    "BundleIdentityDriftError",
    "ClientBaselineMissingError",
    "RepresentationNotPublishedError",
    "BundleAliasDriftError",
    "RouteCredentialError",
    "ContributorSnapshotError",
    "CanonicalFenceError",
    "revocation_policy",
    "derive_doc_key",
    "parse_doc_key",
    "doc_key_matches",
    "RouteCredential",
    "mint_route_credential",
    "assert_route_credential",
    "RoomFactsProbe",
    "probe_room_facts",
    "RoomScope",
    "FrozenBundleIdentity",
    "RoomBaselines",
    "RequestFreeze",
    "BaselineSettlement",
    "RevokeOutcome",
    "ContributorRecord",
    "ContributorSnapshot",
    "CanonicalFenceAdvance",
    "RoomService",
]
