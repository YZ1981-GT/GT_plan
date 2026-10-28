/**
 * L1 短期借款披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：Tab 用外壳 `GtL1ShortTermLoans` 注入的表单（`useL1FormData` + `selfLoad()`：拉回复后
 * `applyResponses` 只留 L1- 条目并解析各 sheet），离屏建同一个 `useL1FormData`、把框架已读的同一批回复交给同一个
 * `applyResponses`（不再发请求、不弹提示）→ 按 Tab 同参建 `useL1DisclosureData`（分类表自审定表 L1-1 派生、逾期表 / 结论
 * 读回）→ `buildL1SyncOptions` → `buildL1SyncPayload` → `buildL1SyncRequestBody`。保存不会触发（只读计算，不写底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useL1FormData } from '@/composables/useL1FormData'
import { useL1DisclosureData } from '@/composables/useL1DisclosureData'
import { buildL1SyncPayload } from './l1NoteSectionMap'
import { buildL1SyncOptions, buildL1SyncRequestBody } from './l1DisclosureSync'

export const l1HeadlessProvider = defineHeadlessProvider({
  // 与 useL1FormData 的条目口径一致（L1-{sheet}-{field}）
  prefix: 'L1-',
  setup: ({ ctx, responses }) => {
    const formData = useL1FormData(ref(ctx.wpId), ref(ctx.projectId), ref(false))
    formData.applyResponses([...responses.values()])
    return useL1DisclosureData(formData, { variant: ctx.variant, isReadonly: ref(false) })
  },
  build: (disclosure, { ctx }) => buildL1SyncRequestBody(
    ctx.variant,
    ctx.wpId,
    buildL1SyncPayload(buildL1SyncOptions(ctx.variant, disclosure)),
  ),
})
