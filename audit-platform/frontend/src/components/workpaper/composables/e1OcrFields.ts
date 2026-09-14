/**
 * E1 OCR 字段契约 — 前后端共用真源
 *
 * 字段以两个弹窗 SFC 的 `export interface` 为唯一裁决者（弹窗是已写好的真源），
 * 本文件从弹窗 re-export 以便后端守卫读 .ts 源码做三向比对。
 *
 * @spec e1-orphan-components-wiring — Task 5
 */

// Re-export from dialog SFC (single source of truth)
export type { CutoffOcrFields } from '../e1/E1CutoffOcrConfirmDialog.vue'
export type { LargeCheckOcrFields } from '../e1/E1LargeCheckOcrConfirmDialog.vue'

/** OCR 端点统一响应形态（与既有 4 个 E1 OCR 端点一致） */
export interface E1OcrResponse<F> {
  fields: Partial<F>
  confidence?: number
  preview?: string
  file_name?: string
}
