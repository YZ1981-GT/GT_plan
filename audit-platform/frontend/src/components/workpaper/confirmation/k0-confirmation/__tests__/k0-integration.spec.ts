/**
 * K0 管理循环函证集成测试
 *
 * 覆盖全部 Requirements：
 * 1. wp_code_overrides 映射正确性（10条K0→对应componentType）
 * 2. K0-5/K0-6 四区块列配置+增删行+合计行（calcBlockTotal）
 * 3. 往来对账差异（calcReconcileDiff）
 * 4. 检查比例除零安全（期末余额=0→0）
 * 5. VALID_COMPONENT_TYPES + htmlRendererRegistry 包含 k05/k06
 * 6. blockColumnConfigs 正确性（K05/K06各4区块）
 * 7. parseNum 兜底安全
 */
import { describe, it, expect } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'

import {
  calcBlockTotal,
  calcCheckRatio,
  calcRowVariance,
  calcReconcileDiff,
  isAbnormal,
  parseNum,
} from '../composables/useK0FormulaEngine'
import { BLOCK_COLUMN_CONFIGS_K05, getSumFieldsK05, getGroupsK05 } from '../../alternativeK05/blockColumnConfigsK05'
import { BLOCK_COLUMN_CONFIGS_K06, getSumFieldsK06, getGroupsK06 } from '../../alternativeK06/blockColumnConfigsK06'
import { getRendererEntry } from '../../../htmlRendererRegistry'

// --- wp_code_overrides 读取 ---
const overridesPath = path.resolve(
  __dirname,
  '../../../../../../../../backend/app/data/wp_code_overrides.json',
)
const wpCodeOverrides: Record<string, string> = JSON.parse(fs.readFileSync(overridesPath, 'utf-8'))

describe('K0 集成: wp_code_overrides 10条映射', () => {
  const K0_MAPPINGS: [string, string][] = [
    ['K0', 'confirmation-hub'],
    ['K0A', 'a-program-console'],
    ['K0-1', 'confirmation-summary'],
    ['K0-2', 'confirmation-entity-verify'],
    ['K0-3', 'confirmation-followup'],
    ['K0-4', 'confirmation-diff-reconcile'],
    ['K0-5', 'confirmation-alternative-k05'],
    ['K0-6', 'confirmation-alternative-k06'],
    ['K0-7', 'confirmation-reliability'],
    ['K0-8', 'confirmation-fraud-risk'],
  ]

  it.each(K0_MAPPINGS)('wp_code "%s" → componentType "%s"', (code, ct) => {
    expect(wpCodeOverrides[code]).toBe(ct)
  })

  it('K0映射数量恰好10条', () => {
    const k0Keys = Object.keys(wpCodeOverrides).filter(k => /^K0[A\-]?/.test(k) && /^K0/.test(k))
    // K0, K0A, K0-1~K0-8 = 10
    const k0Specific = k0Keys.filter(k => k === 'K0' || k === 'K0A' || /^K0-\d$/.test(k))
    expect(k0Specific.length).toBe(10)
  })
})

describe('K0 集成: htmlRendererRegistry 包含 k05/k06', () => {
  it('confirmation-alternative-k05 已注册', () => {
    const entry = getRendererEntry('confirmation-alternative-k05')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('confirmation-alternative-k05')
    expect(entry?.icon).toBe('🔄')
    expect(entry?.label).toContain('其他应收款')
    expect(entry?.emits).toContain('save')
    expect(entry?.component).toBeDefined()
  })

  it('confirmation-alternative-k06 已注册', () => {
    const entry = getRendererEntry('confirmation-alternative-k06')
    expect(entry).toBeDefined()
    expect(entry?.componentType).toBe('confirmation-alternative-k06')
    expect(entry?.icon).toBe('🔄')
    expect(entry?.label).toContain('其他应付款')
    expect(entry?.emits).toContain('save')
    expect(entry?.component).toBeDefined()
  })
})

