# 实验：submit gate 小样本冒烟（4 题）

**假设**：提交前 gate（worktree 复现 + 重跑模型自己跑过的测试）能拦住"早提交型"失败（8269/8475），
且不误伤已能通过的题（8056/8638）。
**唯一变量**：在 `swebench_webhint.yaml` 之上开启 `enable_submit_gate.yaml`（GatedAgent + GatedDockerEnvironment）。
**样本**：4 题 = 8269/8475（基线 & 提示词版均失败、十几步提交）+ 8056/8638（提示词版稳定通过，作为误伤对照）。

## 结果（harness 判分）

| 实例 | baseline | prompt rep1 | prompt rep2 | **gate** | gate 步数 | 被拦次数 |
|---|:---:|:---:|:---:|:---:|---:|---:|
| sphinx-8269 | ✗ | ✗ | ✗ | ✗ | 43 | 2 |
| sphinx-8475 | ✗ | ✗ | ✗ | ✗ | 40 | 2 |
| sphinx-8056 | ✗ | ✓ | ✓ | **✓** | 50 | 2 |
| sphinx-8638 | ✗ | ✓ | ✓ | **✓** | 33 | 2 |

## 发现（含一次真实 bug 修复）

1. **首轮冒烟完全没触发 gate**（两处 bug，已修）：
   - 提交命令实际是 `cd /testbed && echo COMPLETE... && cat patch.txt`，前缀绕过了我的字符串匹配；
   - 批量 runner 硬编码 `ProgressTrackingAgent(DefaultAgent)`，忽略配置里的 `agent_class`，
     导致 `GatedAgent` 从未生效 → 测试目标列表永远是空的。已改为 `make_progress_tracking_agent(base_class)` 工厂。
2. **第二轮冒烟全部被拦 2 次，但拒绝原因全是 `timeout`**（第二个真 bug）：
   模型先跑整个 `tests/test_build_linkcheck.py`（网络型测试，>300s），再跑具体 node；
   我的 coarsening 规则保留了文件级目标 → gate 每次重跑整文件 → 300s 超时 → 假拒绝 → 3 次用尽放行，
   实际等于"gate 什么也没验证"。修复：**同文件既有文件级又有 node 级目标时，只保留 node 级**
   （node 才是模型最后的精确验证意图）。修复后拒绝原因变为真实的 `own_tests FAIL`。
3. **gate 对目标案例无效**：8269/8475 在被拦 2 次、多修 20 步后仍失败。说明这两题**不是**"急着交卷"型
   （基线 19/14 步就提交，但补丁本身确实是错的），而是能力型/理解型失败。
   早提交只是表象，不是这些题的失败原因。→ 原 TODO T2 假设需要修正。
4. **无回归伤害**：8056/8638 仍通过（8056 步数 26→50，成本明显上升）。

## 结论

- gate 实现可用、默认关闭、失败打回机制正常（3 次上限生效，无死循环）。
- 但"gate 能修早提交型失败"的假设在**这两个目标案例上被证伪**；需全量数据判断净效果
  （可能的价值：减少 PASS_TO_PASS 回归、让部分"半对"补丁改进后转正）。
- 成本：每个发生过拒绝的实例多 15–25 步。

## 踩坑

- 冒烟脚本 `--filter` 用的是 `re.match`（从头匹配），需写完整前缀 `sphinx-doc__sphinx-(...)`；
  `-i` 不是批量入口的参数（那是 single 脚本的），批量要用 `--filter`。
- 自定义环境以 dotted path 给定时，`get_sb_environment` 不会注入 `image`；已改为按基类
  （DockerEnvironment / SingularityEnvironment）推断，通用且不特殊点名 gate。
