# -*- coding: utf-8 -*-
"""custom / user-upload（OOXML 本体权威）lane 的**可枚举登记**与 per-lane 消费门（Task 65）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 65
Requirements: 2.11, 3.9, 5.5, 6.19, 12.6, 12.10
Properties: **P50 / P64 / P69**

═══ 一、为什么必须有这一层（三条缺口都是实测的）═══

Task 19 已经把 custom / 上传 / WOPI / F2 四条 OOXML-本体-权威写入迁进
`ContentMutationService.commit(...)`，`OpaqueAuthorityProvisioner` 也能幂等拿到一个
三 slot 全 typed-null-marker 的 approved bundle。但 Task 65 正文要求的三件事当时都不
成立：

1. **「每类 custom/opaque entry」这个分母不存在。**
   `manifest` 的 `capability` 是封闭四值（`bidirectional / single_html /
   single_onlyoffice / unreachable`），**没有** `custom`；custom/opaque 的 `entry_id`
   由 :func:`~app.services.workpaper_sync.writer_migration.opaque_entry_id` 在**运行时**
   合成，manifest 里零登记。于是「每类都发布了 bundle 吗」这个问题在代码里无从提问 ——
   既没有清册，也没有任何判据能发现「新加了一条 opaque writer 但没人给它发 bundle」。

2. **approved bundle 是写路径**顺手**给自己发的。**
   `OpaqueAuthorityProvisioner.ensure()` 里是 `publish_bundle(..., approved=True)`，
   而它的唯一调用者是 `AuthoritativeContentWriter.commit_bytes()` —— 也就是**业务内容
   写入的那一次**。AC 6.19 要求的是「先发布 approved authority-model definition 与
   non-null approved bundle」，写路径自己 approve 自己要用的东西等于自己给自己发证：
   任何时刻库里都恰好有它需要的 bundle，于是「必须先发布」这条承诺没有任何可 falsify
   的判据。

3. **`authority_model` 有默认值。**
   `commit_bytes(..., authority_model=AuthorityModel.custom_authoritative_ooxml)` ——
   user-upload 的 opaque 文件漏传即**静默**落成 custom。四层静态检查（Volar / vitest /
   `get_diagnostics` / HEAD-swap）都查不出，只有事后翻 evidence 的 authority model
   分桶才会发现分桶失真。

本模块补的正是这三格：一张**与源码双向锁死**的 lane 登记表（§2）、一道**只查不发布**
的消费门（§4），以及把 authority model 的选择从「调用方随口传」改成「由 lane 登记
决定」（:func:`authority_model_for_lane`）。

═══ 二、判据不抄 Excel/Word gate 的任何一条 ═══

`excel_entry_gate` 的判据是 sheet/cell/identity-inventory/动态列；`word_entry_gate`
的判据是 tagged-SDT tag 集合与 row_uuid 实例数。**opaque lane 一条都用不上**：它没有
per-entry contract（AC 6.19 明令不得强行 instrumentation），因此没有受管 sheet、没有
字段、没有 tag。照抄过来会得到一堆恒真判据（重言式）—— 那是本 spec 反复实测的假绿第
②源。

opaque lane 真正可判的只有五件事，本模块就只判这五件：

======  ====================================================================
判据     形态
======  ====================================================================
OG-1    lane 已登记，且登记的 writer 在源码里真实存在（不是一个死名字）
OG-2    lane 的 authority model ∈ :data:`OPAQUE_AUTHORITY_MODELS`
        （`projection_contract` 走 `projection_provisioning`，两条通道不得混用）
OG-3    库里**已存在**该 authority model 的 approved authority-model definition
        与 approved bundle（**只查，不发布**）
OG-4    bundle 三个 typed slot 全部是 registry 版本化 typed null marker，
        且 digest 与 registry 真实值逐项等值（definition child 一律拒绝）
OG-5    frozen `(bundle_id, bundle_sha256)` 与 DB row 一致
        （历史读取不得按当前 alias 顶替）
======  ====================================================================

形态判据本身全部**委托单点**：marker registry 用
`definitions.TYPED_NULL_MARKERS`，slot 形态用 `models.validate_bundle_slot`，digest
形态用 `models.is_digest`，bundle 可用性用 `repository.assert_bundle_usable`。复制一份
的后果不是「更安全」，而是任一侧被短路都不改变行为 ⇒ 变异检验判 GREEN。

═══ 三、登记表的约束力来自**反向**判据 ═══

一张手写清单本身不构成分母 —— 漏一条就是漏一条，没人知道。所以本模块的登记表配了一
条反向判据 :func:`assert_lane_registry_covers_source`：用 **AST** 扫描全部生产源码里
`opaque_entry_id(...)` 的调用点，要求

* 每个调用点都恰好命中一条登记（未登记的新 lane ⇒ 打红）；
* 每条登记都命中至少一个调用点（登记了却没有调用点 ⇒ 打红，与 manifest 生成器的
  `stale overlay` 判据同款）；
* 调用点实际传的 `wp_code=` 实参**形态**与登记的 :class:`EntryIdSource` 一致
  （把 `wp_code=ctx.wp_code` 改成 `wp_code=None` ⇒ 打红）。

第三条不是形式主义：`wp_code` 传 `None` 时 `opaque_entry_id` 退回 `str(wp_id)`，于是
**同一个 wp 的同一份权威文件在两条 lane 下会落到两个不同 entry_id**，各自有独立
entry pointer 与 representation generation，rollback 与 evidence 查不到对方的行。这个
分叉今天真实存在（custom 传 `ctx.wp_code`，upload/WOPI 传 `None`），登记表把它记成
**已知且有意**的事实并附理由，而不是让它继续隐身。

═══ 四、本模块**不**做的事（避免制造第三条写入路径）═══

* 不发布任何 definition / bundle —— 发布只由 `OpaqueAuthorityProvisioner.provision()`
  经唯一宿主脚本 `backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py`
  执行（与 Task 76 的 `fix_task76_provision_projection_definitions.py` 同款）；
* 不插 `working_paper_content_representation` 行 —— opaque lane 的 representation 由
  `ContentMutationService.commit(...)` 在业务事务内产出；
* 不 commit、不开事务 —— 与 `WorkpaperSyncRepository` 只 flush 不 commit 的约定一致；
* 不碰 room / forcesave / application 的任何写入面 —— 见 §五。

═══ 五、诚实记账：custom lane 的 room / durable ack 仍未接入 ═══

Task 65 正文第一条要求 custom「进入统一 room/durable ack/content version/
representation/evidence」。当前真实状态：

============================  ==================================================
设施                          custom lane 状态
============================  ==================================================
content version               ✅ `commit_bytes` → `ContentMutationService.commit`
published representation      ✅ 同上（同一业务事务）
evidence（authority 分桶）     ✅ `evidence.SUBSTITUTING_AUTHORITY_MODELS` +
                              本模块的 :func:`authority_model_for_lane` 供给
统一 room / participant       ❌ `/custom-cells` 是同步 HTTP 写，不是 OO room 事件
durable forcesave ack         ❌ 同上：没有 forcesave request，也就没有 durable ack
content application           ❌ 无 request ⇒ 无 application
============================  ==================================================

后三格**不是本任务可以单方面接完的**：custom 的 OO 侧走 `wp_onlyoffice_router` 的四条
resolver 行（`get_sheet_onlyoffice_config` / `get_sheet_wopi_contents` /
`get_whole_excel_grid` / `post_sheet_onlyoffice_callback`），它们在 Task 12 的 resolver
矩阵里是 `status=deferred`，裁决归属（`adjudication_owner_task`）写的是 **Task 71** 的
`multi_resolver` 门。在那条门放行之前，把 custom 接到 room/application 上等于绕过一个
正在把守的发布门。

因此本模块对这三格的态度是**登记为未接入并指名归属**（:data:`CUSTOM_LANE_ROOM_DEBT`），
不写任何「已接入」的文案，也不提供绕过入口。AC 5.5 的 application identity 判据
（same incoming + 不同 bundle/authority model ⇒ 不同 key，永不折叠）在**协议层**是可
独立验证的（`models.compute_application_key` 是纯函数），由 Task 65 的守卫在真库上按
opaque lane 的 bundle/authority digest 实测；它不需要、也不假装需要真实 OO room。
"""

