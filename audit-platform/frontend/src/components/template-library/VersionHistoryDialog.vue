<!--
  VersionHistoryDialog.vue — 版本历史抽屉 [template-library-coordination Sprint 5 Task 5.2]

  需求 14.1-14.5：
  - 14.1 页面顶部版本标识 + 元信息（已在 TemplateLibraryMgmt.vue 完成）
  - 14.2 版本元信息展示（版本号 / 发布日期 / 文件总数 / 变更摘要）
  - 14.3 版本历史列表（时间倒序，从 seed_load_history 读取）
  - 14.4 每次种子加载记录时间戳和操作人
  - 14.5 版本对比仅作信息展示（非可编辑）

  数据源：GET /api/template-library-mgmt/version-info
    - version：当前版本标识
    - release_date：发布日期
    - last_seed_loads[]：最近 20 条 seed 加载记录（seed_name / loaded_at / record_count / inserted / updated / status）

  通过 props.versionInfo 接收已缓存数据避免重复 fetch（与 TemplateLibraryMgmt 主页面联动）。
  通过 props.fileCount 接收文件总数（来自 /list 端点，由父级缓存）。
-->
<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="(v: boolean) => $emit('update:modelValue', v)"
    title="模板库版本历史"
    width="780"
    :close-on-click-modal="true"
    destroy-on-close
    class="gt-vhd"
  >
    <div v-loading="loading" class="gt-vhd-body">
      <!-- ── 当前版本元信息 ── -->
      <div class="gt-vhd-meta">
        <div class="gt-vhd-meta-item">
          <span class="gt-vhd-meta-label">版本号</span>
          <span class="gt-vhd-meta-value gt-vhd-meta-version">{{ versionLabel }}</span>
        </div>
        <div class="gt-vhd-meta-item">
          <span class="gt-vhd-meta-label">发布日期</span>
          <span class="gt-vhd-meta-value gt-amt">{{ releaseDate || '—' }}</span>
        </div>
        <div class="gt-vhd-meta-item">
          <span class="gt-vhd-meta-label">文件总数</span>
          <span class="gt-vhd-meta-value gt-amt">{{ fileCount ?? '—' }}</span>
        </div>
        <div class="gt-vhd-meta-item gt-vhd-meta-item--wide">
          <span class="gt-vhd-meta-label">变更摘要</span>
          <span class="gt-vhd-meta-value gt-vhd-meta-summary">{{ changeSummary }}</span>
        </div>
      </div>

      <!-- ── 版本历史列表 ── -->
      <div class="gt-vhd-history">
        <div class="gt-vhd-history-header">
          <h4 class="gt-vhd-history-title">
            版本历史
            <el-tag size="small" type="info" effect="plain" round style="margin-left: 8px">
              <span class="gt-amt">{{ historyRows.length }}</span> 条记录
            </el-tag>
          </h4>
          <el-button size="small" :loading="loading" @click="reload" round>
            <el-icon style="margin-right: 4px"><Refresh /></el-icon>刷新
          </el-button>
        </div>

        <el-empty
          v-if="!loading && historyRows.length === 0"
          description="暂无版本历史 — 执行一键加载种子后将记录到此处"
          :image-size="80"
        />

        <el-table
          v-else
          :data="historyRows"
          size="small"
          :header-cell-style="{ background: '#f0edf5', color: '#303133', fontWeight: '600' }"
          class="gt-vhd-table"
          max-height="420"
        >
          <el-table-column prop="loaded_at_formatted" label="时间" width="170" sortable>
            <template #default="{ row }">
              <span class="gt-amt">{{ row.loaded_at_formatted }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="seed_label" label="种子模块" min-width="200">
            <template #default="{ row }">
              <span class="gt-vhd-seed-name">{{ row.seed_label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作人" width="140">
            <template #default="{ row }">
              <span class="gt-vhd-operator">{{ row.loaded_by_display || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="记录数" width="100" align="right">
            <template #default="{ row }">
              <span class="gt-amt">{{ row.record_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="新增/更新" width="120" align="right">
            <template #default="{ row }">
              <span class="gt-amt">+{{ row.inserted }}</span>
              <span class="gt-vhd-divider"> / </span>
              <span class="gt-amt">↻{{ row.updated }}</span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90" align="center">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small" effect="plain" round>
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)" round>关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { templateLibraryMgmt as P_tlm } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'

interface SeedLoadRecord {
  seed_name: string
  loaded_at: string
  loaded_by?: string | null
  record_count: number
  inserted: number
  updated: number
  status: string
}

interface VersionInfoPayload {
  version: string
  release_date: string
  last_seed_loads: SeedLoadRecord[]
}

const props = defineProps<{
  modelValue: boolean
  /** 父级已缓存的版本信息，传入则避免重复 fetch */
  versionInfo?: VersionInfoPayload | null
  /** 文件总数（来自 /list 端点，由父级缓存） */
  fileCount?: number | null
}>()

defineEmits<{
  (e: 'update:modelValue', value: boolean): void
}>()

const loading = ref(false)
const localVersionInfo = ref<VersionInfoPayload | null>(null)

// ─── 中文标签映射（与 SeedLoaderPanel.vue 对齐）─────────────────────────
const SEED_LABELS: Record<string, string> = {
  report_config: '报表配置',
  gt_wp_coding: '致同编码体系',
  wp_template_metadata: '底稿模板元数据',
  audit_report_templates: '审计报告模板',
  accounting_standards: '会计准则',
  template_sets: '底稿模板集',
  note_templates: '附注模板',
  prefill_formula_mapping: '预填充公式映射',
  cross_wp_references: '跨底稿引用规则',
}

function seedLabel(seedName: string): string {
  return SEED_LABELS[seedName] || seedName
}

const STATUS_LABELS: Record<string, string> = {
  loaded: '成功',
  partial: '部分',
  failed: '失败',
  unknown: '未知',
}
function statusLabel(s: string): string {
  return STATUS_LABELS[s] || s
}
function statusType(s: string): 'success' | 'warning' | 'danger' | 'info' {
  if (s === 'loaded') return 'success'
  if (s === 'partial') return 'warning'
  if (s === 'failed') return 'danger'
  return 'info'
}

// ─── 数据源（优先 props 传入的缓存，否则自行 fetch）───
const effectiveInfo = computed<VersionInfoPayload | null>(() => {
  return props.versionInfo ?? localVersionInfo.value
})

const versionLabel = computed(() => effectiveInfo.value?.version || '致同 2025 修订版')
const releaseDate = computed(() => effectiveInfo.value?.release_date || '')

/** 变更摘要：从最近一次 seed 加载推导（最近 24h 内变更的 seed 模块） */
const changeSummary = computed(() => {
  const loads = effectiveInfo.value?.last_seed_loads || []
  if (loads.length === 0) return '无最近加载记录'
  // 取最近一次加载时间，列出该时刻附近 ±5 分钟内的 seed 模块
  const latest = new Date(loads[0].loaded_at).getTime()
  const window = 5 * 60 * 1000
  const recent = loads.filter(r => {
    const t = new Date(r.loaded_at).getTime()
    return Math.abs(t - latest) <= window
  })
  const seedNames = Array.from(new Set(recent.map(r => seedLabel(r.seed_name))))
  return `最近加载：${seedNames.slice(0, 5).join('、')}${seedNames.length > 5 ? ` 等 ${seedNames.length} 项` : ''}`
})

const historyRows = computed(() => {
  const loads = effectiveInfo.value?.last_seed_loads || []
  return loads.map(r => ({
    ...r,
    seed_label: seedLabel(r.seed_name),
    loaded_at_formatted: formatDateTime(r.loaded_at),
    loaded_by_display: r.loaded_by ? formatUserId(r.loaded_by) : null,
  }))
})

function formatDateTime(iso: string): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
  } catch {
    return iso
  }
}

/** UUID → 短显示形式（前 8 位 + ...）；后续可接入用户名查询服务 */
function formatUserId(userId: string): string {
  if (!userId) return ''
  return userId.length > 12 ? `${userId.slice(0, 8)}…` : userId
}

async function reload() {
  loading.value = true
  try {
    const data = await api.get<VersionInfoPayload>(P_tlm.versionInfo)
    localVersionInfo.value = data || null
  } catch (e: any) {
    handleApiError(e, '加载版本历史')
  } finally {
    loading.value = false
  }
}

// 打开对话框时，如果父级未传 versionInfo 则 fetch 一次
watch(
  () => props.modelValue,
  (open) => {
    if (open && !props.versionInfo && !localVersionInfo.value) {
      reload()
    }
  },
)
</script>

<style scoped>
.gt-vhd :deep(.el-dialog__body) {
  padding: 16px 20px;
}
.gt-vhd-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 320px;
}

/* ── 当前版本元信息卡片 ── */
.gt-vhd-meta {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 14px 16px;
  background: linear-gradient(135deg, #faf9fc 0%, #f0edf5 100%);
  border-radius: 8px;
  border-left: 3px solid var(--gt-color-primary);
}
.gt-vhd-meta-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-vhd-meta-item--wide {
  grid-column: span 3;
}
.gt-vhd-meta-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-info);
}
.gt-vhd-meta-value {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-primary);
  font-weight: 600;
}
.gt-vhd-meta-version {
  color: var(--gt-color-primary);
}
.gt-vhd-meta-summary {
  font-weight: 400;
  color: var(--gt-color-text-regular);
  font-size: var(--gt-font-size-sm);
}

/* ── 历史列表 ── */
.gt-vhd-history {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gt-vhd-history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gt-vhd-history-title {
  margin: 0;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
}

.gt-vhd-table :deep(.el-table__row:hover > td) {
  background-color: var(--gt-color-primary-bg) !important;
}
.gt-vhd-seed-name {
  font-weight: 500;
  color: var(--gt-color-text-primary);
}
.gt-vhd-operator {
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
.gt-vhd-divider {
  color: var(--gt-color-text-placeholder);
  margin: 0 2px;
}

.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
</style>
