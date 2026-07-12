<script setup lang="ts">
/**
 * D2DerecognitionOverview — 保理终止确认逐份判断总览（D2-12）
 *
 * 面向复核人：卡片式（单体，每份合同一张卡）+ 矩阵式（汇总，所有合同横向对比）双视图，
 * 一屏看清全部保理合同的主要信息、9 步判断状态与终止确认结论。
 * 每份合同独立走 9 步判断向导（附件OCR+知识库+AI辅助+人工确认+回填），判断按 rowId 分别存储。
 */
import { ref, computed, inject, onMounted, onBeforeUnmount } from 'vue'
import D2DerecognitionWizard from './D2DerecognitionWizard.vue'
import {
  STEP_DEFS, parseJudgmentStore, summarizeContract,
  type ContractJudgment, type StepJudgment,
} from '../composables/useD2Derecognition'
import type { FactoringRow } from '../composables/useD2PledgeCheck'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  factoringRows: FactoringRow[]
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const STORAGE_KEY = 'D2-derecognition'

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const viewMode = ref<'card' | 'matrix'>('card')
const store = ref<Record<string, ContractJudgment>>({})

// ─── 加载 + 旧数据迁移（持久化） ────────────────────────────────────────────
function loadStore(): void {
  const parsed = parseJudgmentStore(props.allResponses.get(STORAGE_KEY)?.remark)
  let migrated = false
  // 旧单份判断迁移到第一份保理合同（首份未判断时归入，随后持久化清除 __legacy__）
  if (parsed.__legacy__) {
    const first = props.factoringRows[0]
    if (first && !parsed[first.rowId]) parsed[first.rowId] = parsed.__legacy__
    delete parsed.__legacy__
    migrated = true
  }
  store.value = parsed
  if (migrated && !props.isReadonly) persistStore()
}

function persistStore(): void {
  const remark = JSON.stringify({ byContract: store.value, updatedAt: new Date().toISOString() })
  const item = { item_id: STORAGE_KEY, conclusion: null, remark }
  props.allResponses.set(STORAGE_KEY, item)
  try {
    window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items: [item] } }))
  } catch { /* silent */ }
}

function onSaveItems(e: Event): void {
  const items = (e as CustomEvent).detail?.items || []
  if (Array.isArray(items) && items.some((i: any) => i?.item_id === STORAGE_KEY)) loadStore()
}

onMounted(() => {
  loadStore()
  window.addEventListener('d2:save-items', onSaveItems)
})
onBeforeUnmount(() => window.removeEventListener('d2:save-items', onSaveItems))

// ─── 展示辅助 ────────────────────────────────────────────────────────────────
const STEP_META = STEP_DEFS.map((d, i) => ({ stepId: d.stepId, short: `S${i + 1}`, title: d.title, note: d.note }))

function contractLabel(row: FactoringRow): string {
  return row.debtorName || row.factor || '(未命名保理合同)'
}
function summaryOf(row: FactoringRow) {
  return summarizeContract(store.value[row.rowId])
}
function judgmentColor(j: StepJudgment): string {
  if (j === '符合') return '#67c23a'
  if (j === '不符合') return '#f56c6c'
  if (j === '不适用') return '#c0c4cc'
  return '#ebeef5'
}
function judgmentShort(j: StepJudgment): string {
  if (j === '符合') return '符'
  if (j === '不符合') return '否'
  if (j === '不适用') return '—'
  return ''
}
function conclusionTagType(c: string): 'success' | 'danger' | 'warning' | 'info' {
  if (c === '终止确认') return 'success'
  if (c.startsWith('不终止')) return 'danger'
  if (c.startsWith('按继续涉入')) return 'warning'
  return 'info'
}

// ─── 汇总统计 ────────────────────────────────────────────────────────────────
const stats = computed(() => {
  const rows = props.factoringRows
  let judged = 0, derecog = 0, notDerecog = 0, involve = 0
  for (const r of rows) {
    const s = summaryOf(r)
    if (s.answered > 0 || s.conclusion) judged++
    if (s.conclusion === '终止确认') derecog++
    else if (s.conclusion.startsWith('不终止')) notDerecog++
    else if (s.conclusion.startsWith('按继续涉入')) involve++
  }
  return { total: rows.length, judged, derecog, notDerecog, involve }
})

