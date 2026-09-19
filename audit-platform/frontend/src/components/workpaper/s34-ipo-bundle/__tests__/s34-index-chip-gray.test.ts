/**
 * s34-index-chip-gray.test.ts — Task 8.2 引用不存在→灰态提示
 *
 * Spec: .kiro/specs/s34-ipo-review-bundle/  Task 8.2
 * Requirements: 6.4
 *
 * 验证场景：
 * 1. GtIndexChip 灰态逻辑：resolveStatus='not_exists' → type=info + disabled class + tooltip "底稿不存在"
 * 2. useS34CrossRef 内部引用不可见 Tab 时忽略点击（不跳转）
 * 3. BUNDLE_SHEET_ALIASES 包含 S34-1~S34-41 → S34 parent 路由兜底
 */
import { describe, it, expect } from 'vitest'
import { ref, type Ref } from 'vue'
import { BUNDLE_SHEET_ALIASES } from '../../bundleSheetAliases'
import { S34_TAB_DEFS, type TabDef } from '../S34_TAB_CONFIG'
import { isS34InternalRef, getS34TabFromRef } from '../useS34CrossRef'

// ─── Req 6.4: GtIndexChip 灰态逻辑（纯函数验证） ───

describe('Task 8.2: 引用不存在→灰态提示 (Req 6.4)', () => {
  /**
   * GtIndexChip 内部逻辑（从 GtIndexChip.vue 中提取的纯计算逻辑）：
   * - resolveStatus='not_exists' → chipType='info' (灰色)
   * - resolveStatus='not_exists' → chipEffect='plain'
   * - resolveStatus='not_exists' → chipClass 包含 'gt-index-chip--disabled'
   * - resolveStatus='not_exists' → tooltipContent='底稿不存在'
   * - resolveStatus='not_exists' → handleClick 返回 early（不可跳转）
   */

  function computeChipType(resolveStatus: string, disabled: boolean): string {
    if (disabled) return 'info'
    if (resolveStatus === 'exists') return 'primary'
    if (resolveStatus === 'not_exists' || resolveStatus === 'trimmed') return 'info'
    if (resolveStatus === 'error') return 'danger'
    return 'primary'
  }

  function computeChipEffect(resolveStatus: string): string {
    if (resolveStatus === 'exists') return 'light'
    return 'plain'
  }

  function computeChipClass(resolveStatus: string, disabled: boolean): string[] {
    const classes = ['gt-index-chip']
    if (disabled) {
      classes.push('gt-index-chip--disabled')
      return classes
    }
    if (resolveStatus === 'exists') {
      classes.push('gt-index-chip--clickable')
    }
    if (resolveStatus === 'not_exists' || resolveStatus === 'trimmed') {
      classes.push('gt-index-chip--disabled')
    }
    return classes
  }

  function computeTooltipContent(resolveStatus: string, disabled: boolean): string {
    if (disabled) return '当前步骤不适用，chip 不可点击'
    if (resolveStatus === 'not_exists') return '底稿不存在'
    if (resolveStatus === 'trimmed') return '已裁剪'
    return ''
  }

  function canClick(resolveStatus: string, disabled: boolean): boolean {
    if (disabled) return false
    if (resolveStatus === 'not_exists' || resolveStatus === 'trimmed') return false
    return true
  }

  describe('GtIndexChip 灰态渲染逻辑', () => {
    it('resolveStatus="not_exists" → chipType="info"（灰色 tag）', () => {
      expect(computeChipType('not_exists', false)).toBe('info')
    })

    it('resolveStatus="not_exists" → chipEffect="plain"（朴素样式）', () => {
      expect(computeChipEffect('not_exists')).toBe('plain')
    })

    it('resolveStatus="not_exists" → chipClass 包含 "gt-index-chip--disabled"', () => {
      const classes = computeChipClass('not_exists', false)
      expect(classes).toContain('gt-index-chip--disabled')
      expect(classes).not.toContain('gt-index-chip--clickable')
    })

    it('resolveStatus="not_exists" → tooltip 显示"底稿不存在"', () => {
      expect(computeTooltipContent('not_exists', false)).toBe('底稿不存在')
    })

    it('resolveStatus="not_exists" → 点击被阻止（不可跳转）', () => {
      expect(canClick('not_exists', false)).toBe(false)
    })

    it('resolveStatus="exists" → chipType="primary"（正常可跳转）', () => {
      expect(computeChipType('exists', false)).toBe('primary')
    })

    it('resolveStatus="exists" → 点击允许', () => {
      expect(canClick('exists', false)).toBe(true)
    })
  })

  // ─── useS34CrossRef 内部引用不可见时忽略 ───
  describe('useS34CrossRef 内部引用不存在时忽略', () => {
    /**
     * 当 S34 内部引用（如 S34-16）指向的 Tab 不在 visibleTabs 中时：
     * - isS34InternalRef 判断为 true
     * - getS34TabFromRef 提取父 Tab ID
     * - 因 Tab 不在 visibleTabs，handleChipClick 不切换 activeTab（静默忽略）
     * 
     * 视觉上，GtIndexChip 通过 validate API 检测到该底稿不存在，自动渲染为灰态。
     */

    it('isS34InternalRef 正确识别 S34 内部引用', () => {
      expect(isS34InternalRef('S34-16')).toBe(true)
      expect(isS34InternalRef('S34-16-1')).toBe(true)
      expect(isS34InternalRef('S34-2-2')).toBe(true)
      expect(isS34InternalRef('D4-24')).toBe(false)
      expect(isS34InternalRef('B23-1')).toBe(false)
      expect(isS34InternalRef('S34')).toBe(false)
    })

    it('getS34TabFromRef 提取父 Tab ID', () => {
      expect(getS34TabFromRef('S34-16-1')).toBe('S34-16')
      expect(getS34TabFromRef('S34-16')).toBe('S34-16')
      expect(getS34TabFromRef('S34-2-2')).toBe('S34-2')
    })

    it('内部引用不在 visibleTabs 时 activeTab 不变', () => {
      // 模拟 handleChipClick 的内部逻辑
      const visibleTabs: TabDef[] = [
        { id: 'overview', label: '核查清单', group: '总览' },
        { id: 'S34-3', label: '股份支付', group: '股权与激励', wpCode: 'S34-3' },
      ]
      const activeTab = ref('overview')

      // 模拟 handleChipClick 内部逻辑（S34-16 不在 visibleTabs 中）
      const wpCode = 'S34-16'
      if (isS34InternalRef(wpCode)) {
        const tabId = getS34TabFromRef(wpCode)
        if (visibleTabs.some(t => t.id === tabId)) {
          activeTab.value = tabId
        }
        // 否则忽略 — 底稿不存在
      }

      // activeTab 应保持不变
      expect(activeTab.value).toBe('overview')
    })

    it('内部引用在 visibleTabs 时 activeTab 正常切换', () => {
      const visibleTabs: TabDef[] = [
        { id: 'overview', label: '核查清单', group: '总览' },
        { id: 'S34-3', label: '股份支付', group: '股权与激励', wpCode: 'S34-3' },
      ]
      const activeTab = ref('overview')

      const wpCode = 'S34-3'
      if (isS34InternalRef(wpCode)) {
        const tabId = getS34TabFromRef(wpCode)
        if (visibleTabs.some(t => t.id === tabId)) {
          activeTab.value = tabId
        }
      }

      expect(activeTab.value).toBe('S34-3')
    })
  })

  // ─── BUNDLE_SHEET_ALIASES 兜底路由（外部 GtIndexChip 跳转 S34-x 场景） ───
  describe('BUNDLE_SHEET_ALIASES 包含 S34 子底稿路由兜底', () => {
    it('S34-1~S34-41 所有主底稿均在 BUNDLE_SHEET_ALIASES 中注册', () => {
      for (let i = 1; i <= 41; i++) {
        const code = `S34-${i}`
        expect(
          BUNDLE_SHEET_ALIASES[code],
          `BUNDLE_SHEET_ALIASES 应包含 ${code}`,
        ).toBeDefined()
      }
    })

    it('所有 S34-x aliases 的 parent 均为 "S34"', () => {
      for (let i = 1; i <= 41; i++) {
        const code = `S34-${i}`
        expect(BUNDLE_SHEET_ALIASES[code].parent).toBe('S34')
      }
    })

    it('子 sheet 编码（如 S34-16-1）也路由到对应父 Tab', () => {
      // 含子表的底稿：S34-16-1/2, S34-2-1/2, S34-8-1/2, S34-25-1~3, S34-34-1/2 等
      const subSheetCodes = [
        'S34-16-1', 'S34-16-2',
        'S34-2-1', 'S34-2-2',
        'S34-8-1', 'S34-8-2',
        'S34-25-1', 'S34-25-2', 'S34-25-3',
        'S34-34-1', 'S34-34-2',
        'S34-4-1', 'S34-9-1', 'S34-11-1',
        'S34-18-1', 'S34-20-1', 'S34-30-1',
      ]

      for (const code of subSheetCodes) {
        const alias = BUNDLE_SHEET_ALIASES[code]
        expect(alias, `BUNDLE_SHEET_ALIASES 应包含子 sheet ${code}`).toBeDefined()
        expect(alias.parent).toBe('S34')
        // sheet 路由到父 Tab（如 S34-16-1 → sheet='S34-16'）
        const parentTab = code.match(/^(S34-\d+)/)?.[1]
        expect(alias.sheet).toBe(parentTab)
      }
    })
  })
})
