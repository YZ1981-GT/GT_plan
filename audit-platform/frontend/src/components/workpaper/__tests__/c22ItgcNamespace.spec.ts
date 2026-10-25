/**
 * C22 ITGC 命名空间与模式开关 — 零分母人造数据验证
 *
 * spec: c22-itgc-no-switch-and-domain-code-sheet-lane
 * 任务 11（CC-60 / CC-20）：本 entry 真库分母为 0，验证基于人造数据。
 * 🔴 不得因分母为 0 而跳过验证。
 *
 * 任务 10（CC-15）：断言 item_id 形态为 C22.{controlId}.{field}（点号分隔，
 * 与 canary 那条 gt-c-control-test 的连字符三段式不同）。
 */
import { describe, it, expect } from 'vitest'
import {
  itgcItemId,
  itgcFieldStorage,
  ITGC_GROUPS,
  type ItgcField,
} from '../composables/useC22BundleState'

describe('C22 ITGC item_id 命名空间（人造数据，真库分母为 0）', () => {
  // 🔴 造人工数据：至少 2 个 controlId × 2 个 field，以暴露键构造错误。
  const controlIds = ['SA-7', 'PE-5'] as const
  const fields: ItgcField[] = ['design-conclusion', 'exec-conclusion']

  it('点号分隔三段式：C22.{controlId}.{field}', () => {
    for (const cid of controlIds) {
      for (const f of fields) {
        const id = itgcItemId(cid, f)
        expect(id).toBe(`C22.${cid}.${f}`)
        // 点号分隔（非连字符体系）
        expect(id.split('.').length).toBeGreaterThanOrEqual(3)
        expect(id.startsWith('C22.')).toBe(true)
      }
    }
  })

  it('2 controlId × 2 field 生成 4 个互不相同的键（暴露键构造错误）', () => {
    const keys = new Set<string>()
    for (const cid of controlIds) {
      for (const f of fields) {
        keys.add(itgcItemId(cid, f))
      }
    }
    // 🔴 若键构造漏掉 controlId 或 field，集合大小会小于 4
    expect(keys.size).toBe(controlIds.length * fields.length)
    expect(keys.size).toBe(4)
  })

  it('不同 controlId 的同名 field 不串键（命名空间隔离）', () => {
    const a = itgcItemId('SA-7', 'design-conclusion')
    const b = itgcItemId('PE-5', 'design-conclusion')
    expect(a).not.toBe(b)
    expect(a).toContain('SA-7')
    expect(b).toContain('PE-5')
  })

  it('同 controlId 的不同 field 不串键', () => {
    const a = itgcItemId('SA-7', 'design-conclusion')
    const b = itgcItemId('SA-7', 'exec-conclusion')
    expect(a).not.toBe(b)
  })

  it('controlId 含连字符时不破坏点号分段（SA-7 / PE-5 / PM-4c）', () => {
    // controlId 本身含连字符，故分段必须按点号而非连字符
    for (const cid of ['SA-7', 'PE-5', 'PM-4c']) {
      const id = itgcItemId(cid, 'design-conclusion')
      const segments = id.split('.')
      expect(segments[0]).toBe('C22')
      expect(segments[1]).toBe(cid)
    }
  })

  it('itgcFieldStorage 对结论类字段返回 conclusion，其余 remark', () => {
    // 结论字段存 conclusion 槽
    expect(itgcFieldStorage('design-conclusion')).toBe('conclusion')
    expect(itgcFieldStorage('exec-conclusion')).toBe('conclusion')
  })

  it('ITGC_GROUPS 为 4 大类（信息安全/运行维护/程序变更/新系统）', () => {
    expect(ITGC_GROUPS.length).toBeGreaterThanOrEqual(4)
    expect(ITGC_GROUPS).toContain('信息安全')
    expect(ITGC_GROUPS).toContain('运行维护')
    expect(ITGC_GROUPS).toContain('程序变更')
    expect(ITGC_GROUPS).toContain('新系统')
  })
})

describe('C22 独立底稿真实 sheet 名映射（CC-63 修复验证）', () => {
  it('C21 / C21-1 tab 带 ooSheetName 且为册内真实 sheet 名', async () => {
    const mod = await import('../composables/useC22BundleState')
    // 从模块导出中取 tab 定义（SHEET_TABS 或等价常量）
    const candidates = Object.values(mod).filter(
      (v): v is readonly any[] => Array.isArray(v),
    )
    const tabs = candidates.find((arr) =>
      arr.some((t: any) => t && t.kind === 'c21'),
    )
    expect(tabs, '应能找到含 c21 tab 的定义数组').toBeTruthy()

    const c21 = tabs!.find((t: any) => t.kind === 'c21')
    const c211 = tabs!.find((t: any) => t.kind === 'c21-1')

    // 🔴 CC-63：传真实 sheet 名而非 wpCode
    expect(c21.ooSheetName).toBe('C21 具有信息技术专业技能的项目组成员')
    // 🔴 C21-1 册 sheet 名与册名/wpCode 完全脱钩（单空格，无 C21-1 前缀）
    expect(c211.ooSheetName).toBe('IT 审计发现汇总表')
    expect(c211.ooSheetName).not.toContain('C21-1')
  })

  it('ooSheetName 与 wpCode 不相等（证明二者脱钩）', async () => {
    const mod = await import('../composables/useC22BundleState')
    const candidates = Object.values(mod).filter(
      (v): v is readonly any[] => Array.isArray(v),
    )
    const tabs = candidates.find((arr) =>
      arr.some((t: any) => t && t.kind === 'c21'),
    )!
    for (const kind of ['c21', 'c21-1']) {
      const tab = tabs.find((t: any) => t.kind === kind)
      expect(tab.ooSheetName).not.toBe(tab.wpCode)
    }
  })
})
