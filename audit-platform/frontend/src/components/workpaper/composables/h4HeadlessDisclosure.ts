/**
 * H4 工程物资披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useH4Disclosure`（取数 / 勾稽）+ `useH4Listed/SoeDisclosureForm`（表单状态、挂载 `load`：
 * 无数据则从来源取数，国企另回放本会话的 H2 在建工程审定缓存）→ 同一个快照 → `buildH4ListedSyncPayloads` /
 * `buildH4SoeSyncPayloads`（Tab 传 null 适用准则，这里同参）。上市 Tab 发送时请求体另带 `year`（审计年度），离屏同样带
 * 附注页年度；国企 Tab 不带，离屏也不带。保存回调为空（离屏不改底稿）。
 *
 * 🔴 外壳种子（上市）：宿主 `GtH4EngineeringMaterials` 挂载后用 render-config 的 `detail_prefill`（试算表工程物资叶子科目）
 * 经 `buildH4DetailSeedRows` 把 H4-2 明细种进内存回复（H4-2 已存过就不种），上市 Tab 从来源取数时用的就是这份。离屏在
 * 「上市分类表没存过数（挂载会取数）且 H4-2 没有已存行」时取一次 render-config、用同一个 `buildH4DetailSeedRows` 种进本次
 * 回复再取数（与打开底稿看到的一致）；取不到配置就不写这一节并说明原因。
 *
 * 写入章节与 H2 共用（五、23 / 八、23）：H4 只推「工程物资」表（上市）/ 汇总表（国企），载荷不带 `_removed_table_keys`。
 */
import { ref } from 'vue'
import {
  defineHeadlessProvider,
  loadRenderConfig,
  postHeadlessSyncPayload,
} from '@/components/workpaper/headless/headlessFramework'
import { useH4Disclosure } from './useH4Disclosure'
import { useH4ListedDisclosureForm, useH4SoeDisclosureForm } from './h4DisclosureForm'
import { buildH4ListedSyncPayloads } from './h4DisclosureSyncPayload'
import { buildH4SoeSyncPayloads } from './h4SoeDisclosureSyncPayload'
import { buildH4DetailSeedRows, type H4PrefillItem } from './h4DetailPrefill'

/** 取不到 render-config ⇒ 不知道外壳会种哪些 H4-2 明细 */
export const H4_HOST_SEED_UNKNOWN_REASON = 'H4 工程物资分类表尚未保存过，取不到底稿渲染配置、无法确认底稿页按试算表自动带出的'
  + 'H4-2 明细，本次未写入；请打开 H4 底稿附注披露页一次后再刷新'

/** 宿主拿到的 htmlData 里的 `detail_prefill`（各页签同一份渲染结果，取第一个带它的页签） */
function hostDetailPrefill(renderConfig: any | null): H4PrefillItem[] | null | undefined {
  const sheets: any[] = Array.isArray(renderConfig?.sheets) ? renderConfig.sheets : []
  const hit = sheets.find((s) => s?.html_data && 'detail_prefill' in s.html_data)
  return hit ? hit.html_data.detail_prefill : renderConfig?.html_data?.detail_prefill
}

export const h4HeadlessProvider = defineHeadlessProvider({
  prefix: 'H4-',
  setup: ({ ctx, responses }) => {
    const responsesRef = ref(responses)
    const disclosure = useH4Disclosure(responsesRef)
    return ctx.variant === 'listed'
      ? { variant: 'listed' as const, responsesRef, skip: null as string | null, form: useH4ListedDisclosureForm({ disclosure, onChange: () => {} }) }
      : { variant: 'soe' as const, responsesRef, skip: null as string | null, form: useH4SoeDisclosureForm({ disclosure, onChange: () => {} }) }
  },
  // Tab onMounted：load() = 读回 → 分类表没数则从来源取数（上市取数前先补外壳种子，见文件头）
  prepare: async (inst, { ctx, responses }) => {
    if (inst.variant === 'soe') return inst.form.load(responses, ctx.projectId)
    if (inst.form.readBack(responses)) return
    const existing = responses.get('H4-2-rows')?.remark
    if (!hasSavedRows(existing)) {
      const config = await loadRenderConfig(ctx.wpId)
      if (!config) {
        inst.skip = H4_HOST_SEED_UNKNOWN_REASON
        return
      }
      const seedRows = buildH4DetailSeedRows(hostDetailPrefill(config), existing)
      if (seedRows) {
        inst.responsesRef.value.set('H4-2-rows', { item_id: 'H4-2-rows', remark: JSON.stringify(seedRows), conclusion: null })
      }
    }
    inst.form.pullFromSources()
  },
  build: (inst, { ctx }) => (inst.variant === 'listed'
    ? buildH4ListedSyncPayloads(ctx.wpId, null, inst.form.snapshot())
    : buildH4SoeSyncPayloads(ctx.wpId, null, inst.form.snapshot())),
  post: (inst, payload, { ctx }) => {
    if (inst.skip) return Promise.resolve({ section: payload.section_id, rows: 0, skipped: inst.skip })
    return postHeadlessSyncPayload(
      ctx.projectId,
      inst.variant === 'listed' ? { ...payload, year: ctx.year } as typeof payload : payload,
    )
  },
})

/** H4-2 是否有已存的非空明细行（有 ⇒ 外壳不种） */
function hasSavedRows(existingRowsJson: string | null | undefined): boolean {
  if (!existingRowsJson) return false
  try {
    const existing = JSON.parse(existingRowsJson)
    return Array.isArray(existing) && existing.length > 0
  } catch {
    return false
  }
}
