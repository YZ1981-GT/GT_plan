/**
 * alternativeBlockManifestContract.spec.ts — 区块结构清单契约守卫
 *
 * confirmation-alternative-structure-alignment Task 6.2：
 * - Property 10 每套 blockColumnConfigs* 的 sumField 列集合 SHALL 与 ALTERNATIVE_BLOCK_MANIFEST 一致，漂移即失败
 * - Property 8  每个 sourceExtra 区块 SHALL 在 SOURCE_EXTRA_MANIFEST 有条目 + 非空依据（不仅代码注释）
 * - Property 12 createAlternativeConfirmationData 公共面（返回键集合）SHALL 不变
 * - Property 3  splitByDirection 仅标于源模板借贷两表的套（K05/K06/L05/G06 各一处），单表套不强拆
 * - Property 7  H05 四区块全为 sourceExtra（源模板留白），无新增账面区/检查比例列
 */
import { describe, it, expect } from 'vitest'
import {
  ALTERNATIVE_BLOCK_MANIFEST,
  SOURCE_EXTRA_MANIFEST,
  type AltCycleSheet,
} from '../alternativeBlockManifest'
import { createAlternativeConfirmationData, type AltConfig } from '../createAlternativeConfirmationData'

// getSumFields 导出（8 套工厂型；L05 内联未导出 → 不纳入 drift guard）
import { getSumFields as sumD05 } from '../../alternativeD05/blockColumnConfigs'
import { getSumFieldsD06 } from '../../alternativeD06/blockColumnConfigsD06'
import { getSumFieldsF05 } from '../../alternativeF05/blockColumnConfigsF05'
import { getSumFieldsF06 } from '../../alternativeF06/blockColumnConfigsF06'
import { getSumFieldsH05 } from '../../alternativeH05/blockColumnConfigsH05'
import { getSumFieldsK05 } from '../../alternativeK05/blockColumnConfigsK05'
import { getSumFieldsK06 } from '../../alternativeK06/blockColumnConfigsK06'
import { getSumFieldsG06 } from '../../../g0-confirmation/alternativeG06/blockColumnConfigsG06'

const BLOCKS = ['block1', 'block2', 'block3', 'block4'] as const

// getSumFields 可校验的套（L05 排除）
const SUMFIELD_FNS: Partial<Record<AltCycleSheet, (b: string) => string[]>> = {
  D05: sumD05,
  D06: getSumFieldsD06,
  F05: getSumFieldsF05,
  F06: getSumFieldsF06,
  H05: getSumFieldsH05,
  K05: getSumFieldsK05,
  K06: getSumFieldsK06,
  G06: getSumFieldsG06,
}

// ─── Property 10：sumField 列集合 drift guard ───────────────────────────────

describe('Property 10: blockColumnConfigs* sumField 列与 manifest 一致（漂移即失败）', () => {
  for (const [suite, fn] of Object.entries(SUMFIELD_FNS)) {
    it(`${suite} 各区块 getSumFields === manifest.columns`, () => {
      const specs = ALTERNATIVE_BLOCK_MANIFEST[suite as AltCycleSheet]
      for (const block of BLOCKS) {
        const spec = specs.find((s) => s.block === block)
        expect(spec, `${suite}.${block} 应在 manifest 中登记`).toBeTruthy()
        expect(fn!(block), `${suite}.${block} sumField 漂移`).toEqual(spec!.columns)
      }
    })
  }

  it('L05 内联 getSumFields 不纳入 drift guard，但 manifest 仍登记全 4 区块', () => {
    const specs = ALTERNATIVE_BLOCK_MANIFEST.L05
    expect(specs.map((s) => s.block).sort()).toEqual(['block1', 'block2', 'block3', 'block4'])
    for (const s of specs) expect(s.columns.length).toBeGreaterThan(0)
  })
})

// ─── Property 8：源外区块集中登记 ───────────────────────────────────────────

