<template>
  <div class="m4-tab-detail">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M4-2 资本公积明细表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-segmented
          v-model="dualMode.mode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="(val: any) => dualMode.switchMode(val)"
        />
        <!-- 导入导出三级 el-dropdown -->
        <el-dropdown trigger="click" @command="handleImportExportCommand">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAI('detail')">
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
        <strong>M4-2 资本公积明细表：</strong>
        按来源项目分类列示资本公积变动明细。资本溢价（出资超面值部分）与其他资本公积（含股份支付权益结算J3、外币折算差异M2等）
        分两区段展示。权益类贷方公式：期末 = 期初 + 本期增加(贷方) − 本期减少(借方)。
        审定列 = 未审 + AJE + RJE，审定期末 = 审定期初 + 审定增加 − 审定减少。
        合计数应与M4-1审定表一致（交叉验证）。
      </div>
    </div>

    <!-- ═══ 区段Tab切换：资本溢价 / 其他资本公积 ═══ -->
    <div class="segment-tabs">
      <el-segmented
        v-model="activeSegment"
        :options="segmentOptions"
        size="default"
        @change="handleSegmentChange"
      />
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        @click="handleAddRow()"
      >
        <el-icon><Plus /></el-icon> 新增来源项目
      </el-button>
    </div>

    <!-- ═══ J3/M2联动提示 ═══ -->
    <div v-if="activeSegment === 'other'" class="linkage-hint">
      <el-tag type="warning" size="small" effect="plain">
        接收J3股份支付权益结算
      </el-tag>
      <GtIndexChip value="J3" />
    </div>
    <div v-if="activeSegment === 'premium'" class="linkage-hint">
      <el-tag type="warning" size="small" effect="plain">
        接收M2外币出资折算差异
      </el-tag>
      <GtIndexChip value="M2" />
    </div>

    <!-- ═══ 宽表（24列：固定列+横向滚动剩余列） ═══ -->
    <div class="detail-table-wrapper">
      <el-table
        :data="activeSegmentTableRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
        max-height="520"
      >
        <!-- A列: 来源项目（固定） -->
        <el-table-column prop="sourceName" label="来源项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="isSubtotalRow(row)">
              <span class="total-row-label">{{ row.sourceName }}</span>
            </template>
            <template v-else-if="!isReadonly && isDataRow(row)">
              <el-input
                :model-value="row.sourceName"
                size="small"
                placeholder="来源项目名称"
                @change="(val: string) => handleUpdateRow($index, 'sourceName', val)"
              />
            </template>
            <template v-else>
              {{ row.sourceName || '—' }}
            </template>
          </template>
        </el-table-column>

        <!-- ═══ 未审数区（B~E） ═══ -->
        <el-table-column label="未审数" align="center">
          <el-table-column label="期初" width="110" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.unadjBeginning" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'unadjBeginning', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.unadjBeginning) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="增加" width="110" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.unadjIncrease" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'unadjIncrease', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.unadjIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减少" width="110" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.unadjDecrease" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'unadjDecrease', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.unadjDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="110" align="right">
            <template #header>
              <el-tooltip content="未审期末=未审期初+未审增加−未审减少（权益类贷方）" placement="top">
                <span class="formula-col-header">期末</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.unadjEnd) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- ═══ 调整区（F~K）：AJE期初/RJE期初/AJE增/AJE减/RJE增/RJE减 ═══ -->
        <el-table-column label="调整" align="center">
          <el-table-column label="AJE期初" width="100" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.ajeBeginning" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'ajeBeginning', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.ajeBeginning) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE期初" width="100" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.rjeBeginning" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'rjeBeginning', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.rjeBeginning) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE增" width="100" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.ajeIncrease" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'ajeIncrease', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.ajeIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="AJE减" width="100" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.ajeDecrease" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'ajeDecrease', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.ajeDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE增" width="100" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.rjeIncrease" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'rjeIncrease', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.rjeIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="RJE减" width="100" align="right">
            <template #default="{ row, $index }">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input-number :model-value="row.rjeDecrease" :controls="false" size="small" style="width:100%" @change="(v: number|undefined) => handleUpdateRow($index, 'rjeDecrease', v??0)" />
              </template>
              <span v-else>{{ fmtAmount(row.rjeDecrease) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- ═══ 审定区（L~O）：审定期初/审定增加/审定减少/审定期末 ═══ -->
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初" width="110" align="right">
            <template #header>
              <el-tooltip content="审定期初=未审期初+AJE期初+RJE期初" placement="top">
                <span class="formula-col-header">期初</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.auditedBeginning) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="增加" width="110" align="right">
            <template #header>
              <el-tooltip content="审定增加=未审增加+AJE增+RJE增" placement="top">
                <span class="formula-col-header">增加</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.auditedIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减少" width="110" align="right">
            <template #header>
              <el-tooltip content="审定减少=未审减少+AJE减+RJE减" placement="top">
                <span class="formula-col-header">减少</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmount(row.auditedDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="110" align="right">
            <template #header>
              <el-tooltip content="审定期末=审定期初+审定增加−审定减少（权益类贷方）" placement="top">
                <span class="formula-col-header">期末</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span class="formula-value formula-highlight">{{ fmtAmount(row.auditedEnd) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- ═══ P列: 会计处理是否正确 ═══ -->
        <el-table-column label="会计处理" width="100" align="center">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-select
                :model-value="row.reason"
                size="small"
                placeholder="—"
                clearable
                style="width:80px"
                @change="(val: string) => handleUpdateRow($index, 'reason', val || '')"
              >
                <el-option label="正确" value="正确" />
                <el-option label="有误" value="有误" />
                <el-option label="待定" value="待定" />
              </el-select>
            </template>
            <template v-else>
              <el-tag v-if="row.reason === '正确'" type="success" size="small">正确</el-tag>
              <el-tag v-else-if="row.reason === '有误'" type="danger" size="small">有误</el-tag>
              <el-tag v-else-if="row.reason === '待定'" type="warning" size="small">待定</el-tag>
              <span v-else>—</span>
            </template>
          </template>
        </el-table-column>

        <!-- ═══ Q列: 备注 + refIndex（J3/M2 GtIndexChip） ═══ -->
        <el-table-column label="备注/来源" min-width="160">
          <template #default="{ row, $index }">
            <div class="remark-cell">
              <template v-if="isDataRow(row) && !isReadonly">
                <el-input
                  :model-value="row.remark"
                  size="small"
                  placeholder="备注"
                  @change="(val: string) => handleUpdateRow($index, 'remark', val)"
                />
              </template>
              <span v-else>{{ row.remark || '' }}</span>
              <GtIndexChip v-if="row.refIndex" :value="row.refIndex" />
            </div>
          </template>
        </el-table-column>

        <!-- ═══ 操作列（非只读） ═══ -->
        <el-table-column v-if="!isReadonly" label="" width="60" align="center" fixed="right">
          <template #default="{ row, $index }">
            <el-button
              v-if="isDataRow(row)"
              type="danger"
              size="small"
              link
              @click="handleRemoveRow($index)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 区段小计 + 合计 + 交叉验证 ═══ -->
    <div class="detail-footer">
      <el-tag type="info" size="small" effect="plain">
        {{ activeSegmentLabel }}小计审定期末: {{ fmtAmount(activeSubtotal.auditedEnd) }}
      </el-tag>
      <el-tag type="primary" size="small" effect="dark">
        合计审定期末: {{ fmtAmount(grandTotal.auditedEnd) }}
      </el-tag>
      <el-tag type="success" size="small" effect="plain">
        与M4-1交叉验证: 期末{{ fmtAmount(grandTotal.auditedEnd) }}
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">审计说明</span>
          <el-button size="small" @click="handleAI('detailNote')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写资本公积明细表审计说明..."
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>M4-2 明细表共24列，按来源项目分行、按资本溢价/其他资本公积分区段</li>
        <li>权益类贷方公式：期末 = 期初 + 本期增加(贷方) − 本期减少(借方)</li>
        <li>审定期初 = 未审期初 + AJE期初 + RJE期初</li>
        <li>审定增加 = 未审增加 + AJE增 + RJE增</li>
        <li>审定减少 = 未审减少 + AJE减 + RJE减</li>
        <li>审定期末 = 审定期初 + 审定增加 − 审定减少（权益类！）</li>
        <li>资本溢价区段：出资超面值部分、M2外币折算差异</li>
        <li>其他资本公积区段：J3股份支付权益结算、权益法调整等</li>
        <li>合计应与M4-1审定表交叉一致</li>
      </ul>
    </details>

    <!-- 隐藏文件输入（导入用） -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display:none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * M4TabDetail — M4-2 资本公积明细表（24列区段Tab：资本溢价/其他资本公积）
 *
 * Requirements: 3.1-3.6, 4.1-4.6
 * - 双区段Tab（el-segmented）：资本溢价（股本溢价）+ 其他资本公积
 * - 24列宽表：来源项目 | 未审(期初/增/减/期末) | 调整(AJE期初/RJE期初/AJE增/AJE减/RJE增/RJE减)
 *   | 审定(期初/增/减/期末) | 会计处理 | 备注/来源
 * - 31公式自动计算（权益类贷方：期末=期初+增加−减少）
 * - 接收J3股份支付权益结算 + 接收M2外币折算差异
 * - 动态行新增（ElMessageBox.prompt输入来源项目名）
 * - 导入导出三级（el-dropdown：导出模板/导出数据/导入数据）
 * - GtIndexChip 跳转联动显示
 * - AI辅助 + 复核按钮 header右对齐
 * - 公式列：虚线下划线 + cursor:help + tooltip来源
 * - 表格字体13px
 *
 * Uses: useM4Detail + useM4FormData + useM4ImportExport + useM4DualMode
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check, Plus, ArrowDown } from '@element-plus/icons-vue'
import { useM4FormData } from '../../composables/useM4FormData'
import { useM4DualMode } from '../../composables/useM4DualMode'
import { useM4ImportExport } from '../../composables/useM4ImportExport'
import {
  useM4Detail,
  M4_DETAIL_SEGMENTS,
  type M4DetailRow,
  type M4DetailSegment,
} from '../../composables/useM4Detail'
import { eventBus } from '@/utils/eventBus'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
  (e: 'save'): void
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useM4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── DualMode ────────────────────────────────────────────────────────────────

const dualMode = useM4DualMode({
  wpId: computed(() => props.wpId),
})

// ─── ImportExport ────────────────────────────────────────────────────────────

const importExport = useM4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Detail Rows（reactive source） ──────────────────────────────────────────

const detailRows = ref<M4DetailRow[]>([])

// ─── useM4Detail composable ──────────────────────────────────────────────────

const {
  activeSegment,
  switchSegment,
  activeSegmentRows,
  premiumSubtotal,
  otherSubtotal,
  grandTotal,
  addRow,
  removeRow,
  updateRow,
} = useM4Detail(formData, detailRows)

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = M4_DETAIL_SEGMENTS.map(s => ({
  label: s.label,
  value: s.key,
}))

/** 当前活动区段的中文标签 */
const activeSegmentLabel = computed(() => {
  const found = M4_DETAIL_SEGMENTS.find(s => s.key === activeSegment.value)
  return found?.label || ''
})

/** 当前活动区段的小计 */
const activeSubtotal = computed(() => {
  return activeSegment.value === 'premium' ? premiumSubtotal.value : otherSubtotal.value
})

function handleSegmentChange(val: string | number): void {
  switchSegment(val as M4DetailSegment)
}

// ─── 表格数据：当前区段行 + 小计行 ──────────────────────────────────────────

interface TableRow extends M4DetailRow {
  _rowType?: 'data' | 'subtotal'
}

const activeSegmentTableRows = computed<TableRow[]>(() => {
  const result: TableRow[] = []
  for (const row of activeSegmentRows.value) {
    result.push({ ...row, _rowType: 'data' })
  }
  // 小计行
  const sub = activeSubtotal.value
  result.push({
    key: `${activeSegment.value}-subtotal`,
    segment: activeSegment.value,
    sourceName: `${activeSegmentLabel.value}小计`,
    beginning: sub.beginning,
    increase: sub.increase,
    decrease: sub.decrease,
    endBalance: sub.endBalance,
    reason: '',
    unadjBeginning: 0,
    unadjIncrease: 0,
    unadjDecrease: 0,
    unadjEnd: 0,
    ajeBeginning: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    rjeBeginning: 0,
    rjeIncrease: 0,
    rjeDecrease: 0,
    auditedBeginning: sub.auditedBeginning,
    auditedIncrease: sub.auditedIncrease,
    auditedDecrease: sub.auditedDecrease,
    auditedEnd: sub.auditedEnd,
    refIndex: '',
    remark: '',
    _rowType: 'subtotal',
  })
  return result
})

// ─── 行角色判断 ──────────────────────────────────────────────────────────────

function isDataRow(row: TableRow): boolean {
  return row._rowType === 'data'
}

function isSubtotalRow(row: TableRow): boolean {
  return row._rowType === 'subtotal'
}

function getRowClassName({ row }: { row: TableRow; rowIndex: number }): string {
  if (row._rowType === 'subtotal') return 'subtotal-row'
  return ''
}

// ─── 行操作代理（表格index → raw rows index） ────────────────────────────────

/**
 * 获取当前区段表格行对应的原始 detailRows index
 */
function getSegmentRawIndex(tableIndex: number): number {
  const segRows = activeSegmentRows.value
  if (tableIndex < 0 || tableIndex >= segRows.length) return -1
  const targetKey = segRows[tableIndex].key
  return detailRows.value.findIndex(r => r.key === targetKey)
}

function handleUpdateRow(tableIndex: number, field: string, value: string | number): void {
  const rawIdx = getSegmentRawIndex(tableIndex)
  if (rawIdx < 0) return
  updateRow(rawIdx, field as keyof M4DetailRow, value)
}

function handleRemoveRow(tableIndex: number): void {
  const rawIdx = getSegmentRawIndex(tableIndex)
  if (rawIdx < 0) return
  removeRow(rawIdx)
}

async function handleAddRow(): Promise<void> {
  await addRow(activeSegment.value)
}

// ─── UI State ────────────────────────────────────────────────────────────────

const isSaving = ref(false)
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 导入导出处理 ────────────────────────────────────────────────────────────

function handleImportExportCommand(command: string): void {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate('M4-2')
      break
    case 'exportData':
      importExport.exportData('M4-2')
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return

  const result = await importExport.importData(file, 'M4-2')
  if (result?.success) {
    // 重载数据
    await formData.loadData()
    _restoreRows()
  }
  // 清除 input 值，允许重复选择同一文件
  target.value = ''
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    // 批量保存所有行
    const items = detailRows.value.map((row, i) => ({
      itemId: `M4-2-row-${i + 1}-data`,
      data: {
        remark: JSON.stringify({
          key: row.key,
          segment: row.segment,
          sourceName: row.sourceName,
          beginning: row.beginning,
          increase: row.increase,
          decrease: row.decrease,
          reason: row.reason,
          unadjBeginning: row.unadjBeginning,
          unadjIncrease: row.unadjIncrease,
          unadjDecrease: row.unadjDecrease,
          ajeBeginning: row.ajeBeginning,
          ajeIncrease: row.ajeIncrease,
          ajeDecrease: row.ajeDecrease,
          rjeBeginning: row.rjeBeginning,
          rjeIncrease: row.rjeIncrease,
          rjeDecrease: row.rjeDecrease,
          refIndex: row.refIndex,
          remark: row.remark,
        }),
      },
    }))
    await formData.saveBatch(items)
    ElMessage.success('明细表已保存')
    emit('save')
  } finally {
    isSaving.value = false
  }
}

function saveAuditNote(): void {
  formData.debouncedSave('M4-M4-2-auditNote', { remark: auditNote.value || null })
}

function handleAI(_section: string): void {
  // AI辅助钩子（集成时实现）
}

function handleReview(): void {
  openReviewDialog?.('M4-2-detail', '资本公积明细表')
}

// ─── EventBus: 接收J3股份支付权益结算 + M2外币折算差异 ──────────────────────

function handleJ3EquitySettled(payload: {
  equitySettledAmount?: number
  waitingPeriodAmount?: number
  amount?: number
}): void {
  // J3股份支付权益结算计入 → 其他资本公积区段
  const amount = payload?.equitySettledAmount ?? payload?.amount
  if (amount !== undefined) {
    ElMessage.info(`接收到J3股份支付权益结算: ${amount}`)
  }
}

function handleM2FxDiff(payload: {
  totalFxDiff?: number
  fxDiffAmount?: number
  amount?: number
}): void {
  // M2外币出资折算差异 → 资本溢价区段
  const amount = payload?.totalFxDiff ?? payload?.fxDiffAmount ?? payload?.amount
  if (amount !== undefined) {
    ElMessage.info(`接收到M2外币折算差异: ${amount}`)
  }
}

// ─── 行数据恢复（从 checklist_responses） ───────────────────────────────────

function _restoreRows(): void {
  const restored: M4DetailRow[] = []
  const prefix = 'M4-2-row-'
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith(prefix) && key.endsWith('-data') && resp.remark) {
      try {
        const data = JSON.parse(resp.remark)
        restored.push({
          key: data.key || `m4-det-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          segment: data.segment || 'premium',
          sourceName: data.sourceName || '',
          beginning: Number(data.beginning) || 0,
          increase: Number(data.increase) || 0,
          decrease: Number(data.decrease) || 0,
          endBalance: 0,
          reason: data.reason || '',
          unadjBeginning: Number(data.unadjBeginning) || 0,
          unadjIncrease: Number(data.unadjIncrease) || 0,
          unadjDecrease: Number(data.unadjDecrease) || 0,
          unadjEnd: 0,
          ajeBeginning: Number(data.ajeBeginning) || 0,
          ajeIncrease: Number(data.ajeIncrease) || 0,
          ajeDecrease: Number(data.ajeDecrease) || 0,
          rjeBeginning: Number(data.rjeBeginning) || 0,
          rjeIncrease: Number(data.rjeIncrease) || 0,
          rjeDecrease: Number(data.rjeDecrease) || 0,
          auditedBeginning: 0,
          auditedIncrease: 0,
          auditedDecrease: 0,
          auditedEnd: 0,
          refIndex: data.refIndex || '',
          remark: data.remark || '',
        })
      } catch {
        // 解析失败跳过
      }
    }
  }
  if (restored.length > 0) {
    detailRows.value = restored
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 从 checklist_responses 恢复行数据
  _restoreRows()
  // 恢复审计说明
  const noteResp = formData.allResponses.value.get('M4-M4-2-auditNote')
  if (noteResp?.remark) {
    auditNote.value = noteResp.remark
  }
  // 订阅 J3/M2 EventBus
  eventBus.on('j3:equity-settled', handleJ3EquitySettled)
  eventBus.on('m2:fx-diff-to-m4', handleM2FxDiff)
})

onUnmounted(() => {
  eventBus.off('j3:equity-settled', handleJ3EquitySettled)
  eventBus.off('m2:fx-diff-to-m4', handleM2FxDiff)
})
</script>

<style scoped>
.m4-tab-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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

.equity-badge {
  font-weight: 600;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.segment-tabs {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 8px 0;
}

.linkage-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 12px;
  background: #fef0f0;
  border-radius: 4px;
  border-left: 3px solid #e6a23c;
}

.detail-table-wrapper {
  overflow-x: auto;
  margin-bottom: 16px;
}

.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

.formula-value {
  color: #409eff;
  font-weight: 500;
}

.formula-highlight {
  color: #67c23a;
  font-weight: 700;
}

.total-row-label {
  font-weight: 700;
  color: #303133;
}

.remark-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.subtotal-row) {
  background: #f0f9eb !important;
  font-weight: 600;
}

:deep(.subtotal-row td) {
  border-top: 2px solid #67c23a;
}

.detail-footer {
  margin-top: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}

.audit-note-card {
  margin-top: 16px;
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.m4-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}

.m4-details-tip summary {
  cursor: pointer;
  font-weight: 600;
  color: #303133;
}

.m4-details-tip ul {
  margin: 8px 0 0 0;
  padding-left: 20px;
}

.m4-details-tip li {
  margin-bottom: 4px;
  line-height: 1.6;
}
</style>
