"""Module defining standalone tools (plugins) available to the autonomous agent."""

from langchain_core.tools import tool
from agentllm.sandbox import DockerSandbox
import base64

def create_agent_tools(sandbox: DockerSandbox) -> list:
    """Factory function that creates tools bound to a specific Docker sandbox instance."""

    @tool
    def write_file(file_path: str, content: str) -> str:
        """Writes text content to a file inside the sandbox container safely using Base64 for path and content.
        
        Args:
            file_path: The absolute path inside the container (e.g., '/tmp/hello.py').
            content: The exact text content to write into the file.
        """
        encoded_path = base64.b64encode(file_path.encode("utf-8")).decode("utf-8")
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        # Aucun guillemet nécessaire pour les données grâce au décodage Base64 à la volée
        cmd = (
            "python3 -c \""
            "import base64, pathlib; "
            f"pathlib.Path(base64.b64decode('{encoded_path}').decode('utf-8'))"
            f".write_bytes(base64.b64decode('{encoded_content}'))"
            "\""
        )
        
        exit_code, output = sandbox.execute(cmd)
        if exit_code == 0:
            return f"Successfully wrote file to {file_path}"
        return f"Error writing file (exit code {exit_code}): {output}"

    @tool
    def run_bash(command: str) -> str:
        """Executes a bash command inside the sandbox container.
        
        Args:
            command: The bash command line to run.
        """
        exit_code, output = sandbox.execute(command)
        return f"Exit code: {exit_code}\nOutput:\n{output}"

    return [write_file, run_bash]