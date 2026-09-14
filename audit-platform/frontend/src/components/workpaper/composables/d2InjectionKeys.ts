/**
 * d2InjectionKeys — D2 模块 provide/inject 类型安全的注入键
 *
 * 替代全局 window.dispatchEvent('d2:save-items') 通信模式，使用 Vue provide/inject
 * 实现组件树内类型安全的父子通信。
 *
 * 注：原 d2:writeback-trial-balance / D2_WRITEBACK_KEY 已随 TB 回写显式发布门改造移除
 * （spec: tb-writeback-explicit-publish-gate Task 2）—— TB 回写现由审定表的
 * publishToTb（显式二次确认 → publish-to-tb 端点）承载，不再经 D2 注入键/事件旁路。
 *
 * 优势：
 * - 类型安全（TS 推导参数类型）
 * - 组件隔离（同页面多实例不冲突）
 * - 无需手动 addEventListener/removeEventListener 生命周期管理
 */
import type { InjectionKey } from 'vue'
import type { ChecklistResponse } from './useD2FormData'

/** 保存 checklist items 到后端（替代 d2:save-items 事件） */
export type D2SaveItemsFn = (items: ChecklistResponse[]) => Promise<void>

export const D2_SAVE_ITEMS_KEY: InjectionKey<D2SaveItemsFn> = Symbol('d2SaveItems')
