import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

const SRC = resolve(__dirname, '../../../..')

const STRICT_FORM_DATA = [
  'components/workpaper/composables/useD4FormData.ts',
  'components/workpaper/composables/useF2FormData.ts',
  'components/workpaper/composables/useF2ValuationFormData.ts',
  'components/workpaper/composables/useF2SpecialFormData.ts',
  'components/workpaper/composables/useF2StocktakeFormData.ts',
  'components/workpaper/composables/useF3FormData.ts',
  'components/workpaper/composables/useF4FormData.ts',
  'components/workpaper/composables/useF5CosSalFormData.ts',
  'components/workpaper/composables/useG2IntRecFormData.ts',
  'components/workpaper/composables/useG4BonInvFormData.ts',
  // R1.3 收口：原 14 个 G 循环 LWW formData 全部迁 strict CAS。
  'components/workpaper/composables/useG10FormData.ts',
  'components/workpaper/composables/useG11FormData.ts',
  'components/workpaper/composables/useG12FormData.ts',
  'components/workpaper/composables/useG13FormData.ts',
  'components/workpaper/composables/useG14FormData.ts',
  'components/workpaper/composables/useG1TraFinFormData.ts',
  'components/workpaper/composables/useG3FormData.ts',
  'components/workpaper/composables/useG4EclFormData.ts',
  'components/workpaper/composables/useG5LonRecFormData.ts',
  'components/workpaper/composables/useG6MainFormData.ts',
  'components/workpaper/composables/useG6SppiFormData.ts',
  'components/workpaper/composables/useG8FormData.ts',
  'components/workpaper/composables/useG9FormData.ts',
  'composables/useG4SppiFormData.ts',
  'composables/workpaper/useChecklistPersistence.ts',
] as const

function source(relative: string): string {
  return readFileSync(resolve(SRC, relative), 'utf-8')
}

