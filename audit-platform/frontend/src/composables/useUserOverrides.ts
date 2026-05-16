/**
 * useUserOverrides — 用户手动覆盖保护 composable
 *
 * 追踪用户手动编辑过的预填充单元格，防止刷新取数时覆盖用户修改。
 * 数据持久化到 WorkingPaper.parsed_data.user_overrides。
 *
 * Foundation Sprint 1 Task 1.8
 */

import { ref, computed } from 'vue'

/**
 * 用户覆盖保护 composable
 */
export function useUserOverrides() {
  // key = "SheetName!CellRef"（如 "审定表!C5"）
  const userOverrides = ref<Record<string, boolean>>({})

  /**
   * 标记 cell 为用户手动修改
   */
  function markAsOverride(sheet: string, cellRef: string): void {
    const key = `${sheet}!${cellRef}`
    userOverrides.value[key] = true
  }

  /**
   * 移除 cell 的覆盖标记（恢复预填充）
   */
  function removeOverride(sheet: string, cellRef: string): void {
    const key = `${sheet}!${cellRef}`
    delete userOverrides.value[key]
  }

  /**
   * 查询 cell 是否被用户手动修改过
   */
  function isOverridden(sheet: string, cellRef: string): boolean {
    const key = `${sheet}!${cellRef}`
    return !!userOverrides.value[key]
  }

  /**
   * 序列化为 JSON 用于保存到 parsed_data.user_overrides
   */
  function serializeOverrides(): Record<string, boolean> {
    return { ...userOverrides.value }
  }

  /**
   * 从 parsed_data 恢复覆盖集合
   */
  function loadOverrides(parsedData: any): void {
    const overrides = parsedData?.user_overrides
    if (overrides && typeof overrides === 'object') {
      userOverrides.value = { ...overrides }
    } else {
      userOverrides.value = {}
    }
  }

  /**
   * 清空所有覆盖标记
   */
  function clearAll(): void {
    userOverrides.value = {}
  }

  /**
   * 获取所有被覆盖的 cell 引用列表
   */
  const overriddenCells = computed(() => Object.keys(userOverrides.value))

  /**
   * 覆盖数量
   */
  const overrideCount = computed(() => Object.keys(userOverrides.value).length)

  return {
    userOverrides,
    markAsOverride,
    removeOverride,
    isOverridden,
    serializeOverrides,
    loadOverrides,
    clearAll,
    overriddenCells,
    overrideCount,
  }
}
