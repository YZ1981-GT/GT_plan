/**
 * ACNR 前端 SDK — 地址坐标名称注册中心
 *
 * 统一导出：
 * - useDisclosureSection: 附注披露工厂（替换 30+ 份 useXDisclosureSoe）
 * - buildNoteAddrId: note 子域 addr_id 生成工具
 *
 * Spec: .kiro/specs/acnr/
 */
export {
  useDisclosureSection,
  buildNoteAddrId,
  acnrResolve,
  type DisclosureRow,
  type DisclosureSectionOptions,
  type DisclosureSectionDeps,
  type DisclosureSectionReturn,
} from './useDisclosureSection'
