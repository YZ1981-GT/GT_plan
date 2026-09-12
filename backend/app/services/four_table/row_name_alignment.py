"""名称对齐层 —— 行名 ↔ 账套明细名（aux_name / account_name）的 N:M 可确认映射。

本模块夹在既有「报表行 → 科目码定位」（`select_leaves` / `aggregate_aux_by_name`）
与「账套明细」之间，**只在名称维度**补一层可裁决映射。**不改科目定位真源**：
候选来自已定位科目叶子的账套明细名，不复制 `ReportLineAccountSpec` /
`SemanticAccountSpec` 的定位逻辑（红基线 3）。

四态状态机（`classify`）:

    account 侧候选集 = 该行科目码定位出的叶子 → 其账套明细名集合
      精确同名（归一后）唯一命中          → auto_matched
      归一后多命中 / 相似度命中            → ambiguous（必须人工确认）
      零命中                              → unmatched
      命中来自已落库用户映射且映射未失效   → user_confirmed
      已落库映射目标在当前 active dataset 消失 / 身份不一致 → stale ⇒ unmatched

🔴 名称归一（去空白 / 全半角 / 常见后缀）**仅用于候选生成与匹配判定**，不用于直接
出数；归一后非唯一命中一律 `ambiguous`，不得当精确命中（Requirement 5.2 / Property 1）。

spec: .kiro/specs/formula-row-name-alignment-confirmation/
      Requirements 1.1 / 2.2 / 2.4 / 5.1 / 5.2；Property 1 / 2 / 3 / 6
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from .aux_aggregation import aggregate_aux_by_name
from .leaf_aggregation import LeafRow, filter_by_prefixes, select_leaves, to_leaf_rows

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 版本化的归一 / 相似度参数（写入 evidence，改动即 bump）
# ─────────────────────────────────────────────────────────────────────────────

#: 归一规则版本 —— 任何归一/相似度参数变化必须 bump 并记入 evidence
NORMALIZATION_VERSION = "norm-v1"

#: 相似度算法版本
SIMILARITY_VERSION = "sim-v1"

#: 相似度阈值：>= 视为「相似候选」纳入 ambiguous（不得当精确命中）
SIMILARITY_THRESHOLD = 0.55

#: 候选上限：单行最多返回的候选数（按相似度 / 金额量级排序后截断）
CANDIDATE_LIMIT = 20

#: 归一时剥除的常见机构后缀（仅用于候选匹配，不改展示名）
_COMMON_SUFFIXES = (
    "有限责任公司",
    "有限公司",
    "股份有限公司",
    "分公司",
    "总公司",
    "公司",
)


class CandidateSourceError(Exception):
    """候选取数源（aux / account）发生异常。

    🔴 复盘 #5：不再把取数失败吞成空列表 —— 「真的无候选」与「取数出错」必须可区分，
    否则接线错误（函数签名错/连接失败）会伪装成「本项目无此明细」静默出空。
    调用方（wire / 端点）应据此返回可识别错误码，而非 unmatched。
    """

    def __init__(self, source: str, cause: BaseException):
        self.source = source
        self.cause = cause
        super().__init__(f"候选取数源 {source} 失败: {type(cause).__name__}: {cause}")


class MatchState(str, Enum):
    """行名匹配四态（Requirement 1.1）。"""

    AUTO_MATCHED = "auto_matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"
    USER_CONFIRMED = "user_confirmed"


#: 账套明细来源种类
SOURCE_AUX = "aux_name"
SOURCE_ACCOUNT = "account_name"


@dataclass(frozen=True)
class TargetIdentity:
    """账套明细目标的**稳定身份**（名称仅作展示，不作复用判据）。

    判 stale（Property 2）时按 `dataset_id` / `account_code` / `aux_type` /
    `dimension_key` 比对；仅名称存在不能解除 stale。
    """

    source_kind: str  # SOURCE_AUX | SOURCE_ACCOUNT
    account_code: str  # 科目原始码（aux 侧为定位前缀，account 侧为叶子码）
    aux_type: str | None  # aux 侧的单一维度类型；account 侧 None
    aux_name: str  # 账套明细名（aux_name 或 account_name）
    dimension_key: str  # 稳定维度键（account_code|aux_type|aux_name 归一后）
    dataset_id: str | None

    def identity_tuple(self) -> tuple:
        """用于集合/交集判定的身份元组（不含展示名字符串比较）。"""
        return (
            self.source_kind,
            self.account_code,
            self.aux_type or "",
            self.dimension_key,
            self.dataset_id or "",
        )


@dataclass(frozen=True)
class Candidate:
    """一个账套明细候选（带金额与相似度提示，按稳定身份传输）。"""

    target: TargetIdentity
    display_name: str  # 原始展示名（未归一）
    normalized_name: str  # 归一后名（匹配用）
    amount: Decimal  # 期末余额（排序/量级提示）
    similarity: float  # 与行名的相似度 [0,1]

    def as_wire(self) -> dict:
        return {
            "target_identity": {
                "source_kind": self.target.source_kind,
                "account_code": self.target.account_code,
                "aux_type": self.target.aux_type,
                "aux_name": self.target.aux_name,
                "dimension_key": self.target.dimension_key,
                "dataset_id": self.target.dataset_id,
            },
            "display_name": self.display_name,
            "amount": str(self.amount),
            "similarity": round(self.similarity, 4),
            "source_kind": self.target.source_kind,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 名称归一与相似度（纯函数）
# ─────────────────────────────────────────────────────────────────────────────


def normalize_name(name: str) -> str:
    """归一账套/行名用于**候选匹配**：全半角折叠 + 去空白 + 剥常见机构后缀。

    🔴 仅用于匹配判定，不改任何展示名，也不用于直接出数。
    """
    if not name:
        return ""
    # 全角→半角 / 兼容分解（NFKC 折叠全半角、罗马数字等）
    s = unicodedata.normalize("NFKC", str(name))
    # 去所有空白（含中文空格）
    s = "".join(s.split())
    s = s.strip().lower()
    # 剥常见后缀（从最长后缀开始，避免「有限公司」先被「公司」截断）
    for suffix in _COMMON_SUFFIXES:
        low = suffix.lower()
        if s.endswith(low) and len(s) > len(low):
            s = s[: -len(low)]
            break
    return s


def similarity(a: str, b: str) -> float:
    """归一名之间的相似度 [0,1]：字符二元组 Dice 系数（无第三方依赖）。

    版本 `SIMILARITY_VERSION`。空串或完全不同返回 0；完全相同返回 1。
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    grams_a = _bigrams(na)
    grams_b = _bigrams(nb)
    if not grams_a or not grams_b:
        # 单字符名回退到相等判定
        return 1.0 if na == nb else 0.0
    inter = 0
    b_counts: dict[str, int] = {}
    for g in grams_b:
        b_counts[g] = b_counts.get(g, 0) + 1
    for g in grams_a:
        if b_counts.get(g, 0) > 0:
            inter += 1
            b_counts[g] -= 1
    return (2.0 * inter) / (len(grams_a) + len(grams_b))


