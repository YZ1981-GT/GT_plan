/**
 * 统一社会信用代码（USCC）前端校验器
 *
 * 校验规则（与后端 backend/app/services/uscc_validator.py 等价实现）：
 * 1. 长度必须 18 位
 * 2. 字符集：0-9 + A-H, J-N, P-T, U-W, X（排除 I, O, Z, S, V）
 * 3. 模 31 校验码算法：Wi = 3^(i-1) mod 31（i=1..17），C18 = 31 - (Σ(Ci×Wi) mod 31)，余数 31 映射为 0
 */

/** USCC 允许字符集（不含 I、O、Z、S、V） */
export const USCC_CHARSET = '0123456789ABCDEFGHJKLMNPQRTUWXY'

/** 字符到数值的映射（位置即数值） */
const CHAR_TO_VALUE: Record<string, number> = {}
for (let i = 0; i < USCC_CHARSET.length; i++) {
  CHAR_TO_VALUE[USCC_CHARSET[i]] = i
}

/** 权重因子 Wi = 3^(i-1) mod 31，i=1..17 */
const WEIGHTS: number[] = []
for (let i = 0; i < 17; i++) {
  // 计算 3^i mod 31
  let w = 1
  for (let j = 0; j < i; j++) {
    w = (w * 3) % 31
  }
  WEIGHTS.push(w)
}

export interface USCCValidationResult {
  valid: boolean
  message?: string
}

/**
 * 校验统一社会信用代码
 *
 * @param code 待校验的字符串
 * @returns { valid: true } 或 { valid: false, message: '错误消息' }
 */
export function validateUSCC(code: string): USCCValidationResult {
  // 1. 长度检查
  if (code.length !== 18) {
    return { valid: false, message: '统一社会信用代码必须为 18 位' }
  }

  // 2. 字符集检查
  for (const ch of code) {
    if (!(ch in CHAR_TO_VALUE)) {
      return { valid: false, message: '统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）' }
    }
  }

  // 3. 模 31 校验码验证
  let total = 0
  for (let i = 0; i < 17; i++) {
    total += CHAR_TO_VALUE[code[i]] * WEIGHTS[i]
  }

  const remainder = total % 31
  let checkDigit = 31 - remainder
  // 余数为 31 时映射为 0
  if (checkDigit === 31) {
    checkDigit = 0
  }

  if (CHAR_TO_VALUE[code[17]] !== checkDigit) {
    return { valid: false, message: '统一社会信用代码校验码错误' }
  }

  return { valid: true }
}
