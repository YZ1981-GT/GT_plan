<template>
  <div class="gt-collab gt-fade-in">
    <div class="gt-collab-header">
      <h2 class="gt-page-title">协作管理</h2>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="项目时间线" name="timeline">
        <el-timeline>
          <el-timeline-item v-for="item in timeline" :key="item.id"
            :timestamp="item.date" :type="item.type" placement="top">
            <el-card shadow="hover" style="padding: 8px">
              <p>{{ item.description }}</p>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-if="!timeline.length" description="暂无时间线数据" />
      </el-tab-pane>

      <el-tab-pane label="工时管理" name="workhours">
        <p style="color: #999; padding: 20px">项目级工时视图 — 复用工时管理页面，按当前项目筛选</p>
        <el-button type="primary" @click="$router.push('/work-hours')">前往工时管理</el-button>
      </el-tab-pane>

      <el-tab-pane label="PBC 清单" name="pbc">
        <el-table :data="pbcList" border stripe v-loading="loading">
          <el-table-column prop="item_name" label="资料名称" min-width="250" />
          <el-table-column prop="audit_cycle" label="审计循环" width="100" />
          <el-table-column prop="requested_from" label="提供方" width="120" />
          <el-table-column prop="due_date" label="截止日期" width="120" />
          <el-table-column prop="received_status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.received_status === 'received' ? 'success' : row.received_status === 'overdue' ? 'danger' : 'info'" size="small">
                {{ ({ not_received: '待提供', received: '已提供', overdue: '已逾期' } as Record<string, string>)[row.received_status] || row.received_status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!pbcList.length && !loading" description="暂无 PBC 清单" />
      </el-tab-pane>

      <el-tab-pane label="函证管理" name="confirmations">
        <el-table :data="confirmations" border stripe v-loading="loading">
          <el-table-column prop="confirmation_type" label="类型" width="100" />
          <el-table-column prop="counterparty" label="对象" min-width="200" />
          <el-table-column prop="amount" label="金额" width="140" align="right" />
          <el-table-column prop="status" label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="row.status === 'replied' ? 'success' : row.status === 'sent' ? 'warning' : 'info'" size="small">
                {{ ({ draft: '草稿', sent: '已发', replied: '已回', diff: '有差异' } as Record<string, string>)[row.status] || row.status }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!confirmations.length && !loading" description="暂无函证数据" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import { pbc as P_pbc, confirmations as P_conf } from '@/services/apiPaths'

const route = useRoute()
const activeTab = ref('timeline')
const loading = ref(false)
const timeline = ref<any[]>([])
const pbcList = ref<any[]>([])
const confirmations = ref<any[]>([])

onMounted(async () => {
  const projectId = route.params.projectId as string

  // 加载时间线（简化：从项目状态推断）
  timeline.value = [
    { id: '1', date: '项目创建', description: '项目已创建', type: 'primary' },
    { id: '2', date: '计划阶段', description: '审计计划编制中', type: 'info' },
  ]

  // 加载 PBC 清单
  try {
    const res = await api.get(P_pbc.items(projectId))
    pbcList.value = Array.isArray(res) ? res : (res?.data ?? [])
  } catch {
    pbcList.value = []
  }

  // 加载函证列表
  try {
    const res = await api.get(P_conf.list(projectId))
    confirmations.value = Array.isArray(res) ? res : (res?.data ?? [])
  } catch {
    confirmations.value = []
  }
})
</script>

<style scoped>
.gt-collab { padding: var(--gt-space-4); }
.gt-collab-header { margin-bottom: var(--gt-space-3); }
</style>
