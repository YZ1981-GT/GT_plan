/**
 * X-3「只写不读」四张的读回路径 —— 行为守卫（design §C5a）
 *
 * spec: x3-adjustment-entry-import-export / 任务 4.2
 * Requirements: 2.5, 6.5, 6.6
 *
 * ## 为什么要有本文件（反 additive 死代码）
 *
 * 任务 4.2 只交付 `loadFromResponses` 函数本身，`onMounted` 接线在任务 11.1 ⇒ 在 11.1 落地
 * 之前，这四个函数在**生产侧没有调用方**。GS10（`__tests__/ieWiringIntegrity.spec.ts`）是
 * **源码结构**判据：它证明读回表达式存在、且覆盖的后缀集 == 清单登记集，但**不执行**函数
 * ⇒ 只靠它，键面写对而取值/字段映射写错（例如把 `-ref` 落到 `refIndex`，而 `L6-3` 的行模型
 * 字段其实叫 `indexRef`）照样全绿、导入的索引列永远读不回界面。
 *
 * 故本文件是这四个函数在 11.1 之前的**唯一真实消费方**：真跑函数、断言回填结果。
 *
 * ## 夹具与期望值的真源
 *
 * 键前缀 / 后缀集 / 后缀→字段映射全部从清单 `backend/data/adjustment_ie_contract.json` 装载
 * （`key_families.per_field.{prefix,suffixes,suffix_to_field}` 与 `key_families.data.{prefix,suffix}`），
 * 本文件**不写任何后缀数组、不写任何键前缀字面量** ⇒ 前端侧的后缀表零第二份、清单是唯一真源。
 * 生产代码的键面与清单分叉（前缀单/双写错、丢后缀、族选错）时，本文件拼出的夹具键读不出行，
 * 必红。
 *
 * ## 与 `read_family` 的联动
 *
 * 每张读哪一族由清单 `read_family` 决定：`per_field` ⇒ 逐后缀键夹具；`data` ⇒ 整行 JSON 夹具。
 * 清单改了族而生产代码没跟着改（或反之），夹具形态与实现对不上 ⇒ 必红。
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useL6Adjustment } from '../useL6Adjustment'
import { useM1Adjustment } from '../useM1Adjustment'
import { useM2Adjustment } from '../useM2Adjustment'
import { useM9Adjustment } from '../useM9Adjustment'

// ─── 清单装载（唯一真源）─────────────────────────────────────────────────────

const HERE = path.dirname(fileURLToPath(import.meta.url))

function findRepoRoot(start: string): string {
  let dir = start
  for (let i = 0; i < 12; i++) {
    if (fs.existsSync(path.join(dir, 'backend', 'data', 'adjustment_ie_contract.json'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  throw new Error('未找到仓库根（backend/data/adjustment_ie_contract.json）')
}

const REPO_ROOT = findRepoRoot(HERE)
const CONTRACT = JSON.parse(
  fs.readFileSync(path.join(REPO_ROOT, 'backend', 'data', 'adjustment_ie_contract.json'), 'utf8'),
) as { sheets: Record<string, LedgerSheet> }

interface LedgerSheet {
  read_family?: string
  key_families?: {
    per_field?: { prefix?: string; suffixes?: string[]; suffix_to_field?: Record<string, string> }
    data?: { prefix?: string; suffix?: string }
  }
}

// ─── 作业面（design §C5a 点名的四张）──────────────────────────────────────────

interface EntriesLike {
  entries: { value: Record<string, unknown>[] }
  loadFromResponses: (responses: Map<string, unknown>) => void
}

interface Target {
  sheetCode: string
  /** 真实生产 composable 的工厂（传入 stub formData 只用到 debouncedSave / saveBatch） */
  make: () => EntriesLike
}

const TARGETS: readonly Target[] = [
  { sheetCode: 'L6-3', make: () => useL6Adjustment(stubFormData()) as unknown as EntriesLike },
  { sheetCode: 'M1-3', make: () => useM1Adjustment(stubFormData()) as unknown as EntriesLike },
  { sheetCode: 'M2-3', make: () => useM2Adjustment(stubFormData()) as unknown as EntriesLike },
  { sheetCode: 'M9-3', make: () => useM9Adjustment(stubFormData()) as unknown as EntriesLike },
]

