<template>
  <div class="gt-formula-history">
    <!-- 筛选栏 -->
    <div class="gt-fh-filter-bar">
      <el-input
        v-model="filterRowCode"
        size="small"
        placeholder="按行次筛选..."
        clearable
        style="width: 180px;"
      />
      <el-select v-model="filterAction" size="small" clearable placeholder="操作类型" style="width: 120px;">
        <el-option label="新增" value="create" />
        <el-option label="修改" value="update" />
        <el-option label="删除" value="delete" />
        <el-option label="执行" value="execute" />
      </el-select>
      <el-button size="small" :loading="loading" @click="loadHistory">🔄 刷新</el-button>
      <span class="gt-fh-count">共 {{ filteredEntries.length }} 条记录</span>
    </div>

    <!-- 时间线 -->
    <div v-if="filteredEntries.length" class="gt-fh-timeline">
      <el-timeline>
        <el-timeline-item
          v-for="entry in filteredEntries"
          :key="entry.id"
          :timestamp="formatTime(entry.created_at)"
          :type="actionColor(entry.action)"
          placement="top"
        >
          <div class="gt-fh-entry">
            <div class="gt-fh-entry-header">
              <el-tag :type="actionTagType(entry.action)" size="small">{{ actionLabel(entry.action) }}</el-tag>
              <span class="gt-fh-row-code">{{ entry.row_code }}</span>
              <span class="gt-fh-module">{{ moduleLabel(entry.module) }}</span>
              <span v-if="operationLabel(entry.operation)" class="gt-fh-module">· {{ operationLabel(entry.operation) }}</span>
            </div>
            <div v-if="entry.action === 'update' || entry.action === 'create' || entry.action === 'delete'" class="gt-fh-entry-body">
              <div v-if="entry.old_formula" class="gt-fh-formula-diff">
                <span class="gt-fh-label">旧公式：</span>
                <code class="gt-fh-old" v-html="diffOld(entry.old_formula, entry.new_formula)"></code>
              </div>
              <div v-if="entry.new_formula" class="gt-fh-formula-diff">
                <span class="gt-fh-label">新公式：</span>
                <code class="gt-fh-new" v-html="diffNew(entry.old_formula, entry.new_formula)"></code>
              </div>
              <!-- 紧凑 diff 视图：单行显示变化（两边都有公式时才展示） -->
              <div v-if="entry.old_formula && entry.new_formula && entry.old_formula !== entry.new_formula"
                class="gt-fh-inline-diff">
                <span class="gt-fh-label">变化：</span>
                <code class="gt-fh-diff-inline" v-html="diffInline(entry.old_formula, entry.new_formula)"></code>
              </div>
            </div>
            <div v-if="entry.action === 'execute' && entry.result_value != null" class="gt-fh-entry-body">
              <span class="gt-fh-label">计算结果：</span>
              <span class="gt-fh-result">{{ entry.result_value }}</span>
            </div>
            <!-- 一键回滚按钮（仅 update/delete 且有 old_formula 时显示） -->
            <div v-if="canRollback(entry)" class="gt-fh-entry-actions">
              <el-button
                size="small"
                type="warning"
                text
                :loading="rollingBack === entry.id"
                @click="onRollback(entry)"
              >
                ↺ 一键回滚
              </el-button>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>

    <!-- 空状态 -->
    <el-empty v-else-if="!loading" description="暂无公式变更记录" />

    <!-- 加载中 -->
    <div v-if="loading" style="text-align: center; padding: 40px;">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      <p style="margin-top: 8px; color: var(--gt-color-text-placeholder);">加载中...</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { formulaAuditLog } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { useAuthStore } from '@/stores/auth'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'

const authStore = useAuthStore()

interface HistoryEntry {
  id: string
  module: string
  row_code: string
  action: string
  old_formula: string | null
  new_formula: string | null
  result_value: number | null
  trace: any[] | null
  created_at: string | null
  /** 写入方式（本项目适配 / 同步全局 / 恢复为全局 / 处理待确认 / 订阅模板 …），旧记录无 */
  operation?: string | null
  /** 服务端计算：该条目是否可回滚（需求 13.3） */
  rollbackable?: boolean
  /** 不可回滚原因 */
  rollback_blocked_reason?: string | null
  /** 服务端计算：对应公式位在本项目的当前修订号（回滚请求的 expected_version，需求 13.1） */
  current_version?: number | null
}

