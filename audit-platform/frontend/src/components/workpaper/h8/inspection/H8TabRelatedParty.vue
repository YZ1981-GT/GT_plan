<template>
  <div class="h8-tab-related-party">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>H8-14关联交易检查：识别关联方租赁并评估公允性。价差率=(关联租金-市场租金)/市场租金×100%。价差率>10%需重点关注定价合理性。</p>
    </div>

    <!-- 索引 + 行数 -->
    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-14" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
    </div>

    <!-- 关联租赁检查表 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <div class="section-title">
          <span>关联租赁检查（H8-14，45行15列）</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="primary" plain @click="$emit('open-ai', 'related-party')">AI 辅助</el-button>
            <el-button size="small" @click="$emit('open-review', 'related-party')">复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="rows" border size="small" class="formula-table"
        :row-class-name="getRowClassName">
        <el-table-column prop="contractNo" label="合同号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractNo" size="small"
              @change="updateCell(row.rowId, 'contractNo', row.contractNo)" />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relatedParty" label="关联方" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.relatedParty" size="small"
              @change="updateCell(row.rowId, 'relatedParty', row.relatedParty)" />
            <span v-else>{{ row.relatedParty }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relationship" size="small"
              @change="updateCell(row.rowId, 'relationship', row.relationship)">
              <el-option label="母公司" value="母公司" />
              <el-option label="子公司" value="子公司" />
              <el-option label="联营企业" value="联营企业" />
              <el-option label="合营企业" value="合营企业" />
              <el-option label="关键管理人员" value="关键管理人员" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else>{{ row.relationship }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="承租资产" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small"
              @change="updateCell(row.rowId, 'assetName', row.assetName)" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relatedRental" label="关联租金(年)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.relatedRental" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'relatedRental', v)" />
            <span v-else>{{ fmtAmt(row.relatedRental) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="marketRental" label="市场租金(年)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.marketRental" :controls="false" size="small"
              @change="(v: number | undefined) => updateCell(row.rowId, 'marketRental', v)" />
            <span v-else>{{ fmtAmt(row.marketRental) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="价差率(%)" width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" :class="Math.abs(row.priceDiffRate) > 10 ? 'abnormal' : ''"
              title="公式：(关联租金-市场租金)/市场租金×100%">
              {{ row.marketRental > 0 ? row.priceDiffRate.toFixed(2) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="fairnessAssessment" label="公允性评价" min-width="120">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.fairnessAssessment" size="small"
              @change="updateCell(row.rowId, 'fairnessAssessment', row.fairnessAssessment)">
              <el-option label="公允" value="公允" />
              <el-option label="基本公允" value="基本公允" />
              <el-option label="存在异常" value="存在异常" />
              <el-option label="待核实" value="待核实" />
            </el-select>
            <span v-else>{{ row.fairnessAssessment }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              @change="updateCell(row.rowId, 'remark', row.remark)" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="deleteRow(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>关联租赁必须披露：关联方名称、关系、租赁标的、金额</li>
        <li>价差率>10%：需关注定价合理性，是否存在利益输送</li>
        <li>关联租赁公允性评价：参照同地段市场租金水平</li>
        <li>关联方租赁终止/变更需额外关注商业合理性</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabRelatedParty.vue — H8-14 关联交易检查表
 * 45行15列，价差率计算+公允性评价
 * Spec: Task 4.10 | Requirements: 9.1
 */
import { ref, toRef, reactive, computed, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'

interface RelatedPartyRow {
  rowId: string
  contractNo: string
  relatedParty: string
  relationship: string
  assetName: string
  relatedRental: number
  marketRental: number
  priceDiffRate: number
  fairnessAssessment: string
  remark: string
}

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
}>()

const ROWS_KEY = 'H8-14-rows'
const rows = ref<RelatedPartyRow[]>([])

function _getJson(itemId: string): any {
  const item = props.allResponses.get(itemId)
  if (!item) return null
  const raw = item.remark ?? item.conclusion
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return raw }
}

function _normalizeRow(raw: any): RelatedPartyRow {
  const related = Number(raw.relatedRental) || 0
  const market = Number(raw.marketRental) || 0
  const diffRate = market > 0 ? ((related - market) / market) * 100 : 0
  return {
    rowId: raw.rowId ?? `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    contractNo: raw.contractNo ?? '',
    relatedParty: raw.relatedParty ?? '',
    relationship: raw.relationship ?? '',
    assetName: raw.assetName ?? '',
    relatedRental: related,
    marketRental: market,
    priceDiffRate: diffRate,
    fairnessAssessment: raw.fairnessAssessment ?? '',
    remark: raw.remark ?? '',
  }
}

function load() {
  const data = _getJson(ROWS_KEY)
  rows.value = Array.isArray(data) ? data.map(_normalizeRow) : []
}
load()
watch(() => props.allResponses, () => load())

function addRow(contractNo: string) {
  if (!contractNo?.trim()) return
  rows.value.push(_normalizeRow({ contractNo: contractNo.trim() }))
  persist()
}

function deleteRow(rowId: string) {
  const idx = rows.value.findIndex(r => r.rowId === rowId)
  if (idx !== -1) { rows.value.splice(idx, 1); persist() }
}

function updateCell(rowId: string, field: string, value: any) {
  const row = rows.value.find(r => r.rowId === rowId)
  if (!row) return
  const textFields = ['contractNo', 'relatedParty', 'relationship', 'assetName', 'fairnessAssessment', 'remark']
  if (textFields.includes(field)) { (row as any)[field] = String(value ?? ''); persist(); return }
  const numVal = Number(value) || 0
  if (field === 'relatedRental') row.relatedRental = numVal
  else if (field === 'marketRental') row.marketRental = numVal
  else return
  row.priceDiffRate = row.marketRental > 0 ? ((row.relatedRental - row.marketRental) / row.marketRental) * 100 : 0
  persist()
}

function persist() {
  emit('save', ROWS_KEY, rows.value.map(r => ({
    rowId: r.rowId, contractNo: r.contractNo, relatedParty: r.relatedParty,
    relationship: r.relationship, assetName: r.assetName,
    relatedRental: r.relatedRental, marketRental: r.marketRental,
    fairnessAssessment: r.fairnessAssessment, remark: r.remark,
  })))
}

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入合同号', '新增关联租赁行', {
    confirmButtonText: '确认', cancelButtonText: '取消', inputPlaceholder: '如：LEASE-2024-RP-001',
  })
  if (value) addRow(value)
}

function getRowClassName({ row }: { row: RelatedPartyRow }) {
  if (Math.abs(row.priceDiffRate) > 10) return 'abnormal-row'
  return ''
}
</script>

<style scoped>
.h8-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}

.h8-tab-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }

.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 6px; }

.table-card { margin-bottom: 16px; }
.formula-table { font-size: var(--wp-font-size, 13px); }
.formula-table :deep(.formula-col) { background: #fefce8; }
.formula-table :deep(.abnormal-row) { background: #fef2f2 !important; }
.formula-value { border-bottom: 1px dashed #d97706; cursor: help; color: #d97706; }
.formula-value.abnormal { color: #dc2626; font-weight: 700; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