function stubFormData(): any {
  const responses = ref<Map<string, any>>(new Map())
  return {
    responses,
    allResponses: responses,
    debouncedSave: vi.fn(),
    saveBatch: vi.fn(async () => undefined),
  }
}

// ─── 夹具生成（键面与期望值都由清单派生）──────────────────────────────────────

const FIXTURE_ROWS = 3

/** 后缀→字段映射（清单登记值）；缺登记即抛，不静默兜空 */
function suffixToField(sheetCode: string): Record<string, string> {
  const map = CONTRACT.sheets[sheetCode]?.key_families?.per_field?.suffix_to_field
  if (!map || Object.keys(map).length === 0) {
    throw new Error(`${sheetCode} 清单未登记 key_families.per_field.suffix_to_field`)
  }
  return map
}

/**
 * 逐字段的夹具取值 —— 只按**行模型字段名**分型（金额字段 / AJE-RJE 标记 / 文本），
 * 不按后缀字面量分型 ⇒ 本文件里没有第二份后缀表。
 */
function fixtureValue(field: string, row: number): string {
  if (field.endsWith('Amount')) return String(1000 * row + (field.startsWith('debit') ? 1 : 2))
  if (field === 'type') return row % 2 === 1 ? 'RJE' : 'AJE'
  return `${field}#${row}`
}

function expectedValue(field: string, row: number): string | number {
  const raw = fixtureValue(field, row)
  return field.endsWith('Amount') ? Number(raw) : raw
}

function put(map: Map<string, any>, itemId: string, remark: string | null): void {
  map.set(itemId, { item_id: itemId, conclusion: null, remark })
}

/** per-field 族夹具：`{prefix}{n}-{suffix}` 逐后缀一键（空值落 remark: null，同写入侧与后端导入） */
function perFieldFixture(sheetCode: string, rows: number): Map<string, any> {
  const family = CONTRACT.sheets[sheetCode]?.key_families?.per_field
  const prefix = family?.prefix
  const suffixes = family?.suffixes ?? []
  if (!prefix || suffixes.length === 0) {
    throw new Error(`${sheetCode} 清单未登记 key_families.per_field.{prefix,suffixes}`)
  }
  const mapping = suffixToField(sheetCode)
  const map = new Map<string, any>()
  for (let n = 1; n <= rows; n++) {
    for (const suffix of suffixes) {
      put(map, `${prefix}${n}-${suffix}`, fixtureValue(mapping[suffix], n))
    }
  }
  return map
}

/** `-data` 族夹具：整行 JSON，键集 = 清单 suffix_to_field 的值集（同后端 `_data_payload`） */
function dataFixture(sheetCode: string, rows: number): Map<string, any> {
  const family = CONTRACT.sheets[sheetCode]?.key_families?.data
  const prefix = family?.prefix
  const suffix = family?.suffix
  if (!prefix || !suffix) {
    throw new Error(`${sheetCode} 清单未登记 key_families.data.{prefix,suffix}`)
  }
  const fields = Object.values(suffixToField(sheetCode))
  const map = new Map<string, any>()
  for (let n = 1; n <= rows; n++) {
    const payload: Record<string, unknown> = {}
    for (const field of fields) payload[field] = expectedValue(field, n)
    put(map, `${prefix}${n}${suffix}`, JSON.stringify(payload))
  }
  return map
}

function fixtureFor(sheetCode: string, rows: number = FIXTURE_ROWS): Map<string, any> {
  const readFamily = CONTRACT.sheets[sheetCode]?.read_family
  if (readFamily === 'per_field') return perFieldFixture(sheetCode, rows)
  if (readFamily === 'data') return dataFixture(sheetCode, rows)
  throw new Error(
    `${sheetCode} 清单 read_family=${String(readFamily)} —— ` +
      '任务 4.2 应把这四张改为 per_field / data（none = 读回路径未补齐）',
  )
}

/** 只属于第 `row` 行的夹具键（差集，行号同样由清单键面派生） */
function fixtureKeysOfRow(sheetCode: string, row: number): Map<string, any> {
  const upto = fixtureFor(sheetCode, row)
  const prev = new Set(fixtureFor(sheetCode, row - 1).keys())
  const out = new Map<string, any>()
  for (const [k, v] of upto) if (!prev.has(k)) out.set(k, v)
  return out
}

