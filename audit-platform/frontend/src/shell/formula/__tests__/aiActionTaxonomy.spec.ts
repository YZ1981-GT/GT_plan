/**
 * Formula-toolbar Task 9 — AI action taxonomy.
 */

import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import {
  AI_ACTION_DESCRIPTORS,
  AI_REVIEW_BUSINESS_DUPLICATE_PATTERNS,
  assertAiAssistCarrier,
  assertAiReviewScope,
  assertTaxonomyA11yUnique,
  descriptorFor,
} from '@/shell/formula/aiActionTaxonomy'

describe('Task 9: AI action taxonomy', () => {
  it('keeps five mutually exclusive families with unique a11y names', () => {
    expect(AI_ACTION_DESCRIPTORS).toHaveLength(5)
    expect(() => assertTaxonomyA11yUnique()).not.toThrow()
    expect(descriptorFor('ai_review_page').carrier).toBe('ai-review-toolbar')
    expect(descriptorFor('ai_assist_chat').carrier).toBe('dsh-assist')
    expect(descriptorFor('human_review_thread').action).not.toBe('ai_review_page')
  })

  it('binds page/batch review to ready location + capability epoch', () => {
    const ok = assertAiReviewScope({
      action: 'ai_review_page',
      locationReady: true,
      subjectKey: 'org|p|wp|html|page',
      ownerEpoch: 2,
      contextRevision: 1,
      capabilityEpoch: 2,
      capabilityAllowed: true,
    })
    expect(ok.ok).toBe(true)

    const denied = assertAiReviewScope({
      action: 'ai_review_batch',
      locationReady: true,
      subjectKey: 'x',
      ownerEpoch: 1,
      contextRevision: 1,
      capabilityEpoch: 1,
      capabilityAllowed: false,
    })
    expect(denied.ok).toBe(false)
  })

  it('assist must use DSH carrier and must not borrow review permission', () => {
    expect(
      assertAiAssistCarrier({
        requestedCarrier: 'dsh-assist',
        usingAiReviewPermission: false,
      }).ok,
    ).toBe(true)
    expect(
      assertAiAssistCarrier({
        requestedCarrier: 'ai-review-toolbar',
        usingAiReviewPermission: false,
      }).ok,
    ).toBe(false)
    expect(
      assertAiAssistCarrier({
        requestedCarrier: 'dsh-assist',
        usingAiReviewPermission: true,
      }).ok,
    ).toBe(false)
  })

  it('GtWpAiReviewToolbar uses taxonomy actions; D2 no longer mounts local AI buttons', () => {
    const toolbar = readFileSync(
      join(__dirname, '../../../components/workpaper/review/GtWpAiReviewToolbar.vue'),
      'utf8',
    )
    expect(toolbar).toContain('data-ai-action="ai_review_page"')
    expect(toolbar).toContain('data-ai-action="ai_review_batch"')
    expect(toolbar).toContain("descriptorFor('ai_review_page')")

    const d2 = readFileSync(
      join(__dirname, '../../../components/workpaper/GtD2AccountsReceivable.vue'),
      'utf8',
    )
    expect(d2).not.toContain('GtWpAiReviewToolbar')
    expect(d2).not.toMatch(/@click="onCurrentSheetAiReview"/)
    expect(d2).not.toMatch(/本页AI复核/)
    for (const p of AI_REVIEW_BUSINESS_DUPLICATE_PATTERNS) {
      expect(p.relativePath).toContain('GtD2AccountsReceivable')
    }
  })
})
