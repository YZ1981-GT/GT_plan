<template>
  <div class="l4-tab-fin-liab-other">
    <!-- ═══ 标题 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L4-3 划分为金融负债的其他金融工具明细表</h3>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
        <el-button size="small" @click="handleAI('finLiab')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>划分为金融负债的其他金融工具（CAS 37）：</strong>
        不满足权益工具条件而划分为金融负债的金融工具。包括：优先股（强制分红）、永续债（含利率跳升）、
        可回售工具等。需逐一核实合同条款并判断是否满足负债定义（交付现金或其他金融资产的合同义务）。
      </div>
    </div>

    <!-- ═══ 明细表（27×40简化） ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%"
    >
      <el-table-column type="index" label="#" width="50" align="center" />

      <el-table-column prop="instrumentName" label="工具名称" min-width="180">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.instrumentName" size="small" @change="triggerSave($index)" />
          <span v-else>{{ row.instrumentName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="工具类型" min-width="130">
        <template #default="{ row, $index }">
          <el-select v-if="!isReadonly" v-model="row.instrumentType" size="small" style="width:100%" @change="triggerSave($index)">
            <el-option label="优先股" value="优先股" />
            <el-option label="永续债" value="永续债" />
            <el-option label="可回售工具" value="可回售工具" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.instrumentType || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="合同条款" min-width="200">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.contractTerms" size="small" @change="triggerSave($index)" />
          <span v-else>{{ row.contractTerms || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="划分为负债原因" min-width="200">
        <template #default="{ row, $index }">
          <el-input v-if="!isReadonly" v-model="row.liabilityReason" size="small" @change="triggerSave($index)" />
          <span v-else>{{ row.liabilityReason || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="初始确认金额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.initialAmount" :controls="false" size="small" style="width:100%" @change="triggerSave($index)" />
          <span v-else>{{ fmtAmount(row.initialAmount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" min-width="130" align="right">
        <template #default="{ row, $index }">
          <el-input-number v-if="!isReadonly" v-model="row.endBalance" :controls="false" size="small" style="width:100%" @change="triggerSave($index)" />
          <span v-else>{{ fmtAmount(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="公允价值计量" width="110" align="center">
        <template #default="{ row, $index }">
          <el-checkbox v-model="row.isFairValue" :disabled="isReadonly" @change="triggerSave($index)" />
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="70" align="center" v-if="!isReadonly">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="removeRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计 ═══ -->
    <div class="summary-bar">
      <span>共 <strong>{{ rows.length }}</strong> 项工具</span>
      <span>期末余额合计：<strong>{{ fmtAmount(totalEndBalance) }}</strong></span>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('auditNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写金融负债划分审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="l4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>金融负债核心判断：是否存在交付现金或其他金融资产的合同义务</li>
        <li>优先股：强制分红条款→金融负债</li>
        <li>永续债：含利率跳升/赎回条款→实质为负债</li>
        <li>核实合同条款原件，关注隐含义务</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * L4TabFinLiabOther — L4-3 划分为金融负债的其他金融工具明细表
 *
 * Requirements: 7.4
 * - 27×40 表格（简化展示关键列）
 * - 动态行 + 8个公式/逻辑字段
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, MagicStick, Check } from '@element-plus/icons-vue'
import { useL4FormData } from '../../composables/useL4FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

const formData = useL4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

interface FinLiabRow {
  instrumentName: string
  instrumentType: string
  contractTerms: string
  liabilityReason: string
  initialAmount: number
  endBalance: number
  isFairValue: boolean
}

const rows = ref<FinLiabRow[]>([])

const totalEndBalance = computed(() => rows.value.reduce((sum, r) => sum + r.endBalance, 0))

const auditNote = ref('')

function saveAuditNote() {
  formData.debouncedSave('L4-3-auditNote', { remark: auditNote.value || null })
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入金融工具名称', '新增金融负债工具', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValidator: (val) => (!val?.trim() ? '名称不能为空' : true),
    })
    rows.value.push({
      instrumentName: name?.trim() || '',
      instrumentType: '',
      contractTerms: '',
      liabilityReason: '',
      initialAmount: 0,
      endBalance: 0,
      isFairValue: false,
    })
  } catch { /* cancel */ }
}

function removeRow(index: number) {
  rows.value.splice(index, 1)
}

function triggerSave(index: number) {
  const row = rows.value[index]
  if (!row) return
  const n = index + 1
  formData.debouncedSave(`L4-3-row-${n}-data`, { remark: JSON.stringify(row) })
}

function handleAI(_section: string) {}
function handleReview() { openReviewDialog?.() }

function fmtAmount(val: number): string {
  if (val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

onMounted(async () => {
  await formData.loadData()
})
</script>

<style scoped>
.l4-tab-fin-liab-other { padding: 12px; font-size: 13px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context {
  border-left: 4px solid #e6a23c; background: #fdf6ec;
  padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px;
}
.methodology-text { font-size: 13px; color: #6b5900; line-height: 1.6; }

:deep(.el-table) { font-size: 13px; }

.summary-bar {
  display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px;
  background: #f5f7fa; border-radius: 6px; font-size: 13px; color: #606266;
}

.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }

.l4-details-tip {
  margin-top: 16px; padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266;
}
.l4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.l4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
