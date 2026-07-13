<template>
  <div class="f2-supplier-info">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表核查主要供应商的工商登记信息（信用代码、法定代表人、注册资本、成立日期、经营范围等），验证供应商真实存在且具备履约能力（CAS 1141 / CAS 1231）。</p>
        <p>2. 左侧选择供应商后在右侧录入基础工商信息与审计核查结论；建议与企查查/国家企业信用信息公示系统交叉比对。</p>
        <p>3. 关注成立时间短、注册资本与交易规模不匹配、经营范围与采购内容不符的供应商，警惕空壳公司与虚构采购。</p>
        <p>4. 可通过工具栏"AI 生成"辅助撰写核查结论，"💬"发起复核对话，"导入导出"批量维护供应商信息。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实主要供应商工商登记信息真实有效，评价其履约能力与商业实质，识别空壳公司及未披露关联方风险。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-70"
          :disabled="isReadonly"
          ai-section="supplier-analysis"
          :existing-content="md.auditNote.value"
          review-section="F2-70-check"
          @ai-filled="(t: string) => { md.auditNote.value = t }"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F2-70" /></span>
        <el-tag size="small" type="info">共 {{ md.entityList.value.length }} 家</el-tag>
      </div>
    </div>

    <div class="layout">
      <aside class="list-panel">
        <el-input v-model="md.searchQuery.value" size="small" placeholder="搜索供应商..." clearable />
        <el-button size="small" type="primary" class="add-btn" :disabled="isReadonly" @click="md.addEntity()">+ 新增</el-button>
        <ul class="entity-list">
          <li v-for="s in md.entityList.value" :key="s.id"
            :class="{ active: md.currentId.value === s.id }"
            @click="md.selectEntity(s.id)">
            {{ (s as { supplierName?: string }).supplierName || '未命名' }}
          </li>
        </ul>
      </aside>
      <main v-if="cur" class="detail-panel">
        <el-card shadow="never" header="基础工商信息">
          <div class="field-grid">
            <label v-for="f in basicFields" :key="f.key" class="field">
              {{ f.label }}
              <el-input v-if="!f.number" :model-value="String((cur as any)[f.key] ?? '')" size="small"
                :type="f.textarea ? 'textarea' : 'text'" :rows="f.textarea ? 2 : undefined" :disabled="isReadonly"
                @change="(v: string) => patch(f.key, v)" />
              <el-input-number v-else :model-value="Number((cur as any)[f.key] ?? 0)" size="small" :controls="false"
                :disabled="isReadonly" @change="(v: number) => patch(f.key, v ?? 0)" />
            </label>
          </div>
        </el-card>
        <el-card shadow="never" header="审计核查">
          <div class="field-grid">
            <label v-for="f in auditFields" :key="f.key" class="field">
              {{ f.label }}
              <el-input v-if="!f.number" :model-value="String((cur as any)[f.key] ?? '')" size="small"
                :disabled="isReadonly" @change="(v: string) => patch(f.key, v)" />
              <el-input-number v-else :model-value="Number((cur as any)[f.key] ?? 0)" size="small" :controls="false"
                :disabled="isReadonly" @change="(v: number) => patch(f.key, v ?? 0)" />
            </label>
          </div>
        </el-card>
        <el-button v-if="!isReadonly" type="danger" link size="small" @click="md.removeEntity(cur.id)">删除</el-button>
      </main>
    </div>

    <!-- 审计意见区（卡片式） -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">核查结论</span>
        </div>
      </template>
      <el-input v-model="md.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="汇总供应商工商信息核查结果与审计结论…" />
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="audit-card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNoteText"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：概述所执行的供应商工商信息核查程序、测试范围与结果，以及发现的异常事项及其处理。"
        @change="saveAuditNote"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, toRef } from 'vue'
import { useF2MasterDetail } from '../../composables/useF2MasterDetail'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const kind = computed(() => 'supplier-info' as const)

const md = useF2MasterDetail({
  kind,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const cur = computed(() => md.currentSupplier.value)

const basicFields = [
  { key: 'supplierName', label: '供应商名称' },
  { key: 'creditCode', label: '信用代码' },
  { key: 'legalRepresentative', label: '法定代表人' },
  { key: 'registeredCapital', label: '注册资本' },
  { key: 'establishDate', label: '成立日期' },
  { key: 'businessScope', label: '经营范围', textarea: true },
  { key: 'operatingAddress', label: '经营地址' },
  { key: 'employeeCount', label: '员工人数', number: true },
]

const auditFields = [
  { key: 'cooperationYears', label: '合作年限', number: true },
  { key: 'transactionAmount', label: '交易金额', number: true },
  { key: 'checkMethod', label: '核查方式' },
  { key: 'checkConclusion', label: '核查结论' },
]

function patch(key: string, val: string | number): void {
  if (!cur.value) return
  md.updateSupplier(cur.value.id, { [key]: val })
}

// ─── 审计说明（逐 sheet 打磨补齐，持久化走 f2-spe:save-items）──────────────────
const NOTE_KEY = 'F2-70-audit-note'
const auditNoteText = ref('')
function persistSpeAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNoteText.value = val
  persistSpeAudit(NOTE_KEY, val)
}
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
})
</script>

<style scoped>
.f2-supplier-info { padding: 12px 16px; font-size: var(--wp-font-size, 13px); }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }

/* 工具栏 */
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 主从布局 */
.layout { display: flex; gap: 12px; min-height: 360px; }
.list-panel { width: 260px; flex-shrink: 0; border: 1px solid #ebeef5; padding: 8px; border-radius: 4px; }
.add-btn { margin: 8px 0; width: 100%; }
.entity-list { list-style: none; margin: 0; padding: 0; max-height: 320px; overflow-y: auto; }
.entity-list li { padding: 6px 8px; cursor: pointer; border-radius: 4px; font-size: 12px; }
.entity-list li.active { background: #ecf5ff; color: #409eff; }
.detail-panel { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }

/* 审计意见卡片 */
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.audit-note-card { margin-top: 16px; border-radius: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.audit-card-header { font-weight: 600; font-size: 14px; color: #303133; }
</style>