const props = defineProps<{
  projectId: string
  /** 审计年度；项目没填为 null / 未传 ⇒ 不加载历史、回滚提示去填年度 */
  year?: number | null
  readOnly?: boolean
}>()

const emit = defineEmits<{
  (e: 'rollback-applied', rowCode: string, formula: string): void
}>()

const loading = ref(false)
const entries = ref<HistoryEntry[]>([])
const filterRowCode = ref('')
const filterAction = ref('')
const rollingBack = ref<string | null>(null)

const filteredEntries = computed(() => {
  let result = entries.value
  if (filterRowCode.value.trim()) {
    const q = filterRowCode.value.trim().toLowerCase()
    result = result.filter(e => (e.row_code || '').toLowerCase().includes(q))
  }
  if (filterAction.value) {
    result = result.filter(e => e.action === filterAction.value)
  }
  return result
})

async function loadHistory() {
  if (!props.projectId || !props.year) return
  loading.value = true
  try {
    const data = await api.get(formulaAuditLog.list(props.projectId, props.year), {
      params: { limit: 200 },
    })
    entries.value = Array.isArray(data) ? data : []
  } catch {
    // 加载失败时显示空列表（需求 15.3：失败不提示成功）
    entries.value = []
  } finally {
    loading.value = false
  }
}

/**
 * 可回滚的角色（与后端 `rollback_formula` 的
 * `require_role(["admin", "partner", "manager"])` **逐值对齐**）。
 *
 * 🔴 2026-09-28：后端该端点原先**零鉴权**（任何人可改全局 `report_config` 公式），
 * 补 `require_role` 后成了权限收紧。前端若不同步门控，无权角色仍能看到按钮、
 * 点了必 403 —— 「能点但必失败」是坏体验，也让用户以为系统坏了。
 * 两侧任一改动都必须同步另一侧，守卫 `formulaHistoryRollbackGate.spec.ts`。
 */
const ROLLBACK_ROLES = ['admin', 'partner', 'signing_partner', 'manager'] as const

const canRollbackByRole = computed(() =>
  !props.readOnly && (ROLLBACK_ROLES as readonly string[]).includes(authStore.user?.role || ''),
)

function canRollback(entry: HistoryEntry): boolean {
  if (!canRollbackByRole.value) return false
  // 需求 13.3：只看服务端计算的 rollbackable
  return entry.rollbackable === true
}

