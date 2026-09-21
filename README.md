# ReviewFlow Quality Kit

电商评价分析的开源核心组件。本仓库**只含通用方法论与合成数据**，不包含任何平台适配、客户数据或商业化产品本体——可安全公开，并欢迎社区贡献以共同提升评价分析的质量标准。

## 包含什么

| 文件 | 作用 |
|---|---|
| `quality_baseline.json` | 20 条**合成**评价基准集（5 类×3 + 5 条边界：空泛/多标签/含隐私/超长），用于回归评测分析引擎的归类准确率、脱敏、计数一致性 |
| `QUALITY_RUBRIC.md` | 6 维度 100 分人工审核量表；**脱敏**与**计数一致**为一票否决项，通过线 80 分 |
| `analyzer.py` | 稳健的 LLM 结构化抽取模块（见下），仅依赖标准库，适配任何 OpenAI 兼容网关 |
| `LICENSE` | MIT |

## analyzer.py 的设计取舍（取自社区精华）

本模块融合了公开项目的两点关键经验：

1. **代码本（codebook）驱动归类**——参考 [CoCode](https://github.com/Yingna0614/CoCode)：给每个类别写清定义，显著提升 LLM 归类的稳定性，避免「物流慢」被当成问题描述。
2. **输出修复 + 重试反馈**——参考 [outputguard](https://github.com/ndcorder/outputguard)：剥离 markdown 围栏、从散文中抽取 JSON、修复尾逗号/单引号等畸形；校验失败时把错误回灌模型最多重试 N 次；全部失败再回落兜底规则。

```python
from analyzer import llm_classify, repair_json

samples = ["快递晚了两天，物流不更新", "包装没缓冲边角磕坏", "暂时没有更多意见"]
res = llm_classify(samples)   # {1: {category, suggestion, reply}, ...}
```

默认指向本机 Ollama（`http://127.0.0.1:11434/v1/chat/completions`，模型 `qwen2.5:7b`），可用环境变量 `LLM_ENDPOINT` / `LLM_MODEL` 覆盖。

## 我们如何用这份开源资产

- **对外**：把质量基准与审核量表公开，建立「什么是好报告」的行业话语权。
- **换数据（只收统计，不收内容）**：如果你在自家场景里发现本基准集判错或覆盖不到的**类别/模式**，欢迎提 Issue 描述现象（不要贴真实评价内容）。我们会据此迭代基准集与提示词，**自己先用**再回馈社区。
- **不公开的**：平台发布适配、客户真实数据、付费产品本体——这些留在本仓库之外。

## 许可

MIT。合成数据可自由用于评测与教学。
