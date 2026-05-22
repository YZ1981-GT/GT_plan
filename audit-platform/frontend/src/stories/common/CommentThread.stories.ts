import type { Meta, StoryObj } from '@storybook/vue3'
import CommentThread from '@/components/common/CommentThread.vue'

const meta = {
  title: 'Common/CommentThread',
  component: CommentThread,
  tags: ['autodocs'],
} satisfies Meta<typeof CommentThread>

export default meta
type Story = StoryObj<typeof meta>

const sampleComments = [
  {
    id: '1',
    author: '张经理',
    content: '请核实该科目余额与银行对账单是否一致',
    createdAt: '2026-05-20T10:30:00',
    resolved: false,
    replies: [
      { author: '李助理', content: '已核对，差异为 ¥500，属于在途款项', createdAt: '2026-05-20T11:00:00' },
    ],
  },
  {
    id: '2',
    author: '王合伙人',
    content: '该调整分录需要补充审计依据',
    createdAt: '2026-05-19T14:20:00',
    resolved: true,
  },
]

export const Default: Story = {
  args: {
    comments: sampleComments,
    currentUser: '李助理',
  },
}

export const Empty: Story = {
  args: {
    comments: [],
    currentUser: '张经理',
  },
}

export const ManyReplies: Story = {
  args: {
    comments: [
      {
        id: '1',
        author: '质控',
        content: '请确认重要性水平计算依据',
        createdAt: '2026-05-18T09:00:00',
        resolved: false,
        replies: [
          { author: '项目经理', content: '依据净利润 5%', createdAt: '2026-05-18T09:30:00' },
          { author: '质控', content: '建议同时考虑收入基准', createdAt: '2026-05-18T10:00:00' },
          { author: '项目经理', content: '已补充双基准对比', createdAt: '2026-05-18T11:00:00' },
        ],
      },
    ],
    currentUser: '质控',
  },
}