describe('Property 8: 每个 sourceExtra 区块在 SOURCE_EXTRA_MANIFEST 有条目 + 非空依据', () => {
  it('sourceExtra 区块 ↔ SOURCE_EXTRA_MANIFEST 双向一致', () => {
    const fromManifest = new Set<string>()
    for (const [suite, specs] of Object.entries(ALTERNATIVE_BLOCK_MANIFEST)) {
      for (const s of specs) {
        if (s.sourceExtra) {
          fromManifest.add(`${suite}:${s.block}`)
          // 依据非空
          expect(s.sourceExtraReason && s.sourceExtraReason.trim().length > 0, `${suite}:${s.block} 缺 sourceExtraReason`).toBe(true)
        }
      }
    }
    const fromRegistry = new Set(SOURCE_EXTRA_MANIFEST.map((e) => `${e.suite}:${e.block}`))
    expect(fromRegistry).toEqual(fromManifest)
    // 每条登记依据非空
    for (const e of SOURCE_EXTRA_MANIFEST) {
      expect(e.reason && e.reason.trim().length > 0).toBe(true)
    }
  })

  it('已知源外区块覆盖：H05 四块 + K05.block4 + K06.block4 + L05.block4 + G06.block4', () => {
    const keys = new Set(SOURCE_EXTRA_MANIFEST.map((e) => `${e.suite}:${e.block}`))
    for (const k of [
      'H05:block1', 'H05:block2', 'H05:block3', 'H05:block4',
      'K05:block4', 'K06:block4', 'L05:block4', 'G06:block4',
    ]) {
      expect(keys.has(k), `缺源外登记 ${k}`).toBe(true)
    }
  })
})

// ─── Property 3：一张表的套不强拆 ───────────────────────────────────────────

describe('Property 3: splitByDirection 仅标借贷两表套', () => {
  const SPLIT_EXPECTED: Record<string, string | null> = {
    D05: null, D06: null, F05: null, F06: null, H05: null,
    K05: 'block3', K06: 'block3', L05: 'block3', G06: 'block2',
  }
  for (const [suite, expectedBlock] of Object.entries(SPLIT_EXPECTED)) {
    it(`${suite} splitByDirection = ${expectedBlock ?? '（无，保持单表）'}`, () => {
      const specs = ALTERNATIVE_BLOCK_MANIFEST[suite as AltCycleSheet]
      const splitBlocks = specs.filter((s) => s.splitByDirection).map((s) => s.block)
      if (expectedBlock === null) {
        expect(splitBlocks).toEqual([])
      } else {
        expect(splitBlocks).toEqual([expectedBlock])
      }
    })
  }
})

// ─── Property 7：H05 源模板留白 ─────────────────────────────────────────────

describe('Property 7: H05 四区块全为源外增强（源模板留白，无新增结构）', () => {
  it('H05 每个区块 sourceExtra=true 且无 splitByDirection', () => {
    const specs = ALTERNATIVE_BLOCK_MANIFEST.H05
    expect(specs).toHaveLength(4)
    for (const s of specs) {
      expect(s.sourceExtra, `H05.${s.block} 应标 sourceExtra`).toBe(true)
      expect(s.splitByDirection ?? false, `H05.${s.block} 不应拆借贷`).toBe(false)
    }
  })
})

// ─── Property 12：工厂公共面不变 ────────────────────────────────────────────

describe('Property 12: createAlternativeConfirmationData 返回键集合冻结', () => {
  it('公共面键集合与冻结基准一致', () => {
    const minimalConfig: AltConfig = {
      format: 'alternative-surface-test-v1',
      getSumFields: () => [],
      defaultBalance: () => ({}),
      baseAmount: () => 0,
      ratios: [],
      metricRatioKeys: { receipt: 'r1', shipment: 'r2' },
    }
    const core = createAlternativeConfirmationData(minimalConfig)
    const EXPECTED_SURFACE = [
      '_ensureCompanyId', '_ensureRowId', '_generateId', '_getBlockRows',
      '_initFromHtmlData', '_precise',
      'addBlockRow', 'addCompany', 'buildPayload', 'companies', 'deleteBlockRow',
      'deleteCompany', 'getBlockTotal', 'getBlockTotalByDirection', 'getCompletionStatus',
      'getRatio', 'hasAbnormal', 'importCompanies', 'isDirty', 'metrics',
      'selectedCompanyId', 'updateBlockField', 'updateCompany',
    ]
    expect(Object.keys(core).sort()).toEqual(EXPECTED_SURFACE)
    // getBlockTotalByDirection 为 additive 新增（决策 1）
    expect(typeof core.getBlockTotalByDirection).toBe('function')
  })
})