describe('双向宿主 checklist strict CAS 覆盖', () => {
  it.each(STRICT_FORM_DATA)('%s 通过单一 CAS helper 保存', (relative) => {
    const text = source(relative)
    expect(text, relative).toContain('createChecklistCasClient')
    expect(text, relative).not.toMatch(
      /(?:api|http)\.put\(`\/api\/workpapers\/\$\{[^}]+\}\/checklist-responses/,
    )
  })

  it('helper 固定 strict 请求且版本只从回执推进', () => {
    const text = source('composables/workpaper/checklistCas.ts')
    expect(text).toContain('require_if_match: true')
    expect(text).toContain('remember(result)')
    expect(text).not.toMatch(/Date\.now\(|new Date\(|randomUUID/)
  })
})


const G_STRICT_FORM_DATA = [
  'components/workpaper/composables/useG10FormData.ts',
  'components/workpaper/composables/useG11FormData.ts',
  'components/workpaper/composables/useG12FormData.ts',
  'components/workpaper/composables/useG13FormData.ts',
  'components/workpaper/composables/useG14FormData.ts',
  'components/workpaper/composables/useG1TraFinFormData.ts',
  'components/workpaper/composables/useG3FormData.ts',
  'components/workpaper/composables/useG4EclFormData.ts',
  'components/workpaper/composables/useG5LonRecFormData.ts',
  'components/workpaper/composables/useG6MainFormData.ts',
  'components/workpaper/composables/useG6SppiFormData.ts',
  'components/workpaper/composables/useG8FormData.ts',
  'components/workpaper/composables/useG9FormData.ts',
  'composables/useG4SppiFormData.ts',
] as const

const G_TRANSIENT_RETRY_FORM_DATA = [
  'components/workpaper/composables/useG8FormData.ts',
  'components/workpaper/composables/useG9FormData.ts',
  'components/workpaper/composables/useG10FormData.ts',
  'components/workpaper/composables/useG11FormData.ts',
  'components/workpaper/composables/useG12FormData.ts',
] as const

describe('G 循环 strict CAS 的故障耐久性', () => {
  it('14 家都在失败时保留可恢复草稿，不能只依赖页面生命周期内的 pending', () => {
    expect(G_STRICT_FORM_DATA).toHaveLength(14)
    const missing = G_STRICT_FORM_DATA.filter((relative) => {
      const text = source(relative)
      return !text.includes('restoreDrafts()')
        || !/onPending:\s*(?:drafts\.store|storeDrafts)/.test(text)
        || !/onSettled:\s*(?:drafts\.clear|clearDrafts)/.test(text)
        || !/onRecoveryRequired:/.test(text)
        || !text.includes('draft.requiresConfirmation === true')
        || !text.includes('queue.mark(itemId)')
        || !text.includes('queue.discard([itemId])')
        || !text.includes('queue.requiresRecoveryDecision(itemId)')
        || !text.includes('queue.resolveRecoveryDecision([itemId])')
        || !text.includes('confirmChecklistDraftConflict()')
    })
    expect(missing).toEqual([])
  })

  it('原有五家只对网络或 5xx 保留三次短退避，4xx 仍由队列冻结', () => {
    for (const relative of G_TRANSIENT_RETRY_FORM_DATA) {
      const text = source(relative)
      expect(text, relative).toContain('retry: { attempts: 3, initialDelayMs: 500 }')
      expect(text, relative).toContain('blockOnError: isNonRetryableChecklistSaveError')
    }
  })
})


it('G1 render-config 降级快照不能解除 strict-CAS 的 4xx 冻结', () => {
  const text = source('components/workpaper/composables/useG1TraFinFormData.ts')
  const start = text.indexOf('async function selfLoad()')
  const end = text.indexOf('async function loadAll()', start)
  expect(start).toBeGreaterThanOrEqual(0)
  expect(end).toBeGreaterThan(start)
  expect(text.slice(start, end)).not.toContain('queue.resetBlockedError()')
})


it('自定义草稿仓从后向前遍历，丢弃当前项不会跳过下一条待决草稿', () => {
  for (const relative of [
    'components/workpaper/composables/useG8FormData.ts',
    'components/workpaper/composables/useG9FormData.ts',
    'components/workpaper/composables/useG10FormData.ts',
    'components/workpaper/composables/useG11FormData.ts',
    'components/workpaper/composables/useG12FormData.ts',
  ]) {
    expect(source(relative), relative).toContain('for (let i = localStorage.length - 1; i >= 0; i -= 1)')
  }
})


it('14 家在 401/403 时都禁止恢复本地草稿', () => {
  const missing = G_STRICT_FORM_DATA.filter((relative) => {
    const text = source(relative)
    return !text.includes('isChecklistDraftAccessDenied(error)')
      || !text.includes('本地草稿未恢复')
  })
  expect(missing).toEqual([])
})

it('手写草稿仓也使用当前用户身份作为 key 维度，logout 清理走认证单一入口', () => {
  for (const relative of [
    'components/workpaper/composables/useG8FormData.ts',
    'components/workpaper/composables/useG9FormData.ts',
    'components/workpaper/composables/useG10FormData.ts',
    'components/workpaper/composables/useG11FormData.ts',
    'components/workpaper/composables/useG12FormData.ts',
  ]) {
    const text = source(relative)
    expect(text, relative).toContain('checklistDraftKey(DRAFT_PREFIX')
    expect(text, relative).toContain('checklistDraftPrefix(DRAFT_PREFIX')
  }
  const auth = source('stores/auth.ts')
  expect(auth.match(/clearChecklistDraftsOnLogout\(\)/g)).toHaveLength(2)
})


it('G7/H10 与两类监盘草稿同样按登录身份分区，不回读无身份 legacy 键', () => {
  for (const relative of [
    'components/workpaper/composables/useG7FormData.ts',
    'components/workpaper/composables/useG7SubFormData.ts',
    'components/workpaper/composables/useG7EquityMethodFormData.ts',
    'components/workpaper/composables/useH10FormData.ts',
  ]) {
    const text = source(relative)
    expect(text, relative).toContain('checklistDraftKey(DRAFT_PREFIX')
    expect(text, relative).toContain('checklistDraftPrefix(DRAFT_PREFIX')
    expect(text, relative).not.toContain('`${DRAFT_PREFIX}:${')
  }
  for (const relative of [
    'components/workpaper/InventoryStocktakeDialog.vue',
    'components/workpaper/FixedAssetStocktakeDialog.vue',
  ]) {
    const text = source(relative)
    expect(text, relative).toContain('userScopedWorkpaperDraftKey(')
    expect(text, relative).toContain('if (!key) return')
  }
  const storage = source('composables/workpaper/checklistDraftStorage.ts')
  for (const prefix of ['g7-main-draft:', 'g7-sub-draft:', 'g7-equity-method-draft:', 'h10-draft:', 'gt:stocktake-draft:', 'gt:h-stocktake-draft:']) {
    expect(storage).toContain(`'${prefix}'`)
  }
})