def _bigrams(s: str) -> list[str]:
    return [s[i : i + 2] for i in range(len(s) - 1)] if len(s) >= 2 else []


# ─────────────────────────────────────────────────────────────────────────────
# Task 4: 候选生成（复用既有科目定位，不重写）
# ─────────────────────────────────────────────────────────────────────────────


def _dimension_key(account_code: str, aux_type: str | None, name: str) -> str:
    """稳定维度键：account_code | aux_type | 归一名。用于目标身份比对与去重。"""
    return f"{account_code}|{aux_type or ''}|{normalize_name(name)}"


async def build_candidates(
    db,
    project_id,
    year,
    account_prefixes,
    row_label: str,
    *,
    dataset_id: str | None = None,
) -> list[Candidate]:
    """从已定位科目叶子取账套明细名候选（Requirement 2.2）。

    **复用既有取数**（红基线 3 —— 不重写定位）：
      - aux 侧：:func:`aux_aggregation.aggregate_aux_by_name`（已锁单一 aux_type、走
        `get_active_filter` 只取 active dataset、防维度冗余双算）
      - account 侧：:func:`tb_query.fetch_tb_subtree` + `select_leaves`（`account_name`）

    Args:
        account_prefixes: 由调用方从科目定位（`select_leaves` 上游）解析出的原始码前缀集，
            **不在本函数内重新定位科目**。
        row_label: 底稿行名（用于相似度排序）。
        dataset_id: 当前 active dataset id（写入目标身份供判 stale）。

    Returns:
        `Candidate` 列表（按相似度降序、金额量级降序），截断到 `CANDIDATE_LIMIT`。
        无数据返回 `[]`（正常空结果，不是错误）。
    """
    prefixes = [str(p).strip() for p in (account_prefixes or []) if str(p or "").strip()]
    if not prefixes:
        return []

    # 🔴 复盘 #3：接通真实 active dataset_id —— aggregate_aux_by_name 不返回 dataset_id，
    #    render-config 也未必下发；不接则目标身份 dataset_id 恒 None ⇒ stale 指纹里 dataset
    #    恒空 ⇒ Property 2（dataset 变化判 stale）生产环境永不触发。调用方未显式传时主动查。
    effective_dataset_id = dataset_id
    if effective_dataset_id is None:
        try:
            from app.services.dataset_service import DatasetService

            active_id = await DatasetService.get_active_dataset_id(
                db, project_id, int(year or 0)
            )
            effective_dataset_id = str(active_id) if active_id else None
        except Exception:  # noqa: BLE001 — 取 active dataset 失败不阻断候选生成（降级为无指纹）
            logger.warning(
                "row_name_alignment: 取 active dataset_id 失败 project=%s（stale 指纹降级为空）",
                project_id,
                exc_info=True,
            )
            effective_dataset_id = None

    candidates: list[Candidate] = []

    # ① aux 侧候选（往来单位/明细名）
    try:
        entries, aux_type, _total = await aggregate_aux_by_name(
            db, str(project_id), int(year or 0), prefixes
        )
    except Exception as exc:  # noqa: BLE001 — 记 ERROR 并上抛，不吞成空（复盘 #5）
        logger.error(
            "row_name_alignment: aux 候选取数失败 project=%s prefixes=%s",
            project_id,
            prefixes,
            exc_info=True,
        )
        raise CandidateSourceError("aux", exc) from exc
    for e in entries:
        name = (e.aux_name or "").strip()
        if not name:
            continue
        acc = prefixes[0]
        target = TargetIdentity(
            source_kind=SOURCE_AUX,
            account_code=acc,
            aux_type=aux_type,
            aux_name=name,
            dimension_key=_dimension_key(acc, aux_type, name),
            dataset_id=effective_dataset_id,
        )
        candidates.append(
            Candidate(
                target=target,
                display_name=name,
                normalized_name=normalize_name(name),
                amount=Decimal(str(e.closing or 0)),
                similarity=similarity(row_label, name),
            )
        )

    # ② account 侧候选（叶子科目名）—— aux 无命中或补充
    try:
        from .tb_query import fetch_tb_subtree

        subtree = await fetch_tb_subtree(db, project_id, year, prefixes)
        leaves = select_leaves(to_leaf_rows(subtree))
        leaves = filter_by_prefixes(leaves, prefixes)
    except Exception as exc:  # noqa: BLE001 — 记 ERROR 并上抛，不吞成空（复盘 #5）
        logger.error(
            "row_name_alignment: account 候选取数失败 project=%s prefixes=%s",
            project_id,
            prefixes,
            exc_info=True,
        )
        raise CandidateSourceError("account", exc) from exc
    # 🔴 跨源去重按**归一名**（复盘 #2）：aux 与 account 的 dimension_key 结构不同
    #    （aux 含 aux_type、account 的 account_code 是叶子码）永不相等 —— 只按 dim 去重
    #    等于不去重，同一明细的往来单位名与科目名会各出一条 → 用户各选即金额双算。
    #    aux 候选更细（带维度），优先保留；account 侧同归一名的候选一律跳过。
    seen_dims = {c.target.dimension_key for c in candidates}
    seen_norms = {c.normalized_name for c in candidates if c.normalized_name}
    for lf in leaves:
        name = (lf.account_name or "").strip()
        if not name:
            continue
        norm = normalize_name(name)
        if norm and norm in seen_norms:
            continue  # 同名已由 aux 侧（或先前 account 行）覆盖，防跨源双算
        dim = _dimension_key(lf.account_code, None, name)
        if dim in seen_dims:
            continue
        seen_dims.add(dim)
        if norm:
            seen_norms.add(norm)
        target = TargetIdentity(
            source_kind=SOURCE_ACCOUNT,
            account_code=lf.account_code,
            aux_type=None,
            aux_name=name,
            dimension_key=dim,
            dataset_id=lf.dataset_id or effective_dataset_id,
        )
        candidates.append(
            Candidate(
                target=target,
                display_name=name,
                normalized_name=normalize_name(name),
                amount=Decimal(str(lf.closing or 0)),
                similarity=similarity(row_label, name),
            )
        )

    # 排序：相似度降序 → 金额量级降序 → 名称稳定序；截断候选上限
    candidates.sort(
        key=lambda c: (c.similarity, abs(c.amount), c.display_name),
        reverse=True,
    )
    return candidates[:CANDIDATE_LIMIT]


