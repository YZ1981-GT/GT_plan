<template>
  <div class="i2-outsource-check">
    <!-- Section Header -->
    <div class="section-header">
      <span class="section-title">I2-11 委外研发检查表</span>
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
      <p>核查委外研发支出的真实性和完整性：验证供应商资质、合同金额、交付物实质性、验收记录是否齐全。委外研发费用加计扣除按80%计入。</p>
    </div>

    <!-- 数据表 -->
    <el-table :data="rows" border size="small" class="check-table" max-height="500">
      <el-table-column type="index" label="#" width="40" fixed />
      <el-table-column prop="supplier" label="供应商" min-width="150">
        <template #default="{ row }">
          <el-input v-model="row.supplier" size="small" placeholder="供应商名称" />
        </template>
      </el-table-column>
      <el-table-column prop="contractNo" label="合同号" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.contractNo" size="small" placeholder="合同编号" />
        </template>
      </el-table-column>
      <el-table-column prop="amount" label="金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.amount" size="small" :controls="false" :precision="2" style="width:100%" />
        </template>
      </el-table-column>
      <el-table-column prop="deliverable" label="交付物" min-width="160">
        <template #default="{ row }">
          <el-input v-model="row.deliverable" size="small" placeholder="交付物描述" />
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
      <el-table-column prop="conclusion" label="验收结论" min-width="120">
        <template #default="{ row }">
          <el-select v-model="row.conclusion" size="small" placeholder="结论" style="width:100%">
            <el-option label="验收通过" value="验收通过" />
            <el-option label="验收不通过" value="验收不通过" />
            <el-option label="待验收" value="待验收" />
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
import { ElMessage } from 'element-plus'
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

interface OutsourceRow {
  supplier: string; contractNo: string; amount: number
  deliverable: string; projectName: string; conclusion: string
}

const STORAGE_KEY = 'I2-11-rows'
const rows = ref<OutsourceRow[]>([])

function loadData() {
  const raw = props.allResponses.get(STORAGE_KEY)
  if (!raw) { rows.value = []; return }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : (raw.remark ? JSON.parse(raw.remark) : raw)
    if (Array.isArray(parsed)) rows.value = parsed.map((r: any) => ({
      supplier: r.supplier || '', contractNo: r.contractNo || '',
      amount: Number(r.amount) || 0, deliverable: r.deliverable || '',
      projectName: r.projectName || '', conclusion: r.conclusion || '',
    }))
  } catch { rows.value = [] }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

function handleAddRow() {
  rows.value.push({ supplier: '', contractNo: '', amount: 0, deliverable: '', projectName: '', conclusion: '' })
}

async function handleSave() {
  await props.saveResponse('I2-11', { [STORAGE_KEY]: JSON.stringify(rows.value) })
  emit('save'); ElMessage.success('委外研发检查表已保存')
}

function handleOcr(idx: number) { ElMessage.info('OCR识别合同/验收单...') }
function handleSampling() { ElMessage.info('抽凭引擎(GtVoucherSamplingEngine)加载中...') }
function handleAiAssist() { ElMessage.info('AI辅助委外合规分析...') }
function handleReview() { openReviewDialog('I2-11-委外研发检查') }
</script>

<style scoped>
.i2-outsource-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 16px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6; }
.check-table { font-size: var(--wp-font-size, 13px); }
.table-actions { display: flex; gap: 8px; margin-top: 12px; }
</style>
