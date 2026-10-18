/**
 * crossCheckKeyConsistency.spec.ts — Task 6.2 / MEDIUM-2 表间审核 key 一致性单测
 *
 * 验收判据（tasks.md Task 6.2）：
 *   - 单元：构造树 key 与规则 map key **不一致**样本应判失败（MEDIUM-2）；
 *     反向断言一致样本通过。
 *
 * 🔴 设计要点：需求 7.4 要求「树的父/叶 key 与规则 map 的 key 一致」。本测试不直接
 * 挂载庞大的 FormulaManagerDialog.vue，而是测试其收敛后的**单一 key 生成函数**
 * `crossCheckNodeKey` / `CROSS_CHECK_NODE_KEYS`——树构建与 `crossCheckRulesMap`
 * 初始化在生产代码里都只经它产出。只要两侧都经同一函数，不一致在结构上即不可能。
 *   · 正向：用同一函数分别"模拟"树 key 与规则 map key，断言全等（一致样本通过）。
 *   · 变异反证：手工伪造一个绕开生成函数、直接写字符串的规则 map key（历史缺陷形态：
 *     把 `cross_report_note` 写成 `cross_rn`），断言一致性校验对该样本**判失败**。
 */
import { describe, it, expect } from 'vitest'
import {
  CROSS_CHECK_DOMAINS,
  CROSS_CHECK_NODE_KEYS,
  crossCheckNodeKey,
  type CrossCheckDomain,
} from '../crossCheckKey'

/**
 * 契约校验：给定一棵树（domain→父节点 key）与一张规则 map（domain→map key），
 * 当且仅当每个 domain 两侧 key 全等时返回 true。
 * 这就是「树父/叶 key 与规则 map key 一致」的可执行定义（需求 7.4）。
 */
function treeKeysMatchRuleMapKeys(
  treeKeys: Record<CrossCheckDomain, string>,
  ruleMapKeys: Record<string, string>,
): boolean {
  for (const domain of CROSS_CHECK_DOMAINS) {
    if (treeKeys[domain] !== ruleMapKeys[domain]) return false
  }
  return true
}

describe('crossCheckNodeKey — 单一 key 生成函数（MEDIUM-2 单一真源）', () => {
  it('每个 domain 产出稳定、与历史字面量逐字一致（零行为变化）', () => {
    expect(crossCheckNodeKey('report_note')).toBe('cross_report_note')
    expect(crossCheckNodeKey('report_wp')).toBe('cross_report_wp')
    expect(crossCheckNodeKey('note_wp')).toBe('cross_note_wp')
    expect(crossCheckNodeKey('consol')).toBe('cross_consol')
  })

  it('CROSS_CHECK_NODE_KEYS 索引与函数产出一致', () => {
    for (const domain of CROSS_CHECK_DOMAINS) {
      expect(CROSS_CHECK_NODE_KEYS[domain]).toBe(crossCheckNodeKey(domain))
    }
  })
})

describe('树 key ↔ 规则 map key 一致性（需求 7.4 / MEDIUM-2）', () => {
  it('反向断言：两侧都经 crossCheckNodeKey 生成 → 一致样本通过', () => {
    // 树父节点 key（生产 acnrDrivenTree 的 cross_check 分组用 crossCheckNodeKey）
    const treeKeys = {} as Record<CrossCheckDomain, string>
    for (const domain of CROSS_CHECK_DOMAINS) treeKeys[domain] = crossCheckNodeKey(domain)

    // 规则 map key（生产 crossCheckRulesMap 初始化用 CROSS_CHECK_NODE_KEYS）
    const ruleMapKeys: Record<string, string> = { ...CROSS_CHECK_NODE_KEYS }

    expect(treeKeysMatchRuleMapKeys(treeKeys, ruleMapKeys)).toBe(true)
  })

  it('变异反证：规则 map key 绕开生成函数、直接写字符串（历史缺陷形态）→ 判失败', () => {
    const treeKeys = {} as Record<CrossCheckDomain, string>
    for (const domain of CROSS_CHECK_DOMAINS) treeKeys[domain] = crossCheckNodeKey(domain)

    // 注入历史缺陷：report_note 的规则 map key 被改成 `cross_rn`（与树 key 偏移）。
    // 若生产代码里有人这么写，树点到 `cross_report_note` 却取不到规则集 → 右栏恒空。
    const driftedRuleMapKeys: Record<string, string> = {
      ...CROSS_CHECK_NODE_KEYS,
      report_note: 'cross_rn',
    }

    expect(treeKeysMatchRuleMapKeys(treeKeys, driftedRuleMapKeys)).toBe(false)
  })

  it('变异反证：任一 domain 两侧偏移都应被一致性校验捕获', () => {
    const treeKeys = {} as Record<CrossCheckDomain, string>
    for (const domain of CROSS_CHECK_DOMAINS) treeKeys[domain] = crossCheckNodeKey(domain)

    for (const drifted of CROSS_CHECK_DOMAINS) {
      const ruleMapKeys: Record<string, string> = { ...CROSS_CHECK_NODE_KEYS }
      ruleMapKeys[drifted] = `${ruleMapKeys[drifted]}_X`  // 偏移这一个 domain
      expect(treeKeysMatchRuleMapKeys(treeKeys, ruleMapKeys)).toBe(false)
    }
  })
})
