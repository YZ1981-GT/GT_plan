/**
 * 底稿编辑器壳的能力快照（formula-toolbar Task 12 shell bridge；从 WorkpaperEditor.vue 抽出）。
 *
 * 底稿 / 项目 / 当前页签 / owner epoch 变化即重取；晚到的旧回执丢弃。取不到时一律按拒绝快照（fail-closed）。
 * 底稿本身打不开（403 / 404：无权 / 已删除 / 不存在）时编辑器已经给了一句中性提示，这里不再叠加
 * 「能力快照加载失败，请稍后重试」（spec procedure-chain-hardening-and-java-contracts R10）。
 */
import { ref, watch, type Ref } from 'vue'
import { fetchWorkpaperCapabilitySnapshot } from '@/shell/formula/fetchCapabilitySnapshot'
import { createShellStructuredError, type ShellStructuredError } from '@/shell/formula/shellStructuredError'
import type { CapabilityDecision, WorkpaperCapabilitySnapshot } from '@/shell/formula/workpaperCapabilitySnapshot'

export function denyCapabilitySnapshot(ownerEpoch: number, reasonCode = 'snapshot_uninitialized'): WorkpaperCapabilitySnapshot {
  const deny: CapabilityDecision = {
    allowed: false,
    reasonCode,
    owner: 'workpaper-capability-matrix',
    nextAction: '刷新后重试',
    zhMessage: '能力快照尚未就绪，请稍候。',
  }
  return {
    snapshotVersion: '1.0',
    subjectDigest: '',
    ownerEpoch,
    expiresAt: '1970-01-01T00:00:00Z',
    formulaView: deny,
    formulaEditUser: deny,
    formulaHistory: deny,
    aiReviewPage: deny,
    aiReviewBatch: deny,
    aiAssistChat: deny,
    humanReviewRead: deny,
    humanReviewWrite: deny,
    guidanceRead: deny,
  }
}

interface SheetContextLike {
  sheetUid?: string | null
  ownerEpoch?: number | null
  wholeWorkbook?: boolean
}

function statusOf(err: any): number | undefined {
  return err?.response?.status ?? err?.status
}

export function useShellCapability(opts: {
  wpId: Ref<string>
  projectId: Ref<string>
  activeSheetContext: Ref<SheetContextLike>
}) {
  const shellOwnerEpoch = ref(1)
  const shellCapabilityEpoch = ref(1)
  const shellError = ref<ShellStructuredError | null>(null)
  const shellCapabilitySnapshot = ref<WorkpaperCapabilitySnapshot>(denyCapabilitySnapshot(1))
  let requestSeq = 0

  async function refreshShellCapability(): Promise<void> {
    const request = ++requestSeq
    const ctx = opts.activeSheetContext
    const subject = {
      wpId: opts.wpId.value,
      projectId: opts.projectId.value,
      sheetUid: ctx.value.sheetUid,
      ownerEpoch: ctx.value.ownerEpoch ?? shellOwnerEpoch.value,
    }
    shellOwnerEpoch.value = subject.ownerEpoch
    shellCapabilityEpoch.value = subject.ownerEpoch
    shellCapabilitySnapshot.value = denyCapabilitySnapshot(subject.ownerEpoch, 'snapshot_loading')
    const stillCurrent = () => request === requestSeq
      && opts.wpId.value === subject.wpId
      && opts.projectId.value === subject.projectId
      && ctx.value.sheetUid === subject.sheetUid
      && (ctx.value.ownerEpoch ?? shellOwnerEpoch.value) === subject.ownerEpoch
    try {
      const snap = await fetchWorkpaperCapabilitySnapshot(subject)
      if (!stillCurrent()) return
      if (!snap || snap.ownerEpoch !== subject.ownerEpoch) {
        shellCapabilitySnapshot.value = denyCapabilitySnapshot(subject.ownerEpoch, 'snapshot_subject_mismatch')
        shellError.value = createShellStructuredError({
          domain: 'capability',
          reasonCode: 'snapshot_parse_failed',
          zhMessage: '能力快照不可用，公共操作已暂时阻断。',
          ownerEpoch: subject.ownerEpoch,
          capabilityEpoch: shellCapabilityEpoch.value,
        })
        return
      }
      shellCapabilitySnapshot.value = snap
      shellCapabilityEpoch.value = snap.ownerEpoch
      shellError.value = null
    } catch (err) {
      if (!stillCurrent()) return
      const status = statusOf(err)
      const unavailable = status === 403 || status === 404
      shellCapabilitySnapshot.value = denyCapabilitySnapshot(
        subject.ownerEpoch, unavailable ? 'workpaper_unavailable' : 'snapshot_fetch_failed')
      shellError.value = unavailable ? null : createShellStructuredError({
        domain: 'capability',
        reasonCode: 'snapshot_fetch_failed',
        zhMessage: '能力快照加载失败，请稍后重试。',
        ownerEpoch: subject.ownerEpoch,
        capabilityEpoch: shellCapabilityEpoch.value,
        operation: 'capability-snapshot',
      })
    }
  }

  watch(
    () => [opts.wpId.value, opts.projectId.value, shellOwnerEpoch.value,
      opts.activeSheetContext.value.sheetUid, opts.activeSheetContext.value.wholeWorkbook] as const,
    () => { void refreshShellCapability() },
    { immediate: true },
  )

  return { shellOwnerEpoch, shellCapabilityEpoch, shellError, shellCapabilitySnapshot, refreshShellCapability }
}
