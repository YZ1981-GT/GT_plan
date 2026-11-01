"""合并附注明细模板：来源行名 → 模板目标行的建议算法（纯函数，无 DB）。

从 ``consol_note_detail_source_service`` 拆出（该文件超 800 行门禁）；原导入路径仍可用
（source service 重新导出 ``suggest_template_rows``）。

spec: consol-note-detail-template-and-mapping（consol-note-pull-from-standalone 收口）
"""
from __future__ import annotations

import json
import re
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

_LABEL_WS = str.maketrans("", "", " \t\r\n\u3000")
#: 账龄 / 期限区间的连接符：「1-2年」「1－2年」「1～2年」「1至2年」是同一行
_RANGE_RE = re.compile(r"(\d+)[-－—–~～至到](\d+)(?=年|个月|月|天|日)")
#: 行名里的编制提示「【注意：与会计政策中披露的组合保持一致】」：不是行名（单体附注常把它删掉，合并模板还留着）
_HINT_RE = re.compile(r"【[^】]*】")
#: 整行包在方括号里 = Word 模板的可选行（「[本期转销]」），单体附注填了就去掉括号
_OPTIONAL_RE = re.compile(r"[\[［](.+)[\]］]")
#: 半角括号统一成全角（模板「土地储备(由房地产开发企业填列）」与单体「土地储备（由房地产开发企业填列）」）
_PARENS = str.maketrans({"(": "（", ")": "）"})


def _label_key(label: Any) -> str:
    """行名比较键：去全部空白 + 去「【…】」编制提示 + 去可选行方括号 + 括号统一全角 + 去尾冒号 + 区间连接符统一成「至」
    （模板「合  计」与来源「合计」、「小计：」与「小计」、合并模板「1至2年」与单体组合计提表「1-2年」、
    「按组合计提坏账准备【注意：…】」与「按组合计提坏账准备」、「[本期转销]」与「本期转销」是同一行）。
    整个行名都是「【…】」时不去。"""
    raw = str(label or "").translate(_LABEL_WS)
    s = _HINT_RE.sub("", raw) or raw
    if optional := _OPTIONAL_RE.fullmatch(s):
        s = optional.group(1)
    s = _RANGE_RE.sub(r"\1至\2", s.translate(_PARENS))
    return s.rstrip(":").rstrip("：")


#: 合并附注模板里的「……」可扩位占位行（Word 的意思是「此处按实际列示」，不是一行数据）
PLACEHOLDER_RE = re.compile(r"[.…·]+")


def is_placeholder_label(label: Any) -> bool:
    """行名去空白后整段是省略号 / 句点（「……」「...」「···」）：可扩位占位，不是一行数据。"""
    return bool(PLACEHOLDER_RE.fullmatch(_label_key(label)))


# ── 全局行名别名库 ──

_ALIASES_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_row_label_aliases.json"


@lru_cache(maxsize=1)
def _load_global_aliases() -> dict[str, str]:
    """加载全局别名库，返回 {变体归一键 → 标准名归一键}。"""
    if not _ALIASES_PATH.exists():
        return {}
    raw = json.loads(_ALIASES_PATH.read_bytes())
    index: dict[str, str] = {}
    for entry in raw.get("aliases", []):
        canonical = _label_key(entry.get("canonical", ""))
        if not canonical:
            continue
        for v in entry.get("variants", []):
            vk = _label_key(v)
            if vk and vk != canonical:
                index[vk] = canonical
    return index


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 模板建议算法（R1.1 / D§六）
# ═══════════════════════════════════════════════════════════════════════════════


