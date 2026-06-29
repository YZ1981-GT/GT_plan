/** useA177IndependenceDeclaration — A17-7 独立性声明书 多章节+双模式+AI+批量签署 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

export type Variant = 'team' | 'committee'
export type ThreatType = 'economic_interest' | 'loan_guarantee' | 'business_relation'
export interface MetaInfo { client_name: string; audit_year: string; index_no: string }
export interface PeriodData { business_start: string | null; business_end: string | null; report_start: string | null; report_end: string | null }
export interface CommitmentItem { id: string; label: string; answer: 'Y' | 'N' | null; explanation: string | null }
export interface SignRow { index: number; name: string; signed: boolean; date: string | null }
export interface PartnerSection { confirmed: boolean | null; explanation: string | null; partner_sign: { name: string | null; date: string | null }; manager_sign: { name: string | null; date: string | null } }
export interface EconomicThreatRow { member: string; type: string; amount: string; measure: string }
export interface LoanThreatRow { member: string; type: string; amount: string; measure: string }
export interface BusinessThreatRow { member: string; description: string; measure: string }
export interface ThreatRecords { economic_interest: EconomicThreatRow[]; loan_guarantee: LoanThreatRow[]; business_relation: BusinessThreatRow[] }
export interface ProjectContext { client_name: string; audit_year: string; team_members: { name: string }[]; project_id: string }
export interface ChapterData { title: string; type: 'declaration' | 'commitment' | 'signing' | 'partner' | 'threat' }
export function getPrefix(variant: Variant): string { return variant === 'committee' ? 'a177a-' : 'a177-' }
export const DEFAULT_CHAPTERS: Record<string, ChapterData> = {
  '1': { title: '一、声明正文及业务期间', type: 'declaration' },
  '2': { title: '二、独立性承诺事项', type: 'commitment' },
  '3': { title: '三、项目组成员签字确认', type: 'signing' },
  '4': { title: '四、合伙人及负责经理审查确认', type: 'partner' },
  '5': { title: '五、独立性威胁记录（附件）', type: 'threat' },
}
export const CHAPTER_GUIDANCE: Record<number, string> = {
  1: '独立性声明书应在业务承接阶段签署，并在项目执行过程中如有变化及时更新。\n业务期间指自审计业务承接之日起至审计报告签发之日止的期间。\n财务报告期间指被审计单位财务报表所涵盖的期间。',
  2: '经济利益包括直接经济利益和重大间接经济利益，含股票、债券、基金等投资。\n贷款与担保包括项目组成员或其近亲属与客户之间的贷款或担保关系。\n如对上述任何事项回答"是"，请在说明栏简述具体情况并在附件中记录详细措施。',
  3: '项目组全体成员均须签字确认。签字即表明本人已阅读上述独立性承诺事项并确认遵守。\n可通过"发送确认"按钮将独立性声明弹窗推送给全体项目组成员进行电子签署确认。',
  4: '合伙人审查确认：项目合伙人应审查全体成员的签字及威胁披露情况。\n如确认不存在独立性问题选择"是"，如发现问题选择"否"并说明措施。',
  5: '如存在独立性威胁，应在此附件中如实披露：\n1.经济利益记录 2.贷款担保记录 3.商业关系记录\n无任何威胁时可不填写此附件。',
}
export const DEFAULT_COMMITMENT_ITEMS: CommitmentItem[] = [
  { id: 'economic', label: '本人及直系亲属不持有被审计单位及其关联方的直接或重大间接经济利益', answer: null, explanation: null },
  { id: 'loan', label: '本人及直系亲属与被审计单位及其关联方之间不存在贷款或担保关系', answer: null, explanation: null },
  { id: 'business', label: '本人及直系亲属与被审计单位之间不存在可能产生自身利益威胁的商业关系', answer: null, explanation: null },
  { id: 'family', label: '本人的近亲属未在被审计单位及其关联方担任董事、经理或特定会计岗位', answer: null, explanation: null },
  { id: 'employment', label: '本人未曾在被审计单位担任董事、经理或特定会计岗位（或已满足冷却期要求）', answer: null, explanation: null },
]
export const DECLARATION_TEMPLATES: Record<Variant, string> = {
  team: '本人确认，在本项目的业务期间及财务报告期间内，本人及直系亲属与被审计单位之间不存在可能影响独立性的利害关系。如存在上述情形，已在附件中如实披露并采取了适当防范措施。',
  committee: '本人作为专业技术委员会审核委员，确认在参与本项目的独立性判断过程中，本人与被审计单位之间不存在可能影响判断客观性的利害关系。',
}
