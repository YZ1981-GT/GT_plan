<template>
  <div class="k4-tab-detail">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>K4-2明细表按项目逐笔列示其他流动负债余额。<strong>负债类科目</strong>：期末=期初+贷方(增加)-借方(减少)。明细合计应与K4-1审定表审定数一致。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>所有应当记录的其他流动负债均已记录（负债完整性重点）；</li>
        <li><b>存在：</b>资产负债表中记录的其他流动负债是存在的，且已记录在恰当的账户中；</li>
        <li><b>计价和分摊：</b>其他流动负债以恰当的金额包括在财务报表中，相关计价或分摊调整已恰当记录。</li>
      </ol>
    </el-alert>

    <!-- K4-2 ↔ K4-1 交叉验证 -->
    <el-alert v-if="k41VsK42Diff > 1" type="warning" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>K4-2 明细审定合计（{{ fmtAmt(detail.subtotals.value.auditedEnd) }}）与 K4-1 审定合计（{{ fmtAmt(k41AuditedTotal) }}）差异 {{ fmtAmt(k41VsK42Diff) }} 元</template>
    </el-alert>
    <el-alert v-else-if="k41AuditedTotal > 0 && detail.detailRows.value.length > 0" type="success" :closable="false" show-icon style="margin-bottom:10px">
      <template #title>✓ K4-2 明细审定合计与 K4-1 审定合计核对一致</template>
    </el-alert>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K4-2 其他流动负债明细表</h3>
      <div class="head-actions">
        <el-button v-if="!isReadonly && k41HasData" size="small" type="warning" plain @click="seedFromK41">从K4-1带入</el-button>
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 2区段 el-segmented + 列设置 -->
    <div class="segment-toolbar">
      <el-segmented
        v-model="activeSegmentIdx"
        :options="segmentOptions"
        size="default"
        class="segment-bar"
      />
      <el-popover trigger="click" :width="280" placement="bottom-end">
        <template #reference>
          <el-button size="small" circle title="列设置">⚙</el-button>
        </template>
        <div class="col-prefs-popover">
          <div class="cp-header">
            <span class="cp-title">列显隐设置</span>
            <el-button size="small" link @click="colPrefs.resetAll()">重置</el-button>
          </div>
          <div class="cp-presets">
            <el-tag
              v-for="p in colPrefs.presets"
              :key="p.name"
              :type="colPrefs.activePreset.value === p.name ? 'primary' : 'info'"
              size="small"
              effect="plain"
              style="cursor:pointer;margin-right:4px"
              @click="colPrefs.applyPreset(p.name)"
            >{{ p.name }}</el-tag>
          </div>
          <el-divider style="margin:8px 0" />
          <div v-for="(cols, group) in colPrefs.columnsByGroup.value" :key="group" class="cp-group">
            <div class="cp-group-label">{{ { basic: '基础', check: '检查', adjust: '调整' }[group] }}</div>
            <div v-for="col in cols" :key="col.key" class="cp-item">
              <el-checkbox
                :model-value="col.visible"
                :disabled="col.alwaysShow"
                size="small"
                @change="colPrefs.toggleColumn(col.key)"
              >{{ col.label }}</el-checkbox>
            </div>
          </div>
          <el-divider style="margin:8px 0" />
          <el-button size="small" @click="colPrefs.hideEmptyColumns(detail.detailRows.value)">隐藏空列</el-button>
        </div>
      </el-popover>
    </div>

    <!-- 表格 -->
    <el-table
      :data="detail.detailRows.value"
      border
      size="small"
      :max-height="520"
      class="detail-table"
      show-summary
      :summary-method="summaryMethod"
    >
      <!-- ═══ 区段0 基础 ═══ -->
      <template v-if="activeSegmentIdx === 0">
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }">{{ row.seqNo }}</template>
        </el-table-column>
        <el-table-column label="项目" min-width="200">
          <template #default="{ row }">
            <span>{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="性质" min-width="140">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.nature"
              size="small"
              placeholder="选择性质"
              @change="(v: string) => detail.updateCell(row.rowId, 'nature', v)"
            >
              <el-option v-for="opt in natureOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.beginBalance"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'beginBalance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加(贷方)" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.increase"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'increase', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少(借方)" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.decrease"
              size="small"
              :controls="false"
              class="amount-input"
              @change="(v: number) => detail.updateCell(row.rowId, 'decrease', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="130" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末=期初+贷方-借方（负债类）" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段1 检查 ═══ -->
      <template v-if="activeSegmentIdx === 1">
        <el-table-column label="项目" min-width="180">
          <template #default="{ row }">
            <span>{{ row.projectName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增减原因" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.increaseReason" size="small" placeholder="增减原因" @change="(v: string) => detail.updateCell(row.rowId, 'increaseReason', v)" />
            <span v-else>{{ row.increaseReason || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherRef" size="small" placeholder="凭证号" @change="(v: string) => detail.updateCell(row.rowId, 'voucherRef', v)" />
            <span v-else>{{ row.voucherRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后偿付金额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="次年序时账2245借方按项目归集（验证完整性核心证据）" placement="top">
              <span style="border-bottom:1px dashed;cursor:help">期后偿付 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.postPayment" size="small" :controls="false" class="amount-input" @change="(v: number) => detail.updateCell(row.rowId, 'postPayment', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.postPayment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="偿付日期" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.postPaymentDate" size="small" placeholder="YYYY-MM-DD" @change="(v: string) => detail.updateCell(row.rowId, 'postPaymentDate', v)" />
            <span v-else>{{ row.postPaymentDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核查结论" min-width="140">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.checkConclusion" size="small" placeholder="结论" @change="(v: string) => detail.updateCell(row.rowId, 'checkConclusion', v)">
              <el-option v-for="opt in conclusionOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else>{{ row.checkConclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(v: string) => detail.updateCell(row.rowId, 'remark', v)" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 区段2 调整（未审→期初调整/账项调整/重分类调整→审定，对齐源模板）═══ -->
      <template v-if="activeSegmentIdx === 2">
        <el-table-column label="项目" min-width="140" fixed>
          <template #default="{ row }"><span>{{ row.projectName }}</span></template>
        </el-table-column>
        <el-table-column label="未审期末" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.endBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="期初调整" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingAdjust" size="small" :controls="false" class="amount-input" @change="(v: number) => detail.updateCell(row.rowId, 'openingAdjust', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.openingAdjust) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整-增" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ajeIncrease" size="small" :controls="false" class="amount-input" @change="(v: number) => detail.updateCell(row.rowId, 'ajeIncrease', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.ajeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账项调整-减" min-width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ajeDecrease" size="small" :controls="false" class="amount-input" @change="(v: number) => detail.updateCell(row.rowId, 'ajeDecrease', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.ajeDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类-增" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.rjeIncrease" size="small" :controls="false" class="amount-input" @change="(v: number) => detail.updateCell(row.rowId, 'rjeIncrease', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rjeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类-减" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.rjeDecrease" size="small" :controls="false" class="amount-input" @change="(v: number) => detail.updateCell(row.rowId, 'rjeDecrease', v ?? 0)" />
            <span v-else class="amount-cell">{{ fmtAmt(row.rjeDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定期初" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.auditedBegin) }}</span></template>
        </el-table-column>
        <el-table-column label="审定期末" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="审定期初 + 审定增加 − 审定减少" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.auditedEnd) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（所有区段共享） -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" type="danger" link @click="handleRemoveRow($index)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部统计卡片 (Req 3.4: 项目数/期末合计) -->
    <div class="stats-bar">
      <el-tag type="info" effect="plain">项目数: {{ detail.subtotals.value.count }}</el-tag>
      <el-tag type="primary" effect="plain">未审期末合计: {{ fmtAmt(detail.subtotals.value.endBalance) }}</el-tag>
      <el-tag type="success" effect="plain">期初合计: {{ fmtAmt(detail.subtotals.value.beginBalance) }}</el-tag>
      <el-tag type="warning" effect="plain">审定期末合计: {{ fmtAmt(detail.subtotals.value.auditedEnd) }}</el-tag>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>18列拆为2区段Tab切换（基础/检查），行数据同步</li>
        <li><strong>负债类科目</strong>：期末余额=期初余额+本期增加(贷方)-本期减少(借方)</li>
        <li>新增行需弹窗输入项目名称后创建</li>
        <li>明细合计应与K4-1审定表其他流动负债审定数一致（交叉验证）</li>
        <li>导入导出支持按模板批量录入明细</li>
        <li>性质分类：预提费用/待转销项税额/代扣代缴/短期融资/其他</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K4TabDetail.vue — K4-2 明细表（18列2区段+动态行+导入导出）
 * Spec: .kiro/specs/k4-other-current-liabilities/ | Task: 4.3
 * Requirements: 3.1-3.4
 *
 * 2区段Tab切换(el-segmented: 基础|检查)，同行同步
 * 区段0 基础：序号/项目/性质(下拉)/期初/本期增加(贷方)/本期减少(借方)/期末(公式:虚线)
 * 区段1 检查：项目(只读)/增减原因/凭证号/核查结论(下拉)/备注
 * 动态行新增：el-button"+ 新增"→ElMessageBox.prompt输入项目名称确认后创建
 * 底部统计卡片：项目数/期末合计
 * el-dropdown导入导出(导出模板/导出数据/导入数据)——useK4ImportExport消费
 * 公式列虚线下划线+cursor:help+tooltip
 * 合计行固定底部
 * 表格字体13px
 * AI按钮(section标题行右侧)
 * 编制提示(details折叠底部)
 * Consumes: useK4Detail composable + useK4ImportExport composable
 *
 * 科目：2245 其他流动负债（**贷方/负债类**）
 */
import { ref, computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK4Detail } from '../../composables/useK4Detail'
import { useK4ImportExport } from '../../composables/useK4ImportExport'
import { useK4DetailColumnPrefs } from '../../composables/useK4DetailColumnPrefs'
import http from '@/utils/http'
import type { WorkpaperRuntimeContext } from '../../composables/useWorkpaperScaffold'
import { WorkpaperRuntimeContextKey } from '../../composables/useWorkpaperScaffold'

// ─── Props / Emits ───────────────────────────────────────────────────────────

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

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)

// ─── Constants ───────────────────────────────────────────────────────────────

const natureOptions = ['预提费用', '待转销项税额', '代扣代缴', '短期融资', '其他']
const conclusionOptions = ['正常', '异常', '需关注', '待确认', '确认属流动负债', '已跨期应重分类', '计提依据不充分']

const segmentOptions = [
  { label: '基础', value: 0 },
  { label: '检查', value: 1 },
  { label: '调整', value: 2 },
]

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const detail = useK4Detail({
  allResponses: allResponsesRef as any,
  saveResponse: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

// 列设置 composable
const colPrefs = useK4DetailColumnPrefs()

const {
  exportTemplate,
  exportData,
  importData,
} = useK4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetCode: 'K4-2',
})

// ─── 区段状态 ────────────────────────────────────────────────────────────────

const activeSegmentIdx = ref(0)

// ─── 合计行 (show-summary) ───────────────────────────────────────────────────

function summaryMethod({ columns }: { columns: any[] }): string[] {
  return columns.map((col, idx) => {
    if (idx === 0) return '合计'
    const key = col.property
    if (!key) return ''

    // 基础区段合计
    if (activeSegmentIdx.value === 0) {
      if (['beginBalance', 'increase', 'decrease', 'endBalance'].includes(key)) {
        const total = detail.detailRows.value.reduce((sum, r) => sum + ((r as any)[key] || 0), 0)
        return fmtAmt(total)
      }
    }
    return ''
  })
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await detail.addRow()
}

function handleRemoveRow(idx: number) {
  const row = detail.detailRows.value[idx]
  if (!row) return
  ElMessageBox.confirm(
    `确定删除项目"${row.projectName}"？删除后不可恢复。`,
    '确认删除',
    {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    },
  ).then(() => {
    detail.removeRow(idx)
    ElMessage.success('已删除')
  }).catch(() => {
    // 用户取消
  })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate() }
function handleExportData() { exportData() }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    await importData(file)
  }
  input.click()
}

// ─── AI / 复核 / 版本快照 ────────────────────────────────────────────────────

async function handleAiGenerate(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请根据K4-2其他流动负债明细表数据，分析各项目增减变动原因并生成审计核查建议',
      context: {
        科目: '2245 其他流动负债（负债类，完整性为核心认定）',
        项目数: String(detail.detailRows.value.length),
        期末合计: String(detail.subtotals.value.endBalance),
        审定合计: String(detail.subtotals.value.auditedEnd),
        性质分布: detail.detailRows.value.map(r => r.nature || '未分类').join('、'),
      },
      existingContent: '',
      section: 'K4-2-detail-analysis',
    })
    const content = res?.data?.data?.content || res?.data?.content || ''
    if (content) {
      ElMessage.success('AI 分析已生成，请查看控制台')
      console.log('[K4-2 AI]', content)
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败')
  }
}

function handleReview() {
  openReviewDialog('K4-2-detail')
}

function scheduleAutoSnapshot(): void {
  try { runtime?.version?.scheduleAutoSnapshot?.() } catch { /* silent */ }
}

// ─── K4-1 ↔ K4-2 交叉验证 ───────────────────────────────────────────────────

const k41AuditedTotal = computed(() => {
  const item = props.allResponses.get('K4-1-audited-total')
  const v = item?.remark ?? item?.value ?? item
  return Number(v) || 0
})

const k41VsK42Diff = computed(() => {
  if (k41AuditedTotal.value === 0 || detail.detailRows.value.length === 0) return 0
  return Math.abs(k41AuditedTotal.value - detail.subtotals.value.auditedEnd)
})

// ─── 从 K4-1 审定表带入项目种子 ──────────────────────────────────────────────

const k41HasData = computed(() => {
  // 检查 K4-1 是否有已填写的行数据
  const rowCount = Number(props.allResponses.get('K4-1-row-count')?.remark ?? props.allResponses.get('K4-1-row-count')?.value ?? 0)
  return rowCount > 0 || k41AuditedTotal.value > 0
})

async function seedFromK41(): Promise<void> {
  if (detail.detailRows.value.length > 0) {
    try {
      await ElMessageBox.confirm(
        '明细表已有数据，从K4-1带入将追加新项目（不覆盖已有行）。是否继续？',
        '从K4-1审定表带入',
        { confirmButtonText: '继续', cancelButtonText: '取消', type: 'info' },
      )
    } catch { return }
  }

  const ROW_LABELS = ['短期应付债券', '政府补助', '待转销项税额', '应付退货款', '其他']
  const existingNames = new Set(detail.detailRows.value.map(r => r.projectName))
  let added = 0

  for (let i = 0; i < ROW_LABELS.length; i++) {
    const label = ROW_LABELS[i]
    if (existingNames.has(label)) continue
    // 从 K4-1 读取该行的期初和期末
    const begin = Number(props.allResponses.get(`K4-1-r${i}-begin`)?.remark ?? 0) || 0
    const end = Number(props.allResponses.get(`K4-1-r${i}-unadj`)?.remark ?? 0) || 0
    if (begin === 0 && end === 0) continue // 跳过无数据行
    await detail.addRow(label)
    // 回填期初余额
    const newRow = detail.detailRows.value[detail.detailRows.value.length - 1]
    if (newRow) {
      detail.updateCell(newRow.rowId, 'beginBalance', begin)
      detail.updateCell(newRow.rowId, 'nature', label === '其他' ? '其他' : label)
    }
    added++
  }

  if (added > 0) {
    ElMessage.success(`已从K4-1带入 ${added} 个项目`)
    scheduleAutoSnapshot()
  } else {
    ElMessage.info('K4-1无可带入的新项目（已存在或无数据）')
  }
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k4-tab-detail {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

/* 标题栏 */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* el-segmented 区段栏 + 列设置 */
.segment-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.segment-bar {
  flex: 1;
}

/* 列设置 popover */
.col-prefs-popover { font-size: 12px; }
.cp-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.cp-title { font-weight: 600; }
.cp-presets { margin-bottom: 4px; }
.cp-group { margin-bottom: 6px; }
.cp-group-label { font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 2px; font-weight: 500; }
.cp-item { padding: 1px 0; }

/* 表格 */
.detail-table {
  font-size: var(--wp-font-size, 13px);
}

.amount-cell {
  font-variant-numeric: tabular-nums;
}

.amount-input {
  width: 100%;
}

.amount-input :deep(.el-input__inner) {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 合计行固定底部 */
.detail-table :deep(.el-table__footer-wrapper) {
  font-weight: 600;
  position: sticky;
  bottom: 0;
  z-index: 2;
  background: var(--el-bg-color);
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 12px;
  margin-top: 12px;
  padding: 10px 0;
  flex-wrap: wrap;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
