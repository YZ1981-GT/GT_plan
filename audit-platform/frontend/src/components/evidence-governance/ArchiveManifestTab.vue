<script setup lang="ts">
/**
 * ArchiveManifestTab — 归档前置门禁 + 清单构建/列表/详情 + 离线验签（useArchiveGovernance）
 *
 * Spec: attachment-ocr-ai-evidence-governance-hardening (R11)
 */
import { ref, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useArchiveGovernance,
  type ArchivePreflightResult,
  type ArchiveManifestDetail,
  type ArchiveBuildResult,
} from '@/composables/useArchiveGovernance'

const props = defineProps<{ projectId: string; year: number }>()
const projectIdRef = toRef(props, 'projectId') as any
const yearRef = toRef(props, 'year') as any
const {
  loading, error, manifests,
  preflight, buildManifest, listManifests, getManifest, verifyPackage,
} = useArchiveGovernance(projectIdRef, yearRef)

const preflightResult = ref<ArchivePreflightResult | null>(null)
const buildResult = ref<ArchiveBuildResult | null>(null)
const detail = ref<ArchiveManifestDetail | null>(null)
const verifyInput = ref('')
const verifyResult = ref<Record<string, any> | null>(null)

async function refresh() {
  await listManifests()
  if (error.value) ElMessage.error(error.value)
}

async function runPreflight() {
  preflightResult.value = await preflight()
  if (error.value) ElMessage.error(error.value)
}

async function runBuild() {
  buildResult.value = await buildManifest()
  if (buildResult.value?.success) {
    ElMessage.success(`归档已封存 v${buildResult.value.version}`)
    // 自动把 sealed_package 填入验签输入，便于离线验证
    if (buildResult.value.sealed_package) {
      verifyInput.value = JSON.stringify(buildResult.value.sealed_package, null, 2)
    }
  } else if (buildResult.value?.blocked) {
    ElMessage.warning('归档被阻断，已生成差异报告')
  } else if (error.value) {
    ElMessage.error(error.value)
  }
  await refresh()
}

async function viewDetail(id: string) {
  detail.value = await getManifest(id)
  if (error.value) ElMessage.error(error.value)
}

async function runVerify() {
  if (!verifyInput.value.trim()) { ElMessage.warning('请粘贴封存包 JSON'); return }
  let pkg: Record<string, unknown>
  try {
    pkg = JSON.parse(verifyInput.value)
  } catch {
    ElMessage.error('封存包 JSON 解析失败')
    return
  }
  verifyResult.value = await verifyPackage(pkg)
  if (error.value) ElMessage.error(error.value)
}

const stateType = (s: string) => (s === 'sealed' ? 'success' : s === 'building' ? 'warning' : 'info')

onMounted(refresh)
</script>

<template>
  <div class="evgov-tab">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="归档清单覆盖附件版本/EvidenceRef/OCR/引用/AI/复核/stale 链等；仅验证失败阻断时生成差异报告，成功封存包可离线重算全部 hash。"
      style="margin-bottom: 12px"
    />

    <div class="toolbar">
      <el-button :loading="loading" @click="runPreflight">归档前置门禁</el-button>
      <el-button type="primary" :loading="loading" @click="runBuild">构建并封存归档</el-button>
      <el-button @click="refresh">刷新清单</el-button>
    </div>

    <el-alert v-if="preflightResult" :type="preflightResult.evidence_ready ? 'success' : 'error'" :closable="true" show-icon style="margin: 8px 0"
      :title="`前置门禁 phase=${preflightResult.phase} · watermark=${preflightResult.watermark ?? '-'} · ${preflightResult.evidence_ready ? '证据就绪' : '证据未就绪'}`" />

    <el-alert v-if="buildResult?.blocked" type="error" show-icon :closable="true" style="margin: 8px 0"
      title="归档被阻断：存在缺失 hash / 活动 stale / 未确认 AI/OCR / Blocking Review 等，详见差异报告" />

    <el-alert v-if="error" type="error" :title="error" show-icon :closable="true" style="margin: 8px 0" />

    <el-table :data="manifests" size="small" border stripe v-loading="loading" empty-text="暂无归档清单">
      <el-table-column label="版本" width="80">
        <template #default="{ row }">v{{ row.version_no }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag size="small" :type="stateType(row.state)">{{ row.state }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="Package Hash" min-width="160">
        <template #default="{ row }"><span class="mono">{{ row.package_hash ? row.package_hash.slice(0, 16) + '…' : '-' }}</span></template>
      </el-table-column>
      <el-table-column label="阻断报告" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.has_blocking_report" size="small" type="danger">有</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column prop="sealed_at" label="封存时间" min-width="160" />
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" text @click="viewDetail(row.id)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="detail" shadow="never" :header="`清单详情 v${detail.version_no}（${detail.state}）`" style="margin-top: 16px">
      <div class="detail-meta">entries: {{ detail.entries.length }} · edges: {{ detail.edges.length }} · package hash: <span class="mono">{{ detail.package_hash ?? '-' }}</span></div>
      <el-table :data="detail.entries.slice(0, 50)" size="small" border stripe style="margin-top: 8px" empty-text="无条目">
        <el-table-column prop="node_type" label="节点类型" width="150" />
        <el-table-column prop="node_id" label="节点 ID" min-width="180" />
        <el-table-column label="版本" width="70">
          <template #default="{ row }">v{{ row.node_version ?? '-' }}</template>
        </el-table-column>
        <el-table-column prop="node_state" label="状态" width="100" />
      </el-table>
      <el-alert v-if="detail.blocking_difference_report" type="error" :closable="false" show-icon style="margin-top: 8px" title="该清单含阻断差异报告（未成功封存）" />
    </el-card>

    <el-card shadow="never" header="离线验签封存包" style="margin-top: 16px">
      <el-input v-model="verifyInput" type="textarea" :rows="5" placeholder="粘贴封存包 JSON（构建成功后自动填入）" />
      <div style="margin-top: 8px">
        <el-button type="primary" :loading="loading" @click="runVerify">离线校验</el-button>
      </div>
      <el-alert v-if="verifyResult" :type="verifyResult.verified || verifyResult.valid ? 'success' : 'error'" :closable="true" show-icon style="margin-top: 8px"
        :title="verifyResult.verified || verifyResult.valid ? '离线 hash 校验通过' : '离线校验失败（存在差异）'" />
      <pre v-if="verifyResult" class="verify-json">{{ JSON.stringify(verifyResult, null, 2) }}</pre>
    </el-card>
  </div>
</template>

<style scoped>
.evgov-tab { padding: 4px 0; }
.toolbar { display: flex; gap: 8px; margin-bottom: 8px; }
.mono { font-family: 'Courier New', monospace; font-size: 12px; }
.detail-meta { font-size: 12px; color: #606266; }
.verify-json { max-height: 220px; overflow: auto; background: #f5f7fa; padding: 8px; font-size: 11px; border-radius: 4px; }
</style>
