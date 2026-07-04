<template>
  <div class="f2-supplier-info">
    <h3 class="title">供应商信息核查 F2-70</h3>
    <div class="top-toolbar">
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
    <h4>核查结论</h4>
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
</script>

<style scoped>
.f2-supplier-info { padding: 12px; font-size: 13px; }
.title { margin: 0 0 8px; }
.layout { display: flex; gap: 12px; min-height: 360px; }
.list-panel { width: 260px; flex-shrink: 0; border: 1px solid #ebeef5; padding: 8px; border-radius: 4px; }
.add-btn { margin: 8px 0; width: 100%; }
.entity-list { list-style: none; margin: 0; padding: 0; max-height: 320px; overflow-y: auto; }
.entity-list li { padding: 6px 8px; cursor: pointer; border-radius: 4px; font-size: 12px; }
.entity-list li.active { background: #ecf5ff; color: #409eff; }
.detail-panel { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
h4 { margin: 16px 0 8px; font-size: 13px; }
</style>
