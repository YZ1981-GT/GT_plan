<template>
  <div class="i5-adjudication">
    <!-- 方法论上下文（琥珀色左边线+浅黄背景） -->
    <div class="methodology-context">
      <p><strong>其他非流动资产审定原理：</strong>科目1911（借方/资产类）。期末=期初+增加-减少。</p>
      <p>I5为最简单标准资产类底稿，无摊销/减值等特殊逻辑。审定数=未审数+AJE+RJE。</p>
      <p>三角勾稽：期末余额必须等于(期初+增加-减少)，差额≠0时红色高亮。变动率=(审定-期初)/期初。</p>
    </div>

    <!-- 三角勾稽错误警告 -->
    <el-alert
      v-if="reconciliationStatus === 'mismatch'"
      type="error"
      title="三角勾稽不平：期末 ≠ 期初+增加-减少，请检查数据"
      show-icon
      :closable="false"
      class="adj-warning"
    />

    <!-- 主审定表（11列，89行虚拟滚动） -->
    <div class="table-section">
      <div class="block-header">
        <span class="block-title">其他非流动资产审定表（I5-1）</span>
        <div class="block-actions">
          <el-button size="small" type="primary" @click="addRow" :disabled="isReadonly">
            + 新增
          </el-button>
          <el-button size="small" type="primary" text @click="handleAiGenerate('adjudication')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
          <el-button size="small" type="default" text @click="handleReview">
            复核
          </el-button>
        </div>
      </div>

      <el-table
        :data="virtualScrollData"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
        max-height="600"
        scrollbar-always-on
      >
        <!-- 1. 项目 -->
        <el-table-column prop="项目" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.项目 }}</span>
            <el-button
              v-if="row.isEditable && !isReadonly"
              size="small"
              type="danger"
              text
              class="row-delete-btn"
              @click="removeRow(row.rowId)"
            >✕</el-button>
          </template>
        </el-table-column>

        <!-- 2. 期初 -->
        <el-table-column prop="期初" label="期初" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.期初"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '期初', $event)"
            />
            <span v-else>{{ fmtAmount(row.期初) }}</span>
          </template>
        </el-table-column>

        <!-- 3. 本期增加 -->
        <el-table-column prop="增加" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.增加"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '增加', $event)"
            />
            <span v-else>{{ fmtAmount(row.增加) }}</span>
          </template>
        </el-table-column>

        <!-- 4. 本期减少 -->
        <el-table-column prop="减少" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.减少"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '减少', $event)"
            />
            <span v-else>{{ fmtAmount(row.减少) }}</span>
          </template>
        </el-table-column>

        <!-- 5. 期末（公式列） -->
        <el-table-column label="期末" min-width="110" align="right">
          <template #header>
            <el-tooltip content="期末 = 期初 + 增加 - 减少" placement="top">
              <span class="formula-col-header">期末</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="期末 = 期初 + 增加 - 减少" placement="top">
              <span class="formula-value" :class="{ 'cell-error-text': row.hasError }">
                {{ fmtAmount(row.期末) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 6. 未审 -->
        <el-table-column prop="未审" label="未审" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.未审"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, '未审', $event)"
            />
            <span v-else>{{ fmtAmount(row.未审) }}</span>
          </template>
        </el-table-column>

        <!-- 7. AJE -->
        <el-table-column prop="AJE" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.AJE"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'AJE', $event)"
            />
            <span v-else>{{ fmtAmount(row.AJE) }}</span>
          </template>
        </el-table-column>

        <!-- 8. RJE -->
        <el-table-column prop="RJE" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              v-model="row.RJE"
              size="small"
              :controls="false"
              @change="onCellChange(row.rowId, 'RJE', $event)"
            />
            <span v-else>{{ fmtAmount(row.RJE) }}</span>
          </template>
        </el-table-column>

        <!-- 9. 审定数（公式列） -->
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="审定 = 未审 + AJE + RJE" placement="top">
              <span class="formula-value">{{ fmtAmount(row.审定) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 10. 变动率（公式列） -->
        <el-table-column label="变动率" min-width="90" align="right">
          <template #header>
            <el-tooltip content="变动率 = (审定数 - 期初) / 期初" placement="top">
              <span class="formula-col-header">变动率</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="变动率 = (审定 - 期初) / 期初" placement="top">
              <span class="formula-value" :class="{ 'rate-warn': isHighChangeRate(row.变动率) }">
                {{ fmtRate(row.变动率) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 11. 备注 -->
        <el-table-column prop="备注" label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !isReadonly"
              v-model="row.备注"
              size="small"
              placeholder="备注"
              @change="onCellChange(row.rowId, '备注', $event)"
            />
            <span v-else>{{ row.备注 || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- TB差异区 -->
    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异</span>
        <el-button size="small" type="success" @click="handleWriteback" :disabled="isReadonly">
          回写TB(1911)
        </el-button>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.tbAmount) }}</template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">{{ fmtAmount(row.audited) }}</template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
              {{ fmtAmount(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 跨底稿联动跳转 -->
    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="I5-2" @click="navigateTo('I5-2')" />
      <GtIndexChip value="I5-3" @click="navigateTo('I5-3')" />
      <GtIndexChip value="A13" @click="navigateTo('A13')" />
    </div>

    <!-- 审计说明 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('note')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="请填写审计说明（其他非流动资产分类正确性、期限适当性、可回收性检查情况）..."
        :disabled="isReadonly"
        @blur="onNoteBlur"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" text @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-select
        v-model="auditConclusion"
        placeholder="请选择审计结论"
        :disabled="isReadonly"
        class="conclusion-select"
        @change="onConclusionChange"
      >
        <el-option value="其他非流动资产期末余额列报恰当，分类正确" label="其他非流动资产期末余额列报恰当，分类正确" />
        <el-option value="经审计调整后，其他非流动资产列报恰当" label="经审计调整后，其他非流动资产列报恰当" />
        <el-option value="期末余额公允，分类正确，期限适当" label="期末余额公允，分类正确，期限适当" />
        <el-option value="需进一步关注" label="需进一步关注" />
      </el-select>
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>其他非流动资产科目1911（借方/资产类）：期末=期初+增加-减少</li>
        <li>三角勾稽差额≠0将红色高亮，需查明原因</li>
        <li>"回写TB"按钮将审定合计数回写试算平衡表(1911)</li>
        <li>AJE/RJE来自I5-3调整分录表（EventBus自动同步）</li>
        <li>|变动率|&gt;30%时建议补充原因说明</li>
        <li>89行支持虚拟滚动（max-height=600px），大数据量不卡顿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabAdjudication.vue — I5-1 其他非流动资产审定表（61公式，89行虚拟滚动）
 *
 * 列结构（11列）：
 *   项目 | 期初 | 本期增加 | 本期减少 | 期末 | 未审 | AJE | RJE | 审定数 | 变动率 | 备注
 *
 * 核心公式：
 *   - 期末 = 期初 + 增加 - 减少（资产类借方科目1911）
 *   - 审定 = 未审 + AJE + RJE
 *   - 三角勾稽：差额 = (期初 + 增加 - 减少) - 期末 → 非0红色高亮
 *   - 变动率 = (审定数 - 期初) / 期初 → 期初为0时null
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 4.2
 * Requirements: 2.1-2.7
 */
import { computed, toRef, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useI5Adjudication,
  type I5AdjudicationRow,
} from '../../composables/useI5Adjudication'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted1911: number; audited1911: number }
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject (openReviewDialog from main entry) ───────────────────────────────

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  rows: computedRows,
  auditNote,
  auditConclusion,
  subtotals,
  reconciliationStatus,
  differenceRows,
  virtualScrollData,
  addRow,
  removeRow,
  updateCell,
  writeback,
  saveNote,
  saveConclusion,
} = useI5Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbUnadjusted1911: computed(() => props.tbData?.unadjusted1911 ?? 0),
    tbAudited1911: computed(() => props.tbData?.audited1911 ?? 0),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I5AdjudicationRow }): string {
  if (row.isSubtotal) return 'row-subtotal'
  if (row.hasError) return 'row-has-error'
  return ''
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(rowId: string, field: keyof I5AdjudicationRow, value: number | string | null): void {
  updateCell(rowId, field, value ?? 0)
}

// ─── Note / Conclusion ───────────────────────────────────────────────────────

function onNoteBlur(): void {
  saveNote(auditNote.value)
}

function onConclusionChange(val: string): void {
  saveConclusion(val)
}

// ─── Writeback ───────────────────────────────────────────────────────────────

async function handleWriteback(): Promise<void> {
  await writeback()
}

// ─── AI Generate ─────────────────────────────────────────────────────────────

async function handleAiGenerate(section: string): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section,
      prompt: `I5其他非流动资产审定表${section}`,
      context: {
        wpCode: 'I5-1',
        rule: '期末=期初+增加-减少，科目1911借方资产类',
        auditedTotal: subtotals.value.审定,
      },
    })
    if (res.data?.data?.content) {
      if (section === 'note') {
        auditNote.value = res.data.data.content
        saveNote(auditNote.value)
      } else if (section === 'conclusion') {
        auditConclusion.value = res.data.data.content
        saveConclusion(auditConclusion.value)
      }
    }
  } catch {
    // AI生成失败不阻塞
  }
}

// ─── Review (复核对话) ───────────────────────────────────────────────────────

function handleReview(): void {
  openReviewDialog('I5-1 审定表')
}

// ─── Navigation (emit navigate-sheet for GtIndexChip cross-refs) ─────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Amount / Rate Formatters ────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRate(rate: number | null | undefined): string {
  if (rate == null) return '-'
  return (rate * 100).toFixed(1) + '%'
}

