# 实验记录：unresolved 重跑与强模型复测（doubao-lite 基线）

创建：2026-10-22

## 背景与目的

基线（doubao-seed-2-1-lite-260915 + mini-swe-agent 默认配置）resolved 30/50=60%。
对 20 个 unresolved 做同配置重跑，用于区分失败类型并估计单次 resolved 的随机噪声：

- **努力/运气型**：重跑能过 → 基线 60% 有采样噪声，对加步数/best-of-N/强模型敏感；
- **能力/理解型**：重跑仍败 → 真正需要更强模型或方法改进。

## 实验 A：2 个最难实例重跑（已完成，2026-10-22）

- 目录：`experiments/runs/rerun_2hard_w2/`，结论详见该目录 `NOTES.md`
- 对象：sphinx-8638、sphinx-8056，同模型同配置 w=2
- 结果：
  - **sphinx-8638：失败 → 第二次 ✅ resolved**（100 步 vs 133 步），失败非必然
  - **sphinx-8056：两次均失败**（目标测试 0/1；第二次消除了 PASS_TO_PASS 回归），较稳定的能力型失败
- harness 报告：`rerun_2hard_w2/report/openai__doubao-seed-2-1-lite-260915.rerun2hard.json`

## 实验 B：其余 18 个 unresolved 重跑（进行中）

- 启动：2026-10-22 15:46，PID 记录于 console 启动时；w=2；目录 `experiments/runs/rerun_unresolved_w2/`
- 脚本：`experiments/verified_mini_baseline/rerun_unresolved.sh`（含 18 个 id 的 filter；断点续跑，撞 5 小时配额后重跑同一脚本即可）
- 对象：7 django（11848/11885/11964/12273/12308/12325/12406）+ 11 sphinx（10323/10435/10673/7590/7748/7985/8269/8475/8548/9230/9461）
- 验证命令（不耗模型额度）：

```bash
cd /path/to/mini-swe-agent
export HTTP_PROXY=<你的代理> HTTPS_PROXY=<你的代理> ALL_PROXY=<你的代理>
uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/rerun_unresolved_w2/preds.json \
  --max_workers 2 -id rerun_unresolved \
  --report_dir experiments/runs/rerun_unresolved_w2/report
```

- **完成后要补的分析**：统计 20 个 unresolved 的"重跑救回率"；按（基线结果 × 重跑结果）分四类：稳定成功/救回/随机失败/稳定失败；更新对 60% 基线随机误差的估计。

## 注意：不要同时跑两个 swebench 批量任务（2026-10-22 踩坑）

各任务脚本启动时执行 `docker rm -f minisweagent-*` 全局清理，而容器名没有任务前缀；
同时启动两个批量会互相杀掉对方的容器，被杀任务的线程挂在死容器上。
**同一时刻只允许一个 swebench 批量任务在跑**。实验 B 因此被中断（preds.json 尚未生成，无损失），
待强模型复测结束后用 `rerun_unresolved.sh` 重启即可（18 个全部重跑）。

## 强模型复测 8056/8638

### glm-5.3（2026-10-22 进行中）

- 目录：`experiments/runs/strong_glm-5.3/`，模型 `openai/glm-5.3`，w=2，同 swebench.yaml
- smoke：glm-5.3 在 Coding Plan 端点支持 function-calling（bash 工具调用已验证）
- 验证命令：

```bash
cd /path/to/mini-swe-agent
HTTP_PROXY=<你的代理> HTTPS_PROXY=<你的代理> ALL_PROXY=<你的代理> \
uv run python -m swebench.harness.run_evaluation \
  -d SWE-bench/SWE-bench_Verified -s test \
  -p experiments/runs/strong_glm-5.3/preds.json \
  --max_workers 2 -id strong_glm53 \
  --report_dir experiments/runs/strong_glm-5.3/report
```

### glm-5.3 结果（已完成，2026-10-22）

| 实例 | glm-5.3 | 测试明细 |
|---|---|---|
| sphinx-8638 | ✅ resolved（66 步） | F2P 1/1，P2P 0 回归 |
| sphinx-8056 | ❌ 失败（84 步） | F2P 0/1，P2P **1 回归** |

跨模型汇总：

| 实例 | lite 第1次 | lite 第2次 | glm-5.3 | 判定 |
|---|---|---|---|---|
| sphinx-8638 | 失败(100步) | ✅(133步) | ✅(66步，更省) | 边界型：两模型都能解，lite 首次失败是采样噪声 |
| sphinx-8056 | 失败(100步,1回归) | 失败(46步,0回归) | 失败(84步,1回归) | **稳定失败：两个模型 3 次运行全部没过同一目标测试**，疑为模型共性盲区/题目本身难，而非单模型能力问题 |

## 强模型横向复测汇总（8056 / 8638）

同框架（mini-swe-agent 默认配置、w=2、本地 mini 数据集），仅换模型，各跑一次 8056+8638 并用同一 harness 验证。

| 模型 | 8056 | 8638 | 8056 步数 | 8638 步数 |
|---|---|---|---:|---:|
| doubao-seed-2-1-lite（基线） | ❌（2/2 次均败，一次有回归） | ❌ 后 ✅ | 100 / 46 | 100 / 133 |
| glm-5.3 | ❌（1 回归） | ✅ | 84 | 66 |
| kimi-k3 | ✅ | ✅ | 43 | 54 |
| deepseek-v4-pro | ✅ | ✅ | 42 | 75 |
| deepseek-v4.1-flash | ✅ | ✅ | **21** | **31** |

结论：

1. **8056 是真实的能力分界题**：doubao-lite 两次、glm-5.3 一次全部失败（且都卡在同一目标测试 `test_multiple_parameters`），kimi-k3 / deepseek-v4 系列均解决 → 不是题目无解或框架问题，是模型档位差异。
2. **8638 是边界噪声题**：所有模型最终都能解决；doubao-lite 单次失败属采样波动。
3. deepseek-v4.1-flash 在这两题上步数最少（21/31），效率最高（样本仅 2 题，不外推全面结论）。
4. 环境要点：火山方舟 API 走 socks 代理会对部分模型报 Connection error，**强模型任务一律直连（unset 代理）+ `--subset data/swe-bench-verified-mini` 本地数据集**（HF 加载才需代理）。

### deepseek-v4-1-flash-economy（不可用，2026-10-22）

- curl 小请求正常（2–4s），但在 mini-swe-agent 真实负载（长 system prompt + 工具历史 + 大 max_tokens + 深度推理）下**单次请求长时间挂起、几十分钟不返回**；w=2 启动还触发服务端 `System protection triggered by request burst` 突发限流，空转重试。
- 已测 w=2、w=1、swebench_single 前台均卡死在某一步；目录 `experiments/runs/strong_deepseek-v4-1-flash-economy/` 无有效成果。
- 对照：普通 `deepseek-v4-1-flash`（非 economy）同两题 21/31 步正常 2/2。**结论：economy 档不适合 agent 多轮长上下文调用，后续实验不要用。**

## TODO

- [ ] doubao-seed-2-1-pro / doubao-seed-evolving 复测 8056/8638（同档位对比）
- [ ] 恢复实验 B（`rerun_unresolved.sh` 需改成 unset 代理 + 本地 subset）
- [ ] 用更强模型全量跑 50 题，与 60% 基线对比
