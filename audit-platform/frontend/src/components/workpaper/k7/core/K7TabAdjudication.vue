<template>
  <div class="k7-tab-adjudication">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性（负债重点）：</b>所有应确认的递延收益（政府补助等）均已记录；</li>
        <li><b>存在与义务：</b>递延收益对应尚未满足条件/尚未分摊的政府补助或收益，真实存在；</li>
        <li><b>计价和分摊：</b>与资产相关递延收益按资产使用寿命系统分摊、与收益相关的按期确认，分摊金额恰当（CAS16）；</li>
        <li><b>列报与披露：</b>递延收益及政府补助已恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K7-1 递延收益审定表</h3>
      <div class="header-actions">
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI审计说明
        </el-button>
        <el-button size="small" @click="openReviewDialog?.('K7-1', '审定表K7-1')">💬 复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>递延收益（2401）为<strong>贷方/负债类</strong>科目。期末 = 期初 + 收到（贷方增加） − 分摊（借方减少）。按"与资产相关/与收益相关"分组，审定数 = 未审 + AJE + RJE。分摊去向：与日常活动相关→其他收益(K10)；无关→营业外收入(K12)。</p>
    </div>

    <!-- ═══ 三角勾稽指示器 ═══ -->
    <div v-if="!reconciliation.isBalanced" class="reconciliation-alert">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>
          <el-tooltip :content="`差额 = 审定合计(${fmtNum(grandTotal.audited)}) − 明细期末合计，差异${fmtNum(reconciliation.diff)}`" placement="right">
            <span>三角勾稽不平：审定合计 {{ fmtNum(grandTotal.audited) }}，差异 {{ fmtNum(reconciliation.diff) }}</span>
          </el-tooltip>
        </template>
      </el-alert>
    </div>

    <!-- ═══ 与资产相关分组 ═══ -->
    <div class="group-section group-asset">
      <div class="group-label group-label-asset">
        <span>与资产相关</span>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow('与资产相关')">+ 新增</el-button>
      </div>
      <el-table
        :data="assetTableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="adjRowClassAsset"
        max-height="320"
      >
        <el-table-column prop="project" label="项目" width="140" fixed />
        <el-table-column label="期初" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.beginBalance) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'beginBalance', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="收到(增加)" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.received) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.received" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'received', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="分摊(减少)" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.amortized) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.amortized" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'amortized', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末=期初+收到-分摊（负债类）" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.unadjustedEnd) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="未审" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.unadj) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.unadj" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleCellChange(row.rowKey, 'unadj', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="90" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.aje) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.aje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:75px" @change="(v:number) => handleCellChange(row.rowKey, 'aje', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="90" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.rje) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.rje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:75px" @change="(v:number) => handleCellChange(row.rowKey, 'rje', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="审定=未审+AJE+RJE" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="上期审定" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.priorAudited) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.priorAudited" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'priorAudited', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="80" align="right">
          <template #default="{ row }">
            <el-tooltip :content="`变动率=(审定${fmtNum(row.audited)}-上期${fmtNum(row.priorAudited)})/|上期|`" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'rate-warning': Math.abs(row.changeRate) > 0.3 }">{{ fmtPercent(row.changeRate) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="变动原因" min-width="120">
          <template #default="{ row }">
            <template v-if="!row._isSubtotal">
              <el-input v-model="row.changeReason" :disabled="isReadonly" size="small" placeholder="变动原因" @blur="handleCellChange(row.rowKey, 'changeReason', row.changeReason)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <template v-if="!row._isSubtotal">
              <el-input v-model="row.remark" :disabled="isReadonly" size="small" placeholder="" @blur="handleCellChange(row.rowKey, 'remark', row.remark)" />
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 与收益相关分组 ═══ -->
    <div class="group-section group-income">
      <div class="group-label group-label-income">
        <span>与收益相关</span>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow('与收益相关')">+ 新增</el-button>
      </div>
      <el-table
        :data="incomeTableData"
        border
        size="small"
        style="width: 100%"
        :row-class-name="adjRowClassIncome"
        max-height="320"
      >
        <el-table-column prop="project" label="项目" width="140" fixed />
        <el-table-column label="期初" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.beginBalance) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'beginBalance', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="收到(增加)" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.received) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.received" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'received', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="分摊(减少)" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.amortized) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.amortized" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'amortized', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="期末" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="期末=期初+收到-分摊（负债类）" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.unadjustedEnd) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="未审" width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.unadj) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.unadj" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => handleCellChange(row.rowKey, 'unadj', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="AJE" width="90" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.aje) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.aje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:75px" @change="(v:number) => handleCellChange(row.rowKey, 'aje', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="RJE" width="90" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.rje) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.rje" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:75px" @change="(v:number) => handleCellChange(row.rowKey, 'rje', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="审定数" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="审定=未审+AJE+RJE" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.audited) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="上期审定" width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal"><span class="formula-cell">{{ fmtNum(row.priorAudited) }}</span></template>
            <template v-else>
              <el-input-number v-model="row.priorAudited" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => handleCellChange(row.rowKey, 'priorAudited', v)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="变动率" width="80" align="right">
          <template #default="{ row }">
            <el-tooltip :content="`变动率=(审定${fmtNum(row.audited)}-上期${fmtNum(row.priorAudited)})/|上期|`" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'rate-warning': Math.abs(row.changeRate) > 0.3 }">{{ fmtPercent(row.changeRate) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="变动原因" min-width="120">
          <template #default="{ row }">
            <template v-if="!row._isSubtotal">
              <el-input v-model="row.changeReason" :disabled="isReadonly" size="small" placeholder="变动原因" @blur="handleCellChange(row.rowKey, 'changeReason', row.changeReason)" />
            </template>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <template v-if="!row._isSubtotal">
              <el-input v-model="row.remark" :disabled="isReadonly" size="small" placeholder="" @blur="handleCellChange(row.rowKey, 'remark', row.remark)" />
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 合计汇总栏 ═══ -->
    <div class="grand-total-bar" :class="{ 'total-unbalanced': !reconciliation.isBalanced }">
      <span class="total-label">合计</span>
      <span>期初 {{ fmtNum(grandTotal.beginBalance) }}</span>
      <span>收到 {{ fmtNum(grandTotal.received) }}</span>
      <span>分摊 {{ fmtNum(grandTotal.amortized) }}</span>
      <el-tooltip content="期末=期初+收到-分摊" placement="top">
        <span class="formula-underline">期末 {{ fmtNum(grandTotal.unadjustedEnd) }}</span>
      </el-tooltip>
      <el-tooltip content="审定=未审+AJE+RJE" placement="top">
        <span class="total-audited formula-underline">审定 {{ fmtNum(grandTotal.audited) }}</span>
      </el-tooltip>
    </div>

    <!-- ═══ TB回写 + 勾稽状态 ═══ -->
    <div class="tb-writeback-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" @click="handleTbWriteback">
        回写试算表(2401)
      </el-button>
      <span v-if="reconciliation.isBalanced" class="match-indicator">
        <el-icon color="#67c23a"><CircleCheckFilled /></el-icon> 勾稽平衡
      </span>
      <el-tooltip v-else :content="`差额=${fmtNum(reconciliation.diff)}，审定合计与K7-2明细期末合计不符`" placement="top">
        <span class="mismatch-indicator">
          <el-icon color="#f56c6c"><WarningFilled /></el-icon> 差异 {{ fmtNum(reconciliation.diff) }}
        </span>
      </el-tooltip>
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
        v-model="auditConclusionLocal"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写审计说明、审计程序执行情况、结论..."
        @blur="handleSaveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>负债类科目(2401)：期末 = 期初 + 收到(贷方增加) − 分摊(借方减少)</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>与资产相关：按相关资产使用寿命直线分摊计入其他收益(K10)</li>
        <li>与收益相关：补偿以后期间→分期；补偿已发生→一次性计入当期损益</li>
        <li>三角勾稽：审定合计应等于K7-2明细表期末合计</li>
        <li>回写TB(2401)后自动发布substantive:adjudicated事件通知附注刷新</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K7TabAdjudication.vue — K7-1 递延收益审定表
 * 负债类49公式+相关类型分组(与资产/与收益)+三角勾稽+TB回写+54行虚拟滚动
 *
 * Spec: .kiro/specs/k7-deferred-income/ | Task: 4.2
 * Requirements: 2.1-2.7
 *
 * 列结构(13列): 项目/期初/本期增加(收到)/本期减少(分摊)/期末(公式)/
 *               未审/AJE/RJE/审定(公式)/上期审定/变动率(公式)/变动原因/备注
 *
 * 科目：2401 递延收益（**贷方/负债类**）
 * ⚠️ 负债类！期末=期初+收到(贷方增加)-分摊(借方减少)
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { MagicStick, CircleCheckFilled, WarningFilled } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useK7Adjudication, type K7AdjRow } from '../../composables/useK7Adjudication'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted2401: number; audited2401: number }
  isReadonly: boolean
}>()

