/** H1 固定资产离屏同步：主章节与受限资产段均复用页面纯恢复/构建口径。 */
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { restoreH1ListedState, restoreH1SoeState } from './h1DisclosureTabState'
import { resolveH1ProjectContext } from './h1ProjectContext'
import {
  resolveH1CurrentStandardFromProject,
  resolveH1VariantFromTemplateType,
} from './h1NoteSectionMap'
import {
  buildH1ListedSyncPayloads,
  buildH1SoeSyncPayload,
  type H1SyncFromWorkpaperPayload,
} from './h1DisclosureSyncPayload'
import { H1_DISCLOSURE_SHEET_NAME } from './h1NoteSectionMap'
import { buildRestrictedAssetsSyncPayloads } from './restrictedAssetsSyncPayload'

export const h1HeadlessProvider = defineHeadlessProvider({
  prefix: 'H1-',
  needs: { renderConfig: true },
  setup: ({ ctx, responses, renderConfig }) => {
    const project = resolveH1ProjectContext(renderConfig)
    const templateType = ctx.templateType ?? project.templateType
    const reportScope = ctx.reportScope ?? project.reportScope
    const projectVariant = resolveH1VariantFromTemplateType(templateType)
    const currentStandard = resolveH1CurrentStandardFromProject(
      ctx.variant, templateType, reportScope,
    )
    if (projectVariant && projectVariant !== ctx.variant) return { payloads: [] }

    let main: H1SyncFromWorkpaperPayload[]
    if (ctx.variant === 'listed') {
      const restored = restoreH1ListedState(responses)
      main = restored.hasSource
        ? buildH1ListedSyncPayloads(
            ctx.wpId, [], restored.snapshot, { currentStandard },
          )
        : []
    } else {
      const restored = restoreH1SoeState(responses)
      const payload = restored.hasSource
        ? buildH1SoeSyncPayload(
            ctx.wpId, ctx.applicableStandards, restored.state, { currentStandard },
          )
        : null
      main = payload ? [payload] : []
    }
    const restricted = buildRestrictedAssetsSyncPayloads({
      owner: 'BS-028',
      variant: ctx.variant,
      wpId: ctx.wpId,
      responses,
      applicableStandards: [currentStandard],
      sheetNames: H1_DISCLOSURE_SHEET_NAME,
    }).payloads
    return { payloads: [...main, ...restricted] }
  },
  build: ({ payloads }) => payloads,
})
