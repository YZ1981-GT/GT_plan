/**
 * H2 在建工程披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab（上市 `H2TabDisclosureListed` 五、23 / 国企 `H2TabDisclosureSoe` 八、23）同一套代码（`h2DisclosureTabState`）：
 * Tab 挂载时的 `load`（读回已保存的披露表）→ 没有数据则「从审定/明细取数」的计算部分 `applySources`（H2-1 / H2-2，只改内存）
 * → 「同步到附注」同一个 `syncPayloads`（`buildH2Listed/SoeSyncPayloads(wpId, [], 快照)`）。离屏不写底稿（Tab 挂载取数后的
 * 防抖保存不做）、不弹提示、不调 AI、不推国企受限资产段（八、93 由 Tab 同步后另推）。
 *
 * 🔴 外壳种子：宿主 `GtH2ConstructionInProgress._seedDetailFromPrefill` 在 H2-2 明细没有已存内容时，把本页签 render-config 的
 * `detail_prefill`（试算表 1604 叶子科目）作为 `H2-2-rows` 种进内存回复（不落库），披露 Tab 挂载取数会用上这份种子。种子代码在
 * 宿主组件里，离屏调不到同一份 ⇒ 只在「披露表没有已存数据（挂载要取数）且 H2-2 没有已存明细行」时取一次 render-config，
 * 按 Tab 的同一页签判外壳会不会种：会种（或取不到配置）⇒ 这一节不写、回报原因；不会种 ⇒ 载荷与 Tab 相同，照常写。
 */
import {
  defineHeadlessProvider,
  loadRenderConfig,
  postHeadlessSyncPayload,
  type HeadlessDisclosureContext,
} from '@/components/workpaper/headless/headlessFramework'
import { H2_DISCLOSURE_SHEET_NAME } from './h2NoteSectionMap'
import {
  readH2PullSources,
  useH2ListedDisclosureState,
  useH2SoeDisclosureState,
  type H2ListedDisclosureState,
  type H2SoeDisclosureState,
} from './h2DisclosureTabState'

/** 外壳会用 render-config 种子补 H2-2 明细 ⇒ 底稿页取数结果离屏复现不了 */
export const H2_HOST_SEED_SKIP_REASON = 'H2 披露表尚未保存过，底稿页打开时会按试算表在建工程科目种子（H2-2 明细预填）自动取数，'
  + '离屏同步取不到这份种子，本次未写入；请打开 H2 底稿附注披露页一次后再刷新'
/** 取不到 render-config ⇒ 不知道外壳会不会种 */
export const H2_HOST_SEED_UNKNOWN_REASON = 'H2 披露表尚未保存过，取不到底稿渲染配置、无法确认底稿页自动取数的结果，本次未写入；'
  + '请打开 H2 底稿附注披露页一次后再刷新'

/** 宿主按页签名分发披露 Tab（国企页签名是「国有企业」，与宿主 currentSheet 同口径）⇒ Tab 外壳拿到的 htmlData = 该页签的 html_data */
function disclosureSheetHtmlData(renderConfig: any | null, variant: 'listed' | 'soe'): Record<string, any> | null {
  const sheets: any[] = Array.isArray(renderConfig?.sheets) ? renderConfig.sheets : []
  const pattern = variant === 'listed' ? /附注.*上市|H2-note-listed/ : /附注.*国企|附注.*国有|H2-note-soe/
  const sheet = sheets.find((s) => s?.sheet_name === H2_DISCLOSURE_SHEET_NAME[variant])
    ?? sheets.find((s) => pattern.test(String(s?.sheet_name ?? '')))
  const hd = sheet?.html_data
  return hd && typeof hd === 'object' ? hd : null
}

/** 外壳是否会给 H2-2 种行（与宿主同一判据：`detail_prefill` 是非空数组）；返回不写的原因，null = 不会种 */
async function hostSeedSkipReason(ctx: HeadlessDisclosureContext): Promise<string | null> {
  const htmlData = disclosureSheetHtmlData(await loadRenderConfig(ctx.wpId), ctx.variant)
  if (!htmlData) return H2_HOST_SEED_UNKNOWN_REASON
  const prefill = htmlData.detail_prefill
  return Array.isArray(prefill) && prefill.length > 0 ? H2_HOST_SEED_SKIP_REASON : null
}

interface H2HeadlessInstance {
  state: H2ListedDisclosureState | H2SoeDisclosureState
  /** 非空 = 这一节不写的原因 */
  skip: string | null
}

export const h2HeadlessProvider = defineHeadlessProvider<H2HeadlessInstance>({
  // 与宿主取回复同口径（render-config `responses_snapshot`：item_id LIKE 'H2-%'）
  prefix: 'H2-',
  setup: ({ ctx }) => ({
    state: ctx.variant === 'listed' ? useH2ListedDisclosureState() : useH2SoeDisclosureState(),
    skip: null,
  }),
  // Tab onMounted：load() → 没有数据则 pullFromSources(false)（这里只做计算部分：不保存、不提示）
  prepare: async (inst, { ctx, responses }) => {
    if (inst.state.load(responses)) return
    inst.state.applySources(responses)
    const { det } = readH2PullSources(responses)
    // H2-2 有已存明细行 ⇒ 外壳不种（不覆盖已有数据），Tab 取数用的就是这份
    if (Array.isArray(det) && det.length) return
    inst.skip = await hostSeedSkipReason(ctx)
  },
  build: (inst, { ctx }) => inst.state.syncPayloads(ctx.wpId),
  post: (inst, payload, { ctx }) => (inst.skip
    ? Promise.resolve({ section: payload.section_id, rows: 0, skipped: inst.skip })
    : postHeadlessSyncPayload(ctx.projectId, payload)),
})
