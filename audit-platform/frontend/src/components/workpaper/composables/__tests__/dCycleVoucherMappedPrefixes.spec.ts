/**
 * dCycleVoucherMappedPrefixes.spec.ts — D 循环凭证检查映射码优先级守卫
 *
 * spec: voucher-attach-account-mapping-closure
 * Requirements: R1.3（向后兼容 — inject null → fallback）, R2.1（accountPrefixes 来自 AccountScope）
 * Design: §四.2 — 映射码优先级守卫（三层降级）
 *
 * 验证两件事：
 * 1. **dSlotQueryCodes 三层降级逻辑**：query_codes → standard_codes/fallback → 兜底码
 * 2. **源码级接线**：D3~D7 凭证检查子组件正确走 inject → dSlotQueryCodes → pullSamplesForWorkpaper
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

import {
  D_SLOT_GROSS,
  type DTbSourceCodes,
  dSlotQueryCodes,
  dSlotAccountCode,
  dCycleScope,
} from '../dCycleAccountScope'

// ─── helpers ────────────────────────────────────────────────────────────

/** 后端 SlotAmounts 形态的槽载荷构造器 */
function mkSlot(over: Record<string, unknown> = {}) {
  return {
    key: D_SLOT_GROSS,
    found: true,
    state: 'ok',
    query_codes: ['1122'],
    tb_rows_count: 4,
    prefix_mismatch: false,
    opening: 100,
    closing: 200,
    dropped: [],
    warnings: [],
    ...over,
  }
}

function mkPayload(
  slots: Record<string, unknown>,
  extra: Record<string, unknown> = {},
) {
  return { slots, ...extra } as DTbSourceCodes
}

/** 每个 D 循环的 gross 兜底码（逐字对照 SPECS 声明） */
const D_FALLBACKS: Record<string, string> = {
  D1: '1121',
  D2: '1122',
  D3: '2203',
  D4: '6001',
  D5: '1124',
  D6: '1141',
  D7: '2205',
}

// ─── 三层降级逻辑 ────────────────────────────────────────────────────────

describe('映射码优先级：三层降级（query_codes → standard_codes → 兜底码）', () => {
  it.each(Object.entries(D_FALLBACKS))(
    '%s: 有 query_codes → 取 query_codes（映射码）',
    (wp, _fallback) => {
      const mapped = [`${_fallback}.01`, `${_fallback}.02`]
      const src = mkPayload({ gross: mkSlot({ query_codes: mapped }) })
      expect(dSlotQueryCodes(wp, src)).toEqual(mapped)
    },
  )

  it.each(Object.entries(D_FALLBACKS))(
    '%s: src=null → 退兜底码',
    (wp, fallback) => {
      const codes = dSlotQueryCodes(wp, null)
      expect(codes).toContain(fallback)
      expect(codes.length).toBeGreaterThan(0)
    },
  )

  it.each(Object.entries(D_FALLBACKS))(
    '%s: src=undefined → 退兜底码（同 null 向后兼容）',
    (wp, fallback) => {
      expect(dSlotQueryCodes(wp, undefined)).toContain(fallback)
    },
  )

  it.each(Object.entries(D_FALLBACKS))(
    '%s: 空 query_codes + 空 slots → 退兜底码',
    (wp, fallback) => {
      // 模拟 render 下发了载荷但 slots 里没有 query_codes（历史形态 / 异常态）
      const src = mkPayload({ gross: mkSlot({ query_codes: [] }) })
      // query_codes 空 → dSlotQueryCodes 退到共享工厂 → 工厂按 standard_codes 判
      // → 归一后 standard_codes 也空（因为 query_codes 空 → 投影也空）
      // → 走兜底码
      const codes = dSlotQueryCodes(wp, src)
      expect(codes).toContain(fallback)
    },
  )

  it('有 query_codes 时，与兜底码可以不同（映射码的意义）', () => {
    // 模拟企业用 110201 而非标准码 1122 的场景
    const customerCodes = ['110201', '110202']
    const src = mkPayload({ gross: mkSlot({ query_codes: customerCodes }) })
    const result = dSlotQueryCodes('D2', src)
    expect(result).toEqual(customerCodes)
    expect(result).not.toContain('1122') // 不含兜底标准码
  })

  it('dSlotAccountCode 返回首个码（请求参数 / 回写 TB 用）', () => {
    const src = mkPayload({ gross: mkSlot({ query_codes: ['AAA', 'BBB'] }) })
    expect(dSlotAccountCode('D3', src)).toBe('AAA')
    expect(dSlotAccountCode('D3', null)).toBe('2203') // 兜底
  })

  it('未登记循环 → 空数组，不凭空造前缀', () => {
    expect(dSlotQueryCodes('XX', null)).toEqual([])
    expect(dSlotAccountCode('XX', null)).toBe('')
    // 🔴 即使 src 有 query_codes，dSlotOf 也能从 slots 取到（与 wpCode 无关），
    // 因为 slot 按键名匹配不按循环名。这是正确行为：运行态有数据就用数据。
    // 未登记循环 + 无 src 才是「不凭空造前缀」的判据。
  })

  it('未登记循环 + 有载荷 → 仍能取到 query_codes（运行态数据优先）', () => {
    // dSlotOf 按 slotKey 取槽，不依赖 wpCode 登记 → 运行态有码就返回
    const src = mkPayload({ gross: mkSlot({ query_codes: ['9999'] }) })
    expect(dSlotQueryCodes('XX', src)).toEqual(['9999'])
  })
})

