<template>
  <div class="gt-mobile-review">
    <div class="gt-mr-header">
      <h3>复核意见</h3>
      <el-tag size="small">{{ opinions.length }} 条</el-tag>
    </div>

    <div v-if="loading" style="text-align: center; padding: 40px">
      <el-icon class="is-loading" :size="24"><Loading /></el-icon>
    </div>

    <div v-else-if="opinions.length === 0" class="gt-mr-empty">
      暂无复核意见
    </div>

    <!-- 意见列表（只读，点击展开详情） -->
    <div class="gt-mr-list">
      <div
        v-for="op in opinions"
        :key="op.id"
        class="gt-mr-card"
        @click="toggleExpand(op.id)"
      >
        <div class="gt-mr-card-header">
          <el-tag :type="(statusType(op.status)) || undefined" size="small">{{ statusLabel(op.status) }}</el-tag>
          <span class="gt-mr-card-title">{{ op.title || op.message?.substring(0, 30) || '复核意见' }}</span>
          <el-icon :size="14" style="margin-left: auto">
            <ArrowDown v-if="expandedId !== op.id" />
            <ArrowUp v-else />
          </el-icon>
        </div>
        <transition name="gt-slide">
          <div v-if="expandedId === op.id" class="gt-mr-card-body">
            <p>{{ op.message || '无详细内容' }}</p>
            <div class="gt-mr-meta">
              <span>{{ op.reviewer || '—' }}</span>
              <span>{{ formatDate(op.created_at) }}</span>
            </div>
            <div v-if="op.replies?.length" class="gt-mr-replies">
              <div v-for="(r, i) in op.replies" :key="i" class="gt-mr-reply">
                <span class="gt-mr-reply-user">{{ r.user || '—' }}:</span>
                {{ r.content }}
              </div>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, ArrowUp, Loading } from '@element-plus/icons-vue'
import { listReviewConversations } from '@/services/commonApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)

const loading = ref(false)
const opinions = ref<any[]>([])
const expandedId = ref<string | null>(null)

function toggleExpand(id: string) {
  expandedId.value = expandedId.value === id ? null : id
}

function statusType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  return ({ open: 'danger', replied: 'warning', resolved: 'success' } as Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'>)[s] || 'info'
}

function statusLabel(s: string) {
  return { open: '待处理', replied: '已回复', resolved: '已解决' }[s] || s
}

function formatDate(d: string) {
  if (!d) return ''
  return new Date(d).toLocaleDateString('zh-CN')
}

async function loadOpinions() {
  if (!projectId.value) return
  loading.value = true
  try {
    opinions.value = await listReviewConversations(projectId.value)
  } catch { opinions.value = [] }
  finally { loading.value = false }
}

onMounted(loadOpinions)
</script>

<style scoped>
.gt-mobile-review { padding: 12px; }
.gt-mr-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-mr-header h3 { margin: 0; font-size: 18px; }
.gt-mr-empty { text-align: center; padding: 40px; color: #ccc; }
.gt-mr-list { display: flex; flex-direction: column; gap: 8px; }
.gt-mr-card {
  border: 1px solid #eee; border-radius: 8px; background: #fff;
  overflow: hidden; cursor: pointer; transition: box-shadow 0.2s;
}
.gt-mr-card:active { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.gt-mr-card-header {
  display: flex; align-items: center; gap: 8px; padding: 12px;
}
.gt-mr-card-title { font-size: 14px; font-weight: 500; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-mr-card-body { padding: 0 12px 12px; font-size: 14px; color: #555; line-height: 1.6; }
.gt-mr-meta { display: flex; justify-content: space-between; font-size: 12px; color: #999; margin-top: 8px; }
.gt-mr-replies { margin-top: 8px; padding-top: 8px; border-top: 1px dashed #eee; }
.gt-mr-reply { font-size: 13px; margin-bottom: 4px; }
.gt-mr-reply-user { font-weight: 600; color: var(--gt-color-primary, #4b2d77); }
.gt-slide-enter-active, .gt-slide-leave-active { transition: all 0.2s ease; }
.gt-slide-enter-from, .gt-slide-leave-to { opacity: 0; max-height: 0; }
</style>
