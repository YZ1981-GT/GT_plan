import { ref } from 'vue'
import { listStaff } from '@/services/staffApi'

export function useStaffPartnerOptions() {
  const partnerNames = ref<string[]>([])
  const partnersLoading = ref(false)
  const partnersFailed = ref(false)
  let pending: Promise<void> | null = null

  function loadPartnerOptions(): Promise<void> {
    if (pending) return pending
    partnersLoading.value = true
    partnersFailed.value = false
    partnerNames.value = []
    pending = (async () => {
      try {
        const names = new Set<string>()
        let offset = 0
        let total = 0
        do {
          const page = await listStaff({ title: '合伙人', offset, limit: 200 })
          total = page.total
          if (page.items.length === 0 && offset < total) {
            throw new Error('合伙人名单加载不完整')
          }
          for (const staff of page.items) {
            if (staff.title === '合伙人' && staff.name.trim()) names.add(staff.name)
          }
          offset += page.items.length
        } while (offset < total)
        partnerNames.value = [...names]
      } catch {
        // 请求错误由全局拦截器提示；不把部分名单当作完整结果。
        partnersFailed.value = true
      } finally {
        partnersLoading.value = false
        pending = null
      }
    })()
    return pending
  }

  return { partnerNames, partnersLoading, partnersFailed, loadPartnerOptions }
}
