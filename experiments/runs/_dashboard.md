# Verified-mini run dashboard

| run | status | model | resolved | rate | 95% CI | vs baseline | django | sphinx | steps med/mean | regressions | trunc | repeats | retrieved | infra/empty/err |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline | confirmed | openai/doubao-seed-2-1-lite-260915 | 30/50 | 60% | [46%, 72%] | —（基线） | 18 | 12 | 34/46 | 6(11) | 22 | 16 | 4 | 0/0/0 |
| probes/hard-case-rerun | confirmed | openai/doubao-seed-2-1-lite-260915 | 1/2 | 50% | [9%, 91%] | —（任务集不同） | 0 | 1 | 90/90 | 0(0) | 0 | 1 | 1 | 0/0/0 |
| probes/models/glm-5.3 | confirmed | openai/glm-5.3 | 1/2 | 50% | [9%, 91%] | —（任务集不同） | 0 | 1 | 75/75 | 1(1) | 1 | 0 | 1 | 0/0/0 |
| probes/models/kimi-k3 | confirmed | openai/kimi-k3 | 2/2 | 100% | [34%, 100%] | —（任务集不同） | 0 | 2 | 48/48 | 0(0) | 0 | 1 | 2 | 0/0/0 |
| probes/models/ds-v4-pro | confirmed | openai/deepseek-v4-pro | 2/2 | 100% | [34%, 100%] | —（任务集不同） | 0 | 2 | 58/58 | 0(0) | 6 | 0 | 2 | 0/0/0 |
| probes/models/ds-v4.1-flash | confirmed | openai/deepseek-v4-1-flash | 2/2 | 100% | [34%, 100%] | —（任务集不同） | 0 | 2 | 26/26 | 0(0) | 6 | 0 | 2 | 0/0/0 |
| probes/retrieval-prompt | confirmed | openai/doubao-seed-2-1-lite-260915 | 2/2 | 100% | [34%, 100%] | —（任务集不同） | 0 | 2 | 58/58 | 0(0) | 0 | 0 | 2 | 0/0/0 |
| probes/retrieval-tool | confirmed | openai/doubao-seed-2-1-lite-260915 | 1/2 | 50% | [9%, 91%] | —（任务集不同） | 0 | 1 | 76/76 | 0(0) | 0 | 4 | 1 | 0/0/0 |
| retrieval-tool-50 | confirmed | openai/doubao-seed-2-1-lite-260915 | 36/50 | 72% | [58%, 83%] | 58% 明显重叠 | 20 | 16 | 32/46 | 4(8) | 34 | 23 | 22 | 0/0/0 |
| retrieval-prompt-50 | confirmed | openai/doubao-seed-2-1-lite-260915 | 41/50 | 82% | [69%, 90%] | 15% 边缘 | 22 | 19 | 28/37 | 5(9) | 16 | 230 | 45 | 0/1/0 |
| retrieval-prompt-50__rep2 | confirmed | openai/doubao-seed-2-1-lite-260915 | 42/50 | 84% | [71%, 92%] | 4% 边缘 | 23 | 19 | 29/45 | 3(7) | 16 | 9 | 49 | 0/1/0 |
| gate-smoke | confirmed | openai/doubao-seed-2-1-lite-260915 | 2/4 | 50% | [15%, 85%] | —（任务集不同） | 0 | 2 | 42/42 | 2(6) | 2 | 9 | 4 | 0/0/0 |
| gate-webhint-50 | confirmed | openai/doubao-seed-2-1-lite-260915 | 44/50 | 88% | [76%, 94%] | 0% 不重叠(显著) | 24 | 20 | 34/44 | 4(8) | 15 | 46 | 48 | 0/0/0 |

## 说明（中文）

- `vs baseline`：仅当与基线**跑的是同一批题**时计算（不同任务集或 n=2 探针显示「—（任务集不同）」，因为区间不可比）。数值 = 与基线区间的**重叠宽度 ÷ 较窄区间宽度**。`0%` 不重叠（可称显著）；`<20%` 边缘（再差 1–2 题就分开）；`20–50%` 部分重叠（说不准）；`>50%` 明显重叠（无差异）。
- 该判据**偏保守**：两区间重叠也可能存在真实差异。正式结论应看**差值区间是否跨 0**（同题配对时用 McNemar 更稳）。
- `95% CI` 为 Wilson 置信区间：n=50 时约 ±13pp；n=2 的探针区间宽达 [34%,100%]，其重叠比例仅供参考，不能用来宣称提升。
- 回归数 = 新弄坏的 PASS_TO_PASS 旧测试数；检索 = 轨迹中出现网络请求的实例数；截断 = 观察超 10k 字符被裁剪的次数。

- **baseline**: F2P partially passing but unresolved: django__django-11885, django__django-12406, sphinx-doc__sphinx-8269, sphinx-doc__sphinx-8475
- **gate-smoke**: F2P partially passing but unresolved: sphinx-doc__sphinx-8269, sphinx-doc__sphinx-8475
- **gate-webhint-50**: F2P partially passing but unresolved: sphinx-doc__sphinx-8269, sphinx-doc__sphinx-8475
- **retrieval-prompt-50**: F2P partially passing but unresolved: django__django-11815, django__django-12406, sphinx-doc__sphinx-8269, sphinx-doc__sphinx-8475
- **retrieval-prompt-50__rep2**: F2P partially passing but unresolved: sphinx-doc__sphinx-10435, sphinx-doc__sphinx-8269, sphinx-doc__sphinx-8475
- **retrieval-tool-50**: F2P partially passing but unresolved: django__django-12406, sphinx-doc__sphinx-10435, sphinx-doc__sphinx-8269, sphinx-doc__sphinx-8475
