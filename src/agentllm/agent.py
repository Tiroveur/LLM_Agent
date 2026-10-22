"""Module responsible for managing the autonomous agent logic using native tool binding."""

import json
import logging
import re
import time

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_ollama import ChatOllama

from agentllm.sandbox import DockerSandbox
from agentllm.tools import create_agent_tools

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """{
  'role': 'system',
  'content': 'You are an expert autonomous Linux execution agent operating in an Ubuntu sandbox container.\nYour objective is to execute the provided technical instructions successfully using your available tools.\n\nCRITICAL RULES FOR TOOL USAGE:\n0. ONE STEP AT A TIME: Never generate multiple files or multiple code blocks in a single response. Perform one action (write one file or run one command), wait for the result, and then proceed to the next step.\n1. NEVER call `finish_task` on the first step. You must first create or modify the necessary files using `write_file` or `edit_file`, and verify them.\n2. Do not write code inside your text thoughts to simulate file creation. You MUST call the `write_file` tool natively.\n3. The shared host directory is `/mnt/shared` in READ-ONLY mode. Always copy files to `/tmp` to modify them.\n4. If you need to create a script or a file, use the `write_file` tool instead of bash commands.\n5. If you need to edit an existing file surgically, use the `edit_file` tool.\n6. When you have successfully completed the task and verified the output files, call the `finish_task` tool to provide your final summary.\n7. If a package is missing, install it via bash using `DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y <package>`.\n8. When executing a Python script via bash, always invoke it explicitly using `python3 /tmp/script_name.py`.\n9. NEVER rewrite a file that you have already successfully created and tested unless you are surgically modifying it with `edit_file`.\n10. Never use shell expansion like `{a..z}{a..z}...` for large password lists. Always write a compact Python script using `itertools` to handle combinatorial generation safely.\n\nProgramming language: Shell, Python. Always output a valid tool call in JSON. Environment possible thx to uv for python. \nNever retry something that you already tried. You will execute every program that you create to be sure that it`s working on the computer\nYou can create file only on /tmp directory"
}"""

class AutonomousAgent:
    """Agent orchestrating the tool-use loop between the LLM and the Docker sandbox."""

    def __init__(
        self,
        sandbox: DockerSandbox,
        model_name: str = "qwen2.5-coder",
    ) -> None:
        self.sandbox = sandbox
        self.tools_list = create_agent_tools(sandbox)
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.1,
            num_ctx=16384,
            base_url="http://localhost:11434",
        ).bind_tools(self.tools_list)

        self.tool_map = {tool.name: tool for tool in self.tools_list}

    def _invoke_llm_with_retry(
        self, messages: list, max_retries: int = 3, delay: int = 2
    ) -> object:
        """Invoke the LLM in streaming mode with a retry mechanism."""
        for attempt in range(1, max_retries + 1):
            try:
                stream = self.llm.stream(messages)

                accumulated_chunk = None
                has_content = False
                print("Thought: ", end="", flush=True)

                for chunk in stream:
                    if chunk.content:
                        print(chunk.content, end="", flush=True)
                        has_content = True

                    if accumulated_chunk is None:
                        accumulated_chunk = chunk
                    else:
                        accumulated_chunk += chunk

                if not has_content:
                    print("(No textual thought, direct tool call)", end="")
                print()
                return accumulated_chunk

            except Exception as error:
                logger.error(
                    "Model invocation error (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    error,
                )
                if attempt == max_retries:
                    raise error
                time.sleep(delay)
        return None

    def _execute_tools(self, response, messages: list) -> bool:
        """Execute tools requested by the model and update the message history.

        Returns True if the agent must stop (finish_task), False otherwise.
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

                    if tool_name == "finish_task":
                        print(f"\n{tool_result}")
                        return True

                except Exception as error:
                    tool_result = f"Error executing tool {tool_name}: {error}"
                    logger.error(tool_result)
            else:
                tool_result = f"Error: Tool '{tool_name}' not found."
                logger.error(tool_result)

            print(f"Result:\n{tool_result}")
            print("-" * 50)
            messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))

        return False

    def _trim_messages_if_needed(
        self, messages: list, max_tokens_approx: int = 14000
    ) -> list:
        """Check and truncate history if the message list becomes too large."""
        current_length = sum(len(str(m.content)) for m in messages)

        if current_length > (max_tokens_approx * 4):
            logger.warning("History too long, trimming intermediate messages...")
            system_msg = messages[0]
            user_msg = messages[1]
            recent_messages = messages[-6:]

            return [system_msg, user_msg] + recent_messages

        return messages

    def run(self, task: str, max_steps: int = 15) -> None:
        """Execute the autonomous tool-use loop for a given task."""
        print(f"\nSTARTING TASK: {task}\n" + "=" * 50)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Task to accomplish: {task}"),
        ]

        step = 1
        while step <= max_steps:
            print(f"\n--- STEP {step}/{max_steps} ---")

            messages = self._trim_messages_if_needed(messages)

            try:
                response = self._invoke_llm_with_retry(messages)
            except Exception as error:
                if "context window" in str(error).lower() or "exceeded" in str(error).lower():
                    logger.error("Context window overflow exceeded.")
                else:
                    logger.error("Fatal LLM failure: %s", error)
                break

            messages.append(response)

            # --- FILET DE SÉCURITÉ UNIFIÉ : EXTRACTION JSON ROBUSTE ---
            if not response.tool_calls and response.content:
                # Utilisation d'une regex multi-lignes plus souple pour capturer le JSON d'outil
                json_match = re.search(r'\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{.*?\}\s*\}', response.content, re.DOTALL)
                if json_match:
                    try:
                        # Nettoyage éventuel des retours à la ligne indésirables dans le texte brut
                        json_str = json_match.group(0)
                        tool_data = json.loads(json_str)
                        
                        response.tool_calls = [{
                            "name": tool_data["name"],
                            "args": tool_data["arguments"],
                            "id": "fallback_json_id"
                        }]
                        print(f"[JSON Intercepté] Outil détecté : {tool_data['name']}")
                    except json.JSONDecodeError as e:
                        logger.error("Erreur de décodage JSON sur le fallback : %s", e)
            # ---------------------------------------------------------------------------------

            if not response.tool_calls:
                print("\nTASK COMPLETED OR STOPPED (No tool called).")
                break

            should_finish = self._execute_tools(response, messages)
            if should_finish:
                return

            step += 1