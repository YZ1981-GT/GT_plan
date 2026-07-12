# render 冒烟测试集

> Feature: platform-global-hardening · Requirements: 3.5, 3.6

数据驱动的 Playwright 冒烟测试，对每个 `wp_code` 打开一次底稿并验证：
1. 浏览器 console error 数量 = 0
2. 关键区块选择器（`.gt-wp-root` / `.workpaper-editor` 等）存在

## 运行方式

```bash
# 确保前端(3030) + 后端(9980) 已启动
npm run test:render-smoke

# 或直接调用 Playwright CLI（可过滤）
npx playwright test --config=tests/render-smoke/playwright.config.ts

# 只测指定循环（用 grep 过滤）
npx playwright test --config=tests/render-smoke/playwright.config.ts --grep "D2"
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RENDER_SMOKE_BASE_URL` | `http://localhost:3030` | 前端地址 |
| `RENDER_SMOKE_BACKEND_URL` | `http://localhost:9980` | 后端 API 地址 |

## wp_code 清单生成

`generate-wp-list.ts` 从 `backend/app/data/wp_code_overrides.json` 读取并过滤：
- 排除 `componentType = "skip"` 的子 sheet
- 排除非 wp_code 格式的描述性文本键
- 按字典序排列确保稳定顺序

当前约 **1166** 个有效 wp_code 参与测试。

## CI 集成

挂载于 `governance-checks.yml` 的 `render-smoke` job：
- 初期 `continue-on-error: true`（灰度报告模式）
- 全量迁移完成后转 blocking

## 失败报告

测试失败时输出：
- `[wp_code]` 标识哪个底稿出错
- console error 摘要（最多前 5 条，每条截取前 200 字符）
- 缺失的关键区块选择器列表