from __future__ import annotations

import ast
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_sync_models import (
    WorkpaperSyncDefinitionArtifact,
    WorkpaperSyncDefinitionBundle,
)
from app.services.workpaper_sync.definitions import TYPED_NULL_MARKERS, marker_for
from app.services.workpaper_sync.models import (
    AuthorityModel,
    BundleSlot,
    BundleSlotSpec,
    DefinitionState,
    SyncDomainError,
    is_digest,
    validate_bundle_slot,
)

__all__ = [
    # 异常
    "OpaqueEntryGateError",
    "OpaqueLaneNotRegisteredError",
    "OpaqueLaneWriterMissingError",
    "OpaqueLaneRegistryDriftError",
    "OpaqueAuthorityModelNotOpaqueError",
    "OpaqueBundleNotProvisionedError",
    "OpaqueAuthorityDefinitionStateError",
    "OpaqueBundleStateError",
    "OpaqueSlotNotTypedNullMarkerError",
    "OpaqueBundleDigestMismatchError",
    # 登记与常量
    "EntryIdSource",
    "OpaqueLane",
    "OPAQUE_AUTHORITY_LANES",
    "assert_lane_self_consistent",
    "assert_slots_are_typed_null_markers",
    "CUSTOM_LANE_ROOM_DEBT",
    "PROVISION_HOST_SCRIPT",
    "PRODUCTION_SOURCE_ROOTS",
    # 登记查询
    "lane_ids",
    "lane_for",
    "authority_model_for_lane",
    "lanes_for_authority_model",
    # 反向完整性
    "OpaqueEntryIdCallSite",
    "discover_opaque_entry_id_call_sites",
    "assert_lane_registry_covers_source",
    "assert_lane_writers_exist",
    "CommitBytesLaneArgument",
    "lane_id_argument_of",
    "discover_commit_bytes_lane_arguments",
    "assert_commit_bytes_lane_arguments_match_registry",
    "ENTRY_ID_NAMESPACE_SPLIT_NOTE",
    # 门
    "ResolvedOpaqueBundle",
    "OpaqueEntryGate",
]


_BACKEND: Final[Path] = Path(__file__).resolve().parents[3]

#: 发布 opaque authority definition/bundle 的**唯一**宿主脚本。写成常量而不是把路径
#: 散在错误消息里：fail-closed 的错误必须能直接告诉运维「跑哪一条命令」，而这个路径
#: 同时被守卫用来断言脚本真实存在（登记一个不存在的脚本等于给了一句假指引）。
PROVISION_HOST_SCRIPT: Final[str] = (
    "backend/scripts/fix/fix_task65_provision_opaque_authority_bundles.py"
)

#: AST 反向扫描的生产源码根。刻意**不含** `backend/tests` 与 `backend/scripts`：
#: 测试与脚本里出现 `opaque_entry_id(...)` 是正常的（它们在构造夹具），把它们计入分母
#: 会让登记表被迫登记测试夹具，而那不是运行态 lane。
#:
#: 🔴 同时刻意**不收窄**到某几个业务目录：`_is_production_source` 一旦按目录排除，
#: 「新加一条 opaque writer」只要放在被排除的目录里就能绕过分母判据（Task 74 正文把
#: 「缩小分母」列为禁止的四件事之一，同一形态）。
PRODUCTION_SOURCE_ROOTS: Final[tuple[str, ...]] = ("app",)


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常：每条拒绝一个类型
# ═══════════════════════════════════════════════════════════════════════════
#
# 与 `excel_entry_gate` 的六类 FS-* 同一理由（那里连续三次实测到同一个坑）：两条判据
# 共用一个异常类型时，把靠前那条短路掉会被靠后那条抛出**同样的**类型遮蔽 ⇒ 只断言
# 类型的守卫判 GREEN，于是靠前那条实际上没有任何单点可锁。


class OpaqueEntryGateError(SyncDomainError):
    """Task 65 的域基类。"""

    error_code = "opaque_entry_gate_failed"


class OpaqueLaneNotRegisteredError(OpaqueEntryGateError):
    """lane_id 不在 :data:`OPAQUE_AUTHORITY_LANES` 里。"""

    error_code = "opaque_lane_not_registered"


class OpaqueLaneWriterMissingError(OpaqueEntryGateError):
    """登记的 `writer_ref` 在源码里不存在（登记表指向了一个死名字）。"""

    error_code = "opaque_lane_writer_missing"


class OpaqueLaneRegistryDriftError(OpaqueEntryGateError):
    """登记表与源码 `opaque_entry_id(...)` 调用点集合不一致。

    三种形态共用本类型是**有意**的：它们都是同一条判据（「登记表 ≡ 源码调用点」）的
    不同方向，且消息里逐项列出差集。与上面那条「每条拒绝一个类型」不冲突 ——
    这里不存在「前一条被短路后被后一条遮蔽」的结构：三个方向在同一个函数体里各自算出
    差集后**一起**报告，删掉任一方向会让对应差集从消息里消失，守卫按消息里的差集断言。
    """

    error_code = "opaque_lane_registry_drift"


class OpaqueAuthorityModelNotOpaqueError(OpaqueEntryGateError):
    """authority model 不是 OOXML 本体权威形态（`projection_contract` 走另一条通道）。"""

    error_code = "opaque_lane_authority_model_not_opaque"


class OpaqueBundleNotProvisionedError(OpaqueEntryGateError):
    """库里没有该 authority model 的 approved definition + approved bundle。

    这是 AC 6.19 「必须**先**发布」的可 falsify 形态：消费路径拿不到发布能力，缺供给
    时只能 fail closed 并指向 :data:`PROVISION_HOST_SCRIPT`。
    """

    error_code = "opaque_authority_bundle_not_provisioned"


class OpaqueAuthorityDefinitionStateError(OpaqueEntryGateError):
    """authority-model definition 存在但 kind/state/枚举不合法。"""

    error_code = "opaque_authority_definition_state_invalid"


class OpaqueBundleStateError(OpaqueEntryGateError):
    """bundle 存在但不是 approved。"""

    error_code = "opaque_bundle_state_invalid"


class OpaqueSlotNotTypedNullMarkerError(OpaqueEntryGateError):
    """bundle 的 typed slot 不是 registry 版本化 typed null marker。

    opaque lane 的三个 slot **只能**是 marker：AC 6.19 原文「在 instrumentation/
    contract slot 使用明确版本化 typed null marker」。slot 是 `definition` 时说明有人
    把 projection 侧的 child 塞进了 opaque bundle（或反过来复用了 projection bundle），
    两条通道的 slot 规则相反，混用即 AC 2.3 失守。
    """

    error_code = "opaque_bundle_slot_not_typed_null_marker"


class OpaqueBundleDigestMismatchError(OpaqueEntryGateError):
    """frozen `(bundle_id, bundle_sha256)` 与 DB row 不符 —— 禁止按当前 alias 顶替。"""

    error_code = "opaque_bundle_digest_mismatch"


# ═══════════════════════════════════════════════════════════════════════════
# 2. lane 登记表（可枚举分母）
# ═══════════════════════════════════════════════════════════════════════════


