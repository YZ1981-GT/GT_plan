/**
 * 坏账准备明细表增强 API 封装
 *
 * 端点：/api/workpapers/{wpId}/bad-debt-rows/...
 * - 导出模板 / 导出数据（blob 下载）
 * - 导入解析 / 导入写入
 * - 账龄段配置 CRUD + has-amounts 检查
 *
 * Requirements: 1.1, 2.1, 3.1, 3.8, 3.9, 4.7
 */
import { api } from '@/services/apiProxy'

const BASE = (wpId: string) => `/api/workpapers/${wpId}/bad-debt-rows`

export const badDebtApi = {
  /** 导出空模板 xlsx（blob） */
  exportTemplate: (wpId: string) =>
    api.get(`${BASE(wpId)}/export-template`, { responseType: 'blob' }),

  /** 导出含数据的完整 xlsx（blob） */
  exportData: (wpId: string) =>
    api.get(`${BASE(wpId)}/export-data`, { responseType: 'blob' }),

  /** 上传 xlsx 解析匹配（multipart form） */
  importParse: (wpId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return api.post(`${BASE(wpId)}/import-parse`, fd)
  },

  /** 确认写入匹配到的行 */
  importCommit: (wpId: string, rows: any[]) =>
    api.post(`${BASE(wpId)}/import-commit`, { rows }),

  /** 获取账龄段配置（null = 未配置） */
  getAgingSegments: (wpId: string) =>
    api.get(`${BASE(wpId)}/aging-segments`),

  /** 保存账龄段配置（preset + segments） */
  saveAgingSegments: (wpId: string, config: { preset: string; segments: string[] }) =>
    api.put(`${BASE(wpId)}/aging-segments`, config),

  /** 检查 CREDIT_RISK_AGING 子行是否有已填金额 */
  checkHasAmounts: (wpId: string) =>
    api.get(`${BASE(wpId)}/aging-segments/has-amounts`),
}