describe('K0 集成: K0-5 四区块列配置正确性', () => {
  it('BLOCK_COLUMN_CONFIGS_K05 包含全部4个区块', () => {
    expect(Object.keys(BLOCK_COLUMN_CONFIGS_K05)).toHaveLength(4)
    expect(BLOCK_COLUMN_CONFIGS_K05.block1).toBeDefined()
    expect(BLOCK_COLUMN_CONFIGS_K05.block2).toBeDefined()
    expect(BLOCK_COLUMN_CONFIGS_K05.block3).toBeDefined()
    expect(BLOCK_COLUMN_CONFIGS_K05.block4).toBeDefined()
  })

  it('K0-5 4区块标题正确', () => {
    expect(BLOCK_COLUMN_CONFIGS_K05.block1.title).toContain('期后收款检查')
    expect(BLOCK_COLUMN_CONFIGS_K05.block2.title).toContain('期末余额支持性证据')
    expect(BLOCK_COLUMN_CONFIGS_K05.block3.title).toContain('本期发生额检查')
    expect(BLOCK_COLUMN_CONFIGS_K05.block4.title).toContain('往来对账')
  })

  it('K0-5 每区块都有列配置且含序号+记账凭证+检查证据', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const config = BLOCK_COLUMN_CONFIGS_K05[key]
      expect(config.columns.length).toBeGreaterThan(5)
      expect(config.blockType).toBe(key)
    }
  })

  it('K0-5 每区块含记账凭证5列（voucher_date/voucher_no/business_desc/counter_account/voucher_amount）', () => {
    const voucherFields = ['voucher_date', 'voucher_no', 'business_desc', 'counter_account', 'voucher_amount']
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const fields = BLOCK_COLUMN_CONFIGS_K05[key].columns.map(c => c.field)
      for (const vf of voucherFields) {
        expect(fields).toContain(vf)
      }
    }
  })

  it('K0-5 区块④含对账差异列（reconcile_diff, type=formula）', () => {
    const diffCol = BLOCK_COLUMN_CONFIGS_K05.block4.columns.find(c => c.field === 'reconcile_diff')
    expect(diffCol).toBeDefined()
    expect(diffCol?.type).toBe('formula')
  })

  it('K0-5 getSumFieldsK05 返回金额合计列', () => {
    const sumFields1 = getSumFieldsK05('block1')
    expect(sumFields1.length).toBeGreaterThan(0)
    expect(sumFields1).toContain('voucher_amount')
  })

  it('K0-5 getGroupsK05 返回列分组（记账凭证+银行回单）', () => {
    const groups1 = getGroupsK05('block1')
    expect(groups1).toContain('记账凭证')
    expect(groups1).toContain('银行回单')
  })

  it('K0-5 每区块首列为序号列（seq）', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      expect(BLOCK_COLUMN_CONFIGS_K05[key].columns[0].field).toBe('seq')
    }
  })

  it('K0-5 每区块都有 is_abnormal 和 ref_index 列', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const fields = BLOCK_COLUMN_CONFIGS_K05[key].columns.map(c => c.field)
      expect(fields).toContain('is_abnormal')
      expect(fields).toContain('ref_index')
    }
  })

  it('K0-5 全部4区块都有 tips 字段', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      expect(BLOCK_COLUMN_CONFIGS_K05[key].tips).toBeDefined()
      expect(BLOCK_COLUMN_CONFIGS_K05[key].tips!.length).toBeGreaterThan(0)
    }
  })
})

describe('K0 集成: K0-6 四区块列配置正确性', () => {
  it('BLOCK_COLUMN_CONFIGS_K06 包含全部4个区块', () => {
    expect(Object.keys(BLOCK_COLUMN_CONFIGS_K06)).toHaveLength(4)
    expect(BLOCK_COLUMN_CONFIGS_K06.block1).toBeDefined()
    expect(BLOCK_COLUMN_CONFIGS_K06.block2).toBeDefined()
    expect(BLOCK_COLUMN_CONFIGS_K06.block3).toBeDefined()
    expect(BLOCK_COLUMN_CONFIGS_K06.block4).toBeDefined()
  })

  it('K0-6 4区块标题正确（期后付款/余额证据/发生额/对账）', () => {
    expect(BLOCK_COLUMN_CONFIGS_K06.block1.title).toContain('期后付款检查')
    expect(BLOCK_COLUMN_CONFIGS_K06.block2.title).toContain('期末余额支持性证据')
    expect(BLOCK_COLUMN_CONFIGS_K06.block3.title).toContain('本期发生额检查')
    expect(BLOCK_COLUMN_CONFIGS_K06.block4.title).toContain('往来对账')
  })

  it('K0-6 每区块都有列配置且非空', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const config = BLOCK_COLUMN_CONFIGS_K06[key]
      expect(config.columns.length).toBeGreaterThan(5)
      expect(config.blockType).toBe(key)
    }
  })

  it('K0-6 区块④含对账差异列（reconcileDiff）', () => {
    const block4Fields = BLOCK_COLUMN_CONFIGS_K06.block4.columns.map(c => c.field)
    expect(block4Fields).toContain('reconcileDiff')
  })

  it('K0-6 getSumFieldsK06 返回金额合计列', () => {
    const sumFields1 = getSumFieldsK06('block1')
    expect(sumFields1.length).toBeGreaterThan(0)
    expect(sumFields1).toContain('amount')
  })

  /**
   * 🔴 改写记录（k0-confirmation-source-alignment R7.1，2026-08-07）：
   *    原断言 `toContain('付款审批')` 锁定的是**改造前**的段头用词；源模板
   *    `K0-6!F15` 逐字为「付款审批单」（openpyxl 直读，后端
   *    `test_k0_source_template_facts.py::ALT_BLOCK1_EVIDENCE` 是裁决者）。
   *    段头/叶子 label 已对齐源模板，**字段名一个未动**。
   */
  it('K0-6 getGroupsK06 返回列分组（记账凭证 + 付款审批单 + 银行回单）', () => {
    const groups1 = getGroupsK06('block1')
    expect(groups1).toContain('记账凭证')
    expect(groups1).toContain('付款审批单')
    expect(groups1).toContain('银行回单')
    // 反向锁：旧用词不得复活（否则与源模板再次漂移）
    expect(groups1).not.toContain('付款审批')
  })

  it('K0-6 每区块首列为序号列（seq）', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      expect(BLOCK_COLUMN_CONFIGS_K06[key].columns[0].field).toBe('seq')
    }
  })

  it('K0-6 每区块都有 is_abnormal 和 ref_index 列', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      const fields = BLOCK_COLUMN_CONFIGS_K06[key].columns.map(c => c.field)
      expect(fields).toContain('is_abnormal')
      expect(fields).toContain('ref_index')
    }
  })

  it('K0-6 全部4区块都有 tips 字段', () => {
    for (const key of ['block1', 'block2', 'block3', 'block4']) {
      expect(BLOCK_COLUMN_CONFIGS_K06[key].tips).toBeDefined()
      expect(BLOCK_COLUMN_CONFIGS_K06[key].tips!.length).toBeGreaterThan(0)
    }
  })
})

