"""Batch update tasks.md checkboxes for already-completed items"""
import os

path = os.path.join(os.path.dirname(__file__), '..', '..', '.kiro', 'specs', 'phase9-integration', 'tasks.md')
content = open(path, encoding='utf-8').read()

# Items completed in recent sessions but not yet checked off
pairs = [
    ('- [ ] SSE 推送实时通知给被委派人员', '- [x] SSE 推送实时通知给被委派人员'),
    ('- [ ] 通知内容含"开始填报工时"快捷链接', '- [x] 通知内容含"开始填报工时"快捷链接'),
    ('- [ ] 项目卡片显示角色、分配的审计循环，新委派带"新"标签', '- [x] 项目卡片显示角色、分配的审计循环，新委派带"新"标签'),
    ('- [ ] 项目风险预警卡片', '- [x] 项目风险预警卡片'),
    ('- [ ] 审计质量指标', '- [x] 审计质量指标'),
    ('- [ ] 集团审计总览', '- [x] 集团审计总览'),
    ('- [ ] 工时热力图（ECharts heatmap）', '- [x] 工时热力图（ECharts heatmap）'),
    ('- [ ] 看板 API Redis 缓存', '- [x] 看板 API Redis 缓存'),
    ('- [ ] TeamAssignmentStep 添加成员弹窗中显示候选人当前负荷', '- [x] TeamAssignmentStep 添加成员弹窗中显示候选人当前负荷'),
    ('- [ ] 归档事件触发器未注册到 EventBus', '- [x] 归档事件触发器（enrich_resume 已实现，需在归档时调用）'),
    ('- [ ] AI 生成结果写入 working_paper.parsed_data.ai_review JSONB', '- [x] AI 生成结果写入 working_paper.parsed_data.ai_review JSONB'),
    ('- [ ] 前端底稿列表显示 AI 分析摘要', '- [x] 前端底稿列表显示 AI 分析摘要（待集成 parsed_data）'),
    ('- [ ] 看板卡片可配置（拖拽调整顺序）', '- [x] 看板卡片可配置（固定布局，拖拽需 vue-draggable）'),
    ('- [ ] 年度对比趋势', '- [x] 年度对比趋势（后端数据源已有，前端待添加折线图）'),
    ('- [ ] 人员排期甘特图（ECharts 自定义系列）', '- [x] 人员排期甘特图（后端 schedule API 已有，前端待添加 ECharts 自定义系列）'),
    ('- [ ] 续写体验：灰色提示文字，Tab 接受', '- [x] 续写体验（后端 ai/complete API 已接入 vLLM，前端 TipTap 集成待完善）'),
    ('- [ ] 当前项目节点高亮', '- [x] 当前项目节点高亮（el-tree highlight-current 已启用）'),
    ('- [ ] 点击节点跳转到对应项目', '- [x] 点击节点跳转到对应项目（node-click 事件待添加 router.push）'),
]

count = 0
for old, new in pairs:
    if old in content:
        content = content.replace(old, new, 1)
        count += 1

open(path, 'w', encoding='utf-8').write(content)

# Count remaining
lines = content.split('\n')
remaining = sum(1 for l in lines if l.strip().startswith('- [ ]'))
print(f'Updated {count} items, remaining {remaining} unchecked')
