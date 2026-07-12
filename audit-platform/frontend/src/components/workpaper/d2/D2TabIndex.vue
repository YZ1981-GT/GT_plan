<script setup lang="ts">

/**

 * D2TabIndex — 统一底稿目录（合并3个源xlsx底稿目录）

 * 参照 D4TabIndex：进度条 + GtIndexChip 跳转 + 编制进度

 */

import { computed, inject, onMounted } from 'vue'

import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useAcnrCatalogIndex } from '../composables/useAcnrCatalogIndex'



const props = defineProps<{

  wpId: string

  projectId: string

  allResponses: Map<string, any>

  isReadonly: boolean

}>()



/**
 * 本地目录配置（Req 18.2 / 18.5）：仅保留 catalog 不持有的路由/状态元数据，
 * 按 sheet_code(=code) keyed：
 *   - code       : sheet_code（与 ACNR catalog 合并的主键）
 *   - name       : 硬编码名称，仅作 catalog 不可用时的回退（Req 18.7）
 *   - group      : 分组（本地展示元数据）
 *   - sheetLabel : bundle 内 jumpToSection 目标（纯 sheet 切换，Req 18.3）
 *   - applicable : 适用性（本地逻辑，Req 18.5）
 * 显示用的 name/order/addr_id 由 displayRows 从 ACNR catalog 合并覆盖（Req 18.1）。
 */
interface IndexRow {

  seq: number

  name: string

  code: string

  group: string

  sheetLabel: string

  applicable: boolean

}



const indexRows: IndexRow[] = [

  { seq: 1, name: '应收账款实质性程序表', code: 'D2A', group: '核心', sheetLabel: '应收账款实质性程序表D2A', applicable: true },

  { seq: 2, name: '应收账款审定表', code: 'D2-1', group: '核心', sheetLabel: '审定表D2-1', applicable: true },

  { seq: 3, name: '应收账款明细表', code: 'D2-2', group: '核心', sheetLabel: '明细表D2-2', applicable: true },

  { seq: 4, name: '坏账准备明细表', code: 'D2-3', group: '核心', sheetLabel: '坏账准备明细表D2-3', applicable: true },

  { seq: 5, name: '调整分录汇总表', code: 'D2-4', group: '核心', sheetLabel: '调整分录汇总表D2-4', applicable: true },

  { seq: 6, name: '附注披露信息（上市公司）', code: '附注上市', group: '核心', sheetLabel: '附注披露信息(上市公司)', applicable: true },

  { seq: 7, name: '附注披露信息（国企）', code: '附注国企', group: '核心', sheetLabel: '附注披露信息(国企)', applicable: true },

  { seq: 8, name: '应收账款分析表', code: 'D2-5', group: '分析', sheetLabel: '应收账款分析表D2-5', applicable: true },

  { seq: 9, name: '关联方及交易检查表', code: 'D2-6', group: '检查', sheetLabel: '关联方及交易检查表D2-6', applicable: true },

  { seq: 10, name: '应收账款检查表', code: 'D2-7', group: '检查', sheetLabel: '应收账款检查表D2-7', applicable: true },

  { seq: 11, name: '坏账准备计提会计政策检查', code: 'D2-8', group: '检查', sheetLabel: '坏账准备计提会计政策检查D2-8', applicable: true },

  { seq: 12, name: '应收坏账准备测算', code: 'D2-9', group: '检查', sheetLabel: '应收坏账准备测算D2-9', applicable: true },

  { seq: 13, name: '预期信用损失计量测试', code: 'D2-10', group: '检查', sheetLabel: '预期信用损失的计量测试D2-10', applicable: true },

  { seq: 14, name: '坏账准备转回（收回）、核销检查表', code: 'D2-11', group: '检查', sheetLabel: '坏账准备转回（收回）、核销检查表D2-11', applicable: true },

  { seq: 15, name: '应收账款质押出售情况检查表', code: 'D2-12', group: '检查', sheetLabel: '应收账款质押出售情况检查表D2-12', applicable: true },

  { seq: 16, name: '应收账款业务模式分析', code: 'D2-13', group: '检查', sheetLabel: '应收账款业务模式分析D2-13', applicable: true },

]



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

    case 'D2A':

      return hasJsonRows(m, 'D2-procedure-steps') || hasText(m, 'D2-procedure-overall-conclusion')

    case 'D2-1':

      return [...m.keys()].some(k => k.startsWith('D2-adj-'))

    case 'D2-2':

      return hasJsonRows(m, 'D2-detail-rows')

    case 'D2-3':

      return hasJsonRows(m, 'D2-bd-individual-rows')

        || hasJsonRows(m, 'D2-bd-aging-rows')

        || hasJsonRows(m, 'D2-bd-customer-rows')

    case 'D2-4':

      return hasJsonRows(m, 'D2-entry-rows')

    case '附注上市':

    case '附注国企':

      return [...m.keys()].some(k => k.startsWith('D2-disc-'))

    case 'D2-5':

      return hasText(m, 'D2-analysis-remark') || hasText(m, 'D2-analysis-dataSource')

    case 'D2-6':

      return hasJsonRows(m, 'D2-related-party-rows')

    case 'D2-7':

      return hasJsonRows(m, 'D2-voucher-samples')

    case 'D2-8': {

      const para = m.get('D2-policy-paragraphs')?.remark

      if (!para) return false

      try {

        const arr = JSON.parse(para)

        return Array.isArray(arr) && arr.some((p: any) => p.conclusion)

      } catch { return false }

    }

    case 'D2-9':

      return hasJsonRows(m, 'D2-ecl-single-rows')

    case 'D2-10':

      return hasJsonRows(m, 'D2-ecl-migration-matrix') || hasJsonRows(m, 'D2-ecl-discount-rows')

    case 'D2-11':

      return hasJsonRows(m, 'D2-writeoff-reversal-rows') || hasJsonRows(m, 'D2-writeoff-writeoff-rows')

    case 'D2-12':

      return hasJsonRows(m, 'D2-pledge-rows') || hasJsonRows(m, 'D2-factoring-rows')

    case 'D2-13':

      return hasJsonRows(m, 'D2-bizmodel-judgments') || hasJsonRows(m, 'D2-bizmodel-groups')

    default:

      return false

  }

}



