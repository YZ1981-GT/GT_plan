<template>
  <div class="f2-rp-pricing">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表以市场参考价为基准，核查关联方采购定价的公允性（价差率 = 关联方报价 vs 市场价）。</p>
        <p>2. 灰底列为自动计算列（价差率），不可手动编辑；价差率超阈值行标红提示关注。</p>
        <p>3. 市场参考价应留存取价来源（行业报告 / 公开报价 / 招投标），必要时在备注中记录。</p>
        <p>4. 与询价函核查表（F2-65）交叉印证，关注是否存在利益输送或成本操纵。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：以市场价为基准核查关联方采购定价的公允性，识别显著偏离市场的异常交易。</template>
    </el-alert>

    <header class="sheet-header">
      <div>
        <h3>关联方采购定价公允性核查 — 市场价</h3>
        <span class="code">F2-66</span>
      </div>
      <div class="stat-row">
        <el-tag type="info">{{ rp.filteredRows.value.length }} 行</el-tag>
        <el-tag v-if="rp.abnormalCount.value" type="danger">{{ rp.abnormalCount.value }} 行价差异常</el-tag>
      </div>
    </header>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="rp.addRow()">+ 新增</el-button>
        <el-input v-model="rp.searchQuery.value" size="small" placeholder="搜索关联方/品名" clearable class="search" />
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-66"
          :disabled="isReadonly"
          ai-section="related-party-conclusion"
          :existing-content="rp.auditNote.value"
          review-section="F2-66-market"
          @ai-filled="(t: string) => { rp.auditNote.value = t }"
        />
        <GtIndexChip value="wp:F2-66" />
        <el-tag size="small" type="info">共 {{ rp.filteredRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table
      :data="rp.filteredRows.value"
      border size="small" max-height="460"
      :row-class-name="({ row }) => row.highlight ? 'warn-row' : ''"
    >
      <el-table-column type="index" label="序号" width="55" />
      <el-table-column label="关联方名称" width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.relatedParty" size="small"
            @change="(v: string) => rp.updateMarket(row.id, { relatedParty: v })" />
          <span v-else>{{ row.relatedParty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="采购品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => rp.updateMarket(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联方报价" width="105">
        <template #default="{ row }">
          <el-input-number :model-value="row.relatedPrice" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => rp.updateMarket(row.id, { relatedPrice: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="市场参考价" width="105">
        <template #default="{ row }">
          <el-input-number :model-value="row.marketPrice" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => rp.updateMarket(row.id, { marketPrice: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="价差率%" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="价差率 =（关联方报价 − 市场参考价）/ 市场参考价" placement="top">
            <span :class="row.isHighSpread ? 'spread-warn' : 'formula'">{{ rp.fmtSpread(row.spreadPct) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.conclusion || undefined" size="small" clearable
            @change="(v: string) => rp.updateMarket(row.id, { conclusion: v as any })">
            <el-option v-for="c in rp.PRICING_CONCLUSIONS" :key="c" :label="c" :value="c" />
          </el-select>
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
            @change="(v: string) => rp.updateMarket(row.id, { remark: v })" />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="rp.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 定价公允性结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">定价公允性结论</span>
        </div>
      </template>
      <el-input v-model="rp.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="汇总市场价核查结论，说明价差异常行的原因及公允性判断……" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useF2RelatedPartyPricing } from '../../composables/useF2RelatedPartyPricing'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId?: string; allResponses: Map<string, ChecklistResponse>; isReadonly: boolean }>()
const kind = ref<'market'>('market')
const rp = useF2RelatedPartyPricing({
  kind,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-rp-pricing { padding: 12px 16px; font-size: var(--wp-font-size, 13px); background: linear-gradient(180deg, #f8fafc 0%, #fff 100px); border-radius: 8px; }
.f2-rp-pricing :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-rp-pricing :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.stat-row { display: flex; gap: 6px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.search { width: 200px; }
.formula { text-decoration: underline dotted #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.spread-warn { color: #f56c6c; font-weight: 600; background: #fef0f0; padding: 0 4px; border-radius: 2px; }
:deep(.warn-row) { background: #fef0f0; }
:deep(.compact-num) { width: 100%; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
