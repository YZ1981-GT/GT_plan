/**
 * N 类循环（N1~N5）共用的 `tb_source_codes` 提取器。
 *
 * N 类各循环的科目口径散布在 `n2AccountScope.ts` 等，
 * 本文件只负责从 render-config 返回的 `htmlData` 中提取共用的 `tb_source_codes` 对象，
 * 供 provide/inject 注入给凭证检查子组件使用。
 *
 * spec: voucher-attach-account-mapping-closure（批次 6，任务 19）
 */
import type { TbSourceCodes } from './shared/tbSourceCodes'

/**
 * 从 htmlData 提取 `tb_source_codes`（与 D/E/F/G/H/I/J/K/M 循环同构）。
 *
 * 顶层 `htmlData.tb_source_codes` 优先；兼容 `htmlData.project_context.tb_source_codes`。
 * 两处都读、不做假设，返回 null 时调用方退到兜底码。
 */
export function pickNTbSourceCodes(htmlData: unknown): TbSourceCodes | null {
  if (!htmlData || typeof htmlData !== 'object') return null
  const hd = htmlData as Record<string, any>
  const fromTop = hd.tb_source_codes
  if (fromTop && typeof fromTop === 'object') return fromTop as TbSourceCodes
  const pc = hd.project_context
  if (pc && typeof pc === 'object') {
    const fromPc = (pc as Record<string, any>).tb_source_codes
    if (fromPc && typeof fromPc === 'object') return fromPc as TbSourceCodes
  }
  return null
}