function isHighChangeRate(rate: number | null | undefined): boolean {
  if (rate == null) return false
  return Math.abs(rate) > 0.3
}
</script>

<style scoped>
.i5-adjudication {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }

/* 警告 */
.adj-warning { margin-bottom: 12px; }

/* 区块通用 */
.table-section { margin-bottom: 20px; }
.block-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 0; font-weight: 600; font-size: 14px;
}
.block-actions { display: flex; align-items: center; gap: 4px; }
.block-title { font-size: 14px; }

/* 审定表 */
.adjudication-table { font-size: var(--wp-font-size, 13px); }

/* 公式列虚线下划线 + cursor:help */
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help; padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help; padding-bottom: 1px;
  color: #303133; font-weight: 500;
}

/* 合计行 */
.adjudication-table :deep(.row-subtotal td) {
  font-weight: 600; background: #f0f9ff !important;
}
.subtotal-text { font-weight: 600; }

/* 行级样式——三角勾稽红色高亮 */
.adjudication-table :deep(.row-has-error td) { background: #fef2f2 !important; }
.cell-error-text { color: #dc2626; font-weight: 600; }
.row-delete-btn { margin-left: 4px; font-size: 11px; padding: 2px 4px; }

/* 变动率高亮（|变动率|>30%） */
.rate-warn { color: #d97706; font-weight: 600; }

/* TB差异 */
.tb-section { margin-bottom: 20px; margin-top: 24px; }
.tb-table { font-size: var(--wp-font-size, 13px); }
.difference-warning { color: #dc2626; font-weight: 600; }

/* 跨底稿联动 */
.cross-ref-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 0; margin-bottom: 16px; flex-wrap: wrap;
}
.cross-ref-label { color: #606266; font-size: var(--wp-font-size, 13px); }

/* 审计说明/结论 el-card */
.audit-note-card { margin-bottom: 16px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 500;
}
.conclusion-select { width: 100%; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
