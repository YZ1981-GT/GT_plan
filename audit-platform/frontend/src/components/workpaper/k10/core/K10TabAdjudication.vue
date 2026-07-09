<template>
  <div class="k10-tab-adjudication">
    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="k10-guide">
      <div class="k10-guide-header">
        <el-icon><InfoFilled /></el-icon>
        <span>审定表编制说明</span>
      </div>
      <div class="k10-guide-steps">
        <div class="step-item">
          <span class="step-num">①</span>
          <span class="step-text">TB自动取数：6117发生额（损益类贷方科目）→ 未审列自动填入</span>
        </div>
        <div class="step-item">
          <span class="step-num">②</span>
          <span class="step-text">录入AJE/RJE调整 → 审定数自动计算</span>
        </div>
        <div class="step-item">
          <span class="step-num">③</span>
          <span class="step-text">确认审定数后点击"回写TB" → 发生额回写trial_balance</span>
        </div>
        <div class="step-item">
          <span class="step-num">④</span>
          <span class="step-text">与K10-2明细合计交叉验证 → 差额为零则一致</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>
        <strong>损益类科目（6117其他收益）</strong>：取发生额非余额。6117为贷方科目，贷方=收益增加，借方=冲回。
        审定数=未审数+AJE+RJE。按收益来源分行：政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他。
      </p>
    </div>

    <!-- ═══ Section 标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3>K10-1 其他收益审定表</h3>
        <el-tag size="small" type="warning" effect="plain">损益类·发生额</el-tag>
      </div>
      <div class="header-actions">
        <el-button size="small" type="primary" text @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" text @click="openReviewDialog?.('K10-1-adjudication', '其他收益审定表')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 跨底稿引用 ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-3" :context-project-id="props.projectId" />
      <GtIndexChip value="K10-4" :context-project-id="props.projectId" />
      <GtIndexChip value="K7" :context-project-id="props.projectId" />
    </div>

    <!-- ═══ TB自动取数提示 ═══ -->
    <div v-if="props.tbData" class="tb-info-bar">
      <span>TB取数(6117发生额)：未审 <strong>{{ fmtAmt(props.tbData.unadjusted6117) }}</strong></span>
      <span>审定 <strong>{{ fmtAmt(props.tbData.audited6117) }}</strong></span>
    </div>

    <!-- ═══ 审定表格（11列） ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%; font-size: 13px"
      :row-class-name="getTableRowClassName"
    >
      <!-- 项目 -->
      <el-table-column prop="name" label="项目" min-width="150" fixed="left">
        <template #default="{ row }">
          <strong v-if="row._isTotal">{{ row.name }}</strong>
          <span v-else>{{ row.name }}</span>
        </template>
      </el-table-column>

      <!-- 本期未审 -->
      <el-table-column prop="unadjusted" label="本期未审" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.unadjusted"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'unadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
        </template>
      </el-table-column>

      <!-- AJE -->
      <el-table-column prop="aje" label="AJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.aje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'aje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.aje) }}</span>
        </template>
      </el-table-column>

      <!-- RJE -->
      <el-table-column prop="rje" label="RJE" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.rje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'rje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.rje) }}</span>
        </template>
      </el-table-column>

      <!-- 审定（公式列） -->
      <el-table-column label="审定" width="120" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="审定数 = 未审 + AJE + RJE">审定</span>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :title="`${row.unadjusted} + ${row.aje} + ${row.rje} = ${row.audited}`">
            {{ fmtAmt(row.audited) }}
          </span>
        </template>
      </el-table-column>

      <!-- 索引号（仅普通行） -->
      <el-table-column label="索引号" width="80" align="center">
        <template #default="{ row }">
          <GtIndexChip v-if="!row._isTotal && row.name" :value="`K10-1`" :context-project-id="props.projectId" />
        </template>
      </el-table-column>

      <!-- 上期未审 -->
      <el-table-column prop="priorUnadj" label="上期未审" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.priorUnadj"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'priorUnadj', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorUnadj) }}</span>
        </template>
      </el-table-column>

      <!-- 上期AJE -->
      <el-table-column prop="priorAje" label="上期AJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.priorAje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'priorAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorAje) }}</span>
        </template>
      </el-table-column>

      <!-- 上期RJE -->
      <el-table-column prop="priorRje" label="上期RJE" width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.priorRje"
            size="small"
            :controls="false"
            :precision="2"
            style="width: 100%"
            @change="(v: number | undefined) => adjudication.updateCell(row.rowKey, 'priorRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.priorRje) }}</span>
        </template>
      </el-table-column>

      <!-- 上期审定（公式列） -->
      <el-table-column label="上期审定" width="110" align="right" class-name="formula-col">
        <template #header>
          <span class="formula-header" title="上期审定 = 上期未审 + 上期AJE + 上期RJE">上期审定</span>
        </template>
        <template #default="{ row }">
          <span class="formula-value" :title="`${row.priorUnadj} + ${row.priorAje} + ${row.priorRje} = ${row.priorAudited}`">
            {{ fmtAmt(row.priorAudited) }}
          </span>
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column prop="remark" label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && row.isEditable && !row._isTotal"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => adjudication.updateCell(row.rowKey, 'remark', v)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 操作栏 ═══ -->
    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增来源行</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleWritebackTB">
        回写TB（6117发生额）
      </el-button>
    </div>

    <!-- ═══ 与K10-2交叉验证 ═══ -->
    <div v-if="!adjudication.detailCrossValidation.value.isBalanced" class="cross-validation-alert">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
      >
        <template #title>
          K10-1审定合计与K10-2明细合计不一致，差额：{{ fmtAmt(adjudication.detailCrossValidation.value.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 审计说明 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>审计说明</span>
          <div class="note-card-actions">
            <el-button size="small" type="primary" text @click="handleAiNote">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写审计说明..."
        @change="(v: string) => adjudication.saveNote(v)"
      />
    </el-card>

    <!-- ═══ 结论 ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>审计结论</span>
          <div class="note-card-actions">
            <el-button size="small" type="primary" text @click="handleAiConclusion">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" text @click="openReviewDialog?.('K10-1-conclusion', '审定表结论')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="adjudication.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="填写审计结论..."
        @change="(v: string) => adjudication.saveConclusion(v)"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="compile-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>K10-1为损益类审定表（6117其他收益），取贷方发生额（贷方=收益增加）</li>
        <li>按收益来源分行：政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他</li>
        <li>审定数 = 未审数 + AJE + RJE（公式自动计算）</li>
        <li>审定完成后点击"回写TB"将发生额回写trial_balance（6117）</li>
        <li>合计行应与K10-2明细表合计一致（差额为零）</li>
        <li>与日常活动相关→其他收益(6117)；与日常活动无关→营业外收入(6301,K12)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabAdjudication.vue — K10-1 其他收益审定表
 *
 * Spec: .kiro/specs/k10-other-income/ | Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 功能：
 * - 69公式，损益类6117，发生额取数
 * - 按收益来源分行（政府补助-即征即退/财政贴息/研发补助/稳岗补贴/其他）
 * - 11列：项目|本期未审|AJE|RJE|审定|索引号|上期未审|上期AJE|上期RJE|上期审定|备注
 * - 公式列（审定/上期审定）dashed underline + cursor:help + tooltip
 * - TB回写（6117发生额！）
 * - 与K10-2明细交叉验证（差额提示）
 * - 底部：审计说明 + 结论 + 复核入口
 * - 每个section AI辅助按钮
 */
import { computed, inject, toRef, defineAsyncComponent } from 'vue'
import { InfoFilled, MagicStick } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK10Adjudication, type K10AdjRow } from '../../composables/useK10Adjudication'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData?: { unadjusted6117: number; audited6117: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const adjudication = useK10Adjudication({
  allResponses: toRef(props, 'allResponses'),
  projectId: toRef(props, 'projectId'),
  wpId: toRef(props, 'wpId'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── Table Data (rows + total) ───────────────────────────────────────────────

interface TableRow extends K10AdjRow {
  _isTotal?: boolean
}

const tableData = computed<TableRow[]>(() => {
  const rows: TableRow[] = adjudication.rows.value.map(r => ({ ...r, _isTotal: false }))
  const total = adjudication.totalRow.value
  rows.push({
    rowKey: '__total__',
    name: total.label,
    unadjusted: total.unadjusted,
    aje: total.aje,
    rje: total.rje,
    audited: total.audited,
    priorUnadj: total.priorUnadj,
    priorAje: total.priorAje,
    priorRje: total.priorRje,
    priorAudited: total.priorAudited,
    yoyChange: total.yoyChange,
    remark: '',
    isEditable: false,
    _isTotal: true,
  })
  return rows
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

const isReadonly = computed(() => props.isReadonly)

function fmtAmt(v: number | null | undefined): string {
  if (v == null || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getTableRowClassName({ row }: { row: TableRow }): string {
  if (row._isTotal) return 'total-row'
  return ''
}

// ─── 操作 ────────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入收益来源名称', '新增来源行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：政府补助-XX/专项基金收益...',
    })
    if (value?.trim()) {
      adjudication.addRow(value.trim())
    }
  } catch { /* cancelled */ }
}

async function handleWritebackTB(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确认将审定合计 ${fmtAmt(adjudication.totalRow.value.audited)} 回写TB（6117发生额）？`,
      '回写确认',
      { confirmButtonText: '确认回写', cancelButtonText: '取消', type: 'warning' },
    )
    await adjudication.writeback()
    ElMessage.success('已回写TB（6117其他收益发生额）')
  } catch { /* cancelled */ }
}

function handleAiAssist(): void {
  ElMessage.info('AI辅助审定分析...')
}

function handleAiNote(): void {
  ElMessage.info('AI生成审计说明...')
}

function handleAiConclusion(): void {
  ElMessage.info('AI生成审计结论...')
}
</script>

<style scoped>
.k10-tab-adjudication { padding: 12px; font-size: 13px; }

.k10-guide {
  margin-bottom: 14px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #e8f4fd 0%, #d1ecf9 100%);
  border-radius: 8px;
  border-left: 4px solid #409eff;
}
.k10-guide-header {
  display: flex; align-items: center; gap: 6px;
  font-weight: 600; color: #303133; margin-bottom: 8px;
}
.k10-guide-steps { display: grid; grid-template-columns: 1fr 1fr; gap: 5px 14px; }
.step-item { display: flex; align-items: flex-start; gap: 5px; }
.step-num { color: #409eff; font-weight: 700; min-width: 16px; }
.step-text { color: #606266; line-height: 1.5; font-size: 12px; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: 13px; color: #78350f; line-height: 1.6;
}
.methodology-context p { margin: 0; }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-left h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; align-items: center; }

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }

.tb-info-bar {
  display: flex; gap: 16px; align-items: center;
  margin-bottom: 10px; padding: 6px 12px;
  background: #ecf5ff; border-radius: 4px;
  font-size: 12px; color: #409eff;
}
.tb-info-bar strong { color: #303133; }

/* 公式列样式 */
:deep(.formula-col) .cell { border-bottom: 1px dashed #909399; }
.formula-header {
  cursor: help;
  border-bottom: 1px dashed #606266;
  padding-bottom: 1px;
}
.formula-value {
  cursor: help;
  border-bottom: 1px dashed #c0c4cc;
  padding-bottom: 1px;
}

:deep(.el-table) { font-size: 13px; }
:deep(.total-row) { background-color: #f5f7fa !important; font-weight: 600; }

.table-actions { display: flex; gap: 8px; margin-top: 12px; }

.cross-validation-alert { margin-top: 12px; }

.note-card { margin-top: 16px; }
.note-card-header {
  display: flex; justify-content: space-between; align-items: center;
}
.note-card-header span { font-weight: 600; font-size: 14px; }
.note-card-actions { display: flex; gap: 6px; }

.compile-hint {
  margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary);
  padding: 12px 16px; background: #fafafa;
  border: 1px solid #ebeef5; border-radius: 6px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; color: #303133; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
