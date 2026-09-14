<template>
  <div class="k5-tab-warranty">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性：</b>符合确认条件的产品质量保证（保修）义务均已计提预计负债；</li>
        <li><b>计价和分摊：</b>保修费用计提基于历史保修率/销售规模的最佳估计，计量合理；</li>
        <li><b>列报与披露：</b>产品质量保证准备按 CAS13 恰当列报披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K5-4 产品质量保修检查表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="pullD4Revenue">
          <el-icon><Download /></el-icon> 从D4带入收入
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="applyHistoryRateToCalc">
          📊 带入历史保修率
        </el-button>
        <el-dropdown size="small" :disabled="isReadonly">
          <el-button size="small">导入导出 <el-icon><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>产品质量保修准备计提：<strong>应计提金额 = 计提基数（销售收入）× 历史保修率</strong>。历史保修率基于近3年"实际发生额/销售收入"加权平均。期末余额（负债类）= 期初 + 本期计提 − 本期使用。K5-4期末合计应与K5-1产品质保行审定数一致。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-4 期末合计: <strong>{{ fmtNum(crossCheck.warrantyTotal) }}</strong></span>
      <span>K5-1 产品质保审定: <strong>{{ fmtNum(crossCheck.adjudicationWarranty) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══（一）产品质量保修政策 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header><span class="card-title">（一）产品质量保修政策</span></template>
      <el-input
        v-model="policyText"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="描述被审计单位产品质量保修政策：保修范围、保修期限、计提方法、计提基础等"
        @change="(v: string) => updatePolicy(v)"
      />
    </el-card>

    <!-- ═══（二）历史质量保修情况（评估计提比例是否合理）═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（二）检查历史质量保修情况，评估计提比例是否合理</span>
          <el-button v-if="!isReadonly" size="small" @click="addHistoryRow()">＋ 新增产品</el-button>
        </div>
      </template>
      <el-table :data="historyRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="产品类别" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.productName" :disabled="isReadonly" size="small" @change="(v: string) => updateHistoryCell(row.rowId, 'productName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="本期实际发生" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.currentActual" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'currentActual', v)" /></template>
        </el-table-column>
        <el-table-column label="本期收入" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.currentRevenue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'currentRevenue', v)" /></template>
        </el-table-column>
        <el-table-column label="前1年实际发生" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year1Actual" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year1Actual', v)" /></template>
        </el-table-column>
        <el-table-column label="前1年收入" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year1Revenue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year1Revenue', v)" /></template>
        </el-table-column>
        <el-table-column label="前2年实际发生" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year2Actual" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year2Actual', v)" /></template>
        </el-table-column>
        <el-table-column label="前2年收入" width="115" align="right">
          <template #default="{ row }"><el-input-number v-model="row.year2Revenue" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateHistoryCell(row.rowId, 'year2Revenue', v)" /></template>
        </el-table-column>
        <el-table-column label="3年平均保修率" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="∑实际发生 / ∑收入" placement="top">
              <span class="formula-cell formula-underline">{{ (row.avgRate * 100).toFixed(3) }}%</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeHistoryRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计平均保修率：{{ (historySubtotals.avgRate * 100).toFixed(3) }}%</div>
        </template>
      </el-table>
    </el-card>

    <!-- ═══（三）重新测算产品质量保证金 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（三）重新测算产品质量保证金</span>
          <el-button size="small" :disabled="isReadonly" @click="handleAddRow"><el-icon><Plus /></el-icon> 新增行</el-button>
        </div>
      </template>
      <el-table :data="warrantyRows" border size="small" style="width: 100%" max-height="420">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="产品类别" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.productName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'productName', row.productName)" />
          </template>
        </el-table-column>
        <el-table-column label="计提基数(收入)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.revenue" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => save(row.rowId, 'revenue', v)" />
          </template>
        </el-table-column>
        <el-table-column label="计提比例" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.warrantyRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:80px" @change="(v:number) => save(row.rowId, 'warrantyRate', v)" />
          </template>
        </el-table-column>
        <el-table-column label="应计提金额" width="115" align="right">
          <template #default="{ row }">
            <el-tooltip content="计提基数 × 计提比例" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.estimatedExpense) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面已计提" width="115" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.bookProvision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:95px" @change="(v:number) => save(row.rowId, 'bookProvision', v)" />
          </template>
        </el-table-column>
        <el-table-column label="差异金额" width="110" align="right">
          <template #default="{ row }">
            <el-tooltip content="应计提 − 账面已计提" placement="top">
              <span class="formula-cell formula-underline" :class="{ 'diff-warn': Math.abs(row.variance) > 0.01 }">{{ fmtNum(row.variance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="130">
          <template #default="{ row }">
            <el-input v-model="row.varianceReason" :disabled="isReadonly" size="small" placeholder="差异原因" @blur="save(row.rowId, 'varianceReason', row.varianceReason)" />
          </template>
        </el-table-column>
        <el-table-column label="期初" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => save(row.rowId, 'beginBalance', v)" />
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.periodProvision" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => save(row.rowId, 'periodProvision', v)" />
          </template>
        </el-table-column>
        <el-table-column label="本期使用" width="95" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.periodUsed" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:80px" @change="(v:number) => save(row.rowId, 'periodUsed', v)" />
          </template>
        </el-table-column>
        <el-table-column label="期末" width="105" align="right">
          <template #default="{ row }">
            <el-tooltip content="期初 + 计提 − 使用" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }">
            <el-button link type="danger" size="small" @click="removeRow($index)"><el-icon><Delete /></el-icon></el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>合计行数: {{ subtotals.count }}</span>
        <span>应计提合计: {{ fmtNum(subtotals.estimatedExpense) }}</span>
        <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
      </div>
    </el-card>

    <!-- ═══（四）预计保修发生时间 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（四）预计保修发生时间（流动/非流动划分）</span>
          <el-button v-if="!isReadonly" size="small" @click="addTimingRow()">＋ 新增产品</el-button>
        </div>
      </template>
      <el-table :data="timingRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="产品" min-width="140">
          <template #default="{ row }"><el-input v-model="row.productName" :disabled="isReadonly" size="small" @change="(v: string) => updateTimingCell(row.rowId, 'productName', v)" /></template>
        </el-table-column>
        <el-table-column label="期末数" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.endBalance" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateTimingCell(row.rowId, 'endBalance', v)" /></template>
        </el-table-column>
        <el-table-column label="1年以内" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.within1Year" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateTimingCell(row.rowId, 'within1Year', v)" /></template>
        </el-table-column>
        <el-table-column label="1年以上" width="130" align="right">
          <template #default="{ row }"><el-input-number v-model="row.over1Year" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateTimingCell(row.rowId, 'over1Year', v)" /></template>
        </el-table-column>
        <el-table-column label="校验" width="70" align="center">
          <template #default="{ row }">
            <el-icon v-if="row.endBalance > 0 && Math.abs(row.endBalance - (row.within1Year || 0) - (row.over1Year || 0)) > 0.01" color="#f56c6c"><WarningFilled /></el-icon>
            <el-icon v-else-if="row.endBalance > 0" color="#67c23a"><CircleCheckFilled /></el-icon>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeTimingRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　期末：{{ fmtNum(timingSubtotals.endBalance) }}　1年内：{{ fmtNum(timingSubtotals.within1Year) }}　1年上：{{ fmtNum(timingSubtotals.over1Year) }}</div>
        </template>
      </el-table>
      <el-alert v-if="timingMismatchCount > 0" type="warning" :closable="false" show-icon style="margin-top:8px">
        <template #title>{{ timingMismatchCount }} 行的"期末数 ≠ 1年内 + 1年上"，请检查划分</template>
      </el-alert>
    </el-card>

    <!-- ═══（五）保修率异常预警 + 行业参考 ═══ -->
    <el-card v-if="rateAnomalies.length > 0 || showIndustryRef" shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（五）保修率合理性评价</span>
          <el-button size="small" link @click="showIndustryRef = !showIndustryRef">
            {{ showIndustryRef ? '收起参考' : '📊 行业参考' }}
          </el-button>
        </div>
      </template>
      <!-- 异常预警 -->
      <div v-if="rateAnomalies.length > 0" class="rate-anomaly-list">
        <div v-for="a in rateAnomalies" :key="a.product" class="anomaly-item">
          <el-icon color="#e6a23c"><WarningFilled /></el-icon>
          <span><b>{{ a.product }}</b>：本期保修率 {{ (a.currentRate * 100).toFixed(3) }}% {{ a.direction }}3年均值 {{ (a.avgRate * 100).toFixed(3) }}%（偏离{{ (a.deviation * 100).toFixed(1) }}%），应关注原因</span>
        </div>
      </div>
      <!-- 行业参考 -->
      <div v-if="showIndustryRef" class="industry-ref">
        <div class="ir-title">常见行业产品保修率参考区间</div>
        <el-table :data="industryRateRef" size="small" border style="width:100%;max-width:500px">
          <el-table-column prop="industry" label="行业" width="140" />
          <el-table-column prop="range" label="保修率参考区间" width="140" />
          <el-table-column prop="note" label="备注" min-width="160" />
        </el-table>
        <div class="ir-note">以上为公开数据参考区间，具体应结合企业产品特点、保修政策和历史数据综合判断。</div>
      </div>
    </el-card>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div style="margin-bottom:10px">
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="概述产品质量保修检查情况：保修政策/历史保修率趋势/测算差异/差异处理/流动非流动划分合理性等"
          @change="persistNote" />
      </div>
      <div>
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="基于上述检查，对预计负债-产品质量保证的完整性、计量合理性和披露形成结论..."
          @change="persistNote" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>历史保修率 = 近3年实际保修支出合计 / 近3年销售收入合计（加权平均）</li>
        <li>应计提金额 = 计提基数（本期销售收入）× 历史保修率</li>
        <li>差异金额 = 应计提 − 账面已计提；差异较大应说明原因或提出调整</li>
        <li>负债类期末 = 期初 + 本期计提 − 本期使用（转销）</li>
        <li>预计发生时间用于流动/非流动划分：1年以内→流动，1年以上→非流动</li>
        <li>K5-4 期末合计应与 K5-1 审定表"产品质量保证"行审定数一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabWarrantyCheck.vue — K5-4 产品质量保修检查表
 * 源模板4区段：政策 / 3年历史保修率对照 / 重新测算差异表 / 预计保修发生时间
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.4（源模板对齐增强）
 * Requirements: 6.1-6.4
 */
import { ref, toRef, computed, onMounted } from 'vue'
import { Plus, Delete, MagicStick, Download, ArrowDown, WarningFilled, CircleCheckFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useK5Warranty } from '../../composables/useK5Warranty'
import http from '@/utils/http'
import type { Ref } from 'vue'

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

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  warrantyRows,
  subtotals,
  crossCheck,
  updateCell,
  addRow,
  removeRow,
  policyText,
  updatePolicy,
  historyRows,
  historySubtotals,
  updateHistoryCell,
  addHistoryRow,
  removeHistoryRow,
  timingRows,
  timingSubtotals,
  updateTimingCell,
  addTimingRow,
  removeTimingRow,
} = useK5Warranty({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-4-ai-trigger', { remark: 'warranty-conclusion' }) }

/** 从(二)历史保修率表自动带入到(三)测算表的计提比例（仅填空值） */
function applyHistoryRateToCalc(): void {
  if (!historyRows.value.length) {
    ElMessage.warning('请先填写(二)历史质量保修情况')
    return
  }
  const avgRate = historySubtotals.value.avgRate
  if (avgRate <= 0) {
    ElMessage.warning('历史保修率为0，无法带入')
    return
  }
  let filled = 0
  for (const row of warrantyRows.value) {
    if (!row.warrantyRate || row.warrantyRate === 0) {
      updateCell(row.rowId, 'warrantyRate', avgRate)
      filled++
    }
  }
  if (filled > 0) {
    ElMessage.success(`已将3年平均保修率 ${(avgRate * 100).toFixed(3)}% 填入 ${filled} 行（仅填空值）`)
  } else {
    ElMessage.info('所有行已有计提比例，未覆盖')
  }
}

/** 从 D4 营业收入审定数带入计提基数（仅填空值不覆盖） */
async function pullD4Revenue(): Promise<void> {
  try {
    // 经 custom-query 端点取 D4 收入审定数
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6001' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let totalRevenue = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6001')) {
        // 损益类取发生额：贷方-借方（收入正数）
        const creditAmt = Number(item.credit_amount ?? 0)
        const debitAmt = Number(item.debit_amount ?? 0)
        totalRevenue += (creditAmt - debitAmt)
      }
    }
    if (totalRevenue <= 0) {
      // 回退取 audited_amount
      totalRevenue = list
        .filter((item: any) => String(item.standard_account_code ?? '').startsWith('6001'))
        .reduce((s: number, item: any) => s + Math.abs(Number(item.audited_amount ?? 0)), 0)
    }
    if (totalRevenue <= 0) {
      ElMessage.warning('未取到D4营业收入数据（科目6001）')
      return
    }
    await ElMessageBox.confirm(
      `D4 营业收入审定合计：${fmtNum(totalRevenue)} 元\n\n是否将此金额填入测算表各行"计提基数(收入)"字段？（仅填空值不覆盖）`,
      '从D4带入收入',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }
    )
    // 填入到测算表各行（仅空值）
    let filled = 0
    for (const row of warrantyRows.value) {
      if (!row.revenue || row.revenue === 0) {
        updateCell(row.rowId, 'revenue', totalRevenue)
        filled++
      }
    }
    if (filled > 0) {
      ElMessage.success(`已填入 ${filled} 行，收入 ${fmtNum(totalRevenue)} 元`)
    } else {
      ElMessage.info('所有行已有收入数据，未覆盖')
    }
  } catch (err: any) {
    if (err !== 'cancel' && err?.toString() !== 'cancel') {
      ElMessage.warning('从D4带入收入失败')
    }
  }
}

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 保修率异常预警 ──────────────────────────────────────────────────────────

