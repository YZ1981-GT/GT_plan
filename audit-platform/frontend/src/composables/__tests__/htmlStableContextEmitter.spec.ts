import { describe, expect, it } from 'vitest'
import {
  createHtmlStableContextEmitter,
  projectSheetUid,
  buildHtmlSubjectKey,
} from '../htmlStableContextEmitter'
import type { WorkpaperSheetContext } from '../useWpRenderer'

function ctx(partial: Partial<WorkpaperSheetContext> & Pick<WorkpaperSheetContext, 'sheetName'>): WorkpaperSheetContext {
  return {
    sheetCode: null,
    sheetUid: null,
    sheetUidNullReason: 'sheet_uid_unavailable',
    host: 'html',
    wholeWorkbook: false,
    ...partial,
  }
}

describe('projectSheetUid (G-ID)', () => {
  it('never invents uid from display name', () => {
    expect(projectSheetUid({
      parentWpCode: 'D0',
      sheetCode: null,
      sheetName: '询证函控制表',
      wholeWorkbook: false,
    })).toEqual({ sheetUid: null, nullReason: 'display_name_not_identity' })
  })

  it('projects deterministic uid from canonical code', () => {
    expect(projectSheetUid({
      parentWpCode: 'D0',
      sheetCode: 'D0-4b',
      sheetName: '询证函控制表D0-4b',
      wholeWorkbook: false,
    })).toEqual({ sheetUid: 'uid:D0:D0-4b', nullReason: null })
  })

  it('whole-workbook is honest null', () => {
    expect(projectSheetUid({
      parentWpCode: 'D0',
      sheetCode: 'D0-4b',
      sheetName: '__whole_excel__',
      wholeWorkbook: true,
    })).toEqual({ sheetUid: null, nullReason: 'whole_workbook' })
  })
})

describe('HtmlStableContextEmitter', () => {
  it('routes rapid switches so only last ownerEpoch/contextRevision is current', () => {
    const emitter = createHtmlStableContextEmitter()
    emitter.resetOwner('wp:1')
    const a = emitter.publish(ctx({ sheetName: 'A', sheetUid: 'uid:D0:A', sheetCode: 'A' }))
    const b = emitter.publish(ctx({ sheetName: 'B', sheetUid: 'uid:D0:B', sheetCode: 'B' }))
    const c = emitter.publish(ctx({ sheetName: 'C', sheetUid: 'uid:D0:C', sheetCode: 'C' }))
    expect(a?.contextRevision).toBe(1)
    expect(b?.contextRevision).toBe(2)
    expect(c?.contextRevision).toBe(3)
    expect(emitter.isCurrent(a!.ownerEpoch, a!.contextRevision)).toBe(false)
    expect(emitter.isCurrent(b!.ownerEpoch, b!.contextRevision)).toBe(false)
    expect(emitter.isCurrent(c!.ownerEpoch, c!.contextRevision)).toBe(true)
  })

  it('wp reset bumps ownerEpoch and clears prior subject', () => {
    const emitter = createHtmlStableContextEmitter()
    emitter.resetOwner('wp:old')
    const first = emitter.publish(ctx({ sheetName: 'S', sheetUid: 'uid:X:S', sheetCode: 'S' }))
    emitter.resetOwner('wp:new')
    const second = emitter.publish(ctx({ sheetName: 'S', sheetUid: 'uid:X:S', sheetCode: 'S' }))
    expect(second!.ownerEpoch).toBe((first!.ownerEpoch) + 1)
    expect(second!.contextRevision).toBe(1)
    expect(emitter.isCurrent(first!.ownerEpoch, first!.contextRevision)).toBe(false)
  })

  it('same subject does not bump revision', () => {
    const emitter = createHtmlStableContextEmitter()
    emitter.resetOwner('wp:1')
    const once = emitter.publish(ctx({ sheetName: 'A', sheetUid: 'uid:D0:A', sheetCode: 'A' }))
    const twice = emitter.publish(ctx({ sheetName: 'A', sheetUid: 'uid:D0:A', sheetCode: 'A' }))
    expect(twice?.contextRevision).toBe(once?.contextRevision)
    expect(buildHtmlSubjectKey(once!.context)).toBe('html|sheet:uid:D0:A')
  })
})
