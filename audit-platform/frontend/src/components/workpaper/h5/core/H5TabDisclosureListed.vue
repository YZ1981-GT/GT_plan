<template>
  <div class="h5-tab-disclosure-listed">
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ H5_DISCLOSURE_SHEET_LISTED }}</h3>
        <el-tag type="info" size="small">本版不适用</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="emit('navigate', H5_DISCLOSURE_SHEET_SOE)">
          → 打开国企版披露表
        </el-button>
        <GtReviewTrigger section-id="H5-附注上市-不适用" label="💬 复核" />
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="not-applicable-alert">
      <template #title>上市准则下油气资产不单独设附注章节 —— 源模板有表格，但附注侧无落点</template>
      <template #default>
        <p class="reason">{{ H5_LISTED_NOT_APPLICABLE_REASON.summary }}</p>
        <ul class="reason-list">
          <li v-for="(e, i) in H5_LISTED_NOT_APPLICABLE_REASON.evidence" :key="i">{{ e }}</li>
        </ul>
      </template>
    </el-alert>

    <el-card shadow="never" class="disclosure-card">
      <template #header><span>不适用判据（源模板与附注真源双证）</span></template>
      <el-descriptions :column="1" border size="small">
        <el-descriptions-item label="源模板文件">
          backend/wp_templates/H/H5 油气资产.xlsx
        </el-descriptions-item>
        <el-descriptions-item label="源模板 sheet">
          {{ H5_DISCLOSURE_SHEET_LISTED }}（visible）
        </el-descriptions-item>
        <el-descriptions-item label="sheet 内容">
          <strong>有表格</strong>：A7:G7 表头（项目 / 探明矿区权益 / 未探明矿区权益 /
          井及相关设施 / … / … / 合计）+ 行 8~38 四层 31 行（一、账面原值 → 四、账面价值）
        </el-descriptions-item>
        <el-descriptions-item label="附注章节矩阵">
          you_qi_zi_chan → listed_standalone / listed_consolidated <strong>均为 null</strong>
        </el-descriptions-item>
        <el-descriptions-item label="上市附注模板">
          note_template_listed.json 含「油气」的章节数 <strong>0</strong>（共 204 章节）
        </el-descriptions-item>
        <el-descriptions-item label="国企版对应章节">
          {{ H5_NOTE_SECTION.soe }} 油气资产（{{ H5_DISCLOSURE_SHEET_SOE }}）
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <details class="h5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>
          本页<strong>不是缺功能</strong>：源 sheet 的四层表是模板作者预留的通用格式，
          上市准则未把油气资产列为单独附注项目，故无附注章节可落 —— 强行推送会新建虚构章节
        </li>
        <li>上市项目的油气资产审计工作在 H5-1 审定表、H5-2 明细表与 H5A 程序表完成</li>
        <li>若项目适用国企格式，请到「{{ H5_DISCLOSURE_SHEET_SOE }}」编制披露表</li>
        <li>如后续上市准则要求单独披露，须先补附注章节矩阵与模板章节，再启用本页</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H5TabDisclosureListed — 油气资产附注披露（上市）：**本版不适用说明页**
 *
 * Spec: `.kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/` Task 11
 * （R12.1 ~ R12.6）
 *
 * 🔴 与 N4 国企侧「源模板内容为无」**不同构**，文案不得照抄：
 * N4 的 soe sheet 逐字是 `附注披露信息：` / `无`（真·无内容）；
 * 而 H5 的 `附注披露信息（上市公司）` 是 **visible 且有完整 38 行四层表**。
 * 不适用的唯一依据在**落点侧**：
 * - `note_template_variant_matrix.json` · `you_qi_zi_chan` 的
 *   `listed_standalone` / `listed_consolidated` **均为 `null`**
 * - `note_template_listed.json` 含「油气」的章节数**实测 0**
 * - `h5NoteSectionMap.H5_NOTE_SECTION` 只有 `soe` 键
 *
 * 🔴 改造前本组件有一处**活缺陷**：`noteSectionId: H5_NOTE_SECTION.listed ?? '五、油气资产'`
 * —— `H5_NOTE_SECTION` 连 `listed` 键都没有（`?? ` 恒取右值）⇒ 向 AI／复核链路下发
 * **凭空编造的章节号 `五、油气资产`**（listed 模板里不存在）。故本页删掉
 * `useHCycleDisclosureAi` 接线与两张自造附注表（`costNoteRows`/`depletionNoteRows`）。
 *
 * 数据侧安全：`H5-disc-listed-text` 全库 `checklist_responses` **0 行**（实测），
 * 故删除该持久化键零数据丢失。
 */
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import {
  H5_DISCLOSURE_SHEET_LISTED,
  H5_DISCLOSURE_SHEET_SOE,
  H5_LISTED_NOT_APPLICABLE_REASON,
  H5_NOTE_SECTION,
} from '../../composables/h5NoteSectionMap'

defineProps<{
  wpId: string
  projectId?: string
  allResponses?: Map<string, any>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()
</script>

<style scoped>
.h5-tab-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left,
.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.not-applicable-alert {
  margin-bottom: 16px;
}

.reason {
  margin: 6px 0 0;
  line-height: 1.8;
}

.reason-list {
  margin: 6px 0 0;
  padding-left: 20px;
  line-height: 1.9;
}

.disclosure-card {
  margin-bottom: 16px;
}

.h5-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  color: #606266;
}

.h5-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.h5-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.9;
}
</style>
