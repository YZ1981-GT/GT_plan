<template>
  <div class="k5-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性（负债重点）：</b>所有应当确认的预计负债均已记录，不存在未确认的现时义务（或有事项）；</li>
        <li><b>存在与义务：</b>已记录的预计负债是资产负债表日存在的、很可能导致经济利益流出的现时义务；</li>
        <li><b>计价和分摊：</b>预计负债金额为履行现时义务所需支出的最佳估计数，计量恰当；</li>
        <li><b>列报与披露：</b>预计负债及或有事项已按 CAS13 恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K5-1 预计负债审定表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI审计说明
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '预计负债检查表K5-7')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>预计负债（2701）为<strong>贷方/负债类</strong>科目。期末 = 期初 + 本期计提（增加） − 本期转销/冲回（减少）。按产品质保、诉讼、亏损合同、重组、弃置等类型分行，审定数 = 未审 + AJE + RJE。</p>
    </div>

    <!-- ═══ TB勾稽指示器 ═══ -->
    <div v-if="!tbReconciliation.isMatch" class="reconciliation-alert">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          TB勾稽不平：审定合计 {{ fmtNum(subtotalRow.audited) }} vs TB审定(2701) {{ fmtNum(tbData.audited2701) }}，差异 {{ fmtNum(tbReconciliation.diff) }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 审定表主表 ═══ -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :row-class-name="adjRowClass"
      max-height="480"
    >
      <el-table-column prop="label" label="项目" width="130" fixed />
      <el-table-column label="期初" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.begin) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.begin" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'begin', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="计提(增加)" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.provision) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.provision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'provision', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="转销(减少)" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.release) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.release" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'release', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：期初 + 计提 − 转销" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.end) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="未审" width="110" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.unadjusted) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.unadjusted" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:90px" @change="(v:number) => handleCellChange(row.rowKey, 'unadj', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="AJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.aje) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.aje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => handleCellChange(row.rowKey, 'aje', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="RJE" width="100" align="right">
        <template #default="{ row }">
          <template v-if="row.rowKey === 'subtotal' || row.rowKey === 'diff'">
            <span class="formula-cell">{{ fmtNum(row.rje) }}</span>
          </template>
          <template v-else>
            <el-input-number v-model="row.rje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => handleCellChange(row.rowKey, 'rje', v)" />
          </template>
        </template>
      </el-table-column>
      <el-table-column label="审定数" width="120" align="right">
        <template #default="{ row }">
          <el-tooltip content="公式：未审 + AJE + RJE" placement="top">
            <span class="formula-cell formula-underline" :class="{ 'diff-highlight': row.rowKey === 'diff' && Math.abs(row.audited) > 0.01 }">
              {{ fmtNum(row.audited) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <template v-if="row.rowKey !== 'subtotal' && row.rowKey !== 'diff'">
            <el-input v-model="row.remark" :disabled="isReadonly" size="small" placeholder="备注" @blur="handleCellChange(row.rowKey, 'remark', row.remark)" />
          </template>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="tb-writeback-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="handleTbWriteback">
        回写试算表(2701)
      </el-button>
      <span v-if="tbReconciliation.isMatch" class="match-indicator">
        <el-icon color="#67c23a"><CircleCheckFilled /></el-icon> 勾稽平衡
      </span>
      <span v-else class="mismatch-indicator">
        <el-icon color="#f56c6c"><WarningFilled /></el-icon> 差异 {{ fmtNum(tbReconciliation.diff) }}
      </span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="conclusion-card">
      <template #header>
        <div class="section-header compact">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写审计说明、审计程序执行情况、结论..."
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>负债类科目(2701)：期末 = 期初 + 计提(增加) − 转销/冲回(减少)</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>三角勾稽：审定合计应等于各类型行审定数之和</li>
        <li>各专项检查表期末应与对应类型行审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabAdjudication.vue — K5-1 预计负债审定表
 * 负债类108公式+按类型分行+三角勾稽+TB回写
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.2
 * Requirements: 2.1-2.8
 */
import { computed, toRef } from 'vue'
import { MagicStick, CircleCheckFilled, WarningFilled } from '@element-plus/icons-vue'
import { useK5Adjudication } from '../../composables/useK5Adjudication'
import type { K5TbData } from '../../composables/useK5FormData'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: K5TbData
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Composable wiring ───────────────────────────────────────────────────────

const tbDataRef = computed(() => props.tbData)

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  rows,
  subtotalRow,
  diffRow,
  auditConclusion,
  tbReconciliation,
  saveAll,
} = useK5Adjudication({
  allResponses: allResponsesRef,
  tbData: tbDataRef as Ref<K5TbData>,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

// ─── 表格数据（类型行 + 合计 + 差异） ───────────────────────────────────────

const tableData = computed(() => [...rows.value, subtotalRow.value, diffRow.value])

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: string, value: any) {
  emit('save', `K5-1-${rowKey}-${field}`, { remark: String(value ?? '') })
}

function handleTbWriteback() {
  emit('save', 'K5-1-audited-total', { remark: String(subtotalRow.value.audited) })
}

function handleSaveConclusion() { saveAll() }

function handleAiGenerate() {
  // AI生成结论 - 调用通用AI端点
  emit('save', 'K5-1-ai-trigger', { remark: 'generate' })
}

// ─── Row class（差异行+勾稽不平红色高亮） ────────────────────────────────────

function adjRowClass({ row }: { row: any }): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  if (row.rowKey === 'diff') return Math.abs(row.audited) > 0.01 ? 'diff-row-error' : 'diff-row'
  return ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.section-header.compact { margin-bottom: 0; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.reconciliation-alert { margin-bottom: 12px; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.diff-highlight { color: #f56c6c; font-weight: 600; }
.tb-writeback-bar { display: flex; align-items: center; gap: 12px; margin: 12px 0; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.match-indicator, .mismatch-indicator { display: flex; align-items: center; gap: 4px; font-size: var(--wp-font-size, 13px); }
.match-indicator { color: #67c23a; }
.mismatch-indicator { color: #f56c6c; }
.conclusion-card { margin-top: 16px; }
:deep(.subtotal-row) { background-color: #f0f9eb !important; font-weight: 600; }
:deep(.diff-row) { background-color: #f5f7fa !important; }
:deep(.diff-row-error) { background-color: #fef0f0 !important; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
