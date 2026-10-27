# 与官方参照结果对比（同一 50 道 mini 题目）

参照来源：`mariushobbhahn/make_swe_bench_verified_mini` 仓库 16 模型评估（Inspect swe_bench scaffold，约 2024Q4 模型版本），逐实例分数取自 `data/merged_df_pass_rate_with_metadata.csv`，在 mini 的 50 个 id 上重新计算。

| 模型 (Inspect scaffold) | mini-50 | full-500 |
|---|---:|---:|
| **doubao-seed-2-1-lite + mini-swe-agent（本次基线）** | **60.0%** | — |
| o1-2024-12-17 | 40.0% | 34.2% |
| claude-3-5-sonnet-20241022 | 30.6% | 33.1% |
| claude-3-5-sonnet-20240620 | 22.4% | 26.9% |
| gpt4o-2024-08-06 | 22.0% | 20.6% |
| Qwen2.5-Coder-32B-Instruct | 20.8% | 18.2% |
| Meta-Llama-3.1-405B-Instruct-Turbo | 20.0% | 16.4% |
| Qwen2.5-72B-Instruct-Turbo | 16.0% | 12.4% |
| gpt-4-turbo-2024-04-09 | 16.0% | 17.1% |
| claude-3-opus-20240229 | 14.0% | 14.8% |
| gpt-3.5-turbo-0125 | 10.0% | 5.0% |
| Meta-Llama-3.1-70B-Instruct-Turbo | 8.0% | 11.6% |
| claude-2.1 | 4.0% | 3.8% |
| claude-3-sonnet-20240229 | 4.0% | 8.2% |
| gpt-4o-mini-2024-07-18 | 4.0% | 7.8% |
| Meta-Llama-3.1-8B-Instruct-Turbo | 0.0% | 1.2% |

## 解读注意

1. **框架不同，不是严格可比的模型排名**：参照结果用的是 Inspect AI 的 swe_bench scaffold（OpenAI 官方 agent 配方），本次用 mini-swe-agent 自带 prompt/工具循环；两边 scaffold、采样参数、尝试次数都不同。分数差异里同时包含模型能力与 agent 框架差异。
2. doubao lite 是 2025 年新模型，参照表里最强的是 2024 年底的 o1（mini 40%）/ claude-3.5-sonnet（30.6%）。60% 的数字与这批旧模型不在同一时间基线，仅作量级参照。
3. mini 子集的通过率与 full-500 普遍相差 ±4 个百分点（作者用 LP 选样保分布），说明 mini-50 作为相对比较指标基本可用，但 n=50 下单题波动 ≈ ±7%（1/50），消融差异小于 2 题时不宜下结论。
4. 官方（SWE-bench 团队）只维护 swebench.com 全量 leaderboard，verified-mini 是第三方子集，**没有官方模型榜**；以上 16 模型是数据集作者提供的唯一公开参照。
5. Qwen2.5-7B 一行在该表 mini 上全为 NaN（日志缺失），已剔除（其 full 仅 0%）。

## 建议的强对比

真正有意义的对比是在**同一 mini-swe-agent 框架、同一 50 题**下换模型/做消融（你接下来的实验设计），而不是和这张 Inspect 表比绝对值。若需要外部锚点，可用相同框架跑一个公开模型（如 claude-sonnet-4.5，swebench.yaml 默认）作为框架内参照。