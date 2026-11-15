/**
 * 导出单位口径纯函数。
 *
 * `applyExportUnit` 和 `exportUnitHeaderNote` 只负责数学换算与文案生成，保留
 * 旧的显式参数 API 供已有测试和通用工具复用。正式 Excel/Word/PDF 导出必须
 * 使用下方的 `ExportUnitPolicy` 边界，单位由服务端按项目返回，浏览器不从个人
 * 显示设置推导正式产物口径。
 */

/** 正式导出单位标注。由服务端项目策略投影提供。 */
export type ExportUnitSuffix = '元' | '千元' | '万元'

/**
 * 服务端按项目计算的只读正式导出单位策略。
 *
 * `projectId` 用于证明策略所属项目；`divisor` 与 `unitSuffix` 必须来自同一份
 * 服务端策略，避免只替换其中一个字段造成“数值与标签不一致”。
 */
export interface ExportUnitPolicy {
  readonly projectId: string
  readonly divisor: number
  readonly unitSuffix: ExportUnitSuffix
}

/**
 * 按显式单位除数把原始「元」值换算到导出单位。
 *
 * @param rawYuan 原始金额（以「元」为单位）
 * @param divisor 单位除数（元=1 / 千元=1000 / 万元=10000）
 * @returns 换算后的金额；divisor 为 0/假值时原样返回，避免除零
 */
export function applyExportUnit(rawYuan: number, divisor: number): number {
  return divisor ? rawYuan / divisor : rawYuan
}

/**
 * 生成表头单位标注文本，如 `（单位：万元）`。
 *
 * @param unitSuffix 显式传入的单位后缀（元/千元/万元）
 * @returns 形如 `（单位：万元）` 的标注；unitSuffix 为空时返回空串
 */
export function exportUnitHeaderNote(unitSuffix: string): string {
  return unitSuffix ? `（单位：${unitSuffix}）` : ''
}

/**
 * 正式导出金额换算入口。
 *
 * 该命名入口只接受服务端按项目返回的策略，不接受任何用户界面状态对象。
 */
export function applyFormalExportUnit(rawYuan: number, policy: ExportUnitPolicy): number {
  return applyExportUnit(rawYuan, policy.divisor)
}

/** 正式导出表头单位标注入口，只接受服务端项目策略。 */
export function formalExportUnitHeaderNote(policy: ExportUnitPolicy): string {
  return exportUnitHeaderNote(policy.unitSuffix)
}