async function onRollback(entry: HistoryEntry) {
  // 项目没填审计年度：先说明，不让用户确认一个发不出去的回滚
  const year = props.year
  if (year == null) {
    ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
    return
  }
  // ADR-FHIC-10：回滚目标由服务端从 old_definition 快照读取，条目没有展示用的 old_formula 也能回滚
  // （原先 `if (!entry.old_formula) return` 会把这类条目挡在确认框之前）
  const oldFormula = entry.old_formula || '（服务端快照恢复）'
  // 需求 13.1：回滚必带当前修订号（后端缺版本恒 428）；列表没给出版本就不发请求
  const expectedVersion = entry.current_version
  if (expectedVersion == null) {
    ElMessage.warning('无法确定该公式的当前版本，请刷新后重试')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将行次 "${entry.row_code}" 的公式回滚为历史版本？\n\n旧公式：${oldFormula}\n\n此操作将覆盖当前公式。`,
      '一键回滚确认',
      { confirmButtonText: '确认回滚', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }

  rollingBack.value = entry.id
  try {
    // ADR-FHIC-10：不传 target_formula，回滚目标由服务端从 old_definition 读取
    // 年度用上面收窄过的局部 `year`（props.year 是 number | null，直接传会是类型错）
    const resp = await api.post(formulaAuditLog.rollback(props.projectId, year), {
      row_code: entry.row_code,
      module: entry.module,
      source_log_id: entry.id,
      expected_version: expectedVersion,
    })
    // 按状态码判成功（需求 15.3）
    if (resp && resp.ok) {
      ElMessage.success(`已回滚行次 "${entry.row_code}" 的公式`)
      emit('rollback-applied', entry.row_code, resp.restored_formula || oldFormula)
    }
    await loadHistory()
  } catch (e: any) {
    const status = e?.response?.status || e?.status
    if (status === 428) {
      ElMessage.warning('回滚需要提供版本号，请刷新后重试')
    } else if (status === 409) {
      ElMessage.warning('版本冲突，公式已被修改，请刷新后重试')
    } else {
      handleApiError(e, '回滚失败')
    }
    await loadHistory()
  } finally {
    rollingBack.value = null
  }
}

// ── 字符级 diff（提取到 formulaDiff.ts，供单测覆盖）──────────────────────────
import { diffOld, diffNew, diffInline } from './formulaDiff'

function formatTime(ts: string | null): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return ts
  }
}

function actionLabel(action: string): string {
  const map: Record<string, string> = {
    create: '新增', update: '修改', delete: '删除', execute: '执行',
  }
  return map[action] || action
}

function actionTagType(action: string): 'success' | 'warning' | 'info' | 'danger' | undefined {
  const map: Record<string, 'success' | 'warning' | 'info' | 'danger'> = {
    create: 'success', update: 'warning', delete: 'danger', execute: 'info',
  }
  return map[action] || undefined
}

function actionColor(action: string): 'primary' | 'success' | 'warning' | 'danger' | 'info' | undefined {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'danger' | 'info'> = {
    create: 'success', update: 'warning', delete: 'danger', execute: 'info',
  }
  return map[action] || undefined
}

function moduleLabel(module: string): string {
  const map: Record<string, string> = {
    report: '报表', consol: '合并', note: '附注', wp: '底稿',
    tb_detail: '试算表科目明细', cross_check: '表间审核', consol_note: '合并附注', push: '公式推送',
  }
  return map[module] || module
}

/** 写入方式（spec formula-global-settings-sync 写的审计才有；旧记录返回空串不显示）。 */
function operationLabel(op?: string | null): string {
  const map: Record<string, string> = {
    adapt: '本项目适配', sync_global: '同步全局', restore: '恢复为全局', resolve_pending: '处理待确认',
    push: '他项目应用', rollback: '历史回滚', template_subscribe: '订阅模板', template_unsubscribe: '退订模板',
    template_sync: '模板更新',
  }
  return op ? (map[op] || op) : ''
}

// 组件挂载时自动加载
onMounted(() => {
  loadHistory()
})

// 监听 projectId/year 变化重新加载
watch(() => [props.projectId, props.year], () => {
  loadHistory()
})
</script>

<style scoped>
.gt-formula-history {
  padding: 8px;
  height: 100%;
  overflow-y: auto;
}
.gt-fh-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
}
.gt-fh-count {
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
  margin-left: auto;
}
.gt-fh-timeline {
  max-height: calc(100vh - 400px);
  overflow-y: auto;
  padding: 0 8px;
}
.gt-fh-entry {
  padding: 4px 0;
}
.gt-fh-entry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.gt-fh-row-code {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-text-regular);
}
.gt-fh-module {
  font-size: 11px;
  color: var(--gt-color-text-placeholder);
  background: var(--el-fill-color-light);
  padding: 1px 6px;
  border-radius: 3px;
}
.gt-fh-entry-body {
  margin-top: 4px;
  padding-left: 4px;
}
.gt-fh-formula-diff {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 2px;
}
.gt-fh-label {
  font-size: 11px;
  color: var(--gt-color-text-secondary);
  white-space: nowrap;
}
.gt-fh-old {
  font-size: 12px;
  color: var(--gt-color-danger);
  text-decoration: line-through;
  word-break: break-all;
}
.gt-fh-new {
  font-size: 12px;
  color: var(--gt-color-success);
  word-break: break-all;
}
.gt-fh-result {
  font-size: 12px;
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-fh-entry-actions {
  margin-top: 4px;
}
/* 字符级 diff 高亮 */
:deep(.gt-fh-del) {
  background: #fdd;
  color: #c0392b;
  text-decoration: line-through;
  border-radius: 2px;
  padding: 0 1px;
}
:deep(.gt-fh-add) {
  background: #dfd;
  color: #27ae60;
  border-radius: 2px;
  padding: 0 1px;
}
.gt-fh-inline-diff {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-top: 4px;
  padding: 4px 8px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  border: 1px solid var(--gt-color-border, #ebeef5);
}
.gt-fh-diff-inline {
  font-size: 12px;
  word-break: break-all;
  color: var(--gt-color-text-regular);
}
</style>
