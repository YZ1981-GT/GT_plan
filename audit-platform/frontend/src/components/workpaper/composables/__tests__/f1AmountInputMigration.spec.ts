/**
 * F1 金额控件与列头字面守卫（Property 6 / 12，读 SFC 源码）
 *
 * 三条平台铁律：
 * 1. **可编辑金额千分符只能用 `WpAmountInput`** —— element-plus 2.13.6 的
 *    `el-input-number` 不存在 `formatter` prop（双证），`:formatter` 是空操作。
 * 2. **只读金额单一真源 = `stores/displayPrefs.fmtAmount`**，不许各 Tab 自写
 *    `toLocaleString`（会忽略用户的单位/小数位/showZero 偏好）。
 * 3. **列头字面单一真源 = `f1DisclosureSyncPayload` 的常量**，Tab 模板不得写死
 *    `label="期末余额"` 这类字面（写死必与同步载荷分叉）。
 *
 * spec: .kiro/specs/f1-four-table-extraction-and-disclosure-alignment/ R6.4, R9
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const F1_DIR = resolve(__dirname, '../../f1')

/** 本 spec 收口的三个 Tab（四表取数 + 披露结构改造范围） */
const IN_SCOPE = [
  'F1TabDisclosureListed.vue',
  'F1TabDisclosureSoe.vue',
  'F1TabAdjudication.vue',
] as const

/**
 * 尚未收敛 `fmtAmount` 的 F1 文件（**必须写理由**）。
 * 不在本 spec 范围内（无对应测试覆盖，贸然改动风险 > 收益）；后续循环收口时清空。
 */
const FMT_AMOUNT_PENDING: Readonly<Record<string, string>> = {
  'F1CreditCheckTable.vue': '函证核对表，非本 spec 范围（无披露/四表取数改动）',
  'F1TabAdjustment.vue': 'F1-3 调整分录，非本 spec 范围',
  'F1TabAnalysis.vue': 'F1-4 实质性分析，本 spec 只改其取数来源不改渲染',
  'F1TabComprehensiveCheck.vue': 'F1-7 综合检查，非本 spec 范围',
  'F1TabConfirmationProcedure.vue': '函证程序，非本 spec 范围',
  'F1TabDetail.vue': 'F1-2 明细表（宽表 + 列偏好），改动面大，另立',
  'F1TabLongTerm.vue': 'F1-5 长期挂款，非本 spec 范围',
  'F1TabRelatedParty.vue': 'F1-6 关联方，非本 spec 范围',
}

function read(file: string): string {
  return readFileSync(resolve(F1_DIR, file), 'utf-8')
}

/** 去掉 JS 行/块注释与 HTML 注释 —— 否则守卫注释里的反例会被数成真实调用 */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function count(src: string, pattern: RegExp): number {
  return (src.match(pattern) ?? []).length
}

describe('stripComments 自检（防断言空转）', () => {
  it('注释里的反例不会被数成真实调用', () => {
    const fixture = [
      '<!-- 禁止使用 <el-input-number 千分符不生效 -->',
      '/* 历史写法： <el-input-number /> */',
      '// 也不要写 <el-input-number',
      '<WpAmountInput :model-value="row.amount" />',
    ].join('\n')
    expect(fixture).toContain('el-input-number')
    const stripped = stripComments(fixture)
    expect(count(stripped, /<el-input-number/g)).toBe(0)
    expect(count(stripped, /<WpAmountInput/g)).toBe(1)
  })

  it('剥离后仍保留真实模板内容（不是把整个文件清空）', () => {
    const src = stripComments(read('F1TabDisclosureListed.vue'))
    expect(src).toContain('WpAmountInput')
    expect(src.length).toBeGreaterThan(3000)
  })
})

describe('Property 12：披露 Tab 的 el-input-number 归零', () => {
  it.each(['F1TabDisclosureListed.vue', 'F1TabDisclosureSoe.vue'])('%s 无 el-input-number', (file) => {
    const src = stripComments(read(file))
    expect(count(src, /<el-input-number/g), `${file} 仍有 el-input-number`).toBe(0)
  })

  it('披露 Tab 的可编辑金额格均由 WpAmountInput 渲染', () => {
    // 上市：减值准备期末/期初 + ②表账面余额/减值准备 = 4 处
    expect(count(stripComments(read('F1TabDisclosureListed.vue')), /<WpAmountInput/g)).toBe(4)
    // 国企：①逐段坏账准备期末/期初 + ②表期末余额 + ③表减值准备 = 4 处
    expect(count(stripComments(read('F1TabDisclosureSoe.vue')), /<WpAmountInput/g)).toBe(4)
  })

  it('比例 / 账龄 / 笔数类字段不得套用 WpAmountInput（反向边界）', () => {
    for (const file of ['F1TabDisclosureListed.vue', 'F1TabDisclosureSoe.vue']) {
      const src = stripComments(read(file))
      // WpAmountInput 的 model-value 只允许绑定金额字段
      const bindings = [...src.matchAll(/<WpAmountInput[\s\S]{0,200}?:model-value="([^"]+)"/g)]
        .map((m) => m[1])
      expect(bindings.length, file).toBeGreaterThan(0)
      for (const b of bindings) {
        expect(b, `${file} 绑定了非金额字段 ${b}`).not.toMatch(/Pct|pct|Rate|rate|aging|Aging|count|Count/)
      }
    }
  })
})

