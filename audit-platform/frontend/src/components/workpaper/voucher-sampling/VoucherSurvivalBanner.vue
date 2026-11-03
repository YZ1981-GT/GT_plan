<template>
  <el-alert
    v-if="visible"
    :type="alertType"
    :closable="false"
    show-icon
    class="vsb"
    data-testid="voucher-survival-banner"
  >
    <template #title>
      <div class="vsb-main">
        <div>
          <strong>{{ title }}</strong>
          <span v-if="detail" class="vsb-detail">{{ detail }}</span>
        </div>
        <div class="vsb-actions">
          <el-tag v-if="summary" size="small" type="success" effect="plain">未变 {{ summary.unchanged }}</el-tag>
          <el-tag v-if="summary?.modified" size="small" type="danger" effect="plain">分录已改 {{ summary.modified }}</el-tag>
          <el-tag v-if="summary?.renumbered" size="small" type="warning" effect="plain">疑似重编号 {{ summary.renumbered }}</el-tag>
          <el-tag v-if="summary?.deleted" size="small" type="danger" effect="plain">凭证已删除 {{ summary.deleted }}</el-tag>
          <el-button
            v-if="activeDatasetId && supportedCount > 0"
            size="small"
            type="primary"
            plain
            :loading="checking"
            :disabled="readonly"
            data-testid="run-interim-survival"
            @click="runCheck"
          >{{ needsCheck ? '核对预审样本' : '重新核对' }}</el-button>
        </div>
      </div>
    </template>
  </el-alert>
</template>

