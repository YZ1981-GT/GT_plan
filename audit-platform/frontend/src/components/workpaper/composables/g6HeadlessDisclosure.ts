/**
 * G6 其他债权投资披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿两版披露 Tab 同一套代码（保存回调为空 —— 离屏不改底稿）：
 * - 上市 五、15：`useG6DisclosureListed`（回复里的已存行 + 三阶段块，立即回显）→ 同一个 `buildG6ListedSyncPayload`；
 *   Tab 挂载时只查 AI 可用性，没有 prepare。
 * - 国企 八、16：`useG6SoeDisclosureState`（由国企 Tab 原样抽出）→ prepare = Tab 挂载时的回显 + 从 G6-1 / G6-2 / G6-3 回填
 *   （`loadPersisted` + `applySourceRows(!已存)`，不保存、不提示）→ 同一个发送体 `buildSyncPayload`。章节 / 准则按 Tab 的
 *   口径取自页签 html_data（`needs.renderConfig`，取国企披露页签；实测没有准则键 ⇒ soe_standalone / 八、16）。
 *
 * 🔴 前缀用 `G6-`：外壳 `useG6MainFormData` 只读 `G6A- / G6-1- … / G6-main-`，漏了 `G6-disclosure-` ⇒ 刷新页面后两个 Tab 都读
 *    不到已存披露数据（缺陷已登记）；离屏读本底稿全部 `G6-` 回复，推的是上次保存的披露表。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useG6DisclosureListed } from './useG6DisclosureListed'
import { buildG6ListedSyncPayload } from './g6DisclosureSyncPayload'
import { G6_DISCLOSURE_SHEET_NAME } from './g6NoteSectionMap'
import { useG6SoeDisclosureState } from './g6SoeDisclosureTabState'

/** 国企披露 Tab 拿到的 htmlData = 国企披露页签的 html_data（外壳按页签名分发，与之同一判定） */
function soeSheetHtmlData(renderConfig: any | null): Record<string, any> | null {
  const sheets: any[] = Array.isArray(renderConfig?.sheets) ? renderConfig.sheets : []
  const sheet = sheets.find((s) => s?.sheet_name === G6_DISCLOSURE_SHEET_NAME.soe)
    ?? sheets.find((s) => /G6-note-soe|附注.*国(企|有)/.test(String(s?.sheet_name ?? '')))
  const hd = sheet?.html_data
  return hd && typeof hd === 'object' ? hd : null
}

type G6HeadlessInstance =
  | { variant: 'listed'; dis: ReturnType<typeof useG6DisclosureListed> }
  | { variant: 'soe'; dis: ReturnType<typeof useG6SoeDisclosureState> }

export const g6HeadlessProvider = defineHeadlessProvider<G6HeadlessInstance>({
  prefix: 'G6-',
  needs: { renderConfig: true },
  setup: ({ ctx, responses, renderConfig }) => {
    if (ctx.variant === 'listed') {
      return {
        variant: 'listed',
        dis: useG6DisclosureListed({ allResponses: ref(responses), debouncedSave: () => {}, isReadonly: ref(false) }),
      }
    }
    const htmlData = soeSheetHtmlData(renderConfig)
    return { variant: 'soe', dis: useG6SoeDisclosureState({ allResponses: () => responses, htmlData: () => htmlData }) }
  },
  prepare: (inst) => {
    if (inst.variant !== 'soe') return
    const hadPersisted = inst.dis.loadPersisted()
    inst.dis.applySourceRows(!hadPersisted)
  },
  build: (inst, { ctx }) => (inst.variant === 'soe'
    ? inst.dis.buildSyncPayload(ctx.wpId)
    : buildG6ListedSyncPayload(ctx.wpId, ctx.applicableStandards, inst.dis.state.value)),
})
