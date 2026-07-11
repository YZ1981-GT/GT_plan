<template>
  <div class="k6-tab-adjustment">
    <!-- Section标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">K6-3 调整分录汇总</h3>
      <div class="head-actions">
        <el-dropdown size="small" @command="handleIECommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('K6-3-adjustment')">💬复核</el-button>
      </div>
    </div>

    <!-- 蓝色引导区 -->
    <div class="guidance-area">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span> 新增AJE/RJE调整分录</div>
        <div class="guidance-step"><span class="step-num">②</span> 填写借贷金额（系统自动校验平衡）</div>
        <div class="guidance-step"><span class="step-num">③</span> 保存并回写K6-1审定表</div>
        <div class="guidance-step"><span class="step-num">④</span> 系统自动通知A13错报汇总</div>
      </div>
    </div>

    <!-- 借贷平衡状态 -->
    <div class="balance-bar">
      <span>借方合计：<strong>{{ fmtAmt(totalDebits) }}</strong></span>
      <span>贷方合计：<strong>{{ fmtAmt(totalCredits) }}</strong></span>
      <el-tag :type="isBalanced ? 'success' : 'danger'" size="small" effect="plain">
        {{ isBalanced ? '借贷平衡 ✓' : `差额 ${fmtAmt(balanceDiff)}` }}
      </el-tag>
    </div>

    <!-- 调整分录表 -->
    <el-card shadow="never" class="adj-table-card">
      <template #header>
        <div class="section-card-header">
          <span>AJE/RJE 分录明细</span>
          <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddEntry">+ 新增</el-button>
        </div>
      </template>

      <el-empty v-if="entries.length === 0" description="暂无调整分录，点击"+ 新增"添加" />

      <el-table
        v-else
        :data="entries"
        border
        size="small"
        style="width: 100%"
        :row-class-name="tableRowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column prop="seq" label="序" width="48" align="center" />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">
            <el-select
              :model-value="row.entryType"
              :disabled="isReadonly"
              size="small"
              @change="(v: string) => updateCell(row.id, 'entryType', v)"
            >
              <el-option label="AJE" value="AJE" />
              <el-option label="RJE" value="RJE" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="科目代码" width="100">
          <template #default="{ row }">
            <el-input
              :model-value="row.accountCode"
              :disabled="isReadonly"
              size="small"
              placeholder="科目"
              @blur="(e: FocusEvent) => updateCell(row.id, 'accountCode', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="科目名称" min-width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.accountName"
              :disabled="isReadonly"
              size="small"
              placeholder="科目名称"
              @blur="(e: FocusEvent) => updateCell(row.id, 'accountName', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="150">
          <template #default="{ row }">
            <el-input
              :model-value="row.summary"
              :disabled="isReadonly"
              size="small"
              placeholder="调整摘要"
              @blur="(e: FocusEvent) => updateCell(row.id, 'summary', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column label="借方" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.debitAmount"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.id, 'debitAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.creditAmount"
              :disabled="isReadonly"
              :controls="false"
              :precision="2"
              size="small"
              style="width: 100%"
              @change="(v: number | undefined) => updateCell(row.id, 'creditAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="编制人" width="80">
          <template #default="{ row }">
            <el-input
              :model-value="row.preparedBy"
              :disabled="isReadonly"
              size="small"
              @blur="(e: FocusEvent) => updateCell(row.id, 'preparedBy', (e.target as HTMLInputElement)?.value ?? '')"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="handleRemoveEntry(row.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 保存回写按钮 -->
    <div class="save-bar">
      <el-button
        type="primary"
        :disabled="isReadonly || !isBalanced"
        @click="handleSaveWriteback"
      >
        保存并回写K6-1
      </el-button>
      <span v-if="!isBalanced" class="balance-warning">⚠ 借贷不平衡，无法回写</span>
    </div>

    <!-- 编制提示 -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>AJE=审计调整分录，RJE=重分类调整分录</li>
        <li>保存时系统自动汇总AJE/RJE净额回写K6-1审定表</li>
        <li>保存后发布 adjustment:created 事件通知A13错报汇总底稿</li>
        <li>持有待售资产（借方/资产类）：AJE净调整 = 借方 - 贷方</li>
        <li>持有待售负债（贷方/负债类）：AJE净调整 = 贷方 - 借方</li>
        <li>借贷必须平衡才能保存回写</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传 input -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabAdjustment.vue — K6-3 调整分录汇总
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.6
 * Requirements: 8.2
 *
 * 功能：
 * - AJE/RJE 调整分录管理
 * - 借贷平衡校验
 * - 双向同步K6-1 (applyAdjustment)
 * - publish 'adjustment:created' → A13
 * - 导入导出 (el-dropdown)
 * - 蓝色引导区 + 编制提示
 */
