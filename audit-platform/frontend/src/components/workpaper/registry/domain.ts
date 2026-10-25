/**
 * Registry 领域分类（逻辑视图）
 *
 * 按 componentType 前缀把条目归入逻辑域，供 GtWpRenderer / 测试 / 文档生成使用。
 *
 * 物理归属与逻辑域是两回事：
 * - **物理归属**由 registry/entries/*.ts 的显式数组决定（membership is the array
 *   itself），barrel 直接读显式数组，不做字符串前缀分类。
 * - **逻辑域**保留前缀分类，因为审计循环（A/B/C/D-F/G-I/J-N/S）与物理文件分组
 *   （core/forms/programs/confirmations/reports/specialized）不是一对一映射：
 *   forms.ts 同时装了 D 子模式和 D1~D7，programs.ts 同时装了 A/B 程序表和 G 组。
 *
 * 注意：本文件刻意不放在 index.ts 里。registryDomainSplit.spec.ts 断言 barrel
 * 源文本不得出现 classifyDomain / .startsWith( —— barrel 只装配，不分类。
 * barrel 通过 `export *` re-export 本模块，避免在 barrel 源中出现该字符串。
 */

/** 逻辑审计域 */
export type RegistryDomain =
  | 'core'
  | 'a-b'
  | 'c'
  | 'd-f'
  | 'g-i'
  | 'j-n'
  | 's'
  | 'confirmation'

/** 判断 componentType 所属逻辑域 */
export function classifyDomain(ct: string): RegistryDomain {
  if (ct.startsWith('confirmation-')) return 'confirmation'
  if (ct.startsWith('a') || ct.startsWith('b') || ct === 'e-control-test') return 'a-b'
  if (ct.startsWith('c')) return 'c'
  if (ct.startsWith('d') || ct.startsWith('f') || ct === 'e1-monetary-fund') return 'd-f'
  if (ct.startsWith('g') || ct.startsWith('h') || ct.startsWith('i')) return 'g-i'
  if (
    ct.startsWith('j') ||
    ct.startsWith('k') ||
    ct.startsWith('l') ||
    ct.startsWith('m') ||
    ct.startsWith('n')
  ) {
    return 'j-n'
  }
  if (ct.startsWith('s')) return 's'
  // 通用组件显式归属：它们不以任何审计循环前缀开头，不能靠兜底落进 core ——
  // 否则 PBT「任意 componentType 恰好属于一个领域」会要求 getEntriesByDomain('core')
  // 返回这 4 条，而 registryDomainSplit 要求它们在 programs/reports 里（否则各域重复），
  // 两个断言在 core 这一个同名键上互斥。按审计语义归入 a-b：
  // - procedure-table 程序表、review-checklist 复核面板 → A 类审计程序与复核
  // - report-analysis 报表分析 → A 类报表审定前置分析
  // - regulatory-letter = A18-2 监管沟通函 → A 类循环
  if (
    ct === 'procedure-table' ||
    ct === 'review-checklist' ||
    ct === 'report-analysis' ||
    ct === 'regulatory-letter'
  ) {
    return 'a-b'
  }
  return 'core'
}
