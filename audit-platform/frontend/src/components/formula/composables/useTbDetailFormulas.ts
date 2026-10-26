/**
 * 试算表科目明细公式（加载 / 拼行 / 保存）—— 从 FormulaManagerDialog 拆出。
 *
 * spec formula-global-settings-sync Phase 4 / R10：tb-detail 端点改存 formula_setting，
 * 响应带 layers / loaded / pending；保存后弹应用范围（changed_slot_keys）。
 */
import { ref, type Ref } from 'vue'
import { layerLabel } from '@/composables/formula/useFormulaSettings'

export interface TbDetailDeps {
  projectId: Ref<string>
  year: Ref<number | string | undefined>
  rows: Ref<any[] | undefined>
  addrStore: { loaded: boolean; tbAddresses: any[] }
  api: any
  reportConfigFormula: { tbDetail: (pid: string) => string }
  guardFormulaMutation: () => boolean
  showFormulaError: (e: any, fallback: string) => void
  askApplyScope: (domain: string, slotKeys: string[]) => void
}

export function useTbDetailFormulas(deps: TbDetailDeps) {
  const overrides = ref<Record<string, any>>({})
  const added = ref<any[]>([])
  const loaded = ref<Record<string, string>>({})
  const fallbackAccounts = ref<Array<{ code: string; name: string }>>([])

  async function load() {
    if (!deps.projectId.value) return
    try {
      const data: any = await deps.api.get(deps.reportConfigFormula.tbDetail(deps.projectId.value), {
        _silent: true, validateStatus: (s: number) => s < 600,
      } as any)
      overrides.value = data?.overrides || {}
      added.value = Array.isArray(data?.added) ? data.added : []
      loaded.value = data?.loaded || {}
    } catch { /* silent */ }
    if (!(deps.addrStore.loaded && deps.addrStore.tbAddresses.length > 0)
        && !(deps.rows.value && deps.rows.value.length > 0)
        && !fallbackAccounts.value.length) {
      try {
        const tbData: any = await deps.api.get(`/api/projects/${deps.projectId.value}/trial-balance`, {
          params: { year: deps.year.value },
          _silent: true, validateStatus: (s: number) => s < 600,
        } as any)
        const items = Array.isArray(tbData) ? tbData : (tbData?.items || tbData?.data || [])
        if (Array.isArray(items) && items.length) {
          fallbackAccounts.value = items.map((r: any) => ({
            code: r.standard_account_code || r.account_code || '',
            name: r.account_name || '',
          })).filter((r: { code: string }) => r.code)
        }
      } catch { /* silent fallback */ }
    }
  }

  async function persist(): Promise<boolean> {
    if (!deps.guardFormulaMutation()) return false
    if (!deps.projectId.value) return false
    try {
      const res: any = await deps.api.put(deps.reportConfigFormula.tbDetail(deps.projectId.value), {
        overrides: overrides.value, added: added.value, loaded: loaded.value,
      })
      loaded.value = res?.loaded || loaded.value
      deps.askApplyScope('tb_detail', res?.changed_slot_keys || [])
      return true
    } catch (e) {
      deps.showFormulaError(e, '保存失败')
      return false
    }
  }

  /** 拼出 currentRows 用的行数组（科目预设 + 用户覆盖 + 自定义新增，每行带层级标签）。 */
  function buildRows(base: Array<{ code: string; name: string; computed?: any }>): any[] {
    const ov = overrides.value
    const rows: any[] = base.map((b) => {
      const o = ov[b.code]
      return {
        id: `tbd-${b.code}`,
        row_code: b.code,
        row_name: b.name,
        formula: (o && o.formula != null) ? o.formula : `TB('${b.code}','期末余额')`,
        formula_category: (o && o.formula_category) ? o.formula_category : 'auto_calc',
        formula_description: (o && o.formula_description != null) ? o.formula_description : '从余额表取期末余额',
        _computed_value: b.computed,
        _tbDetail: true,
        _overridden: !!o,
        _layer: o?.layer, _layer_label: o ? layerLabel(o.layer) : '', _pending: !!o?.pending,
      }
    })
    for (let i = 0; i < added.value.length; i++) {
      const a = added.value[i]
      rows.push({
        id: a.row_code ? `tbd-add-${a.row_code}` : `tbd-add-${i}`,
        row_code: a.row_code || '',
        row_name: a.row_name || '',
        formula: a.formula || '',
        formula_category: a.formula_category || 'auto_calc',
        formula_description: a.formula_description || '',
        _computed_value: undefined,
        _tbDetail: true,
        _tbAdded: true,
        _layer: a.layer, _layer_label: layerLabel(a.layer), _pending: !!a.pending,
      })
    }
    return rows
  }

  return { overrides, added, loaded, fallbackAccounts, load, persist, buildRows }
}
