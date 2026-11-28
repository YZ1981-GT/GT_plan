<template>
  <div class="app-container">
    <header class="header">
      <div class="header-left">
        <button type="button" class="logo" aria-label="查看全部智能体" @click="selectCategory('overview')">
          <div class="logo-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
              <rect x="5" y="7" width="14" height="12" rx="3" ry="3" />
              <circle cx="9.5" cy="11" r="1.2" fill="currentColor" stroke="none" />
              <circle cx="14.5" cy="11" r="1.2" fill="currentColor" stroke="none" />
              <path d="M8 14.5c1 1.5 2 2 4 2s3-0.5 4-2" stroke-linecap="round" />
              <line x1="12" y1="5" x2="12" y2="7" stroke-width="1.8" />
              <circle cx="12" cy="4.5" r="1" fill="currentColor" stroke="none" />
              <rect x="3" y="10" width="2.5" height="3" rx="1" />
              <rect x="18.5" y="10" width="2.5" height="3" rx="1" />
            </svg>
          </div>
          <div class="logo-text">GT 智能体商店</div>
        </button>
        <nav class="nav-menu" aria-label="智能体分类">
          <div class="nav-group">
            <button v-for="item in businessNavItems" :key="item.key" type="button"
              class="nav-item" :class="{ active: activeNav === item.key }"
              :aria-pressed="activeNav === item.key" @click="selectCategory(item.key)">
              <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
              <span>{{ item.label }}</span>
            </button>
          </div>
        </nav>
      </div>
    </header>

    <main class="main-layout">
      <div ref="agentsSidebar" class="agents-sidebar">
        <div class="agents-scroll">
          <section class="hero-section">
            <div class="hero-content">
              <div class="hero-badge"><span class="badge-dot" />AI 驱动的工作流</div>
              <h1 class="hero-title">让智能助手<br /><span class="hero-gradient">加速您的业务</span></h1>
              <p class="hero-subtitle">选择专属 AI 助手，探索智能协作新体验</p>
            </div>
            <div class="hero-stats">
              <div class="hero-stat"><div class="stat-number">{{ agents.length }}</div><div class="stat-label">AI 助手</div><div class="stat-trend">规划中</div></div>
              <div class="hero-stat"><div class="stat-number">{{ businessNavItems.length }}</div><div class="stat-label">业务分类</div><div class="stat-trend">可浏览</div></div>
              <div class="hero-stat"><div class="stat-number">{{ connectedCount }}</div><div class="stat-label">已接入</div><div class="stat-trend">待开放</div></div>
            </div>
          </section>

          <div class="agents-container">
            <section v-for="category in businessNavItems" :id="category.key" :key="category.key"
              v-show="shouldShowSection(category.key)" class="agent-category">
              <div class="category-header">
                <div class="category-title">
                  <div class="category-icon" :class="`${category.key}-icon`"><el-icon :size="18"><component :is="category.icon" /></el-icon></div>
                  <span>{{ category.label }}</span>
                  <span class="category-count">{{ agents.filter(agent => agent.category === category.key).length }}</span>
                </div>
              </div>
              <div class="agents-grid">
                <article v-for="agent in agents.filter(agent => agent.category === category.key)" :key="agent.id"
                  class="agent-card" :class="{ 'agent-card--upcoming': agent.upcoming }">
                  <div class="card-inner">
                    <div class="card-icon" :class="agent.category"><el-icon :size="26"><component :is="agent.icon" /></el-icon></div>
                    <div class="card-content">
                      <h2 class="card-title">{{ agent.name }}<span v-if="agent.isNew" class="new-badge">新</span></h2>
                      <p class="card-desc">{{ agent.desc }}</p>
                      <div class="card-meta">
                        <span v-if="agent.url" class="meta-item"><span class="dot online" />已接入</span>
                        <span v-else-if="agent.upcoming" class="meta-item"><span class="dot upcoming" />待上线</span>
                        <span v-else class="meta-item"><span class="dot pending" />待接入</span>
                      </div>
                    </div>
                    <button type="button" class="card-action" :disabled="agent.upcoming" @click="onCardAction(agent)">
                      <span>{{ agent.url ? '开始使用' : agent.upcoming ? '待上线' : '了解详情' }}</span>
                      <svg v-if="!agent.upcoming" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M12 5l7 7-7 7" /></svg>
                    </button>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </div>
      </div>
    </main>

    <div v-if="detailVisible" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-content" role="dialog" aria-modal="true" :aria-label="selectedAgent?.name" @keydown.esc="closeDetail">
        <button type="button" class="modal-close" aria-label="关闭详情" @click="closeDetail">×</button>
        <div v-if="selectedAgent" class="modal-body">
          <div class="modal-icon" :class="selectedAgent.category"><el-icon :size="36"><component :is="selectedAgent.icon" /></el-icon></div>
          <h2 class="modal-title">{{ selectedAgent.name }}</h2>
          <p class="modal-desc">{{ selectedAgent.desc }}</p>
          <div class="modal-stats"><div class="modal-stat"><div class="stat-label">状态</div><div class="stat-number">{{ selectedAgent.url ? '已接入' : '待接入' }}</div></div></div>
          <div class="modal-features"><h4>规划能力</h4><div class="features-list"><div v-for="feature in selectedAgent.features" :key="feature" class="feature"><el-icon><Check /></el-icon><span>{{ feature }}</span></div></div></div>
          <div class="modal-actions"><button type="button" class="btn-secondary" @click="closeDetail">返回列表</button><button v-if="selectedAgent.url" type="button" class="btn-primary" @click="openAgent(selectedAgent)">开始使用</button><button v-else type="button" class="btn-primary" disabled>暂未开放</button></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, ref } from 'vue'
