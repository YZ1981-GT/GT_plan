/**
 * 适用准则归一（leaf 模块，零依赖）。
 *
 * 原实现在 `useF2FormData.ts`（该文件 import 了 vue / element-plus / apiProxy），
 * 而 `useWorkpaperScaffold` 与 `hostApplicableStandards` 都需要它 —— 放在带副作用的
 * 表单 composable 里会把 UI 依赖拖进运行时上下文，也容易形成 import 环。
 * 故抽为零依赖 leaf，`useF2FormData` 改为 re-export（存量 import 零改动）。
 *
 * 口径与后端 `standard_unification_service.derive_applicable_standards` 一致：
 * 组合值在前 + 两个维度值兜底，`stage` 不入列表。
 * 同口径守卫见 `composables/__tests__/normalizeApplicableStandards.spec.ts`
 * 与 `backend/tests/test_applicable_standards_derive.py` 的共享样本表。
 *
 * Spec: applicable-standards-runtime-and-sync-guard R3.3
 */

/** 把项目侧适用准则字段规整为 string[]（兼容 v2 对象 / 单字符串 / 数组） */
export function normalizeApplicableStandards(raw: unknown): string[] {
  if (raw == null || raw === '') return []
  if (Array.isArray(raw)) {
    return raw
      .flatMap((item) => {
        if (item == null) return []
        if (typeof item === 'string') return [item]
        if (typeof item === 'object') {
          const o = item as Record<string, unknown>
          const cand = o.type ?? o.code ?? o.value ?? o.id
          return cand != null && cand !== '' ? [String(cand)] : []
        }
        return [String(item)]
      })
      .map((s) => s.trim())
      .filter(Boolean)
  }
  if (typeof raw === 'string') {
    const t = raw.trim()
    if (!t) return []
    if (t.startsWith('[') || t.startsWith('{')) {
      try {
        return normalizeApplicableStandards(JSON.parse(t))
      } catch { /* fall through */ }
    }
    return t.split(/[,，;；|/]/).map((s) => s.trim()).filter(Boolean)
  }
  if (typeof raw === 'object') {
    const o = raw as Record<string, unknown>
    if (Array.isArray(o.standards)) return normalizeApplicableStandards(o.standards)
    if (Array.isArray(o.list)) return normalizeApplicableStandards(o.list)
    // 🔴 v2 结构化对象 `{entity_type, scope, stage}`（DB 权威源 projects.applicable_standard_v2）
    // 此前**不被识别** → 返回 []，导致披露 Tab 门控恒空：D3 两版对所有项目显示
    // 「当前项目不适用…」（用户不可达），其余循环门控恒开（可在国企项目编辑上市 Tab，
    // 而 sync_from_workpaper 不按 current_standard 定位 → 数据写进错误章节）。
    const entity = firstNonEmpty(o.entity_type, o.entityType)
    const scope = firstNonEmpty(o.scope)
    if (entity || scope) {
      const combo = entity && scope ? `${entity}_${scope}` : ''
      return dedupeNonEmpty([combo, entity, scope])
    }
    const type = o.type ?? o.code ?? o.value
    return type != null && type !== '' ? [String(type)] : []
  }
  return []
}

/** 取首个非空值并归一为小写字符串（v2 维度可能是大写，历史向导写入）。 */
function firstNonEmpty(...candidates: unknown[]): string {
  for (const c of candidates) {
    if (c == null) continue
    const s = String(c).trim().toLowerCase()
    if (s) return s
  }
  return ''
}

function dedupeNonEmpty(values: readonly string[]): string[] {
  const out: string[] = []
  for (const v of values) {
    if (v && !out.includes(v)) out.push(v)
  }
  return out
}

export default normalizeApplicableStandards
