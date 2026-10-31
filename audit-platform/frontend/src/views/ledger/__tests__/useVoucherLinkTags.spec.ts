/**
 * 序时账「已挂 / 已抽」标识（spec voucher-identity-writeback-and-audit-phase 任务 14，需求 5.2）
 *
 * - 行上凭证键与后端同一实现；期初 / 小计等合成行、没有日期的行不查；凭证层的行直接用后端给的 voucher_key；
 * - 一次最多 500 个键，超过分段顺序查（请求体、静默、不参与 GET 去重）；查过的键（含查无记录的）不再查；
 * - 查询失败只是不显示，失败的键下次再查；挂凭后 refresh 只重查这几个键；
 * - 竞态：晚到的旧响应不覆盖之后为同一个键发起的查询结果；切项目 / 年度清空；
 * - 标记文字：底稿编码 · 挂凭 / 抽凭（×条数）· 阶段，旧登记与底稿已删各有说明。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))

import { mount } from '@vue/test-utils'
import http from '@/utils/http'
import { voucherKeyString } from '@/utils/voucherIdentity'
import { resetVoucherEvidenceIndexForTest } from '@/composables/useVoucherEvidenceIndex'
import { rowVoucherKey, useVoucherLinkTags, voucherLinkText, type VoucherLink } from '../useVoucherLinkTags'
import VoucherLinkTags from '../VoucherLinkTags.vue'

const post = http.post as unknown as ReturnType<typeof vi.fn>
const PID = 'p-1'
const COMPANY = '重庆医药集团四川物流有限公司'

function line(no: string, over: Record<string, unknown> = {}) {
  return { voucher_no: no, voucher_date: '2025-01-20', voucher_type: 'FY', company_code: COMPANY, account_code: '1002', ...over }
}
const keyOf = (no: string, over: Record<string, unknown> = {}) => voucherKeyString(line(no, over), 2025)

function link(over: Partial<VoucherLink> = {}): VoucherLink {
  return { working_paper_id: 'wp-j1', wp_code: 'J1', wp_name: '应付职工薪酬', wp_missing: false, source: 'manual',
    phase: 'final', count: 1, legacy: false, ...over }
}

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => {
  post.mockReset()
})

describe('rowVoucherKey', () => {
  it('合成行、缺凭证号或日期的行没有凭证键；凭证层行用后端给的 voucher_key', () => {
    expect(rowVoucherKey({ ...line('0012'), _type: 'subtotal' }, 2025)).toBeNull()
    expect(rowVoucherKey({ ...line('0012'), voucher_date: null }, 2025)).toBeNull()
    expect(rowVoucherKey({ ...line(''), voucher_no: '  ' }, 2025)).toBeNull()
    expect(rowVoucherKey({ ...line('0012'), _type: 'normal' }, 2025)).toBe(keyOf('0012'))
    expect(rowVoucherKey({ ...line('0012'), voucher_key: 'from-backend' }, 2025)).toBe('from-backend')
  })
})

describe('批量查询与缓存', () => {
  it('超过 500 个键分段顺序查；查过的（含查无记录的）不再查', async () => {
    post.mockImplementation(async (_url: string, body: { keys: string[] }) => ({
      data: { links: { [body.keys[0]]: [link()] } },
    }))
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    const rows = Array.from({ length: 1200 }, (_, i) => line(String(i).padStart(4, '0')))
    await tags.loadForRows([...rows, { ...rows[0], _type: 'opening' }])
    expect(post.mock.calls.map(c => (c[1] as { keys: string[] }).keys.length)).toEqual([500, 500, 200])
    const [url, body, opts] = post.mock.calls[0]
    expect(url).toBe(`/api/projects/${PID}/ledger/voucher-links/query`)
    expect(body).toMatchObject({ year: 2025 })
    expect(opts).toMatchObject({ _silent: true, _dedupe: false })
    expect(tags.linksOfRow(rows[0])).toHaveLength(1)
    expect(tags.linksOfRow(rows[1])).toEqual([])
    await tags.loadForRows(rows)
    expect(post).toHaveBeenCalledTimes(3)
  })

  it('查询失败不显示、不进缓存，下次再查', async () => {
    post.mockRejectedValueOnce(new Error('网络'))
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    await tags.loadForRows([line('0012')])
    expect(tags.flagOfRow(line('0012'))).toBeNull()
    post.mockResolvedValueOnce({ data: { links: { [keyOf('0012')]: [link()] } } })
    await tags.loadForRows([line('0012')])
    expect(post).toHaveBeenCalledTimes(2)
    expect(tags.flagOfRow(line('0012'))?.icon).toBe('📎')
  })

  it('项目没填审计年度（year = null）：不拼键、不发请求（含后端给了凭证键的行与挂凭后重查）；填了年度再查', async () => {
    post.mockResolvedValue({ data: { links: {} } })
    const year = ref<number | null>(null)
    const tags = useVoucherLinkTags(ref(PID), year)
    expect(rowVoucherKey(line('0012'), null)).toBeNull()
    await tags.loadForRows([line('0012'), { ...line('0013'), voucher_key: keyOf('0013') }])
    await tags.refresh([keyOf('0013')])
    expect(post).not.toHaveBeenCalled() // 已挂查询的 year 是必填整数，带 null 去查只会 422
    year.value = 2025
    await tags.loadForRows([line('0012')])
    expect(post).toHaveBeenCalledTimes(1)
  })

  it('挂凭后 refresh 只重查给定的键（不论缓存）', async () => {
    post.mockResolvedValue({ data: { links: {} } })
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    await tags.loadForRows([line('0012'), line('0013')])
    post.mockResolvedValueOnce({ data: { links: { [keyOf('0012')]: [link(), link({ wp_code: 'E1', wp_name: '货币资金' })] } } })
    await tags.refresh([keyOf('0012'), null, keyOf('0012')])
    expect((post.mock.calls[1][1] as { keys: string[] }).keys).toEqual([keyOf('0012')])
    expect(tags.linksOfRow(line('0012')).map(l => l.wp_code)).toEqual(['J1', 'E1'])
  })

  it('晚到的旧响应不覆盖之后为同一个键发起的查询结果', async () => {
    const slow = deferred<unknown>()
    post.mockImplementationOnce(() => slow.promise)
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    const first = tags.loadForRows([line('0012')])
    post.mockResolvedValueOnce({ data: { links: { [keyOf('0012')]: [link({ wp_code: 'E1' })] } } })
    await tags.refresh([keyOf('0012')])
    slow.resolve({ data: { links: {} } })
    await first
    expect(tags.linksOfRow(line('0012')).map(l => l.wp_code)).toEqual(['E1'])
  })

  it('切项目或年度清空缓存，旧项目的响应不写进来', async () => {
    const slow = deferred<unknown>()
    post.mockImplementationOnce(() => slow.promise)
    const pid = ref(PID)
    const tags = useVoucherLinkTags(pid, ref(2025))
    const pending = tags.loadForRows([line('0012')])
    pid.value = 'p-2'
    await nextTick()
    slow.resolve({ data: { links: { [keyOf('0012')]: [link()] } } })
    await pending
    expect(tags.links.value.size).toBe(0)
  })
})

describe('标记文字', () => {
  it('底稿编码 · 来源（×条数）· 阶段；旧登记、底稿已删、未指定底稿各有说明', () => {
    expect(voucherLinkText(link())).toBe('J1 应付职工薪酬 · 挂凭 · 年审')
    expect(voucherLinkText(link({ source: 'sampling_engine', count: 2, phase: 'preliminary' })))
      .toBe('J1 应付职工薪酬 · 抽凭 ×2 · 预审')
    expect(voucherLinkText(link({ wp_code: null, wp_name: null, wp_missing: true, phase: null })))
      .toBe('底稿已删除 · 挂凭 · 阶段未标')
    expect(voucherLinkText(link({ wp_code: null, wp_name: null, working_paper_id: null }))).toContain('未指定底稿')
    expect(voucherLinkText(link({ legacy: true }))).toContain('旧登记')
  })

  it('明细层 📎 标记列出全部底稿；没挂没抽不出标记', async () => {
    post.mockResolvedValueOnce({ data: { links: { [keyOf('0012')]: [
      link(), link({ wp_code: 'E1', wp_name: '货币资金', source: 'sampling_engine' })] } } })
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    await tags.loadForRows([line('0012'), line('0099')])
    expect(tags.flagOfRow(line('0012'))).toEqual({
      icon: '📎', tip: '已挂 / 已抽于：J1 应付职工薪酬 · 挂凭 · 年审；E1 货币资金 · 抽凭 · 年审' })
    expect(tags.flagOfRow(line('0099'))).toBeNull()
    expect(tags.flagOfRow({ ...line('0012'), _type: 'subtotal' })).toBeNull()
  })
})

describe('凭证层并入凭证证据（spec attachment-voucher-evidence-binding 需求 7，ADR-AVE-08）', () => {
  const settle = async () => {
    for (let i = 0; i < 6; i++) await Promise.resolve()
    await nextTick()
  }
  const evidence = (key: string) => ({
    [key]: [{
      working_paper_id: 'wp-d2', wp_code: 'D2-4', wp_name: '凭证检查表', attachments: [
        { id: 'a1', file_name: '回单.pdf', file_type: 'pdf', ocr_status: null, evidence_type: 'voucher' },
        { id: 'a2', file_name: '发票.png', file_type: 'png', ocr_status: null, evidence_type: 'voucher' },
      ],
    }],
  })

  beforeEach(() => {
    resetVoucherEvidenceIndexForTest()
  })

  it('linksOfKey = 挂凭 / 抽凭登记 + 各可见底稿的凭证证据（按需查，查到前只有登记）', async () => {
    const key = keyOf('0012')
    post.mockImplementation(async (url: string) => (String(url).endsWith('/voucher-evidence/query')
      ? { data: { evidence: evidence(key) } }
      : { data: { links: { [key]: [link()] } } }))
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    await tags.loadForRows([line('0012')])
    expect(tags.linksOfKey(key).map((t) => t.source)).toEqual(['manual'])
    await settle()
    const merged = tags.linksOfKey(key)
    expect(merged.map((t) => [t.source, t.wp_code, t.count])).toEqual([['manual', 'J1', 1], ['evidence', 'D2-4', 2]])
    expect(voucherLinkText(merged[1])).toBe('D2-4 凭证检查表 · 已取得凭证证据 2 份：回单.pdf、发票.png')
    const calls = post.mock.calls.filter((c) => String(c[0]).endsWith('/voucher-evidence/query'))
    expect(calls.map((c) => c[1])).toEqual([{ year: 2025, keys: [key] }])
  })

  it('明细层 📎（linksOfRow / flagOfRow）照旧只看登记，不查凭证证据', async () => {
    post.mockResolvedValue({ data: { links: { [keyOf('0012')]: [link()] } } })
    const tags = useVoucherLinkTags(ref(PID), ref(2025))
    await tags.loadForRows([line('0012')])
    expect(tags.linksOfRow(line('0012'))).toHaveLength(1)
    expect(tags.flagOfRow(line('0012'))?.icon).toBe('📎')
    await settle()
    expect(post.mock.calls.every((c) => String(c[0]).endsWith('/voucher-links/query'))).toBe(true)
  })

  it('标签：证据条目「D2-4 · 凭证证据 2 份」用蓝色，挂凭橙色、抽凭绿色', () => {
    const ElTag = { props: ['type'], template: '<i class="tag" :data-type="type"><slot /></i>' }
    const ev = { working_paper_id: 'wp-d2', wp_code: 'D2-4', wp_name: '凭证检查表', wp_missing: false as const, source: 'evidence' as const,
      phase: null, count: 2, legacy: false as const, files: ['回单.pdf', '发票.png'] }
    const wrapper = mount(VoucherLinkTags, {
      props: { links: [link(), link({ source: 'sampling_engine', wp_code: 'E1' }), ev] },
      global: { stubs: { 'el-tag': ElTag } },
    })
    expect(wrapper.findAll('.tag').map((t) => [t.text(), t.attributes('data-type')])).toEqual([
      ['J1 · 挂凭 · 年审', 'warning'], ['E1 · 抽凭 · 年审', 'success'], ['D2-4 · 凭证证据 2 份', 'primary'],
    ])
  })
})
