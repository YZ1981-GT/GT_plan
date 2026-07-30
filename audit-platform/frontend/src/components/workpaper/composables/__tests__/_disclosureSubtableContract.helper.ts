/**
 * 披露子表契约测试 —— 参数化 helper（各循环复用）
 *
 * 抽自 `k1NoteSubtableContract.spec.ts`（已验证范式）。各循环只需 ~20 行接入：
 *
 * ```ts
 * import { describe } from 'vitest'
 * import { runDisclosureSubtableContract } from './_disclosureSubtableContract.helper'
 * import { G4_NOTE_SECTION, G4_LISTED_SUBTABLE, G4_SOE_SUBTABLE } from '../g4NoteSectionMap'
 * import { buildG4ListedColumns, buildG4SoeColumns } from '../g4DisclosureSyncPayload'
 *
 * runDisclosureSubtableContract({
 *   cycle: 'G4',
 *   variants: [
 *     { variant: 'listed', section: G4_NOTE_SECTION.listed,
 *       subtables: G4_LISTED_SUBTABLE, columns: buildG4ListedColumns() },
 *     { variant: 'soe', section: G4_NOTE_SECTION.soe,
 *       subtables: G4_SOE_SUBTABLE, columns: buildG4SoeColumns() },
 *   ],
 * })
 * ```
 *
 * 覆盖 5 条 Correctness Property：
 * - P1 子表名与模板 `tables[].name` 逐字一致（错位 → 孤儿子表：附注 TAB 永空 + 底稿数据丢失）
 * - P2 章节号存在于对应 variant 的模板
 * - P3 每张表在 `group`（多级表头）与 `flat`（单级表头）之间明确表态，不得都无、不得并存
 * - P4 列标签与分组名为纯文本（`el-table-column :label` 与 Word 导出都不解析 HTML）
 * - P5 `columns` 的标签列头与该表 `headers[0]` 一致
 *
 * Spec: .kiro/specs/disclosure-sync-path-buildout/ Task 1.2
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/**
 * 契约侧的列定义视图：同时要吃两种输入 ——
 * ① 各循环 `buildXColumns()` 返回的真实 `ColumnDef`（`disclosureColumnDefs.ts`）；
 * ② `note_template_*.json` 里解析出来的模板列。
 *
 * 🔴 **不要加 `[k: string]: unknown` 索引签名**：带索引签名的类型无法从「不带索引
 * 签名的 interface」赋值（TS 结构化赋值规则）→ 8 个循环的契约 spec 全部报 TS2322
 * （`Record<string, ColumnDef[]>` 不可赋给 `Readonly<Record<string, ContractColumnDef[]>>`）。
 * 这类错误 Volar 逐文件诊断查不出，只有全项目 `vue-tsc --noEmit` 能揪出来。
 */
export interface ContractColumnDef {
  key?: string
  label?: string
  is_label?: boolean
  group?: string
  flat?: boolean
  format?: string
}

interface NoteTable {
  name?: string
  headers?: string[]
  columns?: ContractColumnDef[]
  guidance?: string
  _column_groups?: unknown
}

interface NoteSection {
  section_number?: string
  section_title?: string
  tables?: NoteTable[]
  text_sections?: string[]
}

export type DisclosureVariantKey = 'listed' | 'soe'

export interface VariantContractSpec {
  variant: DisclosureVariantKey
  /** 附注章节号，如 '五、14' */
  section: string
  /** 子表名映射：`{语义键: 模板表名}` */
  subtables: Readonly<Record<string, string>>
  /** 列定义：`{模板表名: ColumnDef[]}` */
  columns: Readonly<Record<string, ContractColumnDef[]>>
  /**
   * 允许暂不校验 `columns` 的表名（模板侧列结构尚未补齐时）。
   * 每条必须写理由，随模板补齐逐个移出。
   */
  columnsPending?: Readonly<Record<string, string>>
}

export interface DisclosureContractOptions {
  /** 循环号，如 'G4'（仅用于测试标题） */
  cycle: string
  variants: readonly VariantContractSpec[]
}

const TEMPLATE_FILE: Record<DisclosureVariantKey, string> = {
  listed: 'note_template_listed.json',
  soe: 'note_template_soe.json',
}

const REPO_ROOT = resolve(__dirname, '../../../../../../..')

const _sectionCache = new Map<string, NoteSection[]>()

function loadSections(file: string): NoteSection[] {
  const cached = _sectionCache.get(file)
  if (cached) return cached
  const path = resolve(REPO_ROOT, 'backend/data', file)
  const raw = JSON.parse(readFileSync(path, 'utf-8')) as { sections?: NoteSection[] }
  const sections = raw.sections ?? []
  _sectionCache.set(file, sections)
  return sections
}

function findSection(variant: DisclosureVariantKey, sectionNumber: string): NoteSection | undefined {
  return loadSections(TEMPLATE_FILE[variant]).find(
    (s) => String(s.section_number ?? '').trim() === sectionNumber,
  )
}

const HTML_RE = /<[^>]+>/

