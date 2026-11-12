<template>
  <el-dialog
    v-model="visible"
    title="企业树冲突提示"
    width="560px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
    append-to-body
    data-testid="consol-tree-conflict-dialog"
  >
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      title="企业树按下列规则取值，计算与推送仍可继续。"
      style="margin-bottom: 12px"
    />

    <ul class="gt-consol-tree-conflict-list">
      <li v-for="(diagnostic, index) in diagnostics" :key="`${diagnostic.code}-${index}`">
        <div>{{ diagnostic.message }}</div>
        <div v-if="diagnostic.project_ids?.length" class="gt-consol-tree-conflict-projects">
          <span>涉及项目：</span>
          <el-button
            v-for="projectId in projectIdsOf(diagnostic)"
            :key="`${diagnostic.code}-${projectId}`"
            link
            type="primary"
            size="small"
            @click="openProject(projectId)"
          >
            去修改（{{ projectId }}）
          </el-button>
        </div>
      </li>
    </ul>

    <template #footer>
      <el-button type="primary" data-testid="consol-tree-conflict-ack" @click="acknowledge">
        我知道了
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import type { ConsolTreeDiagnostic } from '@/services/consolidationApi'

const props = defineProps<{
  modelValue: boolean
  diagnostics: ConsolTreeDiagnostic[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  acknowledged: []
}>()

const router = useRouter()
const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

function projectIdsOf(diagnostic: ConsolTreeDiagnostic): string[] {
  return [...new Set((diagnostic.project_ids || []).map(String).filter(Boolean))]
}

function openProject(projectId: string): void {
  visible.value = false
  void router.push(`/projects/new?projectId=${encodeURIComponent(projectId)}`)
}

function acknowledge(): void {
  emit('acknowledged')
  visible.value = false
}
</script>

<style scoped>
.gt-consol-tree-conflict-list {
  margin: 0;
  padding-left: 20px;
  line-height: 1.7;
}

.gt-consol-tree-conflict-list > li + li {
  margin-top: 12px;
}

.gt-consol-tree-conflict-projects {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  color: var(--el-text-color-secondary);
  font-size: var(--gt-font-size-xs);
}
</style>
