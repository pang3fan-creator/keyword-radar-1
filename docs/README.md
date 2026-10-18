# 文档索引

这个仓库的文档分两类：**现行**（跟着代码改）和**调研**（记录当时的判断）。

## 现行

| 文件 | 用途 |
|---|---|
| [README.md](../README.md) | 使用者入口：信号、两条线、命令、成本、报告样例 |
| [AGENTS.md](../AGENTS.md) | 协作契约：布局、命令、测试、交接清单、当前状态 |
| [Roadmap/00-项目约束与评估框架.md](Roadmap/00-项目约束与评估框架.md) | 五条硬约束、统一评估框架、五种词的定义（2026-10-17 确认） |
| [Roadmap/05-整合方法论.md](Roadmap/05-整合方法论.md) | 方法论：架构、信号清单、判断链、数据模型、里程碑、风险 |
| [Roadmap/06-范围与垂直扩展备忘.md](Roadmap/06-范围与垂直扩展备忘.md) | 范围（v1）、明确不做的事、垂直扩展清单 |
| [里程碑.md](里程碑.md) | M0–M5 的开发记录：数字、提交、当时留下的问题 |

## 调研（历史，保留判断过程）

| 文件 | 内容 |
|---|---|
| [Roadmap/01-孟健路线.md](Roadmap/01-孟健路线.md) | 品类组合词工厂 |
| [Roadmap/02-哥飞路线.md](Roadmap/02-哥飞路线.md) | 供应侧侦察、判断工具箱 |
| [Roadmap/03-jason-new-term-radar.md](Roadmap/03-jason-new-term-radar.md) | 上游 new-term-radar 的四栏拆解 |
| [Roadmap/04-trendradar.md](Roadmap/04-trendradar.md) | TrendRadar 的工程件和限制 |

## 图

`make_diagram/` 是流程图的脚本和 GIF。2026-10-18 按当前代码重画：①–⑩ 信号、名字判断、新词表、慢线、1/3/7/14 与 14/30 复盘、MCP。重画需要 `rsvg-convert` 和 `ffmpeg`。

## 约定

- 编号 00–06 是调研期的顺序，不改号；新增文档用描述性文件名。
- `Roadmap/` 里的文件是当时的判断，除事实性错误外不回改；现行规则写进 `AGENTS.md` 或方法论 05。
- 代码注释里的 `docs/05 §x` 是 [Roadmap/05-整合方法论.md](Roadmap/05-整合方法论.md) 的简写（文件移动前的写法，保留未改）。
