/**
 * useVersionTrail — 底稿版本链核心 composable
 *
 * Spec: .kiro/specs/workpaper-version-trail/
 * Task: 5.1
 *
 * 职责：
 * - 定义 TypeScript 接口：SnapshotType、SnapshotMeta、DiffItem、DiffResult、UseVersionTrailOptions
 * - 实现响应式状态：versions, totalCount, currentPage, loading, drawerVisible, diffResult, diffLoading, selectedVersions
 * - loadVersions(page?) — GET /versions?page=&page_size=20
 * - createSnapshot(description?) — POST /versions {snapshot_type:'manual', description}
 * - compareDiff(versionAId, versionBId) — POST /versions/compare
 * - rollback(versionId) — ElMessageBox.confirm 确认弹窗 → POST /versions/{vid}/rollback
 * - canRollback computed（基于用户角色：现场经理+）
 * - hasMore computed（currentPage * 20 < totalCount）
 *
 * Requirements: 3.1, 3.5, 4.1, 5.1, 5.5, 7.1, 7.3
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import { useRoleContextStore } from '@/stores/roleContext'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SnapshotType =
  | 'manual'
  | 'auto_sampling'
  | 'auto_import'
  | 'review_sign'
  | 'status_change'
  | 'rollback'

export interface SnapshotMeta {
  id: string
  snapshotType: SnapshotType
  description: string | null
  changeSummary: string | null
  itemCount: number
  dataSizeBytes: number
  userId: string
  userName: string | null
  createdAt: string
}

export interface DiffItem {
  itemId: string
  changeType: 'added' | 'deleted' | 'modified'
  fieldName?: string  // conclusion/remark/wp_ref
  valueA?: string | null
  valueB?: string | null
}

export interface DiffResult {
  added: DiffItem[]
  deleted: DiffItem[]
  modified: DiffItem[]
  unchangedCount: number
  summary: string
}

export interface UseVersionTrailOptions {
  projectId: Ref<string>
  workpaperId: Ref<string>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PAGE_SIZE = 20

/** 允许回滚的角色列表 */
const ROLLBACK_ALLOWED_ROLES = ['admin', 'partner', 'manager', 'qc']

// ─── Composable ──────────────────────────────────────────────────────────────

