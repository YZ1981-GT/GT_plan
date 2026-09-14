/**
 * G3 模块内依赖注入（替代 g3:save-items / g3:writeback-trial-balance window 事件）
 */
import type { InjectionKey, Ref } from 'vue'
import type { ChecklistResponse } from './useF1FormData'

export type G3SaveItemsFn = (items: ChecklistResponse[]) => void | Promise<void>
export type G3WritebackTbFn = (auditedAmount: number) => void | Promise<void>

export const G3SaveItemsKey: InjectionKey<G3SaveItemsFn> = Symbol('g3SaveItems')
export const G3WritebackTbKey: InjectionKey<G3WritebackTbFn> = Symbol('g3WritebackTb')

/** G3-2 明细内容版本号（表间热更新：切换 Tab 时感知明细变化） */
export const G3DetailRevisionKey: InjectionKey<Ref<number>> = Symbol('g3DetailRevision')
