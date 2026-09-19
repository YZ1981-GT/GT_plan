<template>
  <div class="m8-tab-detail">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M8-2 一般风险准备明细表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额·4104
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading === 'detail'" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>权益类贷方：期末 = 期初 + 贷方 − 借方。</strong>
        一般风险准备从净利润中计提时贷方增加（本期增加），转回/使用时借方减少（本期减少）。
        未审期末 E = 期初B + 增加C − 减少D；审定期初 L = B + F + G；审定增加 M = C + H + J；
        审定减少 N = D + I + K；审定期末 O = L + M − N。合计行自动汇总各列。
      </div>
    </div>

    <!-- ═══ 动态行操作按钮 ═══ -->
    <div class="action-bar">
      <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddRow">
        + 新增明细项目
      </el-button>
      <el-tag type="info" size="small" effect="plain">
        共 {{ detailRows.length }} 行明细
      </el-tag>
    </div>

    <!-- ═══ 18列明细表（分组列头） ═══ -->
    <el-table
      :data="displayRows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      :header-cell-style="{ fontSize: '13px', background: '#fafafa' }"
    >
      <!-- A列: 项目名称（固定列） -->
      <el-table-column prop="itemName" label="项目" min-width="140" fixed>
        <template #default="{ row, $index }">
          <template v-if="row._rowType === 'total'">
            <span class="total-row-label">{{ row.itemName }}</span>
          </template>
          <template v-else-if="!isReadonly">
            <el-input
              :model-value="row.itemName"
              size="small"
              placeholder="明细项目名称"
              @change="(val: string) => handleUpdate($index, 'itemName', val)"
            />
          </template>
          <template v-else>{{ row.itemName || '—' }}</template>
        </template>
      </el-table-column>

      <!-- ═══ 未审数 (B:E) ═══ -->
      <el-table-column label="未审数">
        <!-- B列: 期初数 -->
        <el-table-column label="期初数" width="100" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginning"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'beginning', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginning) }}</span>
          </template>
        </el-table-column>
        <!-- C列: 本期增加 -->
        <el-table-column label="本期增加" width="100" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.increase"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'increase', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <!-- D列: 本期减少 -->
        <el-table-column label="本期减少" width="100" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.decrease"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'decrease', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <!-- E列: 期末数（公式=B+C-D） -->
        <el-table-column width="110" align="right">
          <template #header>
            <el-tooltip content="E = 期初B + 增加C − 减少D（权益类贷方）" placement="top">
              <span class="formula-col-header">期末数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endBalance) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- ═══ 期初调整 (F:G) ═══ -->
      <el-table-column label="期初调整">
        <!-- F列: 账项调整(AJE) -->
        <el-table-column label="账项调整" width="95" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'beginAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginAje) }}</span>
          </template>
        </el-table-column>
        <!-- G列: 重分类(RJE) -->
        <el-table-column label="重分类" width="95" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.beginRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'beginRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.beginRje) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- ═══ 账项调整 (H:I) ═══ -->
      <el-table-column label="账项调整">
        <!-- H列: 增加 -->
        <el-table-column label="增加" width="90" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.increaseAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'increaseAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.increaseAje) }}</span>
          </template>
        </el-table-column>
        <!-- I列: 减少 -->
        <el-table-column label="减少" width="90" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.decreaseAje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'decreaseAje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.decreaseAje) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- ═══ 重分类调整 (J:K) ═══ -->
      <el-table-column label="重分类调整">
        <!-- J列: 增加 -->
        <el-table-column label="增加" width="90" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.increaseRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'increaseRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.increaseRje) }}</span>
          </template>
        </el-table-column>
        <!-- K列: 减少 -->
        <el-table-column label="减少" width="90" align="right">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input-number
                :model-value="row.decreaseRje"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'decreaseRje', val ?? 0)"
              />
            </template>
            <span v-else>{{ fmtAmount(row.decreaseRje) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- ═══ 审定数 (L:O) — 全部公式列 ═══ -->
      <el-table-column label="审定数">
        <!-- L列: 期初 (=B+F+G) -->
        <el-table-column width="110" align="right">
          <template #header>
            <el-tooltip content="L = 期初B + 期初AJE(F) + 期初RJE(G)" placement="top">
              <span class="formula-col-header">期初</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedBegin) }}</span>
          </template>
        </el-table-column>
        <!-- M列: 增加 (=C+H+J) -->
        <el-table-column width="110" align="right">
          <template #header>
            <el-tooltip content="M = 增加C + AJE增加(H) + RJE增加(J)" placement="top">
              <span class="formula-col-header">增加</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedIncrease) }}</span>
          </template>
        </el-table-column>
        <!-- N列: 减少 (=D+I+K) -->
        <el-table-column width="110" align="right">
          <template #header>
            <el-tooltip content="N = 减少D + AJE减少(I) + RJE减少(K)" placement="top">
              <span class="formula-col-header">减少</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.auditedDecrease) }}</span>
          </template>
        </el-table-column>
        <!-- O列: 期末 (=L+M-N) -->
        <el-table-column width="110" align="right">
          <template #header>
            <el-tooltip content="O = 审定期初L + 审定增加M − 审定减少N（权益类贷方）" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value formula-value-end">{{ fmtAmount(row.auditedEnd) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- ═══ 文件依据 (P) ═══ -->
      <el-table-column label="文件依据">
        <!-- P列: 索引号 -->
        <el-table-column label="索引号" width="90">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input
                :model-value="row.refIndex"
                size="small"
                placeholder="索引"
                @change="(val: string) => handleUpdate($index, 'refIndex', val)"
              />
            </template>
            <span v-else>{{ row.refIndex || '—' }}</span>
          </template>
        </el-table-column>
        <!-- Q列: 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row, $index }">
            <template v-if="isDataRow(row) && !isReadonly">
              <el-input
                :model-value="row.remark"
                size="small"
                placeholder="备注"
                @change="(val: string) => handleUpdate($index, 'remark', val)"
              />
            </template>
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 操作列（非只读时显示删除按钮） -->
      <el-table-column v-if="!isReadonly" label="" width="60" align="center" fixed="right">
        <template #default="{ row, $index }">
          <el-button
            v-if="isDataRow(row)"
            type="danger"
            size="small"
            link
            @click="handleRemoveRow($index)"
          >删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计 + 交叉验证状态 ═══ -->
    <div class="detail-footer">
      <el-tag type="primary" size="small" effect="dark">
        审定期末合计: {{ fmtAmount(detail.totals.value.auditedEnd) }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        审定期初合计: {{ fmtAmount(detail.totals.value.auditedBegin) }}
      </el-tag>
      <el-tag type="success" size="small" effect="plain">
        审定增加合计: {{ fmtAmount(detail.totals.value.auditedIncrease) }}
      </el-tag>
      <el-tag type="warning" size="small" effect="plain">
        审定减少合计: {{ fmtAmount(detail.totals.value.auditedDecrease) }}
      </el-tag>
    </div>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="m8-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>一般风险准备（4104）为<strong>权益类贷方科目</strong>：期末 = 期初 + 贷方（计提增加） − 借方（转回/使用减少）</li>
        <li><strong>未审数公式</strong>：E = B + C − D（未审期末 = 期初 + 增加 − 减少）</li>
        <li><strong>审定期初公式</strong>：L = B + F + G（未审期初 + 期初AJE + 期初RJE）</li>
        <li><strong>审定增加公式</strong>：M = C + H + J（未审增加 + AJE增加 + RJE增加）</li>
        <li><strong>审定减少公式</strong>：N = D + I + K（未审减少 + AJE减少 + RJE减少）</li>
        <li><strong>审定期末公式</strong>：O = L + M − N（审定期初 + 审定增加 − 审定减少，权益类贷方）</li>
        <li>合计行（Row 17）= 各列 SUM(Row 10:16)</li>
        <li>明细合计应与M8-1审定表一致（交叉验证）</li>
        <li>支持动态新增/删除明细行 + 导入/导出Excel</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M8TabDetail — M8-2 一般风险准备明细表（22公式 + 动态行 + 导入导出）
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 4.3
 * Requirements: 3.1-3.2, 3.8
 *
 * xlsx结构：24×18 (A:R), 56公式
 * 分组列头（Row 8-9 对应）：
 *   项目(A) | 未审数(B:E) | 期初调整(F:G) | 账项调整(H:I) | 重分类调整(J:K) | 审定数(L:O) | 文件依据(P:R)
 *
 * 公式列（虚线下划线+cursor:help+tooltip）：
 *   E = B + C − D（权益类贷方！）
 *   L = B + F + G
 *   M = C + H + J
 *   N = D + I + K
 *   O = L + M − N（权益类贷方！）
 *
 * 合计行 Row 17: SUM(row 10:16)
 * 动态行：ElMessageBox.prompt 输入名称后创建
 * 导入导出：el-dropdown "导入导出▾" 三级（useM8ImportExport）
 *
 * 科目：4104 一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { useM8FormData } from '../../composables/useM8FormData'
import { useM8Detail, M8_DETAIL_DEFAULT_ITEMS, type M8DetailRow } from '../../composables/useM8Detail'
import { useM8ImportExport } from '../../composables/useM8ImportExport'
import { useVersionTrail } from '../../composables/useVersionTrail'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

// ─── Inject复核对话 + AI ─────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── Composables ─────────────────────────────────────────────────────────────
const formData = useM8FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<M8DetailRow[]>([])
const detail = useM8Detail(formData, detailRows)

const importExport = useM8ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// Version trail (autoSnapshot on save)
useVersionTrail({
  projectId: computed(() => props.projectId),
  workpaperId: computed(() => props.wpId),
})

// ─── UI State ────────────────────────────────────────────────────────────────
const isSaving = ref(false)

// ─── Display rows: computed rows + 合计行 ────────────────────────────────────
interface DisplayRow extends M8DetailRow {
  _rowType?: 'data' | 'total'
}

const displayRows = computed<DisplayRow[]>(() => {
  const rows: DisplayRow[] = detail.computedRows.value.map(r => ({ ...r, _rowType: 'data' as const }))
  // 合计行
  const t = detail.totals.value
  rows.push({
    key: '__total__',
    itemName: '合 计',
    beginning: t.beginning,
    increase: t.increase,
    decrease: t.decrease,
    endBalance: t.endBalance,
    beginAje: t.beginAje,
    beginRje: t.beginRje,
    increaseAje: t.increaseAje,
    decreaseAje: t.decreaseAje,
    increaseRje: t.increaseRje,
    decreaseRje: t.decreaseRje,
    auditedBegin: t.auditedBegin,
    auditedIncrease: t.auditedIncrease,
    auditedDecrease: t.auditedDecrease,
    auditedEnd: t.auditedEnd,
    docReference: '',
    refIndex: '',
    remark: '',
    _rowType: 'total',
  })
  return rows
})

// ─── 行类型判断 ──────────────────────────────────────────────────────────────
function isDataRow(row: DisplayRow): boolean { return row._rowType === 'data' }
function getRowClassName({ row }: { row: DisplayRow; rowIndex: number }): string {
  if (row._rowType === 'total') return 'total-row'
  return ''
}

// ─── 行操作 ──────────────────────────────────────────────────────────────────
function handleUpdate(displayIndex: number, field: keyof M8DetailRow, value: any): void {
  // displayIndex可能包含合计行，需排除
  const row = displayRows.value[displayIndex]
  if (!row || row._rowType !== 'data') return
  // 找到在原始 detailRows 中的实际索引
  const rawIdx = detailRows.value.findIndex(r => r.key === row.key)
  if (rawIdx >= 0) {
    detail.updateRow(rawIdx, field, value)
  }
}

async function handleAddRow(): Promise<void> {
  await detail.addRow()
}

function handleRemoveRow(displayIndex: number): void {
  const row = displayRows.value[displayIndex]
  if (!row || row._rowType !== 'data') return
  const rawIdx = detailRows.value.findIndex(r => r.key === row.key)
  if (rawIdx < 0) return

  ElMessageBox.confirm(
    `确认删除明细项目"${row.itemName || '未命名'}"？`,
    '删除确认',
    { confirmButtonText: '确认删除', cancelButtonText: '取消', type: 'warning' },
  ).then(() => {
    detail.removeRow(rawIdx)
  }).catch(() => { /* 用户取消 */ })
}

// ─── 导入导出处理 ─────────────────────────────────────────────────────────────
function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate('M8-2')
      break
    case 'exportData':
      importExport.exportData('M8-2')
      break
    case 'importData':
      _triggerFileUpload()
      break
  }
}

