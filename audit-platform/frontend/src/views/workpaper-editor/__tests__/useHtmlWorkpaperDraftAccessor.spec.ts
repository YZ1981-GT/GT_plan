/**
 * HTML 底稿路径的未保存草稿访问器（spec chat-host-draft-overlay / Task 4）。
 *
 * 判据取向：
 * * 「未保存状态不另建真源」—— 断言它读的就是 `readHtmlDraft`（共享持久化适配器登记的源），
 *   而不是某个新 dirty 标记；
 * * 「保存后 → null」—— 用同一访问器在源清空前后的两态证明；
 * * 「enabled=false 时如实回答没有」—— Univer 路径由 `UniverEditorCore` 自己登记，
 *   HTML 侧不能同时报告内容（否则同一 wpId 出现两个源）。
 */

import { effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import {
  clearHtmlDraftSources,
  clearWorkpaperDraftAccessors,
  hasWorkpaperDraftOverlay,
  publishHtmlDraftSource,
  readWorkpaperDraftOverlay,
} from '@/composables/workpaper/workpaperDraftOverlay'
import { useHtmlWorkpaperDraftAccessor } from '../useHtmlWorkpaperDraftAccessor'

const WP_ID = '11111111-1111-4111-8111-111111111111'
const BASELINE = '2026-11-15T10:00:00+00:00'

afterEach(() => {
  clearWorkpaperDraftAccessors()
  clearHtmlDraftSources()
})

/** 模拟一个 sheet 宿主：`dirty` 翻转即「改了没保存」/「已保存」。 */
function mountSheetSource(wpId = WP_ID) {
  const dirty = ref(false)
  const content = ref('')
  publishHtmlDraftSource(wpId, {
    label: 'stub-sheet',
    hasUnsaved: () => dirty.value,
    currentDraftContent: () => (dirty.value ? content.value : null),
  })
  return { dirty, content }
}

function mountAccessor(options: Partial<Parameters<typeof useHtmlWorkpaperDraftAccessor>[0]> = {}) {
  const scope = effectScope()
  scope.run(() => {
    useHtmlWorkpaperDraftAccessor({
      wpId: () => WP_ID,
      currentBusinessVersion: () => BASELINE,
      enabled: () => true,
      ...options,
    })
  })
  return scope
}

describe('useHtmlWorkpaperDraftAccessor — 改一处不保存 → 有值；保存后 → null', () => {
  it('两态：宿主有 pending → 有草稿；落库清空 pending → null', async () => {
    const sheet = mountSheetSource()
    const scope = mountAccessor()

    // 打开时干净：没有未保存修改
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()

    // 改一处不保存
    sheet.content.value = '{"item_id":"K1-1","remark":"1200000"}'
    sheet.dirty.value = true
    await nextTick()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(true)
    const overlay = readWorkpaperDraftOverlay(WP_ID)
    expect(overlay).not.toBeNull()
    expect(overlay!.content).toBe('{"item_id":"K1-1","remark":"1200000"}')
    expect(overlay!.baselineVersion).toBe(BASELINE)
    expect(overlay!.contentLength).toBe(overlay!.content.length)

    // 保存成功：pending 清空
    sheet.dirty.value = false
    sheet.content.value = ''
    await nextTick()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
    scope.stop()
  })

  it('基线版本取 wpDetail.updated_at 并冻结（保存后详情刷新不影响基线）', async () => {
    const sheet = mountSheetSource()
    const version = ref<unknown>(BASELINE)
    const scope = mountAccessor({ currentBusinessVersion: () => version.value })

    sheet.dirty.value = true
    sheet.content.value = '未保存正文'
    await nextTick()
    expect(readWorkpaperDraftOverlay(WP_ID)?.baselineVersion).toBe(BASELINE)

    // 保存后 wpDetail 重取 ⇒ updated_at 前进
    version.value = '2026-11-15T12:00:00+00:00'
    await nextTick()
    expect(readWorkpaperDraftOverlay(WP_ID)?.baselineVersion).toBe(BASELINE)
    scope.stop()
  })

  it('enabled=false（走 Univer 路径）时如实回答没有未保存修改', async () => {
    const sheet = mountSheetSource()
    const enabled = ref(false)
    const scope = mountAccessor({ enabled: () => enabled.value })

    sheet.dirty.value = true
    sheet.content.value = 'HTML 侧的正文'
    await nextTick()
    // HTML 路径关闭 ⇒ 不报告（Univer 路径由 UniverEditorCore 自己登记）
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()

    enabled.value = true
    await nextTick()
    expect(readWorkpaperDraftOverlay(WP_ID)?.content).toBe('HTML 侧的正文')
    scope.stop()
  })

  it('详情还没到时基线为空 ⇒ 不给 overlay；拿到真值后才给', async () => {
    const sheet = mountSheetSource()
    const version = ref<unknown>(null)
    const scope = mountAccessor({ currentBusinessVersion: () => version.value })
    sheet.dirty.value = true
    sheet.content.value = '未保存正文'
    await nextTick()
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()

    version.value = BASELINE
    await nextTick()
    expect(readWorkpaperDraftOverlay(WP_ID)?.baselineVersion).toBe(BASELINE)
    scope.stop()
  })

  it('scope 停止后不再报告（离页不留悬挂访问器）', async () => {
    const sheet = mountSheetSource()
    const scope = mountAccessor()
    sheet.dirty.value = true
    sheet.content.value = '未保存正文'
    await nextTick()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(true)
    scope.stop()
    expect(hasWorkpaperDraftOverlay(WP_ID)).toBe(false)
    expect(readWorkpaperDraftOverlay(WP_ID)).toBeNull()
  })
})
