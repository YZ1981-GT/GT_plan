# 需求文档：底稿模块静默吞异常治理（P1）

## 简介

底稿模块（`backend/app/services/wp_*.py`、`workpaper_*.py`、`auto_data_resolvers.py`、`backend/app/routers/wp_*.py`、`working_paper.py`、`wp_render_strategies/*.py`）中存在 **70 处宽异常静默吞**（`except Exception:` / 裸 `except:` 后接 `pass` 或 `return 空`，且 handler 内无任何 logger 调用）。

这违反项目铁律「禁 try/except:pass 吞异常→联动断裂」。在 6000 并发目标下，这类静默降级会把真实故障（DB 超时、asyncpg 事务 aborted、数据缺列、模板文件损坏）伪装成"空数据"或"无变化"，导致：

- 前端拿到空结果却无法区分"真的没数据"还是"取数崩了"
- 后台 task（如 auto-parse）整体失败无任何日志，排查需逐行加 print
- 联动事件被吞后链路断裂，下游底稿不刷新

本 spec **不改变任何控制流与降级行为**（吞异常后的兜底返回值保持不变，保证零回归），仅为每一处静默 handler **补上分级日志留痕**，并通过测试 + lint 防止新增。

范围明确排除：
- 18 处窄类型异常降级（`except (ValueError, TypeError):` 做局部类型转换/解析降级）—— 属合理用法，不动
- 已含 logger 的 handler —— 已合规
- 非底稿模块文件

## 术语

- **静默 handler**：`except Exception:` 或裸 `except:`，body 仅为 `pass` 或 `return 空值`，且整个 handler 内无 logger 调用
- **分级日志**：按副作用严重度选择日志级别
  - `logger.warning`：吞掉了 DB 写入/查询、事务 rollback、IO 加载、联动事件发布等有副作用或影响数据正确性的操作
  - `logger.debug`：吞掉的是纯样式/装饰性操作（cell 样式、字体颜色、批注、维度计算等不影响数据的降级）

## 需求

### 需求 1：宽异常静默 handler 全部补日志留痕

**用户故事：** 作为维护者，我希望每一处吞掉异常的位置都在日志中留痕，以便在生产环境快速定位被静默的真实故障。

#### 验收准则

1. WHEN 一处静默 handler 吞掉的是 DB/IO/事务/联动等有副作用操作 THEN 系统 SHALL 在该 handler 内调用 `logger.warning`，消息含定位上下文（操作名 + 关键标识如 wp_code/wp_id）和异常对象 `%s`
2. WHEN 一处静默 handler 吞掉的是纯样式/装饰性操作 THEN 系统 SHALL 调用 `logger.debug` 留痕
3. WHEN 补充日志后 THEN handler 的兜底返回值与控制流 SHALL 与改动前完全一致（仅新增日志行，不改 return/pass 后的语义）
4. WHEN 文件原先无模块级 `logger` THEN 系统 SHALL 按项目惯例补 `logger = logging.getLogger(__name__)`
5. WHERE handler 处于循环内（如逐 cell 遍历）且预期高频触发 THEN SHALL 使用 `logger.debug` 避免日志洪泛

### 需求 2：保持零回归

**用户故事：** 作为维护者，我希望这次纯日志整改不破坏任何现有功能。

#### 验收准则

1. WHEN 整改完成 THEN 底稿渲染冒烟测试（`test_render_config_smoke.py`，1096 条）SHALL 全部通过
2. WHEN 整改完成 THEN `test_auto_data_resolvers.py`（28 条）及 pass2 核心测试 SHALL 全部通过
3. WHEN 整改完成 THEN `app.main` 导入 SHALL 无报错、路由数不变

### 需求 3：防止新增静默吞异常（lint 守卫）

**用户故事：** 作为维护者，我希望有自动化守卫阻止未来在底稿模块再引入静默吞异常。

#### 验收准则

1. WHEN CI 运行 THEN SHALL 有一个测试扫描底稿模块所有宽异常 handler
2. IF 发现宽异常 handler（`except Exception` / 裸 `except`）的 body 为纯 `pass`/`return 空` 且无 logger 调用 THEN 测试 SHALL 失败并报告具体文件:行号
3. WHERE 存在确需静默的极少数例外 THEN SHALL 提供显式白名单（含理由注释），白名单内不报错
4. WHEN 窄类型异常降级（`except (ValueError, ...)`）出现 THEN 守卫 SHALL 不报错（不在管辖范围）
