/**
 * I2 开发支出披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useI2Disclosure`（由 checklist 响应现算披露表，含旧单表键兼容读）→ 同一个快照函数
 * （上市 `getListedSnapshot` / 国企 `getSoeSnapshot`）→ 同一个 `buildI2ListedSyncPayloads` / `buildI2SoeSyncPayloads`。
 * Tab 打开时只读已存披露数据（「从 I2-2/I2-6 取数」是按钮），离屏同样不取数；保存回调为空（离屏不改底稿，Tab 同步前的
 * 落库在离屏没有意义）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useI2Disclosure } from './useI2Disclosure'
import { buildI2ListedSyncPayloads, buildI2SoeSyncPayloads } from './i2DisclosureSyncPayload'

export const i2HeadlessProvider = defineHeadlessProvider({
  prefix: 'I2-',
  setup: ({ ctx, responses }) => useI2Disclosure(ref(responses), {
    variant: ctx.variant,
    saveResponse: async () => {},
    applicableStandards: () => ctx.applicableStandards,
  }),
  build: (disc, { ctx }) => (disc.variant === 'listed'
    ? buildI2ListedSyncPayloads(ctx.wpId, ctx.applicableStandards, disc.getListedSnapshot())
    : buildI2SoeSyncPayloads(ctx.wpId, ctx.applicableStandards, disc.getSoeSnapshot())),
})
