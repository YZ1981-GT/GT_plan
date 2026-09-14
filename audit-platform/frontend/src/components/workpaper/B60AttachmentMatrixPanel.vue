<template>
  <div v-if="visible" class="b60-matrix-panel">
    <div class="b60-matrix-panel__header">
      <span class="b60-matrix-panel__title">B60 适用性矩阵</span>
      <el-tag v-if="missingCount > 0" type="warning" size="small">缺附件 {{ missingCount }}</el-tag>
      <el-tag v-else-if="state" type="success" size="small">勾稽正常</el-tag>
      <el-tag v-if="state?.simplification" size="small" :type="state.simplification.is_pie ? 'danger' : 'info'">
        {{ state.simplification.is_pie ? 'PIE 完整路径' : '非 PIE 精简' }}
      </el-tag>
    </div>

    <div v-loading="loading" class="b60-matrix-panel__body">
      <template v-if="state">
        <div
          v-for="(def, key) in state.flag_defs"
          :key="key"
          class="b60-matrix-panel__row"
        >
          <el-switch
            :model-value="!!state.flags[key]"
            size="small"
            @change="(v: string | number | boolean) => setFlag(String(key), !!v)"
          />
          <div class="b60-matrix-panel__row-text">
            <div class="b60-matrix-panel__label">{{ def.label }}</div>
            <div class="b60-matrix-panel__codes">→ {{ def.wp_codes.join(', ') }}</div>
          </div>
        </div>

        <el-input
          v-model="materialityRef"
          size="small"
          placeholder="重要性索引（如 B19-1；计算见 B15）"
          class="b60-matrix-panel__mat"
        />

        <div class="b60-matrix-panel__actions">
          <el-checkbox v-model="autoGenerate" size="small">保存时自动生成缺附件</el-checkbox>
          <el-button type="primary" size="small" :loading="saving" @click="save">保存矩阵</el-button>
          <el-button size="small" :loading="saving" @click="bumpPlanVersion">第十五章更新（+版本）</el-button>
          <el-tag v-if="state.plan_version" size="small" type="info">计划 v{{ state.plan_version }}</el-tag>
        </div>

        <!-- 非 PIE 精简提示 -->
        <div v-if="state.simplification && !state.simplification.is_pie" class="b60-matrix-panel__simp">
          <div class="b60-matrix-panel__qc-title">非 PIE 可折叠章节</div>
          <div class="b60-matrix-panel__simp-note">{{ state.simplification.note }}</div>
          <ul class="b60-matrix-panel__simp-list">
            <li v-for="s in state.simplification.collapse_sections" :key="s.id">
              {{ s.title }} — {{ s.default }}
            </li>
          </ul>
        </div>

        <!-- SCOT+ 简表 -->
        <div class="b60-matrix-panel__scot">
          <div class="b60-matrix-panel__qc-title">SCOT+ / risk_id</div>
          <div v-for="(row, idx) in scotRows" :key="idx" class="b60-matrix-panel__scot-row">
            <el-input v-model="row.name" size="small" placeholder="事项" />
            <el-input v-model="row.cycle_code" size="small" placeholder="循环代码" />
            <el-input v-model="row.risk_id" size="small" placeholder="risk_id" />
            <el-input v-model="row.procedure_wp_index" size="small" placeholder="程序索引" />
            <el-select v-model="row.rely_on_controls" size="small" placeholder="依赖控制" clearable>
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待测" value="待测" />
            </el-select>
            <el-button size="small" text type="danger" @click="removeScotRow(idx)">删</el-button>
          </div>
          <div class="b60-matrix-panel__actions">
            <el-button size="small" @click="addScotRow">加行</el-button>
            <el-button size="small" type="primary" :loading="saving" @click="saveScotRows">保存 SCOT+</el-button>
          </div>
        </div>

        <!-- B60D 存档 -->
        <div v-if="state.flags.needs_regulatory_filing" class="b60-matrix-panel__b60d">
          <div class="b60-matrix-panel__qc-title">B60D 报送存档</div>
          <div class="b60-matrix-panel__b60d-row">
            <el-input-number v-model="b60dFiledVersion" size="small" :min="1" controls-position="right" />
            <span class="b60-matrix-panel__codes">对应计划版本</span>
            <el-input v-model="b60dDeliveryDate" size="small" placeholder="报送日期" style="width: 120px" />
            <el-input v-model="b60dRecipient" size="small" placeholder="收件方" style="width: 140px" />
            <el-button size="small" type="primary" :loading="saving" @click="saveB60dArchive">保存存档</el-button>
          </div>
        </div>

        <div v-if="qcFindings.length" class="b60-matrix-panel__qc">
          <div class="b60-matrix-panel__qc-title">质控提示</div>
          <div
            v-for="(f, i) in qcFindings"
            :key="i"
            class="b60-matrix-panel__qc-item"
            :class="`is-${f.severity}`"
          >
            {{ f.message }}
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useB60AttachmentMatrix } from '@/composables/useB60AttachmentMatrix'

const props = defineProps<{
  wpCode: string
  projectId?: string
}>()

const route = useRoute()
const visible = computed(() => props.wpCode === 'B60' || props.wpCode.startsWith('B60'))

const projectIdRef = computed(
  () => props.projectId || (route.params.projectId as string | undefined),
)

const {
  loading,
  saving,
  state,
  qcFindings,
  materialityRef,
  scotRows,
  b60dFiledVersion,
  b60dDeliveryDate,
  b60dRecipient,
  autoGenerate,
  missingCount,
  load,
  save,
  saveScotRows,
  saveB60dArchive,
  bumpPlanVersion,
  setFlag,
  addScotRow,
  removeScotRow,
} = useB60AttachmentMatrix(() => projectIdRef.value)

onMounted(() => {
  if (visible.value) load()
})

watch(
  () => [visible.value, projectIdRef.value, props.wpCode] as const,
  ([vis]) => {
    if (vis) load()
  },
)
</script>

<style scoped>
.b60-matrix-panel {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  background: var(--el-fill-color-blank);
}
.b60-matrix-panel__header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.b60-matrix-panel__title {
  font-weight: 600;
  font-size: 13px;
}
.b60-matrix-panel__row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 8px;
}
.b60-matrix-panel__label {
  font-size: 12px;
  line-height: 1.4;
}
.b60-matrix-panel__codes {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.b60-matrix-panel__mat {
  margin: 8px 0;
}
.b60-matrix-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
.b60-matrix-panel__qc-title {
  font-size: 12px;
  font-weight: 600;
  margin: 8px 0 4px;
}
.b60-matrix-panel__qc-item {
  font-size: 12px;
  line-height: 1.4;
  margin-bottom: 4px;
  padding: 4px 6px;
  border-radius: 4px;
  background: var(--el-color-warning-light-9);
}
.b60-matrix-panel__qc-item.is-info {
  background: var(--el-color-info-light-9);
}
.b60-matrix-panel__qc-item.is-blocking {
  background: var(--el-color-danger-light-9);
}
.b60-matrix-panel__simp,
.b60-matrix-panel__scot,
.b60-matrix-panel__b60d {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--el-border-color-lighter);
}
.b60-matrix-panel__simp-note {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.b60-matrix-panel__simp-list {
  margin: 0;
  padding-left: 16px;
  font-size: 11px;
  color: var(--el-text-color-regular);
}
.b60-matrix-panel__scot-row {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr 0.8fr 0.8fr 0.7fr auto;
  gap: 4px;
  margin-bottom: 4px;
  align-items: center;
}
.b60-matrix-panel__b60d-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
