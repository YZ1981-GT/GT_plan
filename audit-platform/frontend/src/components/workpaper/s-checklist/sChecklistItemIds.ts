/**
 * S-checklist componentType → checklist_responses.item_id 映射。
 *
 * 这张表与后端 `_s_checklist_sheets.py` 的 S_CHECKLIST_ITEM_IDS
 * 逐值对账；没有可写 checklist 行的参考/说明页明确使用 null。
 * D3.2 只统一身份映射，保存与 readonly 行为由 D4 处理。
 */
export const sChecklistItemIds = {
  's1-regulation-record': 'S1-1-sheet-data',
  's8-adjudication': 'S8-1-sheet-data',
  's9-adjudication': 'S9-1-sheet-data',
  's9-internal-control': 'S9-2-sheet-data',
  's9-legal-regulations': null,
  's9-program-description': null,
  's10-adjudication': 'S10-1-sheet-data',
  's10-internal-control': 'S10-2-sheet-data',
  's10-environmental-regulations': null,
  's17-nonrecurring-detail': 'S17-1-sheet-data',
  's17-reconciliation': 'S17-11-sheet-data',
  's17-tax-impact': 'S17-21-sheet-data'
} as const

export type SChecklistComponentType = keyof typeof sChecklistItemIds
