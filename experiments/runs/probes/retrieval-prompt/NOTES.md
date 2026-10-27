# 消融实验：doubao-lite + 联网检索提示（prompt-only）

日期：2026-10-22
假设：强模型在 8056/8638 上成功是因为主动用 curl 检索了 GitHub 上的 issue/PR；
若仅在 prompt 中显式提示 doubao-lite 去检索上游信息（模型、配置、工具集均不变，仍只有 bash），
弱模型也应能翻盘。

## 改动（唯一变量）

- 模型：仍是 `openai/doubao-seed-2-1-lite-260915`，swebench.yaml 其余配置不变，w=2，直连+本地数据集。
- 仅在 system/instance 指令中新增一节 "Searching for upstream context"，提示用 curl 查
  GitHub issues/comments/timeline/PR diff，强调当作线索、自行复现与验证、不要盲抄。
- 变体配置：`experiments/verified_mini_baseline/swebench_webhint.yaml`。

## 结果：两个原本失败的实例都翻盘（2/2 resolved）

| 实例 | 基线 lite（无提示） | **+ 联网提示** | 步数 | GitHub 请求 | 测试 |
|---|---|---|---:|---:|---|
| sphinx-8056 | ❌（两次，0 次联网） | **✅** | 21 | 28 | F2P 1/1，0 回归 |
| sphinx-8638 | ❌→✅（第二次才过，0 次联网） | **✅** | 96 | 78 | F2P 1/1，0 回归 |

harness 报告：`report/openai__doubao-seed-2-1-lite-260915.lite_webhint.json`。

## 结论

1. **假设成立**：决定 8056 成败的主要不是模型档位，而是"主动检索上游信息"的策略。
   一句 prompt 提示就让 doubao-lite 从 3 次全败变成 1 次解决，行为从"封闭试错"转为"开卷查证"。
2. 这证明给弱模型加**显式检索能力/提示**是性价比最高的优化方向，比直接换强模型便宜得多。
3. 8638 在加提示后稳定解决（96 步，仍偏慢）；8056 仅 21 步，与最强的 ds-flash（21 步）持平。

## 必须注意的评测口径

- 该变体属于**允许联网的开卷设定**。SWE-bench 容器默认有网、官方不禁止，但结果与"闭卷独立解出"不可直接混为一谈；
  汇总分数时应单独标注 webhint 设定。
- 轨迹含 GitHub 访问 = 可能参考了官方 PR，应区分 **lookup 成功** 与 **独立解出**，避免把检索能力误记为模型推理能力。
- 下一步：在全量 50 题上跑该 prompt 变体，量化对总体 resolved 率的提升（预期对"有公开 PR 修复"的题帮助最大），
  并统计联网使用频率、步数/成本变化。