describe('K0 集成: K0-5/K0-6 四区块增删行+合计行', () => {
  it('calcBlockTotal 正确求和多行金额', () => {
    const amounts = [100, 200, 300, 50.5]
    expect(calcBlockTotal(amounts)).toBeCloseTo(650.5, 8)
  })

  it('calcBlockTotal 空数组返回0', () => {
    expect(calcBlockTotal([])).toBe(0)
  })

  it('calcBlockTotal 含NaN兜底为0', () => {
    expect(calcBlockTotal([100, NaN, 200])).toBeCloseTo(300, 8)
  })

  it('模拟增删行后合计正确', () => {
    // 模拟区块1的行数据
    let rows = [{ voucher_amount: 1000 }, { voucher_amount: 2000 }]
    let total = calcBlockTotal(rows.map(r => r.voucher_amount))
    expect(total).toBe(3000)

    // 新增一行
    rows.push({ voucher_amount: 500 })
    total = calcBlockTotal(rows.map(r => r.voucher_amount))
    expect(total).toBe(3500)

    // 删除第一行
    rows = rows.slice(1)
    total = calcBlockTotal(rows.map(r => r.voucher_amount))
    expect(total).toBe(2500)
  })
})

describe('K0 集成: 往来对账差异（calcReconcileDiff）', () => {
  it('calcReconcileDiff(100, 80) === 20', () => {
    expect(calcReconcileDiff(100, 80)).toBe(20)
  })

  it('calcReconcileDiff(v, v) === 0（自身对账无差异）', () => {
    expect(calcReconcileDiff(500, 500)).toBe(0)
    expect(calcReconcileDiff(0, 0)).toBe(0)
    expect(calcReconcileDiff(-100, -100)).toBe(0)
  })

  it('对账差异可为负数（对方余额>本方余额）', () => {
    expect(calcReconcileDiff(80, 100)).toBe(-20)
  })

  it('区块④对账差异列类型为formula（K05 reconcile_diff）', () => {
    const diffCol = BLOCK_COLUMN_CONFIGS_K05.block4.columns.find(c => c.field === 'reconcile_diff')
    expect(diffCol).toBeDefined()
    expect(diffCol?.type).toBe('formula')
  })
})

describe('K0 集成: 检查比例除零安全', () => {
  it('期末余额=0时，检查比例返回0', () => {
    expect(calcCheckRatio(100, 0)).toBe(0)
  })

  it('期末余额<0时，检查比例返回0', () => {
    expect(calcCheckRatio(100, -50)).toBe(0)
  })

  it('期末余额>0时，正常计算比例', () => {
    expect(calcCheckRatio(100, 200)).toBeCloseTo(0.5, 8)
    expect(calcCheckRatio(200, 200)).toBeCloseTo(1.0, 8)
    expect(calcCheckRatio(300, 200)).toBeCloseTo(1.5, 8)
  })

  it('已检查金额=0、余额>0时，比例=0', () => {
    expect(calcCheckRatio(0, 100)).toBe(0)
  })
})

describe('K0 集成: 异常判定（isAbnormal）', () => {
  it('isAbnormal(0) === false（无差异不异常）', () => {
    expect(isAbnormal(0)).toBe(false)
  })

  it('isAbnormal(0.01) === true（有差异即异常）', () => {
    expect(isAbnormal(0.01)).toBe(true)
  })

  it('isAbnormal(-5) === true（负差异也异常）', () => {
    expect(isAbnormal(-5)).toBe(true)
  })

  it('行差异为0时判定不异常', () => {
    const variance = calcRowVariance(100, 100)
    expect(isAbnormal(variance)).toBe(false)
  })

  it('行差异非0时判定异常', () => {
    const variance = calcRowVariance(100, 99)
    expect(isAbnormal(variance)).toBe(true)
  })
})

describe('K0 集成: parseNum 兜底安全', () => {
  it('NaN → 0', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it('Infinity → 0', () => {
    expect(parseNum(Infinity)).toBe(0)
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('null/undefined → 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
  })

  it('有效数字字符串 → 数值', () => {
    expect(parseNum('123.45')).toBe(123.45)
  })

  it('空字符串 → 0', () => {
    expect(parseNum('')).toBe(0)
  })
})
