/**
 * 共享回填函数（spec voucher-identity-writeback-and-audit-phase 任务 9，需求 4.1~4.6、4.8、6.3，
 * ADR-VK-06 / 07 / 08 / 12）
 *
 * - prepareSamples：按后端配对结果展开 / 拼接 / 标「多科目」，金额落在样本自己的借贷栏；
 * - mergeVoucherCheckRows：追加按分录指纹去重、替换只动本阶段抽凭行、旧行触碰迁移；
 * - useVoucherCheckFill：抽凭两次 / 挂凭导入两次不重复、抽凭与挂凭命中同一分录只留一行、
 *   替换前确认、撤销按批次删行（确认 / 取消 / 后端失败）、年审阶段预审行只读（rowClass / guardPersist）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { __resetProjectAuditPhaseCache } from '@/composables/useProjectAuditPhase'
import {
  combineRowClass,
  counterpartLabelOf,
  legacyIdentity,
  mergeVoucherCheckRows,
  metaOf,
  newEntriesOnly,
  prepareSamples,
  sideTableOf,
  useVoucherCheckFill,
  withRowMeta,
  type FillSample,
  type PreparedItem,
  type SamplePairing,
  type VoucherRowMeta,
} from '../voucherCheckFill'

const mockGet = (http as unknown as { get: ReturnType<typeof vi.fn> }).get
const confirm = vi.mocked(ElMessageBox.confirm)

function setPhase(phase: 'preliminary' | 'final') {
  __resetProjectAuditPhaseCache()
  mockGet.mockResolvedValue({ data: { current_audit_phase: phase, interim_cutoff_date: '2025-09-30', can_edit: true } })
}

const VK = JSON.stringify(['2025', '0101', '2025-01-20', 'FY', '0012'])

function sample(over: Partial<FillSample> = {}): FillSample {
  return {
    voucherKey: VK, lineFp: 'fp-1', voucherNo: '0012', voucherDate: '2025-01-20',
    debitAmount: '3680.00', creditAmount: null, counterpartAccount: null, counterpartAccountName: null,
    pairing: null, ...over,
  }
}

function paired(cps: Array<[string, string]>): SamplePairing {
  return {
    status: 'paired', basis: 'one_to_many',
    counterparts: cps.map(([code, amount]) => ({ account_code: code, account_name: `科目${code}`, amount, line_fp: `cp-${code}` })),
    counterpart_summary: [],
  }
}

interface Row {
  voucherNo: string
  voucherDate: string
  debitAmount: string | null
  creditAmount: string | null
  counterpart: string
  checkResult: string
  attachments?: string[]
  _gt?: VoucherRowMeta
}

const toRow = (item: PreparedItem): Row => ({
  voucherNo: item.sample.voucherNo,
  voucherDate: item.sample.voucherDate,
  debitAmount: item.debitAmount,
  creditAmount: item.creditAmount,
  counterpart: item.counterpartAccount,
  checkResult: '',
})

function meta(over: Partial<VoucherRowMeta> = {}): VoucherRowMeta {
  return { vk: VK, lfp: 'fp-x', ph: 'final', b: 'b-0', src: ['engine'], pr: 'paired', cp: null, ...over }
}

function row(over: Partial<Row> = {}, m: Partial<VoucherRowMeta> | null = {}): Row {
  const base: Row = { voucherNo: '0012', voucherDate: '2025-01-20', debitAmount: '100.00', creditAmount: null, counterpart: '1002', checkResult: '', ...over }
  return m === null ? base : { ...base, _gt: meta(m) }
}

beforeEach(() => {
  vi.clearAllMocks()
  confirm.mockReset()
  setPhase('final')
})

// ─── prepareSamples ───────────────────────────────────────────────────────────

describe('prepareSamples：按后端配对结果生成待写入项', () => {
  const ctx = { phase: 'final' as const, source: 'engine' as const, batchId: 'b-1' }

  it('expand：配上多个对方科目按科目一行一个，金额落在样本自己的借贷栏，同科目合并', () => {
    const items = prepareSamples([sample({ pairing: paired([['1002', '2000.00'], ['2241', '1000.00'], ['1002', '680.00']]) })], 'expand', ctx)
    expect(items.map(i => [i.counterpartAccount, i.debitAmount, i.creditAmount, i.meta.cp])).toEqual([
      ['1002', '2680.00', null, '1002'],
      ['2241', '1000.00', null, '2241'],
    ])
    expect(items.every(i => i.meta.lfp === 'fp-1' && i.meta.b === 'b-1' && i.meta.ph === 'final')).toBe(true)
  })

  it('贷方样本展开后金额仍在贷方栏（旧实现会翻到借方）', () => {
    const items = prepareSamples([sample({ debitAmount: null, creditAmount: '500.00', pairing: paired([['6602', '300.00'], ['6603', '200.00']]) })], 'expand', ctx)
    expect(items.map(i => [i.debitAmount, i.creditAmount])).toEqual([[null, '300.00'], [null, '200.00']])
  })

  it('join：一个样本一行，对方科目用「/」拼接，金额 = 样本金额', () => {
    const [item] = prepareSamples([sample({ pairing: paired([['1002', '2000.00'], ['2241', '1680.00']]) })], 'join', ctx)
    expect([item.counterpartAccount, item.debitAmount, item.meta.cp]).toEqual(['1002/2241', '3680.00', null])
  })

  it('配不上 / 分录过多：一行「多科目」，不推金额', () => {
    for (const status of ['multi', 'large'] as const) {
      const [item] = prepareSamples([sample({ pairing: { status, basis: null, counterparts: [], counterpart_summary: [] } })], 'expand', ctx)
      expect([item.counterpartAccount, item.isMultiAccount, item.debitAmount, item.meta.pr]).toEqual(['多科目', true, '3680.00', status])
    }
  })

  it('没有配对结果：沿用样本自带对方科目；借贷双填两栏照写；金额解析不了原样透传', () => {
    const [plain] = prepareSamples([sample({ counterpartAccount: '1122' })], 'expand', ctx)
    expect([plain.counterpartAccount, plain.isMultiAccount]).toEqual(['1122', false])
    const [both] = prepareSamples([sample({ debitAmount: '10', creditAmount: '10' })], 'expand', ctx)
    expect([both.debitAmount, both.creditAmount]).toEqual(['10.00', '10.00'])
    const [bad] = prepareSamples([sample({ debitAmount: '1,234.00' })], 'expand', ctx)
    expect(bad.debitAmount).toBe('1,234.00')
  })

  it('配对结果 → 旧字段标签：一个对方科目填科目，多个或配不上填「多科目」', () => {
    expect(counterpartLabelOf(paired([['1002', '1']]))).toEqual({ code: '1002', name: '科目1002' })
    expect(counterpartLabelOf(paired([['1002', '1'], ['2241', '1']]))?.code).toBe('多科目')
    expect(counterpartLabelOf({ status: 'unknown_side', basis: null, counterparts: [], counterpart_summary: [] })).toBeNull()
  })
})

// ─── sideTableOf ──────────────────────────────────────────────────────────────

describe('sideTableOf：分借方 / 贷方两张表的宿主按分录自己的借贷栏进表', () => {
  it('只有贷方栏有数进贷方（红字也是），只有借方栏有数进借方；借贷栏不明进借方', () => {
    const at = (debitAmount: string | null, creditAmount: string | null) => sideTableOf({ debitAmount, creditAmount })
    expect(at('1000.00', null)).toBe('debit')
    expect(at(null, '300.00')).toBe('credit')
    // 贷方红字：贷方栏 -50（不是借方负数），进贷方
    expect(at(null, '-50.00')).toBe('credit')
    expect(at('0.00', '-50.00')).toBe('credit')
    // 借方红字进借方
    expect(at('-30.00', null)).toBe('debit')
    // 借贷两栏都有数 / 都为零 / 金额解析不了：进借方
    expect(at('100.00', '100.00')).toBe('debit')
    expect(at('0.00', '0.00')).toBe('debit')
    expect(at('abc', null)).toBe('debit')
  })
})

// ─── mergeVoucherCheckRows ───────────────────────────────────────────────────

describe('mergeVoucherCheckRows：追加去重 / 替换只动本阶段抽凭行 / 旧行触碰迁移', () => {
  const opts = { mode: 'append' as const, phase: 'final' as const, source: 'engine' as const }

  it('追加：已有同指纹的行不再插入，保留原行全部内容，来源并入', () => {
    const old = row({ checkResult: 'Y', attachments: ['a.pdf'] }, { lfp: 'fp-1', src: ['attach'] })
    const res = mergeVoucherCheckRows([old], [row({}, { lfp: 'fp-1' }), row({}, { lfp: 'fp-2' })], opts)
    expect([res.added, res.existed]).toEqual([1, 1])
    expect(res.rows[0]).toMatchObject({ checkResult: 'Y', attachments: ['a.pdf'] })
    expect(res.rows[0]._gt?.src).toEqual(['attach', 'engine'])
  })

  it('同一次写入里重复的分录只进一行', () => {
    const res = mergeVoucherCheckRows([], [row({}, { lfp: 'fp-1' }), row({}, { lfp: 'fp-1' })], opts)
    expect([res.rows.length, res.added, res.existed]).toEqual([1, 1, 1])
  })

  it('替换：只删同阶段且来源只有抽凭的行；预审行、手工行、挂凭行、抽凭+挂凭行都保留', () => {
    const existing = [
      row({}, { lfp: 'p', ph: 'preliminary' }),
      row({}, { lfp: 'f-engine', ph: 'final' }),
      row({}, { lfp: 'f-attach', ph: 'final', src: ['attach'] }),
      row({}, { lfp: 'f-both', ph: 'final', src: ['engine', 'attach'] }),
      row({ voucherNo: 'M-1' }, null),
    ]
    const res = mergeVoucherCheckRows(existing, [row({}, { lfp: 'new' })], { ...opts, mode: 'replace' })
    expect(res.rows.map(r => r._gt?.lfp ?? 'manual')).toEqual(['p', 'f-attach', 'f-both', 'manual', 'new'])
    expect(res.replaced).toBe(1)
  })

  it('替换：要删的行里已填核对内容的列进 needConfirm', () => {
    const filled = row({ checkResult: 'Y' }, { lfp: 'f1' })
    const res = mergeVoucherCheckRows([filled, row({}, { lfp: 'f2' })], [], {
      ...opts, mode: 'replace', hasUserContent: r => !!r.checkResult,
    })
    expect(res.needConfirm).toEqual([filled])
  })

  it('旧行（没有 _gt）凭证号 + 日期 + 金额相同：不再插入，补写 _gt（阶段未标、来源 = 手工 + 本次）', () => {
    const legacy = row({ checkResult: '异常' }, null)
    const res = mergeVoucherCheckRows([legacy], [row({}, { lfp: 'fp-9', ph: 'final', b: 'b-9' })], opts)
    expect([res.rows.length, res.added, res.existed]).toEqual([1, 0, 1])
    expect(res.rows[0].checkResult).toBe('异常')
    expect(res.rows[0]._gt).toMatchObject({ lfp: 'fp-9', ph: null, b: null, src: ['manual', 'engine'] })
  })

  it('旧行同号别日：是别的分录，照样插入', () => {
    const legacy = row({ voucherDate: '2025-02-07' }, null)
    expect(mergeVoucherCheckRows([legacy], [row({}, { lfp: 'fp-9' })], opts).added).toBe(1)
  })

  it('待写入行没有指纹（预览里手工增补的）：凭证号 + 日期 + 金额与已有行相同即算已有', () => {
    const res = mergeVoucherCheckRows([row({}, { lfp: 'fp-1' })], [row({}, { lfp: null })], opts)
    expect([res.added, res.existed]).toEqual([0, 1])
  })

  it('旧行身份：金额写法不同也认同一笔；解析不了的金额不抛错', () => {
    expect(legacyIdentity({ voucherNo: ' 0012 ', voucherDate: '2025-01-20 00:00:00', debitAmount: '100' }))
      .toBe(legacyIdentity({ voucher_no: '0012', voucher_date: '2025-01-20', debit_amount: '100.00' }))
    expect(() => legacyIdentity({ voucherNo: '1', debitAmount: '1,234' })).not.toThrow()
  })

  it('newEntriesOnly：截止抽样的样本列表与底稿回填同口径', () => {
    const existing = [{ voucherNo: 'A', voucherDate: '2025-01-01', debitAmount: '1', creditAmount: null, lineFp: 'fa' }]
    const incoming = [
      { voucherNo: 'A', voucherDate: '2025-01-01', debitAmount: '1', creditAmount: null, lineFp: 'fa' },
      { voucherNo: 'A', voucherDate: '2025-01-02', debitAmount: '1', creditAmount: null, lineFp: null },
      { voucherNo: 'A', voucherDate: '2025-01-02', debitAmount: '1', creditAmount: null, lineFp: null },
    ]
    expect(newEntriesOnly(existing, incoming).map(v => v.voucherDate)).toEqual(['2025-01-02'])
  })

  it('withRowMeta：宿主解析 / 保存时透传 _gt，没有就不加', () => {
    const src = row({}, { lfp: 'fp-1', sv: { status: 'unchanged' } })
    expect(metaOf(withRowMeta({ a: 1 }, src))).toMatchObject({ lfp: 'fp-1', sv: { status: 'unchanged' } })
    expect('_gt' in withRowMeta({ a: 1 }, { a: 1 })).toBe(false)
    expect(combineRowClass<{ row: Row }>(() => 'a', () => '', undefined, () => 'b')({ row: row() })).toBe('a b')
  })
})

// ─── useVoucherCheckFill ─────────────────────────────────────────────────────

function host(initial: Row[] = []) {
  const rows = ref<Row[]>(initial)
  const persist = vi.fn()
  const fill = useVoucherCheckFill<Row>({
    projectId: 'p-1',
    tables: rows,
    mapSampleToRow: toRow,
    persist,
    hasUserContent: r => !!r.checkResult || !!r.attachments?.length,
  })
  return { rows, persist, fill }
}

const engineSamples = () => [sample({ lineFp: 'fp-1' }), sample({ lineFp: 'fp-2', debitAmount: '50.00' })]

describe('useVoucherCheckFill：抽凭、挂凭导入、撤销', () => {
  it('抽凭两次（追加）不重复，第二次提示已存在；行带阶段 / 批次 / 来源', async () => {
    const { rows, persist, fill } = host()
    await fill.onEngineFilled({ samples: engineSamples(), phase: 'final', fillMode: 'append', batchId: 'b-1' })
    expect(ElMessage.success).toHaveBeenLastCalledWith('填入 2 行')
    await fill.onEngineFilled({ samples: engineSamples(), phase: 'final', fillMode: 'merge', batchId: 'b-2' })
    expect(rows.value.map(r => r._gt?.lfp)).toEqual(['fp-1', 'fp-2'])
    expect(rows.value[0]._gt).toMatchObject({ ph: 'final', b: 'b-1', src: ['engine'] })
    expect(persist).toHaveBeenCalledTimes(2)
    expect(ElMessage.info).toHaveBeenLastCalledWith('填入 0 行，已存在 2 行未重复填入')
  })

  it('挂凭导入两次幂等，提示「已存在 N 行」；与抽凭命中同一分录只留一行，来源记为两者', async () => {
    const { rows, fill } = host()
    await fill.onEngineFilled({ samples: [sample({ lineFp: 'fp-1' })], phase: 'final', batchId: 'b-1' })
    await fill.onAttachImported(engineSamples())
    await fill.onAttachImported(engineSamples())
    expect(rows.value.map(r => [r._gt?.lfp, r._gt?.src])).toEqual([['fp-1', ['engine', 'attach']], ['fp-2', ['attach']]])
    expect(ElMessage.success).toHaveBeenLastCalledWith('导入 0 行，已存在 2 行')
  })

  it('行阶段取项目当前阶段（挂凭）或引擎日志的阶段（抽凭）', async () => {
    setPhase('preliminary')
    const { rows, fill } = host()
    await fill.onAttachImported([sample({ lineFp: 'fp-a' })])
    await fill.onEngineFilled({ samples: [sample({ lineFp: 'fp-e' })], phase: 'preliminary', batchId: 'b-1' })
    expect(rows.value.map(r => r._gt?.ph)).toEqual(['preliminary', 'preliminary'])
  })

  it('替换：年审阶段不动预审行；要删的行有核对内容先确认，取消则底稿不动', async () => {
    const prelim = row({ checkResult: 'Y' }, { lfp: 'p-1', ph: 'preliminary', b: 'b-p' })
    const finalFilled = row({ checkResult: 'N' }, { lfp: 'f-1', ph: 'final', b: 'b-f' })
    const { rows, persist, fill } = host([prelim, finalFilled])
    confirm.mockRejectedValueOnce('cancel')
    const cancelled = await fill.onEngineFilled({ samples: [sample({ lineFp: 'n-1' })], phase: 'final', fillMode: 'replace' })
    expect(cancelled.cancelled).toBe(true)
    expect(rows.value).toEqual([prelim, finalFilled])
    expect(persist).not.toHaveBeenCalled()

    confirm.mockResolvedValueOnce('confirm' as never)
    await fill.onEngineFilled({ samples: [sample({ lineFp: 'n-1' })], phase: 'final', fillMode: 'replace' })
    expect(rows.value.map(r => r._gt?.lfp)).toEqual(['p-1', 'n-1'])
    expect(persist).toHaveBeenCalledTimes(1)
  })

  it('多张表：tableOf 分区，替换只动 scope 指定的表', async () => {
    const occ = ref<Row[]>([row({}, { lfp: 'o-1' })])
    const post = ref<Row[]>([row({}, { lfp: 's-1' })])
    const fill = useVoucherCheckFill<Row>({
      projectId: 'p-1', tables: { occ, post }, mapSampleToRow: toRow, persist: vi.fn(),
      tableOf: item => (item.sample.voucherDate > '2025-12-31' ? 'post' : 'occ'),
    })
    await fill.onEngineFilled({ samples: [sample({ lineFp: 'o-2' })], phase: 'final', fillMode: 'replace' }, { tables: ['occ'] })
    expect(occ.value.map(r => r._gt?.lfp)).toEqual(['o-2'])
    expect(post.value.map(r => r._gt?.lfp)).toEqual(['s-1'])
  })

  it('多张表：替换只删范围内表的抽凭行；路由到范围外表的分录按追加并入（D3 选目标区块）', async () => {
    const occ = ref<Row[]>([row({}, { lfp: 'o-1' })])
    const post = ref<Row[]>([row({}, { lfp: 's-1' }), row({}, { lfp: 's-2' })])
    const fill = useVoucherCheckFill<Row>({
      projectId: 'p-1', tables: { occ, post }, mapSampleToRow: toRow, persist: vi.fn(),
      // 已在期后表的分录仍进期后表，其余进用户所选区块（返回空 = 进 scope 的第一张表）
      tableOf: item => (post.value.some(r => r._gt?.lfp === item.meta.lfp) ? 'post' : null),
    })
    const out = await fill.onEngineFilled(
      { samples: [sample({ lineFp: 'o-2' }), sample({ lineFp: 's-2', voucherNo: '0099' })], phase: 'final', fillMode: 'replace' },
      { tables: ['occ'] },
    )
    expect(occ.value.map(r => r._gt?.lfp)).toEqual(['o-2'])
    expect(post.value.map(r => r._gt?.lfp)).toEqual(['s-1', 's-2'])
    expect([out.added, out.existed, out.replaced]).toEqual([1, 1, 1])
  })

  it('撤销：确认后删本批次填入的行（同时来自挂凭的保留并去掉抽凭来源），提示实际删除行数', async () => {
    const { rows, persist, fill } = host([
      row({ checkResult: 'Y' }, { lfp: 'a', b: 'b-1' }),
      row({}, { lfp: 'b', b: 'b-1', src: ['engine', 'attach'] }),
      row({}, { lfp: 'c', b: 'b-2' }),
    ])
    confirm.mockResolvedValueOnce('confirm' as never)
    const performUndo = vi.fn(async () => true)
    expect(await fill.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo })).toBe(true)
    expect(confirm.mock.calls[0][0]).toContain('删除本批次填入的 1 行，其中 1 行已填核对内容或附件')
    expect(rows.value.map(r => [r._gt?.lfp, r._gt?.b, r._gt?.src])).toEqual([['b', null, ['attach']], ['c', 'b-2', ['engine']]])
    expect(persist).toHaveBeenCalledTimes(1)
    expect(ElMessage.success).toHaveBeenCalledWith('已撤销本批次，删除 1 行；1 行同时来自挂凭或手工录入，已保留')
  })

  it('撤销：取消确认则不调后端、不删行；后端撤销失败也不删行', async () => {
    const initial = [row({}, { lfp: 'a', b: 'b-1' })]
    const { rows, persist, fill } = host([...initial])
    const performUndo = vi.fn(async () => false)
    confirm.mockRejectedValueOnce('cancel')
    expect(await fill.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo })).toBe(false)
    expect(performUndo).not.toHaveBeenCalled()
    confirm.mockResolvedValueOnce('confirm' as never)
    expect(await fill.onUndoRequest({ logId: 'l-1', batchId: 'b-1', performUndo })).toBe(false)
    expect(performUndo).toHaveBeenCalledTimes(1)
    expect(rows.value).toEqual(initial)
    expect(persist).not.toHaveBeenCalled()
  })

  it('撤销：年审阶段的预审批次不能撤销（预审行只读）', async () => {
    const { rows, fill } = host([row({}, { lfp: 'p', ph: 'preliminary', b: 'b-p' })])
    const performUndo = vi.fn(async () => true)
    expect(await fill.onUndoRequest({ logId: 'l-1', batchId: 'b-p', performUndo })).toBe(false)
    expect(performUndo).not.toHaveBeenCalled()
    expect(rows.value).toHaveLength(1)
    expect(ElMessage.warning).toHaveBeenCalled()
  })
})

describe('年审阶段预审行只读：rowClass + guardPersist', () => {
  it('年审阶段预审行加 gt-row-locked；保存时改过的改回、删掉的补回，行元数据取当前的', async () => {
    const prelim = row({ checkResult: 'Y' }, { lfp: 'p', ph: 'preliminary' })
    const { rows, fill } = host([prelim, row({}, { lfp: 'f' })])
    await fill.ready()
    fill.markLoaded()
    expect(fill.rowClass({ row: rows.value[0] })).toBe('gt-row-locked')
    expect(fill.rowClass({ row: rows.value[1] })).toBe('')

    const tampered = { ...rows.value[0], checkResult: 'N', _gt: { ...rows.value[0]._gt!, src: ['engine', 'attach'] } } as Row
    const guarded = fill.guardPersist([tampered, rows.value[1]])
    expect(guarded[0].checkResult).toBe('Y')
    expect(guarded[0]._gt?.src).toEqual(['engine', 'attach'])
    const restored = fill.guardPersist([rows.value[1]])
    expect(restored.map(r => r._gt?.lfp)).toEqual(['f', 'p'])
  })

  it('读入时没有指纹的预审行，之后被触碰迁移补了指纹，保存时仍认得出（不重复补回）', async () => {
    const noFp = row({ checkResult: 'Y' }, { lfp: null, ph: 'preliminary', b: null })
    const { rows, fill } = host([noFp])
    await fill.ready()
    fill.markLoaded()
    await fill.onAttachImported([sample({ lineFp: 'fp-new', debitAmount: '100.00' })])
    expect(rows.value).toHaveLength(1)
    expect(rows.value[0]._gt?.lfp).toBe('fp-new')
    const guarded = fill.guardPersist(rows.value)
    expect(guarded).toHaveLength(1)
    expect(guarded[0]).toMatchObject({ checkResult: 'Y', _gt: { lfp: 'fp-new', ph: 'preliminary' } })
  })

  it('预审阶段不限制，并把这次保存的预审行记为新的读入版本', async () => {
    setPhase('preliminary')
    const { rows, fill } = host([row({ checkResult: '' }, { lfp: 'p', ph: 'preliminary' })])
    await fill.ready()
    fill.markLoaded()
    expect(fill.rowClass({ row: rows.value[0] })).toBe('')
    const edited = [{ ...rows.value[0], checkResult: 'Y' }]
    expect(fill.guardPersist(edited)).toBe(edited)
  })
})
