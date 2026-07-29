<template>
  <div class="gt-confirmation-fraud-risk">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-fraud-risk__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：fraud-risk-d08-v1 -->
    <template v-else>
      <!-- 看板 -->
      <FraudRiskDashboard :metrics="data.metrics.value" />

      <!-- 检查清单 -->
      <FraudRiskChecklist
        :items="data.items.value"
        :readonly="readonly"
        :is-highlighted="data.isHighlighted"
        :needs-countermeasure="data.needsCountermeasure"
        @add="handleAddItem"
        @delete="handleDeleteItem"
        @update="handleUpdateItem"
        @import="handleImport"
        @export="handleExport"
        @jump-ref="handleJumpRef"
        @auto-fill="handleAutoFill"
      />

      <!-- 汇总评价 -->
      <FraudRiskSummary
        :summary="data.summary.value"
        :readonly="readonly"
        :metrics="data.metrics.value"
        @update="handleSummaryUpdate"
        @jump-b50="handleJumpB50"
      />

      <!-- 审计结论 -->
      <FraudRiskConclusion
        :conclusion="data.conclusion.value"
        :metrics="data.metrics.value"
        :readonly="readonly"
        @update="handleConclusionUpdate"
      />

      <!-- 保存按钮 -->
      <div v-if="!readonly" class="gt-confirmation-fraud-risk__actions">
        <el-button
          type="primary"
          :disabled="!data.isDirty.value"
          @click="handleSave"
        >
          保存
        </el-button>
        <span v-if="data.isDirty.value" class="gt-confirmation-fraud-risk__dirty-hint">
          有未保存的更改
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useFraudRiskData } from './composables/useFraudRiskData'
import { useFraudSignalCollector } from '../coordination/useFraudSignalCollector'
import { filterSummaryRows, fetchWorkpaperHtmlRows, fetchConfirmationSummaryRows } from '../coordination/importFromSummary'
import type { FraudSignal } from '../coordination/useFraudSignalCollector'
import FraudRiskDashboard from './FraudRiskDashboard.vue'
import FraudRiskChecklist from './FraudRiskChecklist.vue'
import FraudRiskSummary from './FraudRiskSummary.vue'
import FraudRiskConclusion from './FraudRiskConclusion.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => {
  // 新格式或空数据都走新组件
  const d = props.htmlData
  return !d || !!d._format || Object.keys(d).length === 0
})

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useFraudRiskData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAddItem() {
  data.addItem()
}

function handleDeleteItem(rowId: string) {
  data.deleteItem(rowId)
}

function handleUpdateItem(rowId: string, field: string, value: any) {
  data.updateItem(rowId, field, value)
}

function handleSummaryUpdate(field: string, value: string) {
  ;(data.summary.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  data.isDirty.value = false
}

function handleImport() {
  // TODO: 复用 useExcelIO 批量导入自定义条目
  console.log('[GtConfirmationFraudRisk] Excel 导入')
}

function handleExport() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationFraudRisk] Excel 导出')
}

function handleJumpRef(ref: string) {
  // TODO: 跨底稿跳转（通过 useConfirmationNavigation）
  console.log('[GtConfirmationFraudRisk] 跳转索引:', ref)
}

// ─── 舞弊信号收集器 ──────────────────────────────────────────────────────────

const fraudSignals = ref<FraudSignal[]>([])
const collector = useFraudSignalCollector({ signals: fraudSignals })
const autoFillLoading = ref(false)