// ─── 共享工厂 queryCodes 也走同逻辑 ──────────────────────────────────────

describe('共享工厂 queryCodes 的 standard_codes 中间层', () => {
  it('工厂 queryCodes 有 standard_codes 时取 standard_codes', () => {
    const scope = dCycleScope('D3')!
    // 构造扁平形态（历史/语义共存）：只有 gross_standard，无 slots
    const src: DTbSourceCodes = {
      gross_standard: ['2203', '2203.01'],
    }
    // 工厂走扁平 → slotOf 还原成 slot → queryCodes 取 standard_codes
    expect(scope.queryCodes(src, D_SLOT_GROSS)).toEqual(['2203', '2203.01'])
  })

  it('工厂 queryCodes 无 standard_codes 时退兜底码', () => {
    const scope = dCycleScope('D3')!
    expect(scope.queryCodes(null, D_SLOT_GROSS)).toEqual(['2203'])
    expect(scope.queryCodes(undefined, D_SLOT_GROSS)).toEqual(['2203'])
  })

  it('工厂 queryCodes：空 standard_codes → 兜底码', () => {
    const scope = dCycleScope('D3')!
    const src: DTbSourceCodes = { gross_standard: [] }
    expect(scope.queryCodes(src, D_SLOT_GROSS)).toEqual(['2203'])
  })
})

// ─── 源码级接线守卫 ──────────────────────────────────────────────────────

const WP_ROOT = path.resolve(__dirname, '../..')

/**
 * D 循环凭证检查子组件清单（Task 2 已接入 inject 的 5 个）。
 *
 * 🔴 D2TabVoucherCheck 不在此列 —— D2 当前走 `dCycleScope('D2')?.queryCodes()` 直接取
 * 兜底码（见其注释「本组件无 `tbSourceCodes` prop ⇒ 走兜底码」），不经 inject。
 * D2 属后续批次处理范围。
 */
const WIRED_COMPONENTS: Array<{
  file: string
  wp: string
  desc: string
}> = [
  {
    file: 'd3/D3TabVoucherCheck.vue',
    wp: 'D3',
    desc: 'D3 预收款项凭证检查',
  },
  {
    file: 'd4/inspection/D4TabVoucherCheck.vue',
    wp: 'D4',
    desc: 'D4 营业收入发生检查',
  },
  {
    file: 'd5/D5TabVoucherCheck.vue',
    wp: 'D5',
    desc: 'D5 应收款项融资凭证检查',
  },
  {
    file: 'd6/D6TabVoucherCheck.vue',
    wp: 'D6',
    desc: 'D6 合同资产凭证检查',
  },
  {
    file: 'd7/D7TabVoucherCheck.vue',
    wp: 'D7',
    desc: 'D7 合同负债凭证检查',
  },
]

