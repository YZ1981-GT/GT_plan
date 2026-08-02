/**
 * 平台级守卫：**推「多段共享表」必须带 `_row_scope`**。
 *
 * **Validates: disclosure-note-row-level-merge Requirements 8.2, 8.3 / Property 15**
 *
 * 共享表 = 同一张附注子表内按科目分段、每段归属不同循环（段首行带
 * `report_row_code`）。全库实测 **29 张**（listed 23 / soe 6），清单真源 =
 * `backend/data/note_shared_table_segments.json`（由
 * `backend/scripts/gen/gen_note_shared_table_segments.py --write` 生成）。
 *
 * 🔴 不带 `_row_scope` 就推这类表 = **表级整表覆盖**，会清掉其他循环已录的段。
 * 服务端只在声明了 `_row_scope` 时才走行级合并（不声明就是既有的表级语义）。
 *
 * 含两条反向自检：
 * 1. 去掉 E1 的 `_row_scope` 声明后，判定函数必须把该文件报为违规
 * 2. `stripComments()` 必须真的剥掉注释（本文件与被扫文件的说明里都写了被禁的反例）
 */
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const REPO_ROOT = resolve(__dirname, '../../../../../..')
const MANIFEST = resolve(REPO_ROOT, 'backend/data/note_shared_table_segments.json')
const COMPOSABLES = resolve(__dirname, '../composables')

interface ManifestTable {
  variant: string
  section_number: string
  section_title: string
  table_name: string
  row_count: number
  segments: Array<{
    row_code: string
    label: string
    start: number
    /** 到下一个段首前 */
    end: number
    /** **可写区**右界 —— 排除段尾的表级合计行（合计不属于任何 owner） */
    data_end: number
  }>
}

const manifest = JSON.parse(readFileSync(MANIFEST, 'utf-8')) as {
  counts: Record<string, number>
  tables: ManifestTable[]
}

/**
 * **不参与源码扫描**的共享表名 + 理由。
 *
 * 这些名字来自 md 重建留下的脏数据（表头首格泄漏 / 裸续表名 / 空表名），
 * 拿去做「源码里是否出现该字面量」的扫描会大面积误报（`项  目` 遍地都是）。
 * 属另一个 data-hygiene 待办；本守卫只保证不被误用。
 */
const GENERIC_TABLE_NAMES: Record<string, string> = {
  '': '空表名（listed 风险管理）—— 不可作 sub_table_data 键，后端 template_rows 已拒绝',
  '项  目': '表头首格泄漏，多循环模板里遍地出现 → 源码扫描必误报',
  // `续：` 曾在此登记；已由 restricted-assets-note-row-scope-rollout Task 3
  // 正名为「所有权或使用权受到限制的资产（续：上年年末）」→ 按 R3「已修好必删」移出
}