function _triggerFileUpload(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importExport.importData('M8-2', file)
    if (result?.success) {
      // 重新加载数据
      await formData.loadData()
      _restoreRows()
    }
  }
  input.click()
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────
async function handleAI(section: string): Promise<void> {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const t = detail.totals.value
    const context: Record<string, string> = {
      科目: '4104 一般风险准备（权益类/贷方）',
      底稿: 'M8-2 一般风险准备明细表',
      审定期初合计: fmtAmount(t.auditedBegin),
      审定增加合计: fmtAmount(t.auditedIncrease),
      审定减少合计: fmtAmount(t.auditedDecrease),
      审定期末合计: fmtAmount(t.auditedEnd),
      明细行数: String(detailRows.value.length),
    }
    const text = await generateAiText({ section: `m8-detail-${section}`, context, existingContent: '' })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    ElMessageBox.alert(text, 'AI 辅助建议', { confirmButtonText: '知道了' }).catch(() => {})
  } catch { ElMessage.warning('AI 生成失败，请稍后重试') } finally { aiLoading.value = '' }
}

function handleReview(): void {
  openReviewDialog?.('M8-2-detail', '一般风险准备明细表')
}

// ─── 保存 ────────────────────────────────────────────────────────────────────
async function handleSave(): Promise<void> {
  isSaving.value = true
  try {
    // 保存所有行数据 + 合计
    for (let i = 0; i < detailRows.value.length; i++) {
      const row = detailRows.value[i]
      formData.debouncedSave(`M8-2-row-${i}-data`, {
        remark: JSON.stringify({
          key: row.key,
          itemName: row.itemName,
          beginning: row.beginning,
          increase: row.increase,
          decrease: row.decrease,
          beginAje: row.beginAje,
          beginRje: row.beginRje,
          increaseAje: row.increaseAje,
          decreaseAje: row.decreaseAje,
          increaseRje: row.increaseRje,
          decreaseRje: row.decreaseRje,
          docReference: row.docReference,
          refIndex: row.refIndex,
          remark: row.remark,
        }),
      })
    }
    // 保存行数 metadata
    formData.debouncedSave('M8-2-rowCount', { remark: String(detailRows.value.length) })
    emit('save')
  } finally {
    isSaving.value = false
  }
}

