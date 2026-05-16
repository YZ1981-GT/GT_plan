/**
 * useCrossModuleRefs — 跨模块引用标签 composable
 *
 * 从 cross_wp_references.json 加载当前 wp_code 的所有引用目标，
 * 提供 cell → refs 映射、路由计算、颜色映射。
 *
 * Foundation Sprint 1 Task 1.6
 */

import { ref, type Ref } from 'vue'

// ── 目标类型颜色映射 ──
export const TARGET_COLOR_MAP: Record<string, string> = {
  note_section: '#CE93D8',   // 附注 → 紫色
  report_row: '#64B5F6',     // 报表 → 蓝色
  workpaper: '#4DD0E1',      // 底稿 → 青色
}

export interface CrossModuleRef {
  ref_id: string
  target_type: 'note_section' | 'report_row' | 'workpaper'
  target_label: string
  target_route: string
  source_cell: string
  source_sheet: string
  target_wp_code: string
  category: string
  severity: string
}

interface RawReference {
  ref_id: string
  description: string
  source_wp: string
  source_sheet: string
  source_cell: string
  targets: Array<{
    wp_code: string
    sheet: string
    cell: string
    formula: string
  }>
  category: string
  severity: string
}

/**
 * 跨模块引用 composable
 */
export function useCrossModuleRefs(wpCode: Ref<string>, projectId: Ref<string>) {
  const refs = ref<CrossModuleRef[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  /**
   * 从 JSON 数据加载当前 wp_code 的引用
   */
  function loadFromJson(referencesData: { references: RawReference[] }) {
    const result: CrossModuleRef[] = []

    for (const rawRef of referencesData.references || []) {
      // 当前底稿作为 source 的引用（本底稿数据被其他底稿引用）
      if (rawRef.source_wp === wpCode.value) {
        for (const target of rawRef.targets) {
          result.push({
            ref_id: rawRef.ref_id,
            target_type: _inferTargetType(target.wp_code),
            target_label: _buildLabel(target.wp_code, rawRef.description),
            target_route: computeRouterPath({
              ref_id: rawRef.ref_id,
              target_type: _inferTargetType(target.wp_code),
              target_wp_code: target.wp_code,
            } as CrossModuleRef),
            source_cell: rawRef.source_cell,
            source_sheet: rawRef.source_sheet,
            target_wp_code: target.wp_code,
            category: rawRef.category,
            severity: rawRef.severity,
          })
        }
      }

      // 当前底稿作为 target 的引用（本底稿引用其他底稿数据）
      for (const target of rawRef.targets) {
        if (target.wp_code === wpCode.value) {
          result.push({
            ref_id: rawRef.ref_id,
            target_type: _inferTargetType(rawRef.source_wp),
            target_label: `← ${rawRef.source_wp}: ${rawRef.description}`,
            target_route: computeRouterPath({
              ref_id: rawRef.ref_id,
              target_type: 'workpaper',
              target_wp_code: rawRef.source_wp,
            } as CrossModuleRef),
            source_cell: target.cell,
            source_sheet: target.sheet,
            target_wp_code: rawRef.source_wp,
            category: rawRef.category,
            severity: rawRef.severity,
          })
        }
      }
    }

    refs.value = result
    loaded.value = true
  }

  /**
   * 获取指定 cell 的所有跨模块引用
   */
  function getRefsForCell(sheet: string, cellRef: string): CrossModuleRef[] {
    return refs.value.filter(
      r => r.source_sheet === sheet && r.source_cell === cellRef
    )
  }

  /**
   * 计算跳转路由路径
   */
  function computeRouterPath(refItem: CrossModuleRef): string {
    const pid = projectId.value
    const targetCode = refItem.target_wp_code

    switch (refItem.target_type) {
      case 'note_section':
        return `/projects/${pid}/disclosure-notes`
      case 'report_row':
        return `/projects/${pid}/reports`
      case 'workpaper':
      default:
        // 跳转到目标底稿（需要通过 wp_code 查找 wp_id）
        return `/projects/${pid}/workpapers?wp_code=${targetCode}`
    }
  }

  return {
    refs,
    loading,
    loaded,
    loadFromJson,
    getRefsForCell,
    computeRouterPath,
    TARGET_COLOR_MAP,
  }
}

// ── 辅助函数 ──

function _inferTargetType(wpCode: string): 'note_section' | 'report_row' | 'workpaper' {
  if (wpCode === 'IS' || wpCode === 'BS' || wpCode === 'CFS' || wpCode === 'EQ') {
    return 'report_row'
  }
  return 'workpaper'
}

function _buildLabel(targetWpCode: string, description: string): string {
  return `→ ${targetWpCode}: ${description}`
}