# ─────────────────────────────────────────────────────────────────────────────
# Task 5: classify 四态分类（纯函数）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassifyResult:
    """`classify` 结果：四态 + 命中身份 + stale 原因。"""

    state: MatchState
    matched_targets: tuple[TargetIdentity, ...] = ()
    stale_reason: str | None = None


def classify(
    row_label: str,
    candidates: list[Candidate],
    saved_mapping: "SavedMapping | None" = None,
    *,
    active_target_keys: frozenset[tuple] | None = None,
) -> ClassifyResult:
    """产出行名的匹配四态（纯函数，Property 1）。

    优先级：
      1. 有已落库用户映射 → 校验目标身份是否仍在当前 active 候选身份集内
         - 全部有效 → USER_CONFIRMED
         - 有目标失效（dataset 变化 / 身份不一致 / 名称消失）→ stale ⇒ UNMATCHED
      2. 无映射 → 按归一名精确匹配候选
         - 归一后唯一精确命中 → AUTO_MATCHED
         - 归一后多命中 / 存在相似候选（>= 阈值但非唯一精确）→ AMBIGUOUS
         - 零命中 → UNMATCHED

    🔴 归一后非唯一命中一律 AMBIGUOUS，绝不当精确命中出数（Requirement 5.2）。
    """
    cand_list = candidates or []

    # ① 已落库映射优先，先判 stale（Property 2）
    if saved_mapping is not None and saved_mapping.targets:
        # active 身份集：优先用调用方传入的权威集，否则用当前候选身份集
        if active_target_keys is None:
            active_keys = {c.target.identity_tuple() for c in cand_list}
        else:
            active_keys = set(active_target_keys)
        stale: list[TargetIdentity] = []
        valid: list[TargetIdentity] = []
        for t in saved_mapping.targets:
            if t.identity_tuple() in active_keys:
                valid.append(t)
            else:
                stale.append(t)
        if stale:
            return ClassifyResult(
                state=MatchState.UNMATCHED,
                matched_targets=(),
                stale_reason=(
                    f"{len(stale)} 个已确认目标在当前账套已失效"
                    "（数据集变化 / 科目或维度不一致 / 明细名消失），需重新确认"
                ),
            )
        return ClassifyResult(
            state=MatchState.USER_CONFIRMED,
            matched_targets=tuple(valid),
        )

    # ② 无映射：按归一名匹配
    norm_row = normalize_name(row_label)
    if not norm_row or not cand_list:
        return ClassifyResult(state=MatchState.UNMATCHED)

    exact = [c for c in cand_list if c.normalized_name == norm_row]
    if len(exact) == 1:
        return ClassifyResult(
            state=MatchState.AUTO_MATCHED,
            matched_targets=(exact[0].target,),
        )
    if len(exact) > 1:
        # 归一后多命中 → 必须人工确认
        return ClassifyResult(
            state=MatchState.AMBIGUOUS,
            matched_targets=tuple(c.target for c in exact),
        )

    # 无精确命中，看有无相似候选
    similar = [c for c in cand_list if c.similarity >= SIMILARITY_THRESHOLD]
    if similar:
        return ClassifyResult(
            state=MatchState.AMBIGUOUS,
            matched_targets=tuple(c.target for c in similar),
        )
    return ClassifyResult(state=MatchState.UNMATCHED)