describe('Property 12：只读金额走 displayPrefs 单一真源', () => {
  it.each(IN_SCOPE)('%s 的 fmtAmount 委托 displayPrefs', (file) => {
    const src = stripComments(read(file))
    expect(src, `${file} 未 import displayPrefs`).toContain('useDisplayPrefsStore')
    expect(src, `${file} fmtAmount 未委托`).toMatch(/return\s+displayPrefs\.fmtAmount\(/)
    // `fmtAmount` **函数体内**不得残留自写的 toLocaleString
    // （`fmtPct` 等百分比格式化不受限 → 必须只截函数体，不能用固定字符窗口，
    //   否则窗口会溢出到下一个函数造成误报）
    const body = /function fmtAmount\([^)]*\)[^{]*\{([^}]*)\}/.exec(src)?.[1]
    expect(body, `${file} 未找到 fmtAmount 函数体（反向自检）`).toBeDefined()
    expect(body ?? '', `${file} 的 fmtAmount 仍自写 toLocaleString`).not.toContain('toLocaleString')
  })

  it('待收敛清单每项都有理由，且不含已收敛文件', () => {
    for (const [file, reason] of Object.entries(FMT_AMOUNT_PENDING)) {
      expect(reason.trim(), `${file} 缺理由`).not.toBe('')
      expect(IN_SCOPE as readonly string[], `${file} 已收敛，应从清单移除`).not.toContain(file)
    }
  })
})

describe('Property 6：列头字面引用常量，不写死', () => {
  /**
   * 只列**被本 spec 修正掉**的旧字面。
   * 🔴 不能把「期末余额」一并禁掉 —— 国企②表源模板 `C17` 字面就是「期末余额」，
   *    那是合法列头（与①表的两级表头父组名「期末数」是两回事）。
   */
  const FORBIDDEN = ['上年年末余额'] as const

  it('披露 Tab 不得写死已被修正的旧列头字面', () => {
    for (const file of ['F1TabDisclosureListed.vue', 'F1TabDisclosureSoe.vue']) {
      const src = stripComments(read(file))
      for (const bad of FORBIDDEN) {
        expect(src.includes(`label="${bad}"`), `${file} 写死了 label="${bad}"`).toBe(false)
      }
    }
  })

  it('披露 Tab 的账龄表列头绑定常量（:label="AGING_..."）', () => {
    for (const file of ['F1TabDisclosureListed.vue', 'F1TabDisclosureSoe.vue']) {
      const src = stripComments(read(file))
      expect(src, file).toContain(':label="AGING_LABEL_COL"')
      expect(src, file).toContain(':label="AGING_GROUPS.end"')
      expect(src, file).toContain(':label="AGING_GROUPS.prior"')
      expect(src, file).toContain(':label="AMOUNT_LABEL"')
      expect(src, file).toContain(':label="PCT_LABEL"')
    }
  })

  it('常量从 f1DisclosureSyncPayload 导入（与同步载荷同源）', () => {
    for (const file of ['F1TabDisclosureListed.vue', 'F1TabDisclosureSoe.vue']) {
      const src = stripComments(read(file))
      expect(src, file).toMatch(/F1_AGING_LABEL_COL[\s\S]{0,400}from '\.\.\/composables\/f1DisclosureSyncPayload'/)
    }
  })
})

describe('披露 Tab 已挂溯源与勾稽面板（杜绝 dead output）', () => {
  it.each(['F1TabDisclosureListed.vue', 'F1TabDisclosureSoe.vue'])('%s 挂载两个面板', (file) => {
    const src = stripComments(read(file))
    expect(src, file).toContain('<F1FourTableSourcePanel')
    expect(src, file).toContain('<F1DisclosureConsistencyPanel')
    expect(src, file).toContain('buildF1ConsistencyChecks')
  })

  it('F1-1 审定表挂载溯源面板 + 「从四表库带入未审数」按钮', () => {
    const src = stripComments(read('F1TabAdjudication.vue'))
    expect(src).toContain('<F1FourTableSourcePanel')
    expect(src).toContain('从四表库带入未审数')
    expect(src).toContain('pullNatureFromTB')
    // 平台铁律：按钮须有 loading + 只读禁用
    expect(src).toMatch(/:loading="pullingFromTb"/)
    expect(src).toMatch(/:disabled="isReadonly"/)
  })
})
