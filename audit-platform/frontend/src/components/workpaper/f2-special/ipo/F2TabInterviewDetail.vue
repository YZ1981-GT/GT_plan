<template>
  <div class="f2-interview-detail">
    <h3 class="title">供应商访谈记录 F2-72</h3>
    <div class="top-toolbar">
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
    <h4>审计说明</h4>
    <el-input v-model="md.auditNote.value" type="textarea" :rows="3" :disabled="isReadonly" />
  </div>
</template>

<script setup lang="ts">
import { computed, toRef } from 'vue'
import { useF2MasterDetail } from '../../composables/useF2MasterDetail'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'

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
.f2-interview-detail { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
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
h4 { margin: 12px 0 8px; font-size: 13px; }
</style>
