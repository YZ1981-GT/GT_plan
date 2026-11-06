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

// 🔴 2026-11-05 删除 `k1SaveItemIds` / `k1AdjudicationSaveItemIds`（原按生成文件过滤独占键）。
//
// 它们与 K1 的产品裁决相反：**K1 宿主保留完整保存集合**，后端独占键的分类只用于提示条接线
// （裁决记在 `__tests__/k1FormulaPushHost.spec.ts` 的文件头与「根宿主保存入口把原始 itemId 交给
// persistence.save」那条源码级判据里）。两个函数的注释自己写着「K1 接入前生成文件无 K1 → 不过滤」
// —— 那正是它们当初能与裁决共存的原因；`formula-push-all-subjects-rollout` 把 K1 binding 接进生成
// 文件后过滤真的生效了，于是三条「保留完整集合」的判据一起打红，而生产代码一个调用方都没有
// （现算：只有测试文件 import 它们）。删掉而不是改成恒等：恒等函数会让下一个人以为这里有口径。
//
// E1 的同形函数（`e1AdjudicationSaveItemIds`）**不要**跟着删 —— 它有生产调用方
// `useE1Adjudication.ts`，且 E1 的裁决恰好相反（独占键前端只在内存算、不保存）。
