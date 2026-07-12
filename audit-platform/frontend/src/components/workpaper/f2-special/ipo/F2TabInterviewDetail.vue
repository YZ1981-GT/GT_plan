<template>
  <div class="f2-interview-detail">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表逐个记录 IPO 供应商访谈明细，含访谈基本信息、问答记录、审计关注点与结论。</p>
        <p>2. 访谈应核实供应商真实经营、交易内容与金额、是否存在关联关系或代垫资金。</p>
        <p>3. 问答记录应完整反映访谈过程，关注回答与账面记录、合同条款的一致性。</p>
        <p>4. 访谈结论汇总至供应商访谈汇总表（F2-71），异常事项须追查处理。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>审计目标：通过供应商访谈明细验证采购交易的真实性与商业合理性，识别关联关系及异常安排。</template>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-title">供应商访谈记录</span>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-72"
          :disabled="isReadonly"
          ai-section="supplier-analysis"
          :existing-content="md.auditNote.value"
          review-section="F2-72-interview"
          @ai-filled="(t: string) => { md.auditNote.value = t }"
        />
        <GtIndexChip value="wp:F2-72" />
        <el-tag size="small" type="info">共 {{ md.entityList.value.length }} 条</el-tag>
      </div>
    </div>
    <div class="layout">
      <aside class="list-panel">
        <el-input v-model="md.searchQuery.value" size="small" placeholder="搜索..." clearable />
        <el-button size="small" type="primary" class="add-btn" :disabled="isReadonly" @click="md.addEntity()">+ 新增访谈</el-button>
        <ul class="entity-list">
          <li v-for="i in md.entityList.value" :key="i.id"
            :class="{ active: md.currentId.value === i.id }"
            @click="md.selectEntity(i.id)">
            {{ (i as { supplierName?: string }).supplierName }} / {{ (i as { interviewDate?: string }).interviewDate }}
          </li>
        </ul>
      </aside>
      <main v-if="cur" class="detail-panel">
        <div class="field-grid">
          <label class="field">供应商
            <el-input :model-value="cur.supplierName" size="small" :disabled="isReadonly"
              @change="(v: string) => md.updateInterview(cur!.id, { supplierName: v })" />
          </label>
          <label class="field">访谈日期
            <el-input :model-value="cur.interviewDate" size="small" :disabled="isReadonly"
              @change="(v: string) => md.updateInterview(cur!.id, { interviewDate: v })" />
          </label>
          <label class="field">受访人
            <el-input :model-value="cur.interviewee" size="small" :disabled="isReadonly"
              @change="(v: string) => md.updateInterview(cur!.id, { interviewee: v })" />
          </label>
          <label class="field">主题
            <el-input :model-value="cur.topic" size="small" :disabled="isReadonly"
              @change="(v: string) => md.updateInterview(cur!.id, { topic: v })" />
          </label>
        </div>
        <h4>问答记录</h4>
        <div v-for="qa in cur.qaPairs" :key="qa.id" class="qa-block">
          <el-input :model-value="qa.question" type="textarea" :rows="2" placeholder="问题" :disabled="isReadonly"
            @change="(v: string) => md.updateQa(cur!.id, qa.id, { question: v })" />
          <el-input :model-value="qa.answer" type="textarea" :rows="2" placeholder="回答" :disabled="isReadonly"
            @change="(v: string) => md.updateQa(cur!.id, qa.id, { answer: v })" />
          <el-button v-if="!isReadonly && cur.qaPairs.length > 1" link type="danger" size="small"
            @click="md.removeQa(cur!.id, qa.id)">删除问答</el-button>
        </div>
        <el-button v-if="!isReadonly" size="small" @click="md.addQa(cur.id)">+ 添加问答</el-button>
        <label class="field full">审计关注点
          <el-input :model-value="cur.auditFocus" type="textarea" :rows="2" :disabled="isReadonly"
            @change="(v: string) => md.updateInterview(cur!.id, { auditFocus: v })" />
        </label>
        <label class="field full">结论
          <el-input :model-value="cur.conclusion" type="textarea" :rows="2" :disabled="isReadonly"
            @change="(v: string) => md.updateInterview(cur!.id, { conclusion: v })" />
        </label>
        <el-button v-if="!isReadonly" type="danger" link size="small" @click="md.removeEntity(cur.id)">删除访谈</el-button>
      </main>
    </div>
    <!-- 审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
        </div>
      </template>
      <el-input v-model="md.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="汇总供应商访谈明细发现，说明交易真实性、关联关系核查及异常处理……" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useF2MasterDetail } from '../../composables/useF2MasterDetail'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const kind = computed(() => 'interview' as const)

const md = useF2MasterDetail({
  kind,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const cur = computed(() => md.currentInterview.value)
</script>

<style scoped>
.f2-interview-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f2-interview-detail :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f2-interview-detail :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.toolbar-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.layout { display: flex; gap: 12px; min-height: 400px; }
.list-panel { width: 260px; flex-shrink: 0; border: 1px solid #ebeef5; padding: 8px; border-radius: 4px; }
.add-btn { margin: 8px 0; width: 100%; }
.entity-list { list-style: none; margin: 0; padding: 0; max-height: 360px; overflow-y: auto; }
.entity-list li { padding: 6px 8px; cursor: pointer; border-radius: 4px; font-size: 12px; }
.entity-list li.active { background: #ecf5ff; color: #409eff; }
.detail-panel { flex: 1; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.field.full { grid-column: 1 / -1; }
.qa-block { margin-bottom: 12px; display: flex; flex-direction: column; gap: 6px; }
h4 { margin: 12px 0 8px; font-size: var(--wp-font-size, 13px); }
</style>
