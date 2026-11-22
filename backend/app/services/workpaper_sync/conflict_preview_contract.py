"""冲突预览用哪份契约：**默认读冻结的那份**，显式传入的仍走原判据。

═══ 为什么单独一个模块（spec frozen-contract-read-path 任务 5 / ADR-FC-003） ═══

`ConflictResolutionService.preview()` 原本要求调用方**传** contract，而 router 只能从
registry 现取 ⇒ 只要契约改过一次，历史 operation 的预览就永久
`frozen_contract_digest_drift`（实测遗留 operation `11809f53…` 冻结 `75fca57d…`，
该 entry 当前 `645e0500…`，24 条冲突永远看不到）。

本模块把「该用哪份契约」收成一处：

| 调用方 | 结果 |
| --- | --- |
| 省略 `contract`（**新默认**） | 按 bundle 的 `contract_slot_ref` 读**冻结**契约 |
| 显式传入且与 slot digest 相符 | 用传入的那份（`contract_source="explicit"`） |
| 显式传入但 digest 不符 | **仍抛** `FrozenContractDriftError`（判据一个字不改） |

🔴 为什么不直接改 `preview()` 内部：`conflict_resolution.py` 已到行数门 +5% 阈值只剩
**18 行**余量（1711 / 1729），塞不下错误映射与 source 判定。抽成模块是行数门的正解，
不是「为了好看」。

🔴 `contract_source` **只作标注**：它不得被用来门控任何按钮可用性（前端守卫钉住）。
把「历史契约」当成「不能操作」会让本 spec 的整个目的（让历史 operation 能继续）落空。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from app.services.workpaper_sync.contracts import SyncContract
from app.services.workpaper_sync.frozen_contract_reader import (
    FrozenContractReader,
    FrozenContractReaderError,
    FrozenContractSnapshot,
)
from app.services.workpaper_sync.models import BundleSlot

__all__ = [
    "ContractSource",
    "PreviewContractResolution",
    "resolve_preview_contract",
    "PreviewContractUnavailableError",
    "FROZEN_CONTRACT_SOURCE_LABEL",
    "EXPLICIT_CONTRACT_SOURCE_LABEL",
]

ContractSource = Literal["frozen", "explicit"]

#: 前端展示用的固定取值（**不是**自由文本：DTO 要按这两个字面量判分支）
FROZEN_CONTRACT_SOURCE_LABEL: ContractSource = "frozen"
EXPLICIT_CONTRACT_SOURCE_LABEL: ContractSource = "explicit"


class PreviewContractUnavailableError(FrozenContractReaderError):
    """冻结契约读不回来 —— 预览无法按该 operation 的历史视角渲染。

    🔴 它**不是** `frozen_contract_digest_drift`：那是「调用方传错了契约」，
    这是「该 operation 冻结的那份契约本身读不回来」（数据链 / 存储层）。
    两者的处置完全不同，混成一个码会让运维查错方向。
    """

    error_code = "frozen_contract_unavailable_for_preview"


@dataclass(frozen=True)
class PreviewContractResolution:
    """预览实际用的契约 + 它从哪来（响应里如实标注，R2.3）。"""

    contract: SyncContract
    source: ContractSource
    #: bundle 上冻结的 contract slot digest（两种 source 都填）
    frozen_digest: str
    #: 冻结契约的 definition 行 id（`source="frozen"` 时有值）
    definition_id: Any = None
    #: 显式传入时调用方给的那份的 digest（`source="explicit"` 时有值）
    provided_digest: str | None = None

    @property
    def is_frozen(self) -> bool:
        return self.source == FROZEN_CONTRACT_SOURCE_LABEL


async def resolve_preview_contract(
    *,
    session: Any,
    artifacts: Any,
    bundle: Any,
    provided: SyncContract | None,
    assert_matches_bundle: Any,
    where: str,
) -> PreviewContractResolution:
    """决定预览该用哪份契约。

    Args:
        bundle: :class:`~app.services.workpaper_sync.resolution.DefinitionBundleSnapshot`
        provided: 调用方显式传入的契约；`None` ⇒ 读冻结那份
        assert_matches_bundle: 原判据
            :func:`~app.services.workpaper_sync.conflict_resolution.assert_frozen_contract_matches_bundle`
            以参数注入而不是 import —— 它是**判据**，由调用方（同模块）提供，
            这样「判据一个字不改」在代码形态上也成立。
        where: 判据失败时的定位串

    Raises:
        FrozenContractDriftError: 显式传入的契约与冻结 slot digest 不符（原判据原样抛）。
        PreviewContractUnavailableError: 该 operation 冻结的契约读不回来。
    """
    slot = bundle.slots[BundleSlot.contract]
    frozen_digest = str(slot.slot_digest)

    if provided is not None:
        # 🔴 显式传入这条路**保持原样**：不读冻结契约、不改变任何行为。
        assert_matches_bundle(
            contract=provided, slot_digest=frozen_digest, where=where
        )
        return PreviewContractResolution(
            contract=provided,
            source=EXPLICIT_CONTRACT_SOURCE_LABEL,
            frozen_digest=frozen_digest,
            provided_digest=provided.canonical_sha256,
        )

    # 省略 ⇒ 读冻结那份（本 spec 新增的唯一行为）
    reader = FrozenContractReader(session=session, artifacts=artifacts)
    try:
        snapshot: FrozenContractSnapshot = await reader.read(bundle=bundle)
    except FrozenContractReaderError as exc:
        raise PreviewContractUnavailableError(
            f"该 operation 冻结的契约读不回来（{exc.error_code}）：{exc}",
            diagnostics={
                **dict(exc.diagnostics),
                "bundle_id": str(getattr(bundle, "bundle_id", "")),
                "where": where,
            },
        ) from exc

    return PreviewContractResolution(
        contract=snapshot.contract,
        source=FROZEN_CONTRACT_SOURCE_LABEL,
        frozen_digest=frozen_digest,
        definition_id=snapshot.definition_id,
    )


def contract_source_fields(resolution: PreviewContractResolution) -> Mapping[str, Any]:
    """响应里 `contract_source` 那几个字段的单一来源（`ConflictPreview.as_dict` 用它）。

    独立成函数而不是在 `as_dict` 里内联：两处（preview / 未来其他读侧入口）
    必须给出**同一组**键名与语义，抄一份就会漂。
    """
    payload: dict[str, Any] = {
        "contract_source": resolution.source,
        "frozen_digest": resolution.frozen_digest,
    }
    if resolution.provided_digest is not None:
        payload["provided_digest"] = resolution.provided_digest
    if resolution.definition_id is not None:
        payload["contract_definition_id"] = str(resolution.definition_id)
    return payload
