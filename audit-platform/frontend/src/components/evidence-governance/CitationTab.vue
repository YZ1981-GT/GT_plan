<script setup lang="ts">
/**
 * CitationTab — RAG 引用快照列表 + 定位 + 批量校验（useCitationGovernance）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R7/R9)
 */
import { ref, toRef, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useCitationGovernance,
  type CitationLocateResult,
  type CitationValidateResult,
} from '@/composables/useCitationGovernance'

const props = defineProps<{ projectId: string; year: number }>()
const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const { loading, error, citations, listCitations, locateCitation, validateCitations } =
  useCitationGovernance(projectIdRef, yearRef)

const aiFilter = ref('')
const selectedIds = ref<string[]>([])
const locateResult = ref<CitationLocateResult | null>(null)
const validateResult = ref<CitationValidateResult | null>(null)

async function refresh() {
  await listCitations({ ai_content_log_id: aiFilter.value || undefined })
  if (error.value) ElMessage.error(error.value)
}

async function onLocate(id: string) {
  locateResult.value = await locateCitation(id)
  if (error.value) ElMessage.error(error.value)
}

async function onValidate() {
  if (!selectedIds.value.length) {
    ElMessage.warning('请勾选至少一条引用')
    return
  }
  validateResult.value = await validateCitations(selectedIds.value)
  if (error.value) ElMessage.error(error.value)
}

function handleSelection(rows: any[]) {
  selectedIds.value = rows.map((r) => r.id)
}

const statusType = (s: string) =>
  s === 'valid' || s === 'active' ? 'success' : s === 'stale' ? 'warning' : 'danger'

function truncate(h: string | null): string {
  if (!h) return '-'
  return h.length <= 16 ? h : h.slice(0, 8) + '…' + h.slice(-8)
}

const hasLocate = computed(() => !!locateResult.value)
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="RAG 引用快照包含 EvidenceRef、版本、页码、区域、Hash、索引版本；打开引用时重新鉴权，来源变化即标记 stale/invalid。"
      style="margin-bottom: 12px"
    />

    <el-form :inline="true" size="default">
      <el-form-item label="按 AI 内容过滤">
        <el-input v-model="aiFilter" placeholder="ai_content_log_id（可选）" style="width: 280px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="refresh">加载引用</el-button>
        <el-button :disabled="!selectedIds.length" @click="onValidate">批量校验勾选项</el-button>
      </el-form-item>
    </el-form>

    <el-alert v-if="error" type="error" :title="error" show-icon :closable="true" style="margin-bottom: 12px" />

    <el-table :data="citations" size="small" border stripe v-loading="loading" empty-text="暂无引用快照" @selection-change="handleSelection">
      <el-table-column type="selection" width="42" />
      <el-table-column label="页码" width="70">
        <template #default="{ row }">{{ row.page ?? '-' }}</template>
      </el-table-column>
      <el-table-column prop="region" label="区域" width="120" />
      <el-table-column label="版本" width="70">
        <template #default="{ row }">v{{ row.target_version ?? '-' }}</template>
      </el-table-column>
      <el-table-column label="Hash" min-width="140">
        <template #default="{ row }">
          <span class="mono">{{ truncate(row.target_hash) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="index_version" label="索引版本" width="120" />
      <el-table-column label="操作" width="100" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click="onLocate(row.id)">定位</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="hasLocate" shadow="never" header="定位结果" style="margin-top: 16px">
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="状态">
          <el-tag size="small" :type="statusType(locateResult!.status)">{{ locateResult!.status }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="可读">{{ locateResult!.readable ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="来源可用">{{ locateResult!.source_available ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="版本有效">{{ locateResult!.version_valid ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="Hash 有效">{{ locateResult!.hash_valid ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="页码">{{ locateResult!.page ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="区域">{{ locateResult!.region ?? '-' }}</el-descriptions-item>
        <el-descriptions-item label="定位器" :span="2">
          <span class="mono">{{ locateResult!.locator ?? '-' }}</span>
        </el-descriptions-item>
        <el-descriptions-item v-if="locateResult!.reason" label="原因" :span="3">{{ locateResult!.reason }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card v-if="validateResult" shadow="never" header="批量校验结果" style="margin-top: 16px">
      <el-tag :type="validateResult.all_valid ? 'success' : 'danger'" style="margin-bottom: 8px">
        {{ validateResult.all_valid ? '全部有效' : '存在失效引用' }}
      </el-tag>
      <div class="validate-grid">
        <div><b>有效</b> ({{ validateResult.valid.length }})</div>
        <div><b>Stale</b> ({{ validateResult.stale.length }})</div>
        <div><b>无效</b> ({{ validateResult.invalid.length }})</div>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.mono { font-family: 'Courier New', monospace; font-size: 12px; }
.validate-grid { display: flex; gap: 24px; }
</style>