class EntryIdSource(str, Enum):
    """`opaque_entry_id(wp_code=...)` 实参的**形态**分类。

    它描述的是 entry_id 命名空间的口径，不是一个自由标签：

    * :attr:`wp_code` —— 传业务码（`ctx.wp_code`），entry_id = `opaque-{wp_code}`；
    * :attr:`wp_code_with_sheet` —— 传 `f"{wp_code or wp_id}#{sheet}"`，一个底稿的
      多份文档各占一个 entry；
    * :attr:`wp_id` —— 传 `None`，`opaque_entry_id` 退回 `str(wp_id)`。
    """

    wp_code = "wp_code"
    wp_code_with_sheet = "wp_code_with_sheet"
    wp_id = "wp_id"


@dataclass(frozen=True)
class OpaqueLane:
    """一条 OOXML-本体-权威写入 lane 的登记。

    `lane_id` 是稳定 key（守卫、evidence、错误消息共用），不是展示名。
    """

    lane_id: str
    authority_model: AuthorityModel
    entry_id_source: EntryIdSource
    writer_module: str
    writer_qualname: str
    document_type: str
    has_html_counterpart: bool
    instrumentation_required: bool
    delivered_by_task: str
    adjudication_owner_task: str
    reason: str

    @property
    def writer_ref(self) -> str:
        return f"{self.writer_module}::{self.writer_qualname}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "authority_model": self.authority_model.value,
            "entry_id_source": self.entry_id_source.value,
            "writer_ref": self.writer_ref,
            "document_type": self.document_type,
            "has_html_counterpart": self.has_html_counterpart,
            "instrumentation_required": self.instrumentation_required,
            "delivered_by_task": self.delivered_by_task,
            "adjudication_owner_task": self.adjudication_owner_task,
        }


#: **全部** OOXML-本体-权威写入 lane。分母由 :func:`assert_lane_registry_covers_source`
#: 与源码 `opaque_entry_id(...)` 调用点双向锁死 —— 这张表不是「记得写就写」的清单。
#:
#: `authority_model` 的取值判据来自 design §「authority model 的选择由有没有 HTML 对端
#: 决定，不由调用方随口传」：`custom_authoritative_ooxml` 是平台生成的 xlsx（有 HTML
#: 投影视图但投影只读），`opaque_single_onlyoffice` 是没有 HTML 对端的纯 OO/上传入口。
#: 故本表把 `has_html_counterpart` 与 `authority_model` 一起登记，并由
#: :func:`_assert_lane_self_consistent` 交叉锁死：改了一个不改另一个即打红。
#:
#: `instrumentation_required` 恒为 False 且被守卫锁死：AC 6.19 明令「custom/user-uploaded
#: xlsx 在无显式 contract 时不得被强行 instrumentation」。它是一列**判据**而不是一列
#: 配置 —— 允许它为 True 就等于给自己开了一条「给用户原文件注入 `_GT_SYNC` 隐藏表」的
#: 后门（sidecar 不得改变原文件语义）。
OPAQUE_AUTHORITY_LANES: Final[tuple[OpaqueLane, ...]] = (
    OpaqueLane(
        lane_id="custom_cells",
        authority_model=AuthorityModel.custom_authoritative_ooxml,
        entry_id_source=EntryIdSource.wp_code,
        writer_module="app.routers.custom_workpaper_cells",
        writer_qualname="update_custom_cells",
        document_type="xlsx",
        has_html_counterpart=True,
        instrumentation_required=False,
        delivered_by_task="19",
        adjudication_owner_task="65",
        reason=(
            "custom 底稿（`create-custom` 建的自建底稿 / 有自定义程序实例的底稿）的 HTML "
            "侧单元格写入。权威是 xlsx 本体：端点先 `write_cells_to_xlsx` 落盘、再 "
            "`refresh_custom_projection` 从 xlsx 重投影、最后把**xlsx 本体字节**交 "
            "`commit_bytes`。`has_html_counterpart=True` 是它与另四条 lane 的实质差别 —— "
            "`parsed_data.html_data[wp_code]` 是这份 xlsx 的只读投影，所以 authority model "
            "取 `custom_authoritative_ooxml` 而不是 `opaque_single_onlyoffice`。"
            "🔴 room / durable ack / content application 三格未接入，归属见 "
            "`CUSTOM_LANE_ROOM_DEBT`。"
        ),
    ),
    OpaqueLane(
        lane_id="offline_upload",
        authority_model=AuthorityModel.opaque_single_onlyoffice,
        entry_id_source=EntryIdSource.wp_id,
        writer_module="app.services.wp_download_service",
        writer_qualname="WpUploadService.upload_file",
        document_type="dynamic",
        has_html_counterpart=False,
        instrumentation_required=False,
        delivered_by_task="19",
        adjudication_owner_task="65",
        reason=(
            "离线上传回传（下载 → 本机 Excel 编辑 → 回传覆盖）。用户上传的原始文件没有"
            "平台模板、没有 per-entry contract，也**不得**被 instrumentation（AC 6.19）："
            "`ExcelInstrumentationUpgrader.instrument_source_bytes` 的 `_assert_within_templates` "
            "只接受 `backend/wp_templates/` 下的权威模板，本 lane 一次都不调它。"
            "`document_type='dynamic'` 是实情：`commit_bytes(document_type=...)` 取的是"
            "上传文件的后缀（`file_path.suffix`），xlsx/xlsm/docx 都可能。"
            "`entry_id_source=wp_id` ⇒ 与 `custom_cells` 的 `wp_code` 口径**不同**，见 "
            "`ENTRY_ID_NAMESPACE_SPLIT_NOTE`。"
        ),
    ),
    OpaqueLane(
        lane_id="wopi_put_file",
        authority_model=AuthorityModel.opaque_single_onlyoffice,
        entry_id_source=EntryIdSource.wp_id,
        writer_module="app.services.wopi_service",
        writer_qualname="WOPIHostService.put_file",
        document_type="dynamic",
        has_html_counterpart=False,
        instrumentation_required=False,
        delivered_by_task="19",
        adjudication_owner_task="65",
        reason=(
            "WOPI PutFile（OnlyOffice / Office 客户端经 WOPI 协议保存）。与 "
            "`offline_upload` 同为「没有 HTML 对端的 OOXML 本体」，故共用 "
            "`opaque_single_onlyoffice`；两者是**两条** lane 而不是一条，因为 writer、"
            "冲突语义（PutFile 抛 PermissionError vs 上传返 status=conflict）与审计留痕"
            "顺序都不同，合并登记会让其中一条的实参形态漂移无法被 AST 判据发现。"
        ),
    ),
    OpaqueLane(
        lane_id="f2_stocktake_plan",
        authority_model=AuthorityModel.opaque_single_onlyoffice,
        entry_id_source=EntryIdSource.wp_code_with_sheet,
        writer_module="app.routers.wp_render_strategies._f2_stocktake_plan_sync",
        writer_qualname="_save_fields",
        document_type="docx",
        has_html_counterpart=False,
        instrumentation_required=False,
        delivered_by_task="19",
        adjudication_owner_task="60",
        reason=(
            "F2-22 存货监盘计划的 OO→HTML 回写。**登记在此不代表 Task 65 接管它** —— "
            "它的 per-entry Word 契约、authority model 发布记录与 published "
            "representation finalize 归 Task 60/61/77。登记的理由是**分母完整性**："
            "它真实调用 `opaque_entry_id(...)` + `commit_bytes(authority_model="
            "opaque_single_onlyoffice)`，不登记就会让 "
            "`assert_lane_registry_covers_source` 把它报成「未登记的新 lane」，而那条"
            "反向判据正是本模块登记表的全部约束力来源。"
            "`entry_id_source=wp_code_with_sheet`：F2-22 与 F2-23 是同一底稿的两份不同"
            "文档，entry_id 必须带 sheet code，否则互相顶掉 representation generation。"
        ),
    ),
    OpaqueLane(
        lane_id="f2_stocktake_summary",
        authority_model=AuthorityModel.opaque_single_onlyoffice,
        entry_id_source=EntryIdSource.wp_code_with_sheet,
        writer_module="app.routers.wp_render_strategies._f2_stocktake_summary_sync",
        writer_qualname="_save_fields",
        document_type="docx",
        has_html_counterpart=False,
        instrumentation_required=False,
        delivered_by_task="19",
        adjudication_owner_task="60",
        reason=(
            "F2-23 存货监盘汇总的 OO→HTML 回写。与 `f2_stocktake_plan` 同理由登记、"
            "同归属（Task 60/61/77），本模块只提供它的 authority model 真源与消费门。"
        ),
    ),
)


