<template>
  <div class="h7-tab-recoverable">
    <el-alert type="info" :closable="false" show-icon class="audit-goal">
      <template #title>
        审计目标：复核可收回金额的确定方法与计算过程，验证取"公允价值减去处置费用"与"预计未来现金流量现值"两者较高者，为 H7-15 减值测算提供依据（CAS 8《资产减值》）。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H7-16" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>
            H7-16 可收回金额测试
            <GtIndexChip value="wp:H7-15" />
            <el-tag size="small" type="info" class="row-tag">共 {{ rows.length }} 行</el-tag>
          </span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H7-16')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-block">
        可收回金额 = max(公允价值 − 处置费用, 预计未来现金流量现值)。农业生物资产未来现金流量可参考产量记录、产品市场价格及养殖/种植周期折现估算。
      </div>

      <el-table :data="rows" border stripe size="small" class="check-table" max-height="500">
        <el-table-column type="index" label="序" width="46" align="center" fixed />
        <el-table-column prop="assetGroup" label="资产/资产组" min-width="130" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetGroup" size="small" @change="persistRows" />
            <span v-else>{{ row.assetGroup }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="fairValueLessCost" label="公允价值减处置费用" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.fairValueLessCost" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.fairValueLessCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="presentValue" label="未来现金流量现值" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.presentValue" :controls="false" size="small" @change="persistRows" />
            <span v-else class="amount-cell">{{ fmtAmt(row.presentValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="可收回金额" min-width="120" align="right">
          <template #default="{ row }">
            <span class="calc-cell" title="=max(公允价值减处置费用, 未来现金流量现值)">{{ fmtAmt(recoverable(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="method" label="采用方法" width="150">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.method" size="small" @change="persistRows">
              <el-option v-for="m in METHOD_OPTIONS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.method }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="discountRate" label="折现率(%)" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.discountRate" :controls="false" :precision="2" size="small" @change="persistRows" />
            <span v-else>{{ row.discountRate }}%</span>
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
        <el-button size="small" @click="handleAddRow">+ 新增测试项</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><div class="section-title"><span>审计说明</span></div></template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly" placeholder="记录可收回金额测试的实施过程、取值依据与关键假设。" @blur="persist('H7-16-note', auditNote)" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>审计结论</span>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="记录可收回金额确定方法、关键假设与合理性评价" @blur="persist('H7-16-conclusion', auditConclusion)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>可收回金额取"公允价值减处置费用"与"未来现金流量现值"两者较高者。</li>
        <li>未来现金流量现值应基于合理的产量预测、产品价格及适当的折现率（反映资产特定风险）估算。</li>
        <li>可收回金额结果传递至 H7-15 减值测算表用于计算减值损失。</li>
        <li>复杂 DCF 模型建议使用 OnlyOffice 查看详细现金流量表。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, onMounted, toRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import { useH7Impairment } from '../../composables/useH7Impairment'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly?: boolean }>()
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)
const impair = useH7Impairment(allResponsesRef as any, { wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })

const METHOD_OPTIONS = ['公允价值减处置费用', '未来现金流量现值(DCF)', '两者较高者']

interface Row {
  rowId: string
  assetGroup: string
  fairValueLessCost: number
  presentValue: number
  method: string
  discountRate: number
  conclusion: string
}

const rows = ref<Row[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function recoverable(r: Row): number { return Math.max(Number(r.fairValueLessCost) || 0, Number(r.presentValue) || 0) }

function normalize(raw: any): Row {
  return {
    rowId: raw.rowId ?? `r-${Math.random().toString(36).slice(2, 9)}`,
    assetGroup: raw.assetGroup ?? '',
    fairValueLessCost: Number(raw.fairValueLessCost) || 0,
    presentValue: Number(raw.presentValue) || 0,
    method: raw.method ?? '',
    discountRate: Number(raw.discountRate) || 0,
    conclusion: raw.conclusion ?? '',
  }
}

function seed(): void {
  const raw = impair.getString('H7-16-rows')
  if (raw) { try { const p = JSON.parse(raw); if (Array.isArray(p)) rows.value = p.map(normalize) } catch { /* ignore */ } }
  auditNote.value = impair.getString('H7-16-note')
  auditConclusion.value = impair.getString('H7-16-conclusion')
}
onMounted(seed)

function persist(itemId: string, val: any): void { if (!props.isReadonly) saveResponse(itemId, val) }
function persistRows(): void { persist('H7-16-rows', rows.value) }

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产/资产组名称', '新增测试项', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value) { rows.value.push(normalize({ assetGroup: value })); persistRows() }
  } catch { /* cancelled */ }
}
function removeRow(rowId: string): void {
  const i = rows.value.findIndex((r) => r.rowId === rowId)
  if (i >= 0) { rows.value.splice(i, 1); persistRows() }
}
function handleReview(id: string): void { openReviewDialog(id) }
function fmtAmt(v: number | null | undefined): string {
  return v == null ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h7-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.audit-goal { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.chip-wrap { display: inline-flex; }
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.row-tag { margin-left: 8px; }
.methodology-block { padding: 10px 14px; background: #fffbe6; border-left: 3px solid #e6a23c; border-radius: 4px; margin-bottom: 16px; font-size: 12px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.calc-cell { font-variant-numeric: tabular-nums; background: var(--el-fill-color-light); border-bottom: 1px dashed var(--el-border-color); cursor: help; display: inline-block; width: 100%; text-align: right; }
.action-bar { margin: 12px 0; }
.note-card { margin-bottom: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
