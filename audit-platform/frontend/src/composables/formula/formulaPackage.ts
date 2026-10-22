/**
 * 公式包（JSON）：把一个项目的公式适配带到另一个项目 / 另一套环境（spec formula-governance-coverage-closure R4）。
 *
 * - 导出只收**本项目适配**（层级 = 本项目 / 模板 / 暂缓采用）。系统预设与全局设置每个环境本来就有，
 *   带进包再导入会把它们复制成目标项目的适配 —— 以后全局一更新，这个项目反倒要逐条确认。
 * - 导入写本项目适配，走公式管理中心保存同一接口（PUT overrides）与同一并发校验：
 *   已有适配带本地修订号；与目标项目现有定义相同的不写；适用范围不同的整域跳过
 *   （同一行编号在国企 / 上市模板里不是同一个项目，宁缺毋错）。
 * - 域清单取后端（含推送规则），不在前端写死。
 */
import {
  formulaErrorText, formulaSettingsApi,
  type Definition, type EffectiveResult, type FormulaDomainInfo, type SlotChange,
} from '@/composables/formula/useFormulaSettings'

export const FORMULA_PACKAGE_FORMAT = 'gt_formula_package'
export const FORMULA_PACKAGE_VERSION = '1.1'
/** 本项目适配所在的层（effective 接口的 layer） */
export const ADAPTATION_LAYERS: readonly string[] = ['project', 'template', 'pinned']

export interface PackageSlot {
  slot_key: string
  label: string
  layer: string
  definition: Definition
  structure?: Record<string, any> | null
}
export interface PackageDomain { scope: string; slot_count: number; slots: PackageSlot[] }
export interface FormulaPackage {
  version: string
  format: string
  exported_at: string
  source: string
  domains: Record<string, PackageDomain>
}

export interface DomainOutcome { domain: string; label: string; count: number; reason: string }
export interface ApplyReport {
  written: number
  unchanged: number
  writtenDomains: string[]
  skipped: DomainOutcome[]
  failed: DomainOutcome[]
}

const isObj = (v: unknown): v is Record<string, any> => !!v && typeof v === 'object' && !Array.isArray(v)

function stable(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(stable)
  if (!isObj(v)) return v
  return Object.fromEntries(Object.keys(v).sort().map((k) => [k, stable(v[k])]))
}

/** 两个定义逐字段相同（与键顺序无关） */
export function sameDefinition(a: unknown, b: unknown): boolean {
  return JSON.stringify(stable(a ?? null)) === JSON.stringify(stable(b ?? null))
}

const domainLabel = (infos: FormulaDomainInfo[], key: string) => infos.find((d) => d.key === key)?.label || key

/** 逐域读本项目有效定义，收本项目适配。任何一个域读失败就整体失败（不生成缺域的包）。 */
export async function buildProjectPackage(projectId: string): Promise<{ pack: FormulaPackage; count: number }> {
  const { domains } = await formulaSettingsApi.domains()
  const pack: FormulaPackage = {
    version: FORMULA_PACKAGE_VERSION, format: FORMULA_PACKAGE_FORMAT,
    exported_at: new Date().toISOString(), source: `project:${projectId}`, domains: {},
  }
  let count = 0
  for (const info of domains) {
    let eff: EffectiveResult
    try {
      eff = await formulaSettingsApi.effective(projectId, info.key)
    } catch (e) {
      throw new Error(formulaErrorText(e, `读取「${info.label}」失败`))
    }
    const slots: PackageSlot[] = (eff?.slots || [])
      .filter((s) => ADAPTATION_LAYERS.includes(s.layer) && isObj(s.definition))
      .map((s) => ({
        slot_key: s.slot_key, label: s.label, layer: s.layer, definition: s.definition as Definition,
        structure: isObj(s.structure) && Object.keys(s.structure).length ? s.structure : null,
      }))
    if (!slots.length) continue
    pack.domains[info.key] = { scope: eff.scope, slot_count: slots.length, slots }
    count += slots.length
  }
  return { pack, count }
}

