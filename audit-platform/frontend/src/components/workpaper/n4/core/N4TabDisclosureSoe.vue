<template>
  <div class="n4-tab-disclosure-soe">
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ N4_DISCLOSURE_SHEET_NAME.soe }}</h3>
        <el-tag type="info" size="small">本版不适用</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="emit('navigate', '附注披露信息（上市公司）')">
          → 打开上市版披露表
        </el-button>
        <GtReviewTrigger section-id="N4-附注国企-不适用" label="💬 复核" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="not-applicable-alert">
      <template #title>国有企业格式财务报表不单独披露税金及附加</template>
      <template #default>
        <p class="reason">{{ N4_SOE_NOT_APPLICABLE_REASON }}</p>
      </template>
    </el-alert>

    <el-card shadow="never" class="disclosure-card">
      <template #header><span>源模板依据</span></template>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="源模板文件">
          backend/wp_templates/N/N4 税金及附加.xlsx
        </el-descriptions-item>
        <el-descriptions-item label="源模板 sheet">
          {{ N4_DISCLOSURE_SHEET_NAME.soe }}
        </el-descriptions-item>
        <el-descriptions-item label="sheet 内容">
          R5 「附注披露信息：」 / R6 「无」（全 sheet 无表格）
        </el-descriptions-item>
        <el-descriptions-item label="附注章节矩阵">
          shui_jin_ji_fu_jia → soe_standalone / soe_consolidated 均为空
        </el-descriptions-item>
        <el-descriptions-item label="上市版对应章节">
          {{ N4_NOTE_SECTION.listed }} 税金及附加
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <details class="n4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本页<strong>不是缺功能</strong>：源模板国企版本节内容为「无」，故无披露表、无同步按钮、不产生附注章节</li>
        <li>国企项目的税金及附加审计工作在 N4-1 审定表、N4-2 明细表与 N4A 程序表完成</li>
        <li>若项目同时适用上市准则，请到「{{ N4_DISCLOSURE_SHEET_NAME.listed }}」编制披露表</li>
        <li>如后续国资委格式要求披露，须先补附注章节矩阵与模板章节，再启用本页</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabDisclosureSoe — 税金及附加附注披露（国企）：**本版不适用说明页**
 *
 * Spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`（R2.4 / R5.7 / R6.5）
 *
 * 🔴 源模板 `N4 税金及附加.xlsx` 的 `附注披露信息（国企）` sheet 内容是
 * `附注披露信息：` / **`无`** —— 国有企业格式财务报表不单独披露税金及附加。
 * `note_template_variant_matrix.json` 里 `shui_jin_ji_fu_jia` 的 soe 变体为 `null`，是正确的。
 *
 * 本组件此前是**自造的整套国企披露表**（把上市口径复制过来还加了变动分析列），
 * 会把不存在的章节推给附注。现改为说明页：不提供表格、不提供同步入口、
 * `buildN4SyncPayload('soe', …)` 恒返回 `null`。
 */
import { onMounted } from 'vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  N4_DISCLOSURE_SHEET_NAME,
  N4_NOTE_SECTION,
  N4_SOE_NOT_APPLICABLE_REASON,
} from '../../composables/n4NoteSectionMap'

defineProps<{
  wpId: string
  projectId?: string
  allResponses?: Map<string, any>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

onMounted(() => {
  // 无数据加载：本页无持久化字段，避免多余请求
})
</script>

<style scoped>
.n4-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.not-applicable-alert { margin-bottom: 16px; }
.reason { margin: 6px 0 0; line-height: 1.8; }

.disclosure-card { margin-bottom: 16px; }

.n4-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
