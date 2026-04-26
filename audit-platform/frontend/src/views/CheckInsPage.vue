<template>
  <div class="gt-checkins gt-fade-in">
    <div class="gt-page-header">
      <h2 class="gt-page-title">打卡签到</h2>
      <el-button type="primary" @click="onCheckIn">打卡</el-button>
    </div>
    <el-table :data="checkIns" stripe>
      <el-table-column prop="check_time" label="打卡时间">
        <template #default="{ row }">{{ row.check_time?.slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column prop="location_name" label="位置" />
      <el-table-column prop="check_type" label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.check_type === 'morning' ? 'success' : 'warning'" size="small">
            {{ row.check_type === 'morning' ? '上班' : '下班' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!checkIns.length" description="暂无打卡记录" />
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { checkIn, listCheckIns } from '@/services/commonApi'
const route = useRoute()
const staffId = ref(route.params.staffId as string || '')
const checkIns = ref<any[]>([])
async function fetch() { if (staffId.value) checkIns.value = await listCheckIns(staffId.value) }
async function onCheckIn() {
  if (!staffId.value) return ElMessage.warning('缺少人员ID')
  await checkIn(staffId.value, { check_type: new Date().getHours() < 12 ? 'morning' : 'evening' })
  ElMessage.success('打卡成功')
  await fetch()
}
onMounted(fetch)
</script>
<style scoped>
.gt-checkins { padding: var(--gt-space-4); }
.gt-page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
</style>
