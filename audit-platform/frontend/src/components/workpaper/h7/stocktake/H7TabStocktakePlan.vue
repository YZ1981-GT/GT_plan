<template>
  <div class="h7-tab-stocktake-plan">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：制定生产性生物资产监盘计划，合理安排时间、地点、范围与样本，确保对活体生物资产（畜禽/林木/水产）实施有效的实地监盘（CAS 1311《对存货监盘的审计程序》参照适用）。
      </template>
    </el-alert>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 确定盘点时间、地点、生物资产范围</div>
        <div class="guide-step"><span class="step-num">②</span> 确定盘点方法（清点/称重/估算）与抽样标准</div>
        <div class="guide-step"><span class="step-num">③</span> 安排人员（观察员/点数员/兽医或农技专家）</div>
        <div class="guide-step"><span class="step-num">④</span> 编制时间安排并明确标识核对方式（耳标/树牌）</div>
      </div>
    </div>

    <el-card shadow="never" class="plan-card">
      <template #header>
        <div class="section-title">
          <span>一、监盘基本信息 <GtIndexChip value="wp:H7-9" /></span>
          <el-button size="small" type="default" link @click="handleReview('H7-8-basic')">💬 复核</el-button>
        </div>
      </template>
      <el-form :model="planInfo" label-width="110px" size="small">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="盘点日期">
              <el-date-picker v-model="planInfo.stocktakeDate" type="date" value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%" @change="persistPlan" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点地点">
              <el-input v-model="planInfo.location" :disabled="isReadonly" placeholder="如：养殖场/林场/鱼塘" @change="persistPlan" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="参与人员">
              <el-input v-model="planInfo.participants" :disabled="isReadonly" placeholder="盘点人/观察员/兽医/农技专家" @change="persistPlan" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="盘点方法">
              <el-select v-model="planInfo.method" :disabled="isReadonly" style="width:100%" @change="persistPlan">
                <el-option v-for="m in METHOD_OPTIONS" :key="m" :label="m" :value="m" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="计量方式">
              <el-select v-model="planInfo.measureWay" :disabled="isReadonly" style="width:100%" @change="persistPlan">
                <el-option v-for="w in MEASURE_OPTIONS" :key="w" :label="w" :value="w" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="标识核对">
              <el-input v-model="planInfo.identityCheck" :disabled="isReadonly" placeholder="耳标/芯片/树牌/网箱编号" @change="persistPlan" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="盘点范围">
          <el-input v-model="planInfo.scope" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" :disabled="isReadonly" placeholder="说明盘点涵盖的生物资产类别/数量/金额范围..." @change="persistPlan" />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="plan-card">
      <template #header>
        <div class="section-title">
          <span>二、样本选取标准（{{ samples.length }} 项）</span>
          <el-button size="small" type="primary" @click="handleAddSample" :disabled="isReadonly">+ 新增</el-button>
        </div>
      </template>
      <el-table :data="samples" border stripe size="small">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column prop="category" label="资产分类" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="persistSamples" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="criteria" label="选取标准" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.criteria" size="small" @change="persistSamples" />
            <span v-else>{{ row.criteria }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sampleSize" label="样本量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.sampleSize" :controls="false" size="small" @change="persistSamples" />
            <span v-else>{{ row.sampleSize }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="coverageAmount" label="金额覆盖" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.coverageAmount" :controls="false" size="small" @change="persistSamples" />
            <span v-else class="amount-cell">{{ fmtAmt(row.coverageAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="coverageRate" label="覆盖率(%)" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.coverageRate" :controls="false" :precision="1" size="small" @change="persistSamples" />
            <span v-else class="calc-cell">{{ row.coverageRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="removeSample(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="plan-card">
      <template #header><span>三、时间安排</span></template>
      <el-input v-model="schedule" type="textarea" :autosize="{ minRows: 3, maxRows: 6 }" :disabled="isReadonly" placeholder="具体时间安排（如：8:00集合→8:30分区清点→称重→标识核对→17:00汇总）" @change="persist('H7-8-schedule', schedule)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>盘点日尽量选择资产负债表日或临近日；活体资产注意周转（出栏/出售）导致的时点差异。</li>
        <li>抽样盘点金额覆盖率建议 ≥ 70%；对价值高、易流失的资产提高样本比例。</li>
        <li>活体生物资产需清点数量（头/株/尾）并辅以称重、估算及标识（耳标/树牌）核对。</li>
        <li>完成计划后进入 H7-9 盘点检查执行现场监盘。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, inject, onMounted, toRef } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Stocktake } from '../../composables/useH7Stocktake'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const stk = useH7Stocktake(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const METHOD_OPTIONS = ['全面盘点', '抽样盘点', '账实核对']
const MEASURE_OPTIONS = ['清点数量', '称重估算', '抽样折算', '产量倒推']

const planInfo = reactive({ stocktakeDate: '', location: '', participants: '', method: '抽样盘点', measureWay: '清点数量', identityCheck: '', scope: '' })
const schedule = ref('')

interface Sample { rowId: string; category: string; criteria: string; sampleSize: number; coverageAmount: number; coverageRate: number }
const samples = ref<Sample[]>([])

function normalizeSample(raw: any): Sample {
  return {
    rowId: raw.rowId ?? `s-${Math.random().toString(36).slice(2, 9)}`,
    category: raw.category ?? '',
    criteria: raw.criteria ?? '',
    sampleSize: Number(raw.sampleSize) || 0,
    coverageAmount: Number(raw.coverageAmount) || 0,
    coverageRate: Number(raw.coverageRate) || 0,
  }
}

function seed(): void {
  const rawPlan = stk.getString('H7-8-plan')
  if (rawPlan) { try { Object.assign(planInfo, JSON.parse(rawPlan)) } catch { /* ignore */ } }
  const rawSamples = stk.getString('H7-8-samples')
  if (rawSamples) { try { const p = JSON.parse(rawSamples); if (Array.isArray(p)) samples.value = p.map(normalizeSample) } catch { /* ignore */ } }
  schedule.value = stk.getString('H7-8-schedule')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistPlan(): void { persist('H7-8-plan', { ...planInfo }) }
function persistSamples(): void { persist('H7-8-samples', samples.value) }

function handleAddSample(): void { samples.value.push(normalizeSample({})); persistSamples() }
function removeSample(rowId: string): void {
  const i = samples.value.findIndex((s) => s.rowId === rowId)
  if (i >= 0) { samples.value.splice(i, 1); persistSamples() }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-stocktake-plan { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.plan-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
