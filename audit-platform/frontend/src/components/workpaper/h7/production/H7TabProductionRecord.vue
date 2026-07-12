<template>
  <div class="h7-tab-production-record">
    <el-alert v-if="!embedded" type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：核查生产性生物资产的产出记录（产蛋/产奶/割胶/收获果实等），评价资产的生产能力与产量合理性，关注产量异常波动是否反映减值迹象（CAS 5《生物资产》）。
      </template>
    </el-alert>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            产量记录（H7 独有）— {{ rows.length }}项
            <GtIndexChip value="wp:H7-15" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
            <el-tag v-if="warnCount > 0" size="small" type="warning" class="row-tag">波动预警 {{ warnCount }}</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-14-prod')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-block">
        生产性生物资产以"产出"为核心特征。产量记录用于评估资产生产能力：产量持续下降（本期较上期变动 &lt; −30%）可能表明资产老化或存在减值迹象，应结合 H7-15 减值测算综合判断。
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetName" label="生物资产" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="persistRows" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="product" label="产出品" width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.product" size="small" filterable allow-create default-first-option @change="persistRows">
              <el-option v-for="p in PRODUCT_OPTIONS" :key="p" :label="p" :value="p" />
            </el-select>
            <span v-else>{{ row.product }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unit" label="计量单位" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" placeholder="吨/枚/升/kg" @change="persistRows" />
            <span v-else>{{ row.unit }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="currentOutput" label="本期产量" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentOutput" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtNum(row.currentOutput) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorOutput" label="上期产量" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.priorOutput" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtNum(row.priorOutput) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="产量变动率" min-width="110" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-warn': isWarn(row) }" title="=(本期产量-上期产量)/上期产量×100%">
              {{ fmtRate(changeRate(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="unitYield" label="单产/头均" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unitYield" size="small" placeholder="如 300枚/羽·年" @change="persistRows" />
            <span v-else>{{ row.unitYield }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="异常说明/关注点" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persistRows" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增产量记录</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>产量分析说明</span>
          <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录产量趋势分析、异常波动原因及对资产减值的影响判断" @blur="persist('H7-14-prod-note', auditNote)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>产量变动率 = (本期产量 − 上期产量) / 上期产量 × 100%；|变动率| &gt; 30% 触发黄色预警。</li>
        <li>产量大幅下降是生产性生物资产减值的重要迹象，应联动 H7-15 减值测算表评估。</li>
        <li>单产指标（如每羽产蛋数、每头产奶量、每亩产果量）可用于横向对比行业水平判断合理性。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7ProductionRecord } from '../../composables/useH7ProductionRecord'
import { calcChangeRate } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean; embedded?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<((section: string, ctx: string, existing: string) => Promise<string>) | null>('generateAiText', null)

const allResponsesRef = computed(() => props.allResponses)
const prod = useH7ProductionRecord(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const PRODUCT_OPTIONS = ['禽蛋', '鲜奶', '天然橡胶（胶乳）', '水果', '茶叶', '种苗', '仔畜', '其他']

interface Row {
  rowId: string
  assetName: string
  product: string
  unit: string
  currentOutput: number
  priorOutput: number
  unitYield: string
  remark: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')

function changeRate(r: Row): number { return calcChangeRate(Number(r.currentOutput) || 0, Number(r.priorOutput) || 0) }
function isWarn(r: Row): boolean { return (Number(r.priorOutput) || 0) > 0 && Math.abs(changeRate(r)) > 30 }
const warnCount = computed(() => rows.value.filter((r) => isWarn(r)).length)

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetName: raw.assetName ?? '',
    product: raw.product ?? '',
    unit: raw.unit ?? '',
    currentOutput: Number(raw.currentOutput) || 0,
    priorOutput: Number(raw.priorOutput) || 0,
    unitYield: raw.unitYield ?? '',
    remark: raw.remark ?? '',
  }
}

function seed(): void {
  const raw = prod.getString('H7-14-prod-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = prod.getString('H7-14-prod-note')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-14-prod-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入生物资产名称', '新增产量记录', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(normalize({ assetName: value })); persistRows() }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
async function handleAi(): Promise<void> {
  if (!generateAiText) return
  const ctx = `产量记录 ${rows.value.length} 项，其中产量波动超 30% 的有 ${warnCount.value} 项。`
  const text = await generateAiText('h7-production', ctx, auditNote.value)
  if (text) { auditNote.value = text; persist('H7-14-prod-note', auditNote.value) }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtNum(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}
function fmtRate(v: number): string { return `${v.toFixed(2)}%` }
</script>

<style scoped>
.h7-tab-production-record { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.methodology-block { padding: 10px 14px; background: #fffbe6; border-left: 3px solid #e6a23c; border-radius: 4px; margin-bottom: 16px; font-size: 12px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.calc-cell.has-warn { color: var(--el-color-warning); font-weight: 600; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
