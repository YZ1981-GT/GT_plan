/**
 * USCC 前端校验器单元测试
 *
 * 覆盖：
 * 1. 合法 USCC（构造校验码验证通过）
 * 2. 非法：空字符串、长度错误、禁止字符、校验码错误
 */
import { describe, it, expect } from 'vitest'
import { validateUSCC, USCC_CHARSET } from '../uscc_validator'

/**
 * 辅助函数：根据 17 位前缀计算 USCC 校验码并返回完整 18 位编码
 */
function computeUSCC(prefix: string): string {
  const WEIGHTS: number[] = []
  for (let i = 0; i < 17; i++) {
    let w = 1
    for (let j = 0; j < i; j++) {
      w = (w * 3) % 31
    }
    WEIGHTS.push(w)
  }

  const charToValue: Record<string, number> = {}
  for (let i = 0; i < USCC_CHARSET.length; i++) {
    charToValue[USCC_CHARSET[i]] = i
  }

  let total = 0
  for (let i = 0; i < 17; i++) {
    total += charToValue[prefix[i]] * WEIGHTS[i]
  }
  let checkDigit = 31 - (total % 31)
  if (checkDigit === 31) {
    checkDigit = 0
  }
  return prefix + USCC_CHARSET[checkDigit]
}

describe('validateUSCC — 合法 USCC 通过校验', () => {
  it('全数字前缀构造的合法 USCC 通过', () => {
    const code = computeUSCC('91110000710930451')
    const result = validateUSCC(code)
    expect(result.valid).toBe(true)
    expect(result.message).toBeUndefined()
  })

  it('含字母前缀构造的合法 USCC 通过', () => {
    const code = computeUSCC('11100000MB2XY197A')
    const result = validateUSCC(code)
    expect(result.valid).toBe(true)
    expect(result.message).toBeUndefined()
  })

  it('全零前缀构造的合法 USCC 通过', () => {
    // 全零前缀 → total=0 → remainder=0 → checkDigit=31 → 映射为 0
    const code = computeUSCC('00000000000000000')
    expect(code).toBe('000000000000000000') // checkDigit=0 → char '0'
    const result = validateUSCC(code)
    expect(result.valid).toBe(true)
  })

  it('含高值字符（X Y W）前缀构造的合法 USCC 通过', () => {
    const code = computeUSCC('9XYWU1234567890A1')
    const result = validateUSCC(code)
    expect(result.valid).toBe(true)
  })
})

describe('validateUSCC — 长度错误', () => {
  it('空字符串返回长度错误', () => {
    const result = validateUSCC('')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码必须为 18 位')
  })

  it('17 位返回长度错误', () => {
    const result = validateUSCC('1234567890ABCDEFG')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码必须为 18 位')
  })

  it('19 位返回长度错误', () => {
    const result = validateUSCC('1234567890ABCDEFGH1')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码必须为 18 位')
  })
})

describe('validateUSCC — 字符集错误', () => {
  it('包含小写字母返回字符集错误', () => {
    const result = validateUSCC('91110000710930451a')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）')
  })

  it('包含禁止字符 I 返回字符集错误', () => {
    const result = validateUSCC('91110000I109304510')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）')
  })

  it('包含禁止字符 O 返回字符集错误', () => {
    const result = validateUSCC('91110000O109304510')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）')
  })

  it('包含禁止字符 Z 返回字符集错误', () => {
    const result = validateUSCC('91110000Z109304510')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）')
  })

  it('包含禁止字符 S 返回字符集错误', () => {
    const result = validateUSCC('91110000S109304510')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）')
  })

  it('包含禁止字符 V 返回字符集错误', () => {
    const result = validateUSCC('91110000V109304510')
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码只能包含数字与大写字母（不含 I、O、Z、S、V）')
  })
})

describe('validateUSCC — 校验码错误', () => {
  it('前 17 位合法但第 18 位错误返回校验码错误', () => {
    // 构造一个合法编码然后篡改最后一位
    const valid = computeUSCC('91110000710930451')
    const lastChar = valid[17]
    // 选一个不同的合法字符替换
    const wrongChar = lastChar === '0' ? '1' : '0'
    const tampered = valid.slice(0, 17) + wrongChar
    const result = validateUSCC(tampered)
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码校验码错误')
  })

  it('全 A 前缀 + 错误校验码', () => {
    const valid = computeUSCC('AAAAAAAAAAAAAAAAA')
    // 篡改最后一位
    const wrongChar = valid[17] === 'X' ? 'Y' : 'X'
    const tampered = valid.slice(0, 17) + wrongChar
    const result = validateUSCC(tampered)
    expect(result.valid).toBe(false)
    expect(result.message).toBe('统一社会信用代码校验码错误')
  })
})


// ---------------------------------------------------------------------------
// Task 3.3: 跨语言一致性 — 共享 golden file 测试向量
// ---------------------------------------------------------------------------

import testVectors from '@fixtures/uscc_test_vectors.json'

interface TestVector {
  input: string
  expected_valid: boolean
  expected_message: string | null
}

describe('validateUSCC — golden file 一致性验证', () => {
  it.each(testVectors as TestVector[])(
    'vector: $input → valid=$expected_valid',
    ({ input, expected_valid, expected_message }) => {
      const result = validateUSCC(input)
      expect(result.valid).toBe(expected_valid)
      if (expected_valid) {
        expect(result.message).toBeUndefined()
      } else {
        expect(result.message).toBe(expected_message)
      }
    }
  )
})