/** 解析包文件文本；结构不对给出原因。未知域、缺字段的条目记为提醒并剔除。 */
export function parseFormulaPackage(
  text: string, infos: FormulaDomainInfo[],
): { domains: Record<string, PackageDomain>; total: number; warnings: string[] } | { error: string } {
  let pack: any
  try { pack = JSON.parse(text) } catch { return { error: '文件不是合法的 JSON 格式' } }
  if (!isObj(pack) || pack.format !== FORMULA_PACKAGE_FORMAT) {
    return { error: '该文件不是标准公式包（缺少 format: "gt_formula_package" 标识）' }
  }
  const known = new Set(infos.map((d) => d.key))
  const warnings: string[] = []
  const out: Record<string, PackageDomain> = {}
  let slotCount = 0
  for (const [key, raw] of Object.entries(isObj(pack.domains) ? pack.domains : {})) {
    if (!known.has(key)) { warnings.push(`跳过未知的公式类别「${key}」`); continue }
    const slots: any[] = isObj(raw) && Array.isArray(raw.slots) ? raw.slots : []
    const bySlot = new Map<string, PackageSlot>()
    for (const s of slots) {
      if (!isObj(s) || typeof s.slot_key !== 'string' || !s.slot_key.trim() || !isObj(s.definition)) continue
      bySlot.set(s.slot_key, {
        slot_key: s.slot_key, label: String(s.label || ''), layer: String(s.layer || ''),
        definition: s.definition, structure: isObj(s.structure) ? s.structure : null,
      })
    }
    if (bySlot.size !== slots.length) {
      warnings.push(`「${domainLabel(infos, key)}」有 ${slots.length - bySlot.size} 条缺公式位或定义（或重复），已忽略`)
    }
    if (!bySlot.size) continue
    out[key] = { scope: String((isObj(raw) && raw.scope) || ''), slot_count: bySlot.size, slots: [...bySlot.values()] }
    slotCount += bySlot.size
  }
  return { domains: out, total: slotCount, warnings }
}

/** 把解析好的包写成本项目适配，逐域一个请求（每域在后端是一个事务）。 */
export async function applyFormulaPackage(
  projectId: string, domains: Record<string, PackageDomain>, infos: FormulaDomainInfo[],
): Promise<ApplyReport> {
  const report: ApplyReport = { written: 0, unchanged: 0, writtenDomains: [], skipped: [], failed: [] }
  for (const [key, dom] of Object.entries(domains)) {
    const label = domainLabel(infos, key)
    let eff: EffectiveResult
    try {
      eff = await formulaSettingsApi.effective(projectId, key)
    } catch (e) {
      report.failed.push({ domain: key, label, count: dom.slots.length, reason: formulaErrorText(e, '读取本项目定义失败') })
      continue
    }
    if (eff.frozen) {
      report.skipped.push({ domain: key, label, count: dom.slots.length, reason: '本项目已归档（只读）' })
      continue
    }
    if (dom.scope && eff.scope && dom.scope !== eff.scope) {
      report.skipped.push({ domain: key, label, count: dom.slots.length,
        reason: `适用范围不同（包：${dom.scope}，本项目：${eff.scope}）` })
      continue
    }
    const current = new Map((eff.slots || []).map((s) => [s.slot_key, s]))
    const items: SlotChange[] = []
    for (const s of dom.slots) {
      const cur = current.get(s.slot_key)
      if (cur && sameDefinition(cur.definition, s.definition)) { report.unchanged += 1; continue }
      items.push({
        slot_key: s.slot_key, definition: s.definition,
        expected_version: cur?.local_version ?? null,
        label: s.label || cur?.label || '',
        structure: s.structure || (cur && Object.keys(cur.structure || {}).length ? cur.structure : null),
      })
    }
    if (!items.length) continue
    try {
      await formulaSettingsApi.saveOverrides(projectId, key, items)
      report.written += items.length
      report.writtenDomains.push(key)
    } catch (e) {
      report.failed.push({ domain: key, label, count: items.length, reason: formulaErrorText(e, '写入失败') })
    }
  }
  return report
}

/** 结果一句话（成功 / 未改 / 跳过 / 失败逐类写明） */
export function describeApplyReport(r: ApplyReport): string {
  const parts = [`已写入 ${r.written} 条`]
  if (r.unchanged) parts.push(`${r.unchanged} 条与本项目相同未改`)
  for (const s of r.skipped) parts.push(`「${s.label}」${s.count} 条跳过：${s.reason}`)
  for (const f of r.failed) parts.push(`「${f.label}」${f.count} 条失败：${f.reason}`)
  return parts.join('；')
}
