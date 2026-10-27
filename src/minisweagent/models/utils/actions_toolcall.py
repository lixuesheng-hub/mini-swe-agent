"""Parse actions & format observations with toolcalls"""

import json
import time

from jinja2 import StrictUndefined, Template

from minisweagent.exceptions import FormatError
from minisweagent.models.utils.openai_multimodal import expand_multimodal_content

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute a bash command",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute",
                }
            },
            "required": ["command"],
        },
    },
}


# ---------------------------------------------------------------------------
# Tool registry
#
# ``bash`` is the built-in, always-available tool that runs a command in the
# environment. Optional tools are registered in ``EXTRA_TOOLS`` and enabled by
# name via model config (``model.extra_tools=[...]``). Every optional tool is
# executed by translating its validated arguments into a single bash command
# (``to_command``), so the environment/execution path stays unchanged.
#
# To add a new tool: define the OpenAI function spec and a to_command(args)
# translator, then register it in EXTRA_TOOLS. No other code changes needed.
# ---------------------------------------------------------------------------

GITHUB_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "github_fetch",
        "description": (
            "Fetch public GitHub REST API JSON for a repository. Use this to inspect an issue's "
            "comments/timeline or a pull request and its changed files when the task is a real "
            "open-source issue and an upstream discussion/fix may already exist. Output is "
            "truncated to about 12k characters."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repository as owner/name, e.g. sphinx-doc/sphinx",
                },
                "resource": {
                    "type": "string",
                    "enum": ["issue_comments", "issue_timeline", "pull", "pull_files"],
                    "description": "What to fetch for the given issue/PR number.",
                },
                "number": {"type": "integer", "description": "Issue or pull request number"},
            },
            "required": ["repo", "resource", "number"],
        },
    },
}

_GITHUB_FETCH_PATHS = {
    "issue_comments": "issues/{number}/comments",
    "issue_timeline": "issues/{number}/timeline",
    "pull": "pulls/{number}",
    "pull_files": "pulls/{number}/files",
}


def github_fetch_args_to_command(args: dict) -> str:
    """Translate validated github_fetch arguments into a curl command run in the container."""
    repo = args["repo"]
    resource = args["resource"]
    number = int(args["number"])
    if "/" not in repo:
        raise ValueError("repo must be in owner/name form")
    if resource not in _GITHUB_FETCH_PATHS:
        raise ValueError(f"unknown resource '{resource}'")
    path = _GITHUB_FETCH_PATHS[resource].format(number=number)
    url = f"https://api.github.com/repos/{repo}/{path}?per_page=100"
    return f"curl -sL --max-time 20 '{url}' | head -c 12000"


# name -> (OpenAI function spec, args -> bash command)
EXTRA_TOOLS: dict[str, tuple[dict, callable]] = {
    "github_fetch": (GITHUB_FETCH_TOOL, github_fetch_args_to_command),
}


def get_enabled_tools(extra_tool_names: list[str] | None) -> list[dict]:
    """Return the tool specs advertised to the LLM (bash always first)."""
    tools = [BASH_TOOL]
    for name in extra_tool_names or []:
        if name not in EXTRA_TOOLS:
            raise ValueError(f"Unknown extra tool '{name}', available: {sorted(EXTRA_TOOLS)}")
        tools.append(EXTRA_TOOLS[name][0])
    return tools


def parse_toolcall_actions(
    tool_calls: list,
    *,
    format_error_template: str,
    template_kwargs: dict | None = None,
    extra_tool_names: list[str] | None = None,
) -> list[dict]:
    """Parse tool calls from the response. Raises FormatError if unknown tool or invalid args.

    ``template_kwargs`` are extra variables exposed to ``format_error_template`` (e.g.
    ``{"finish_reason": ...}`` so a template can distinguish a real format mistake from a
    ``max_tokens`` truncation).
    """
    template_kwargs = template_kwargs or {}
    enabled_extras = {name: EXTRA_TOOLS[name][1] for name in (extra_tool_names or [])}
    if not tool_calls:
        raise FormatError(
            {
                "role": "user",
                "content": Template(format_error_template, undefined=StrictUndefined).render(
                    error="No tool calls found in the response. Every response MUST include at least one tool call.",
                    actions=[],
                    has_tool_calls=False,
                    **template_kwargs,
                ),
                "extra": {"interrupt_type": "FormatError"},
            }
        )
    actions = []
    for tool_call in tool_calls:
        error_msg = ""
        args = {}
        try:
            args = json.loads(tool_call.function.arguments)
        except Exception as e:
            error_msg = f"Error parsing tool call arguments: {e}."
        name = tool_call.function.name
        if name == "bash":
            if not isinstance(args, dict) or "command" not in args:
                error_msg += "Missing 'command' argument in bash tool call."
            command = args.get("command") if isinstance(args, dict) else None
        elif name in enabled_extras:
            try:
                command = enabled_extras[name](args)
            except Exception as e:
                error_msg += f"Invalid {name} arguments: {e}."
                command = None
        else:
            error_msg += f"Unknown tool '{name}'."
            command = None
        if error_msg:
            raise FormatError(
                {
                    "role": "user",
                    "content": Template(format_error_template, undefined=StrictUndefined).render(
                        actions=[], error=error_msg.strip(), has_tool_calls=True, **template_kwargs
                    ),
                    "extra": {"interrupt_type": "FormatError"},
                }
            )
        actions.append({"command": command, "tool_call_id": tool_call.id})
    return actions


def format_toolcall_observation_messages(
    *,
    actions: list[dict],
    outputs: list[dict],
    observation_template: str,
    template_vars: dict | None = None,
    multimodal_regex: str = "",
) -> list[dict]:
    """Format execution outputs into tool result messages."""
    not_executed = {"output": "", "returncode": -1, "exception_info": "action was not executed"}
    padded_outputs = outputs + [not_executed] * (len(actions) - len(outputs))
    results = []
    for action, output in zip(actions, padded_outputs):
        content = Template(observation_template, undefined=StrictUndefined).render(
            output=output, **(template_vars or {})
        )
        msg = {
            "content": content,
            "extra": {
                "raw_output": output.get("output", ""),
                "returncode": output.get("returncode"),
                "timestamp": time.time(),
                "exception_info": output.get("exception_info"),
                **output.get("extra", {}),
            },
        }
        if "tool_call_id" in action:
            msg["tool_call_id"] = action["tool_call_id"]
            msg["role"] = "tool"
        else:
            msg["role"] = "user"  # human issued commands
        if multimodal_regex:
            msg = expand_multimodal_content(msg, pattern=multimodal_regex)
        results.append(msg)
    return results