// ─── 从 checklist_responses 恢复行数据 ───────────────────────────────────────
function _restoreRows(): void {
  const restored: M8DetailRow[] = []
  for (const [key, resp] of formData.allResponses.value.entries()) {
    if (key.startsWith('M8-2-row-') && key.endsWith('-data') && resp.remark) {
      try {
        const d = JSON.parse(resp.remark)
        restored.push({
          key: d.key || `m8-detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          itemName: d.itemName || '',
          beginning: Number(d.beginning) || 0,
          increase: Number(d.increase) || 0,
          decrease: Number(d.decrease) || 0,
          endBalance: 0,
          beginAje: Number(d.beginAje) || 0,
          beginRje: Number(d.beginRje) || 0,
          increaseAje: Number(d.increaseAje) || 0,
          decreaseAje: Number(d.decreaseAje) || 0,
          increaseRje: Number(d.increaseRje) || 0,
          decreaseRje: Number(d.decreaseRje) || 0,
          auditedBegin: 0,
          auditedIncrease: 0,
          auditedDecrease: 0,
          auditedEnd: 0,
          docReference: d.docReference || '',
          refIndex: d.refIndex || '',
          remark: d.remark || '',
        })
      } catch { /* skip corrupt data */ }
    }
  }
  if (restored.length > 0) {
    detailRows.value = restored
  }
}

/** 默认明细行（对应xlsx rows 10-16） */
function _defaultRows(): M8DetailRow[] {
  return M8_DETAIL_DEFAULT_ITEMS.map((name, i) => ({
    key: `m8-detail-default-${i + 1}`,
    itemName: name,
    beginning: 0,
    increase: 0,
    decrease: 0,
    endBalance: 0,
    beginAje: 0,
    beginRje: 0,
    increaseAje: 0,
    decreaseAje: 0,
    increaseRje: 0,
    decreaseRje: 0,
    auditedBegin: 0,
    auditedIncrease: 0,
    auditedDecrease: 0,
    auditedEnd: 0,
    docReference: '',
    refIndex: '',
    remark: '',
  }))
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(async () => {
  await formData.loadData()

  // 恢复行数据
  _restoreRows()
  if (detailRows.value.length === 0) {
    detailRows.value = _defaultRows()
  }
})

onUnmounted(() => {
  // flush pending saves handled by onScopeDispose in useM8FormData
})
</script>

<style scoped>
.m8-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }

/* ─── 方法论上下文（琥珀色） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

/* ─── 动态行操作区 ─── */
.action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

/* ─── 公式列虚线下划线 + cursor:help ─── */
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value-end { color: #67c23a; font-weight: 600; }

/* ─── 行样式 ─── */
.total-row-label { font-weight: 700; color: #303133; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.total-row) { background: #ecf5ff !important; font-weight: 700; }
:deep(.total-row td) { border-top: 2px solid #409eff; }

/* ─── Footer ─── */
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

/* ─── 编制提示折叠 ─── */
.m8-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.m8-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m8-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m8-details-tip li { margin-bottom: 4px; line-height: 1.5; }

/* ─── el-input-number 紧凑 ─── */
:deep(.el-input-number) { width: 100%; }
:deep(.el-input-number .el-input__inner) { text-align: right; }
</style>
