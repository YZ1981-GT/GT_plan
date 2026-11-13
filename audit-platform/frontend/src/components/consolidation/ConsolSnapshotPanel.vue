<template>
  <div class="gt-consol-snapshot" data-testid="consol-snapshot-panel">
    <!-- 工具栏：刷新 / 诊断快照 / 签字锁定 -->
    <div class="gt-snap-toolbar">
      <div class="gt-snap-toolbar-left">
        <el-button size="small" :loading="listLoading" @click="loadList">🔄 刷新</el-button>
        <span v-if="year == null" class="gt-snap-hint" data-testid="snap-no-year">
          未设置审计年度，请先在项目口径中设置年度
        </span>
      </div>
      <div class="gt-snap-toolbar-right">
        <el-tooltip :content="createDisabledReason" placement="bottom" :disabled="!createDisabledReason">
          <span>
            <el-button
              size="small"
              :loading="creatingManual"
              :disabled="!!createDisabledReason"
              data-testid="snap-create-manual"
              @click="onCreateManual"
            >📸 创建诊断快照</el-button>
          </span>
        </el-tooltip>
        <el-tooltip :content="signDisabledReason" placement="bottom" :disabled="!signDisabledReason">
          <span>
            <el-button
              size="small"
              type="primary"
              :loading="signing"
              :disabled="!!signDisabledReason"
              data-testid="snap-sign-lock"
              @click="onSignLock"
            >🔏 签字并锁定</el-button>
          </span>
        </el-tooltip>
      </div>
    </div>

    <!-- 诊断快照：允许 partial（分片采集失败不阻断）；签字快照 fail-closed，不会 partial -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="gt-snap-note"
      title="诊断快照用于留痕排查，允许部分分片缺失；签字并锁定会校验完整性与就绪度，任一不满足即拒绝，并在通过后冻结合并工作区为只读。"
    />

    <!-- 列表加载错误（保留上次成功数据） -->
    <el-alert
      v-if="listError"
      type="error"
      :closable="true"
      show-icon
      class="gt-snap-error"
      :title="listError"
      data-testid="snap-list-error"
      @close="listError = ''"
    />

    <el-table
      v-loading="listLoading"
      :data="snapshots"
      border
      size="small"
      max-height="56vh"
      style="width: 100%"
      :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }"
      :cell-style="{ padding: '4px 8px', fontSize: '12px' }"
      data-testid="snap-table"
    >
      <el-table-column type="index" label="序号" width="52" align="center" />
      <el-table-column label="创建时间" min-width="160">
        <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="年度" width="70" align="center">
        <template #default="{ row }">{{ row.year }}</template>
      </el-table-column>
      <el-table-column label="类型" width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.locked ? 'success' : 'info'" size="small" effect="plain">
            {{ triggerLabel(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="完整性" width="120" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.partial" type="warning" size="small" effect="plain" :title="failedSourcesText(row)">
            部分缺失（{{ row.failed_sources.length }}）
          </el-tag>
          <el-tag v-else-if="row.manifest_version === 2" size="small" effect="plain">完整（v2）</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">{{ formatLabel(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="运行 / 版本" min-width="200">
        <template #default="{ row }">
          <div class="gt-snap-refs">
            <span v-if="row.operation_ref && row.operation_ref.operation_id" :title="row.operation_ref.operation_id">
              运行 {{ shortId(row.operation_ref.operation_id) }}<span v-if="row.operation_ref.revision != null"> · 修订 {{ row.operation_ref.revision }}</span>
            </span>
            <span v-else class="gt-snap-muted">无运行引用</span>
            <span v-if="row.version_ref && row.version_ref.digest" class="gt-snap-muted" :title="row.version_ref.digest">
              版本 {{ shortId(row.version_ref.digest) }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="根 hash" min-width="130">
        <template #default="{ row }">
          <span class="gt-snap-hash" :title="row.root_hash || ''">{{ row.root_hash ? shortId(row.root_hash) : '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" :loading="busyId === row.id && busyAction === 'restore'" @click="onCheckIntegrity(row)">完整性校验</el-button>
          <el-button link type="primary" size="small" :loading="busyId === row.id && busyAction === 'compare'" @click="onCompare(row)">对比当前</el-button>
          <el-button link type="primary" size="small" :loading="busyId === row.id && busyAction === 'download'" @click="onDownload(row)">下载</el-button>
        </template>
      </el-table-column>

      <template #empty>
        <el-empty :description="listLoading ? '加载中…' : '暂无签字快照'" />
      </template>
    </el-table>

    <!-- 完整性校验结果弹窗 -->
    <el-dialog v-model="integrityVisible" title="快照完整性校验" width="560px" append-to-body destroy-on-close>
      <div v-loading="integrityLoading" style="min-height: 100px">
        <template v-if="integrityResult">
          <el-result
            :icon="integrityResult.hash_valid ? 'success' : 'warning'"
            :title="integrityResult.hash_valid ? '完整性校验通过' : '完整性校验未通过'"
            :sub-title="integrityResult.hash_valid
              ? '逐分片与根 hash 全部匹配，快照未被篡改。'
              : (integrityResult.legacy ? '旧格式快照（无法逐分片校验）。' : '分片或根 hash 不匹配，快照可能已被篡改或损坏。')"
          />
          <ul class="gt-snap-integrity-detail">
            <li>根 hash：<span class="gt-snap-hash">{{ integrityResult.hash || '—' }}</span></li>
            <li v-if="integrityResult.root_valid != null">根 hash 校验：{{ integrityResult.root_valid ? '通过' : '不通过' }}</li>
            <li v-if="integrityResult.shard_mismatches && integrityResult.shard_mismatches.length" class="gt-snap-bad">
              不匹配分片：{{ integrityResult.shard_mismatches.map(shardLabel).join('、') }}
            </li>
            <li>锁定状态：{{ integrityResult.locked ? '已锁定（只读）' : '未锁定' }}</li>
          </ul>
        </template>
        <el-empty v-else-if="!integrityLoading" description="无校验结果" />
      </div>
    </el-dialog>

    <!-- 签字时 vs 当前对比弹窗 -->
    <el-dialog v-model="compareVisible" title="签字时合并数 vs 当前合并数" width="720px" top="6vh" append-to-body destroy-on-close>
      <div v-loading="compareLoading" style="min-height: 120px">
        <template v-if="compareResult">
          <el-alert
            :type="compareResult.changed_count ? 'warning' : 'success'"
            :closable="false"
            show-icon
            class="gt-snap-compare-summary"
            :title="compareResult.changed_count
              ? `签字后有 ${compareResult.changed_count} 个科目的合并数发生变化`
              : '签字后合并数未发生变化'"
          />
          <el-table
            :data="compareRows"
            border
            size="small"
            max-height="48vh"
            style="width: 100%; margin-top: 10px"
            :header-cell-style="{ background: '#f0edf5', fontSize: '12px' }"
            :cell-style="{ padding: '2px 8px', fontSize: '12px' }"
          >
            <el-table-column prop="account_code" label="科目" width="130" />
            <el-table-column label="签字时" align="right" min-width="140">
              <template #default="{ row }"><GtAmountCell :value="row.snapshot_amount" /></template>
            </el-table-column>
            <el-table-column label="当前" align="right" min-width="140">
              <template #default="{ row }"><GtAmountCell :value="row.current_amount" /></template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.changed" type="warning" size="small" effect="plain">已变化</el-tag>
                <span v-else class="gt-snap-muted">一致</span>
              </template>
            </el-table-column>
          </el-table>
          <el-checkbox v-model="showChangedOnly" size="small" style="margin-top: 8px">只看已变化科目</el-checkbox>
        </template>
        <el-empty v-else-if="!compareLoading" description="无对比结果" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import {
  compareConsolSnapshot,
  createConsolSnapshot,
  downloadConsolSnapshot,
  listConsolSnapshots,
  restoreConsolSnapshot,
  type ConsolSnapshotCompareResult,
  type ConsolSnapshotListItem,
  type ConsolSnapshotRejection,
  type ConsolSnapshotRestoreResult,
} from '@/services/consolidationApi'

const props = defineProps<{
  projectId: string
  year: number | null
  /** 工作区只读原因（归档 / 锁定 / 无权限 / 锁状态未知）；非空 = 不能发起签字锁定 */
  readonlyReason?: string
}>()

const emit = defineEmits<{
  /** 签字锁定成功后通知父页刷新锁状态与 readiness */
  (e: 'locked'): void
  /** 创建任意快照后通知父页（readiness 的 lifecycle 域可能变化） */
  (e: 'created'): void
}>()

const snapshots = ref<ConsolSnapshotListItem[]>([])
const listLoading = ref(false)
const listError = ref('')
const creatingManual = ref(false)
const signing = ref(false)

const busyId = ref<string | null>(null)
const busyAction = ref<'restore' | 'compare' | 'download' | null>(null)

const integrityVisible = ref(false)
const integrityLoading = ref(false)
const integrityResult = ref<ConsolSnapshotRestoreResult | null>(null)

const compareVisible = ref(false)
const compareLoading = ref(false)
const compareResult = ref<ConsolSnapshotCompareResult | null>(null)
const showChangedOnly = ref(false)

const compareRows = computed(() => {
  const rows = compareResult.value?.by_account ?? []
  return showChangedOnly.value ? rows.filter((r) => r.changed) : rows
})

/** 创建诊断快照禁用原因（需要年度 + 编辑权限，但不受锁定阻拦：诊断快照不写业务数据） */
const createDisabledReason = computed(() => {
  if (props.year == null) return '未设置审计年度'
  if (props.readonlyReason && props.readonlyReason.includes('归档')) return props.readonlyReason
  if (props.readonlyReason && props.readonlyReason.includes('权限')) return props.readonlyReason
  return ''
})

/** 签字锁定禁用原因（任何只读原因都不能签字；年度必须有） */
const signDisabledReason = computed(() => {
  if (props.year == null) return '未设置审计年度'
  if (props.readonlyReason) return props.readonlyReason
  return ''
})

const SHARD_LABELS: Record<string, string> = {
  tree: '企业树',
  worksheet_data: '工作表数据',
  entries: '抵销分录',
  worksheet_calc: '差额计算',
  trial: '合并试算',
  report: '合并报表',
  consol_notes: '合并附注',
  mappings: '映射规则',
  formulas: '公式版本',
  lifecycle: '生命周期',
  artifact: '不可变产物',
}

function shardLabel(key: string): string {
  return SHARD_LABELS[key] ?? key
}

function triggerLabel(row: ConsolSnapshotListItem): string {
  if (row.locked) return '签字锁定'
  return '诊断快照'
}

function formatLabel(row: ConsolSnapshotListItem): string {
  if (row.format === 'manifest-v2') return '完整（v2）'
  if (row.format === 'gzip+base64') return '旧格式（v1）'
  return '旧空壳'
}

function failedSourcesText(row: ConsolSnapshotListItem): string {
  if (!row.failed_sources.length) return ''
  return '缺失分片：' + row.failed_sources.map(shardLabel).join('、')
}

function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 10 ? `${value.slice(0, 8)}…` : value
}

function fmtTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

async function loadList() {
  if (!props.projectId) { snapshots.value = []; return }
  listLoading.value = true
  try {
    snapshots.value = await listConsolSnapshots(props.projectId)
    listError.value = ''
  } catch (e: any) {
    // 保留上次成功数据，只提示错误
    listError.value = e?.response?.data?.message || e?.message || '快照列表加载失败，请稍后重试'
  } finally {
    listLoading.value = false
  }
}

async function onCreateManual() {
  if (createDisabledReason.value || creatingManual.value) return
  creatingManual.value = true
  try {
    await createConsolSnapshot(props.projectId, { year: props.year, reason: 'manual' })
    ElMessage.success('已创建诊断快照')
    emit('created')
    await loadList()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || e?.message || '创建诊断快照失败')
  } finally {
    creatingManual.value = false
  }
}

async function onSignLock() {
  if (signDisabledReason.value || signing.value) return
  try {
    await ElMessageBox.confirm(
      '签字并锁定后，合并工作区将冻结为只读，且会写入签字记录。确认当前合并结果已复核无误？',
      '签字并锁定',
      { confirmButtonText: '确认签字锁定', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  signing.value = true
  try {
    await createConsolSnapshot(props.projectId, { year: props.year, reason: 'sign' })
    ElMessage.success('签字成功，合并工作区已锁定')
    emit('created')
    emit('locked')
    await loadList()
  } catch (e: any) {
    const status = e?.response?.status
    const detail = e?.response?.data?.detail as ConsolSnapshotRejection | undefined
    if (status === 409 && detail?.failures?.length) {
      // fail-closed 拒绝：逐条列明原因
      ElMessageBox.alert(
        detail.failures.map((f) => `· ${f.message}`).join('\n'),
        '签字锁定被拒绝（完整性 / 就绪度未满足）',
        { confirmButtonText: '我知道了', type: 'error' },
      )
    } else {
      ElMessage.error(detail?.message || e?.response?.data?.message || e?.message || '签字锁定失败')
    }
  } finally {
    signing.value = false
  }
}

async function onCheckIntegrity(row: ConsolSnapshotListItem) {
  integrityVisible.value = true
  integrityResult.value = null
  integrityLoading.value = true
  busyId.value = row.id
  busyAction.value = 'restore'
  try {
    integrityResult.value = await restoreConsolSnapshot(props.projectId, row.id)
  } catch (e: any) {
    integrityVisible.value = false
    ElMessage.error(e?.response?.data?.message || e?.message || '完整性校验失败')
  } finally {
    integrityLoading.value = false
    busyId.value = null
    busyAction.value = null
  }
}

async function onCompare(row: ConsolSnapshotListItem) {
  compareVisible.value = true
  compareResult.value = null
  showChangedOnly.value = false
  compareLoading.value = true
  busyId.value = row.id
  busyAction.value = 'compare'
  try {
    compareResult.value = await compareConsolSnapshot(props.projectId, row.id)
  } catch (e: any) {
    compareVisible.value = false
    ElMessage.error(e?.response?.data?.message || e?.message || '对比失败')
  } finally {
    compareLoading.value = false
    busyId.value = null
    busyAction.value = null
  }
}

async function onDownload(row: ConsolSnapshotListItem) {
  busyId.value = row.id
  busyAction.value = 'download'
  try {
    await downloadConsolSnapshot(props.projectId, row.id, row.year)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.message || e?.message || '下载失败')
  } finally {
    busyId.value = null
    busyAction.value = null
  }
}

watch(
  () => [props.projectId, props.year] as const,
  () => { void loadList() },
  { immediate: true },
)

defineExpose({ loadList })
</script>

<style scoped>
.gt-consol-snapshot {
  padding: 4px 0;
}
.gt-snap-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; flex-wrap: wrap; margin-bottom: 10px;
}
.gt-snap-toolbar-left { display: flex; align-items: center; gap: 10px; }
.gt-snap-toolbar-right { display: flex; align-items: center; gap: 8px; }
.gt-snap-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-warning, #e6a23c); }
.gt-snap-note { margin-bottom: 10px; }
.gt-snap-error { margin-bottom: 10px; }
.gt-snap-refs { display: flex; flex-direction: column; gap: 2px; }
.gt-snap-muted { color: var(--gt-color-text-placeholder, #c0c4cc); }
.gt-snap-hash { font-family: var(--gt-font-mono, monospace); font-size: var(--gt-font-size-xs); }
.gt-snap-integrity-detail {
  list-style: none; padding: 0; margin: 12px 0 0; font-size: var(--gt-font-size-sm);
}
.gt-snap-integrity-detail li { padding: 3px 0; }
.gt-snap-bad { color: var(--gt-color-danger, #f56c6c); }
.gt-snap-compare-summary { margin-top: 4px; }
</style>
