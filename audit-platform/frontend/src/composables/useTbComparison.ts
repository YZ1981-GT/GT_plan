/**
 * 试算表跨年度/跨项目对比 composable
 * - 加载对比数据（复用已有 GET /trial-balance 端点）
 * - 按 standard_account_code outer-join
 * - 计算变动额/变动率
 * - 会话级缓存
 */
import { ref, computed, type Ref } from 'vue'
import { getTrialBalance } from '@/services/auditPlatformApi'

export interface ComparisonTarget {
  key: string        // year string or project_id
  label: string      // "2024年" or "子公司A"
  type: 'year' | 'project'
}

export interface JoinedRow {
  standard_account_code: string
  account_name: string
  current_audited: number
  targets: Record<string, number | null>  // key → audited_amount
  variances: Record<string, { amount: number; rate: number | null }>
  onlyCurrent: boolean   // only in current, not in any target
  onlyTarget: string[]   // only in these targets, not in current
}

export function useTbComparison(
  projectId: Ref<string>,
  year: Ref<number>,
  currentRows: Ref<any[]>,
) {
  const targets = ref<ComparisonTarget[]>([])
  const targetData = ref<Map<string, any[]>>(new Map())
  const loading = ref<Map<string, boolean>>(new Map())
  const errors = ref<Map<string, string>>(new Map())

  // Session-level cache
  const cache = new Map<string, any[]>()

  async function loadComparisonYear(targetYear: number) {
    const key = String(targetYear)
    if (cache.has(key)) {
      targetData.value.set(key, cache.get(key)!)
      if (!targets.value.find(t => t.key === key)) {
        targets.value.push({ key, label: `${targetYear}年`, type: 'year' })
      }
      return
    }
    loading.value.set(key, true)
    errors.value.delete(key)
    try {
      const rows = await getTrialBalance(projectId.value, targetYear)
      const data = Array.isArray(rows) ? rows : (rows as any)?.items || []
      cache.set(key, data)
      targetData.value.set(key, data)
      if (!targets.value.find(t => t.key === key)) {
        targets.value.push({ key, label: `${targetYear}年`, type: 'year' })
      }
    } catch (e: any) {
      errors.value.set(key, e?.response?.status === 403 ? '无权限' : '加载失败')
    } finally {
      loading.value.set(key, false)
    }
  }

  async function loadComparisonProject(targetPid: string, targetName: string) {
    const key = targetPid
    if (cache.has(key)) {
      targetData.value.set(key, cache.get(key)!)
      if (!targets.value.find(t => t.key === key)) {
        targets.value.push({ key, label: targetName, type: 'project' })
      }
      return
    }
    loading.value.set(key, true)
    errors.value.delete(key)
    try {
      const rows = await getTrialBalance(targetPid, year.value)
      const data = Array.isArray(rows) ? rows : (rows as any)?.items || []
      cache.set(key, data)
      targetData.value.set(key, data)
      if (!targets.value.find(t => t.key === key)) {
        targets.value.push({ key, label: targetName, type: 'project' })
      }
    } catch (e: any) {
      errors.value.set(key, e?.response?.status === 403 ? '无权限访问该项目' : '加载失败')
    } finally {
      loading.value.set(key, false)
    }
  }

  function removeTarget(key: string) {
    targets.value = targets.value.filter(t => t.key !== key)
    targetData.value.delete(key)
  }

  const joinedRows = computed<JoinedRow[]>(() => {
    if (!targets.value.length) return []

    // Build current map
    const currentMap = new Map<string, any>()
    for (const row of currentRows.value) {
      if (row.standard_account_code) {
        currentMap.set(row.standard_account_code, row)
      }
    }

    // Build target maps
    const targetMaps = new Map<string, Map<string, any>>()
    for (const t of targets.value) {
      const rows = targetData.value.get(t.key) || []
      const map = new Map<string, any>()
      for (const row of rows) {
        if (row.standard_account_code) map.set(row.standard_account_code, row)
      }
      targetMaps.set(t.key, map)
    }

    // Union all account codes
    const allCodes = new Set<string>([...currentMap.keys()])
    for (const [, map] of targetMaps) {
      for (const code of map.keys()) allCodes.add(code)
    }

    // Build joined rows
    const result: JoinedRow[] = []
    for (const code of [...allCodes].sort()) {
      const currentRow = currentMap.get(code)
      const currentAudited = currentRow ? (Number(currentRow.audited_amount) || 0) : 0
      const inCurrent = currentMap.has(code)

      const targetValues: Record<string, number | null> = {}
      const variances: Record<string, { amount: number; rate: number | null }> = {}
      const onlyTarget: string[] = []

      for (const t of targets.value) {
        const targetMap = targetMaps.get(t.key)!
        const targetRow = targetMap.get(code)
        if (targetRow) {
          const targetAudited = Number(targetRow.audited_amount) || 0
          targetValues[t.key] = targetAudited
          const amount = currentAudited - targetAudited
          const rate = targetAudited !== 0 ? amount / Math.abs(targetAudited) : null
          variances[t.key] = { amount, rate }
        } else {
          targetValues[t.key] = null
          variances[t.key] = { amount: currentAudited, rate: null }
          if (!inCurrent) onlyTarget.push(t.key)
        }
      }

      result.push({
        standard_account_code: code,
        account_name: currentRow?.account_name || '',
        current_audited: currentAudited,
        targets: targetValues,
        variances,
        onlyCurrent: inCurrent && Object.values(targetValues).every(v => v === null),
        onlyTarget,
      })
    }

    return result
  })

  function invalidateCache() {
    cache.clear()
    targetData.value.clear()
  }

  return {
    targets,
    loading,
    errors,
    joinedRows,
    loadComparisonYear,
    loadComparisonProject,
    removeTarget,
    invalidateCache,
  }
}
