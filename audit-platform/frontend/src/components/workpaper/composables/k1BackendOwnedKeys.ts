/**
 * K1-1 后端公式推送独占键分类。
 *
 * 提示条识别用手写正则（K1 binding 接入前生成文件无 K1 键）；
 * 保存集合从生成文件派生（K1 接入后自动生效，接入前不过滤）。
 *
 * spec: formula-push-all-subjects-rollout · 阶段 4 / 任务 13
 */
import { isOwnedKey } from '@/generated/formulaPushOwnedKeys'

/** 提示条用的独占键识别（含 K1 binding 尚未接入时的手写正则兜底）。 */
const _K1_BACKEND_OWNED_PATTERNS = [
  /^K1-1-(?:nature-(?:gross|prov)-n[0-4]|(?:receivable|baddebt)-r[0-3])-(?:begin|unadj)$/,
  /^K1-1-fs-(?:interest|dividend|other-total)$/,
  /^K1-1-audited-(?:receivable|baddebt|net)$/,
] as const

export function isK1BackendOwnedKey(itemId: string): boolean {
  // 生成文件优先（K1 接入后精确匹配）；兜底手写正则（K1 接入前提示条仍能识别）
  if (isOwnedKey('K1', itemId)) return true
  return _K1_BACKEND_OWNED_PATTERNS.some((re) => re.test(itemId))
}

/** K1 宿主保存集合：按生成文件过滤独占键（K1 接入前生成文件无 K1 → 不过滤）。 */
export function k1SaveItemIds(itemIds: Iterable<string>): string[] {
  return [...itemIds].filter((id) => !isOwnedKey('K1', id))
}

/** K1-1 审定表保存集合：同上口径。 */
export function k1AdjudicationSaveItemIds(itemIds: Iterable<string>): string[] {
  return [...itemIds].filter((id) => !isOwnedKey('K1', id))
}