import { ref, computed, onMounted, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useK6ImportExport } from '@/components/workpaper/composables/useK6ImportExport'

const K6_ACCOUNT_CODE_ASSET = '1481'  // 持有待售资产
const K6_ACCOUNT_CODE_LIAB = '2245'   // 持有待售负债
const ITEM_PREFIX = 'K6-3-adj'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ═══ 导入导出 ═══
const { exportTemplate, exportData, importData } = useK6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K6-3',
})

const fileInputRef = ref<HTMLInputElement | null>(null)

// ═══ 数据模型 ═══
interface AdjustmentEntry {
  id: string
  seq: number
  entryType: 'AJE' | 'RJE'
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  summary: string
  preparedBy: string
  remark: string
}

const entries = ref<AdjustmentEntry[]>([])
let nextId = 1

// ═══ 计算属性：借贷平衡 ═══
const totalDebits = computed(() => entries.value.reduce((sum, e) => sum + (e.debitAmount || 0), 0))
const totalCredits = computed(() => entries.value.reduce((sum, e) => sum + (e.creditAmount || 0), 0))
const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
const isBalanced = computed(() => Math.abs(balanceDiff.value) < 0.005)

// ═══ 初始化加载 ═══
onMounted(() => {
  loadFromResponses()
})

function loadFromResponses(): void {
  const saved = props.allResponses.get(`${ITEM_PREFIX}-entries`)
  const raw = saved?.remark ?? saved?.value ?? (typeof saved === 'string' ? saved : null)
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (Array.isArray(parsed)) {
        entries.value = parsed.map((e: any, idx: number) => ({
          id: e.id || `entry-${++nextId}`,
          seq: idx + 1,
          entryType: e.entryType || 'AJE',
          accountCode: e.accountCode || '',
          accountName: e.accountName || '',
          debitAmount: Number(e.debitAmount) || 0,
          creditAmount: Number(e.creditAmount) || 0,
          summary: e.summary || '',
          preparedBy: e.preparedBy || '',
          remark: e.remark || '',
        }))
        nextId = entries.value.length + 1
      }
    } catch { /* ignore parse error */ }
  }
}

// ═══ 行操作 ═══
async function handleAddEntry(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入分录摘要', '新增调整分录', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：调整持有待售减值准备',
    })
    if (value?.trim()) {
      const entry: AdjustmentEntry = {
        id: `entry-${++nextId}`,
        seq: entries.value.length + 1,
        entryType: 'AJE',
        accountCode: K6_ACCOUNT_CODE_ASSET,
        accountName: '持有待售资产',
        debitAmount: 0,
        creditAmount: 0,
        summary: value.trim(),
        preparedBy: '',
        remark: '',
      }
      entries.value.push(entry)
      persistEntries()
    }
  } catch { /* cancelled */ }
}

async function handleRemoveEntry(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该调整分录行？', '删除确认', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    entries.value = entries.value.filter(e => e.id !== id)
    reSequence()
    persistEntries()
  } catch { /* cancelled */ }
}

function updateCell(id: string, field: keyof AdjustmentEntry, value: any): void {
  const entry = entries.value.find(e => e.id === id)
  if (entry) {
    ;(entry as any)[field] = value
    persistEntries()
  }
}

function reSequence(): void {
  entries.value.forEach((e, i) => { e.seq = i + 1 })
}

// ═══ 持久化 ═══
function persistEntries(): void {
  emit('save', `${ITEM_PREFIX}-entries`, { remark: JSON.stringify(entries.value) })
}

