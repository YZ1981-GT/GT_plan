/**
 * cycleDirectory.ts — 底稿目录页「本循环底稿目录」grid 数据源（单一真源，全循环复用）
 *
 * 🔴 只显示源模板（wp_templates/_index.json）里存在的 canonical 科目，过滤掉
 *    wp_index 里跨模板集混入的污染项（如 K14-K18 上市损益类审定表，无源模板）。
 *
 * 数据组合：
 *   1. GET /wp-templates/list  → canonical 科目清单（wp_code/wp_name/cycle，_index.json 派生，无污染）
 *   2. listWorkpapersPaged     → wp_code → wp_id 映射（已生成底稿，供跨底稿跳转导航）
 *   两者取交集：canonical 决定"显示哪些"，working-papers 决定"是否可点/跳哪里"。
 */
import http from '@/utils/http'
import { workpapers as P_wp } from '@/services/apiPaths'
import { listWorkpapersPaged } from '@/services/workpaperApi'

export interface CycleWpCard {
  wp_code: string
  wp_name: string
  wp_id: string | null
  is_current: boolean
}

/** 顶层科目编码正则（如 K0/K13/D2/H10），排除子表 K1-2 等。 */
function topLevelRe(cycleLetter: string): RegExp {
  return new RegExp(`^${cycleLetter}\\d+$`)
}

function codeNum(code: string, cycleLetter: string): number {
  const n = parseInt(code.replace(new RegExp(`^${cycleLetter}`), ''), 10)
  return Number.isFinite(n) ? n : 0
}

/**
 * 加载指定循环的「本循环底稿目录」卡片。
 * @param projectId    项目 ID
 * @param cycleLetter  循环字母（K/D/F/G/H/I/J/L/M/N/E...）
 * @param currentWpId  当前底稿 wp_id（用于高亮"当前"）
 */
export async function loadCycleWorkpaperCards(
  projectId: string,
  cycleLetter: string,
  currentWpId: string,
): Promise<CycleWpCard[]> {
  if (!projectId || !cycleLetter) return []
  const re = topLevelRe(cycleLetter)

  // 1. canonical 科目清单（源模板权威，无污染）
  let canonical: Array<{ wp_code: string; wp_name: string }> = []
  try {
    const { data } = await http.get(P_wp.templateList(projectId))
    const items: any[] = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : []
    canonical = items
      .filter((it) => re.test(String(it?.wp_code || '')))
      .map((it) => ({ wp_code: String(it.wp_code), wp_name: String(it.wp_name ?? it.wp_code) }))
  } catch {
    canonical = []
  }
  if (canonical.length === 0) return []

  // 2. working-papers → wp_code → wp_id 映射（仅已生成）
  const idByCode = new Map<string, string>()
  try {
    const collected: any[] = []
    let page = 1
    for (;;) {
      const env: any = await listWorkpapersPaged(projectId, { page, page_size: 100 })
      const items: any[] = Array.isArray(env?.items) ? env.items : []
      collected.push(...items)
      const total = Number.isFinite(env?.total) ? Number(env.total) : collected.length
      if (items.length === 0 || collected.length >= total || page > 20) break
      page += 1
    }
    for (const it of collected) {
      const code = String(it?.wp_code || '')
      if (!re.test(code)) continue
      const generated = it?.wp_generated !== false
      const wpId = (it?.wp_id ?? it?.id ?? null) as string | null
      if (generated && wpId && !idByCode.has(code)) idByCode.set(code, wpId)
    }
  } catch {
    // 拿不到 wp_id 时仍显示 canonical 卡片（灰色不可点）
  }

  // 3. 组合：canonical 决定显示，working-papers 决定可点/跳转
  const rows: CycleWpCard[] = canonical.map((c) => {
    const wpId = idByCode.get(c.wp_code) ?? null
    return {
      wp_code: c.wp_code,
      wp_name: c.wp_name,
      wp_id: wpId,
      is_current: !!wpId && wpId === currentWpId,
    }
  })
  rows.sort((a, b) => codeNum(a.wp_code, cycleLetter) - codeNum(b.wp_code, cycleLetter))
  return rows
}