interface RateAnomaly {
  product: string
  currentRate: number
  avgRate: number
  deviation: number
  direction: string
}

const rateAnomalies = computed<RateAnomaly[]>(() => {
  const anomalies: RateAnomaly[] = []
  for (const row of historyRows.value) {
    if (!row.currentRevenue || row.currentRevenue <= 0) continue
    const currentRate = (row.currentActual || 0) / row.currentRevenue
    const avgRate = row.avgRate || 0
    if (avgRate <= 0) continue
    const deviation = Math.abs(currentRate - avgRate) / avgRate
    if (deviation > 0.5) { // 偏离50%以上
      anomalies.push({
        product: row.productName || '未命名',
        currentRate,
        avgRate,
        deviation,
        direction: currentRate > avgRate ? '高于' : '低于',
      })
    }
  }
  return anomalies
})

// ─── 行业保修率参考 ──────────────────────────────────────────────────────────

const showIndustryRef = ref(false)

const industryRateRef = [
  { industry: '汽车制造', range: '1.0% - 3.0%', note: '含三包政策延保' },
  { industry: '家用电器', range: '0.5% - 2.0%', note: '白色家电偏低/小家电偏高' },
  { industry: '建筑施工', range: '2.0% - 5.0%', note: '质保期通常2-5年' },
  { industry: '电子产品', range: '1.0% - 3.5%', note: '消费电子退换率较高' },
  { industry: '机械设备', range: '0.5% - 2.5%', note: '大型设备质保期长' },
  { industry: '医疗器械', range: '1.0% - 4.0%', note: '三类器械要求严格' },
  { industry: '软件/IT', range: '0.2% - 1.0%', note: '主要为服务承诺' },
]