// ═══ 保存回写K6-1 + EventBus ═══
function handleSaveWriteback(): void {
  if (!isBalanced.value) {
    ElMessage.warning('借贷不平衡，无法回写')
    return
  }

  // 持有待售资产(借方/资产类): AJE净调整 = 借方-贷方(借方增资产)
  const ajeAsset = entries.value
    .filter(e => e.entryType === 'AJE' && (e.accountCode === K6_ACCOUNT_CODE_ASSET || e.accountCode.startsWith('148')))
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)
  const rjeAsset = entries.value
    .filter(e => e.entryType === 'RJE' && (e.accountCode === K6_ACCOUNT_CODE_ASSET || e.accountCode.startsWith('148')))
    .reduce((sum, e) => sum + (e.debitAmount - e.creditAmount), 0)

  // 持有待售负债(贷方/负债类): AJE净调整 = 贷方-借方(贷方增负债)
  const ajeLiab = entries.value
    .filter(e => e.entryType === 'AJE' && (e.accountCode === K6_ACCOUNT_CODE_LIAB || e.accountCode.startsWith('224')))
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)
  const rjeLiab = entries.value
    .filter(e => e.entryType === 'RJE' && (e.accountCode === K6_ACCOUNT_CODE_LIAB || e.accountCode.startsWith('224')))
    .reduce((sum, e) => sum + (e.creditAmount - e.debitAmount), 0)

  // 汇总AJE/RJE总额（简化：合并资产+负债）
  const ajeTotal = ajeAsset + ajeLiab
  const rjeTotal = rjeAsset + rjeLiab

  // 同步到allResponses供K6-1审定表读取
  props.allResponses.set('K6-1-aje-total', { item_id: 'K6-1-aje-total', value: ajeTotal })
  props.allResponses.set('K6-1-rje-total', { item_id: 'K6-1-rje-total', value: rjeTotal })
  props.allResponses.set('K6-1-aje-asset', { item_id: 'K6-1-aje-asset', value: ajeAsset })
  props.allResponses.set('K6-1-rje-asset', { item_id: 'K6-1-rje-asset', value: rjeAsset })
  props.allResponses.set('K6-1-aje-liab', { item_id: 'K6-1-aje-liab', value: ajeLiab })
  props.allResponses.set('K6-1-rje-liab', { item_id: 'K6-1-rje-liab', value: rjeLiab })

  // 持久化
  emit('save', 'K6-1-aje-total', ajeTotal)
  emit('save', 'K6-1-rje-total', rjeTotal)
  emit('save', 'K6-1-aje-asset', ajeAsset)
  emit('save', 'K6-1-rje-asset', rjeAsset)
  emit('save', 'K6-1-aje-liab', ajeLiab)
  emit('save', 'K6-1-rje-liab', rjeLiab)
  persistEntries()

  // EventBus publish adjustment:created → A13
  try {
    eventBus.emit('adjustment:created', {
      wpCode: 'K6',
      accountCode: K6_ACCOUNT_CODE_ASSET,
      projectId: props.projectId,
      ajeTotal,
      rjeTotal,
      entryCount: entries.value.length,
    })
  } catch { /* silent */ }

  ElMessage.success('已保存并回写K6-1审定表，已通知A13')
}

// ═══ 导入导出 ═══
function handleIECommand(cmd: string): void {
  if (cmd === 'template') {
    exportTemplate()
  } else if (cmd === 'export') {
    exportData()
  } else if (cmd === 'import') {
    fileInputRef.value?.click()
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  input.value = '' // reset

  const result = await importData(file)
  if (result && result.rowCount > 0) {
    ElMessage.info('导入完成，请刷新查看最新数据')
  }
}

// ═══ Table Summary ═══
function getSummary({ columns }: any): string[] {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'debitAmount' || idx === 5) return fmtAmt(totalDebits.value)
    if (col.property === 'creditAmount' || idx === 6) return fmtAmt(totalCredits.value)
    return ''
  })
}

// ═══ 复核 ═══（使用inject的openReviewDialog）

// ═══ 格式化 ═══
function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function tableRowClassName({ row }: { row: AdjustmentEntry }): string {
  if (row.entryType === 'RJE') return 'rje-row'
  return ''
}
</script>

<style scoped>
.k6-tab-adjustment { padding: 12px; font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; }

.guidance-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.guidance-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guidance-step { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; color: #1a5276; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; border-radius: 50%; background: #2980b9; color: #fff; font-size: 10px; flex-shrink: 0; }

.balance-bar {
  display: flex; gap: 16px; align-items: center; padding: 8px 12px;
  background: #f5f7fa; border-radius: 6px; margin-bottom: 12px; font-size: 13px;
}

.adj-table-card { margin-bottom: 12px; }
.section-card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }

.save-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.balance-warning { color: #e6a23c; font-size: 12px; }

:deep(.rje-row) { background-color: #fdf6ec !important; }

.k6-details-tip { margin-top: 16px; font-size: 12px; color: #666; }
.k6-details-tip summary { cursor: pointer; color: #409eff; font-weight: 500; }
.k6-details-tip ul { margin: 8px 0 0 16px; line-height: 1.8; }
</style>
