"""Module responsible for managing the autonomous agent logic using native tool binding."""

from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from agentllm.sandbox import DockerSandbox
from agentllm.tools import create_agent_tools


SYSTEM_PROMPT = """You are an autonomous Linux execution agent operating in an Ubuntu sandbox container.
Your objective is to complete the user task successfully.

EXECUTION RULES:
1. The shared host directory is '/mnt/shared' in READ-ONLY mode. Always copy files to '/tmp' to modify them.
2. If you need to create a script or a file, use the 'write_file' tool instead of complex bash commands.
3. If a package is missing, install it via bash using 'DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y <package>'.
4. Analyze outputs carefully at each step before concluding.
"""

class AutonomousAgent:
    """Agent orchestrating the tool-use loop between the LLM and the Docker sandbox."""

    def __init__(self, sandbox: DockerSandbox, model_name: str = "maternion/mimo-v2.6-heretic:9b") -> None:
        self.sandbox = sandbox
        self.tools_list = create_agent_tools(sandbox)
        self.llm = ChatOllama(
            model=model_name,
            temperature=0.1,
            num_ctx=16384,
            base_url="http://localhost:11434"
        ).bind_tools(self.tools_list)

        self.tool_map = {tool.name: tool for tool in self.tools_list}

    def run(self, task: str, max_steps: int = 15) -> None:
        """Executes the autonomous tool-use loop for a given task."""
        print(f"\nSTARTING TASK: {task}\n" + "=" * 50)

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Task to accomplish: {task}")
        ]

        step = 1
        while step <= max_steps:
            print(f"\n--- STEP {step}/{max_steps} ---")
            print("Reasoning & Decision...", flush=True)

            try:
                response = self.llm.invoke(messages)
            except Exception as error:
                print(f"Model invocation error: {error}")
                break

            # Affichage de la pensée du modèle si elle existe
            if response.content:
                print(f"Thought: {response.content}")

            messages.append(response)

            # Si le modèle ne demande l'appel d'aucun outil, la tâche est finie ou bloquée
            if not response.tool_calls:
                print("\nTASK COMPLETED OR STOPPED (No tool called).")
                break

            # Exécution des outils demandés par le modèle
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                print(f"Tool Call : {tool_name}")
                print(f"Arguments : {tool_args}")

                if tool_name in self.tool_map:
                    try:
                        # Exécution de la fonction Python associée à l'outil
                        tool_result = self.tool_map[tool_name].invoke(tool_args)
                    except Exception as error:
                        tool_result = f"Error executing tool {tool_name}: {error}"
                else:
                    tool_result = f"Error: Tool '{tool_name}' not found."

                print(f"Result    :\n{tool_result}")

                # On renvoie le résultat de l'outil sous forme de message d'outil
                messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))

            step += 1