def suggest_template_rows(
    source_groups: list[dict[str, Any]],
    *,
    existing_template_rows: list[dict[str, Any]] | None = None,
    history_mappings: list[dict[str, Any]] | None = None,
    previous_year_suggestions: list[dict[str, Any]] | None = None,
    fuzzy_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """生成模板建议行列表。

    每条来源标签依次匹配（命中即停）：
    0. 集团下推行身份（``_pushed_row_id``，exact_id）
    1. 精确匹配目标 canonical_name
    2. 别名匹配 aliases；2.5 全局别名库
    3. 账龄 / 期限区间包含（``aging_bucket``，``note_aging_buckets``；原「规则模板库」一级随 V202 退役后空出的一级）
    4. 上年同集团项目匹配（previous_year_suggestions，confidence=0.88）
    5. 本项目本章节已确认规则（history，同一行名 → 同一目标行）—— 排在模糊匹配之前：用户确认过的对应
       比字面相似度可靠（原先排在模糊之后，相似度过线的行永远走不到历史规则）
    6. 模糊匹配（SequenceMatcher ≥ threshold）
    7. 未匹配 → 建议新增

    可自动确认（不必人工看）的只有 ``AUTO_CONFIRM_MATCH_TYPES``，见 ``is_auto_confirmable``。

    返回 ``[{source_label, suggested_target, confidence, match_type, candidates}]``
    """
    template_rows = existing_template_rows or []
    history = history_mappings or []

    # 构建上年项目建议索引
    prev_year_index: dict[str, dict[str, Any]] = {}
    for s in (previous_year_suggestions or []):
        sl = str(s.get("source_label", "")).strip()
        if sl and s.get("suggested_target"):
            prev_year_index[sl] = s

    # 收集所有来源标签（去重保序）
    all_labels: list[str] = []
    seen: set[str] = set()
    # V204: 同时收集来源行的 _pushed_row_id（集团下推的行）
    label_to_pushed_rid: dict[str, str] = {}
    label_row_type: dict[str, str] = {}
    for group in source_groups:
        for sr in group.get("source_rows", []):
            label = sr["label"]
            if label and label not in seen:
                all_labels.append(label)
                seen.add(label)
                label_row_type[label] = str(sr.get("row_type") or "data")
                # 来源行带 _pushed_row_id = 集团下推的行
                rid = sr.get("_pushed_row_id") or ""
                if rid:
                    label_to_pushed_rid[label] = rid

    # 构建目标索引（按去空白的行名比较：模板「合  计」与来源「合计」是同一行）
    name_to_target: dict[str, dict[str, Any]] = {}
    alias_to_target: dict[str, dict[str, Any]] = {}
    for tr in template_rows:
        cn = _label_key(tr.get("canonical_name", ""))
        if cn:
            name_to_target[cn] = tr
        for alias in tr.get("aliases", []):
            a = _label_key(alias)
            if a:
                alias_to_target[a] = tr

    # 历史映射索引
    history_index: dict[str, str] = {}
    for hm in history:
        sl = str(hm.get("source_label", "")).strip()
        trid = str(hm.get("target_row_id", "")).strip()
        if sl and trid:
            history_index[sl] = trid

    # 构建目标行 row_id 索引（V204: 第 0 级 row_id 精确匹配）
    target_by_rid: dict[str, dict[str, Any]] = {}
    for tr in template_rows:
        trid = str(tr.get("target_row_id", "")).strip()
        if trid:
            target_by_rid[trid] = tr

    from app.services.note_aging_buckets import containing_bucket

    bucket_names = [tr.get("canonical_name", "") for tr in template_rows]
    suggestions: list[dict[str, Any]] = []
    for label in all_labels:
        key = _label_key(label)

        # 0. row_id 精确匹配（集团下推的行带 _pushed_row_id）
        pushed_rid = label_to_pushed_rid.get(label, "")
        if pushed_rid and pushed_rid in target_by_rid:
            suggestions.append(_suggestion(
                label, target_by_rid[pushed_rid], "exact_id", 1.0,
            ))
            continue

        # 1. 精确匹配 canonical_name
        if key in name_to_target:
            suggestions.append(_suggestion(
                label, name_to_target[key], "exact", 1.0,
            ))
            continue

        # 2. 别名匹配
        if key in alias_to_target:
            suggestions.append(_suggestion(
                label, alias_to_target[key], "alias", 0.95,
            ))
            continue

        # 2.5. 全局别名库匹配（行名变体归一后找到等价的标准名）
        global_aliases = _load_global_aliases()
        canonical_key = global_aliases.get(key)
        if canonical_key and canonical_key in name_to_target:
            suggestions.append(_suggestion(
                label, name_to_target[canonical_key], "global_alias", 0.93,
            ))
            continue
        # 反向：来源用标准名、模板行用变体名（原先没找到时看「上一条建议是不是 global_alias」决定跳过，
        # 上一行按别名配上、这一行反向没配上 ⇒ 这一行整条建议丢失）
        variant = next((vk for vk, ck in global_aliases.items() if ck == key and vk in name_to_target), None)
        if variant is not None:
            suggestions.append(_suggestion(label, name_to_target[variant], "global_alias", 0.93))
            continue

        # 3. 账龄 / 期限区间整段落在模板唯一一档里（单体「3至4年」「5年以上」→ 合并「3年以上」，多档相加）
        bucket = containing_bucket(label, bucket_names)
        if bucket is not None:
            suggestions.append(_suggestion(label, template_rows[bucket], "aging_bucket", 0.9))
            continue

        # 4. 上年同集团项目匹配（confidence=0.88）
        if label in prev_year_index:
            s = prev_year_index[label]
            suggestions.append({
                "source_label": label,
                "suggested_target": s["suggested_target"],
                "confidence": s.get("confidence", 0.88),
                "match_type": "previous_year",
                "candidates": s.get("candidates", []),
            })
            continue

        # 5. 本项目本章节已确认规则（目标行不在当前模板里 ⇒ 继续往下匹配）
        history_target = next(
            (tr for tr in template_rows if str(tr.get("target_row_id", "")) == history_index.get(label)), None,
        ) if label in history_index else None
        if history_target is not None:
            suggestions.append(_suggestion(label, history_target, "history", 0.85))
            continue

        # 6'. 来源的合计 / 小计行不模糊配（原先「小  计」按字面配到「合  计」）：合计行对模板唯一的合计行；
        #     模板没有的合计 / 小计行忽略 —— 合计按本表数据重算，模板没有这一行就没有要写的数（R6.5）
        if label_row_type.get(label) in ("total", "subtotal"):
            totals = [tr for tr in template_rows if tr.get("row_type") == "total"]
            if label_row_type[label] == "total" and len(totals) == 1:
                suggestions.append(_suggestion(label, totals[0], "total_row", 0.9))
            else:
                suggestions.append({"source_label": label, "suggested_target": None, "confidence": 1.0,
                                    "match_type": TOTAL_IGNORED, "mapping_action": "ignore",
                                    "ignore_reason": TOTAL_IGNORED_REASON, "candidates": []})
            continue

        # 6. 模糊匹配
        best_ratio = 0.0
        best_target: dict[str, Any] | None = None
        candidates: list[dict[str, Any]] = []
        for tr in template_rows:
            cn = str(tr.get("canonical_name", ""))
            ratio = SequenceMatcher(None, label, cn).ratio()
            if ratio >= fuzzy_threshold:
                candidates.append({"target": tr, "ratio": round(ratio, 3)})
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_target = tr
            for alias in tr.get("aliases", []):
                r2 = SequenceMatcher(None, label, str(alias)).ratio()
                if r2 >= fuzzy_threshold and r2 > best_ratio:
                    best_ratio = r2
                    best_target = tr
                    candidates.append({"target": tr, "ratio": round(r2, 3)})

        if best_target is not None:
            suggestions.append(_suggestion(
                label, best_target, "fuzzy", round(best_ratio, 3), candidates,
            ))
            continue

        # 7. 未匹配
        suggestions.append({
            "source_label": label,
            "suggested_target": None,
            "confidence": 0.0,
            "match_type": "manual",
            "candidates": [],
        })

    return _split_repeated_labels(suggestions, source_groups, template_rows, target_by_rid, history)


def _split_repeated_labels(
    suggestions: list[dict[str, Any]],
    source_groups: list[dict[str, Any]],
    template_rows: list[dict[str, Any]],
    target_by_rid: dict[str, dict[str, Any]],
    history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """同名行逐个建议（R11 起；spec note-chain-followup-optimizations R3 改按分组判别）。

    来源表里同名行出现多次、或模板里同名（含别名）行不止一个 ⇒ 来源每一处（行名, 分组, 组内序号）各一条建议，带
    ``source_group`` / ``source_group_occurrence``（``consol_note_row_groups``，来源与模板同一函数）：模板里同一一级分组
    只有一个同名行 ⇒ 对它；同一分组有几个 ⇒ 按完整分组键与组内序号对；确认过的（行名, 分组）历史优先于下面的退回。
    都对不上 ⇒ 退回按第几次出现对模板第几个同名行，``match_type="position"``（来源少一组 / 组序不同时会配到别的组，
    须人工复核，不自动确认）。下推行按各自行身份（exact_id）。只出现一次、模板里也只有一个同名行的行名不带分组（兼容旧规则）。
    """
    from app.services.consol_note_row_groups import group_label, row_groups

    occs: dict[str, list[tuple[str, int, int, str]]] = {}  # 行名 → [(分组, 组内序号, 第几次出现, 下推行身份)]
    repeated: set[str] = set()
    for group in source_groups:
        seen: dict[str, int] = {}
        for sr in group.get("source_rows", []):
            label = sr.get("label") or ""
            if not label:
                continue
            k = sr.get("occurrence") if isinstance(sr.get("occurrence"), int) else seen.get(label, 0)
            seen[label] = seen.get(label, 0) + 1
            entry = (str(sr.get("group") or ""), int(sr.get("group_occurrence") or 0), k, str(sr.get("_pushed_row_id") or ""))
            if entry[:2] not in {e[:2] for e in occs.setdefault(label, [])}:
                occs[label].append(entry)
        repeated.update(label for label, n in seen.items() if n > 1)
    tpl_groups = row_groups([tr.get("canonical_name", "") for tr in template_rows],
                            [tr.get("row_type") for tr in template_rows])
    by_id = {str(tr.get("target_row_id", "")): tr for tr in template_rows}
    history_group = {(str(h.get("source_label", "")).strip(), h["source_group"], int(h.get("source_group_occurrence") or 0)):
                     str(h.get("target_row_id", ""))
                     for h in history if isinstance(h.get("source_group"), str) and h.get("target_row_id")}
    history_occ = {(str(h.get("source_label", "")).strip(), h["source_occurrence"]): str(h.get("target_row_id", ""))
                   for h in history if isinstance(h.get("source_occurrence"), int) and h.get("target_row_id")}

    aliases = _load_global_aliases()

    def canon(group: str) -> str:
        """分组键里的行名按通用别名归一：单体「按单项计提减值准备」下的「其中：」与模板「按单项计提坏账准备」下的是同一组。"""
        return "›".join(aliases.get(part, part) for part in group.split("›"))

    def level1(group: str) -> str:
        return group.split("›", 1)[0]

    tpl_canon = [canon(g) for g, _occ in tpl_groups]
    out: list[dict[str, Any]] = []
    for s in suggestions:
        label = s["source_label"]
        key = _label_key(label)
        same = [i for i, tr in enumerate(template_rows) if _label_key(tr.get("canonical_name", "")) == key
                or key in {_label_key(a) for a in tr.get("aliases", [])}]
        if label not in repeated and len(same) < 2:
            out.append(s)
            continue
        # 按行名对得上模板（精确 / 别名；下推行里没带行身份的那几处按行名对）
        by_name = s["match_type"] if s["match_type"] in ("exact", "alias") else (
            "exact" if s["match_type"] == "exact_id" and same else None)
        src_count = Counter(canon(g) for g, _go, _k, _rid in occs.get(label, []))
        for group, group_occ, k, rid in occs.get(label, []):
            cg = canon(group)
            cands = [i for i in same if level1(tpl_canon[i]) == level1(cg)]
            tpl_count = Counter(tpl_canon[i] for i in cands)
            # 同一一级分组里模板有几个同名行：完整分组键两边都唯一才算对上（组内只剩顺序可分的不算）
            exact = [i for i in cands if tpl_canon[i] == cg and tpl_count[cg] == 1 and src_count[cg] == 1]
            hist = by_id.get(history_group.get((label, group, group_occ)) or history_occ.get((label, k), ""))
            confidence = s["confidence"] if by_name == s["match_type"] else 1.0
            if rid and rid in target_by_rid:
                item = _suggestion(label, target_by_rid[rid], "exact_id", 1.0)
            elif by_name and len(cands) > 1 and exact:
                item = _suggestion(label, template_rows[exact[0]], by_name, confidence)
            elif hist is not None:
                item = _suggestion(label, hist, "history", 0.85)
            elif by_name and len(cands) == 1:  # 这一组模板里只有一个同名行：都对它（同组同名几行相加）
                item = _suggestion(label, template_rows[cands[0]], by_name, confidence)
            elif by_name and same:
                item = _suggestion(label, template_rows[same[min(k, len(same) - 1)]], "position", 0.6)
            else:
                item = dict(s)
            out.append({**item, "source_group": group, "source_group_label": group_label(group),
                        "source_group_occurrence": group_occ})
    return out


#: 可自动确认的匹配方式：行身份 / 行名 / 别名 / 账龄区间包含 / 模板唯一合计行 / 用户确认过的同名对应。模糊、上年规则、
#: 同名行只能按位置配（``position``）须人工看一眼。
AUTO_CONFIRM_MATCH_TYPES = frozenset({"exact_id", "exact", "alias", "global_alias", "aging_bucket", "total_row", "history"})
#: 模板没有的来源合计 / 小计行：建议「忽略」（``mapping_action=ignore``），可自动确认
TOTAL_IGNORED = "total_ignored"
TOTAL_IGNORED_REASON = "合并模板没有这一行合计 / 小计（合计按本表数据重算）"


def is_auto_confirmable(suggestion: dict[str, Any]) -> bool:
    """建议可不经人工确认直接采用：有目标行且匹配方式属于 ``AUTO_CONFIRM_MATCH_TYPES``，或模板没有的合计 / 小计行
    建议忽略（预览与「⚡ 自动映射」共用）。"""
    if suggestion.get("match_type") == TOTAL_IGNORED:
        return True
    target = suggestion.get("suggested_target")
    return bool(isinstance(target, dict) and target.get("target_row_id")) \
        and suggestion.get("match_type") in AUTO_CONFIRM_MATCH_TYPES


def _suggestion(
    label: str,
    target: dict[str, Any],
    match_type: str,
    confidence: float,
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "source_label": label,
        "suggested_target": {
            "target_row_id": target.get("target_row_id"),
            "canonical_name": target.get("canonical_name"),
        },
        "confidence": confidence,
        "match_type": match_type,
        "candidates": candidates or [],
    }