/** 剔注释（与 samplingAccountCodeSource.spec.ts 同口径） */
function stripComments(src: string): string {
  return src
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^[ \t]*\/\/.*$/gm, '')
    .replace(/([^:])\/\/[^\n'"`]*$/gm, '$1')
}

describe('源码级接线：D3~D7 凭证检查 inject→dSlotQueryCodes→pullSamplesForWorkpaper', () => {
  for (const { file, wp, desc } of WIRED_COMPONENTS) {
    describe(desc, () => {
      const fullPath = path.join(WP_ROOT, file)
      const raw = fs.readFileSync(fullPath, 'utf-8')
      const src = stripComments(raw)

      it('文件存在且可读（路径不陈旧）', () => {
        expect(fs.existsSync(fullPath), `${file} 不存在`).toBe(true)
        expect(src.length).toBeGreaterThan(100)
      })

      it('使用 inject("tbSourceCodes", null) 取映射码', () => {
        // 匹配 inject<Ref<any> | null>('tbSourceCodes', null) 或类似写法
        expect(src).toMatch(/inject\s*[<(].*['"]tbSourceCodes['"]/)
      })

      it(`调用 dSlotQueryCodes('${wp}', ...)`, () => {
        const pattern = new RegExp(`dSlotQueryCodes\\s*\\(\\s*'${wp}'`)
        expect(src).toMatch(pattern)
      })

      it('pullSamplesForWorkpaper 的 prefixes 参数来自 computed dSlotQueryCodes 结果', () => {
        // 验证两处接线：
        // (1) 有一个 computed 引用 dSlotQueryCodes 的结果
        // (2) pullSamplesForWorkpaper 调用存在
        expect(src).toContain('pullSamplesForWorkpaper')
        expect(src).toMatch(/dSlotQueryCodes/)
        // 且 computed 变量名包含 ACCOUNT_PREFIXES（D3~D7 都用 Dx_ACCOUNT_PREFIXES）
        const prefixVar = `${wp}_ACCOUNT_PREFIXES`
        expect(src).toContain(prefixVar)
      })

      it('不含硬编码科目前缀字面量作为 pullSamplesForWorkpaper 的参数', () => {
        // 找 pullSamplesForWorkpaper 的调用行，确认第4参数不是字面量数组
        const lines = src.split('\n')
        const callLines = lines.filter((l) =>
          l.includes('pullSamplesForWorkpaper'),
        )
        for (const line of callLines) {
          // 不应有 ['1122'] 或 ['2203'] 之类的字面量数组作参数
          expect(line).not.toMatch(
            /pullSamplesForWorkpaper\s*\([^)]*\[\s*['"][0-9]/,
          )
        }
      })
    })
  }
})

// ─── D2 当前状态的反向自检（确认 D2 走的是另一条路径）──────────────────────

describe('D2 现状：走 dCycleScope 直接取兜底码（不走 inject）', () => {
  it('D2TabVoucherCheck 不含 inject("tbSourceCodes")', () => {
    const d2Path = path.join(WP_ROOT, 'd2/D2TabVoucherCheck.vue')
    if (!fs.existsSync(d2Path)) {
      // D2 可能在后续批次才改
      return
    }
    const src = stripComments(fs.readFileSync(d2Path, 'utf-8'))
    // D2 当前不走 inject('tbSourceCodes') —— 走的是 dCycleScope('D2')?.queryCodes()
    expect(src).not.toMatch(/inject\s*[<(].*['"]tbSourceCodes['"]/)
    expect(src).toContain("dCycleScope('D2')")
  })
})