async function handleAutoFill() {
  if (props.readonly) return
  if (autoFillLoading.value) return // 防重复点击
  autoFillLoading.value = true
  const items = data.items.value
  const pid = props.projectId
  if (!pid) {
    ElMessage.warning('缺少项目上下文')
    return
  }

  // 循环码派生
  const cycleBase = (props.wpCode || '').split('-')[0] // D0/F0/G0/...
  let hasAnySignal = false

  // 清空临时收集器（每次重新汇集）
  fraudSignals.value = []

  // ─── D0-7 不可靠 ───────────────────────────────────────────────────────────
  try {
    const reliabilityCode = `${cycleBase}-7`
    let reliRes = await fetchWorkpaperHtmlRows(pid, reliabilityCode, 'reliability-v1')
    // 回退：X0-7 不独立存在时尝试父底稿 X0
    if (!reliRes || (!reliRes.rows.length && !reliRes.htmlData)) {
      reliRes = await fetchWorkpaperHtmlRows(pid, cycleBase, 'reliability-v1')
    }
    if (reliRes && reliRes.rows.length > 0) {
      for (const row of reliRes.rows) {
        if (row.conclusion_status === '不可靠') {
          collector.addD07Unreliable(row.confirm_index || '', row.entity_name || '')
          hasAnySignal = true
        }
      }
    }
  } catch (e) {
    console.warn('[FraudRisk] D0-7 数据不可读，跳过:', e)
  }

  // ─── D0-3 控制失败 ─────────────────────────────────────────────────────────
  try {
    const followupCode = `${cycleBase}-3`
    let fupRes = await fetchWorkpaperHtmlRows(pid, followupCode, 'confirmation-followup-v1')
    // 回退父底稿
    if (!fupRes || (!fupRes.rows.length && !fupRes.htmlData)) {
      fupRes = await fetchWorkpaperHtmlRows(pid, cycleBase, 'confirmation-followup-v1')
    }
    if (fupRes && fupRes.rows.length > 0) {
      for (const row of fupRes.rows) {
        if (row.control_conclusion === 'fail' || row.control_conclusion === '否') {
          collector.addD03ControlFailure(row.confirm_index || '', row.entity_name || '')
          hasAnySignal = true
        }
      }
    }
  } catch (e) {
    console.warn('[FraudRisk] D0-3 数据不可读，跳过:', e)
  }

  // ─── D0-1 低回函率 ─────────────────────────────────────────────────────────
  try {
    const summaryCode = `${cycleBase}-1`
    let sumRes = await fetchConfirmationSummaryRows(pid, summaryCode)
    // 回退父底稿
    if (!sumRes) {
      sumRes = await fetchConfirmationSummaryRows(pid, cycleBase)
    }
    if (sumRes && sumRes.rows.length > 0) {
      const sent = sumRes.rows.length
      const replied = sumRes.rows.filter(r => r.is_replied).length
      const rate = sent > 0 ? (replied / sent) * 100 : 100
      if (rate < 50) {
        collector.addD01LowReplyRate(rate)
        hasAnySignal = true
      }
    }
  } catch (e) {
    console.warn('[FraudRisk] D0-1 数据不可读，跳过:', e)
  }

  // ─── 汇集结果填入 D0-8 检查项（手工优先） ──────────────────────────────────
  if (hasAnySignal) {
    const d08Map = collector.exportForD08()
    for (const [itemNo, sig] of d08Map) {
      const item = items.find(i => i.seq === itemNo)
      if (item && !item.is_exist) {
        item.is_exist = '待核实'
        item.source_ref = sig.index_refs.join(',') || `${cycleBase}-*`
        item.response_note = sig.note
        item._auto_filled = true
        data.isDirty.value = true
      }
    }
    ElMessage.success(`已从上游底稿自动汇集 ${d08Map.size} 类舞弊信号，请逐项确认后修改为"是"或"否"`)
  } else {
    // fail-open 降级：无信号时用规则预填（保留原行为）
    _ruleFallbackFill(items)
  }

  // 持久化
  if (data.isDirty.value) {
    const payload = data.buildPayload()
    emit('save', payload)
  }
  autoFillLoading.value = false
}

/** 规则预填降级（原 handleAutoFill 逻辑，作为 fail-open 兜底） */
function _ruleFallbackFill(items: any[]) {
  const item7 = items.find((i: any) => i.seq === 7)
  if (item7 && !item7.is_exist) {
    item7.is_exist = '待核实'
    item7.source_ref = 'D0-7'
    item7._auto_filled = true
    data.isDirty.value = true
  }
  const item10 = items.find((i: any) => i.seq === 10)
  if (item10 && !item10.is_exist) {
    item10.is_exist = '待核实'
    item10.source_ref = 'D0-2'
    item10._auto_filled = true
    data.isDirty.value = true
  }
  const item14 = items.find((i: any) => i.seq === 14)
  if (item14 && !item14.is_exist) {
    item14.is_exist = '待核实'
    item14.source_ref = 'D0-1'
    item14._auto_filled = true
    data.isDirty.value = true
  }
  const item15 = items.find((i: any) => i.seq === 15)
  if (item15 && !item15.is_exist) {
    item15.is_exist = '待核实'
    item15.source_ref = 'D0-3'
    item15._auto_filled = true
    data.isDirty.value = true
  }
  ElMessage.success('上游底稿无可用信号，已用规则预填第 7/10/14/15 条，请逐项确认')
}

function handleJumpB50() {
  // TODO: 跳转 B50 风险评估底稿
  console.log('[GtConfirmationFraudRisk] 跳转 B50')
}
</script>

<style scoped>
.gt-confirmation-fraud-risk {
  padding: 8px 0;
}

.gt-confirmation-fraud-risk__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-fraud-risk__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-extra-light);
}

.gt-confirmation-fraud-risk__dirty-hint {
  font-size: 12px;
  color: var(--el-color-warning);
}
</style>
