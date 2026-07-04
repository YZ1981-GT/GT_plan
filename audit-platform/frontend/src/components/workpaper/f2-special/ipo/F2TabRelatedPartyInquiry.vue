<template>
  <div class="f2-rp-pricing">
    <header class="sheet-header">
      <div>
        <h3>关联方采购定价公允性核查 — 询价函</h3>
        <span class="code">F2-65</span>
      </div>
      <div class="stat-row">
        <el-tag type="info">{{ rp.filteredRows.value.length }} 行</el-tag>
        <el-tag v-if="rp.abnormalCount.value" type="danger">{{ rp.abnormalCount.value }} 行价差异常</el-tag>
        <el-tag v-if="rp.unfairCount.value" type="warning">{{ rp.unfairCount.value }} 行待关注结论</el-tag>
      </div>
    </header>

    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="rp.addRow()">+ 新增</el-button>
      <F2SheetToolbar
        :wp-id="wpId"
        api-prefix="f2-spe"
        sheet="F2-65"
        :disabled="isReadonly"
        ai-section="related-party-conclusion"
        :existing-content="rp.auditNote.value"
        review-section="F2-65-inquiry"
        @ai-filled="(t: string) => { rp.auditNote.value = t }"
      />
      <el-input v-model="rp.searchQuery.value" size="small" placeholder="搜索关联方/品名" clearable class="search" />
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
            @change="(v: string) => rp.updateInquiry(row.id, { relatedParty: v })" />
          <span v-else>{{ row.relatedParty }}</span>
        </template>
      </el-table-column>
      <el-table-column label="采购品名" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.itemName" size="small"
            @change="(v: string) => rp.updateInquiry(row.id, { itemName: v })" />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="关联方报价" width="105">
        <template #default="{ row }">
          <el-input-number :model-value="row.relatedPrice" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => rp.updateInquiry(row.id, { relatedPrice: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="第三方名称" width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.thirdPartyName" size="small"
            @change="(v: string) => rp.updateInquiry(row.id, { thirdPartyName: v })" />
          <span v-else>{{ row.thirdPartyName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="第三方报价" width="105">
        <template #default="{ row }">
          <el-input-number :model-value="row.inquiryPrice" size="small" :controls="false" :disabled="isReadonly"
            class="compact-num" @change="(v: number) => rp.updateInquiry(row.id, { inquiryPrice: v ?? 0 })" />
        </template>
      </el-table-column>
      <el-table-column label="价差率%" width="90" align="right">
        <template #default="{ row }">
          <span :class="row.isHighSpread ? 'spread-warn' : 'formula'">{{ rp.fmtSpread(row.spreadPct) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.conclusion || undefined" size="small" clearable
            @change="(v: string) => rp.updateInquiry(row.id, { conclusion: v as any })">
            <el-option v-for="c in rp.PRICING_CONCLUSIONS" :key="c" :label="c" :value="c" />
          </el-select>
          <span v-else>{{ row.conclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="rp.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <footer class="footer">
      <h4>定价公允性结论</h4>
      <el-input v-model="rp.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly"
        placeholder="汇总询价函核查结论…" />
    </footer>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useF2RelatedPartyPricing } from '../../composables/useF2RelatedPartyPricing'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

const props = defineProps<{ wpId?: string; allResponses: Map<string, ChecklistResponse>; isReadonly: boolean }>()
const kind = ref<'inquiry'>('inquiry')
const rp = useF2RelatedPartyPricing({
  kind,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
</script>

<style scoped>
.f2-rp-pricing { padding: 12px 16px; font-size: 13px; background: linear-gradient(180deg, #f8fafc 0%, #fff 100px); border-radius: 8px; }
.sheet-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-header h3 { margin: 0; font-size: 16px; display: inline; }
.code { font-size: 12px; color: #909399; margin-left: 8px; }
.stat-row { display: flex; gap: 6px; }
.toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
.search { width: 200px; }
.formula { text-decoration: underline dotted #909399; }
.spread-warn { color: #f56c6c; font-weight: 600; background: #fef0f0; padding: 0 4px; border-radius: 2px; }
:deep(.warn-row) { background: #fef0f0; }
:deep(.compact-num) { width: 100%; }
.footer { margin-top: 14px; }
.footer h4 { margin: 0 0 8px; font-size: 13px; color: #606266; }
</style>
