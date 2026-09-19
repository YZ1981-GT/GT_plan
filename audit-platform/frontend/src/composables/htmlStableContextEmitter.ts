/**
 * HTML stable context emitter (guidance Task 11).
 *
 * All HTML activation paths (initial / deep-link / tab / navigate / locate /
 * section / wp reset) must publish through this single owner. Identity comes
 * from render-config sheet_uid/sheet_code — never from display-name regex or
 * array index. Fast switches bump contextRevision; wp ownership bumps ownerEpoch.
 * Formula runtime remains the CanonicalWorkpaperLocation owner; this module only
 * publishes stable host input + race stamps.
 */

import { buildHtmlSubjectKey } from './sheetUidProjection'
import type { WorkpaperSheetContext } from './useWpRenderer'

export { projectSheetUid, buildHtmlSubjectKey } from './sheetUidProjection'

export interface HtmlStableContextPublication {
  context: WorkpaperSheetContext
  ownerEpoch: number
  contextRevision: number
  /** Stable subject without transient revision — for cache / race identity. */
  subjectKey: string
}

/**
 * Single HTML publish owner. Create one per GtWpRenderer / editor session.
 */
export class HtmlStableContextEmitter {
  private ownerEpoch = 0
  private contextRevision = 0
  private ownerKey: string | null = null
  private lastSubject: string | null = null
  private lastPublication: HtmlStableContextPublication | null = null

  getOwnerEpoch(): number {
    return this.ownerEpoch
  }

  getContextRevision(): number {
    return this.contextRevision
  }

  /** wp reset / route enter — bumps ownerEpoch and clears last subject. */
  resetOwner(ownerKey: string): void {
    const next = ownerKey.trim()
    if (!next) return
    this.ownerEpoch += 1
    this.contextRevision = 0
    this.ownerKey = next
    this.lastSubject = null
    this.lastPublication = null
  }

  /**
   * Publish the latest HTML sheet context. Same subject keeps revision;
   * different subject bumps contextRevision. Null input clears publication.
   */
  publish(input: WorkpaperSheetContext | null): HtmlStableContextPublication | null {
    if (!input) {
      this.lastSubject = null
      this.lastPublication = null
      return null
    }
    if (this.ownerEpoch < 1) {
      this.resetOwner(`wp:${input.sheetCode || input.sheetName || 'pending'}`)
    }
    const subjectKey = buildHtmlSubjectKey(input)
    if (subjectKey === this.lastSubject && this.lastPublication) {
      return this.lastPublication
    }
    this.contextRevision += 1
    const context: WorkpaperSheetContext = {
      ...input,
      ownerEpoch: this.ownerEpoch,
      contextRevision: this.contextRevision,
    }
    const publication: HtmlStableContextPublication = {
      context,
      ownerEpoch: this.ownerEpoch,
      contextRevision: this.contextRevision,
      subjectKey,
    }
    this.lastSubject = subjectKey
    this.lastPublication = publication
    return publication
  }

  /** Race gate: only the latest ownerEpoch + contextRevision may land. */
  isCurrent(ownerEpoch: number, contextRevision: number): boolean {
    return ownerEpoch === this.ownerEpoch && contextRevision === this.contextRevision
  }
}

export function createHtmlStableContextEmitter(): HtmlStableContextEmitter {
  return new HtmlStableContextEmitter()
}
