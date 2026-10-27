/**
 * F1-7 逐笔凭证的附件位置（spec attachment-inline-preview）
 *
 * 一笔凭证的附件只有一个位置：表页 `F1-7-{本期借方/本期贷方/期后}`、单元格 `item:{槽位}`，槽位由行 id 散列得到
 * （与「逐笔单据核对」弹窗 ⑤ 本笔附件同口径，spec attachment-evidence-intake）。表格 📎 行内识别、弹窗分单据识别、
 * 弹窗 ⑤ 手工上传都挂到这里，表格行尾的小眼睛与弹窗 ⑤ 列表看到的是同一组文件。
 */
import { itemCellRef } from '@/components/attachment/workpaperEvidence'
import type { F1VoucherSection } from '../composables/useF1ComprehensiveCheck'

/** 行 id → 附件槽位（100 ~ 9099；行 id 不变则槽位不变，排序 / 删行不影响） */
export function f1VoucherAttSlot(rowId: string | null | undefined): number {
  const id = rowId || '0'
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0
  return (Math.abs(h) % 9000) + 100
}

export function f1VoucherEvidenceSheet(section: F1VoucherSection): string {
  return `F1-7-${section}`
}

/** 本笔凭证附件的位置：表页 + 单元格 */
export function f1VoucherEvidence(section: F1VoucherSection, rowId: string | null | undefined): { sheet: string; cell: string } {
  return { sheet: f1VoucherEvidenceSheet(section), cell: itemCellRef(f1VoucherAttSlot(rowId)) }
}