// ─── ACNR catalog 名称合并（Req 18.1 / 18.2 / 18.7）───────────────────────────
// catalog 提供 sheet_name/addr_id/order 真源；按 code(=sheet_code) 合并覆盖显示名称。
// catalog 空/失败 → 回退本地硬编码 name，保证目录不空白（Req 18.7）。
const { catalogIndex, loadCatalogIndex } = useAcnrCatalogIndex()

onMounted(() => {
  // D2 属于 D 循环；catalog 不可用时 map 为空，displayRows 自动回退硬编码。
  loadCatalogIndex('D')
})

interface DisplayRow extends IndexRow {
  /** ACNR catalog addr_id（命中时），供跨底稿一致性/未来 chip 使用 */
  addrId?: string
  /** 显示/排序 order：catalog 优先，缺失回退本地 seq */
  order: number
}

const displayRows = computed<DisplayRow[]>(() =>
  indexRows.map((r) => {
    const cat = catalogIndex.value.get(r.code)
    return {
      ...r,
      // 名称从 catalog 取（Req 18.1）；miss/空 → 回退硬编码（Req 18.7）
      name: cat?.sheet_name || r.name,
      addrId: cat?.addr_id,
      order: cat?.order ?? r.seq,
    }
  }),
)



const applicableRows = computed(() => displayRows.value.filter(r => r.applicable))



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

  <div class="d2-tab-index">

    <div class="index-header">

      <h3>D2 应收账款底稿目录</h3>
      <GtReviewTrigger section-id="D2-index-directory" />

      <div class="progress-wrap">

        <span class="progress-label">编制进度 {{ completedCount }}/{{ applicableRows.length }}</span>

        <el-progress :percentage="progressPct" :stroke-width="10" />

      </div>

    </div>



    <el-table :data="displayRows" size="small" border stripe>

      <el-table-column prop="seq" label="序号" width="60" align="center" />

      <el-table-column prop="group" label="分组" width="80" />

      <el-table-column prop="code" label="索引号" width="90" />

      <el-table-column label="底稿名称" min-width="260">

        <template #default="{ row }">

          <span :class="{ 'na-row': !row.applicable }">{{ row.name }}</span>

          <GtIndexChip

            v-if="row.applicable && jumpToSection"

            :label="row.code"

            :prevent-navigate="true"

            :validate="false"

            class="index-chip"

            @click="jumpToSection(row.sheetLabel)"

          />

          <el-tag

            v-if="row.applicable && isSheetComplete(row.code, allResponses)"

            type="success"

            size="small"

            class="done-tag"

          >已编制</el-tag>
          <GtReviewDot v-if="row.applicable" :section-id="`D2-index-${row.code}`" class="index-review-dot" />

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

      <p>推荐工作流：D2A 程序表 → D2-1 审定表 → D2-2 明细表 → D2-5 分析 → D2-9 政策 → D2-10 测算 → D2-4 调整分录。D2-2 信用风险组合方式列驱动 D2-1 SUMIF 聚合。</p>

    </details>

  </div>

</template>



<style scoped>

.d2-tab-index { padding: 4px 0; }

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

