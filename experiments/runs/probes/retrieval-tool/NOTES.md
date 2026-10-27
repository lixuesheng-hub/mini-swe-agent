# 工具版消融：doubao-lite + 注册 github_fetch 工具（原提示词不变）

日期：2026-10-22
假设：把"GitHub 上游检索"做成一个显式工具（而非在提示词里提示），弱模型是否会自发使用并翻盘。
与 prompt 版（`probes/retrieval-prompt`）互为对照：本题唯一变量是工具/提示，模型与其它配置完全相同。

## 实现（可扩展的工具注册表）

源码改动（默认行为不变，`model.extra_tools` 默认空 = bash only，与基线逐字节一致）：

- `src/minisweagent/models/utils/actions_toolcall.py`
  - 新增 `EXTRA_TOOLS` 注册表：`name -> (OpenAI function spec, args -> bash command)`；
  - 新增 `get_enabled_tools(names)`（bash 始终在内）；
  - `parse_toolcall_actions(..., extra_tool_names=...)` 把已注册额外工具的参数翻译成一条
    在同一容器里执行的 curl 命令，复用 bash 执行/观察链路，未知工具仍报错。
  - **以后加工具只需写 spec + `to_command` 并在 `EXTRA_TOOLS` 登记，无需改其它代码。**
- `src/minisweagent/models/litellm_model.py`
  - `LitellmModelConfig` 新增 `extra_tools: list[str] = []`；`_query` 按开关注册工具。
- 开关：`experiments/verified_mini_baseline/enable_github_tool.yaml`（`model.extra_tools: [github_fetch]`）。
- 工具：`github_fetch(repo, resource∈{issue_comments,issue_timeline,pull,pull_files}, number)`，
  内部执行 `curl -sL https://api.github.com/repos/<repo>/<path>?per_page=100 | head -c 12000`。
- 提示词：仍用原始 `swebench.yaml`，**没有任何联网/检索提示**——模型只能靠工具自带的 name/description 发现它。
- 测试：`tests/models/test_actions_toolcall.py`、`test_litellm_model.py` 共 20 项通过。

## 结果

| 实例 | 基线 | prompt 版(webhint) | **工具版(github_fetch)** | 工具使用 |
|---|---|---|---|---|
| sphinx-8056 | ❌（两次） | ✅ 21步 | **✅ 55步** | github_fetch 4 次，bash 59 次 |
| sphinx-8638 | ❌→✅ | ✅ 96步 | **❌ 98步** | **github_fetch 0 次**（模型完全没用新工具） |

harness：8056 F2P 1/1、0 回归；8638 F2P 0/1、0 回归。
报告：`report/openai__doubao-seed-2-1-lite-260915.lite_githubtool.json`。

## 结论

1. **工具版有效但不如 prompt 版稳定**：在 8056 上模型靠工具描述自发学会用 github_fetch 并成功，
   证明"加显式工具"路线成立；但在 8638 上模型**根本没调用新工具**（0 次），仍按纯 bash 老路子走而失败。
2. **工具需要被"发现"**：工具 schema 只在模型主动选择时出现，弱模型倾向于只用最熟悉的 bash；
   prompt 版因为有明确指令，两题都去检索了（2/2）。→ 显式引导比单纯提供工具更可靠。
3. **最佳实践**：工具 + 一句提示组合最稳（工具负责正确/省事的调用，提示负责触发使用）。
4. 单题随机性仍在：8638 在基线第二次、prompt 版都成功，工具版失败，再次印证 n=50 需多次重复。

## 三版对照（doubao-seed-2-1-lite，同框架，仅改检索能力的呈现方式）

| 变体 | 8056 | 8638 | 检索呈现 |
|---|:---:|:---:|---|
| 基线 | ❌ | ❌→✅ | 无 |
| prompt 版 | ✅ | ✅ | 提示里教用 curl |
| 工具版 | ✅ | ❌ | 独立 github_fetch 工具，无提示 |
