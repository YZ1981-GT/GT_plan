# -*- coding: utf-8 -*-
"""共享 JSON Pointer 路径读写（支持 list 下标段）。

D4 `months/0..11` 是首个需要「段为十进制非负整数且游标为 list → 按 index」的生产形态。
既有 Phase 5 provider 的 `_resolve_json_path` / `_set_json_path` 只认 dict，会把 `"0"`
当成键或在 list 上游标上静默返回 None —— 本模块是唯一允许的数组段实现真源。

错误码封闭（fail closed，禁止回落到 None / 截断 / 补零）：
  - ``json_path_missing_segment``
  - ``json_path_type_mismatch``
  - ``json_path_array_index_invalid``
  - ``json_path_array_index_oob``
  - ``json_path_array_length_invalid``
"""
from __future__ import annotations

from typing import Any, Final, Mapping

from app.services.workpaper_sync.models import SyncDomainError

#: D4 及同形态底稿：名为 `months` 的数组必须长度恰好 12。
FIXED_ARRAY_LENGTHS: Final[Mapping[str, int]] = {"months": 12}


class JsonPathError(SyncDomainError):
    """JSON Pointer 路径读写失败（数组下标 / 类型 / 长度）。"""

    error_code = "json_path_error"


class JsonPathMissingSegmentError(JsonPathError):
    error_code = "json_path_missing_segment"


class JsonPathTypeMismatchError(JsonPathError):
    error_code = "json_path_type_mismatch"


class JsonPathArrayIndexInvalidError(JsonPathError):
    error_code = "json_path_array_index_invalid"


class JsonPathArrayIndexOobError(JsonPathError):
    error_code = "json_path_array_index_oob"


class JsonPathArrayLengthInvalidError(JsonPathError):
    error_code = "json_path_array_length_invalid"


def _is_array_index_token(token: str) -> bool:
    """RFC 6901：数组下标是十进制非负整数，禁止前导零（除 ``0`` 本身）。"""
    if token == "0":
        return True
    return token.isdigit() and not token.startswith("0")


def _decode_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def resolve_json_path(
    root: Mapping[str, Any] | list[Any],
    json_path: str,
    *,
    fixed_array_lengths: Mapping[str, int] | None = None,
) -> Any:
    """按 ``a/b/0`` 相对路径取值（不含前导 ``/``，与既有 provider ``json_path`` 一致）。"""
    if not isinstance(json_path, str) or not json_path or json_path.startswith("/"):
        raise JsonPathTypeMismatchError(
            f"json_path 必须是非空相对路径（无前导 /），实得 {json_path!r}"
        )
    lengths = fixed_array_lengths if fixed_array_lengths is not None else FIXED_ARRAY_LENGTHS
    cursor: Any = root
    parts = json_path.split("/")
    for i, raw in enumerate(parts):
        token = _decode_token(raw)
        parent_key = _decode_token(parts[i - 1]) if i > 0 else None
        if _is_array_index_token(token):
            if not isinstance(cursor, list):
                raise JsonPathTypeMismatchError(
                    f"路径 {json_path!r} 段 {token!r} 需要 list，实得 {type(cursor).__name__}"
                )
            if parent_key is not None and parent_key in lengths:
                expected = lengths[parent_key]
                if len(cursor) != expected:
                    raise JsonPathArrayLengthInvalidError(
                        f"数组 {parent_key!r} 长度必须为 {expected}，实得 {len(cursor)}"
                    )
            index = int(token)
            if index < 0 or index >= len(cursor):
                raise JsonPathArrayIndexOobError(
                    f"路径 {json_path!r} 下标 {index} 越界（len={len(cursor)}）"
                )
            cursor = cursor[index]
            continue
        if not isinstance(cursor, Mapping):
            raise JsonPathTypeMismatchError(
                f"路径 {json_path!r} 段 {token!r} 需要 mapping，实得 {type(cursor).__name__}"
            )
        if token not in cursor:
            raise JsonPathMissingSegmentError(
                f"路径 {json_path!r} 缺失段 {token!r}"
            )
        cursor = cursor[token]
    return cursor


