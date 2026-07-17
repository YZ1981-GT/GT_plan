<script setup lang="ts">
/**
 * EvidenceRefsTab — 证据关系查询 + 影响路径（复用 useEvidenceRefs + GtEvidenceDrawer）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R2/R3/R4)
 */
import { ref, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import { useEvidenceRefs, type EvidenceRefItem, type ImpactNode } from '@/composables/useEvidenceRefs'
import GtEvidenceDrawer from '@/components/common/GtEvidenceDrawer.vue'

const props = defineProps<{ projectId: string; year: number }>()

const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const { loading, error, refs, hasMore, queryRefs, queryImpact } = useEvidenceRefs(projectIdRef, yearRef)

const direction = ref<'source' | 'evidence'>('source')
const sourceType = ref('workpaper_cell')
const sourceId = ref('')
const evidenceType = ref('attachment_version')
const evidenceId = ref('')

const impactNodes = ref<ImpactNode[]>([])
const impactLoading = ref(false)
const drawerVisible = ref(false)

async function runQuery() {
  await queryRefs({
    direction: direction.value,
    source_type: direction.value === 'source' ? sourceType.value : undefined,
    source_id: direction.value === 'source' ? sourceId.value : undefined,
    evidence_type: direction.value === 'evidence' ? evidenceType.value : undefined,
    evidence_id: direction.value === 'evidence' ? evidenceId.value : undefined,
    status: 'active',
    limit: 100,
  })
}

async function runImpact() {
  if (!sourceId.value) {
    ElMessage.warning('请先填写源对象 ID')
    return
  }
  impactLoading.value = true
  const res = await queryImpact({
    source_type: sourceType.value,
    source_id: sourceId.value,
    max_depth: 10,
    limit: 100,
  })
  impactNodes.value = res?.nodes || []
  impactLoading.value = false
}

function truncate(h: string | null): string {
  if (!h) return '-'
  return h.length <= 16 ? h : h.slice(0, 8) + '…' + h.slice(-8)
}
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="按源对象或证据对象双向查询持久 EvidenceRef，并展示直接/传递影响路径（仅当前项目年度、去重）"
      style="margin-bottom: 12px"
    />

    <el-form :inline="true" size="default" class="query-form">
      <el-form-item label="查询方向">
        <el-select v-model="direction" style="width: 140px">
          <el-option label="从源端查" value="source" />
          <el-option label="从证据端查" value="evidence" />
        </el-select>
      </el-form-item>
      <template v-if="direction === 'source'">
        <el-form-item label="源类型">
          <el-select v-model="sourceType" style="width: 170px">
            <el-option label="底稿单元格" value="workpaper_cell" />
            <el-option label="抽样项" value="sampling_item" />
            <el-option label="凭证" value="voucher" />
            <el-option label="函证" value="confirmation" />
            <el-option label="复核意见" value="review_opinion" />
            <el-option label="附注表格" value="note_table" />
            <el-option label="报告段落" value="report_section" />
            <el-option label="交付件" value="deliverable" />
          </el-select>
        </el-form-item>
        <el-form-item label="源 ID">
          <el-input v-model="sourceId" placeholder="如 D2-1!B5" style="width: 200px" />
        </el-form-item>
      </template>
      <template v-else>
        <el-form-item label="证据类型">
          <el-select v-model="evidenceType" style="width: 170px">
            <el-option label="附件版本" value="attachment_version" />
            <el-option label="OCR 结果" value="ocr_result" />
            <el-option label="引用快照" value="citation_snapshot" />
          </el-select>
        </el-form-item>
        <el-form-item label="证据 ID">
          <el-input v-model="evidenceId" placeholder="证据对象 ID" style="width: 200px" />
        </el-form-item>
      </template>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="runQuery">查询引用</el-button>
        <el-button v-if="direction === 'source'" :loading="impactLoading" @click="runImpact">查看影响路径</el-button>
        <el-button @click="drawerVisible = true">打开关系抽屉</el-button>
      </el-form-item>
    </el-form>

    <el-alert v-if="error" type="error" :title="error" show-icon :closable="true" style="margin-bottom: 12px" />

    <el-table :data="refs" size="small" border stripe v-loading="loading" empty-text="暂无引用">
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
            {{ row.status === 'active' ? '有效' : '已停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="evidence_type" label="证据类型" width="140" />
      <el-table-column label="来源" min-width="180">
        <template #default="{ row }">{{ row.source_type }}:{{ row.source_id }}</template>
      </el-table-column>
      <el-table-column label="版本" width="70">
        <template #default="{ row }">v{{ row.target_version ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="Hash" min-width="150">
        <template #default="{ row }">
          <el-tooltip :content="row.target_hash || '无'" placement="top">
            <span class="mono">{{ truncate(row.target_hash) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="label" label="标签" width="120" />
    </el-table>
    <div v-if="hasMore" class="more-hint">更多引用请缩小查询范围</div>

    <template v-if="impactNodes.length">
      <el-divider content-position="left">影响路径（{{ impactNodes.length }} 个下游）</el-divider>
      <el-timeline>
        <el-timeline-item
          v-for="node in impactNodes"
          :key="`${node.target_type}:${node.target_id}`"
          :color="node.distance === 1 ? '#409eff' : '#e6a23c'"
          :hollow="node.distance > 1"
        >
          <span class="mono">{{ node.target_type }}:{{ node.target_id }}</span>
          <el-tag size="small" :type="node.distance === 1 ? '' : 'warning'" style="margin-left: 8px">
            {{ node.distance === 1 ? '直接' : `传递(${node.distance}层)` }}
          </el-tag>
        </el-timeline-item>
      </el-timeline>
    </template>

    <GtEvidenceDrawer
      v-model:visible="drawerVisible"
      :project-id="projectId"
      :year="year"
      :direction="direction"
      :source-type="sourceType"
      :source-id="sourceId"
      :evidence-type="evidenceType"
      :evidence-id="evidenceId"
      title="证据关系"
    />
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.query-form { margin-bottom: 8px; }
.mono { font-family: 'Courier New', monospace; font-size: 12px; }
.more-hint { text-align: center; color: #909399; font-size: 12px; padding: 8px 0; }
</style>
