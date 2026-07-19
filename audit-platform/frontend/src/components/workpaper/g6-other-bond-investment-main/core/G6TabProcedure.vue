<script setup lang="ts">
/** G6A — 其他债权投资实质性程序表（对齐 D4A） */
import CycleProgramConsoleTab from '../../shared/CycleProgramConsoleTab.vue'
import { G_CYCLE_PROCEDURE_SHEETS } from '../../composables/cycleProcedureSheets'

const cfg = G_CYCLE_PROCEDURE_SHEETS.G6A

defineProps<{
  htmlData?: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly?: boolean
  readonly?: boolean
}>()
</script>

<template>
  <div class="g6-tab-procedure-wrap">
    <CycleProgramConsoleTab
      :html-data="htmlData"
      :wp-id="wpId"
      :project-id="projectId"
      :is-readonly="isReadonly"
      :readonly="readonly"
      :sheet-code="cfg.sheetCode"
      :sheet-label="cfg.sheetLabel"
      :review-section-id="cfg.reviewSectionId"
      root-class="g6-tab-procedure"
    />

    <details class="guide-details">
      <summary>📋 编制提示</summary>
      <div class="guide-content">
        <p>1. G6A 是其他债权投资实质性程序总控表：勾选/记录拟执行与已执行程序，并与各明细底稿索引对应。</p>
        <p>2. 建议编制顺序：G6-7/G6-8（分类）→ G6-2（明细）→ G6-6（利息）/ G6-5（公允价值）→ G6-9/G6-10（盘点倒轧）→ G6-11~14（ECL）→ G6-15（抽凭）→ G6-4（调整）→ G6-1（审定）→ 附注。</p>
        <p>3. 每完成一项程序，在本表标记执行情况并填写索引（如 wp:G6-2、wp:G6-6）；例外事项索引至 G6-4 或说明不调整理由。</p>
        <p>4. 函证相关程序可交叉引用投资循环函证底稿（G0-x）；替代程序须在备注中说明范围与结论。</p>
        <p>5. 本表不替代各明细表勾稽：金额审定以 G6-1 为准，程序执行完整性以本表勾选为准。</p>
        <p>6. 复核时核对：计划程序是否均已执行或豁免说明充分；未执行高风险程序不得直接出具「未见异常」结论。</p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.guide-details {
  margin: 0 12px 16px;
}
.guide-details summary {
  cursor: pointer;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  font-weight: 600;
}
.guide-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}
.guide-content p {
  margin: 0;
}
</style>