// ─── 断言 ────────────────────────────────────────────────────────────────────

describe('X-3 只写不读四张的 loadFromResponses（design §C5a / 任务 4.2）', () => {
  it('反空转锚点：四张都已在清单登记读回族与键面（否则下面的夹具无从生成）', () => {
    const missing: string[] = []
    for (const { sheetCode } of TARGETS) {
      const entry = CONTRACT.sheets[sheetCode]
      const readFamily = entry?.read_family
      if (readFamily !== 'per_field' && readFamily !== 'data') {
        missing.push(`${sheetCode}: read_family=${String(readFamily)}`)
        continue
      }
      const family =
        readFamily === 'per_field' ? entry?.key_families?.per_field : entry?.key_families?.data
      if (!family?.prefix) missing.push(`${sheetCode}: key_families.${readFamily}.prefix 缺失`)
    }
    expect(
      missing,
      '清单未登记读回族/键前缀 ⇒ 本文件的夹具键拼不出来、所有行为断言恒空转（design §C5a 第 2 条）',
    ).toEqual([])
    expect(TARGETS.length, '作业面 = design §C5a 点名的四张').toBe(4)
  })

  for (const { sheetCode, make } of TARGETS) {
    describe(sheetCode, () => {
      it('逐后缀/整行 JSON 都能回填到对应行字段（键面与映射取自清单）', () => {
        const adj = make()
        adj.loadFromResponses(fixtureFor(sheetCode))

        expect(
          adj.entries.value.length,
          `${sheetCode}：按清单键面写入 ${FIXTURE_ROWS} 行，读回 ${adj.entries.value.length} 行 ` +
            '⇒ 生产代码的族前缀/族选择与清单分叉（导入后界面读不到 = R6.5 / R6.7 不通过）',
        ).toBe(FIXTURE_ROWS)

        const mapping = suffixToField(sheetCode)
        const mismatched: string[] = []
        adj.entries.value.forEach((row, idx) => {
          const n = idx + 1
          if (row.index !== n) mismatched.push(`第 ${n} 行 index=${String(row.index)}`)
          for (const field of Object.values(mapping)) {
            const want = expectedValue(field, n)
            if (row[field] !== want) {
              mismatched.push(`第 ${n} 行 ${field}: 期望 ${String(want)} / 实际 ${String(row[field])}`)
            }
          }
        })
        expect(
          mismatched,
          `${sheetCode}：读回字段与清单 suffix_to_field 分叉 —— ` +
            '该后缀的导入值永远读不回界面（索引列字段名 indexRef / refIndex 逐 sheet 不同，禁用全局常量）',
        ).toEqual([])
      })

      it('取值为空的行不算断档（判据是键存在，不是值非空）', () => {
        const readFamily = CONTRACT.sheets[sheetCode]?.read_family
        if (readFamily !== 'per_field') {
          // `-data` 族的行存在判据是整行 JSON 非空，空 JSON 本身就是断档 ⇒ 本条只对逐字段族有意义
          expect(readFamily).toBe('data')
          return
        }
        const family = CONTRACT.sheets[sheetCode]!.key_families!.per_field!
        const mapping = suffixToField(sheetCode)
        const descSuffix = Object.keys(mapping).find((s) => mapping[s] === 'description')
        expect(descSuffix, `${sheetCode}：清单 suffix_to_field 里没有映到 description 的后缀`).toBeTruthy()

        const map = perFieldFixture(sheetCode, 2)
        // 第 2 行的「调整事项说明」清空（键仍在、值为 null）—— 写入侧 `entry.description || null`
        // 与后端导入的 `_scalar_cell` 都是这个形态
        put(map, `${family.prefix}2-${descSuffix}`, null)
        const adj = make()
        adj.loadFromResponses(map)
        expect(
          adj.entries.value.length,
          `${sheetCode}：说明为空的行被当成断档而截断 ⇒ 导入的行会少（用 remark 非空当行判据的典型错法）`,
        ).toBe(2)
        expect(adj.entries.value[1].description).toBe('')
      })

      it('行号断档即停，不造幽灵空行', () => {
        // 第 1、2 行 + 跳号的第 5 行（第 3、4 行整行缺键）
        const map = fixtureFor(sheetCode, 2)
        for (const [k, v] of fixtureKeysOfRow(sheetCode, 5)) map.set(k, v)
        const adj = make()
        adj.loadFromResponses(map)
        expect(
          adj.entries.value.length,
          `${sheetCode}：行序应自第 1 行连续取到断档为止（同范本 useM6Adjustment 与后端 _rows_from_per_field_family）`,
        ).toBe(2)
      })

      it('空 allResponses 不清空既有行（无持久化时不覆盖界面）', () => {
        const adj = make()
        adj.loadFromResponses(fixtureFor(sheetCode))
        expect(adj.entries.value.length).toBe(FIXTURE_ROWS)
        adj.loadFromResponses(new Map())
        expect(
          adj.entries.value.length,
          `${sheetCode}：空 Map 会把已加载的行清空 ⇒ 刷新时机不对就把界面清空`,
        ).toBe(FIXTURE_ROWS)
      })
    })
  }

  it('M2-3：表级独立键不得被当成分录行（清单 observed.other_data_keys）', () => {
    const sheetCode = 'M2-3'
    const standalone = ((CONTRACT.sheets[sheetCode] as any)?.observed?.other_data_keys ??
      []) as string[]
    expect(
      standalone.length,
      'M2-3 的清单 observed.other_data_keys 应登记「调整分录说明」表级键（design §C5a / R2.4）',
    ).toBeGreaterThan(0)

    const map = fixtureFor(sheetCode, 2)
    for (const key of standalone) put(map, key, '表级说明：不属于任何一行')

    const adj = TARGETS.find((t) => t.sheetCode === sheetCode)!.make()
    adj.loadFromResponses(map)
    expect(
      adj.entries.value.length,
      '表级独立键被当成了一行（它不带行号、后缀也不在登记的 10 项里）',
    ).toBe(2)
    const leaked = adj.entries.value.flatMap((row, idx) =>
      Object.entries(row)
        .filter(([, v]) => typeof v === 'string' && v.includes('表级说明'))
        .map(([f]) => `第 ${idx + 1} 行 ${f}`),
    )
    expect(leaked, '表级说明文本被读进了行字段').toEqual([])
  })

  it('M9-3：ociBlock 必须随整行 JSON 读回（design E20 的第 11 个字段）', () => {
    const mapping = suffixToField('M9-3')
    expect(
      Object.values(mapping),
      'M9-3 清单 suffix_to_field 应含 ociBlock（比其余三张多一项）',
    ).toContain('ociBlock')

    const adj = TARGETS.find((t) => t.sheetCode === 'M9-3')!.make()
    adj.loadFromResponses(fixtureFor('M9-3'))
    const blocks = adj.entries.value.map((r) => r.ociBlock)
    expect(
      blocks,
      'ociBlock 未读回 ⇒ 导入后 OCI 分类恒空（不可重分类 / 可重分类分不出）',
    ).toEqual([1, 2, 3].map((n) => expectedValue('ociBlock', n)))
  })

  it('type 是透传兜底、不做大小写归一（清单登记大写枚举）', () => {
    // 小写值原样穿过 `|| 'AJE'`（它只兜 falsy）⇒ 该行在 AJE / RJE 两个分区都不出现，
    // 是清单 unmapped_fields[type] 量化过的静默丢行，不该被读回侧偷偷改掉
    const sheetCode = 'L6-3'
    const family = CONTRACT.sheets[sheetCode]!.key_families!.per_field!
    const mapping = suffixToField(sheetCode)
    const typeSuffix = Object.keys(mapping).find((s) => mapping[s] === 'type')!
    const map = perFieldFixture(sheetCode, 1)
    put(map, `${family.prefix}1-${typeSuffix}`, 'aje')
    const lower = TARGETS.find((t) => t.sheetCode === sheetCode)!.make()
    lower.loadFromResponses(map)
    expect(lower.entries.value[0].type, '读回侧不得把小写归一成大写（归一会掩盖落值缺陷）').toBe(
      'aje',
    )

    // falsy 才兜 'AJE'（同范本 useM6Adjustment.loadFromResponses）
    put(map, `${family.prefix}1-${typeSuffix}`, null)
    const empty = TARGETS.find((t) => t.sheetCode === sheetCode)!.make()
    empty.loadFromResponses(map)
    expect(empty.entries.value[0].type).toBe('AJE')
  })
})
