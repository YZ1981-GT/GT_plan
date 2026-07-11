<template>
  <div class="h7-tab-impairment">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：检查成本模式下生产性生物资产减值迹象判断与减值测算的恰当性，验证减值损失计算准确并已恰当核算（CAS 5《生物资产》第二十一条 / CAS 8《资产减值》）。
      </template>
    </el-alert>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-15 减值测算（本期补提 {{ fmtAmt(totalAdditional) }}）
            <GtIndexChip value="wp:H7-16" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
            <el-button size="small" type="default" link @click="handleReview('H7-15')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="summary-row">
        <span>减值损失合计：{{ fmtAmt(totalLoss) }}</span>
        <span :class="{ 'text-danger': totalAdditional > 0 }">本期补提合计：{{ fmtAmt(totalAdditional) }}</span>
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetGroup" label="资产/资产组" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetGroup" size="small" @change="persistRows" />
            <span v-else>{{ row.assetGroup }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentSign" label="减值迹象" width="130">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.impairmentSign" size="small" filterable allow-create default-first-option @change="persistRows">
              <el-option v-for="s in SIGN_OPTIONS" :key="s" :label="s" :value="s" />
            </el-select>
            <span v-else>{{ row.impairmentSign }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookValue" label="账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="recoverableAmount" label="可收回金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.recoverableAmount" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.recoverableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值损失" min-width="110" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-loss': loss(row) > 0 }" title="=max(0, 账面价值-可收回金额)">{{ fmtAmt(loss(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="priorImpairment" label="已确认减值" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.priorImpairment" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.priorImpairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期补提" min-width="110" align="right">
          <template #default="{ row }">
            <span class="calc-cell" :class="{ 'has-loss': additional(row) > 0 }" title="=max(0, 减值损失-已确认减值)">{{ fmtAmt(additional(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="结论" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.conclusion" size="small" @change="persistRows" />
            <span v-else>{{ row.conclusion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="56" align="center" v-if="!isReadonly">
          <template #default="{ row }"><el-button type="danger" link size="small" @click="removeRow(row.rowId)">删除</el-button></template>
        </el-table-column>
      </el-table>

      <div class="action-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增减值测算项</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAi"><el-icon><MagicStick /></el-icon> AI说明</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录减值迹象识别、可收回金额取值依据与减值损失核算" @blur="persist('H7-15-note', auditNote)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>减值损失 = max(0, 账面价值 − 可收回金额)；可收回金额详见 H7-16 可收回金额测试表。</li>
        <li>本期补提 = max(0, 减值损失 − 已确认减值)。</li>
        <li>成熟生产性生物资产的减值损失一经确认，在以后会计期间不得转回（CAS 8）。</li>
        <li>减值迹象可结合 H7 产量记录（产量大幅下降）、市场价格下跌、资产老化等综合判断。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Impairment } from '../../composables/useH7Impairment'
import { calcSubtotal } from '../../composables/useH7FormulaEngine'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<((section: string, ctx: string, existing: string) => Promise<string>) | null>('generateAiText', null)

const allResponsesRef = computed(() => props.allResponses)
const impair = useH7Impairment(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const SIGN_OPTIONS = ['产量持续下降', '市场价格大幅下跌', '资产老化/病害', '技术淘汰', '无减值迹象', '其他']

interface Row {
  rowId: string
  assetGroup: string
  impairmentSign: string
  bookValue: number
  recoverableAmount: number
  priorImpairment: number
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')

function loss(r: Row): number { return Math.max(0, (Number(r.bookValue) || 0) - (Number(r.recoverableAmount) || 0)) }
function additional(r: Row): number { return Math.max(0, loss(r) - (Number(r.priorImpairment) || 0)) }

const totalLoss = computed(() => calcSubtotal(rows.value.map((r) => loss(r))))
const totalAdditional = computed(() => calcSubtotal(rows.value.map((r) => additional(r))))

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetGroup: raw.assetGroup ?? '',
    impairmentSign: raw.impairmentSign ?? '',
    bookValue: Number(raw.bookValue) || 0,
    recoverableAmount: Number(raw.recoverableAmount) || 0,
    priorImpairment: Number(raw.priorImpairment) || 0,
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = impair.getString('H7-15-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = impair.getString('H7-15-note')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-15-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产/资产组名称', '新增减值测算项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(normalize({ assetGroup: value })); persistRows() }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
async function handleAi(): Promise<void> {
  if (!generateAiText) return
  const ctx = `减值测算 ${rows.value.length} 项，减值损失合计 ${fmtAmt(totalLoss.value)}，本期补提 ${fmtAmt(totalAdditional.value)}。`
  const text = await generateAiText('h7-impairment', ctx, auditNote.value)
  if (text) { auditNote.value = text; persist('H7-15-note', auditNote.value) }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-impairment { padding: 16px; font-size: 13px; }
.audit-goal { margin-bottom: 12px; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.summary-row { display: flex; gap: 24px; margin-bottom: 12px; padding: 6px 12px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.text-danger { color: var(--el-color-danger); }
.check-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.calc-cell.has-loss { color: var(--el-color-danger); font-weight: 600; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