import { Avatar, Check, Connection, DataAnalysis, DocumentCopy, Files, FolderOpened, House, Management, Microphone, Search, Ticket, UserFilled } from '@element-plus/icons-vue'

type Category = 'audit' | 'hq' | 'branch'
type Agent = { id: string; name: string; desc: string; icon: typeof Search; category: Category; isNew?: boolean; features: string[]; url?: string; upcoming?: boolean }
const businessNavItems = [
  { key: 'audit', label: '审计业务', icon: FolderOpened },
  { key: 'hq', label: '总部职能', icon: House },
  { key: 'branch', label: '分所业务', icon: Connection },
] as const
const agents: Agent[] = [
  { id: 'interview', name: '访谈 AI 助手', desc: '智能访谈记录整理、关键信息提取和洞察分析', icon: Microphone, category: 'audit', isNew: true, features: ['语音转文字', '关键信息提取', '访谈报告草稿'], url: 'http://www.gt.qccz.com.cn:31004' },
  { id: 'ocr', name: 'OCR 整理助手', desc: '文档图像识别、表格提取、票据扫描与结构化处理', icon: DocumentCopy, category: 'audit', features: ['多格式识别', '表格提取', '资料整理'], url: 'http://www.gt.qccz.com.cn:31003/' },
  { id: 'audit', name: '审计 AI 助手', desc: '辅助审计程序、风险线索整理和异常提示', icon: Management, category: 'audit', features: ['风险线索整理', '异常提示', '审计程序辅助'], url: 'http://www.gt.qccz.com.cn:31006/' },
  { id: 'proposal', name: '标书 AI 助手', desc: '标书智能撰写、条款审核、风险提示和格式规范检查', icon: Ticket, category: 'hq', features: ['标书草稿', '条款审核', '格式检查'], url: 'http://www.gt.qccz.com.cn:31001/' },
  { id: 'hr', name: '人力 AI 助手', desc: '招聘流程辅助、简历整理、候选人匹配和政策检索', icon: UserFilled, category: 'hq', features: ['简历整理', '候选人比对', '政策检索'], url: 'http://www.gt.qccz.com.cn:31005/' },
  { id: 'contract', name: '合同审查 AI', desc: '合同条款提取、法律风险提示和修订建议', icon: Files, category: 'hq', features: ['条款提取', '风险提示', '修订建议'], upcoming: true },
  { id: 'project', name: '项目立项助手', desc: '项目申报材料整理、可行性分析和进度跟踪', icon: DataAnalysis, category: 'branch', features: ['材料整理', '可行性分析', '进度跟踪'], upcoming: true },
  { id: 'customer', name: '客户画像', desc: '客户信息整理、需求分析和服务建议', icon: Avatar, category: 'branch', features: ['客户信息整理', '需求梳理', '服务建议'], upcoming: true },
]
const activeNav = ref<'overview' | Category>('overview')
const selectedAgent = ref<Agent | null>(null)
const detailVisible = ref(false)
const shouldShowSection = (category: Category) => activeNav.value === 'overview' || activeNav.value === category
const agentsSidebar = ref<HTMLElement | null>(null)
async function selectCategory(category: 'overview' | Category) {
  activeNav.value = category
  await nextTick()
  agentsSidebar.value?.scrollTo({ top: 0, behavior: 'smooth' })
}
const connectedCount = agents.filter(agent => agent.url).length
function openAgent(agent: Agent) {
  if (agent.url) window.open(agent.url, '_blank', 'noopener,noreferrer')
}
function onCardAction(agent: Agent) {
  if (agent.upcoming) return
  if (agent.url) openAgent(agent)
  else openDetail(agent)
}
function openDetail(agent: Agent) { selectedAgent.value = agent; detailVisible.value = true }
function closeDetail() { detailVisible.value = false; selectedAgent.value = null }
</script>

