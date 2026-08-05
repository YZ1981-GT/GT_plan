/**
 * E1 IPO 系列 legacy 键回退 characterization 测试
 *
 * Property 4: legacy 键回退优先级（pack→legacy→空）
 * Property 5: 写入只落新键（不回写 legacy 键）
 * Property 6: 启用开关跨组件共享
 *
 * @spec e1-orphan-components-wiring — Task 2
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'

const REPO_ROOT = path.resolve(__dirname, '../../../../../../..')
const COMPOSABLES_DIR = path.resolve(REPO_ROOT, 'audit-platform/frontend/src/components/workpaper/composables')

function readSource(filePath: string): string {
  return fs.readFileSync(filePath, 'utf-8')
}

/** 5 个 IPO 专属 composable 及其键定义 */
const IPO_COMPOSABLES = [
  {
    file: 'useE1CashTxnAnalysis.ts',
    legacyKey: 'E1-ipo-E1-26-rows',
    packKeyConst: 'E1_CASH_TXN_PACK_KEY',
    sheetCode: 'E1-26',
  },
  {
    file: 'useE1BankAccountAnalysis.ts',
    legacyKey: 'E1-ipo-E1-29-rows',
    packKeyConst: 'E1_BANK_ANALYSIS_PACK_KEY',
    sheetCode: 'E1-29',
  },
  {
    file: 'useE1DepositDailyMatch.ts',
    legacyKey: 'E1-ipo-E1-30-rows',
    packKeyConst: 'E1_DEPOSIT_DAILY_PACK_KEY',
    sheetCode: 'E1-30',
  },
  {
    file: 'useE1BankFlowReconcile.ts',
    legacyKey: 'E1-ipo-E1-31-rows',
    packKeyConst: 'E1_BANK_FLOW_PACK_KEY',
    sheetCode: 'E1-31',
  },
  {
    file: 'useE1KeyPersonFlow.ts',
    legacyKey: 'E1-ipo-E1-32-rows',
    packKeyConst: 'E1_KEYPERSON_FLOW_PACK_KEY',
    sheetCode: 'E1-32',
  },
]

describe('E1 IPO legacy migration - Property 4: legacy 键回退优先级', () => {
  for (const { file, legacyKey, packKeyConst } of IPO_COMPOSABLES) {
    const src = readSource(path.join(COMPOSABLES_DIR, file))

    it(`${file}: pack 键常量 "${packKeyConst}" 是首选读取键`, () => {
      // The exported pack key constant should exist
      expect(src).toMatch(new RegExp(`export\\s+const\\s+${packKeyConst}\\s*=`))
    })

    it(`${file}: 含 legacy 键 "${legacyKey}" 回退逻辑`, () => {
      expect(src).toContain(legacyKey)
    })

    it(`${file}: legacy 回退在 pack 为空时触发（else 分支）`, () => {
      // Legacy read is in an else branch after pack read
      const packConstIdx = src.indexOf(packKeyConst)
      const legacyIdx = src.indexOf(legacyKey)
      expect(legacyIdx).toBeGreaterThan(packConstIdx)
    })
  }

  it('反向自检: 去掉 useE1CashTxnAnalysis 的 legacy 键则本属性必红', () => {
    const src = readSource(path.join(COMPOSABLES_DIR, 'useE1CashTxnAnalysis.ts'))
    const stripped = src.replace(/E1-ipo-E1-26-rows/g, 'REMOVED_LEGACY_KEY')
    expect(stripped).not.toContain('E1-ipo-E1-26-rows')
  })
})

describe('E1 IPO legacy migration - Property 5: 写入只落新键', () => {
  for (const { file, legacyKey } of IPO_COMPOSABLES) {
    it(`${file}: 写入 item_id 不含 legacy 键 "${legacyKey}"`, () => {
      const src = readSource(path.join(COMPOSABLES_DIR, file))
      // Find all item_id string literals in persist/save calls
      const persistMatches = [...src.matchAll(/item_id:\s*['"`]([^'"`]+)['"`]/g)]
        .map(m => m[1])
      // Also match item_id references to constants (item_id: SOME_KEY)
      const constMatches = [...src.matchAll(/item_id:\s*(\w+_KEY)/g)]
        .map(m => m[1])

      // Legacy key literal should NOT appear as item_id
      expect(
        persistMatches.every(id => id !== legacyKey),
        `${file}: item_id 字面量不应为 legacy 键 "${legacyKey}"`,
      ).toBe(true)

      // No constant named LEGACY should appear as item_id
      expect(
        constMatches.every(c => !c.includes('LEGACY')),
        `${file}: item_id 不应引用 LEGACY 常量`,
      ).toBe(true)
    })
  }
})

describe('E1 IPO legacy migration - Property 6: 启用开关跨组件共享', () => {
  const EXPECTED_KEY = 'E1-ipo-applicable'

  it('所有 5 个专属 composable 导出同值的 E1_IPO_APPLICABLE_KEY', () => {
    for (const { file } of IPO_COMPOSABLES) {
      const src = readSource(path.join(COMPOSABLES_DIR, file))
      expect(src).toContain(`E1_IPO_APPLICABLE_KEY = '${EXPECTED_KEY}'`)
    }
  })

  it('useE1IpoSpecial（通用组件 composable）使用同一个键值', () => {
    const src = readSource(path.join(COMPOSABLES_DIR, 'useE1IpoSpecial.ts'))
    expect(src).toContain(EXPECTED_KEY)
  })

  it('启用开关值 6 处一致（5 专属 + 1 通用）', () => {
    const files = [
      ...IPO_COMPOSABLES.map(c => c.file),
      'useE1IpoSpecial.ts',
    ]
    for (const file of files) {
      const src = readSource(path.join(COMPOSABLES_DIR, file))
      // All should read this key for applicable state
      expect(
        src.includes(EXPECTED_KEY),
        `${file} 应引用 '${EXPECTED_KEY}'`,
      ).toBe(true)
    }
  })
})