// ─── 预计发生时间校验 ────────────────────────────────────────────────────────

const timingMismatchCount = computed(() => {
  return timingRows.value.filter((r: any) =>
    r.endBalance > 0 && Math.abs(r.endBalance - (r.within1Year || 0) - (r.over1Year || 0)) > 0.01
  ).length
})

// ─── 审计说明与结论 ──────────────────────────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

function loadNote(): void {
  const noteItem = props.allResponses.get('K5-4-audit-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const conclItem = props.allResponses.get('K5-4-audit-conclusion')
  if (conclItem?.remark) auditConclusion.value = conclItem.remark
}

function persistNote(): void {
  emit('save', 'K5-4-audit-note', { remark: auditNote.value })
  emit('save', 'K5-4-audit-conclusion', { remark: auditConclusion.value })
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleExportTemplate(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-template`, null, { params: { sheet: 'K5-4' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'K5-4_产品质保_模板.xlsx'; a.click(); URL.revokeObjectURL(url)
    ElMessage.success('模板已下载')
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-data`, null, { params: { sheet: 'K5-4' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'K5-4_产品质保_数据.xlsx'; a.click(); URL.revokeObjectURL(url)
    ElMessage.success('数据已导出')
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportData(): Promise<void> {
  const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]; if (!file) return
    const formData = new FormData(); formData.append('file', file)
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/k5/import-data`, formData, { params: { sheet: 'K5-4' }, headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
      ElMessage.success(`导入成功，共 ${res?.data?.imported_count ?? res?.data?.data?.rowCount ?? 0} 条`)
    } catch (err: any) { ElMessage.error('导入失败：' + (err?.response?.data?.message || err?.response?.data?.detail || '文件格式错误')) }
  }
  input.click()
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => { loadNote() })
</script>

<style scoped>
.k5-tab-warranty { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.cross-check-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.k5-section-card { margin-bottom: 12px; }
.k5-section-card :deep(.el-card__header) { padding: 8px 14px; }
.k5-section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.hnum { width: 100%; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: #606266; font-weight: 600; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
/* 保修率异常 */
.rate-anomaly-list { margin-bottom: 10px; }
.anomaly-item { display: flex; align-items: flex-start; gap: 6px; padding: 4px 0; font-size: 12px; color: #78350f; line-height: 1.5; }
/* 行业参考 */
.industry-ref { margin-top: 10px; }
.ir-title { font-weight: 600; font-size: 12px; color: #303133; margin-bottom: 6px; }
.ir-note { margin-top: 6px; font-size: 11px; color: #909399; font-style: italic; }
</style>
