# 强模型复测报告：8056 / 8638 两个 sphinx 难例

日期：2026-10-22
框架：mini-swe-agent 2.4.6，统一配置（`swebench.yaml`、yolo、同一 50 题数据集、同一官方 harness 判分），仅更换模型。
端点：火山方舟 Coding Plan `https://ark.cn-beijing.volces.com/api/coding/v3`。

## 1. 起因

doubao-seed-2-1-lite 基线在 verified-mini 上 resolved 30/50 = 60%。
对 20 个 unresolved 中步数最多的两个实例做同配置重跑，发现一个失败有随机性、一个两次都失败：
随后用多个更强模型复测，以区分"题目无解 / 框架问题 / 模型能力差异"。

- `sphinx-doc__sphinx-8638`：`sphinx/domains/python.py`，目标测试 `test_info_field_list_var`（1 个 FAIL_TO_PASS）。
- `sphinx-doc__sphinx-8056`：`sphinx/ext/napoleon/docstring.py`，目标测试 `NumpyDocstringTest::test_multiple_parameters`（1 个 FAIL_TO_PASS）。

## 2. 跨模型结果汇总

| 模型 | 8056 | 8638 | 8056 步数 | 8638 步数 | 备注 |
|---|:---:|:---:|---:|---:|---|
| doubao-seed-2-1-lite（基线） | ❌ | ❌→✅ | 100 / 46（两次） | 100 / 133（两次） | 每个实例跑了两次 |
| glm-5.3 | ❌ | ✅ | 84 | 66 | 8056 引入 1 个 PASS_TO_PASS 回归 |
| kimi-k3 | ✅ | ✅ | 43 | 54 | |
| deepseek-v4-pro | ✅ | ✅ | 42 | 75 | |
| deepseek-v4-1-flash | ✅ | ✅ | **21** | **31** | 两个实例步数都最少 |
| deepseek-v4-1-flash-economy | ⛔ | ⛔ | — | — | 真实 agent 负载下请求挂死，不可用 |

判定均来自官方 harness（swebench 5.0.2 + `SWE-bench/SWE-bench_Verified`）：✅=FAIL_TO_PASS 全过且无 PASS_TO_PASS 回归。

各模型产物目录：
`experiments/runs/probes/models/glm-5.3/`、`probes/models/kimi-k3/`、`probes/models/ds-v4-pro/`、
`probes/models/ds-v4.1-flash/`、`probes/models/ds-v4.1-flash-economy/`（最后一个无有效成果）。

## 3. 核心结论

### 3.1 8056 是真实的"模型能力分界题"

- doubao-lite 两次、glm-5.3 一次共 3 次运行全部失败，且都卡在同一个目标测试
  `NumpyDocstringTest::test_multiple_parameters`；三个不同模型/多次尝试都定位到同一个源文件
  （napoleon numpy 参数解析），说明问题定位稳定，但这一档模型修不对。
- kimi-k3、deepseek-v4-pro、deepseek-v4-1-flash 均一次解决。
- 因此 8056 不是题目无解、也不是 mini-swe-agent 框架缺陷，而是**模型档位的真实能力分水岭**，
  可作为后续筛选模型的高区分度探针。

### 3.2 8638 是"能力边界 + 采样噪声题"

- 所有模型最终都能解决；doubao-lite 首次失败（100 步）、第二次成功（133 步）。
- 同配置下一次败一次胜，证明**单次 resolved 结果对处于能力边界的题目存在随机波动**。

### 3.3 对基线 60% 的含义

- n=50 时单题权重 2%，8638 这类边界题的随机性意味着基线 resolved 率有约 ±3–5 个百分点的采样误差。
- 消融/换模型实验差异不足 2–3 题（4–6pp）时不宜下结论；关键实验建议跑 2–3 次取均值或报区间。
- 失败至少分两类：努力/运气型（8638，多探索/重试可越过，对加步数、best-of-N、强模型敏感）
  与能力/理解型（8056，需要真正更强的模型）。

### 3.4 deepseek-v4-1-flash-economy 不可用于 agent 场景

- curl 小请求正常（2–4s、能发工具调用），但在 mini-swe-agent 真实负载
  （长 system prompt + 工具历史 + 大 max_tokens + 深度推理）下单次请求长时间挂起、几十分钟不返回。
- w=2 启动还触发服务端 `System protection triggered by request burst` 突发流量保护，指数退避空转。
- 已验证 w=2、w=1、swebench_single 前台均卡死。对照普通 `deepseek-v4-1-flash` 21/31 步正常完成。
- **economy 档的排队/限速不适合多轮长上下文 agent，后续实验不要使用。**

## 4. 模型效率（仅这 2 题，样本极小，不外推全量结论）

在两个都成功的模型中：
- deepseek-v4-1-flash 总步数 52（21+31），最少；
- kimi-k3 总步数 97（43+54）；
- deepseek-v4-pro 总步数 117（42+75）；
- glm-5.3 总步数 150（84+66），且 8056 未解。

## 5. 复现实验方式

强模型复测统一采用"直连火山端点 + 本地数据集"（见 5.2 原因）：

```bash
cd /path/to/mini-swe-agent
docker ps -a --filter name=minisweagent- -q | xargs -r docker rm -f
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY MSWEA_COST_TRACKING=ignore_errors \
uv run python -m minisweagent.run.benchmarks.swebench \
  --subset data/swe-bench-verified-mini --split test \
  --filter '^sphinx-doc__sphinx-(8056|8638)$' \
  -m "openai/<MODEL_ID>" \
  -c swebench.yaml -c agent.mode=yolo -w 2 \
  -o experiments/runs/strong_<model>

# 验证（harness 用 HF 新 schema 数据集，需代理；纯本地不耗模型额度）
HTTP_PROXY=<你的代理> HTTPS_PROXY=<你的代理> \
uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/strong_<model>/preds.json \
  --max_workers 2 -id <run_id> --report_dir experiments/runs/strong_<model>/report
```

### 5.1 环境踩坑（务必沿用）

1. **同一时刻只能跑一个 swebench 批量任务**：各脚本启动时执行全局
   `docker rm -f minisweagent-*`，容器名无任务前缀，两个批量会互相杀容器。
2. **火山 API 直连、HF 数据集走代理**：socks 代理线路会让部分模型（kimi-k3、economy 等）报
   Connection error；解决方案是 unset 代理 + `--subset data/swe-bench-verified-mini` 用本地数据集。
   harness 验证阶段才需要代理（从 HF 加载 `SWE-bench/SWE-bench_Verified`，已缓存）。
3. Coding Plan 有 5 小时滚动配额（`AccountQuotaExceeded`）与瞬时突发保护，批量默认 w=2，economy 类档位需 w=1。

## 6. 待办

- [ ] doubao-seed-2-1-pro / doubao-seed-evolving 复测这两题（与 lite 同厂商档位对比）。
- [ ] 恢复实验 B：doubao-lite 重跑剩余 17 个 unresolved（脚本需改成直连 + 本地 subset），统计"重跑救回率"。
- [ ] 用 deepseek-v4-1-flash 或 kimi-k3 全量跑 50 题，与 doubao-lite 的 60% 基线正面对比。
