<template>
  <div class="l6-tab-adjudication">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">L6-1 专项应付款审定表</h3>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('adjudication')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>专项应付款为负债类贷方科目（2601）：</strong>
        审定数 = 未审数 + 账项调整(AJE) + 重分类调整(RJE)。
        变动额 = 期末审定 − 期初审定。变动率 = IF(期初=0且变动=0, 0, IF(期初=0且变动>0, 100%, 变动额/期初审定))。
        各专项项目按行列示，合计行自动汇总。
      </div>
    </div>

    <!-- ═══ 专项应付款审定表（单区块 负债类贷方） ═══ -->
    <div class="block-section">
      <h4 class="block-title">专项应付款（贷方/负债类 科目2601）</h4>
      <el-table
        :data="computedRows"
        border
        size="small"
        style="width: 100%"
        show-summary
        :summary-method="getSummaries"
      >
        <!-- A列：项目 -->
        <el-table-column prop="project" label="项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.project"
                size="small"
                placeholder="专项项目名称"
                @change="(val: string) => updateRow($index, 'project', val)"
              />
            </template>
            <span v-else>{{ row.project || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 期初组：B/C/D/E -->
        <el-table-column label="期初数" align="center">
          <el-table-column label="未审数" width="120" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.beginUnadjusted"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateRow($index, 'beginUnadjusted', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.beginUnadjusted) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="账项调整" width="120" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.beginAje"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateRow($index, 'beginAje', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.beginAje) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="重分类" width="120" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.beginRje"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateRow($index, 'beginRje', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.beginRje) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="审定数" width="120" align="right">
            <template #header>
              <el-tooltip content="期初审定 = 未审 + AJE + RJE" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 期末组：F/G/H/I -->
        <el-table-column label="期末数" align="center">
          <el-table-column label="未审数" width="120" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.endUnadjusted"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateRow($index, 'endUnadjusted', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.endUnadjusted) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="账项调整" width="120" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.endAje"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateRow($index, 'endAje', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.endAje) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="重分类" width="120" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.endRje"
                  :controls="false"
                  size="small"
                  style="width: 100%"
                  @change="(val: number | undefined) => updateRow($index, 'endRje', val ?? 0)"
                />
              </template>
              <span v-else>{{ fmtAmount(row.endRje) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="审定数" width="120" align="right">
            <template #header>
              <el-tooltip content="期末审定 = 未审 + AJE + RJE" placement="top">
                <span class="formula-col-header">审定数</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.endAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 变动分析组：J/K -->
        <el-table-column label="本期审定数与上期审定数的比较" align="center">
          <el-table-column label="变动额" width="120" align="right">
            <template #header>
              <el-tooltip content="变动额 = 期末审定 − 期初审定" placement="top">
                <span class="formula-col-header">变动额</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value" :class="{ 'variance-negative': row.variance < 0 }">
                {{ fmtAmount(row.variance) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="变动率" width="100" align="right">
            <template #header>
              <el-tooltip content="IF(期初=0且变动=0, 0, IF(期初=0且变动>0, 100%, 变动额/期初))" placement="top">
                <span class="formula-col-header">变动率</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtPercent(row.varianceRate) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" text size="small" @click="handleRemoveRow($index)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 新增行按钮 -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="handleAddRow">+ 新增专项项目</el-button>
      </div>
    </div>

    <!-- ═══ 合计区 ═══ -->
    <div class="total-section">
      <div class="total-grid">
        <div class="total-item">
          <span class="total-label">期末审定合计</span>
          <span class="total-value" :class="{ 'total-abnormal': totalRow.endAudited < 0 }">
            {{ fmtAmount(totalRow.endAudited) }}
          </span>
        </div>
        <div class="total-item">
          <span class="total-label">期初审定合计</span>
          <span class="total-value">{{ fmtAmount(totalRow.beginAudited) }}</span>
        </div>
        <div class="total-item">
          <span class="total-label">本期变动额</span>
          <span class="total-value">{{ fmtAmount(totalRow.variance) }}</span>
        </div>
        <div class="total-item">
          <span class="total-label">变动率</span>
          <span class="total-value">{{ fmtPercent(totalRow.varianceRate) }}</span>
        </div>
      </div>
      <el-alert v-if="totalRow.endAudited < 0" type="warning" :closable="false" show-icon style="margin-top: 8px">
        余额异常：专项应付款期末审定为负，请核查各项目金额
      </el-alert>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
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
        placeholder="请填写审定表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="l6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>专项应付款为负债类贷方科目（2601）：期末=期初+贷方−借方</li>
        <li>审定数 = 未审数 + 账项调整(AJE) + 重分类调整(RJE)</li>
        <li>变动额 = 期末审定 − 期初审定</li>
        <li>变动率 = IF(期初=0且变动=0, 0, IF(期初=0且变动>0, 100%, 变动额/期初))</li>
        <li>各项目从明细表L6-2引用，合计行自动汇总</li>
        <li>审定合计变化自动回写TB（科目2601）并通知附注组件</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传 -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display: none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * L6TabAdjudication — L6-1 专项应付款审定表
 *
 * Requirements: 2.1-2.7
 * - 负债类单区块：专项应付款(贷方/负债，按专项项目分类+小计)
 * - 列结构(来源xlsx)：项目 | 期初(未审/AJE/RJE/审定) | 期末(未审/AJE/RJE/审定) | 变动额 | 变动率
 * - 公式列(readonly): 期初审定=B+C+D, 期末审定=F+G+H, 变动额=I-E, 变动率=IF logic
 * - 公式列虚线下划线 + cursor:help + tooltip来源
 * - 合计行(小计)
 * - TB回写: 审定合计变化 → writebackTB(2601)
 * - EventBus: publish 'substantive:adjudicated' after writeback
 * - Section标题行右侧: 复核按钮 + AI辅助按钮
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { fmtAmount } from '@/utils/formatters'
import { useL6FormData } from '../../../composables/useL6FormData'
import { useL6DualMode } from '../../../composables/useL6DualMode'
import { useL6ImportExport } from '../../../composables/useL6ImportExport'
import {
  useL6Adjudication,
  type L6AdjudicationRow,
} from '../../../composables/useL6Adjudication'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<() => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useL6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetPrefix: 'L6-L6-1',
})

// ─── DualMode ────────────────────────────────────────────────────────────────

const dualMode = useL6DualMode({
  wpId: computed(() => props.wpId),
})

// ─── ImportExport ────────────────────────────────────────────────────────────

const importExport = useL6ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── 审定表行数据 ────────────────────────────────────────────────────────────

const adjudicationRows = ref<L6AdjudicationRow[]>([
  { key: 'l6-adj-1', project: '', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
  { key: 'l6-adj-2', project: '', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
  { key: 'l6-adj-3', project: '', beginUnadjusted: 0, beginAje: 0, beginRje: 0, beginAudited: 0, endUnadjusted: 0, endAje: 0, endRje: 0, endAudited: 0, variance: 0, varianceRate: 0 },
])

// ─── Adjudication Composable ─────────────────────────────────────────────────

const {
  computedRows,
  totalRow,
  addRow,
  removeRow,
  updateRow,
  saveAndWriteback,
  subscribeDisclosure,
} = useL6Adjudication(formData, adjudicationRows)

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function getSummaries({ columns }: { columns: any[] }) {
  const sums: string[] = []
  const t = totalRow.value
  columns.forEach((_col: any, index: number) => {
    if (index === 0) { sums[index] = '合 计'; return }
    // Map column indices to totalRow fields
    const vals: (number | string)[] = [
      t.beginUnadjusted, t.beginAje, t.beginRje, t.beginAudited,
      t.endUnadjusted, t.endAje, t.endRje, t.endAudited,
      t.variance, t.varianceRate,
    ]
    const i = index - 1
    if (i < 9) {
      sums[index] = fmtAmount(vals[i] as number)
    } else if (i === 9) {
      sums[index] = fmtPercent(vals[i] as number)
    } else {
      sums[index] = ''
    }
  })
  return sums
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

/** 变动率格式化（calcVarianceRate 返回小数，×100 显示） */
function fmtPercent(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return (val * 100).toFixed(2) + '%'
}

// ─── 操作 ─────────────────────────────────────────────────────────────────────

async function handleSave() {
  isSaving.value = true
  try {
    await saveAndWriteback()
    ElMessage.success('审定表已保存并回写TB')
  } finally {
    isSaving.value = false
  }
}

async function handleAddRow() {
  const { value: projectName } = await ElMessageBox.prompt(
    '请输入专项项目名称',
    '新增专项项目',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX科研经费',
    },
  ).catch(() => ({ value: null }))

  if (projectName) {
    addRow(projectName)
  }
}

function handleRemoveRow(index: number) {
  removeRow(index)
}

function handleImportExport(command: string) {
  switch (command) {
    case 'export-template':
      importExport.exportTemplate()
      break
    case 'export-data':
      importExport.exportData()
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    importExport.importData(file)
  }
  if (input) input.value = ''
}

function saveAuditNote() {
  formData.debouncedSave('L6-L6-1-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string) {
  // AI辅助钩子（集成时实现）
}

function handleReview() {
  openReviewDialog?.()
}

// ─── 加载已保存数据 ──────────────────────────────────────────────────────────

function hydrateFromResponses(): void {
  const responses = formData.responses.value
  if (!responses || responses.size === 0) return

  // 恢复行数据
  const loadedRows: L6AdjudicationRow[] = []
  let i = 1
  while (true) {
    const dataResp = responses.get(`L6-L6-1-row-${i}-data`)
    if (!dataResp?.remark) break
    try {
      const parsed = JSON.parse(dataResp.remark)
      loadedRows.push({
        key: parsed.key || `l6-adj-${i}`,
        project: parsed.project || '',
        beginUnadjusted: parsed.beginUnadjusted ?? 0,
        beginAje: parsed.beginAje ?? 0,
        beginRje: parsed.beginRje ?? 0,
        beginAudited: 0,
        endUnadjusted: parsed.endUnadjusted ?? 0,
        endAje: parsed.endAje ?? 0,
        endRje: parsed.endRje ?? 0,
        endAudited: 0,
        variance: 0,
        varianceRate: 0,
      })
    } catch {
      break
    }
    i++
  }

  if (loadedRows.length > 0) {
    adjudicationRows.value = loadedRows
  }

  // 恢复审计说明
  const noteResp = responses.get('L6-L6-1-auditNote')
  if (noteResp?.remark) {
    auditNote.value = noteResp.remark
  }
}

// ─── EventBus 订阅 ───────────────────────────────────────────────────────────

let unsubscribeDisclosure: (() => void) | null = null

onMounted(async () => {
  await formData.loadData()
  hydrateFromResponses()

  // 订阅附注变化
  unsubscribeDisclosure = subscribeDisclosure(() => {
    // 附注更新时可在此刷新相关数据
  })
})

onUnmounted(() => {
  if (unsubscribeDisclosure) {
    unsubscribeDisclosure()
    unsubscribeDisclosure = null
  }
})
</script>

<style scoped>
.l6-tab-adjudication {
  padding: 12px;
  font-size: 13px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: 13px;
  color: #6b5900;
  line-height: 1.6;
}

.block-section {
  margin-bottom: 20px;
}

.block-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

.variance-negative {
  color: #f56c6c;
}

:deep(.el-table) {
  font-size: 13px;
}

.add-row-bar {
  margin-top: 8px;
  text-align: center;
}

.total-section {
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.total-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.total-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.total-label {
  font-size: 12px;
  color: #909399;
}

.total-value {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
}

.total-abnormal {
  color: #f56c6c !important;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.l6-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.l6-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.l6-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
