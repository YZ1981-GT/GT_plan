/**
 * useOnlyOfficeHealthProbe — OO 健康检查共享 composable
 *
 * BP-6 探活收敛：L5~L8 四个 DualMode 各自直调 onlyoffice/health 的裸端点，
 * 收敛到此统一入口。调用方通过此 composable 获取 isOOHealthy / ooChecking 状态，
 * 不再各自维护 health 检查逻辑。
 *
 * 端点：GET /api/workpapers/onlyoffice/health
 * 双层.data兼容：ResponseWrapperMiddleware 信封 {code,message,data:{healthy:true}}
 *
 * 🔴 不得直调 onlyoffice-config（L 域只探活不取配置，LB-P10）。
 */
import { ref } from 'vue'
import http from '@/utils/http'

/** OO 健康检查端点（单一真源，禁止在其他文件重复声明） */
const OO_HEALTH_ENDPOINT = '/api/workpapers/onlyoffice/health'

/**
 * 共享 OO 健康探测 composable
 *
 * @returns isOOHealthy - OO 是否可用
 * @returns ooChecking - 是否正在检查中
 * @returns checkOOHealth - 执行一次健康检查
 */
export function useOnlyOfficeHealthProbe() {
  const isOOHealthy = ref<boolean>(false)
  const ooChecking = ref(false)

  /**
   * 检查 OnlyOffice 服务是否可用
   * 双层.data兼容: ResponseWrapperMiddleware 信封 {code,message,data:{healthy:true}}
   */
  async function checkOOHealth(): Promise<boolean> {
    ooChecking.value = true
    try {
      const response = await http.get(OO_HEALTH_ENDPOINT)
      // 双层.data兼容
      const healthy = (response as any).data?.data?.healthy
        ?? (response as any).data?.healthy
        ?? false
      isOOHealthy.value = Boolean(healthy)
      return isOOHealthy.value
    } catch {
      isOOHealthy.value = false
      return false
    } finally {
      ooChecking.value = false
    }
  }

  return {
    isOOHealthy,
    ooChecking,
    checkOOHealth,
  }
}

export default useOnlyOfficeHealthProbe
