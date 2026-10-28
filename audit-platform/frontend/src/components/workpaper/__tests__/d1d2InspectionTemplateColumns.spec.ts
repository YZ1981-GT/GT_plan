/**
 * D2-6 / D2-11 / D2-12 / D2-13 与 D1-8 背书表按模板接列（spec oo-writeback-template-parity-closure R3 批 B2b）。
 *
 * 契约按模板声明的列前端原来没有：D2-6 发生时间及账龄 / 期后回款 / 索引号（L 原接「备注」）、D2-11 收回方式 /
 * 原确定坏账准备的依据 / 累计已计提 / 应收账款性质 / 是否关联交易、D2-12 期末余额（原与质押金额同接一个键）/
 * 质押条件 / 质押协议、D2-13 具体依据 / 索引号、D1-8 背书表 前手 / 背书转让单位 / 背书转让日期 / 说明
 * （原沿用贴现表列）。本文件钉：行模型带这些键、载入保留、表单列序前段 = 模板列序。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createEmptyRow as createRpRow, useD2RelatedParty } from '../composables/useD2RelatedParty'
import { useD2WriteoffCheck } from '../composables/useD2WriteoffCheck'
import { useD2PledgeCheck } from '../composables/useD2PledgeCheck'
import { useD2BizModel } from '../composables/useD2BizModel'
import { useD1EndorsementDetail } from '../composables/useD1EndorsementDetail'
import { emptyMemoRow, type MemoRow } from '../composables/useD1MemoReconciliation'
import { useD2DisclosureNote } from '../composables/useD2DisclosureNote'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

function responses(entries: Record<string, unknown>) {
  return ref(new Map<string, any>(
    Object.entries(entries).map(([k, v]) => [k, { item_id: k, conclusion: null, remark: JSON.stringify(v) }]),
  ))
}
const base = (allResponses: any) => ({ wpId: ref('wp'), projectId: ref('p'), allResponses, isReadonly: ref(false) })

/** 表单里某张表（`:data="..."` 起到 `</el-table>`）的列标签，按出现顺序（去掉操作列的空标签）。 */
function tableLabels(vue: string, dataAttr: string): string[] {
  const src = readFileSync(resolve(__dirname, '..', vue), 'utf-8')
  const start = src.indexOf(`:data="${dataAttr}"`)
  expect(start, `${vue} 找不到 :data="${dataAttr}"`).toBeGreaterThan(0)
  const body = src.slice(start, src.indexOf('</el-table>', start))
  return [...body.matchAll(/<el-table-column\b[^>]*?\blabel="([^"]*)"/g)]
    .map((m) => m[1])
    .filter((label) => label && label !== '操作')
}