#: custom lane 尚未接入 room / durable ack / content application 的**归属登记**。
#:
#: 写成结构化常量而不是散在注释里：Task 67 的 structural pre-reconcile 要「如实报告未
#: 裁决、假双向、未验收」，而 Task 70 要按 profile 推导 required scenario。两者都需要
#: 一个机器可读的「这三格没接、归谁」而不是一句散文。
CUSTOM_LANE_ROOM_DEBT: Final[Mapping[str, Any]] = {
    "lane_id": "custom_cells",
    "missing_facilities": ("unified_room", "durable_forcesave_ack", "content_application"),
    "blocking_reason": (
        "custom 的 OO 侧走 `wp_onlyoffice_router` 的四条 resolver 行"
        "（get_sheet_onlyoffice_config / get_sheet_wopi_contents / get_whole_excel_grid / "
        "post_sheet_onlyoffice_callback），它们在 Task 12 的 resolver 矩阵里是 "
        "`status=deferred`；HTML 侧 `/custom-cells` 则是同步 HTTP 写，根本不产生 "
        "forcesave request，因此也没有 durable ack 与 application 可言。"
    ),
    "adjudication_owner_task": "71",
    "verification_status": "UNVERIFIABLE",
    "what_is_verifiable_now": (
        "AC 5.5 的 application identity 判据（same incoming + 不同 bundle/authority model "
        "⇒ 不同 application_key，永不折叠）是 `models.compute_application_key` 的纯函数"
        "性质，可在真库上按 opaque lane 的真实 bundle/authority digest 独立验证，"
        "不依赖真实 OO room。"
    ),
}


#: entry_id 命名空间分叉的**已知且有意**登记。
#:
#: 同一个 wp 的同一份权威文件，经 `custom_cells` 落 `opaque-{wp_code}`、经
#: `offline_upload` / `wopi_put_file` 落 `opaque-{wp_id}`。这**不是**可以顺手统一的
#: 事情：entry_id 是 `.versions/{wp_id}/representations/{entry_id}/` 的目录名，也是
#: `working_paper_sync_scope_index` 的 scope 分量，改口径等于给已发布的
#: representation 换 scope。真库实测 `working_paper_content_representation` 与
#: `working_paper_content_version` 当前**均为 0 行**，所以今天改是零迁移成本的；但
#: 「该不该合并」本身是业务裁决（custom 底稿的 wp_code 是用户自定义的、可改名，而
#: wp_id 不可改名 —— 用 wp_code 当 scope 的代价是改名即换 scope），归 Task 67 的
#: structural pre-reconcile 统一裁决。此处只把事实与代价记清楚，不擅自合并。
ENTRY_ID_NAMESPACE_SPLIT_NOTE: Final[Mapping[str, Any]] = {
    "lanes_using_wp_code": ("custom_cells",),
    "lanes_using_wp_code_with_sheet": ("f2_stocktake_plan", "f2_stocktake_summary"),
    "lanes_using_wp_id": ("offline_upload", "wopi_put_file"),
    "consequence": (
        "同一 wp 的同一份权威文件在两种口径下落到两个 entry_id，各自有独立 entry "
        "pointer / representation generation；rollback 与 evidence 查不到对方的行。"
    ),
    "measured_migration_cost_at_task65": {
        "working_paper_content_version_rows": 0,
        "working_paper_content_representation_rows": 0,
        "working_paper_content_application_rows": 0,
    },
    "adjudication_owner_task": "67",
}


_LANES_BY_ID: Final[Mapping[str, OpaqueLane]] = {
    lane.lane_id: lane for lane in OPAQUE_AUTHORITY_LANES
}


def assert_lane_self_consistent(lanes: Sequence[OpaqueLane] | None = None) -> None:
    """登记表的自洽判据（import 期对 :data:`OPAQUE_AUTHORITY_LANES` 即跑，坏表不许被加载）。

    四条：lane_id 唯一、`instrumentation_required` 恒 False、authority model 落在
    :data:`OPAQUE_AUTHORITY_MODELS`、`has_html_counterpart` 与 authority model 交叉一致。

    🔴 第四条是把 design §「authority model 的选择由有没有 HTML 对端决定」变成可执行
    判据。没有它时 `has_html_counterpart` 就只是一列注释，改了不会有任何后果。

    `lanes` 可注入是为了让上面四条能被**逐条**独立 falsify：不可注入时守卫只能断言
    「当前这张表通过」，而那对「判据是否真的存在」毫无信息量 —— 把函数体整个删掉，
    守卫照样绿（本 spec 记录的假绿第②源）。
    """
    from app.services.workpaper_sync.writer_migration import OPAQUE_AUTHORITY_MODELS

    checked = OPAQUE_AUTHORITY_LANES if lanes is None else tuple(lanes)
    seen: set[str] = set()
    for lane in checked:
        if lane.lane_id in seen:
            raise OpaqueLaneRegistryDriftError(f"lane_id 重复: {lane.lane_id!r}")
        seen.add(lane.lane_id)
        if lane.instrumentation_required:
            raise OpaqueLaneRegistryDriftError(
                f"lane {lane.lane_id}: `instrumentation_required=True` 违反 AC 6.19 —— "
                "无显式 contract 的 custom/user-upload 文件不得被强行 instrumentation，"
                "sidecar 不得改变原文件语义"
            )
        if lane.authority_model not in OPAQUE_AUTHORITY_MODELS:
            raise OpaqueAuthorityModelNotOpaqueError(
                f"lane {lane.lane_id}: authority model={lane.authority_model.value} 不是 "
                f"OOXML 本体权威形态（封闭集 "
                f"{sorted(m.value for m in OPAQUE_AUTHORITY_MODELS)}）—— "
                "`projection_contract` 必须走 `projection_provisioning` 的全量协议"
            )
        expected = (
            AuthorityModel.custom_authoritative_ooxml
            if lane.has_html_counterpart
            else AuthorityModel.opaque_single_onlyoffice
        )
        if lane.authority_model is not expected:
            raise OpaqueLaneRegistryDriftError(
                f"lane {lane.lane_id}: has_html_counterpart="
                f"{lane.has_html_counterpart} 与 authority model="
                f"{lane.authority_model.value} 矛盾（期望 {expected.value}）—— "
                "authority model 的选择由「有没有 HTML 对端」决定，两列必须同改"
            )


assert_lane_self_consistent()


def lane_ids() -> tuple[str, ...]:
    return tuple(lane.lane_id for lane in OPAQUE_AUTHORITY_LANES)


