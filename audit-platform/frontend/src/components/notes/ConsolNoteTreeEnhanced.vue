<template>
  <!-- B.1.11: 章节树 180 章节 + 「来自 N 家子公司」标识 -->
  <!-- B.1.14: 多层合并 lineage 可视化 -->
  <!-- B.1.15: 合并附注顶部准则切换器 -->
  <div class="consol-note-tree-enhanced">
    <!-- B.1.15: 准则切换器（合并项目） -->
    <div v-if="isConsolProject" class="consol-toolbar">
      <NoteTemplateSwitch
        :project-id="projectId"
        :year="year"
        :template-type="templateType"
        @update:template-type="$emit('update:templateType', $event)"
        @switched="$emit('refresh')"
      />
      <el-tag size="small" type="info" style="margin-left: 8px">
        合并版 · {{ totalSections }} 章节
      </el-tag>
    </div>

    <!-- B.1.11: 章节树 -->
    <el-tree
      :data="treeData"
      :props="{ label: 'title', children: 'children' }"
      node-key="section_id"
      highlight-current
      @node-click="onNodeClick"
    >
      <template #default="{ data }">
        <span class="tree-node">
          <span>{{ data.rendered_number }} {{ data.title }}</span>
          <el-tag v-if="data.is_aggregated" size="small" type="success" effect="plain">
            来自 {{ data.children_count }} 家子公司
          </el-tag>
          <el-tag v-if="data.is_consol_only" size="small" type="warning" effect="plain">
            仅合并
          </el-tag>
          <el-tag v-if="data.is_stale" size="small" type="danger" effect="plain">
            需重新汇总
          </el-tag>
        </span>
      </template>
    </el-tree>

    <!-- B.1.13: 重新汇总按钮 -->
    <div v-if="isConsolProject" class="consol-actions">
      <el-button
        type="primary"
        size="small"
        :loading="reaggregating"
        @click="handleReaggregate"
      >
        🔄 重新汇总
      </el-button>
    </div>

    <!-- B.1.12: Cell 溯源对话框 -->
    <el-dialog v-model="showProvenance" title="数据溯源" width="500px">
      <el-table v-if="provenanceData" :data="provenanceData.contributions" border size="small">
        <el-table-column prop="subsidiary_name" label="子公司" />
        <el-table-column prop="template_type" label="准则" width="80" />
        <el-table-column prop="amount" label="贡献金额" width="120" align="right">
          <template #default="{ row }">
            {{ row.amount?.toLocaleString() }}
          </template>
        </el-table-column>
      </el-table>
      <div v-if="provenanceData?.elimination" style="margin-top: 12px">
        <el-tag type="danger">内部抵销: -{{ provenanceData.elimination.toLocaleString() }}</el-tag>
      </div>
      <div v-if="provenanceData" style="margin-top: 12px; font-weight: 500">
        合计: {{ provenanceData.total?.toLocaleString() }}
      </div>
    </el-dialog>

    <!-- B.1.14: Lineage 可视化 -->
    <el-dialog v-model="showLineage" title="多层合并 Lineage" width="600px">
      <div class="lineage-chain">
        <div v-for="(level, idx) in lineageChain" :key="idx" class="lineage-level">
          <el-tag :type="idx === 0 ? 'primary' : 'info'">
            {{ level.name }} (Level {{ level.consol_level }})
          </el-tag>
          <span v-if="idx < lineageChain.length - 1" class="lineage-arrow">→</span>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import NoteTemplateSwitch from './NoteTemplateSwitch.vue'
import { useNoteAggregation } from '@/composables/useNoteAggregation'
import { useNoteSectionNumbering } from '@/composables/useNoteSectionNumbering'

interface Props {
  projectId: string
  year: number
  isConsolProject: boolean
  templateType: string
  sections: any[]
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:templateType': [val: string]
  'refresh': []
  'select-section': [sectionId: string]
}>()

// C.3.1: Composables integration
const aggregation = useNoteAggregation(() => props.projectId, () => props.year)
const numbering = useNoteSectionNumbering(() => props.projectId, () => props.year)

const reaggregating = computed(() => aggregation.state.value.isAggregating)
const showProvenance = ref(false)
const showLineage = ref(false)
const provenanceData = ref<any>(null)
const lineageChain = ref<any[]>([])

const totalSections = computed(() => props.sections.length)

const treeData = computed(() => props.sections)

function onNodeClick(data: any) {
  emit('select-section', data.section_id)
}

async function handleReaggregate() {
  await aggregation.reaggregate()
  emit('refresh')
}
</script>

<style scoped>
.consol-note-tree-enhanced {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.consol-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 0;
}
.consol-actions {
  padding: 8px 0;
  border-top: 1px solid #ebeef5;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
}
.lineage-chain {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.lineage-arrow {
  color: #909399;
  font-size: 16px;
}
</style>