// ─── 向导 ────────────────────────────────────────────────────────────────────
const wizardVisible = ref(false)
const activeContractId = ref('')
const activeContractLabel = ref('')
const activeContext = ref<Record<string, unknown>>({})

function openWizard(row: FactoringRow): void {
  activeContractId.value = row.rowId
  activeContractLabel.value = contractLabel(row)
  activeContext.value = {
    debtorName: row.debtorName,
    factoringAmount: row.factoringAmount,
    factor: row.factor,
    factoringDate: row.factoringDate,
    autoDerecognition: row.derecognition,
    riskTransferred: row.riskTransferred,
    controlRetained: row.controlRetained,
  }
  wizardVisible.value = true
}

function onApplied(): void {
  loadStore()
}
</script>

<template>
  <div class="d2-derec-overview">
    <div class="ov-header">
      <div class="ov-title">
        <span class="ov-title-text">保理终止确认逐份判断（CAS 23 · 9 步）</span>
        <el-tag size="small" type="info" effect="plain">共 {{ stats.total }} 份</el-tag>
        <el-tag size="small" type="primary" effect="plain">已判断 {{ stats.judged }}</el-tag>
        <el-tag v-if="stats.derecog" size="small" type="success" effect="light">终止确认 {{ stats.derecog }}</el-tag>
        <el-tag v-if="stats.notDerecog" size="small" type="danger" effect="light">不终止 {{ stats.notDerecog }}</el-tag>
        <el-tag v-if="stats.involve" size="small" type="warning" effect="light">继续涉入 {{ stats.involve }}</el-tag>
      </div>
      <el-segmented
        v-model="viewMode"
        :options="[{ label: '🃏 卡片视图', value: 'card' }, { label: '▦ 矩阵视图', value: 'matrix' }]"
        size="small"
      />
    </div>

    <el-empty v-if="!factoringRows.length" description="暂无保理合同，请先在上方保理表格中添加" :image-size="60" />

    <!-- 卡片视图（单体） -->
    <div v-else-if="viewMode === 'card'" class="ov-cards">
      <div v-for="row in factoringRows" :key="row.rowId" class="derec-card">
        <div class="card-top">
          <div class="card-debtor" :title="contractLabel(row)">{{ contractLabel(row) }}</div>
          <el-tag
            :type="conclusionTagType(summaryOf(row).conclusion)"
            size="small"
            effect="dark"
          >{{ summaryOf(row).conclusion || '未判断' }}</el-tag>
        </div>
        <div class="card-info">
          <span>保理金额：<b>{{ displayPrefs.fmtAmount(row.factoringAmount) }}</b> 元</span>
          <span>保理商：{{ row.factor || '—' }}</span>
          <span>保理日期：{{ row.factoringDate || '—' }}</span>
          <span>自动判定：
            <el-tag :type="row.derecognition === '终止确认' ? 'success' : 'warning'" size="small" effect="plain">{{ row.derecognition || '—' }}</el-tag>
          </span>
        </div>
        <div class="card-steps">
          <div class="steps-label">9 步判断
            <span class="steps-progress">{{ summaryOf(row).answered }}/{{ summaryOf(row).total }}</span>
          </div>
          <div class="steps-dots">
            <el-tooltip
              v-for="(j, i) in summaryOf(row).stepJudgments"
              :key="i"
              :content="`${STEP_META[i].title}：${j || '未判断'}`"
              placement="top"
            >
              <span class="step-dot" :style="{ background: judgmentColor(j) }">{{ judgmentShort(j) }}</span>
            </el-tooltip>
          </div>
          <el-progress
            :percentage="Math.round((summaryOf(row).answered / summaryOf(row).total) * 100)"
            :stroke-width="6"
            :show-text="false"
            style="margin-top:6px"
          />
        </div>
        <div class="card-actions">
          <el-button size="small" type="primary" plain @click="openWizard(row)">
            {{ summaryOf(row).answered > 0 ? '继续/编辑判断' : '开始 9 步判断' }} ▶
          </el-button>
        </div>
      </div>
    </div>

    <!-- 矩阵视图（汇总） -->
    <div v-else class="ov-matrix">
      <el-table :data="factoringRows" size="small" border stripe :row-key="'rowId'">
        <el-table-column label="债务人" min-width="140" fixed>
          <template #default="{ row }">
            <span class="mx-debtor">{{ contractLabel(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="保理金额" width="120" align="right">
          <template #default="{ row }">{{ displayPrefs.fmtAmount(row.factoringAmount) }}</template>
        </el-table-column>
        <el-table-column label="保理商" min-width="110">
          <template #default="{ row }">{{ row.factor || '—' }}</template>
        </el-table-column>
        <el-table-column
          v-for="(meta, i) in STEP_META"
          :key="meta.stepId"
          :label="meta.short"
          width="46"
          align="center"
        >
          <template #header>
            <el-tooltip :content="`${meta.title}：${meta.note}`" placement="top">
              <span class="mx-step-head">{{ meta.short }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="`${meta.title}：${summaryOf(row).stepJudgments[i] || '未判断'}`" placement="top">
              <span class="mx-dot" :style="{ background: judgmentColor(summaryOf(row).stepJudgments[i]) }">{{ judgmentShort(summaryOf(row).stepJudgments[i]) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="70" align="center">
          <template #default="{ row }">{{ summaryOf(row).answered }}/{{ summaryOf(row).total }}</template>
        </el-table-column>
        <el-table-column label="终止确认结论" min-width="160">
          <template #default="{ row }">
            <el-tag :type="conclusionTagType(summaryOf(row).conclusion)" size="small">{{ summaryOf(row).conclusion || '未判断' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="96" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="openWizard(row)">
              {{ summaryOf(row).answered > 0 ? '编辑' : '判断' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="mx-legend">
        图例：
        <span class="lg"><i style="background:#67c23a" />符合</span>
        <span class="lg"><i style="background:#f56c6c" />不符合</span>
        <span class="lg"><i style="background:#c0c4cc" />不适用</span>
        <span class="lg"><i style="background:#ebeef5" />未判断</span>
      </div>
    </div>

    <!-- 9 步判断向导（按合同复用） -->
    <D2DerecognitionWizard
      v-model="wizardVisible"
      :wp-id="wpId"
      :project-id="projectId"
      :all-responses="allResponses"
      :is-readonly="isReadonly"
      :contract-id="activeContractId"
      :contract-label="activeContractLabel"
      :factoring-context="activeContext"
      @applied="onApplied"
    />
  </div>
</template>

<style scoped>
.d2-derec-overview { margin-top: 16px; }
.ov-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.ov-title { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ov-title-text { font-size: 14px; font-weight: 600; color: #303133; }

/* 卡片视图 */
.ov-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.derec-card {
  border: 1px solid #ebeef5; border-radius: 8px; padding: 12px 14px; background: #fff;
  box-shadow: 0 1px 4px rgba(0,0,0,0.04); transition: box-shadow .2s;
}
.derec-card:hover { box-shadow: 0 3px 12px rgba(0,0,0,0.08); }
.card-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; }
.card-debtor { font-size: 14px; font-weight: 600; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-info { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: #606266; margin-bottom: 10px; }
.card-info b { color: #303133; }
.card-steps { border-top: 1px dashed #ebeef5; padding-top: 8px; }
.steps-label { font-size: 12px; color: #909399; margin-bottom: 6px; display: flex; justify-content: space-between; }
.steps-progress { font-weight: 600; color: #409eff; }
.steps-dots { display: flex; gap: 4px; flex-wrap: wrap; }
.step-dot {
  width: 20px; height: 20px; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center;
  font-size: 11px; color: #fff; font-weight: 600; border: 1px solid rgba(0,0,0,0.04);
}
.card-actions { margin-top: 10px; text-align: right; }

/* 矩阵视图 */
.ov-matrix .mx-debtor { font-weight: 600; }
.mx-step-head { cursor: help; font-weight: 600; }
.mx-dot {
  display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
  border-radius: 4px; color: #fff; font-size: 11px; font-weight: 600; border: 1px solid rgba(0,0,0,0.04);
}
.mx-legend { margin-top: 8px; font-size: 12px; color: #909399; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.mx-legend .lg { display: inline-flex; align-items: center; gap: 4px; }
.mx-legend .lg i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
</style>
