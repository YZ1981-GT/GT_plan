"""统一社会信用代码（USCC）校验器。

校验规则：
1. 长度必须 18 位
2. 字符集：0-9 + A-H, J-N, P-T, U-W, X（排除 I, O, Z, S, V）
3. 模 31 校验码算法：Wi = 3^(i-1) mod 31（i=1..17），C18 = 31 - (Σ(Ci×Wi) mod 31)，余数 31 映射为 0
"""

# USCC 允许字符集（不含 I、O、Z、S、V）
USCC_CHARSET = "0123456789ABCDEFGHJKLMNPQRTUWXY"

# 字符到数值的映射（位置即数值）
_CHAR_TO_VALUE: dict[str, int] = {ch: idx for idx, ch in enumerate(USCC_CHARSET)}

# 权重因子 Wi = 3^(i-1) mod 31，i=1..17
_WEIGHTS: list[int] = [pow(3, i, 31) for i in range(17)]


def validate_uscc(code: str) -> tuple[bool, str | None]:
    """校验统一社会信用代码。

    Args:
        code: 待校验的字符串

    Returns:
        (is_valid, error_message) — 合法时返回 (True, None)，否则返回 (False, 错误消息)
    """
    # 1. 长度检查
    if len(code) != 18:
        return False, "统一社会信用代码必须为 18 位"

    # 2. 字符集检查
    for ch in code:
        if ch not in _CHAR_TO_VALUE:
            return False, "统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）"

    # 3. 模 31 校验码验证
    total = 0
    for i in range(17):
        total += _CHAR_TO_VALUE[code[i]] * _WEIGHTS[i]

    remainder = total % 31
    check_digit = 31 - remainder
    # 余数为 31 时映射为 0
    if check_digit == 31:
        check_digit = 0

    if _CHAR_TO_VALUE[code[17]] != check_digit:
        return False, "统一社会信用代码校验码错误"

    return True, None
