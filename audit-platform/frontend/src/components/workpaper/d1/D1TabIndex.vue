<script setup lang="ts">

/**

 * D1TabIndex — 统一底稿目录（参照 D2TabIndex / D4TabIndex）

 */

import { computed, inject } from 'vue'

import GtIndexChip from '../GtIndexChip.vue'

import GtReviewDot from '../GtReviewDot.vue'

import GtReviewTrigger from '../GtReviewTrigger.vue'

import { D1_INDEX_ROWS, resolveD1SheetLabel } from '../composables/d1SheetLabels'



const props = defineProps<{

  wpId: string

  projectId: string

  allResponses: Map<string, any>

  isReadonly: boolean

  availableSheets?: Array<{ sheet_name?: string }>

}>()



const indexRows = computed(() =>

  D1_INDEX_ROWS.map(row => ({

    ...row,

    sheetLabel: resolveD1SheetLabel(row.code, props.availableSheets),

  })),

)



function hasJsonRows(m: Map<string, any>, key: string): boolean {

  const raw = m.get(key)?.remark

  if (!raw) return false

  try {

    const parsed = JSON.parse(raw)

    return Array.isArray(parsed) && parsed.length > 0

  } catch {

    return false

  }

}



function hasText(m: Map<string, any>, key: string): boolean {

  const v = m.get(key)?.remark

  return typeof v === 'string' && v.trim().length > 0

}



function isSheetComplete(code: string, m: Map<string, any>): boolean {

  switch (code) {

    case 'D1A':

      return hasText(m, 'D1-proc-overall') || [...m.keys()].some(k => k.startsWith('D1-proc-'))

    case 'D1-1':

      return [...m.keys()].some(k => k.startsWith('D1-adj-'))

    case 'D1-2':

      return hasJsonRows(m, 'D1-cat-rows')

    case 'D1-3':

      return hasJsonRows(m, 'D1-cust-rows')

    case 'D1-4':

      return hasJsonRows(m, 'D1-bd-individual-rows') || hasJsonRows(m, 'D1-bd-portfolio-rows')

    case 'D1-5':

      return hasJsonRows(m, 'D1-entry-rows') || hasText(m, 'D1-entry-count') || [...m.keys()].some(k => k.startsWith('D1-entry-'))

    case 'D1-6':

      return hasJsonRows(m, 'D1-bm-basis-rows')

    case 'D1-7':

      return hasJsonRows(m, 'D1-memo-rows')

    case 'D1-8':

      return hasJsonRows(m, 'D1-endorse-discount-rows') || hasJsonRows(m, 'D1-endorse-transfer-rows')

    case 'D1-9':

      return hasJsonRows(m, 'D1-interest-rows')

    case 'D1-10':

      return hasJsonRows(m, 'D1-inventory-rows')

    case 'D1-11':

      return hasJsonRows(m, 'D1-rp-rows')

    case 'D1-12':

      return hasJsonRows(m, 'D1-pledge-rows')

    case 'D1-13':

      return hasJsonRows(m, 'D1-sampling-vouching-rows')

        || hasText(m, 'D1-sampling-population-desc')

        || hasJsonRows(m, 'D1-sampling-specific-samples')

    case 'D1-14': {

      const para = m.get('D1-policy-paragraphs')?.remark

      if (!para) return false

      try {

        const arr = JSON.parse(para)

        return Array.isArray(arr) && arr.some((p: any) => p.conclusion)

      } catch { return false }

    }

    case 'D1-15':

      return hasJsonRows(m, 'D1-ecl-portfolio-rows') || hasJsonRows(m, 'D1-ecl-individual-rows')

    case 'D1-16':

      return hasJsonRows(m, 'D1-writeoff-reversal-rows') || hasJsonRows(m, 'D1-writeoff-writeoff-rows')

    case '附注上市':

    case '附注国企':

      return [...m.keys()].some(k => k.startsWith('D1-disc-'))

    default:

      return false

  }

}



const applicableRows = computed(() => indexRows.value.filter(r => r.applicable))



const completedCount = computed(() =>

  applicableRows.value.filter(r => isSheetComplete(r.code, props.allResponses)).length,

)



const progressPct = computed(() => {

  const total = applicableRows.value.length

  return total > 0 ? Math.round((completedCount.value / total) * 100) : 0

})



const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

</script>



<template>

  <div class="d1-tab-index">

    <div class="index-header">

      <h3>D1 应收票据底稿目录</h3>

      <GtReviewTrigger section-id="D1-index-directory" />

      <div class="progress-wrap">

        <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>

        <el-progress :percentage="progressPct" :stroke-width="10" />

      </div>

    </div>



    <el-table :data="indexRows" size="small" border stripe>

      <el-table-column prop="seq" label="序号" width="60" align="center" />

      <el-table-column prop="group" label="分组" width="80" />

      <el-table-column prop="code" label="索引号" width="90" />

      <el-table-column label="底稿名称" min-width="260">

        <template #default="{ row }">

          <span :class="{ 'na-row': !row.applicable }">{{ row.name }}</span>

          <GtIndexChip

            v-if="row.applicable && jumpToSection"

            :label="row.code"

            class="index-chip"

            @click="jumpToSection(row.sheetLabel)"

          />

          <el-tag

            v-if="row.applicable && isSheetComplete(row.code, allResponses)"

            type="success"

            size="small"

            class="done-tag"

          >已编制</el-tag>

          <GtReviewDot v-if="row.applicable" :section-id="`D1-index-${row.code}`" class="index-review-dot" />

        </template>

      </el-table-column>

      <el-table-column label="适用" width="70" align="center">

        <template #default="{ row }">

          <el-tag :type="row.applicable ? 'success' : 'info'" size="small">

            {{ row.applicable ? '适用' : 'N/A' }}

          </el-tag>

        </template>

      </el-table-column>

    </el-table>



    <details class="methodology-hint">

      <summary>编制提示</summary>

      <p>推荐工作流：D1A 程序表 → D1-1 审定表 → D1-2/D1-3 明细 → D1-4 坏账 → D1-14/D1-15 ECL → D1-5 调整分录。监盘核查组 D1-10~D1-13 可与 D1-1 审定表交叉核对。</p>

    </details>

  </div>

</template>



<style scoped>

.d1-tab-index { padding: 4px 0; }

.index-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }

.index-header h3 { margin: 0; font-size: 16px; color: #303133; }

.progress-wrap { min-width: 220px; }

.progress-label { font-size: 12px; color: #606266; display: block; margin-bottom: 4px; }

.index-chip { margin-left: 8px; }

.done-tag { margin-left: 6px; }

.index-review-dot { margin-left: 4px; }

.na-row { color: #909399; }

.methodology-hint {

  margin-top: 16px;

  padding: 10px 12px;

  border-left: 3px solid #409eff;

  background: #ecf5ff;

  border-radius: 0 4px 4px 0;

  font-size: var(--wp-font-size, 13px);

  color: #606266;

}

.methodology-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }

</style>