export function useVersionTrail(options: UseVersionTrailOptions) {
  const { projectId, workpaperId } = options

  // ─── Stores ─────────────────────────────────────────────────────────────
  const authStore = useAuthStore()
  const roleContextStore = useRoleContextStore()

  // ─── API 路径构造 ────────────────────────────────────────────────────────

  function basePath(): string {
    return `/api/projects/${projectId.value}/workpapers/${workpaperId.value}/versions`
  }

  // ─── Reactive State ─────────────────────────────────────────────────────

  const versions = ref<SnapshotMeta[]>([])
  const totalCount = ref(0)
  const currentPage = ref(1)
  const loading = ref(false)
  const drawerVisible = ref(false)
  const diffResult = ref<DiffResult | null>(null)
  const diffLoading = ref(false)
  const selectedVersions = ref<[string | null, string | null]>([null, null])

  // ─── Computed ───────────────────────────────────────────────────────────

  /** 基于用户角色判断是否允许回滚（现场经理及以上） */
  const canRollback: ComputedRef<boolean> = computed(() => {
    // 优先取 roleContext 的 effectiveRole
    const effectiveRole = roleContextStore.effectiveRole
    if (effectiveRole) {
      return ROLLBACK_ALLOWED_ROLES.includes(effectiveRole)
    }
    // 降级到 authStore 的系统角色
    const systemRole = authStore.user?.role ?? ''
    return ROLLBACK_ALLOWED_ROLES.includes(systemRole)
  })

  /** 是否有更多分页数据 */
  const hasMore: ComputedRef<boolean> = computed(() => {
    return currentPage.value * PAGE_SIZE < totalCount.value
  })

  // ─── loadVersions ──────────────────────────────────────────────────────

  async function loadVersions(page?: number): Promise<void> {
    const targetPage = page ?? 1
    loading.value = true
    try {
      const res = await http.get(basePath(), {
        params: { page: targetPage, page_size: PAGE_SIZE },
      })

      const data = res.data as any
      const items: any[] = data?.items ?? []
      const total: number = data?.total ?? 0

      versions.value = items.map(mapSnapshotMeta)
      totalCount.value = total
      currentPage.value = targetPage
    } catch (err: any) {
      ElMessage.error(err?.message || '加载版本历史失败')
    } finally {
      loading.value = false
    }
  }

  // ─── createSnapshot ────────────────────────────────────────────────────

  /**
   * 生成版本快照
   *
   * @param description 快照描述（含方法学要素时可携带方法/间隔/样本量/seed）
   * @param options.snapshotType 快照类型，默认 'manual'；抽凭自动填充用 'auto_sampling'
   * @param options.silent 静默模式：不弹成功提示、不刷新列表（供 fire-and-forget 场景）
   *
   * 执行人（user_id/user_name）与时间（created_at）由后端在快照记录中补全，
   * 无需前端传入。
   */
  async function createSnapshot(
    description?: string,
    options?: { snapshotType?: SnapshotType; silent?: boolean },
  ): Promise<void> {
    const snapshotType: SnapshotType = options?.snapshotType ?? 'manual'
    const silent = options?.silent ?? false
    loading.value = true
    try {
      await http.post(basePath(), {
        snapshot_type: snapshotType,
        description: description || null,
      })

      if (!silent) {
        ElMessage.success('版本快照已保存')
        // 刷新列表到第一页
        await loadVersions(1)
      }
    } catch (err: any) {
      if (!silent) ElMessage.error(err?.message || '保存版本失败')
    } finally {
      loading.value = false
    }
  }

  // ─── compareDiff ───────────────────────────────────────────────────────

  async function compareDiff(versionAId: string, versionBId: string): Promise<void> {
    diffLoading.value = true
    diffResult.value = null
    try {
      const res = await http.post(`${basePath()}/compare`, {
        version_a_id: versionAId,
        version_b_id: versionBId,
      })

      const data = res.data as any
      diffResult.value = {
        added: (data.added ?? []).map(mapDiffItem),
        deleted: (data.deleted ?? []).map(mapDiffItem),
        modified: (data.modified ?? []).map(mapDiffItem),
        unchangedCount: data.unchanged_count ?? data.unchangedCount ?? 0,
        summary: data.summary ?? '',
      }
    } catch (err: any) {
      ElMessage.error(err?.message || '版本对比失败')
    } finally {
      diffLoading.value = false
    }
  }

  // ─── rollback ──────────────────────────────────────────────────────────

  async function rollback(versionId: string): Promise<void> {
    // 找到目标版本以显示时间
    const targetVersion = versions.value.find(v => v.id === versionId)
    const targetTime = targetVersion?.createdAt ?? '未知时间'

    try {
      await ElMessageBox.confirm(
        `确定回滚到 ${targetTime} 的版本吗？此操作将覆盖当前底稿数据，无法撤销。`,
        '确认回滚',
        {
          confirmButtonText: '确定回滚',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch {
      // 用户取消
      return
    }

    loading.value = true
    try {
      await http.post(`${basePath()}/${versionId}/rollback`)

      ElMessage.success('回滚成功，底稿数据已恢复')

      // 刷新列表
      await loadVersions(1)
    } catch (err: any) {
      ElMessage.error(err?.message || '回滚失败')
    } finally {
      loading.value = false
    }
  }

  // ─── Drawer 控制 ───────────────────────────────────────────────────────

  function openDrawer(): void {
    drawerVisible.value = true
    // 打开时自动加载第一页
    loadVersions(1)
  }

  function closeDrawer(): void {
    drawerVisible.value = false
    // 重置对比状态
    diffResult.value = null
    selectedVersions.value = [null, null]
  }

  // ─── 辅助映射函数 ──────────────────────────────────────────────────────

  function mapSnapshotMeta(item: any): SnapshotMeta {
    return {
      id: item.id,
      snapshotType: item.snapshot_type ?? item.snapshotType ?? 'manual',
      description: item.description ?? null,
      changeSummary: item.change_summary ?? item.changeSummary ?? null,
      itemCount: item.item_count ?? item.itemCount ?? 0,
      dataSizeBytes: item.data_size_bytes ?? item.dataSizeBytes ?? 0,
      userId: item.user_id ?? item.userId ?? '',
      userName: item.user_name ?? item.userName ?? null,
      createdAt: item.created_at ?? item.createdAt ?? '',
    }
  }

  function mapDiffItem(item: any): DiffItem {
    return {
      itemId: item.item_id ?? item.itemId ?? '',
      changeType: item.change_type ?? item.changeType ?? 'modified',
      fieldName: item.field_name ?? item.fieldName ?? undefined,
      valueA: item.value_a ?? item.valueA ?? null,
      valueB: item.value_b ?? item.valueB ?? null,
    }
  }

  // ─── Return ─────────────────────────────────────────────────────────────

  return {
    // 状态
    versions,
    totalCount,
    currentPage,
    loading,
    drawerVisible,
    diffResult,
    diffLoading,
    selectedVersions,

    // 操作
    loadVersions,
    createSnapshot,
    compareDiff,
    rollback,
    openDrawer,
    closeDrawer,

    // 计算属性
    canRollback,
    hasMore,
  }
}

export default useVersionTrail