describe('表单列序：前段 = 模板列序，模板没有的列排在后面', () => {
  it('D2-6 关联方', () => {
    expect(tableLabels('d2/D2TabRelatedParty.vue', 'rows')).toEqual([
      '关联方名称', '关联关系', '期初余额', '借方发生', '贷方发生', '期末余额', '减：坏账准备', '账面价值',
      '发生时间及账龄', '发生原因（款项性质）', '期后回款', '索引号', '公允交易', '备注',
    ])
  })
  it('D2-11 转回 / 核销两区', () => {
    expect(tableLabels('d2/D2TabWriteoffCheck.vue', 'reversalRows')).toEqual([
      '单位名称', '转回原因', '收回方式', '原确定坏账准备的依据', '收回或转回金额',
      '收回或转回前累计已计提坏账准备金额', '合理性分析', '索引号', '原确认日期', '审批文件', '合理性判断',
    ])
    expect(tableLabels('d2/D2TabWriteoffCheck.vue', 'writeoffRows')).toEqual([
      '单位名称', '应收账款性质', '核销金额', '核销原因', '履行的核销程序', '是否由关联交易产生',
      '合理性分析', '索引号', '原确认日期', '合理性判断',
    ])
  })
  it('D2-12 质押区', () => {
    expect(tableLabels('d2/D2TabPledgeCheck.vue', 'pledgeRows')).toEqual([
      '客户名称', '期末余额', '质押金额', '质权人', '质押原因', '质押条件', '质押期限', '质押协议', '索引号',
      '质押日期', '状态', '备注',
    ])
  })
  it('D2-13 业务模式分组表', () => {
    expect(tableLabels('d2/D2TabBizModel.vue', 'groups')).toEqual([
      '组合名称', '管理业务模式', '具体依据', '索引号', '备注', 'SPPI结果', '计量基础',
    ])
  })
  it('D1-8 背书表 F / K / L / M 四列按模板（二），贴现表不变', () => {
    const src = readFileSync(resolve(__dirname, '../d1/D1TabEndorsementDetail.vue'), 'utf-8')
    expect(src).toMatch(/accruedInterest: \{ field: 'endorser', label: '前手'/)
    expect(src).toMatch(/discountBank: \{ field: 'endorsedTo', label: '背书转让单位'/)
    expect(src).toMatch(/discountAmount: \{ field: 'endorsedDate', label: '背书转让日期', width: \d+, type: 'date'/)
    expect(src).toMatch(/discountInterest: \{ field: 'description', label: '说明'/)
    expect(src).toContain('cols: ENDORSE_COLS')
    expect(src).toContain('cols: DISCOUNT_COLS')
    expect(src).toContain('v-for="col in cfg.cols"')
    expect(src).not.toMatch(/v-for="col in COLS"/)
  })
})

// ─── 契约列 ↔ 表单列：契约每个字段绑的键，表单里那一列的标签就是模板表头 ───
// 字段名对拍只看「键前端有没有」：D2-6 L 接 remark（前端「备注」）、D2-12 B 接 pledgeAmount（前端「质押金额」）
// 键都存在，查不出来；这里按表单列标签核。
const REPO = resolve(__dirname, '../../../../../..')
function contractFields(contract: string, tableKey: string): Array<{ key: string; header: string }> {
  const c = JSON.parse(readFileSync(resolve(REPO, 'backend/data/workpaper_sync_contracts', contract), 'utf-8'))
  const table = c.sheets.flatMap((s: any) => s.tables ?? []).find((t: any) => t.table_key === tableKey)
  expect(table, `${contract} 没有 ${tableKey}`).toBeTruthy()
  return table.fields.map((f: any) => ({ key: f.json_pointer.split('/').pop(), header: f.header_text }))
}
/** 表单表格每列 → (标签, 绑定的行字段)：列体里第一个 `row.<键>`（rowId 除外）。 */
function uiColumns(vue: string, dataAttr: string): Map<string, string> {
  const src = readFileSync(resolve(__dirname, '..', vue), 'utf-8')
  const start = src.indexOf(`:data="${dataAttr}"`)
  const body = src.slice(start, src.indexOf('</el-table>', start))
  const out = new Map<string, string>()
  for (const chunk of body.split('<el-table-column').slice(1)) {
    const label = /\blabel="([^"]*)"/.exec(chunk)?.[1]
    const field = /\brow\.(?!rowId\b)(\w+)/.exec(chunk)?.[1]
    if (label && field && !out.has(field)) out.set(field, label)
  }
  return out
}
const norm = (s: string) => s.replace(/\s/g, '').replace(/（/g, '(').replace(/）/g, ')')
/** 表单列标签对模板表头的已知简写（其余逐字相同）。 */
const LABEL_ALIAS: Record<string, string> = {
  被审计单位管理应收票据业务模式: '管理业务模式', 出票人全称: '出票人', 出票日期: '出票日', 承兑单位信用等级: '信用等级',
}

describe('契约列 ↔ 表单列逐列一致（契约绑的键，表单那一列就是模板这一列）', () => {
  const D2 = 'd2.inspection.json'
  const cases: Array<[string, string, string, string]> = [
    ['D2-6', 'related_party_rows', 'd2/D2TabRelatedParty.vue', 'rows'],
    ['D2-11 区①', 'writeoff_reversal_rows', 'd2/D2TabWriteoffCheck.vue', 'reversalRows'],
    ['D2-11 区②', 'writeoff_writeoff_rows', 'd2/D2TabWriteoffCheck.vue', 'writeoffRows'],
    ['D2-12 区①', 'pledge_rows', 'd2/D2TabPledgeCheck.vue', 'pledgeRows'],
    ['D2-13 区①', 'bizmodel_group_rows', 'd2/D2TabBizModel.vue', 'groups'],
  ]
  it.each(cases)('%s', (_label, tableKey, vue, dataAttr) => {
    const ui = uiColumns(vue, dataAttr)
    const bad = contractFields(D2, tableKey)
      .filter(({ key, header }) => norm(ui.get(key) ?? '') !== norm(LABEL_ALIAS[header] ?? header))
      .map(({ key, header }) => `${key}：模板「${header}」 表单「${ui.get(key) ?? '（没有这一列）'}」`)
    expect(bad).toEqual([])
  })
  it('D1-8 背书表（列由 DISCOUNT_COLS + ENDORSE_SWAP 生成）', () => {
    const src = readFileSync(resolve(__dirname, '../d1/D1TabEndorsementDetail.vue'), 'utf-8')
    const pick = (block: string) => [...block.matchAll(/field: '(\w+)', label: '([^']+)'/g)].map((m) => [m[1], m[2]])
    const discount = pick(src.slice(src.indexOf('const DISCOUNT_COLS'), src.indexOf('const ENDORSE_SWAP')))
    const swapBlock = src.slice(src.indexOf('const ENDORSE_SWAP'), src.indexOf('const ENDORSE_COLS'))
    const swap = new Map([...swapBlock.matchAll(/(\w+): \{ field: '(\w+)', label: '([^']+)'/g)].map((m) => [m[1], [m[2], m[3]]]))
    const ui = new Map(discount.map(([f, l]) => swap.get(f) ?? [f, l]) as Array<[string, string]>)
    const bad = contractFields('d1.notes_receivable_detail.json', 'endorse_transfer_rows')
      .filter(({ key, header }) => norm(ui.get(key) ?? '') !== norm(LABEL_ALIAS[header] ?? header))
      .map(({ key, header }) => `${key}：模板「${header}」 表单「${ui.get(key) ?? '（没有这一列）'}」`)
    expect(bad).toEqual([])
  })
})

describe('D2-6 关联方行模型', () => {
  it('补 发生时间及账龄 / 期后回款 / 索引号，载入保留', () => {
    expect(createRpRow()).toMatchObject({ agingPeriod: '', postPayment: 0, indexRef: '' })
    const rp = useD2RelatedParty(base(responses({
      'D2-related-party-rows': [{ rowId: 'rp-1', debtorName: '甲', agingPeriod: '1年以内', postPayment: '50', indexRef: 'D2-2', remark: '备' }],
    })))
    expect(rp.rows.value[0]).toMatchObject({ agingPeriod: '1年以内', postPayment: 50, indexRef: 'D2-2', remark: '备' })
    rp.updateCell('rp-1', 'postPayment', '88.5')
    expect(rp.rows.value[0].postPayment).toBe(88.5)
    expect(rp.totalRow.value).not.toHaveProperty('postPayment') // 模板合计行不合计期后回款
  })
  it('从 D2-2 导入：借贷取本期发生，期末按 期初 + 借 − 贷 算（原写了期末又被重算成期初）', () => {
    const rp = useD2RelatedParty(base(responses({
      'D2-detail-rows': [{ customerName: '乙公司', relationType: '子公司', priorAudited: 100, debitOccurrence: 30,
        creditOccurrence: 10, endBalance: 120, postPayment: 40 }],
    })))
    rp.importFromDetail()
    expect(rp.rows.value[0]).toMatchObject({
      debtorName: '乙公司', priorBalance: 100, debitAmount: 30, creditAmount: 10, endBalance: 120, postPayment: 40,
    })
  })
})

describe('D2-11 / D2-12 / D2-13 行模型', () => {
  it('D2-11 两区补列，累计已计提按数值录入并合计', () => {
    const wo = useD2WriteoffCheck(base(responses({
      'D2-writeoff-reversal-rows': [{ rowId: 'wo-1', debtorName: '甲', recoveryMethod: '银行转账', originalBasis: '单项计提', cumulativeProvision: 9 }],
      'D2-writeoff-writeoff-rows': [{ rowId: 'wo-2', debtorName: '乙', receivableType: '货款', isRelatedParty: '否' }],
    })))
    expect(wo.reversalRows.value[0]).toMatchObject({ recoveryMethod: '银行转账', originalBasis: '单项计提', cumulativeProvision: 9 })
    expect(wo.writeoffRows.value[0]).toMatchObject({ receivableType: '货款', isRelatedParty: '否' })
    wo.updateCell('wo-1', 'cumulativeProvision', '12.5')
    expect(wo.reversalRows.value[0].cumulativeProvision).toBe(12.5)
    expect(wo.reversalProvisionTotal.value).toBe(12.5)
  })
  it('D2-12 质押区期末余额与质押金额是两个键', () => {
    const pl = useD2PledgeCheck(base(responses({
      'D2-pledge-rows': [{ rowId: 'pl-1', debtorName: '丙', endBalance: 500, pledgeAmount: 300, pledgeCondition: '到期还款', pledgeAgreement: '合同-01' }],
    })))
    expect(pl.pledgeRows.value[0]).toMatchObject({ endBalance: 500, pledgeAmount: 300, pledgeCondition: '到期还款', pledgeAgreement: '合同-01' })
    pl.updateCell('pl-1', 'endBalance', '600')
    expect(pl.pledgeRows.value[0]).toMatchObject({ endBalance: 600, pledgeAmount: 300 })
    expect(pl.pledgeEndBalanceTotal.value).toBe(600)
  })
  it('D2-13 分组表补 具体依据 / 索引号', () => {
    const bm = useD2BizModel(base(responses({
      'D2-bizmodel-groups': [{ rowId: 'bm-1', groupName: '高', basis: '频繁出售', indexRef: 'D2-13-1' }],
    })))
    expect(bm.groups.value[0]).toMatchObject({ basis: '频繁出售', indexRef: 'D2-13-1' })
  })
})

describe('D1-8 背书表行模型', () => {
  function memo(status: string, extra: Partial<MemoRow>): MemoRow {
    return { ...emptyMemoRow('bank'), status, amount: 1000, ...extra } as MemoRow
  }
  it('从备查簿导入：背书表带 前手 / 被背书人 / 流转日，不带贴现字段；贴现表反之', () => {
    const d1 = useD1EndorsementDetail({
      allResponses: ref(new Map()), wpId: ref('wp'), projectId: ref('p'), saveImmediate: vi.fn(), isReadonly: ref(false),
    })
    const source = [
      memo('背书', { endorser: '乙公司', endorsee: '丙公司', transferDate: '2025-12-01', discountBank: '某行' }),
      memo('贴现', { endorser: '丁公司', discountBank: '某行', discountInterest: 5, currentDiscounted: 900 }),
    ]
    d1.importFromMemo('endorse', source)
    d1.importFromMemo('discount', source)
    expect(d1.endorseRows.value[0]).toMatchObject({
      endorser: '乙公司', endorsedTo: '丙公司', endorsedDate: '2025-12-01', discountBank: '', discountAmount: 0,
    })
    expect(d1.discountRows.value[0]).toMatchObject({
      endorser: '', endorsedTo: '', discountBank: '某行', discountInterest: 5, discountAmount: 900,
    })
  })
  it('四列可录、可载入', () => {
    const d1 = useD1EndorsementDetail({
      allResponses: responses({ 'D1-endorse-transfer-rows': [{ rowId: 'e1', endorser: '甲', description: '支付货款' }] }),
      wpId: ref('wp'), projectId: ref('p'), saveImmediate: vi.fn(), isReadonly: ref(false),
    })
    expect(d1.endorseRows.value[0]).toMatchObject({ endorser: '甲', description: '支付货款' })
    d1.updateCell('endorse', 'e1', 'endorsedDate', '2025-11-30')
    expect(d1.endorseRows.value[0].endorsedDate).toBe('2025-11-30')
  })
})

describe('D2 附注从 D2-11 带入补列后的字段', () => {
  it('转回 / 核销明细带上收回方式、原依据、累计已计提、性质、程序、是否关联交易', () => {
    const api = useD2DisclosureNote({
      allResponses: responses({
        'D2-writeoff-reversal-rows': [{ debtorName: 'C公司', amount: 5, reason: '收回', recoveryMethod: '银行转账', originalBasis: '账龄组合', cumulativeProvision: 12 }],
        'D2-writeoff-writeoff-rows': [{ debtorName: 'D公司', amount: 3, reason: '破产', receivableType: '货款', approvalDoc: '董事会审批', isRelatedParty: '否' }],
      }),
      wpId: ref('wp'), projectId: ref('p'), variant: 'listed', save: vi.fn(), isReadonly: ref(false),
    } as any)
    expect(api.importReversalFromWriteoffCheck()).toBe(1)
    expect(api.reversalRows.value[0]).toMatchObject({ recoveryMethod: '银行转账', originalBasis: '账龄组合', cumulativeProvision: 12 })
    expect(api.importWriteOffFromWriteoffCheck()).toBe(1)
    expect(api.writeOffRows.value[0]).toMatchObject({ nature: '货款', procedure: '董事会审批', relatedParty: '否' })
  })
})
