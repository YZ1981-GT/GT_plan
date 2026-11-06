<template>
  <div v-if="view && view.applicable" class="cpe" data-testid="combined-phase-evaluation">
    <div class="cpe-head">
      <span class="cpe-title">全年合并评价</span>
      <el-tag v-if="view.mode" size="small" type="info" effect="plain">{{ FINAL_POPULATION_MODE_LABELS[view.mode] }}</el-tag>
      <el-tag v-if="c && !c.scopeConsistent" size="small" type="warning" effect="plain">仅供参考</el-tag>
    </div>
    <el-alert
      v-if="!c"
      type="warning"
      :closable="false"
      show-icon
      :title="view.reason"
      data-testid="combined-unavailable"
    />
    <template v-else>
      <div class="cpe-grid">
        <div class="cpe-item">
          <span class="cpe-label">{{ interimLabel }}</span>
          <span class="cpe-value" data-testid="combined-interim">{{ interimText }}</span>
        </div>
        <div class="cpe-item">
          <span class="cpe-label">年审推断错报 / 错报上限</span>
          <span class="cpe-value">{{ c.finalProjected }} / {{ c.finalUpperLimit }} 元</span>
        </div>
        <div class="cpe-item">
          <span class="cpe-label">全年推断错报</span>
          <span class="cpe-value" data-testid="combined-projected">{{ c.projected }} 元</span>
        </div>
        <div class="cpe-item">
          <span class="cpe-label">全年错报上限</span>
          <span class="cpe-value cpe-value--emphasis" data-testid="combined-upper">{{ c.upperLimit }} 元</span>
        </div>
      </div>
      <el-table v-if="view.interim.length" :data="view.interim" size="small" border class="cpe-table">
        <el-table-column label="预审批次" width="110">
          <template #default="{ row }">第 {{ row.seq }} 个</template>
        </el-table-column>
        <!-- 固定按元显示：与上方分量、抽样评价卡片的「元」一致，不随全局万元偏好换算 -->
        <template v-if="view.mode === 'remaining'">
          <el-table-column label="推断错报（元）" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.projected" unit="yuan" /></template>
          </el-table-column>
          <el-table-column label="错报上限（元）" align="right">
            <template #default="{ row }"><GtAmountCell :value="row.upperLimit" unit="yuan" /></template>
          </el-table-column>
        </template>
        <el-table-column v-else label="样本实际错报合计（元）" align="right">
          <template #default="{ row }"><GtAmountCell :value="row.sampleErrorTotal" unit="yuan" /></template>
        </el-table-column>
      </el-table>
      <el-alert
        :type="alertType"
        :closable="false"
        show-icon
        :title="c.conclusionMessage"
        data-testid="combined-conclusion"
      />
    </template>
  </div>
  <el-alert
    v-else-if="loadFailed"
    type="warning"
    :closable="false"
    show-icon
    title="全年合并评价读取失败，请稍后重新打开抽凭面板"
    data-testid="combined-load-failed"
  />
</template>

<script setup lang="ts">
/**
 * 全年合并评价面板（spec voucher-identity-writeback-and-audit-phase 任务 16，需求 7.5 / 7.6，ADR-VK-10）。
 *
 * 挂在抽凭引擎「错报推断与总体结论」卡片里：评价卡片显示的是年审批次（带口径）时，展示该批次的全年合并评价；
 * 预审批次、抽凭时没有预审工作的年审批次不显示（后端 applicable=false）。数字与结论全取后端
 * `GET /sampling/phase-evaluation`，与写进批次评价、抽样记录结论的是同一份；算不出时显示后端给的原因。
 */
import { computed, ref, watch } from 'vue'
import GtAmountCell from '@/components/common/GtAmountCell.vue'
import { FINAL_POPULATION_MODE_LABELS } from '../composables/useFinalPopulationMode'
import { loadPhaseEvaluation, type PhaseEvaluationView } from '../composables/samplingPhaseEvaluation'

const props = defineProps<{
  projectId: string
  workpaperId: string
  /** 评价卡片当前显示的批次；null 时后端取本底稿最近一次带年审口径的批次（刚回填、还没单独保存过评价） */
  logId: string | null
  /** 变化即重读（评价保存时间、回填批次号） */
  refreshKey: string
  /** 卡片上有落库的批次才读：预览阶段还没有批次 */
  enabled: boolean
}>()

const view = ref<PhaseEvaluationView | null>(null)
const loadFailed = ref(false)
let latest = 0

const c = computed(() => view.value?.combined ?? null)
const interimLabel = computed(() =>
  view.value?.mode === 'remaining' ? '预审各批推断错报 / 错报上限' : '预审样本实际错报合计',
)
const interimText = computed(() => {
  const v = c.value
  if (!v) return ''
  return v.mode === 'remaining' ? `${v.interimComponent} / ${v.interimUpperComponent} 元` : `${v.interimComponent} 元`
})
const alertType = computed(() => {
  const code = c.value?.conclusionCode
  return code === 'acceptable' ? 'success' : code === 'not_acceptable' ? 'error' : 'info'
})

async function load(): Promise<void> {
  const mine = ++latest
  if (!props.enabled || !props.projectId || !props.workpaperId) {
    view.value = null
    loadFailed.value = false
    return
  }
  try {
    const next = await loadPhaseEvaluation(props.projectId, props.workpaperId, props.logId)
    if (mine !== latest) return // 晚到的旧响应不覆盖新的
    view.value = next
    loadFailed.value = false
  } catch {
    if (mine !== latest) return
    view.value = null
    loadFailed.value = true
  }
}

watch(
  () => [props.enabled, props.projectId, props.workpaperId, props.logId, props.refreshKey],
  () => { void load() },
  { immediate: true },
)
</script>

<style scoped>
.cpe {
  margin-top: var(--gt-space-3);
  padding: var(--gt-space-2) var(--gt-space-3);
  border: 1px solid var(--gt-color-border-lighter);
  border-radius: var(--gt-radius-sm);
}
.cpe-head {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-2);
}
.cpe-title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.cpe-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--gt-space-3) var(--gt-space-6);
  margin-bottom: var(--gt-space-2);
}
.cpe-item {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-1);
  min-width: 140px;
}
.cpe-label {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-secondary);
}
.cpe-value {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.cpe-value--emphasis {
  font-size: var(--gt-font-size-base);
}
.cpe-table {
  margin-bottom: var(--gt-space-2);
}
</style>
