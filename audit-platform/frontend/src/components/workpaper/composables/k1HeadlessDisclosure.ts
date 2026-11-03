/**
 * K1 其他应收款披露表离屏同步（附注页「刷新」用，spec note-pull-followup-closure R1）。
 *
 * 与底稿披露 Tab 同一套代码：`useK1DisclosureListed` / `useK1DisclosureSoe`（由 checklist 回复 + 项目账龄配置现算披露表）
 * → Tab 挂载时的同一步 `initialFillFromSources`（还没有已存披露数据 ⇒ 从 K1-1/K1-2/K1-3/K1-7/K1-9 强制取数；离屏不弹提示）
 * → 同一个 `buildSyncPayloads`（Tab 的「同步到附注」也调它：快照 + 本口径 builder，口径不适用回空）。
 * 上市 五、8 / 国企 八、9 与 G2、G3 共用章节（后端按子表名浅合并；K1 载荷不带 `_removed_table_keys`）。
 * 账龄配置由框架先预取进缓存（`useAgingConfig` 离屏时只套用缓存）；保存回调为空（离屏不改底稿）。
 */
import { ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useK1DisclosureListed } from './useK1DisclosureListed'
import { useK1DisclosureSoe } from './useK1DisclosureSoe'

type K1HeadlessInstance = ReturnType<typeof useK1DisclosureListed> | ReturnType<typeof useK1DisclosureSoe>

export const k1HeadlessProvider = defineHeadlessProvider<K1HeadlessInstance>({
  // 与宿主 GtK1OtherReceivables 的条目口径一致（K1-{sheet}-{field}；不含 K10~K13）
  prefix: 'K1-',
  needs: { aging: true },
  setup: ({ ctx, responses }) => {
    const opts = {
      wpId: ref(ctx.wpId),
      projectId: ref(ctx.projectId),
      allResponses: ref(responses),
      isReadonly: ref(false),
      onSave: () => {},
      applicableStandards: () => ctx.applicableStandards,
    }
    return ctx.variant === 'soe' ? useK1DisclosureSoe(opts) : useK1DisclosureListed(opts)
  },
  prepare: (disc) => {
    disc.initialFillFromSources()
  },
  build: (disc) => disc.buildSyncPayloads(),
})
