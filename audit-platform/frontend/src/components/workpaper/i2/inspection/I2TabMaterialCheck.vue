<template>
  <div class="i2-material-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-8 研发材料投入检查表</span>
      <div class="section-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
      </div>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>核查研发材料领用的真实性和完整性：验证品名、数量、单价、金额是否与领用单据一致，审核材料是否确实用于研发项目。</p>
    </div>

    <!-- 数据表 -->
    <el-table :data="rows" border size="small" class="check-table" max-height="500">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="materialName" label="品名" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.materialName" size="small" placeholder="材料品名" />
        </template>
      </el-table-column>
      <el-table-column prop="quantity" label="数量" min-width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.quantity" size="small" :controls="false" :precision="2" @change="recalcAmount(row)" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="unitPrice" label="单价" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.unitPrice" size="small" :controls="false" :precision="4" @change="recalcAmount(row)" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" min-width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" :title="`数量×单价=${row.quantity}×${row.unitPrice}`">{{ fmtNum(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="requisitionNo" label="领用单号" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.requisitionNo" size="small" placeholder="单号" />
        </template>
      </el-table-column>
      <el-table-column prop="projectName" label="归属项目" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.projectName" size="small" placeholder="项目" />
        </template>
      </el-table-column>
      <el-table-column label="📎" width="50" align="center">
        <template #default="{ $index }">
          <el-button size="small" text @click="handleOcr($index)">📎</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="conclusion" label="审核结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" placeholder="结论" style="width:100%">
            <el-option label="相符" value="相符" />
            <el-option label="不符" value="不符" />
            <el-option label="待查" value="待查" />
          </el-select>
        </template>
      </el-table-column>
    </el-table>

    <!-- 行操作 -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain @click="handleAddRow">+ 新增行</el-button>
      <el-button size="small" type="warning" plain @click="handleSampling">抽凭引擎</el-button>
      <el-button size="small" type="success" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
}>()

const emit = defineEmits<{ 'save': []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

interface MaterialRow {
  materialName: string; quantity: number; unitPrice: number; amount: number
  requisitionNo: string; projectName: string; conclusion: string
}

const STORAGE_KEY = 'I2-8-rows'
const rows = ref<MaterialRow[]>([])

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) { rows.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) rows.value = parsed.map(normRow)
  } catch { rows.value = [] }
}

function normRow(r: any): MaterialRow {
  const row: MaterialRow = {
    materialName: r.materialName || '', quantity: Number(r.quantity) || 0,
    unitPrice: Number(r.unitPrice) || 0, amount: 0,
    requisitionNo: r.requisitionNo || '', projectName: r.projectName || '',
    conclusion: r.conclusion || '',
  }
  row.amount = Math.round(row.quantity * row.unitPrice * 100) / 100
  return row
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

function recalcAmount(row: MaterialRow) { row.amount = Math.round(row.quantity * row.unitPrice * 100) / 100 }

function handleAddRow() { rows.value.push(normRow({})) }

async function handleSave() {
  await props.saveResponse('I2-8', { [STORAGE_KEY]: JSON.stringify(rows.value) })
  emit('save'); ElMessage.success('材料投入检查表已保存')
}

function handleOcr(idx: number) { ElMessage.info('OCR识别领用单据...') }
function handleSampling() { ElMessage.info('抽凭引擎(GtVoucherSamplingEngine)加载中...') }
function handleAiAssist() { ElMessage.info('AI辅助材料归集分析...') }
function handleReview() { openReviewDialog('I2-8-研发材料投入检查') }
function fmtNum(v: number): string { return v == null || isNaN(v) ? '—' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
</script>

<style scoped>
.i2-material-check { font-size: 13px; padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.check-table { font-size: 13px; }
.formula-cell { color: #6366f1; font-weight: 500; border-bottom: 1px dashed #a5b4fc; cursor: help; }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
