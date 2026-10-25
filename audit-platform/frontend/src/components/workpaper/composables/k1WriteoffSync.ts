import type { Ref } from 'vue'
import { api } from '@/services/apiProxy'
import { readStoreProjection } from '../sync/workpaperSyncApi'
import { useD4SyncMode } from '../d4/composables/useD4SyncMode'

const ENTRY_ID = 'xlsx/gt-k1-other-receivables'
const SHEET_KEY = 'k109-managed'
const ITEM_ID = 'K1-9-writeoff'

export interface UseK1WriteoffSyncOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  isReadonly: Ref<boolean>
  snapshotRemark: () => string
  onReloaded: (minimumRevision: number) => Promise<void>
}

/** K1-9 dict store 的真双向接桥；派生 total 键不进入受管 projection。 */
export function useK1WriteoffSync(options: UseK1WriteoffSyncOptions) {
  return useD4SyncMode({
    entryId: ENTRY_ID,
    sheetKey: SHEET_KEY,
    wpId: options.wpId,
    projectId: options.projectId,
    isReadonly: options.isReadonly,
    views: ['结构化视图'],
    flushHtml: async () => {
      await api.put(`/api/workpapers/${options.wpId.value}/checklist-responses`, {
        project_id: options.projectId.value,
        items: [{ item_id: ITEM_ID, conclusion: null, remark: options.snapshotRemark() }],
      })
      const snap = await readStoreProjection({
        projectId: options.projectId.value,
        wpId: options.wpId.value,
        entryId: ENTRY_ID,
      })
      return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: SHEET_KEY }
    },
    reloadHtml: options.onReloaded,
  })
}

export const K1_ONLINE_EDIT_LABEL = '在线编辑'
