/**
 * 导出单位口径纯函数
 *
 * 收敛「屏幕万元、导出元」口径漂移：底稿导出 Excel 时，数值必须按当前
 * `displayPrefs.unitDivisor` 口径还原，表头按 `displayPrefs.unitSuffix` 标注单位，
 * 使屏幕口径与导出口径一致（Req 1.6）。
 *
 * 本模块只提供纯函数，不依赖 store，便于属性测试（Property 5：可还原度量关系
 * `applyExportUnit(rawYuan, divisor) * divisor` 在浮点误差内等于 rawYuan）。
 *
 * ## 用法（供导入/导出 composable 复用）
 *
 * ```ts
 * import { useDisplayPrefsStore } from '@/stores/displayPrefs'
 * import { applyExportUnit, exportUnitHeaderNote } from '@/utils/exportUnit'
 *
 * const prefs = useDisplayPrefsStore()
 * // 数值：把原始「元」值换算到当前展示单位口径
 * const cellValue = applyExportUnit(rawYuan, prefs.unitDivisor)
 * // 表头：标注单位，如「金额（单位：万元）」
 * const header = `金额${exportUnitHeaderNote(prefs.unitSuffix)}`
 * ```
 *
 * 说明：全量导出路径改接本函数属后续任务（M1/迁移波次），此处仅沉淀单一真源纯函数。
 */

/**
 * 按单位除数把原始「元」值换算到展示单位口径。
 *
 * @param rawYuan 原始金额（以「元」为单位）
 * @param divisor 单位除数（元=1 / 千元=1000 / 万元=10000），来自 `displayPrefs.unitDivisor`
 * @returns 换算后的金额；divisor 为 0/假值时原样返回，避免除零
 */
export function applyExportUnit(rawYuan: number, divisor: number): number {
  return divisor ? rawYuan / divisor : rawYuan
}

/**
 * 生成表头单位标注文本，如 `（单位：万元）`。
 *
 * @param unitSuffix 单位后缀（元/千元/万元），来自 `displayPrefs.unitSuffix`
 * @returns 形如 `（单位：万元）` 的标注；unitSuffix 为空时返回空串
 */
export function exportUnitHeaderNote(unitSuffix: string): string {
  return unitSuffix ? `（单位：${unitSuffix}）` : ''
}