def lane_for(lane_id: str) -> OpaqueLane:
    """按 lane_id 取登记；未登记即 :class:`OpaqueLaneNotRegisteredError`。"""
    lane = _LANES_BY_ID.get(str(lane_id).strip())
    if lane is None:
        raise OpaqueLaneNotRegisteredError(
            f"lane_id {lane_id!r} 未登记（已登记 {sorted(_LANES_BY_ID)}）—— "
            "新增一条 OOXML 本体权威写入必须先进 `OPAQUE_AUTHORITY_LANES`，"
            "否则它的 authority model 就没有真源，evidence 的分桶会失真"
        )
    return lane


def authority_model_for_lane(lane_id: str) -> AuthorityModel:
    """lane 的 authority model 真源。

    这是本模块存在的第三个理由：改造前 authority model 由**调用方**传，
    `commit_bytes` 还给了默认值 `custom_authoritative_ooxml` ⇒ user-upload 的 opaque
    文件漏传即静默落成 custom，四层静态检查都查不出。
    """
    return lane_for(lane_id).authority_model


def lanes_for_authority_model(model: AuthorityModel | str) -> tuple[OpaqueLane, ...]:
    am = model if isinstance(model, AuthorityModel) else AuthorityModel(str(model))
    return tuple(lane for lane in OPAQUE_AUTHORITY_LANES if lane.authority_model is am)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 反向完整性：AST 扫描源码调用点 ↔ 登记表
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class OpaqueEntryIdCallSite:
    """一处生产代码里的 `opaque_entry_id(...)` 调用。"""

    module: str
    relative_path: str
    line: int
    entry_id_source: EntryIdSource
    enclosing_qualname: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "relative_path": self.relative_path,
            "line": self.line,
            "entry_id_source": self.entry_id_source.value,
            "enclosing_qualname": self.enclosing_qualname,
        }


def _classify_wp_code_argument(node: ast.AST | None) -> EntryIdSource:
    """把 `wp_code=` 实参的 AST 节点分类成 :class:`EntryIdSource`。

    三类判据都落在**节点形态**上，不看变量名：

    * `Constant(None)` ⇒ :attr:`EntryIdSource.wp_id`（`opaque_entry_id` 对 None 退回 wp_id）；
    * `JoinedStr` 且字面量片段里含 `#` ⇒ :attr:`EntryIdSource.wp_code_with_sheet`；
    * 其余（`Name` / `Attribute` / 普通字符串）⇒ :attr:`EntryIdSource.wp_code`。

    🔴 关键字缺失（位置参数）不在此处兜底 —— `opaque_entry_id` 的签名是
    keyword-only（`def opaque_entry_id(*, wp_code, wp_id)`），位置传参在运行期就是
    `TypeError`。分类函数遇到拿不到 `wp_code=` 的调用直接抛，而不是猜一个默认值：
    猜默认值会让「把 `wp_code=ctx.wp_code` 删掉」这种改动被静默归入某一类。
    """
    if node is None:
        raise OpaqueLaneRegistryDriftError(
            "`opaque_entry_id(...)` 调用缺 `wp_code=` 关键字实参 —— 它是 keyword-only "
            "参数，缺失即运行期 TypeError；分类函数不为它编造默认口径"
        )
    if isinstance(node, ast.Constant) and node.value is None:
        return EntryIdSource.wp_id
    if isinstance(node, ast.JoinedStr):
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str) and "#" in part.value:
                return EntryIdSource.wp_code_with_sheet
        return EntryIdSource.wp_code
    return EntryIdSource.wp_code


def _module_name(path: Path) -> str:
    rel = path.relative_to(_BACKEND).with_suffix("")
    return ".".join(rel.parts)


def _enclosing_qualname(tree: ast.Module, target: ast.AST) -> str:
    """target 所在的最内层 def/class 链（`Class.method` 形态）。

    用于把调用点与登记的 `writer_qualname` 对上。做成「逐层记录祖先」而不是「找最近的
    FunctionDef」：`WOPIHostService.put_file` 这种嵌在类里的方法必须带类名，否则登记的
    `WOPIHostService.put_file` 与扫出来的 `put_file` 永远对不上，判据就只能退化成
    「模块级匹配」。
    """
    chain: list[str] = []

    def walk(node: ast.AST, stack: list[str]) -> bool:
        for child in ast.iter_child_nodes(node):
            new_stack = stack
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                new_stack = [*stack, child.name]
            if child is target:
                chain.extend(new_stack)
                return True
            if walk(child, new_stack):
                return True
        return False

    walk(tree, [])
    return ".".join(chain)


def _iter_production_sources() -> list[Path]:
    out: list[Path] = []
    for root in PRODUCTION_SOURCE_ROOTS:
        base = _BACKEND / root
        if not base.is_dir():
            raise OpaqueLaneRegistryDriftError(
                f"生产源码根不存在: {base} —— `PRODUCTION_SOURCE_ROOTS` 与仓库结构脱钩，"
                "分母会静默变空（缩小分母是禁止形态）"
            )
        out.extend(sorted(base.rglob("*.py")))
    return out


