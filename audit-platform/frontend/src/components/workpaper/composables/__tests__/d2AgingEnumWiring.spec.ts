/**
 * D2 账龄枚举贯通守卫（Requirement 6.3/6.4，Property 11）。
 *
 * 背景（2026-08-01 Wave 3.2 复核）：D2 已由并发会话（2026-07-26）完整接通项目账龄
 * 枚举（3 年段 / 5 年段 / 自定义），链路分两层：
 *   ① 底稿内部数据结构：`useD2DisclosureNote` 用 `useAgingConfig(projectId,'D2')`
 *      驱动 `agingSegments`/`agingRows`/组合计提分表行，未加载时回退 5 年段预设
 *      （与 `useAgingConfig._applyDefault` 对 D2 的默认一致，避免首帧段数跳变）。
 *   ② 推送附注时的标签口径：`d2NoteSectionMap.buildD2SyncPayload` 用
 *      `disclosureAgingLabels.toDisclosureAgingLabel` 转换（上市「1年以内」/
 *      国企「1年以内（含1年）」，`D2_AGING_LABEL_OVERRIDES` 单一真源）。
 * 本守卫锁死这两层不退化（防止未来改动重新硬编码账龄档位）。
 *
 * spec: .kiro/specs/d-cycle-extraction-chain-completion/ Task 3.2
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const NOTE_COMPOSABLE = resolve(__dirname, '../useD2DisclosureNote.ts')
const SECTION_MAP = resolve(__dirname, '../d2NoteSectionMap.ts')

describe('D2 账龄枚举 ↔ 项目配置单一真源', () => {
  it('useD2DisclosureNote 使用 useAgingConfig（不得硬编码档位清单）', () => {
    const src = readFileSync(NOTE_COMPOSABLE, 'utf-8')
    expect(src).toContain("useAgingConfig(projectId, 'D2')")
    // 反向自检：文件确实含账龄相关内容（防止误读空文件）
    expect(src).toContain('agingSegments')
  })

  it('未加载完成时的回退预设必须是 useAgingConfig 提供的 PRESET_SEGMENTS，非自造清单', () => {
    const src = readFileSync(NOTE_COMPOSABLE, 'utf-8')
    expect(src).toMatch(/PRESET_SEGMENTS\.FIVE_YEAR/)
    // 不得出现自造的硬编码账龄标签数组（如平台曾踩坑的 '一年以内'/'1年以内（含1年）' 字面清单）
    expect(src).not.toMatch(/const\s+\w*AGING\w*\s*=\s*\[\s*['"]/i)
  })

  it('组合计提分表行随账龄配置变化自动补齐（watch agingSegments）', () => {
    const src = readFileSync(NOTE_COMPOSABLE, 'utf-8')
    expect(src).toMatch(/watch\(agingSegments/)
  })

  it('推送附注时的标签口径经 disclosureAgingLabels 单一真源转换，不写死字面量', () => {
    const src = readFileSync(SECTION_MAP, 'utf-8')
    expect(src).toContain('toDisclosureAgingLabel')
    expect(src).toContain('SOE_AGING_OVERRIDES')
    expect(src).toMatch(/D2_AGING_LABEL_OVERRIDES/)
  })

  it('反向自检：正则确实能在真实源码上命中（防空转）', () => {
    const src = readFileSync(NOTE_COMPOSABLE, 'utf-8')
    expect(src.length).toBeGreaterThan(1000)
    expect(src).not.toMatch(/^\s*$/)
  })
})
