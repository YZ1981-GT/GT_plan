/**
 * H3 投资性房地产披露表离屏同步。
 *
 * 与真实披露 Tab 共用宿主 responses Map、`useH3FormData` 的读取口径、
 * `useH3MeasurementModel` 的持久化模式，以及 `useH3Disclosure` / `buildH3SyncPayload`。
 * 离屏只读取已存数据，不保存 checklist、不订阅事件，也不挂载界面。
 */
import { ref, type Ref } from 'vue'
import { defineHeadlessProvider } from '@/components/workpaper/headless/headlessFramework'
import { useH3Disclosure } from './useH3Disclosure'
import { useH3FormData, type ChecklistItem } from './useH3FormData'
import { useH3MeasurementModel, type MeasurementModelType } from './useH3MeasurementModel'
import { buildH3SyncPayload } from './h3NoteSectionMap'

const ignoreWrite = () => {}
const ignoreImmediateWrite = async () => {}

export const h3HeadlessProvider = defineHeadlessProvider({
  // 与 useH3FormData.loadAllResponses 相同；同时覆盖权威模式键 H3-measurement-model。
  prefix: ['H3-', 'H3A-'],
  setup: ({ ctx, responses }) => {
    const allResponses = ref(responses) as unknown as Ref<Map<string, ChecklistItem>>
    // useH3FormData 先接入同一宿主 Map；该占位 ref 只供其未调用的 TB 路径使用。
    const bootstrapModel = ref<MeasurementModelType>('cost')
    const form = useH3FormData({
      wpId: ref(ctx.wpId),
      projectId: ref(ctx.projectId),
      measurementModel: bootstrapModel,
      allResponses,
    })
    // 真实宿主与离屏都以 H3-measurement-model 为权威持久化键。
    const { measurementModel } = useH3MeasurementModel({
      getValue: form.getValue,
      saveImmediate: ignoreImmediateWrite,
    })
    const disclosure = useH3Disclosure({
      allResponses,
      wpId: ref(ctx.wpId),
      projectId: ref(ctx.projectId),
      getValue: form.getValue,
      setValue: ignoreWrite,
      saveImmediate: ignoreImmediateWrite,
      measurementModel,
      variant: ref(ctx.variant),
    })
    return { disclosure, measurementModel }
  },
  build: ({ disclosure, measurementModel }, { ctx }) => {
    const listed = ctx.variant === 'listed'
    const fairRows = listed
      ? disclosure.getSectionRowsForSync('fair-change')
      : disclosure.getSectionRowsForSync('soe-fair-change')
        ?? disclosure.getSectionRowsForSync('soe-fair-value')
    const payload = buildH3SyncPayload({
      variant: ctx.variant,
      measurementModel: measurementModel.value,
      costOriginalRows: disclosure.getSectionRowsForSync(listed ? 'cost-original' : 'soe-cost'),
      costDepRows: disclosure.getSectionRowsForSync(listed ? 'cost-dep' : 'soe-cost-dep'),
      costImpairRows: disclosure.getSectionRowsForSync(listed ? 'cost-impair' : 'soe-impair'),
      fairChangeRows: fairRows,
      titleRows: disclosure.getSectionRowsForSync(listed ? 'title-cert' : 'soe-unlicensed'),
      sectionTexts: { ...disclosure.sectionTexts },
      projectId: ctx.projectId,
      wpId: ctx.wpId,
    })
    // 与 Tab 的 POST body 属性顺序一致：builder 载荷之后追加审计年度。
    return { ...payload, year: ctx.year }
  },
})