<script setup lang="ts">
/**
 * 底稿级预审样本存续核对横幅（任务 17，需求 8）。
 *
 * 挂在 GtWpRenderer，子循环经 voucherSurvivalRegistry 提供预审行。项目在年审且有预审行时显示；
 * 当前 active 账套与行上 `_gt.sv.datasetId` 不同（或汇总不存在）时要求核对。后端按 ADR-VK-11 四步判定，
 * 本组件把结果写回全部同 lfp 行并调用每个宿主自己的 persist。缺 lfp 的预审旧行明确报数，不静默漏掉。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { AUDIT_PHASE, useProjectAuditPhase } from '@/composables/useProjectAuditPhase'
import {
  applyVoucherSurvivalResult,
  collectVoucherSurvivalRows,
  voucherSurvivalRegistryRevision,
  type SurvivalCheckWire,
} from '../composables/shared/voucherSurvivalRegistry'

interface Summary {
  check_id: string
  dataset_id: string
  total: number
  unchanged: number
  modified: number
  renumbered: number
  deleted: number
  unacked: number
}

const props = defineProps<{
  projectId: string
  workpaperId: string
  year: number | null
  readonly: boolean
}>()

const auditPhase = useProjectAuditPhase(() => props.projectId)
void auditPhase.load()
const activeDatasetId = ref<string | null>(null)
const summary = ref<Summary | null>(null)
const loadError = ref('')
const checking = ref(false)
let statusLoading = false
let reloadRequested = false

const local = computed(() => {
  void voucherSurvivalRegistryRevision.value
  return collectVoucherSurvivalRows(props.workpaperId)
})
const supportedCount = computed(() => local.value.rows.length)
const visible = computed(() => auditPhase.phase.value === AUDIT_PHASE.final && local.value.preliminaryCount > 0)
const needsCheck = computed(() => {
  const dataset = activeDatasetId.value
  if (!dataset || !summary.value) return true
  return local.value.rows.some(row => row.previous_dataset_id !== dataset)
})
const localUnacked = computed(() => {
  const dataset = activeDatasetId.value
  if (!dataset) return 0
  return local.value.rows.filter(row =>
    row.previous_dataset_id === dataset && row.previous_status !== 'unchanged' && !row.acknowledged,
  ).length
})
const changedTotal = computed(() => (summary.value?.modified ?? 0) + (summary.value?.renumbered ?? 0) + (summary.value?.deleted ?? 0))
const alertType = computed(() =>
  loadError.value || !activeDatasetId.value || local.value.unsupportedCount > 0 || localUnacked.value > 0
    ? 'warning'
    : needsCheck.value ? 'warning' : 'success',
)
const title = computed(() => {
  if (loadError.value) return '预审样本存续状态读取失败'
  if (!activeDatasetId.value) return '预审样本暂不能核对：本年度没有已激活账套'
  if (needsCheck.value) return `预审样本需在当前账套核对（${supportedCount.value} 条）`
  if (localUnacked.value > 0) return `预审样本核对发现变化，尚有 ${localUnacked.value} 条未确认`
  if (changedTotal.value > 0) return '预审样本变化均已确认'
  return '预审样本已与当前账套核对'
})
const detail = computed(() => {
  const parts: string[] = []
  if (local.value.unsupportedCount) parts.push(`${local.value.unsupportedCount} 条预审旧行缺分录指纹，无法自动核对`)
  if (loadError.value) parts.push(loadError.value)
  else if (activeDatasetId.value) parts.push(`账套版本 ${activeDatasetId.value.slice(0, 8)}`)
  return parts.join('；')
})

function unwrap(res: any): any {
  return res?.data?.data ?? res?.data ?? res
}

async function loadStatus(): Promise<void> {
  if (!props.projectId || !props.workpaperId || props.year == null || !visible.value) return
  // markLoaded / persist 可能连续 bump registry。http 的同 GET 去重会取消先发请求；这里做 single-flight，
  // 运行中再来只记一次补跑，避免控制台出现 canceled，也不让旧 catch 短暂覆盖成功结果。
  if (statusLoading) {
    reloadRequested = true
    return
  }
  statusLoading = true
  const key = `${props.projectId}|${props.workpaperId}|${props.year}`
  try {
    const res = await http.get(`/api/projects/${props.projectId}/sampling/interim-survival/status`, {
      params: { wp_id: props.workpaperId, year: props.year }, _silent: true,
    } as any)
    if (key !== `${props.projectId}|${props.workpaperId}|${props.year}`) return
    const body = unwrap(res)
    activeDatasetId.value = body?.active_dataset_id ?? null
    summary.value = body?.check ?? null
    loadError.value = ''
  } catch {
    if (key !== `${props.projectId}|${props.workpaperId}|${props.year}`) return
    loadError.value = '请稍后重试，当前未把读取失败当成“无需核对”'
  } finally {
    statusLoading = false
    if (reloadRequested) {
      reloadRequested = false
      void loadStatus()
    }
  }
}

async function runCheck(): Promise<void> {
  if (checking.value || props.readonly || props.year == null) return
  const rows = local.value.rows
  if (!rows.length) return
  checking.value = true
  try {
    const res = await http.post(`/api/projects/${props.projectId}/sampling/interim-survival`, {
      wp_id: props.workpaperId, year: props.year, rows,
    }, { _silent: true } as any)
    const result = unwrap(res) as SurvivalCheckWire
    await applyVoucherSurvivalResult(props.workpaperId, result)
    activeDatasetId.value = result.dataset_id
    summary.value = result as unknown as Summary
    loadError.value = ''
    ElMessage.success(result.unacked
      ? `核对完成：${result.unacked} 条变化待逐行确认`
      : '核对完成：预审样本在当前账套均未变化')
  } catch (err: any) {
    const detail = err?.response?.data?.detail ?? err?.response?.data?.message
    ElMessage.error(typeof detail === 'object' ? String(detail.message ?? '预审样本核对失败') : String(detail ?? '预审样本核对失败'))
  } finally {
    checking.value = false
  }
}

watch(
  () => [props.projectId, props.workpaperId, props.year, auditPhase.phase.value,
    local.value.preliminaryCount, voucherSurvivalRegistryRevision.value],
  () => { void loadStatus() },
  { immediate: true },
)
</script>

<style scoped>
.vsb {
  margin-bottom: var(--gt-space-2);
}
.vsb-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gt-space-3);
  width: 100%;
}
.vsb-detail {
  margin-left: var(--gt-space-2);
  color: var(--gt-color-text-secondary);
  font-weight: 400;
}
.vsb-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--gt-space-1);
}
</style>
