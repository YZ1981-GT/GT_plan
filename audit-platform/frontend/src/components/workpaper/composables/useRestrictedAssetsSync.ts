/**
 * 受限资产段推送 —— **各 owner 循环共用的一行接线件**。
 *
 * 把「读 `checklist_responses` → 归纳成段内一行 → 带 `_row_scope` 推送 →
 * fail closed 提示 → 广播刷新」这一整套收敛到一处，各披露 Tab 只需：
 *
 * ```ts
 * const syncRestrictedAssets = useRestrictedAssetsSync({
 *   owner: 'BS-028',
 *   variant: () => 'listed',
 *   wpId: () => props.wpId,
 *   projectId: () => props.projectId,
 *   responses: () => props.allResponses,
 *   applicableStandards: () => hostApplicableStandards.value,
 *   sheetNames: H1_DISCLOSURE_SHEET_NAME,
 * })
 * ```
 *
 * 🔴 采集逻辑**不在这里**，在声明表 `restrictedAssetsSources.ts`（纯函数、可单测）。
 * 本文件只负责编排与网络，保证 4 个 owner 的行为逐字一致。
 *
 * 🔴 `useRestrictedAssetsSync` 必须在 **setup 作用域**调用（返回的函数可在任意
 * 时机调用）—— 与平台既有铁律一致：setup 作用域 composable 写进函数体会静默失效。
 * 本文件不 inject 任何东西，故实际无此约束，但保持同款用法以免后续踩坑。
 *
 * spec: .kiro/specs/restricted-assets-note-row-scope-rollout/ Requirement 3
 */
import { ElMessage } from 'element-plus'

import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

// fail closed 提示文案单一真源（含**为什么**，不只是哪张表）
import { rowScopeFailureMessage } from './shared/rowScopeFailure'

import {
  buildRestrictedAssetsPayloads,
  RESTRICTED_ASSETS_NOTE_SECTION,
  RESTRICTED_ASSETS_OWNERS,
  summarizeRestrictedRows,
  type RestrictedAssetsOwner,
  type RestrictedAssetsSheetNames,
  type RestrictedAssetsVariant,
} from './restrictedAssetsNoteSectionMap'
import { findRestrictedAssetsSource, type ResponseMap } from './restrictedAssetsSources'

export interface RestrictedAssetsSyncOptions {
  owner: RestrictedAssetsOwner
  variant: () => RestrictedAssetsVariant
  wpId: () => string | undefined
  projectId: () => string | undefined
  responses: () => ResponseMap | undefined
  applicableStandards?: () => readonly string[] | null | undefined
  sheetNames: RestrictedAssetsSheetNames
  /** 审计年度（不传则由后端按 `projects.audit_year` 定位） */
  year?: () => number | undefined
  /** 只读态跳过推送 */
  isReadonly?: () => boolean
}

/**
 * 返回 `syncRestrictedAssets()`：
 * - 无数据 / 只读 / 缺 projectId → 静默跳过（**不推空段** —— 空推送会把段恢复成模板骨架）
 * - `row_scope_unresolved` 非空 → 提示审计师（fail closed 是静默跳过，必须可见）
 * - 网络失败 → warning，不抛（受限资产是附加推送，不能盖掉主章节的「已同步」提示）
 */
export function useRestrictedAssetsSync(
  opts: RestrictedAssetsSyncOptions,
): () => Promise<void> {
  const source = findRestrictedAssetsSource(opts.owner)

  return async function syncRestrictedAssets(): Promise<void> {
    const projectId = opts.projectId()
    if (!projectId || opts.isReadonly?.()) return
    if (!source) {
      // 声明表里没有该 owner → 说明该循环还没接（守卫会红），这里静默不报错
      return
    }
    const responses = opts.responses()
    if (!responses) return

    const variant = opts.variant()
    const details = source.collect(responses)
    const payloads = buildRestrictedAssetsPayloads(
      variant,
      opts.wpId() || '',
      opts.applicableStandards?.() ?? null,
      {
        ownerRowCode: opts.owner,
        rows: summarizeRestrictedRows(RESTRICTED_ASSETS_OWNERS[opts.owner], details),
      },
      opts.sheetNames,
    )
    if (!payloads.length) return

    const year = opts.year?.()
    const sectionId = RESTRICTED_ASSETS_NOTE_SECTION[variant]
    for (const payload of payloads) {
      try {
        const resp: any = await http.post(
          `/api/projects/${projectId}/disclosure-notes/sync-from-workpaper`,
          year ? { ...payload, year } : payload,
        )
        const data = resp?.data ?? resp
        const failure = rowScopeFailureMessage(
          '受限资产',
          data?.row_scope_unresolved,
          data?.row_scope_unresolved_reasons,
        )
        if (failure) {
          ElMessage.warning(failure)
          continue
        }
        if (data && (data.success || data.section_id)) {
          eventBus.emit('disclosure:note-text-updated', {
            wpCode: source.wpCode,
            variant,
            projectId,
            sectionIds: [sectionId],
            timestamp: Date.now(),
          })
        }
      } catch (err: any) {
        // 重复点击被请求去重取消 → 静默
        if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
        ElMessage.warning('受限资产同步附注失败，请稍后重试')
        return
      }
    }
  }
}