# ─────────────────────────────────────────────────────────────────────────────
# Task 6: resolve_amounts + 多对一口径与无值语义
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SavedMapping:
    """一行已落库的用户确认映射（读服务投影，纯数据）。"""

    row_key: str
    targets: tuple[TargetIdentity, ...]
    mapping_version: int = 1
    confirmed_by: str | None = None
    confirmed_at: str | None = None


@dataclass(frozen=True)
class RowAmount:
    """一行的重算结果。

    `amount is None` = 无值语义（unmatched / stale），**绝不是 0 或上期值**
    （Requirement 5.1 / Property 6）。
    """

    row_key: str
    amount: Decimal | None
    state: MatchState
    duplicate_reference: bool = False  # 多对一重复引用告警（Property 3）
    stale_reason: str | None = None


def resolve_amounts(
    mappings: dict[str, SavedMapping],
    amount_by_identity: dict[tuple, Decimal],
    states: dict[str, MatchState] | None = None,
    *,
    stale_reasons: dict[str, str] | None = None,
) -> dict[str, RowAmount]:
    """按映射聚合各行金额，处理多对一告警与无值语义（纯函数，Property 3 / 6）。

    Args:
        mappings: `{row_key: SavedMapping}`（仅含 user_confirmed 行）。
        amount_by_identity: `{identity_tuple: 期末金额}`（来自 active 候选）。
        states: `{row_key: MatchState}`；缺省视为按 mapping 有无推断。
        stale_reasons: `{row_key: stale 原因}`，这些行强制无值。

    Returns:
        `{row_key: RowAmount}`。

    多对一（DEC-3）：**不自动去重**（各行按映射各自聚合），但若两个不同 row_key 的
    目标身份交集非空，则涉及的每一行都标 `duplicate_reference=True`。
    """
    states = states or {}
    stale_reasons = stale_reasons or {}

    # 先算「哪些目标身份被多个 row_key 引用」（多对一检测）
    identity_to_rows: dict[tuple, set[str]] = {}
    for rk, m in mappings.items():
        for t in m.targets:
            identity_to_rows.setdefault(t.identity_tuple(), set()).add(rk)
    shared_identities = {
        idt for idt, rows in identity_to_rows.items() if len(rows) > 1
    }
    rows_with_dup = {
        rk
        for idt in shared_identities
        for rk in identity_to_rows[idt]
    }

    out: dict[str, RowAmount] = {}
    for rk, m in mappings.items():
        state = states.get(rk, MatchState.USER_CONFIRMED)
        # stale / unmatched → 无值语义，不出金额
        if rk in stale_reasons or state in (MatchState.UNMATCHED, MatchState.AMBIGUOUS):
            out[rk] = RowAmount(
                row_key=rk,
                amount=None,
                state=MatchState.UNMATCHED if rk in stale_reasons else state,
                duplicate_reference=rk in rows_with_dup,
                stale_reason=stale_reasons.get(rk),
            )
            continue
        total = Decimal("0")
        for t in m.targets:
            total += amount_by_identity.get(t.identity_tuple(), Decimal("0"))
        out[rk] = RowAmount(
            row_key=rk,
            amount=total,
            state=state,
            duplicate_reference=rk in rows_with_dup,
        )
    return out


__all__ = [
    "CANDIDATE_LIMIT",
    "Candidate",
    "CandidateSourceError",
    "ClassifyResult",
    "MatchState",
    "NORMALIZATION_VERSION",
    "RowAmount",
    "SIMILARITY_THRESHOLD",
    "SIMILARITY_VERSION",
    "SOURCE_ACCOUNT",
    "SOURCE_AUX",
    "SavedMapping",
    "TargetIdentity",
    "build_candidates",
    "classify",
    "normalize_name",
    "resolve_amounts",
    "similarity",
]