def discover_opaque_entry_id_call_sites() -> tuple[OpaqueEntryIdCallSite, ...]:
    """AST 扫描全部生产源码里的 `opaque_entry_id(...)` **调用点**。

    刻意用 AST 而不是 grep：grep 会把 `def opaque_entry_id(`、`import opaque_entry_id`、
    docstring 与注释里的字样一起数进来，于是「删掉一个真实调用点、在注释里留个名字」
    也能让分母看起来没变（假绿第②源）。
    """
    sites: list[OpaqueEntryIdCallSite] = []
    for path in _iter_production_sources():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - 环境异常
            raise OpaqueLaneRegistryDriftError(f"读取源码失败 {path}: {exc}") from exc
        if "opaque_entry_id" not in source:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover - 语法错在 CI 早就红了
            raise OpaqueLaneRegistryDriftError(f"解析源码失败 {path}: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name != "opaque_entry_id":
                continue
            wp_code_arg = next(
                (kw.value for kw in node.keywords if kw.arg == "wp_code"), None
            )
            sites.append(
                OpaqueEntryIdCallSite(
                    module=_module_name(path),
                    relative_path=path.relative_to(_BACKEND.parent).as_posix(),
                    line=node.lineno,
                    entry_id_source=_classify_wp_code_argument(wp_code_arg),
                    enclosing_qualname=_enclosing_qualname(tree, node),
                )
            )
    return tuple(sites)


def assert_lane_registry_covers_source(
    sites: Sequence[OpaqueEntryIdCallSite] | None = None,
) -> Mapping[str, tuple[str, ...]]:
    """登记表 ≡ 源码调用点（三个方向一起报告）。

    返回按 lane_id 归组的调用点 `module:line` 列表（供 evidence / 诊断脚本使用）。

    三个方向：

    1. **未登记的调用点** —— 新加一条 opaque writer 却没进登记表；
    2. **无调用点的登记** —— 登记了一条已经消失的 lane（与 manifest 生成器的
       `stale overlay` 判据同款）；
    3. **实参形态漂移** —— 调用点传的 `wp_code=` 形态与登记的 `entry_id_source` 不同，
       即 entry_id 命名空间被悄悄换了。

    🔴 三个方向必须**一起**算完再报告，不能算到第一个就 raise：只报第一个时，守卫为了
    覆盖第三个方向必须先把前两个方向构造成通过，而那需要改生产源码 —— 于是第三条判据
    在测试里根本无法被独立 falsify。
    """
    discovered = tuple(sites) if sites is not None else discover_opaque_entry_id_call_sites()

    by_lane: dict[str, list[str]] = {lane.lane_id: [] for lane in OPAQUE_AUTHORITY_LANES}
    unregistered: list[str] = []
    drifted: list[str] = []

    for site in discovered:
        # 定义处自身不是调用点，`discover_*` 只收 `ast.Call`，故此处无需再排除；
        # 但同一模块里可能有多个 lane（当前没有），所以匹配用 (module, qualname) 双键。
        matched = [
            lane
            for lane in OPAQUE_AUTHORITY_LANES
            if lane.writer_module == site.module
            and _qualname_matches(lane.writer_qualname, site.enclosing_qualname)
        ]
        if len(matched) != 1:
            unregistered.append(
                f"{site.relative_path}:{site.line} "
                f"[{site.module}::{site.enclosing_qualname or '<module>'}] "
                f"命中登记 {len(matched)} 条"
            )
            continue
        lane = matched[0]
        by_lane[lane.lane_id].append(f"{site.module}:{site.line}")
        if site.entry_id_source is not lane.entry_id_source:
            drifted.append(
                f"{site.relative_path}:{site.line} lane={lane.lane_id} "
                f"登记 entry_id_source={lane.entry_id_source.value} "
                f"实测={site.entry_id_source.value}"
            )

    stale = sorted(lane_id for lane_id, hits in by_lane.items() if not hits)

    if unregistered or stale or drifted:
        raise OpaqueLaneRegistryDriftError(
            "opaque lane 登记表与源码 `opaque_entry_id(...)` 调用点不一致：\n"
            f"  未登记的调用点 ({len(unregistered)}): {unregistered}\n"
            f"  无调用点的登记 ({len(stale)}): {stale}\n"
            f"  实参形态漂移 ({len(drifted)}): {drifted}\n"
            "登记表是 custom/opaque 的**唯一**可枚举分母：漏登记等于让一条写入路径没有 "
            "authority model 真源，形态漂移等于悄悄换了 entry_id 命名空间"
        )
    return {lane_id: tuple(hits) for lane_id, hits in by_lane.items()}


@dataclass(frozen=True)
class CommitBytesLaneArgument:
    """一处 `commit_bytes(..., lane_id=...)` 调用里的 lane_id 字面量。"""

    module: str
    relative_path: str
    line: int
    lane_id: str
    enclosing_qualname: str


def lane_id_argument_of(call: ast.Call, *, where: str) -> str:
    """从一次 `commit_bytes(...)` 调用的 AST 节点里取出 `lane_id` 字面量。

    两条拒绝：

    * 缺 `lane_id=` —— 它是必填 keyword，authority model 由它单向决定；
    * 不是**字符串字面量** —— `lane_id=some_var` 让「这条写入路径用的是哪个 authority
      model」变成运行期才知道的事，本模块与 Task 67 的 structural pre-reconcile 的静态
      判据当场退化成猜测。

    🔴 抽成独立函数是为了让这两条能被**行为**判据 falsify。首版它们内联在
    :func:`discover_commit_bytes_lane_arguments` 的循环里，于是守卫只能断言
    「源码里有『不是字符串字面量』这句话」—— 一条 grep 式判据。变异检验实测：把那个
    `if` 改成 `if False:` 后守卫**照样绿**（M06 判 GREEN），因为被改的是控制流而判据看的
    是字符串。现在守卫直接喂合成 AST 节点，短路任一条即打红。
    """
    arg = next((kw.value for kw in call.keywords if kw.arg == "lane_id"), None)
    if arg is None:
        raise OpaqueLaneRegistryDriftError(
            f"{where} `commit_bytes(...)` 缺 `lane_id=` 实参 —— 它是必填 keyword，"
            "authority model 由它单向决定"
        )
    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
        raise OpaqueLaneRegistryDriftError(
            f"{where} `commit_bytes(lane_id=...)` 不是字符串字面量（实得 "
            f"{type(arg).__name__}）—— 运行期变量会让 authority model 的静态判据"
            "退化成猜测"
        )
    return arg.value


def discover_commit_bytes_lane_arguments() -> tuple[CommitBytesLaneArgument, ...]:
    """AST 扫描生产源码里 `commit_bytes(..., lane_id=<字面量>)` 的实参。

    形态判据委托 :func:`lane_id_argument_of`（单点，可独立 falsify）；本函数只负责
    遍历、归属与排除转发模块。
    """
    out: list[CommitBytesLaneArgument] = []
    for path in _iter_production_sources():
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - 环境异常
            raise OpaqueLaneRegistryDriftError(f"读取源码失败 {path}: {exc}") from exc
        if "commit_bytes" not in source:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:  # pragma: no cover
            raise OpaqueLaneRegistryDriftError(f"解析源码失败 {path}: {exc}") from exc
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name != "commit_bytes":
                continue
            module = _module_name(path)
            # 定义处自身（`async def commit_bytes` 内部对 `self._mutation.commit` 的调用
            # 不叫 commit_bytes；而 `commit_restore` 里对 `self.commit_bytes(...)` 的调用
            # 是真实调用点）。装配面所在模块按 lane 登记不到，故显式排除本模块与
            # writer_migration 的转发调用。
            if module in _COMMIT_BYTES_FORWARDING_MODULES:
                continue
            relative = path.relative_to(_BACKEND.parent).as_posix()
            lane_id = lane_id_argument_of(node, where=f"{relative}:{node.lineno}")
            out.append(
                CommitBytesLaneArgument(
                    module=module,
                    relative_path=relative,
                    line=node.lineno,
                    lane_id=lane_id,
                    enclosing_qualname=_enclosing_qualname(tree, node),
                )
            )
    return tuple(out)


#: `commit_bytes` 的装配面/转发处所在模块（它们不是 lane，不参与 lane_id 比对）。
_COMMIT_BYTES_FORWARDING_MODULES: Final[frozenset[str]] = frozenset(
    {
        "app.services.workpaper_sync.writer_migration",
        "app.services.workpaper_sync.opaque_entry_gate",
    }
)


def assert_commit_bytes_lane_arguments_match_registry(
    arguments: Sequence[CommitBytesLaneArgument] | None = None,
) -> Mapping[str, str]:
    """每处 `commit_bytes(lane_id=...)` 的字面量必须等于它所在 writer 的登记 lane_id。

    与 :func:`assert_lane_registry_covers_source` 是**两条**判据：那条比「调用点集合」，
    本条比「传进去的那个字符串」。合成一条之后，把 `custom_workpaper_cells` 的
    `lane_id="custom_cells"` 改成 `lane_id="wopi_put_file"` 仍会通过 —— 而那一改
    直接把 custom 底稿的 authority model 从 `custom_authoritative_ooxml` 换成
    `opaque_single_onlyoffice`，evidence 的分桶与 `application_key` 一起失真。
    """
    mismatched: list[str] = []
    unknown: list[str] = []
    mapping: dict[str, str] = {}
    discovered = (
        tuple(arguments) if arguments is not None else discover_commit_bytes_lane_arguments()
    )
    for arg in discovered:
        matched = [
            lane
            for lane in OPAQUE_AUTHORITY_LANES
            if lane.writer_module == arg.module
            and _qualname_matches(lane.writer_qualname, arg.enclosing_qualname)
        ]
        if len(matched) != 1:
            unknown.append(
                f"{arg.relative_path}:{arg.line} [{arg.module}::"
                f"{arg.enclosing_qualname or '<module>'}] 命中登记 {len(matched)} 条"
            )
            continue
        lane = matched[0]
        mapping[f"{arg.module}:{arg.line}"] = arg.lane_id
        if arg.lane_id != lane.lane_id:
            mismatched.append(
                f"{arg.relative_path}:{arg.line} 实参 lane_id={arg.lane_id!r}，"
                f"该 writer 登记为 {lane.lane_id!r}"
            )
    if mismatched or unknown:
        raise OpaqueLaneRegistryDriftError(
            "`commit_bytes(lane_id=...)` 实参与 lane 登记不一致：\n"
            f"  lane_id 不符 ({len(mismatched)}): {mismatched}\n"
            f"  无法归属的调用点 ({len(unknown)}): {unknown}\n"
            "lane_id 单向决定 authority model —— 传错即静默换掉这条写入路径的权威模型"
        )
    return mapping


def _qualname_matches(registered: str, discovered: str) -> bool:
    """登记的 qualname 与 AST 扫出的 def 链是否指同一个 writer。

    允许 AST 链**更深**（真实调用点常在内层 helper 或 `try` 块里的嵌套函数中），但必须
    以登记的链为前缀；不允许更浅（更浅意味着登记指向了一个不存在的内层函数）。
    """
    if registered == discovered:
        return True
    return discovered.startswith(f"{registered}.")


def assert_lane_writers_exist() -> tuple[str, ...]:
    """OG-1：每条登记的 `writer_ref` 在源码里真实存在（import + 逐段 getattr）。

    与 :func:`assert_lane_registry_covers_source` 是**两条**判据：那条管「调用点集合与
    登记集合是否等价」（纯 AST，不 import），本条管「登记的名字是不是一个能真正取到的
    对象」。合成一条之后，把 `writer_qualname` 写成一个不存在的方法名仍会通过 —— 因为
    AST 侧的 `_qualname_matches` 只比字符串。
    """
    import importlib

    verified: list[str] = []
    for lane in OPAQUE_AUTHORITY_LANES:
        try:
            module = importlib.import_module(lane.writer_module)
        except ImportError as exc:
            raise OpaqueLaneWriterMissingError(
                f"lane {lane.lane_id}: 无法 import `{lane.writer_module}`: {exc}"
            ) from exc
        target: Any = module
        for part in lane.writer_qualname.split("."):
            target = getattr(target, part, None)
            if target is None:
                raise OpaqueLaneWriterMissingError(
                    f"lane {lane.lane_id}: `{lane.writer_ref}` 取不到 —— 登记表指向了一个"
                    "死名字，它的 authority model 真源实际上没有消费方"
                )
        if not callable(target):
            raise OpaqueLaneWriterMissingError(
                f"lane {lane.lane_id}: `{lane.writer_ref}` 不可调用（实得 "
                f"{type(target).__name__}）"
            )
        verified.append(lane.writer_ref)
    return tuple(verified)


# ═══════════════════════════════════════════════════════════════════════════
# 4. 消费门：只查已发布的 approved bundle
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResolvedOpaqueBundle:
    """一条 lane 解析到的 approved bundle 身份（全部来自 DB 列，无一项现算）。"""

    lane_id: str
    authority_model: AuthorityModel
    authority_model_definition_id: uuid.UUID
    authority_model_definition_sha256: str
    bundle_id: uuid.UUID
    bundle_sha256: str
    slots: Mapping[BundleSlot, BundleSlotSpec]

    @property
    def typed_slot_inventory(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            (s.value, self.slots[s].slot_type, self.slots[s].slot_digest) for s in BundleSlot
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "lane_id": self.lane_id,
            "authority_model": self.authority_model.value,
            "authority_model_definition_id": str(self.authority_model_definition_id),
            "authority_model_definition_sha256": self.authority_model_definition_sha256,
            "definition_bundle_id": str(self.bundle_id),
            "definition_bundle_sha256": self.bundle_sha256,
            "typed_slot_inventory": [list(item) for item in self.typed_slot_inventory],
        }


def _slot_map_of(bundle: WorkpaperSyncDefinitionBundle) -> dict[BundleSlot, BundleSlotSpec]:
    return {
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


def assert_slots_are_typed_null_markers(
    slots: Mapping[BundleSlot, BundleSlotSpec], *, where: str
) -> None:
    """OG-4：三个 slot 全为 registry 版本化 typed null marker，逐项 digest 等值。

    形态判据（空串 / 全零 / 非 64 位小写 hex / `marker:{type}` 一致性 / 跨 slot marker）
    **委托** `models.validate_bundle_slot`；本函数只加两条它拿不到的：

    * slot 是 `definition` 时拒绝（opaque lane 不该有 definition child）——
      `validate_bundle_slot` 对 `definition` 是**放行**的，它不知道调用方处在哪条通道；
    * marker digest 必须等于 `definitions.TYPED_NULL_MARKERS` 里的**真实** digest ——
      registry 是 marker 的唯一来源，V151 的 seed 与它逐字节同源。
    """
    for slot in BundleSlot:
        spec = slots.get(slot)
        if spec is None:
            raise OpaqueSlotNotTypedNullMarkerError(
                f"{where}: 缺 {slot.value} slot —— 三个 typed slot 必须全出现"
            )
        validate_bundle_slot(spec)
        if spec.is_definition:
            raise OpaqueSlotNotTypedNullMarkerError(
                f"{where}: {slot.value} slot 是 `definition`（ref={spec.slot_ref!r}）—— "
                "OOXML 本体权威 lane 的三个 slot 只能是 registry 版本化 typed null "
                "marker（AC 6.19）。出现 definition child 说明这是一个 "
                "`projection_contract` bundle 被误用，或有人往 opaque bundle 里塞了 "
                "per-entry contract；两条通道的 slot 规则相反，混用即 AC 2.3 失守"
            )
        marker = TYPED_NULL_MARKERS.get(spec.slot_type)
        if marker is None:
            raise OpaqueSlotNotTypedNullMarkerError(
                f"{where}: {slot.value} slot type={spec.slot_type!r} 不在 marker registry "
                f"（已登记 {sorted(TYPED_NULL_MARKERS)}）"
            )
        expected = marker_for(slot, version=marker.version)
        if spec.slot_digest != expected.slot_digest:
            raise OpaqueSlotNotTypedNullMarkerError(
                f"{where}: {slot.value} marker digest 与 registry 真实值不一致："
                f"实得 {spec.slot_digest!r}，registry {expected.slot_digest!r} —— "
                "禁止伪造 typed null digest"
            )


class OpaqueEntryGate:
    """opaque lane 的**消费**门：只解析已发布的 approved bundle，永不发布。

    ═══ 为什么门里没有任何发布能力 ═══

    构造函数只吃 `session`，方法里只有 `select`。这不是自律，而是结构：本类没有
    `DefinitionPublisher`、没有 `CanonicalArtifactRepository`、也没有 repository 的写
    入面，因此「消费路径顺手 approve 自己要用的 bundle」在**装配层**不可表达。守卫据此
    断言（检查本类的 `__init__` 签名与模块 import 图），而不是断言「源码里没出现
    publish 这个词」。

    发布唯一入口是 `OpaqueAuthorityProvisioner.provision()`，唯一宿主是
    :data:`PROVISION_HOST_SCRIPT`。
    """

    def __init__(self, *, session: AsyncSession) -> None:
        self._session = session

    async def resolve_approved_bundle(
        self,
        *,
        lane_id: str,
        frozen_bundle_id: uuid.UUID | None = None,
        frozen_bundle_sha256: str | None = None,
    ) -> ResolvedOpaqueBundle:
        """按 lane 解析 approved authority definition + approved bundle。

        `frozen_*` 两参给出时按 frozen 身份加载并逐项比对（历史读取路径：AC 2.10 禁止
        按当前 alias 重组 bundle）；不给时按 lane 的 authority model 查当前 approved
        bundle（首次消费路径）。两条路都**不发布**。
        """
        lane = lane_for(lane_id)
        if frozen_bundle_id is not None:
            resolved = await self._load_frozen(lane, frozen_bundle_id, frozen_bundle_sha256)
        else:
            resolved = await self._load_current(lane)
        assert_slots_are_typed_null_markers(
            resolved.slots, where=f"lane {lane.lane_id} bundle {resolved.bundle_id}"
        )
        return resolved

    # ─────────────────────────────────────────────────────────────────

    async def _load_current(self, lane: OpaqueLane) -> ResolvedOpaqueBundle:
        """按 authority model 查一个 approved bundle；查不到即 fail closed。

        判据逐项落在**列**上（authority model 枚举 + 两侧 approved + 三个 slot 的 marker
        type/digest 与当前 registry 等值），与
        `OpaqueAuthorityProvisioner._find_approved_bundle` 同一口径 —— 那是**有意**的
        重合：provision 侧决定「发不发」，consume 侧决定「能不能用」，两者必须对同一
        身份达成一致，否则会出现「发布了但用不了」。为避免两份实现漂移，两侧的 slot 期望
        都由 `definitions.marker_slot_spec` 现算，不写死字面量。
        """
        marker_slots = {slot: marker_for(slot) for slot in BundleSlot}
        row = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle, WorkpaperSyncDefinitionArtifact)
                .join(
                    WorkpaperSyncDefinitionArtifact,
                    WorkpaperSyncDefinitionArtifact.id
                    == WorkpaperSyncDefinitionBundle.authority_model_definition_id,
                )
                .where(
                    WorkpaperSyncDefinitionArtifact.authority_model_type
                    == lane.authority_model.value,
                    WorkpaperSyncDefinitionArtifact.state == DefinitionState.approved.value,
                    WorkpaperSyncDefinitionBundle.state == DefinitionState.approved.value,
                    WorkpaperSyncDefinitionBundle.template_slot_type
                    == marker_slots[BundleSlot.template].slot_type,
                    WorkpaperSyncDefinitionBundle.template_slot_digest
                    == marker_slots[BundleSlot.template].slot_digest,
                    WorkpaperSyncDefinitionBundle.instrumentation_slot_type
                    == marker_slots[BundleSlot.instrumentation].slot_type,
                    WorkpaperSyncDefinitionBundle.instrumentation_slot_digest
                    == marker_slots[BundleSlot.instrumentation].slot_digest,
                    WorkpaperSyncDefinitionBundle.contract_slot_type
                    == marker_slots[BundleSlot.contract].slot_type,
                    WorkpaperSyncDefinitionBundle.contract_slot_digest
                    == marker_slots[BundleSlot.contract].slot_digest,
                )
                .order_by(
                    WorkpaperSyncDefinitionBundle.created_at,
                    WorkpaperSyncDefinitionBundle.id,
                )
                .limit(1)
            )
        ).first()
        if row is None:
            raise OpaqueBundleNotProvisionedError(
                f"lane {lane.lane_id}: 库里没有 authority model="
                f"{lane.authority_model.value} 的 approved authority-model definition + "
                "approved bundle（三 slot 全 registry typed null marker）。\n"
                "AC 6.19 要求**先**发布再消费 —— 消费路径不发布任何 definition/bundle。\n"
                f"请先运行：.\\.venv\\Scripts\\python.exe {PROVISION_HOST_SCRIPT} --apply"
            )
        bundle, authority = row
        return self._build(lane, bundle, authority)

    async def _load_frozen(
        self,
        lane: OpaqueLane,
        bundle_id: uuid.UUID,
        bundle_sha256: str | None,
    ) -> ResolvedOpaqueBundle:
        bundle = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionBundle).where(
                    WorkpaperSyncDefinitionBundle.id == bundle_id
                )
            )
        ).scalar_one_or_none()
        if bundle is None:
            raise OpaqueBundleNotProvisionedError(
                f"lane {lane.lane_id}: frozen bundle {bundle_id} 不存在 —— 历史读取只能读"
                "自己 frozen 的 `definition_bundle_id`，不得按当前 alias 顶替"
            )
        if bundle.state != DefinitionState.approved.value:
            raise OpaqueBundleStateError(
                f"lane {lane.lane_id}: bundle {bundle_id} state={bundle.state}，"
                "只有 approved 可用于 room/finalize/consume"
            )
        if bundle_sha256 is not None:
            if not is_digest(bundle_sha256):
                raise OpaqueBundleDigestMismatchError(
                    f"lane {lane.lane_id}: frozen bundle digest 非法（空串/全零/非 64 位"
                    f"小写 hex）: {bundle_sha256!r}"
                )
            if bundle.canonical_payload_sha256.strip() != bundle_sha256.strip():
                raise OpaqueBundleDigestMismatchError(
                    f"lane {lane.lane_id}: frozen bundle digest {bundle_sha256} 与 DB row "
                    f"{bundle.canonical_payload_sha256} 不符 —— 禁止按当前 alias 顶替"
                )
        authority = (
            await self._session.execute(
                sa.select(WorkpaperSyncDefinitionArtifact).where(
                    WorkpaperSyncDefinitionArtifact.id
                    == bundle.authority_model_definition_id
                )
            )
        ).scalar_one_or_none()
        if authority is None:
            raise OpaqueAuthorityDefinitionStateError(
                f"lane {lane.lane_id}: bundle {bundle_id} 的 authority model definition "
                f"{bundle.authority_model_definition_id} 不存在"
            )
        return self._build(lane, bundle, authority)

    def _build(
        self,
        lane: OpaqueLane,
        bundle: WorkpaperSyncDefinitionBundle,
        authority: WorkpaperSyncDefinitionArtifact,
    ) -> ResolvedOpaqueBundle:
        """把两行 DB row 组成快照，并把 authority 侧的三条判据一次算完。"""
        if authority.kind != "authority_model":
            raise OpaqueAuthorityDefinitionStateError(
                f"lane {lane.lane_id}: authority child kind={authority.kind!r}，"
                "必须为 `authority_model`"
            )
        if authority.state != DefinitionState.approved.value:
            raise OpaqueAuthorityDefinitionStateError(
                f"lane {lane.lane_id}: authority-model definition state="
                f"{authority.state!r}，只有 approved 可参与 bundle"
            )
        declared = str(authority.authority_model_type or "")
        if declared != lane.authority_model.value:
            raise OpaqueAuthorityDefinitionStateError(
                f"lane {lane.lane_id}: 登记 authority model={lane.authority_model.value}，"
                f"bundle 的 authority child 实为 {declared!r} —— lane 登记与 bundle 身份"
                "必须双向锁死，否则 evidence 的 authority 分桶会指向另一条通道"
            )
        if authority.sha256.strip() != bundle.authority_model_definition_sha256.strip():
            raise OpaqueAuthorityDefinitionStateError(
                f"lane {lane.lane_id}: bundle 的 authority digest "
                f"{bundle.authority_model_definition_sha256} 与 child 实际 sha256 "
                f"{authority.sha256} 不一致"
            )
        for name, value in (
            ("authority_model_definition_sha256", bundle.authority_model_definition_sha256),
            ("canonical_payload_sha256", bundle.canonical_payload_sha256),
        ):
            if not is_digest(value):
                raise OpaqueBundleDigestMismatchError(
                    f"lane {lane.lane_id}: bundle.{name} 非法（空串/全零/非 64 位小写 "
                    f"hex）: {value!r} —— application key 的入参必须是真实非空 digest"
                )
        return ResolvedOpaqueBundle(
            lane_id=lane.lane_id,
            authority_model=lane.authority_model,
            authority_model_definition_id=authority.id,
            authority_model_definition_sha256=bundle.authority_model_definition_sha256.strip(),
            bundle_id=bundle.id,
            bundle_sha256=bundle.canonical_payload_sha256.strip(),
            slots=_slot_map_of(bundle),
        )
