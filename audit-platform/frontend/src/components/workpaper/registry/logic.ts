/**
 * 逻辑审计域的条目投影
 *
 * 物理归属（entries/*.ts 的显式数组）与逻辑审计域是两套视角：
 * - 物理文件按「渲染器家族」分组：forms.ts 同时装 D 子模式和 D1~D7；
 *   programs.ts 同时装 A/B 程序表和 G 组。
 * - 逻辑域按「审计循环」分组：a-b / c / d-f / g-i / j-n / s / confirmation / core。
 *
 * 本模块提供逻辑域 → 条目的投影，供 GtWpRenderer 按审计循环取数、
 * 以及 registrySplitEquivalence.pbt.spec.ts 断言「任意 componentType 恰好属于
 * 一个逻辑域」时使用。
 *
 * barrel（index.ts）只 re-export，不在此处重复实现前缀分类：
 * registryDomainSplit.spec.ts 断言 barrel 源不得出现 classifyDomain / startsWith。
 */
import type { HtmlRendererEntry } from './types'
import type { RegistryDomain as LogicalDomain } from './domain'
import { classifyDomain } from './domain'

/**
 * 按逻辑审计域取条目。
 * 每个 componentType 恰好落入一个逻辑域（classifyDomain 的分支互斥且穷尽），
 * 因此各逻辑域投影的并集等于全量注册表。
 */
export function entriesByLogicalDomain(
  domain: string,
  entries: readonly HtmlRendererEntry[],
): readonly HtmlRendererEntry[] {
  return entries.filter((e) => classifyDomain(e.componentType) === domain)
}