/** 剥掉注释：说明文字里会写被禁的反例。 */
function stripComments(src: string): string {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

/** 该 map 文件里出现的（可扫描的）共享表名字面量。 */
function sharedTableLiterals(body: string, names: readonly string[]): string[] {
  return names.filter(
    (name) => body.includes(`'${name}'`) || body.includes(`"${name}"`) || body.includes(`\`${name}\``),
  )
}

/** 该文件是否声明了行级合并（`_row_scope` + owner_row_code）。 */
function declaresRowScope(body: string): boolean {
  return body.includes('_row_scope') && body.includes('owner_row_code')
}

const SCANNABLE = [...new Set(manifest.tables.map((t) => t.table_name))].filter(
  (n) => !(n in GENERIC_TABLE_NAMES),
)

/** 表名 → 该表允许的 owner code 全集（跨变体并集）。 */
const OWNER_CODES: Record<string, Set<string>> = {}
for (const t of manifest.tables) {
  const set = (OWNER_CODES[t.table_name] ??= new Set())
  for (const s of t.segments) set.add(s.row_code)
}

/**
 * 已知会命中但**暂不接线**的表 → 登记理由 + 归属 spec。
 * 每条随对应循环接入后必须移出（只许缩不许扩）。
 */
const NOT_WIRED_ALLOWLIST: Record<string, { reason: string; owner: string }> = {}

/**
 * **单一 owner 独占整张表** → 表级覆盖是正确语义，不需要 `_row_scope`。
 *
 * 判据：该表的**全部段**都由同一个底稿推送。此时行级合并只会增加复杂度
 * （合并结果 ≡ 整替换，见后端 Property 12 的同款零回归论证）。
 * 🔴 一旦有第二个循环开始推同一张表，必须移出本表并改走 `_row_scope`。
 */
const WHOLE_TABLE_OWNER: Record<string, { reason: string; segments: string[] }> = {
  未经抵销的递延所得税资产和递延所得税负债: {
    reason:
      'N1 递延所得税披露表**同时**承载资产段（BS-036）与负债段（BS-067）—— '
      + 'N1TabDisclosure 的表(1) 本就分「一、递延所得税资产 / 二、递延所得税负债」两段录入，'
      + 'N3 与 N1 共章节但不独立推送（N3 自造的披露 Tab 已在 n-cycle spec 里删除）',
    segments: ['BS-036', 'BS-067'],
  },
  以抵销后净额列示的递延所得税资产或负债: {
    reason: '同上：N1 的「以抵销后净额列示」表两段皆由 N1 推送（源模板 A36=A13 行镜像）',
    segments: ['BS-036', 'BS-067'],
  },
}

function mapFiles(): string[] {
  return readdirSync(COMPOSABLES).filter((f) => f.endsWith('NoteSectionMap.ts'))
}

describe('共享表清单（真源自洽）', () => {
  it('清单是 29 张（listed 23 / soe 6）', () => {
    expect(manifest.counts).toEqual({ listed: 23, soe: 6 })
    expect(manifest.tables.length).toBe(29)
  })

  it('每张表 ≥2 段且区间不重叠', () => {
    for (const t of manifest.tables) {
      expect(t.segments.length, `${t.section_number} ${t.table_name}`).toBeGreaterThanOrEqual(2)
      let prev = 0
      for (const s of t.segments) {
        expect(s.start).toBeGreaterThanOrEqual(prev)
        expect(s.end).toBeGreaterThan(s.start)
        prev = s.end
      }
    }
  })

  it('🔴 每段都有 data_end（可写区右界），且 start < data_end ≤ end', () => {
    // `data_end` 剔除段尾的**表级合计行** —— 合计不属于任何 owner，
    // 若算进末段，末段 owner 一推数据就会把整表合计删掉。
    for (const t of manifest.tables) {
      for (const s of t.segments) {
        expect(s.data_end, `${t.section_number} ${t.table_name} ${s.row_code} 缺 data_end`)
          .toBeTypeOf('number')
        expect(s.data_end).toBeGreaterThan(s.start)
        expect(s.data_end).toBeLessThanOrEqual(s.end)
      }
    }
  })

  it('🔴 实测基线：15 个段的可写区窄于段区间（14 表尾合计行 + 1 unowned 兜底行）', () => {
    // 第 15 条 = soe `八、93 受限资产` 末行「其他」（模板标 `row_type: "unowned"`，
    // 由 restricted-assets-note-row-scope-rollout Task 3 加）
    const narrowed = manifest.tables.flatMap((t) =>
      t.segments
        .filter((s) => s.data_end !== s.end)
        .map((s) => `${t.variant} ${t.section_number} ${t.table_name} ${s.row_code}`),
    )
    expect(narrowed.length, `受影响段数变了：${narrowed.join(' / ')}`).toBe(15)
    expect(narrowed.some((x) => x.includes('八、93'))).toBe(true)
    // 外币表（首个消费者）零影响 → 引入 data_end 前后逐字等价
    expect(narrowed.some((x) => x.includes('外币货币性项目'))).toBe(false)
    // 受限资产 / 列报项目 / 筹资活动负债变动 —— 高优先级三张表都在其中
    for (const key of ['五、32', '五、71', '八、91', '八、81']) {
      expect(narrowed.some((x) => x.includes(key)), `${key} 应在清单里`).toBe(true)
    }
  })

  it('脏表名登记表只许缩不许扩，且每条都真实存在于清单里', () => {
    const names = new Set(manifest.tables.map((t) => t.table_name))
    for (const [name, reason] of Object.entries(GENERIC_TABLE_NAMES)) {
      expect(names.has(name), `已不在清单里的脏表名请移出：${name}`).toBe(true)
      expect(reason.length, `${name} 必须写明理由`).toBeGreaterThan(10)
    }
    expect(Object.keys(GENERIC_TABLE_NAMES).length).toBeLessThanOrEqual(2)
  })

  it('可扫描表名非空（否则下面的扫描全部空转）', () => {
    // 29 张表 → 17 个去重表名 → 剔掉 2 个脏名后 **15 个**可扫描
    //（`续：` 已正名故不再是脏名，2026-08-02 实测）
    expect(SCANNABLE.length).toBe(15)
    expect(SCANNABLE).toContain('外币货币性项目')
    expect(SCANNABLE).toContain('所有权或使用权受到限制的资产（续：上年年末）')
  })

  it('🟡 记录：4 个 `项  目（…）` 派生表名仍带表头泄漏痕迹（其中一个还含 `<br/>`）', () => {
    // 属另一个 data-hygiene 待办（本 spec 不处理）：这些名字足够具体不至于误报，
    // 但作为 `sub_table_data` 的键很脆弱 —— 一旦模板重建就会漂移成孤儿表。
    const leaky = SCANNABLE.filter((n) => n.startsWith('项  目'))
    expect(leaky.length).toBe(4)
    expect(leaky.some((n) => n.includes('<br/>')), '含 HTML 的表名').toBe(true)
  })
})

describe('Property 15：推共享表必带 _row_scope', () => {
  it('全量扫描 *NoteSectionMap.ts', () => {
    const offenders: string[] = []
    const wired: string[] = []
    for (const file of mapFiles()) {
      const raw = readFileSync(resolve(COMPOSABLES, file), 'utf-8')
      const body = stripComments(raw)
      const hits = sharedTableLiterals(body, SCANNABLE).filter(
        (n) => !(n in NOT_WIRED_ALLOWLIST) && !(n in WHOLE_TABLE_OWNER),
      )
      if (!hits.length) continue
      if (declaresRowScope(body)) {
        wired.push(`${file} → ${hits.join('、')}`)
        continue
      }
      offenders.push(`${file} 推共享表 ${hits.join('、')} 但未声明 _row_scope`)
    }
    expect(offenders, '表级覆盖会清掉其他循环已录的段 —— 必须声明 _row_scope').toEqual([])
    // 反向自检：至少有一个已接线的消费者，否则本用例恒绿
    expect(wired.length, '一个共享表消费者都扫不到 → 扫描逻辑失效').toBeGreaterThanOrEqual(1)
    expect(wired.join(' ')).toContain('e1FxNoteSectionMap.ts')
  })

  it('已声明的 owner_row_code 必须 ∈ 该表段集合', () => {
    for (const file of mapFiles()) {
      const body = stripComments(readFileSync(resolve(COMPOSABLES, file), 'utf-8'))
      if (!declaresRowScope(body)) continue
      const hits = sharedTableLiterals(body, SCANNABLE).filter((n) => !(n in WHOLE_TABLE_OWNER))
      expect(hits.length, `${file} 声明了 _row_scope 却没推任何共享表`).toBeGreaterThanOrEqual(1)
      const codes = [...body.matchAll(/'(BS-\d{3})'/g)].map((m) => m[1])
      expect(codes.length, `${file} 未见 owner code 字面量`).toBeGreaterThanOrEqual(1)
      const allowed = new Set<string>()
      for (const name of hits) for (const c of OWNER_CODES[name] || []) allowed.add(c)
      for (const c of codes) {
        expect(allowed.has(c), `${file} 的 owner_row_code ${c} 不是这些表的段首 code`).toBe(true)
      }
    }
  })

  it('未接线登记表为空或每条都写明归属（只许缩不许扩）', () => {
    for (const [name, meta] of Object.entries(NOT_WIRED_ALLOWLIST)) {
      expect(SCANNABLE, `${name} 不在可扫描清单里`).toContain(name)
      expect(meta.reason.length).toBeGreaterThan(10)
      expect(meta.owner.length).toBeGreaterThan(2)
    }
  })
})

describe('🔴 反向自检', () => {
  it('去掉 E1 的 _row_scope 声明 → 判定函数报违规', () => {
    const raw = readFileSync(resolve(COMPOSABLES, 'e1FxNoteSectionMap.ts'), 'utf-8')
    const body = stripComments(raw)
    expect(declaresRowScope(body)).toBe(true)
    expect(sharedTableLiterals(body, SCANNABLE)).toContain('外币货币性项目')

    // 🔴 替换串里不能再含 `_row_scope`（否则 includes 仍命中 → 自检空转）
    const mutated = body.replace(/_row_scope/g, 'ROWSCOPE_REMOVED')
    expect(mutated).not.toContain('_row_scope')
    expect(declaresRowScope(mutated), '去掉声明后仍判为安全 → 守卫空转').toBe(false)
  })

  it('WHOLE_TABLE_OWNER 登记表每条都真实存在且写明段归属', () => {
    for (const [name, meta] of Object.entries(WHOLE_TABLE_OWNER)) {
      expect(SCANNABLE, `${name} 已不在共享表清单里 → 请移出`).toContain(name)
      expect(meta.reason.length).toBeGreaterThan(20)
      const codes = OWNER_CODES[name]
      expect([...codes].sort()).toEqual([...meta.segments].sort())
    }
  })

  it('stripComments 真的剥掉了注释', () => {
    const raw = readFileSync(resolve(COMPOSABLES, 'e1FxNoteSectionMap.ts'), 'utf-8')
    expect(raw).toContain('跨循环共享表')
    expect(stripComments(raw)).not.toContain('跨循环共享表')
    // 不能把代码也剥掉
    expect(stripComments(raw)).toContain('export function buildE1FxSyncPayload')
  })
})
