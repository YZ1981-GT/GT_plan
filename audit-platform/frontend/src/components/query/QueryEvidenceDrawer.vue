<template>
  <!-- 历史与证据抽屉（AQF §8.1 QueryEvidenceDrawer）-->
  <el-drawer
    v-model="visible"
    title="历史与证据"
    direction="rtl"
    size="520px"
    @open="onOpen"
  >
    <el-tabs v-model="activeTab">
      <!-- ── 查询历史 ── -->
      <el-tab-pane label="查询历史" name="history">
        <div class="qed__toolbar">
          <el-button size="small" @click="clearHistory">清空历史</el-button>
        </div>
        <el-empty v-if="!runs.length" description="暂无历史记录" />
        <div v-else class="qed__list">
          <div v-for="run in runs" :key="String(run.id)" class="qed__item">
            <div class="qed__item-main">
              <span class="qed__source">{{ (run as Record<string, unknown>).source_key }}</span>
              <span class="qed__count">共 {{ (run as Record<string, unknown>).execution_count }} 次</span>
            </div>
            <div class="qed__item-meta">
              {{ fmtBeijingTime(String((run as Record<string, unknown>).last_executed_at ?? '')) }}
              · {{ (run as Record<string, unknown>).artifact_count ?? 0 }} 个证据
            </div>
            <div class="qed__item-actions">
              <el-button size="small" @click="onReplay(run)">重新查询</el-button>
              <el-button size="small" @click="onHideRun(String((run as Record<string, unknown>).id))">移除</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ── 导出证据 ── -->
      <el-tab-pane label="导出证据" name="artifacts">
        <el-empty v-if="!artifacts.length" description="暂无证据记录" />
        <div v-else class="qed__list">
          <div v-for="art in artifacts" :key="String(art.id)" class="qed__item">
            <div class="qed__item-main">
              <span class="qed__source">{{ (art as Record<string, unknown>).source_key }}</span>
              <el-tag
                size="small"
                :type="(art as Record<string, unknown>).status === 'ready' ? 'success' : 'info'"
              >
                {{ (art as Record<string, unknown>).status === 'ready' ? '可用' : '已清理' }}
              </el-tag>
            </div>
            <div class="qed__item-meta">
              {{ fmtBeijingTime(String((art as Record<string, unknown>).created_at ?? '')) }}
              · {{ fmtRows((art as Record<string, unknown>).row_count as number) }} 行
            </div>
            <div v-if="(art as Record<string, unknown>).status === 'ready'" class="qed__item-actions">
              <el-button size="small" @click="onDownload(String((art as Record<string, unknown>).id))">下载</el-button>
              <el-button size="small" @click="onViewManifest(String((art as Record<string, unknown>).id))">查看清单</el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 清单 JSON 弹窗 -->
    <el-dialog v-model="manifestVisible" title="证据清单" width="640px" append-to-body>
      <pre class="qed__manifest-json">{{ manifestJson }}</pre>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fmtBeijingTime, fmtRows } from './queryRunFormat'

interface Props {
  modelValue: boolean
  entry: 'business' | 'builder'
  projectId?: string
  evidence: Pick<
    ReturnType<typeof import('./useQueryRunEvidence').useQueryRunEvidence>,
    'runs' | 'artifacts' | 'loadRuns' | 'loadArtifacts' | 'hideRun' | 'clearRuns' | 'downloadArtifact' | 'fetchManifest' | 'fetchRunDetail'
  >
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  replay: [run: unknown]
}>()

const visible = ref(props.modelValue)
watch(() => props.modelValue, v => { visible.value = v })
watch(visible, v => emit('update:modelValue', v))

const activeTab = ref('history')
const manifestVisible = ref(false)
const manifestJson = ref('')
const runs = props.evidence.runs
const artifacts = props.evidence.artifacts

async function onOpen() {
  await Promise.all([
    props.evidence.loadRuns(props.projectId),
    props.evidence.loadArtifacts(props.projectId),
  ])
}

async function onReplay(run: unknown) {
  const runId = String((run as Record<string, unknown>)?.id ?? '')
  if (!runId) return
  try {
    const detail = await props.evidence.fetchRunDetail(runId)
    emit('replay', detail)
    visible.value = false
  } catch {
    ElMessage.warning('加载查询详情失败，请稍后重试')
  }
}

async function onHideRun(id: string) {
  await props.evidence.hideRun(id)
}

async function clearHistory() {
  await props.evidence.clearRuns()
}

async function onDownload(id: string) {
  await props.evidence.downloadArtifact(id)
}

async function onViewManifest(id: string) {
  try {
    const manifest = await props.evidence.fetchManifest(id)
    manifestJson.value = JSON.stringify(manifest, null, 2)
    manifestVisible.value = true
  } catch {
    ElMessage.warning('加载清单失败，请稍后重试')
  }
}
</script>

<style scoped>
.qed__toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.qed__list { display: flex; flex-direction: column; gap: 10px; }
.qed__item { border: 1px solid #e9ecef; border-radius: 6px; padding: 10px 12px; }
.qed__item-main { display: flex; align-items: center; gap: 8px; font-weight: 500; }
.qed__item-meta { font-size: 12px; color: #868e96; margin: 2px 0; }
.qed__item-actions { display: flex; gap: 6px; margin-top: 6px; }
.qed__source { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.qed__count { font-size: 11px; color: #868e96; white-space: nowrap; }
.qed__manifest-json { white-space: pre-wrap; word-break: break-all; font-size: 12px; max-height: 60vh; overflow: auto; background: #f8f9fa; padding: 10px; border-radius: 4px; }
</style>