<style scoped>
.app-container{display:flex;flex-direction:column;height:100%;min-height:500px;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;background:linear-gradient(135deg,#F5F7FA 0%,#F0F2F5 100%)}
.header{display:flex;justify-content:space-between;align-items:center;padding:12px 32px;background:rgba(255,255,255,.98);backdrop-filter:blur(10px);border-bottom:1px solid rgba(0,0,0,.05);flex-shrink:0;z-index:1}.header-left{display:flex;align-items:center;gap:48px}.logo{display:flex;align-items:center;gap:12px;cursor:pointer;flex-shrink:0;padding:0;border:0;background:transparent;font:inherit}.logo-icon{width:40px;height:40px;background:linear-gradient(135deg,#4F46E5,#7C3AED);border-radius:14px;display:flex;align-items:center;justify-content:center;color:white;box-shadow:0 4px 12px rgba(79,70,229,.25)}.logo-text{font-size:22px;font-weight:700;letter-spacing:-.3px;color:#1A1A2E}.nav-menu,.nav-group{display:flex;align-items:center;gap:4px}.nav-item{display:flex;align-items:center;gap:8px;padding:8px 18px;border:0;border-radius:40px;background:transparent;color:#5B6778;font-size:14px;font-weight:500;cursor:pointer;transition:all .2s}.nav-item:hover{background:#F5F7FA;color:#1A1A2E}.nav-item.active{background:#EEF2FF;color:#4F46E5}.nav-icon{font-size:18px}
.main-layout{flex:1;position:relative;min-height:0;overflow:hidden}.agents-sidebar{height:100%;overflow-y:auto;background:linear-gradient(135deg,#F5F7FA 0%,#F0F2F5 100%)}.agents-sidebar::-webkit-scrollbar{width:6px}.agents-sidebar::-webkit-scrollbar-track{background:#E4E7EB;border-radius:3px}.agents-sidebar::-webkit-scrollbar-thumb{background:#C4C8D2;border-radius:3px}.agents-scroll{padding:32px 40px;max-width:1400px;margin:0 auto}
.hero-section{background:linear-gradient(135deg,#FFFFFF 0%,#F8F9FF 100%);border-radius:32px;padding:32px 40px;margin-bottom:32px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:32px;box-shadow:0 4px 20px rgba(0,0,0,.02),0 1px 2px rgba(0,0,0,.03)}.hero-badge{display:inline-flex;align-items:center;gap:8px;padding:5px 14px;background:#EEF2FF;border-radius:40px;font-size:12px;font-weight:500;color:#4F46E5;margin-bottom:20px}.badge-dot{width:6px;height:6px;background:#4F46E5;border-radius:50%}.hero-title{font-size:36px;font-weight:700;line-height:1.2;letter-spacing:-.5px;color:#1A1A2E;margin:0 0 16px}.hero-gradient{background:linear-gradient(135deg,#4F46E5,#7C3AED,#A855F7);background-clip:text;-webkit-background-clip:text;-webkit-text-fill-color:transparent}.hero-subtitle{font-size:15px;color:#6B7280;margin:0 0 28px}.hero-stats{display:flex;gap:40px}.hero-stat{text-align:center}.hero-stat .stat-number{font-size:32px;font-weight:700;color:#1A1A2E}.hero-stat .stat-label{font-size:13px;color:#8A94A6;margin-top:6px}.hero-stat .stat-trend{font-size:11px;color:#8A94A6;margin-top:4px}
.agent-category{margin-bottom:48px}.category-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:12px}.category-title{display:flex;align-items:center;gap:12px;font-size:18px;font-weight:600;color:#1A1A2E}.category-icon{width:34px;height:34px;border-radius:10px;display:flex;align-items:center;justify-content:center;color:white}.audit-icon,.card-icon.audit{background:#0094B3}.hq-icon,.card-icon.hq{background:#FF5149}.branch-icon,.card-icon.branch{background:#FFC23D}.category-count{padding:2px 10px;background:#F0F2F5;border-radius:30px;font-size:12px;font-weight:500;color:#5B6778}
.agents-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:20px}.agent-card{background:#FFFFFF;border-radius:20px;transition:all .3s cubic-bezier(.2,0,0,1);border:1px solid rgba(0,0,0,.05);overflow:hidden}.agent-card:hover{transform:translateY(-4px);border-color:transparent;box-shadow:0 20px 32px rgba(0,0,0,.08),0 4px 12px rgba(0,0,0,.02)}.card-inner{padding:20px}.card-icon{width:48px;height:48px;border-radius:14px;display:flex;align-items:center;justify-content:center;color:white;margin-bottom:16px}.card-title{font-size:16px;font-weight:600;color:#1A1A2E;margin:0 0 6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}.new-badge{font-size:10px;padding:2px 8px;background:#FEF3C7;border-radius:20px;color:#D97706;font-weight:500}.card-desc{font-size:13px;color:#6B7280;line-height:1.5;margin:0 0 14px}.card-meta{display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap}.meta-item{display:flex;align-items:center;gap:6px;font-size:12px;color:#8A94A6}.dot{width:6px;height:6px;border-radius:50%}.dot.online{background:#10B981;box-shadow:0 0 0 2px rgba(16,185,129,.2)}.dot.upcoming{background:#9CA3AF;box-shadow:0 0 0 2px rgba(156,163,175,.2)}.agent-card--upcoming{opacity:.6}.agent-card--upcoming:hover{transform:none;box-shadow:none;border-color:rgba(0,0,0,.05)}.card-action:disabled{cursor:not-allowed;color:#9CA3AF;background:#F5F7FA;border-color:#E4E7EB}.card-action:disabled:hover{background:#F5F7FA;border-color:#E4E7EB}.dot.pending{background:#D9A046;box-shadow:0 0 0 2px rgba(217,160,70,.2)}.card-action{width:100%;display:flex;align-items:center;justify-content:center;gap:8px;padding:8px;background:#F8F9FF;border:1px solid #E4E7EB;border-radius:40px;font-size:13px;font-weight:500;color:#4F46E5;cursor:pointer;transition:all .2s}.card-action:hover{background:#EEF2FF;border-color:#C7D2FE}.card-action svg{transition:transform .2s}.card-action:hover svg{transform:translateX(4px)}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;z-index:2000}.modal-content{width:460px;max-width:90%;background:#FFFFFF;border-radius:28px;padding:28px;position:relative;animation:modalIn .3s ease}.modal-close{position:absolute;top:16px;right:16px;width:32px;height:32px;background:#F5F7FA;border:none;border-radius:50%;color:#8A94A6;font-size:18px;cursor:pointer}.modal-close:hover{background:#E4E7EB;color:#1A1A2E}.modal-body{text-align:center}.modal-icon{width:72px;height:72px;border-radius:20px;display:flex;align-items:center;justify-content:center;color:white;margin:0 auto 16px}.modal-icon.audit{background:linear-gradient(135deg,#10B981,#059669)}.modal-icon.hq{background:linear-gradient(135deg,#EF4444,#DC2626)}.modal-icon.branch{background:linear-gradient(135deg,#3B82F6,#2563EB)}.modal-title{font-size:22px;font-weight:700;color:#1A1A2E;margin:0 0 8px}.modal-desc{font-size:14px;color:#6B7280;margin:0 0 20px}.modal-stats{display:flex;justify-content:center;gap:28px;padding:14px;background:#F8F9FF;border-radius:20px;margin-bottom:20px;flex-wrap:wrap}.modal-stat .stat-label{font-size:12px;color:#8A94A6;margin-bottom:4px}.modal-stat .stat-number{font-size:18px;font-weight:600;color:#1A1A2E}.modal-features{text-align:left;margin-bottom:24px}.modal-features h4{font-size:14px;font-weight:600;color:#1A1A2E;margin-bottom:12px}.features-list{display:flex;flex-wrap:wrap;gap:10px}.feature{display:flex;align-items:center;gap:6px;padding:5px 12px;background:#F8F9FF;border-radius:40px;font-size:12px;color:#374151}.feature .el-icon{color:#10B981}.modal-actions{display:flex;gap:12px}.modal-actions button{flex:1;justify-content:center}.btn-primary,.btn-secondary{display:inline-flex;align-items:center;justify-content:center;gap:10px;padding:10px 24px;border-radius:40px;font-size:14px;cursor:pointer}.btn-primary{background:linear-gradient(135deg,#4F46E5,#7C3AED);border:0;font-weight:600;color:white}.btn-primary:disabled{opacity:.5;cursor:not-allowed}.btn-secondary{background:#FFFFFF;border:1px solid #E4E7EB;font-weight:500;color:#374151}.btn-secondary:hover{background:#F5F7FA}
@keyframes modalIn{from{opacity:0;transform:scale(.95)}to{opacity:1;transform:scale(1)}}button:focus-visible,.logo:focus-visible{outline:2px solid #4F46E5;outline-offset:2px}@media(max-width:1024px){.agents-scroll{padding:24px}.hero-section{flex-direction:column;text-align:center;padding:28px}.hero-title{font-size:30px}.header-left{gap:16px}}@media(max-width:768px){.header{padding:12px 16px}.logo-text{font-size:17px}.nav-menu{overflow-x:auto}.nav-item{padding:8px;white-space:nowrap}.nav-item span{display:none}.hero-title{font-size:24px}.hero-section{padding:20px}.agents-grid{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){.agent-card,.card-action,.nav-item{transition:none}.agent-card:hover,.card-action:hover svg{transform:none}.modal-content{animation:none}}
</style>
