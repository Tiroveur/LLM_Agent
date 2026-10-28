"""Module responsible for managing the autonomous agent logic using native tool binding."""

import json
import logging
import re
import time
import uuid

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from agentllm.multi_agent import MODEL, NUM_CTX
from agentllm.sandbox import DockerSandbox
from agentllm.tools import create_agent_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert autonomous Linux execution agent operating in an Ubuntu sandbox container.
Your objective is to execute the provided technical instructions successfully using your available tools.

CRITICAL RULES FOR TOOL USAGE:
0. ONE STEP AT A TIME: Never generate multiple files or multiple code blocks in a single response. Perform one action (write one file or run one command), wait for the result, then proceed.
1. NEVER call `finish_task` on the first step. First create or modify the necessary files with `write_file` or `edit_file`, and verify them.
2. Always act through the provided tools (function calling). Never write JSON or code blocks in your message to simulate a tool call.
3. The shared host directory is `/mnt/shared` in READ-ONLY mode. Always copy files to `/tmp` to modify them.
4. If you need to create a script or a file, use `write_file` instead of bash commands.
5. If you need to edit an existing file surgically, use `edit_file`.
6. When you have completed the task and verified the output files, call `finish_task` with your final summary.
7. If a package is missing, install it via bash using `DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y <package>`.
8. When executing a Python script via bash, always invoke it explicitly using `python3 /tmp/script_name.py`.
9. NEVER rewrite a file that you have already created and tested, unless you modify it surgically with `edit_file`.
10. Never use shell expansion like `{a..z}{a..z}...` for large password lists. Write a compact Python script using `itertools` instead.

Programming languages: Shell, Python (environment managed with uv).
Never retry something that you already tried. Execute every program you create to be sure it works.
You can create files only in the /tmp directory."""

MAX_TOOL_OUTPUT_CHARS = 4000
MAX_NUDGES = 2


def _extract_tool_call(content: str, valid_names: set[str]) -> dict | None:
    """Récupère un appel d'outil écrit en JSON nu, en ```json ou dans <tool_call>."""
    if not content:
        return None

    cleaned = re.sub(r"</?tool_call>|```(?:json)?", "", content).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(0).replace(r"\'", "'"))
    except json.JSONDecodeError as error:
        logger.error("Erreur de décodage JSON sur le fallback : %s", error)
        return None

    name = data.get("name")
    args = data.get("arguments") or data.get("parameters")
    if name in valid_names and isinstance(args, dict):
        return {"name": name, "args": args, "id": uuid.uuid4().hex}
    return None


class AutonomousAgent:
    """Agent orchestrating the tool-use loop between the LLM and the Docker sandbox."""

    def __init__(self, sandbox: DockerSandbox, model_name: str = MODEL) -> None:
        self.sandbox = sandbox
        self.tools_list = create_agent_tools(sandbox)
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.1,
            num_ctx=NUM_CTX,
            reasoning=False,
            keep_alive="10m",
            base_url="http://localhost:11434",
        ).bind_tools(self.tools_list)

        self.tool_map = {tool.name: tool for tool in self.tools_list}

    def _invoke_llm_with_retry(self, messages: list, max_retries: int = 3, delay: int = 2):
        """Invoke the LLM in non-streaming mode with a retry mechanism."""
        for attempt in range(1, max_retries + 1):
            try:
                response = self.llm.invoke(messages)

                print("Thought: ", end="", flush=True)
                if response.content:
                    print(response.content, flush=True)
                else:
                    print("(No textual thought, direct tool call)", flush=True)

                return response

            except Exception as error:
                logger.error(
                    "Model invocation error (attempt %d/%d): %s", attempt, max_retries, error
                )
                if attempt == max_retries:
                    raise
                time.sleep(delay)

    def _execute_tools(self, response, messages: list, log: list[str]) -> str | None:
        """Execute the requested tools.

        Returns the final summary if finish_task was called, None otherwise.
        """
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]

            print(f"Tool Call: {tool_name}")
            print(f"Arguments: {tool_args}")

            if tool_name in self.tool_map:
                try:
                    tool_result = self.tool_map[tool_name].invoke(tool_args)
                except Exception as error:
                    tool_result = f"Error executing tool {tool_name}: {error}"
                    logger.error(tool_result)
            else:
                tool_result = f"Error: Tool '{tool_name}' not found."
                logger.error(tool_result)

            log.append(f"[{tool_name}] args={str(tool_args)[:300]} -> {str(tool_result)[:500]}")

            if tool_name == "finish_task":
                print(f"\n{tool_result}")
                return str(tool_result)

            print(f"Result:\n{tool_result}")
            print("-" * 50)
            messages.append(
                ToolMessage(content=str(tool_result)[:MAX_TOOL_OUTPUT_CHARS], tool_call_id=tool_id)
            )

        return None

    def _trim_messages_if_needed(self, messages: list, max_tokens_approx: int = 6000) -> list:
        """Truncate the history if it grows too large, without orphaning tool messages."""
        if sum(len(str(m.content)) for m in messages) <= max_tokens_approx * 4:
            return messages

        logger.warning("History too long, trimming intermediate messages...")
        head = messages[:2]
        tail = messages[2:][-6:]
        while tail and not isinstance(tail[0], AIMessage):
            tail = tail[1:]
        return head + tail

    def run(self, task: str, max_steps: int = 15, feedback: str | None = None) -> dict:
        """Execute the tool-use loop and return a report for the supervisor."""
        print(f"\nSTARTING TASK: {task}\n" + "=" * 50)

        prompt = f"Task to accomplish: {task}"
        if feedback:
            prompt += (
                "\n\nA supervisor reviewed your previous attempt and rejected it. "
                f"Fix these issues:\n{feedback}\n"
                "Files from the previous attempt may still exist in /tmp: check them before rewriting."
            )

        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        log: list[str] = []
        nudges = 0
        step = 1

        while step <= max_steps:
            print(f"\n--- STEP {step}/{max_steps} ---")
            messages = self._trim_messages_if_needed(messages)

            try:
                response = self._invoke_llm_with_retry(messages)
            except Exception as error:
                logger.error("Fatal LLM failure: %s", error)
                return {"finished": False, "summary": f"LLM failure: {error}", "log": log}

            text = response.content or ""

            if not response.tool_calls:
                fallback = _extract_tool_call(text, set(self.tool_map))
                if fallback:
                    response.tool_calls = [fallback]
                    print(f"[JSON Intercepté] Outil détecté : {fallback['name']}")

            if response.tool_calls:
                response.content = ""
            messages.append(response)

            if not response.tool_calls:
                if nudges < MAX_NUDGES:
                    nudges += 1
                    messages.append(
                        HumanMessage(
                            content="You must call one of the available tools. "
                            "Do not answer in plain text or raw JSON."
                        )
                    )
                    step += 1
                    continue
                return {
                    "finished": False,
                    "summary": f"Stopped without calling a tool. Last message: {text[:300]}",
                    "log": log,
                }

            summary = self._execute_tools(response, messages, log)
            if summary is not None:
                return {"finished": True, "summary": summary, "log": log}

            step += 1

        return {"finished": False, "summary": "Max steps reached without finish_task.", "log": log}