// 父组件模板绑定会自动解包顶层 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string, label?: string) => void>('openReviewDialog', undefined)

// ─── Composable wiring ───────────────────────────────────────────────────────

const adj = useK7Adjudication({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', field, value)
  },
})

const {
  assetRelatedRows,
  incomeRelatedRows,
  assetSubtotal,
  incomeSubtotal,
  grandTotal,
  reconciliation,
  auditConclusion,
} = adj

// Local ref binding for textarea v-model
const auditConclusionLocal = auditConclusion

// ─── 表格数据（含小计行标记） ─────────────────────────────────────────────────

interface DisplayRow extends K7AdjRow {
  _isSubtotal?: boolean
  remark?: string
}

const assetTableData = computed((): DisplayRow[] => {
  const dataRows = assetRelatedRows.value.map(r => ({ ...r, _isSubtotal: false, remark: (r as any).remark ?? '' }))
  const subtotal: DisplayRow = {
    ...assetSubtotal.value,
    project: '与资产相关小计',
    _isSubtotal: true,
    rowKey: 'asset-subtotal',
    group: '与资产相关',
    unadjustedEnd: assetSubtotal.value.unadjustedEnd,
    changeRate: 0,
    changeReason: '',
    remark: '',
  }
  return [...dataRows, subtotal]
})

