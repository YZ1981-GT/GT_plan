/**
 * 公式语法解析器测试。
 *
 * spec: formula-management-ux-improvements · A 批 · Task A2
 */
import { describe, it, expect } from 'vitest'
import { tokenize, validate, cursorContext, knownFunctions } from '../formulaSyntaxParser'

// ── tokenize ────────────────────────────────────────────────────────────────

describe('tokenize', () => {
  it('解析简单 TB 公式', () => {
    const tokens = tokenize("TB('1001','期末余额')")
    const types = tokens.map(t => t.type)
    expect(types).toEqual(['function', 'paren', 'string', 'comma', 'string', 'paren'])
    expect(tokens[0].value).toBe('TB')
    expect(tokens[2].value).toBe("'1001'")
    expect(tokens[4].value).toBe("'期末余额'")
  })

  it('解析多函数混合运算', () => {
    const tokens = tokenize("TB('1001','期末余额') + ROW('BS-001')")
    const funcs = tokens.filter(t => t.type === 'function')
    expect(funcs).toHaveLength(2)
    expect(funcs[0].value).toBe('TB')
    expect(funcs[1].value).toBe('ROW')
    expect(tokens.some(t => t.type === 'operator' && t.value === '+')).toBe(true)
  })

  it('解析数字常量', () => {
    const tokens = tokenize("ROW('BS-001') * 0.5")
    const nums = tokens.filter(t => t.type === 'number')
    expect(nums).toHaveLength(1)
    expect(nums[0].value).toBe('0.5')
  })

  it('标记未知函数', () => {
    const tokens = tokenize("UNKNOWN('arg')")
    expect(tokens[0].type).toBe('unknown')
    expect(tokens[0].error).toContain('未知函数')
  })

  it('标记未闭合引号', () => {
    // 末尾缺右引号：TB('1001','期末余额
    const tokens = tokenize("TB('1001','期末余额")
    const errTokens = tokens.filter(t => t.error)
    expect(errTokens.length).toBeGreaterThan(0)
    expect(errTokens[0].error).toContain('未闭合')
  })

  it('解析等号前缀（Excel 惯例）', () => {
    const tokens = tokenize("=TB('1001','期末余额')")
    expect(tokens[0].type).toBe('operator')
    expect(tokens[0].value).toBe('=')
    expect(tokens[1].type).toBe('function')
  })

  it('解析空串不报错', () => {
    const tokens = tokenize('')
    expect(tokens).toEqual([])
  })

  it('解析纯空白', () => {
    const tokens = tokenize('   ')
    expect(tokens).toHaveLength(1)
    expect(tokens[0].type).toBe('whitespace')
  })

  it('解析 WP 三参形式', () => {
    const tokens = tokenize("WP('D2','坏账准备明细表D2-3','期末余额')")
    const funcs = tokens.filter(t => t.type === 'function')
    expect(funcs).toHaveLength(1)
    expect(funcs[0].value).toBe('WP')
    const strings = tokens.filter(t => t.type === 'string')
    expect(strings).toHaveLength(3)
  })

  it('解析 SUM_ROW', () => {
    const tokens = tokenize("SUM_ROW('BS-001','BS-010')")
    expect(tokens[0].type).toBe('function')
    expect(tokens[0].value).toBe('SUM_ROW')
  })

  it('解析比较运算符', () => {
    const tokens = tokenize("TB('1001','期末') >= 0")
    const ops = tokens.filter(t => t.type === 'operator')
    expect(ops.some(o => o.value === '>=')).toBe(true)
  })
})

// ── validate ────────────────────────────────────────────────────────────────

describe('validate', () => {
  it('正确公式返回 valid', () => {
    const result = validate("TB('1001','期末余额')")
    expect(result.valid).toBe(true)
    expect(result.errors).toEqual([])
    expect(result.functions).toHaveLength(1)
    expect(result.functions[0].name).toBe('TB')
    expect(result.functions[0].args).toEqual(["'1001'", "'期末余额'"])
  })

  it('空串视为 valid', () => {
    expect(validate('').valid).toBe(true)
    expect(validate('  ').valid).toBe(true)
  })

  it('未闭合括号报错', () => {
    const result = validate("TB('1001','期末余额'")
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.message.includes('未闭合'))).toBe(true)
  })

  it('多余右括号报错', () => {
    const result = validate("TB('1001','期末余额'))")
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.message.includes('多余'))).toBe(true)
  })

  it('未知函数名报错', () => {
    const result = validate("BOGUS('arg')")
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.message.includes('未知函数'))).toBe(true)
  })

  it('TB 参数数量错误', () => {
    const result = validate("TB('1001')")
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.message.includes('2 个参数'))).toBe(true)
  })

  it('TB 参数过多', () => {
    const result = validate("TB('1001','期末','多余')")
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.message.includes('2 个参数'))).toBe(true)
  })

  it('ROW 只需 1 个参数', () => {
    const r1 = validate("ROW('BS-001')")
    expect(r1.valid).toBe(true)
    const r2 = validate("ROW('BS-001','多余')")
    expect(r2.valid).toBe(false)
  })

  it('WP 接受 2~3 个参数', () => {
    expect(validate("WP('D2','审定数')").valid).toBe(true)
    expect(validate("WP('D2','sheet','坐标')").valid).toBe(true)
    expect(validate("WP('D2')").valid).toBe(false)
  })

  it('复合公式（多函数+运算符）', () => {
    const result = validate("TB('1001','期末余额') + ROW('BS-001') * 0.5")
    expect(result.valid).toBe(true)
    expect(result.functions).toHaveLength(2)
  })

  it('函数后缺括号报错', () => {
    const result = validate("TB")
    expect(result.valid).toBe(false)
    expect(result.errors.some(e => e.message.includes('缺少'))).toBe(true)
  })

  it('提取嵌套公式的函数列表', () => {
    const result = validate("REPORT('BS-002','期末') + NOTE('货币资金','合计')")
    expect(result.functions).toHaveLength(2)
    expect(result.functions[0].name).toBe('REPORT')
    expect(result.functions[1].name).toBe('NOTE')
  })

  it('未闭合引号也算 invalid', () => {
    const result = validate("TB('1001,'期末余额')")
    expect(result.valid).toBe(false)
  })
})

