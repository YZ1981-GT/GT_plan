/**
 * D2 披露页小节标题守卫。
 *
 * 背景（2026-08-01 Wave 3.1 复核）：D1 曾出现「披露页 `sectionLabels` 独立映射
 * 与表名常量 `D1_TABLE_NAMES` 各写一份、彼此漂移」的缺陷（7 条里 5 条措辞不一致，
 * 上市主表还与质押表撞编号）。D2 复核确认**不存在同款问题**——`D2DisclosureNoteBody.vue`
 * 的卡片标题直接引用 `D2_TABLE_NAMES` 常量渲染（`{{ T.classEnd }}` 等），没有第二份
 * 独立的标题字符串，天然不可能漂移。
 *
 * 本守卫钉死这个架构优点：①国企侧编号唯一 ②披露页不得新增独立于 `D2_TABLE_NAMES`
 * 的标题字面量（防止未来重构引入第二套真源）。
 *
 * spec: .kiro/specs/d-cycle-extraction-chain-completion/ Task 3.1
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { D2_TABLE_NAMES } from '../d2NoteSectionMap'

const BODY = resolve(__dirname, '../../d2/D2DisclosureNoteBody.vue')

describe('D2 披露页小节标题 ↔ D2_TABLE_NAMES 单一真源', () => {
  it('国企侧编号（N）唯一不重复', () => {
    const nums = Object.values(D2_TABLE_NAMES.soe)
      .map((v) => String(v).match(/^（(\d+)）/)?.[1])
      .filter((v): v is string => Boolean(v))
    expect(nums.length).toBeGreaterThan(0)
    expect(nums.length).toBe(new Set(nums).size)
  })

  it('上市侧表名不带编号（源模板主表本就无编号，避免与其它表撞号）', () => {
    for (const v of Object.values(D2_TABLE_NAMES.listed)) {
      expect(String(v)).not.toMatch(/^（\d+）/)
    }
  })

  it('披露页卡片标题（card-title）全部来自 T.xxx / D2_TABLE_NAMES.xxx 表达式，非独立字面量', () => {
    const src = readFileSync(BODY, 'utf-8')
    const titleBlocks = [...src.matchAll(/<span class="card-title">([\s\S]*?)<\/span>/g)].map((m) => m[1])
    expect(titleBlocks.length).toBeGreaterThan(0)
    // 动态组合分表（每个组合一张、名字随审计师命名，不在 D2_TABLE_NAMES 固定表名里）
    // 用通用描述做卡片标题，是合理例外，非漂移。
    const DYNAMIC_PORTFOLIO_TITLE = '组合计提项目（每个组合一张分表）'
    for (const block of titleBlocks) {
      if (block.includes(DYNAMIC_PORTFOLIO_TITLE)) continue
      // 卡片标题表达式必须引用 T.xxx 或 D2_TABLE_NAMES.xxx（含三元表达式），
      // 不得是不引用这两者的裸中文字面量（防止悄悄加一份独立标题映射）
      const referencesTableNames = /\bT\.\w+|\bD2_TABLE_NAMES\.\w+\.\w+/.test(block)
      expect(referencesTableNames, `card-title 未引用 D2_TABLE_NAMES：${block.slice(0, 80)}`).toBe(true)
    }
  })

  it('反向自检：卡片标题正则确实能命中真实内容（非空转）', () => {
    const src = readFileSync(BODY, 'utf-8')
    const hits = [...src.matchAll(/<span class="card-title">([\s\S]*?)<\/span>/g)]
    expect(hits.length).toBeGreaterThanOrEqual(5)
  })
})
