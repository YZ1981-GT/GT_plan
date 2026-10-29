/**
 * F1 预付款项披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码，外壳那部分也照主入口 `GtF1Prepayment` 装配：
 * - 账龄口径 `useF1AgingScope`（表级覆盖 > 项目账龄配置，配置由框架预取进缓存）→ 跨表 `useF1CrossSheet`；
 * - 减值准备预填 / 被审计单位名称：外壳传给 Tab 的是本口径披露 sheet 的 `html_data`，这里用共享的
 *   `f1DisclosureHtmlDataOf` 在渲染配置里按宿主同一名称语义定位，再按主入口同一取法读取；
 * - 上市 `useF1DisclosureListed` / 国企 `useF1DisclosureSoe` → 同一个 `getSyncSnapshot` → 同一个子表 builder →
 *   同一个 `buildF1SyncPayload`（口径不适用回 null）。保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useF1AgingScope } from './useF1AgingScope'
import { useF1CrossSheet } from './useF1CrossSheet'
import { useF1DisclosureListed } from './useF1DisclosureListed'
import { useF1DisclosureSoe } from './useF1DisclosureSoe'
import { buildF1ListedSubTableData, buildF1SoeSubTableData, buildF1SyncPayload } from './f1DisclosureSyncPayload'
import { f1ClientNameOf, f1DisclosureHtmlDataOf, f1ImpairmentPrefillOf } from './f1HostRenderContext'

export const f1HeadlessProvider = defineHeadlessProvider({
  // 与主入口 useF1FormData 同口径
  prefix: 'F1-',
  needs: { aging: true, renderConfig: true },
  setup: ({ ctx, responses, renderConfig }) => {
    const allResponses = ref(responses)
    const projectId = ref(ctx.projectId)
    const isReadonly = ref(false)
    const agingScope = useF1AgingScope({ allResponses, projectId, debouncedSave: () => {}, isReadonly })
    const htmlData = f1DisclosureHtmlDataOf(renderConfig, ctx.variant)
    const options = {
      allResponses,
      wpId: ref(ctx.wpId),
      projectId,
      saveImmediate: async () => {},
      debouncedSave: () => {},
      crossSheet: useF1CrossSheet({ allResponses, segments: agingScope.segments }),
      isReadonly,
      applicableStandards: ref([...ctx.applicableStandards]),
      impairmentPrefill: ref(f1ImpairmentPrefillOf(htmlData)),
      clientName: ref(f1ClientNameOf(htmlData)),
      listenForNoteUpdates: false,
    }
    return ctx.variant === 'listed'
      ? { variant: 'listed' as const, disclosure: useF1DisclosureListed(options) }
      : { variant: 'soe' as const, disclosure: useF1DisclosureSoe(options) }
  },
  build: (instance, { ctx }) => buildF1SyncPayload(
    instance.variant,
    ctx.wpId,
    ctx.applicableStandards,
    instance.variant === 'listed'
      ? buildF1ListedSubTableData(instance.disclosure.getSyncSnapshot())
      : buildF1SoeSubTableData(instance.disclosure.getSyncSnapshot()),
    ctx.year,
  ),
})
