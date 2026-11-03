/**
 * 汇算申报表接口：取值 / 保存手工值（含表单「是否填报」）。
 * 值格式、结果结构与税审底稿接口一致（TaxSheetResult），表格组件直接复用。
 */
import { api } from '@/services/apiProxy'
import { taxAssurance as P_ta } from '@/services/apiPaths'
import type { TaxInputs, TaxSheetResult } from '@/views/tax-workpapers/taxWorkpaperApi'

export function fetchTaxReturnSheet(projectId: string, year: number, code: string): Promise<TaxSheetResult> {
  return api.get(P_ta.taxReturnSheet(projectId, code), { params: { year } }) as Promise<TaxSheetResult>
}

export function saveTaxReturnSheet(projectId: string, year: number, code: string, version: number, inputs: TaxInputs): Promise<TaxSheetResult> {
  return api.put(P_ta.taxReturnSheet(projectId, code), { version, inputs }, { params: { year }, _silent: true } as any) as Promise<TaxSheetResult>
}
