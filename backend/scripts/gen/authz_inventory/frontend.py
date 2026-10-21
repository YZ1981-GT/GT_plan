"""附注编辑器前端调用点扫描与匹配（spec partner-manager-edit-permission，需求 1.3 / 1.4，design §4.12 第 6 步）。

本模块目前只包含匹配纯函数（任务 8.7）。完整的前端调用点扫描（任务 8.3）后续实施。

匹配规则（设计文档 §4.12 第 6 步）：
- 方法相同；
- 路径去查询串后逐段对应：插值段（``${}``）对应任一段，``{x:path}`` 对一段及以上；
- 多个命中取字面段最多的；仍并列全部列出，标「歧义」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence
from urllib.parse import urlsplit

# 匹配 FastAPI 路径参数（含 `{param:path}` 变体）
_PATH_PARAM = re.compile(r"^\{[^}]*\}$")
_PATH_PARAM_WITH_PATH = re.compile(r"^\{[^}]*:path\}$")

# 匹配前端模板字符串插值段 `${...}`
_INTERPOLATION = re.compile(r"\$\{[^}]*\}")


@dataclass(frozen=True)
class MatchResult:
    """一个前端调用的匹配结果。"""

    method: str
    call_path: str  # 原始调用路径（含查询串）
    matches: tuple[str, ...]  # 命中的后端路径（按字面段数降序）
    ambiguous: bool  # 并列的命中 > 1
    literal_segments: int  # 最优命中的字面段数（无命中为 0）


def _strip_query(path: str) -> str:
    """去掉查询串。"""
    return urlsplit(path).path


def _split_segments(path: str) -> list[str]:
    """按 ``/`` 拆段，去掉首尾空段。"""
    return [seg for seg in path.split("/") if seg]


def _is_interpolation(seg: str) -> bool:
    """前端模板串里的插值段（``${expr}`` 或纯插值段）。"""
    return bool(_INTERPOLATION.search(seg))


def _is_path_param(seg: str) -> bool:
    """后端路径里的 ``{x:path}`` 参数。"""
    return bool(_PATH_PARAM_WITH_PATH.match(seg))


def _is_param(seg: str) -> bool:
    """后端路径里的普通 ``{x}`` 参数（不含 ``:path``）。"""
    return bool(_PATH_PARAM.match(seg)) and not _is_path_param(seg)


def _segments_match(call_segs: list[str], endpoint_segs: list[str]) -> tuple[bool, int]:
    """逐段匹配一条前端路径与一条后端路径。

    返回 ``(是否匹配, 字面段对应数)``。

    规则：
    - 前端插值段 ``${...}`` 匹配后端任一段。
    - 后端普通参数 ``{x}`` 匹配前端任一段。
    - 后端 ``{x:path}`` 匹配前端一段及以上（贪心匹配剩余段落）。
    - 字面段必须严格相等。
    - 字面段对应数 = 两侧都是字面量且相等的段数。
    """
    ci, ei = 0, 0
    literal_count = 0
    cn, en = len(call_segs), len(endpoint_segs)

    while ci < cn and ei < en:
        cseg = call_segs[ci]
        eseg = endpoint_segs[ei]

        if _is_path_param(eseg):
            # {x:path} 吃掉前端剩余段落（至少一段），但要给后端后续段留空间
            remaining_endpoint = en - ei - 1
            available_call = cn - ci
            if available_call < 1 + remaining_endpoint:
                return False, 0
            # 贪心：{x:path} 吃掉尽可能多的段（给后续段恰好留够）
            consume = available_call - remaining_endpoint
            ci += consume
            ei += 1
            continue

        if _is_interpolation(cseg) or _is_param(eseg):
            # 插值段 / 参数段：匹配任一段
            ci += 1
            ei += 1
            continue

        # 两侧都是字面量
        if cseg == eseg:
            literal_count += 1
            ci += 1
            ei += 1
            continue

        return False, 0

    if ci == cn and ei == en:
        return True, literal_count
    return False, 0


def match_call(
    method: str,
    call_path: str,
    endpoints: Sequence[tuple[str, str]],
) -> MatchResult:
    """将一个前端写方法调用匹配到后端端点列表。

    Parameters
    ----------
    method:
        HTTP 方法（大写），如 ``POST``。
    call_path:
        前端发出的路径（可含查询串与插值段 ``${...}``）。
    endpoints:
        后端端点列表，每个为 ``(method, path)``。

    Returns
    -------
    MatchResult
        命中列表按字面段数降序，取最多者；并列标歧义。
    """
    stripped = _strip_query(call_path)
    call_segs = _split_segments(stripped)

    candidates: list[tuple[str, int]] = []
    for ep_method, ep_path in endpoints:
        if ep_method != method:
            continue
        ep_segs = _split_segments(ep_path)
        ok, lit = _segments_match(call_segs, ep_segs)
        if ok:
            candidates.append((ep_path, lit))

    if not candidates:
        return MatchResult(method, call_path, (), False, 0)

    # 取字面段最多者
    max_lit = max(lit for _, lit in candidates)
    best = tuple(ep for ep, lit in candidates if lit == max_lit)

    return MatchResult(
        method=method,
        call_path=call_path,
        matches=best,
        ambiguous=len(best) > 1,
        literal_segments=max_lit,
    )