const incomeTableData = computed((): DisplayRow[] => {
  const dataRows = incomeRelatedRows.value.map(r => ({ ...r, _isSubtotal: false, remark: (r as any).remark ?? '' }))
  const subtotal: DisplayRow = {
    ...incomeSubtotal.value,
    project: '与收益相关小计',
    _isSubtotal: true,
    rowKey: 'income-subtotal',
    group: '与收益相关',
    unadjustedEnd: incomeSubtotal.value.unadjustedEnd,
    changeRate: 0,
    changeReason: '',
    remark: '',
  }
  return [...dataRows, subtotal]
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: string, value: any) {
  adj.updateCell(rowKey, field, value)
}

function handleTbWriteback() {
  emit('save', 'K7-1-audited-total', { remark: String(grandTotal.value.audited) })
}

function handleSaveConclusion() {
  adj.saveAll()
}

function handleAiGenerate() {
  emit('save', 'K7-1-ai-trigger', { remark: 'generate' })
}

async function handleAddRow(group: '与资产相关' | '与收益相关') {
  try {
    const { value } = await ElMessageBox.prompt('请输入补助项目名称', '新增行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '例如：XX设备购置补助',
      inputValidator: (val) => (!val?.trim() ? '项目名称不能为空' : true),
    })
    if (value?.trim()) adj.addRow(value.trim(), group)
  } catch { /* cancelled */ }
}

// ─── Row class（小计行粗体，分组配色） ────────────────────────────────────────

function adjRowClassAsset({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'subtotal-row'
  return 'asset-row'
}

function adjRowClassIncome({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'subtotal-row'
  return 'income-row'
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: number | null | undefined): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(v: number | null | undefined): string {
  if (v == null || (!v && v !== 0)) return '-'
  return (v * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.k7-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* Section header */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.section-header.compact { margin-bottom: 0; }
.header-actions { display: flex; gap: 8px; }

/* 方法论上下文 */
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }

/* 三角勾稽警告 */
.reconciliation-alert { margin-bottom: 12px; }

/* 分组区域 */
.group-section { margin-bottom: 16px; }
.group-label { display: flex; align-items: center; justify-content: space-between; font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; margin-bottom: 6px; padding: 6px 10px; border-radius: 4px; }
.group-label-asset { background: #ecf5ff; color: #1d4ed8; border-left: 3px solid #409eff; }
.group-label-income { background: #f0f9eb; color: #166534; border-left: 3px solid #67c23a; }

/* 分组行配色 */
:deep(.asset-row) { background-color: #f8fbff !important; }
:deep(.income-row) { background-color: #f8fdf5 !important; }
:deep(.subtotal-row) { background-color: #e8f4fd !important; font-weight: 600; border-top: 2px solid #c6e2ff; }

/* 公式列虚线下划线 + cursor:help */
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.rate-warning { color: #f56c6c; font-weight: 600; }

/* 合计汇总栏 */
.grand-total-bar { display: flex; align-items: center; gap: 16px; margin: 12px 0; padding: 10px 14px; background: #ecf5ff; border-radius: 6px; font-size: var(--wp-font-size, 13px); font-weight: 600; border-top: 2px solid #409eff; }
.grand-total-bar.total-unbalanced { background: #fef0f0; border-top-color: #f56c6c; }
.total-label { font-weight: 700; color: #303133; font-size: 14px; }
.total-audited { color: #409eff; font-weight: 700; }

/* TB回写栏 */
.tb-writeback-bar { display: flex; align-items: center; gap: 12px; margin: 12px 0; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.match-indicator, .mismatch-indicator { display: flex; align-items: center; gap: 4px; font-size: var(--wp-font-size, 13px); }
.match-indicator { color: #67c23a; }
.mismatch-indicator { color: #f56c6c; cursor: help; }

/* 审计说明卡片 */
.conclusion-card { margin-top: 16px; }

/* 表格字体 */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }

/* 编制提示 */
.k7-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