// ── cursorContext ────────────────────────────────────────────────────────────

describe('cursorContext', () => {
  it('光标在 TB 第一个参数位', () => {
    const ctx = cursorContext("TB('", 4)
    expect(ctx).toEqual({ funcName: 'TB', argIndex: 0 })
  })

  it('光标在 TB 第二个参数位', () => {
    const ctx = cursorContext("TB('1001',", 10)
    expect(ctx).toEqual({ funcName: 'TB', argIndex: 1 })
  })

  it('光标不在函数内', () => {
    const ctx = cursorContext("TB('1001','期末') + ", 20)
    expect(ctx).toBeNull()
  })

  it('光标在 WP 第三个参数位', () => {
    const ctx = cursorContext("WP('D2','sheet',", 17)
    expect(ctx).toEqual({ funcName: 'WP', argIndex: 2 })
  })

  it('光标在嵌套函数内', () => {
    // 嵌套场景：光标在 ROW 的参数里
    const ctx = cursorContext("TB('1001','期末') + ROW('", 25)
    expect(ctx).toEqual({ funcName: 'ROW', argIndex: 0 })
  })
})

// ── knownFunctions ──────────────────────────────────────────────────────────

describe('knownFunctions', () => {
  it('返回非空列表', () => {
    const fns = knownFunctions()
    expect(fns.length).toBeGreaterThan(0)
  })

  it('包含 TB', () => {
    expect(knownFunctions().some(f => f.name === 'TB')).toBe(true)
  })

  it('每个函数有 description', () => {
    for (const f of knownFunctions()) {
      expect(f.description).toBeTruthy()
    }
  })
})


// ── formula-settings-wiring-closure：新增函数对齐 ────────────────────────

describe('新增函数识别与校验（wiring-closure T11）', () => {
  it('SUM_TB 被识别为 function（非 unknown）', () => {
    const tokens = tokenize("SUM_TB('1001~1099','期末余额')")
    expect(tokens[0].type).toBe('function')
    expect(tokens[0].value).toBe('SUM_TB')
  })

  it('SUM_TB 参数校验 = 2', () => {
    expect(validate("SUM_TB('1001~1099','期末余额')").valid).toBe(true)
    expect(validate("SUM_TB('1001~1099')").valid).toBe(false)
  })

  it('PREV 被识别（PRIOR 的官方名称）', () => {
    expect(validate("PREV('1001','期末余额','上期')").valid).toBe(true)
    expect(validate("PREV('1001')").valid).toBe(false)  // 至少 2 参
  })

  it('ABS / ROUND / MAX / MIN / IF', () => {
    expect(validate("ABS(ROW('BS-001'))").valid).toBe(true)
    expect(validate("ROUND(TB('1001','期末余额'), 2)").valid).toBe(true)
    expect(validate("MAX(ROW('BS-001'), 0)").valid).toBe(true)
    expect(validate("MIN(ROW('BS-001'), 0)").valid).toBe(true)
    expect(validate("IF(ROW('BS-001'), 0, 1)").valid).toBe(true)
    // IF 需要 3 个参数
    expect(validate("IF(ROW('BS-001'), 0)").valid).toBe(false)
  })

  it('knownFunctions 包含全部 16 个', () => {
    const names = knownFunctions().map(f => f.name)
    for (const fn of ['TB', 'SUM_TB', 'WP', 'NOTE', 'ROW', 'SUM_ROW', 'REPORT',
      'ADJ', 'AUX', 'PREV', 'PRIOR', 'ABS', 'ROUND', 'MAX', 'MIN', 'IF']) {
      expect(names).toContain(fn)
    }
  })

  it('cursorContext 在 SUM_TB 参数位正确', () => {
    const ctx = cursorContext("SUM_TB('1001~1099',", 20)
    expect(ctx).toEqual({ funcName: 'SUM_TB', argIndex: 1 })
  })
})
