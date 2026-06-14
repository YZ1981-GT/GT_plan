<template>
  <div class="review-panel">
    <div class="review-panel-header">
      <h3>{{ panelData?.title || '复核面板' }}</h3>
      <el-tag v-if="panelData?.status === 'submitted'" type="success" size="small">已提交</el-tag>
      <el-tag v-else type="info" size="small">草稿</el-tag>
    </div>

    <el-table v-if="panelData?.items" :data="panelData.items" class="gt-compact-table" style="margin-top: 12px">
      <el-table-column type="index" label="序号" width="60" />
      <el-table-column prop="content" label="检查要点" min-width="250" />
      <el-table-column label="自动检查" width="150">
        <template #default="{ row }">
          <span v-if="row.auto_result" class="auto-result">{{ row.auto_result }}</span>
          <span v-else class="auto-result-na">—</span>
        </template>
      </el-table-column>
      <el-table-column label="通过" width="70" align="center">
        <template #default="{ row }">
          <el-checkbox v-model="row.checked" :disabled="panelData.status === 'submitted'" />
        </template>
      </el-table-column>
      <el-table-column label="备注" width="200">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            placeholder="备注"
            :disabled="panelData.status === 'submitted'"
          />
        </template>
      </el-table-column>
      <el-table-column label="关联对话" width="100" align="center">
        <template #default="{ row }">
          <el-badge :value="row.conversations?.length || 0" :hidden="!row.conversations?.length">
            <el-button size="small" text @click="showConversations(row)">查看</el-button>
          </el-badge>
        </template>
      </el-table-column>
    </el-table>

    <!-- 复核意见 -->
    <div class="review-opinion" style="margin-top: 16px">
      <label>复核意见：</label>
      <el-input
        v-model="opinion"
        type="textarea"
        :rows="3"
        placeholder="填写复核总体意见"
        :disabled="panelData?.status === 'submitted'"
      />
    </div>

    <!-- 操作按钮 -->
    <div class="review-actions" style="margin-top: 12px; display: flex; gap: 8px">
      <el-button @click="save(false)" :disabled="panelData?.status === 'submitted'">保存草稿</el-button>
      <el-button type="primary" @click="save(true)" :disabled="panelData?.status === 'submitted'">提交复核</el-button>
      <el-button @click="exportArchive">导出归档</el-button>
    </div>

    <!-- 对话抽屉：当前检查项的关联对话 + 未关联可归类 -->
    <el-drawer v-model="showUnlinked" :title="`检查项关联对话`" size="460px">
      <div class="conv-section">
        <h4 class="conv-section-title">已关联（{{ selectedConversations.length }}）</h4>
        <div v-if="selectedConversations.length === 0" class="conv-empty">暂无关联对话</div>
        <div v-for="conv in selectedConversations" :key="conv.id" class="conv-card">
          <div class="conv-card-head">
            <span class="conv-card-title">{{ conv.title }}</span>
            <el-tag size="small" :type="conv.status === 'open' ? 'warning' : 'success'">
              {{ conv.status === 'open' ? '进行中' : '已解决' }}
            </el-tag>
          </div>
          <div v-if="conv.recent_messages?.length" class="conv-messages">
            <div v-for="(m, i) in conv.recent_messages" :key="i" class="conv-msg">
              <span class="conv-msg-content">{{ m.content }}</span>
            </div>
          </div>
          <el-button size="small" text type="danger" @click="unlinkConversation(conv.id)">取消关联</el-button>
        </div>
      </div>

      <el-divider />

      <div class="conv-section">
        <h4 class="conv-section-title">未关联（可归类到当前项）</h4>
        <div v-if="!panelData?.unlinked_conversations?.length" class="conv-empty">无未关联对话</div>
        <div v-for="conv in panelData?.unlinked_conversations" :key="conv.id" class="unlinked-item">
          <span class="unlinked-title">{{ conv.title }}</span>
          <el-button size="small" @click="linkConversation(conv.id)">关联</el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiProxy } from '@/utils/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  projectId: string
  year: number
  role: string
  auditType?: string
  businessCategory?: string
}>()

const panelData = ref<any>(null)
const opinion = ref('')
const showUnlinked = ref(false)
const selectedRefKey = ref('')

const selectedConversations = computed(() => {
  if (!panelData.value?.items) return []
  const item = panelData.value.items.find((i: any) => i.ref_key === selectedRefKey.value)
  return item?.conversations || []
})

async function fetchPanel() {
  const params = new URLSearchParams({
    role: props.role,
    audit_type: props.auditType || 'financial',
    business_category: props.businessCategory || 'C',
  })
  panelData.value = await apiProxy.get(
    `/api/projects/${props.projectId}/review-workflow/${props.year}/panel?${params}`
  )
  opinion.value = panelData.value?.opinion || ''
}

async function save(submit: boolean) {
  if (!panelData.value) return
  const items = panelData.value.items.map((i: any) => ({
    seq: i.seq,
    checked: i.checked,
    remark: i.remark || '',
  }))
  await apiProxy.post(`/api/projects/${props.projectId}/review-workflow/${props.year}/save`, {
    template_code: panelData.value.template_code,
    items,
    opinion: opinion.value,
    submit,
  })
  ElMessage.success(submit ? '复核已提交' : '草稿已保存')
  await fetchPanel()
}

function showConversations(row: any) {
  selectedRefKey.value = row.ref_key
  showUnlinked.value = true
}

async function linkConversation(conversationId: string) {
  await apiProxy.post(`/api/projects/${props.projectId}/review-workflow/${props.year}/link-conversation`, {
    conversation_id: conversationId,
    checklist_ref: selectedRefKey.value,
  })
  ElMessage.success('已关联')
  await fetchPanel()
}

async function unlinkConversation(conversationId: string) {
  await apiProxy.post(
    `/api/projects/${props.projectId}/review-workflow/${props.year}/unlink-conversation?conversation_id=${conversationId}`
  )
  ElMessage.success('已取消关联')
  await fetchPanel()
}

async function exportArchive() {
  window.open(
    `/api/projects/${props.projectId}/review-workflow/${props.year}/archive?template_code=${panelData.value?.template_code}`,
    '_blank'
  )
}

onMounted(fetchPanel)
</script>

<style scoped>
.review-panel-header { display: flex; align-items: center; gap: 12px; }
.review-panel-header h3 { margin: 0; }
.auto-result { color: var(--gt-purple, #4b2d77); font-size: 12px; }
.auto-result-na { color: var(--el-text-color-placeholder); }
.unlinked-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.unlinked-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-section-title { font-size: 13px; font-weight: 600; color: var(--gt-color-text-secondary, #666); margin: 0 0 10px; }
.conv-empty { color: var(--el-text-color-placeholder); font-size: 13px; padding: 8px 0; }
.conv-card { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; }
.conv-card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; }
.conv-card-title { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-messages { background: var(--gt-purple-light, #f4f0fa); border-radius: 6px; padding: 8px 10px; margin: 6px 0; }
.conv-msg { font-size: 12px; color: var(--gt-color-text-secondary, #555); padding: 2px 0; }
.conv-msg-content { line-height: 1.5; }
</style>
