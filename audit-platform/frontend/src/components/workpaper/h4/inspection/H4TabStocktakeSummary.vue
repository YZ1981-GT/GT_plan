<template>
  <div class="h4-tab-stocktake-summary">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：参照固定资产监盘小结范式，汇总工程物资现场盘点结果，证实存在性与完整性，并衔接减值关注。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H4-6B" :context-project-id="projectId" />
        <el-tag size="small" type="info">抽盘 {{ checkStats.total }} 项</el-tag>
        <el-tag size="small" :type="checkStats.varianceCount > 0 ? 'danger' : 'success'">
          差异 {{ checkStats.varianceCount }}
        </el-tag>
        <el-tag size="small" :type="checkStats.concernCount > 0 ? 'warning' : 'info'">
          关注 {{ checkStats.concernCount }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="emit('navigate-sheet', 'H4-6A')">← H4-6A 计划</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H4-6')">H4-6 检查表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H4-7')">H4-7 减值</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="onSync">从 H4-6 回填</el-button>
        <el-button size="small" type="default" link @click="openReview('H4-6B')">💬 复核</el-button>
      </div>
    </div>

    <el-tag v-if="summary.lastAutoSyncAt" size="small" type="info">
      已回填 {{ summary.lastAutoSyncAt.slice(0, 19).replace('T', ' ') }}
    </el-tag>

    <ItemAttachment
      v-if="projectId && wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-key="H4-6B"
      :item-index="0"
      accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx,.mp4,.mov"
    />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>〇、抽盘结果仪表板（联动 H4-6）</span>
          <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H4-6')">打开检查表</el-button>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="6"><div class="stat-box"><div class="stat-label">抽盘总数</div><div class="stat-value">{{ checkStats.total }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box success"><div class="stat-label">账实相符</div><div class="stat-value">{{ checkStats.matchCount }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box warning"><div class="stat-label">盘盈</div><div class="stat-value">{{ checkStats.surplusCount }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box danger"><div class="stat-label">盘亏</div><div class="stat-value">{{ checkStats.deficitCount }}</div></div></el-col>
      </el-row>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>一、资产负债表日</span></template>
      <el-input
        :model-value="summary.balanceSheetDate"
        :disabled="isReadonly"
        placeholder="YYYY-MM-DD"
        @update:model-value="(v: string) => updateSummary('balanceSheetDate', v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>二、盘前检查</span></template>
      <el-input
        :model-value="summary.preCountCheck"
        type="textarea"
        :rows="2"
        :disabled="isReadonly"
        placeholder="盘点前账面与仓管记录核对、截止性安排等…"
        @update:model-value="(v: string) => updateSummary('preCountCheck', v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>三、人员与时间</span></template>
      <el-input
        :model-value="summary.staffAndTime"
        type="textarea"
        :rows="2"
        :disabled="isReadonly"
        placeholder="地点、时间、企业人员、监盘人员…"
        @update:model-value="(v: string) => updateSummary('staffAndTime', v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>四、现场抽盘情况</span></template>
      <el-input
        :model-value="summary.walkthroughNote"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="双向抽盘执行情况、三数量核对要点…"
        @update:model-value="(v: string) => updateSummary('walkthroughNote', v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>五、总体核对与覆盖率</span></template>
      <el-input
        :model-value="summary.overallReconcile"
        type="textarea"
        :rows="2"
        :disabled="isReadonly"
        @update:model-value="(v: string) => updateSummary('overallReconcile', v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>六、异常与跟进</span></template>
      <el-form label-width="80px" size="small">
        <el-form-item label="异常说明">
          <el-input
            :model-value="summary.abnormalNote"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            @update:model-value="(v: string) => updateSummary('abnormalNote', v)"
          />
        </el-form-item>
        <el-form-item label="后续跟进">
          <el-input
            :model-value="summary.followUp"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            @update:model-value="(v: string) => updateSummary('followUp', v)"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>七、监盘小结结论</span></template>
      <el-input
        :model-value="summary.summaryConclusion"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="就本节审计目标是否实现发表结论…"
        @update:model-value="(v: string) => updateSummary('summaryConclusion', v)"
      />
    </el-card>

    <details class="hint">
      <summary>编制提示</summary>
      <ul>
        <li>优先点击「从 H4-6 回填」，再手工补充盘前检查与资产负债表日。</li>
        <li>品质异常/盘亏应在 H4-6 推送至 H4-7，并在跟进段交叉引用。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useH4StocktakePlan } from '../../composables/useH4StocktakePlan'
import { calcStocktakeStats, normalizeCheckRow } from '../../composables/h4StocktakeCheckModel'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const {
  summary, updateSummary, syncSummaryFromCheck,
} = useH4StocktakePlan({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses') as any,
})

const isReadonly = computed(() => props.isReadonly)
const projectId = computed(() => props.projectId)
const wpId = computed(() => props.wpId)

const checkStats = computed(() => {
  const item = props.allResponses.get('H4-6-rows')
  const raw = item?.remark
  let rows: any[] = []
  if (raw) {
    try {
      const p = typeof raw === 'string' ? JSON.parse(raw) : raw
      rows = Array.isArray(p) ? p.map((r, i) => normalizeCheckRow(r, i)) : []
    } catch { /* ignore */ }
  }
  return calcStocktakeStats(rows)
})

function onSync() {
  const r = syncSummaryFromCheck()
  ElMessage.success(r.message)
}
function openReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.h4-tab-stocktake-summary { padding: 16px; font-size: var(--wp-font-size, 13px); display: flex; flex-direction: column; gap: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.block-card { margin: 0; }
.section-title { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.stat-box {
  background: var(--el-fill-color-light); border-radius: 6px; padding: 12px; text-align: center;
}
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-value { font-size: 20px; font-weight: 650; margin-top: 4px; }
.stat-box.success .stat-value { color: var(--el-color-success); }
.stat-box.warning .stat-value { color: var(--el-color-warning); }
.stat-box.danger .stat-value { color: var(--el-color-danger); }
.hint { font-size: 12px; color: var(--el-text-color-secondary); }
.hint summary { cursor: pointer; font-weight: 500; }
.hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.7; }
</style>