def set_json_path(
    root: dict[str, Any],
    json_path: str,
    value: Any,
    *,
    fixed_array_lengths: Mapping[str, int] | None = None,
) -> bool:
    """按相对路径写值；list 下标段只改目标位，不建 dict、不扩容、不截断。

    返回是否真的改了值。
    """
    if not isinstance(json_path, str) or not json_path or json_path.startswith("/"):
        raise JsonPathTypeMismatchError(
            f"json_path 必须是非空相对路径（无前导 /），实得 {json_path!r}"
        )
    if not isinstance(root, dict):
        raise JsonPathTypeMismatchError(
            f"set_json_path 根必须是 dict，实得 {type(root).__name__}"
        )
    lengths = fixed_array_lengths if fixed_array_lengths is not None else FIXED_ARRAY_LENGTHS
    parts = [_decode_token(p) for p in json_path.split("/")]
    cursor: Any = root
    for i, token in enumerate(parts[:-1]):
        leaf_is_index = _is_array_index_token(parts[i + 1]) if i + 1 < len(parts) else False
        if _is_array_index_token(token):
            if not isinstance(cursor, list):
                raise JsonPathTypeMismatchError(
                    f"路径 {json_path!r} 段 {token!r} 需要 list，实得 {type(cursor).__name__}"
                )
            parent_key = parts[i - 1] if i > 0 else None
            if parent_key is not None and parent_key in lengths:
                expected = lengths[parent_key]
                if len(cursor) != expected:
                    raise JsonPathArrayLengthInvalidError(
                        f"数组 {parent_key!r} 长度必须为 {expected}，实得 {len(cursor)}"
                    )
            index = int(token)
            if index < 0 or index >= len(cursor):
                raise JsonPathArrayIndexOobError(
                    f"路径 {json_path!r} 下标 {index} 越界（len={len(cursor)}）"
                )
            cursor = cursor[index]
            continue
        if not isinstance(cursor, dict):
            raise JsonPathTypeMismatchError(
                f"路径 {json_path!r} 段 {token!r} 需要 dict，实得 {type(cursor).__name__}"
            )
        nxt = cursor.get(token)
        if leaf_is_index:
            # 下一段是数组下标：当前段必须已是 list，禁止改建成 dict。
            if not isinstance(nxt, list):
                raise JsonPathTypeMismatchError(
                    f"路径 {json_path!r} 段 {token!r} 必须已是 list 才能按下标写入，"
                    f"实得 {type(nxt).__name__}"
                )
            if token in lengths and len(nxt) != lengths[token]:
                raise JsonPathArrayLengthInvalidError(
                    f"数组 {token!r} 长度必须为 {lengths[token]}，实得 {len(nxt)}"
                )
            cursor = nxt
            continue
        if not isinstance(nxt, dict):
            nxt = {}
            cursor[token] = nxt
        cursor = nxt

    leaf = parts[-1]
    if _is_array_index_token(leaf):
        if not isinstance(cursor, list):
            raise JsonPathTypeMismatchError(
                f"路径 {json_path!r} 叶段 {leaf!r} 需要 list，实得 {type(cursor).__name__}"
            )
        parent_key = parts[-2] if len(parts) >= 2 else None
        if parent_key is not None and parent_key in lengths:
            expected = lengths[parent_key]
            if len(cursor) != expected:
                raise JsonPathArrayLengthInvalidError(
                    f"数组 {parent_key!r} 长度必须为 {expected}，实得 {len(cursor)}"
                )
        index = int(leaf)
        if index < 0 or index >= len(cursor):
            raise JsonPathArrayIndexOobError(
                f"路径 {json_path!r} 下标 {index} 越界（len={len(cursor)}）"
            )
        if cursor[index] != value:
            cursor[index] = value
            return True
        return False

    if not isinstance(cursor, dict):
        raise JsonPathTypeMismatchError(
            f"路径 {json_path!r} 叶段 {leaf!r} 需要 dict，实得 {type(cursor).__name__}"
        )
    if cursor.get(leaf) != value:
        cursor[leaf] = value
        return True
    return False


__all__ = [
    "FIXED_ARRAY_LENGTHS",
    "JsonPathArrayIndexInvalidError",
    "JsonPathArrayIndexOobError",
    "JsonPathArrayLengthInvalidError",
    "JsonPathError",
    "JsonPathMissingSegmentError",
    "JsonPathTypeMismatchError",
    "resolve_json_path",
    "set_json_path",
]
