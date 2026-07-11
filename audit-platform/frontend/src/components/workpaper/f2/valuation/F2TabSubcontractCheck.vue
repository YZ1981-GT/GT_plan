<template>
  <div class="f2-val-sheet">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表抽取样本核查委外加工业务，逐笔核对委托方、单号、品名、金额、账龄与凭证。</p>
        <p>2. 覆盖率＝已查金额 / 账面总额，覆盖率偏低时自动橙色提示，应扩大样本或说明抽样理由。</p>
        <p>3. 关注委外加工物资的发出、收回与加工费归集是否完整，账龄异常（长期挂账）须重点核查。</p>
        <p>4. 依《企业会计准则第 1 号——存货》，加工成本应准确计入委托加工物资成本，防止跨期或漏记。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：验证委外加工物资发出、收回及加工费归集的真实性与完整性，确认委托加工物资成本计价准确。"
    />

    <header class="sheet-header">
      <div><h3>{{ ic.title }}</h3><span class="code">{{ ic.sheetCode }}</span></div>
      <span :class="['coverage', { warn: ic.isCoverageLow.value }]">覆盖率 {{ ic.coverageRatio.value.toFixed(1) }}%</span>
    </header>
    <div class="meta-bar">
      <span>账面总额<el-input-number :model-value="ic.bookTotal.value" size="small" :controls="false" :disabled="isReadonly" @change="(v: number) => ic.updateBookTotal(v ?? 0)" /></span>
      <span>已查 {{ ic.checkedTotal.value.toLocaleString() }}</span>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="ic.addRow()">+ 新增</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-val"
          sheet="F2-35"
          :disabled="isReadonly"
          ai-section="inspection-conclusion"
          :existing-content="ic.auditNote.value"
          :related-context="{ coverageRatio: ic.coverageRatio.value }"
          ai-title="AI 生成 · 委外加工检查结论"
          review-section="F2-35-conclusion"
          @ai-filled="(t: string) => { ic.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-1" /></span>
        <el-tag size="small" type="info">共 {{ ic.rows.value.length }} 行</el-tag>
      </div>
    </div>
    <el-table :data="ic.rows.value" border size="small" max-height="440">
      <el-table-column prop="seq" label="序号" width="50" />
      <el-table-column label="委托方" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.party" size="small" @change="(v: string) => ic.updateRow(row.id, { party: v })" />
          <span v-else>{{ row.party }}</span>
        </template>
      </el-table-column>
      <el-table-column label="单号" width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.docNo" size="small" @change="(v: string) => ic.updateRow(row.id, { docNo: v })" />
          <span v-else>{{ row.docNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small" @change="(v: string) => ic.updateRow(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100">
        <template #default="{ row }">
          <el-input-number :model-value="row.amount" size="small" :controls="false" :disabled="isReadonly" class="compact-num" @change="(v: number) => ic.updateRow(row.id, { amount: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="账龄(天)" width="85">
        <template #default="{ row }">
          <el-input-number :model-value="row.daysOutstanding ?? 0" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => ic.updateRow(row.id, { daysOutstanding: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="95">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => ic.updateRow(row.id, { voucherNo: v })" />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="48">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="ic.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header"><span class="opinion-title">检查结论</span></div>
      </template>
      <el-input v-model="ic.auditNote.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="请输入委外加工检查结论..." />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import { useF2SubcontractCheck } from '../../composables/useF2InspectionCheck'
import type { ChecklistResponse } from '../../composables/useF2ValuationFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()
const ic = useF2SubcontractCheck({ allResponses: toRef(props, 'allResponses'), isReadonly: toRef(props, 'isReadonly') })
</script>

<style scoped src="./f2ValSheetStyles.css"></style>
<style scoped>
.f2-val-sheet :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.f2-val-sheet :deep(.el-table .cell) { font-size: 13px !important; }
/* 编制提示（蓝色） */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.meta-bar { display: flex; gap: 16px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.coverage { font-weight: 600; }
.coverage.warn { color: #e6a23c; }
/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
/* 审计意见卡片 */
.opinion-card { margin-top: 14px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