/** 判定某表的表头声明状态（与后端 `_extract_column_groups` 三态同口径） */
export function columnDeclState(cols: readonly ContractColumnDef[] | undefined):
  | 'flat'
  | 'group'
  | 'none'
  | 'conflict' {
  const defs = (cols ?? []).filter((c) => c && typeof c === 'object')
  if (defs.length === 0) return 'none'
  const hasFlat = defs.some((c) => c.flat)
  const hasGroup = defs.some((c) => c.group)
  if (hasFlat && hasGroup) return 'conflict'
  if (hasFlat) return 'flat'
  if (hasGroup) return 'group'
  return 'none'
}

/**
 * 跑一整套披露子表契约。在 spec 文件顶层调用即可。
 */
export function runDisclosureSubtableContract(opts: DisclosureContractOptions): void {
  const { cycle, variants } = opts

  describe(`${cycle} 披露子表 ↔ note_template 契约`, () => {
    // ── P2: 章节号存在 ───────────────────────────────────────────
    for (const v of variants) {
      it(`P2 ${v.variant} 章节 ${v.section} 存在于 ${TEMPLATE_FILE[v.variant]}`, () => {
        const sec = findSection(v.variant, v.section)
        expect(
          sec,
          `模板缺章节 ${v.section} → 必须先补模板章节，不得同步到不存在的章节`,
        ).toBeDefined()
      })
    }

    // ── P1: 子表名逐字一致 ───────────────────────────────────────
    for (const v of variants) {
      const sec = findSection(v.variant, v.section)
      const names = new Set((sec?.tables ?? []).map((t) => t.name))
      const entries = Object.entries(v.subtables)

      it(`P1 ${v.variant} 声明了子表（防空映射空转）`, () => {
        expect(entries.length).toBeGreaterThan(0)
      })

      it.each(entries)(
        `P1 ${v.variant} %s → 「%s」存在于 ${v.section}`,
        (_key, name) => {
          expect(
            names.has(name),
            `子表名与模板不一致会产生孤儿子表（附注 TAB 永空 + 底稿数据丢失）。` +
              `模板现有表名：${[...names].join(' | ')}`,
          ).toBe(true)
        },
      )

      it(`P1 ${v.variant} 子表名无重复`, () => {
        const vals = entries.map(([, n]) => n)
        expect(new Set(vals).size).toBe(vals.length)
      })
    }

    // ── P3/P4/P5: 列定义 ────────────────────────────────────────
    for (const v of variants) {
      const sec = findSection(v.variant, v.section)
      const byName = new Map((sec?.tables ?? []).map((t) => [t.name, t]))
      const pending = v.columnsPending ?? {}
      const tableNames = Object.values(v.subtables)

      it(`P3 ${v.variant} 每张表在 group / flat 之间明确表态`, () => {
        const offenders: string[] = []
        for (const name of tableNames) {
          if (name in pending) continue
          const state = columnDeclState(v.columns[name])
          if (state !== 'flat' && state !== 'group') offenders.push(`${name}(${state})`)
        }
        expect(
          offenders,
          `未表态的表在 seed 路径会被 _infer_groups_from_headers 塞凭空父表头；` +
            `单级表头标 flat，多级表头标 group`,
        ).toEqual([])
      })

      it(`P4 ${v.variant} 列标签与分组名为纯文本`, () => {
        const bad: string[] = []
        for (const name of tableNames) {
          for (const c of v.columns[name] ?? []) {
            if (HTML_RE.test(String(c.label ?? ''))) bad.push(`${name}.label=${c.label}`)
            if (HTML_RE.test(String(c.group ?? ''))) bad.push(`${name}.group=${c.group}`)
          }
        }
        expect(
          bad,
          `el-table-column :label 与 Word 导出都不解析 HTML，md 表格搬来的 <br/> 会显示为字面量`,
        ).toEqual([])
      })

      it(`P5 ${v.variant} 标签列头与模板 headers[0] 一致`, () => {
        const mismatches: string[] = []
        for (const name of tableNames) {
          if (name in pending) continue
          const defs = v.columns[name] ?? []
          if (defs.length === 0) continue
          const labelDef = defs.find((c) => c.is_label) ?? defs[0]
          const expected = byName.get(name)?.headers?.[0]
          if (expected === undefined) continue
          if (String(labelDef.label ?? '') !== String(expected)) {
            mismatches.push(`${name}: ${labelDef.label} ≠ ${expected}`)
          }
        }
        expect(mismatches, '标签列头与模板首列不一致会导致同步后表头错位').toEqual([])
      })

      it(`${v.variant} columnsPending 每条都有理由`, () => {
        const blank = Object.entries(pending)
          .filter(([, r]) => !String(r ?? '').trim())
          .map(([k]) => k)
        expect(blank, 'columnsPending 每条必须写明为何暂不校验').toEqual([])
      })

      it(`${v.variant} columnsPending 不得残留已补齐的表`, () => {
        const fixed = Object.keys(pending).filter((n) => {
          const st = columnDeclState(v.columns[n])
          return st === 'flat' || st === 'group'
        })
        expect(fixed, `以下表已表态，请从 columnsPending 移出：${fixed.join(', ')}`).toEqual([])
      })
    }
  })
}

/** 供各循环 spec 复用：断言载荷不适用变体时返回 null（P5 of design） */
export function expectNullForInapplicableVariant(
  buildPayload: (...args: never[]) => unknown,
  buildArgs: readonly unknown[],
  label = '不适用变体',
): void {
  it(`${label} 时 buildSyncPayload 返回 null`, () => {
    expect(buildPayload(...(buildArgs as never[]))).toBeNull()
  })
}
