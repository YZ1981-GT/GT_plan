/**
 * E1 后端独占键（公式推送引擎是唯一写入方）—— 前端只在内存里算、**不保存**。
 *
 * 从生成文件 `formulaPushOwnedKeys.ts` 派生（Task 13 改造），保留导出名以兼容
 * 既有宿主 / 测试的 import。
 *
 * spec: formula-push-all-subjects-rollout · design §五 · 需求 4.4
 */
import { isOwnedKey } from '@/generated/formulaPushOwnedKeys'

export function isE1BackendOwnedKey(itemId: string): boolean {
  return isOwnedKey('E1', itemId)
}

/** 审定表防抖保存要提交的条目：`E1-adj-` 前缀、且不是后端独占键。 */
export function e1AdjudicationSaveItemIds(itemIds: Iterable<string>): string[] {
  return [...itemIds].filter((id) => id.startsWith('E1-adj-') && !isE1BackendOwnedKey(id))
}
