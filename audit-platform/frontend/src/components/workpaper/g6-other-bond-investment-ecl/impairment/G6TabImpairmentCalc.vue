<!--
  G6TabImpairmentCalc.vue — G6-12 减值准备测算表（22列 → 2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 未审+调整(12列): 投资项目|①摊余成本余额|公允价值|②预期信用损失率|③坏账准备(公式)|④账面价值(公式)|⑤余额调整|②A调整后损失率|⑥坏账调整(公式)|阶段|OCI影响|索引
  - Tab2: 审定数(10列): 投资项目|⑦审定余额(公式)|⑧审定坏账(公式)|⑨审定账面价值(公式)|审定公允价值|上年坏账|本年计提(公式)|本年转回|OCI调整|差异说明

  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  按Stage分组：Stage1/Stage2/Stage3 + 分组小计 + 总计行
  公式列：虚线下划线 + cursor:help + el-tooltip显示公式来源

  Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 6.2
  Requirements: 3.1, 3.2, 3.3, 3.4, 6.3
-->
<template>
  <div class="g6-impairment-calc">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <span class="methodology-icon">📋</span>
      <span>其他债权投资按<b>摊余成本口径</b>计算预期信用损失（ECL）。</span>
      <span>公式链：③=①×② / ⑥=⑤×②A+①×(②A-②) / ⑦=①+⑤ / ⑧=③+⑥ / ⑨=⑦-⑧</span>
    </div>

    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-12 减值准备测算表</h3>
      <div class="head-actions">
        <el-segmented v-model="activeTab" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 投资项目
        </el-button>
        <!-- 导入导出 dropdown -->
        <el-dropdown size="small" trigger="click" @command="handleImportExportCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="opt in importExportOptions"
                :key="opt.command"
                :command="opt.command"
              >{{ opt.label }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" link @click="handleAiConclusion">
          🤖 AI
        </el-button>
        <el-button size="small" @click="openReviewDialog('G6-12-impairment-calc')">💬复核</el-button>
      </div>
    </div>

    <!-- Stage分组表格 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="impairment-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal">
            <span class="subtotal-label">{{ row._groupLabel }}小计</span>
          </template>
          <template v-else-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <!-- 投资项目列（始终显示作为锚定列） -->
      <el-table-column label="投资项目" width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 未审+调整列 (12列) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="①摊余成本余额" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.amortizedCost) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.amortizedCost" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'amortizedCost', v)" />
              <span v-else>{{ fmtNum(row.amortizedCost) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="公允价值(参考)" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.fairValue" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'fairValue', v)" />
              <span v-else>{{ fmtNum(row.fairValue) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②预期信用损失率" min-width="140" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.creditLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                @change="(v: number) => updateField(row.id, 'creditLossRate', v)" />
              <span v-else>{{ (row.creditLossRate * 100).toFixed(2) }}%</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="③坏账准备" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentProvision) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="③ = ① × ②" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="④账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.bookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="④ = ① - ③" placement="top">
                <span class="formula-cell">{{ fmtNum(row.bookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑤余额调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.balanceAdjustment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'balanceAdjustment', v)" />
              <span v-else>{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②A调整后损失率" min-width="140" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.adjustedCreditLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                @change="(v: number) => updateField(row.id, 'adjustedCreditLossRate', v)" />
              <span v-else>{{ (row.adjustedCreditLossRate * 100).toFixed(2) }}%</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑥坏账调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentAdjustment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑥ = ⑤×②A + ①×(②A-②)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentAdjustment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="阶段" min-width="90" align="center">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" :model-value="row.stage" size="small"
                @change="(v: string) => updateField(row.id, 'stage', v)">
                <el-option label="Stage1" value="Stage1" />
                <el-option label="Stage2" value="Stage2" />
                <el-option label="Stage3" value="Stage3" />
              </el-select>
              <span v-else>{{ row.stage }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="OCI影响" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.ociImpact" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'ociImpact', v)" />
              <span v-else>{{ fmtNum(row.ociImpact) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引" min-width="80" align="center">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <GtIndexChip :value="row.indexRef" @update="(v: string) => updateField(row.id, 'indexRef', v)" />
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 审定数列 (10列) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="⑦审定余额" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjBalance) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑦ = ① + ⑤" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjBalance) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑧审定坏账" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjImpairment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑧ = ③ + ⑥" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjImpairment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑨审定账面价值" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjBookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑨ = ⑦ - ⑧" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjBookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="审定公允价值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.adjFairValue" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'adjFairValue', v)" />
              <span v-else>{{ fmtNum(row.adjFairValue) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="上年坏账" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.priorImpairment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'priorImpairment', v)" />
              <span v-else>{{ fmtNum(row.priorImpairment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年计提" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-tooltip content="本年计提 = max(0, ⑧ - 上年坏账)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.currentProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年转回" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.currentReversal" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'currentReversal', v)" />
              <span v-else>{{ fmtNum(row.currentReversal) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="OCI调整" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.ociAdjustment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'ociAdjustment', v)" />
              <span v-else>{{ fmtNum(row.ociAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="差异说明" min-width="150">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.differenceNote" size="small"
                @change="(v: string) => updateField(row.id, 'differenceNote', v)" />
              <span v-else>{{ row.differenceNote }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isSubtotal && !row._isTotal" title="确认删除？"
            @confirm="calc.removeRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiConclusion">
          🤖 AI生成
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入减值准备测算的审计结论..."
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>③ 坏账准备 = ① 摊余成本余额 × ② 预期信用损失率</li>
        <li>④ 账面价值 = ① - ③</li>
        <li>⑥ 坏账调整 = ⑤×②A + ①×(②A-②)，可为负值（代表冲回）</li>
        <li>⑦ 审定余额 = ① + ⑤</li>
        <li>⑧ 审定坏账 = ③ + ⑥</li>
        <li>⑨ 审定账面价值 = ⑦ - ⑧</li>
        <li>本年计提 = max(0, ⑧ - 上年坏账)</li>
        <li>本年转回 = max(0, 上年坏账 - ⑧)</li>
        <li>按Stage分组：Stage1(12个月ECL) / Stage2(整个存续期ECL) / Stage3(存续期ECL+净额利息)</li>
        <li>其他债权投资减值按摊余成本口径计算（非公允价值口径）</li>
      </ul>
    </details>

    <!-- 隐藏 file input 用于导入 -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabImpairmentCalc.vue — G6-12 减值准备测算表（2区段Tab + Stage分组）
 *
 * - el-segmented 切换 Tab1(未审+调整 12列) / Tab2(审定数 10列)
 * - 行共享同一reactive数组，Tab切换只改可见列（不销毁表格实例）
 * - selectedRowIndex跨Tab保持（行同步）
 * - Stage1/Stage2/Stage3分组 + 小计行 + 总计行
 * - 公式列: 虚线下划线 + cursor:help + el-tooltip显示公式来源
 * - 导入导出 dropdown + AI按钮 + 复核按钮 + GtIndexChip
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG6EclImpairmentCalc } from '../../composables/useG6EclImpairmentCalc'
import { useG6EclImportExport } from '../../composables/useG6EclImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ImpairmentCalcRow } from '../../composables/useG6EclFormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG6EclImpairmentCalc()
const conclusion = ref('')
const activeTab = ref<'tab1' | 'tab2'>('tab1')
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const importExport = useG6EclImportExport({ wpId: wpIdRef })

const importExportOptions = computed(() => importExport.getDropdownOptions('G6-12'))

async function handleImportExportCommand(command: string) {
  const [action, sheet] = command.split(':') as [string, string]
  if (action === 'export-template') {
    await importExport.exportTemplate('G6-12')
  } else if (action === 'export-data') {
    await importExport.exportData('G6-12')
  } else if (action === 'import-data') {
    fileInputRef.value?.click()
  }
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await importExport.importData('G6-12', file)
  if (result) {
    ElMessage.success(`导入成功：${result.rowCount}行`)
  }
  input.value = ''
}

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '未审+调整', value: 'tab1' },
  { label: '审定数', value: 'tab2' },
]

// ─── 只读属性便利ref ─────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly)

// ─── Stage分组显示行（插入小计和总计行） ─────────────────────────────────────

interface DisplayRow extends ImpairmentCalcRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _groupLabel?: string
}

const displayRows = computed<DisplayRow[]>(() => {
  const grouped = calc.groupedRows.value
  const result: DisplayRow[] = []

  // Stage1
  if (grouped.stage1.rows.length > 0) {
    for (const r of grouped.stage1.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyRow(),
      _isSubtotal: true,
      _groupLabel: 'Stage1',
      ...grouped.stage1.subtotal,
    } as DisplayRow)
  }

  // Stage2
  if (grouped.stage2.rows.length > 0) {
    for (const r of grouped.stage2.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyRow(),
      _isSubtotal: true,
      _groupLabel: 'Stage2',
      ...grouped.stage2.subtotal,
    } as DisplayRow)
  }

  // Stage3
  if (grouped.stage3.rows.length > 0) {
    for (const r of grouped.stage3.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyRow(),
      _isSubtotal: true,
      _groupLabel: 'Stage3',
      ...grouped.stage3.subtotal,
    } as DisplayRow)
  }

  // 总计行
  result.push({
    ...createEmptyRow(),
    _isTotal: true,
    ...grouped.grandTotal,
  } as DisplayRow)

  return result
})

function createEmptyRow(): ImpairmentCalcRow {
  return {
    id: crypto.randomUUID(),
    seq: 0,
    investProject: '',
    stageGroup: 'Stage1',
    amortizedCost: 0,
    fairValue: 0,
    creditLossRate: 0,
    impairmentProvision: 0,
    bookValue: 0,
    balanceAdjustment: 0,
    adjustedCreditLossRate: 0,
    impairmentAdjustment: 0,
    stage: 'Stage1',
    ociImpact: 0,
    indexRef: '',
    adjBalance: 0,
    adjImpairment: 0,
    adjBookValue: 0,
    adjFairValue: 0,
    priorImpairment: 0,
    currentProvision: 0,
    currentReversal: 0,
    ociAdjustment: 0,
    differenceNote: '',
  }
}

// ─── 行同步（selectedRowIndex 跨Tab保持） ───────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isSubtotal || row._isTotal) return
  const idx = calc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) calc.selectedRowIndex.value = idx
}

// ─── 行样式 ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  if (row._isTotal) return 'row-total'
  return ''
}

// ─── 字段更新（触发公式重算） ───────────────────────────────────────────────

function updateField(id: string, field: keyof ImpairmentCalcRow, value: any) {
  const row = calc.rows.value.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value ?? 0
  calc.recalcRow(row)
}

// ─── 动态行增删（ElMessageBox.prompt） ──────────────────────────────────────

async function handleAddRow() {
  await calc.addRow('Stage1')
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成减值测算结论(impairment-conclusion)将在AI模块完成后启用')
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载（从htmlData初始化） ───────────────────────────────────────────

onMounted(() => {
  if (props.htmlData?.impairmentCalc) {
    const data = props.htmlData.impairmentCalc
    if (data.rows) calc.loadRows(data.rows)
    if (data.conclusion) conclusion.value = data.conclusion
  }
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    rows: calc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g6-impairment-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 14px;
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
  border-radius: 0 4px 4px 0;
}
.methodology-icon {
  margin-right: 6px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.impairment-table {
  font-size: var(--wp-font-size, 13px);
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 50px;
  text-align: right;
}

/* 小计行 */
:deep(.row-subtotal) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
:deep(.row-subtotal td) {
  background-color: #f5f7fa !important;
}

.subtotal-label {
  color: #606266;
  font-weight: 600;
  font-size: 12px;
}

.subtotal-num {
  font-weight: 600;
  color: #303133;
}

/* 总计行 */
:deep(.row-total) {
  background-color: #ecf5ff !important;
  font-weight: 700;
}
:deep(.row-total td) {
  background-color: #ecf5ff !important;
}

.total-label {
  color: #409eff;
  font-weight: 700;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
