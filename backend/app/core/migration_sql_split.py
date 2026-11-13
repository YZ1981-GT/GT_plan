"""迁移 SQL 分句：把一个迁移文件切成可逐条执行的语句（``MigrationRunner`` 的执行与回滚都经这里）。

从 ``migration_runner.py`` 原样抽出（2026-11-04，该文件超行数门）；``MigrationRunner._split_sql_statements``
保留为委托，既有调用方不变。分句规则见 :func:`split_sql_statements`。
"""
from __future__ import annotations

import re


def is_comment_only(stmt: str) -> bool:
    """判断一段 SQL 文本是否全部为注释或空白。

    支持两种注释格式：
    - ``--`` 单行注释
    - ``/* ... */`` 块注释（可跨行）

    Parameters
    ----------
    stmt : str
        已去除首尾空白的 SQL 片段

    Returns
    -------
    bool
        True 表示该片段只含注释/空行，可以跳过执行
    """
    # 先去掉所有 /* ... */ 块注释（使用顶部已导入的 re 模块），再检查剩余内容
    stripped = re.sub(r'/\*.*?\*/', '', stmt, flags=re.DOTALL)
    for line in stripped.splitlines():
        line = line.strip()
        if line and not line.startswith("--"):
            return False
    return True


def split_sql_statements(sql_content: str) -> list[str]:
    """将 SQL 文件内容分割为独立语句列表。

    处理规则：
    1. 识别 ``$tag$ ... $tag$`` 美元引号块（PL/pgSQL DO 块等），整体保留不按分号分割
    2. 识别 ``/* ... */`` 块注释，整体保留（由 is_comment_only 过滤）
    3. 识别 ``'...'`` 字符串字面量（``''`` 转义；``E'...'`` 另认反斜杠转义）与 ``"..."`` 引号标识符
       （``""`` 转义），其中的分号不分句（2026-11-03：V236 的 ``COMMENT ... IS 'a; b'`` 曾被切成半截字符串）
    4. 按分号分割普通语句
    5. 过滤空语句和纯注释语句（``--`` 单行注释 + ``/* */`` 块注释）
    6. 去掉文件开头的 UTF-8 BOM（2026-11-03：V248 / V249 带 BOM，PG 报 syntax error at or near "\\ufeff"）

    Parameters
    ----------
    sql_content : str
        SQL 文件的完整文本内容

    Returns
    -------
    list[str]
        可逐条执行的 SQL 语句列表（已去除首尾空白）
    """
    if sql_content.startswith("\ufeff"):
        sql_content = sql_content[1:]
    statements: list[str] = []
    current: list[str] = []   # 当前语句的字符缓冲
    in_dollar_quote = False    # 是否在 $tag$ 块内
    dollar_tag = ""            # 当前美元引号标签，如 $$ 或 $body$
    in_block_comment = False   # 是否在 /* */ 块注释内
    in_line_comment = False    # 是否在 -- 单行注释内（R10 修复：之前缺，注释内 ; 会破坏分句）
    in_single_quote = False    # 是否在 '...' 字符串字面量内
    quote_backslash = False    # 当前字符串是否 E'...'（反斜杠转义）
    in_double_quote = False    # 是否在 "..." 引号标识符内
    i = 0
    n = len(sql_content)

    while i < n:
        # 字符串字面量 / 引号标识符内：原样收集到闭合引号（'' / "" 是转义，不闭合）
        if in_single_quote:
            ch = sql_content[i]
            current.append(ch)
            if quote_backslash and ch == "\\" and i + 1 < n:
                current.append(sql_content[i + 1])
                i += 2
                continue
            if ch == "'":
                if i + 1 < n and sql_content[i + 1] == "'":
                    current.append("'")
                    i += 2
                    continue
                in_single_quote = False
            i += 1
            continue
        if in_double_quote:
            ch = sql_content[i]
            current.append(ch)
            if ch == '"':
                if i + 1 < n and sql_content[i + 1] == '"':
                    current.append('"')
                    i += 2
                    continue
                in_double_quote = False
            i += 1
            continue

        # 检测 -- 单行注释开始（不在美元引号块/块注释内）
        if not in_dollar_quote and not in_block_comment and not in_line_comment and sql_content[i:i+2] == '--':
            in_line_comment = True
            current.append('--')
            i += 2
            continue

        # 在单行注释内，遇换行结束
        if in_line_comment:
            if sql_content[i] == '\n':
                in_line_comment = False
            current.append(sql_content[i])
            i += 1
            continue

        # 检测 /* 块注释开始（不在美元引号块内）
        if not in_dollar_quote and not in_block_comment and sql_content[i:i+2] == '/*':
            in_block_comment = True
            current.append('/*')
            i += 2
            continue

        # 在块注释内，检测 */ 结束
        if in_block_comment:
            if sql_content[i:i+2] == '*/':
                in_block_comment = False
                current.append('*/')
                i += 2
            else:
                current.append(sql_content[i])
                i += 1
            continue

        # 检测美元引号开始（$tag$ 格式，tag 可为空字符串）
        if not in_dollar_quote and sql_content[i] == '$':
            j = i + 1
            # tag 只能包含字母、数字、下划线
            while j < n and (sql_content[j].isalnum() or sql_content[j] == '_'):
                j += 1
            if j < n and sql_content[j] == '$':
                # 找到合法的美元引号标签
                tag = sql_content[i:j + 1]  # 包含两端的 $
                in_dollar_quote = True
                dollar_tag = tag
                current.append(sql_content[i:j + 1])
                i = j + 1
                continue
            # 不是合法标签，当作普通字符处理
            current.append(sql_content[i])
            i += 1
            continue

        # 在美元引号块内，检测结束标签
        if in_dollar_quote:
            tag_len = len(dollar_tag)
            if sql_content[i:i + tag_len] == dollar_tag:
                current.append(dollar_tag)
                i += tag_len
                in_dollar_quote = False
                dollar_tag = ""
            else:
                current.append(sql_content[i])
                i += 1
            continue

        # 普通模式：字符串字面量 / 引号标识符开始（E'...' 前缀不能是更长标识符的尾字母）
        if sql_content[i] == "'":
            prev = sql_content[i - 1] if i > 0 else ""
            prev2 = sql_content[i - 2] if i > 1 else ""
            quote_backslash = prev in ("E", "e") and not (prev2.isalnum() or prev2 == "_")
            in_single_quote = True
            current.append("'")
            i += 1
            continue
        if sql_content[i] == '"':
            in_double_quote = True
            current.append('"')
            i += 1
            continue

        # 普通模式：遇到分号则结束当前语句
        if sql_content[i] == ';':
            stmt = "".join(current).strip()
            if stmt and not is_comment_only(stmt):
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(sql_content[i])
        i += 1

    # 处理末尾没有分号的语句
    remaining = "".join(current).strip()
    if remaining and not is_comment_only(remaining):
        statements.append(remaining)

    return statements
