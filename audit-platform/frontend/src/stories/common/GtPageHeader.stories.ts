import type { Meta, StoryObj } from '@storybook/vue3'
import GtPageHeader from '@/components/common/GtPageHeader.vue'

const meta = {
  title: 'Common/GtPageHeader',
  component: GtPageHeader,
  tags: ['autodocs'],
  argTypes: {
    variant: { control: 'select', options: ['default', 'banner'] },
    backMode: { control: 'select', options: ['route', 'history'] },
  },
} satisfies Meta<typeof GtPageHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    title: '试算平衡表',
    showBack: true,
  },
}

export const BannerVariant: Story = {
  args: {
    title: '项目仪表盘',
    variant: 'banner',
    icon: '📊',
    showBack: false,
  },
}

export const WithSyncStatus: Story = {
  args: {
    title: '底稿编辑器',
    showBack: true,
    showSyncStatus: true,
  },
}

export const NoBackButton: Story = {
  args: {
    title: '报表视图',
    showBack: false,
  },
}
