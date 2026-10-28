import base64
import logging
import posixpath
import re

from langchain_core.tools import tool
from agentllm.tools.securite import check_file

logger = logging.getLogger(__name__)


def get_write_file_tool(sandbox):
    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write text content to a file in the /tmp directory of the sandbox.

        Args:
            file_path: Absolute path starting with /tmp/ (e.g. /tmp/script.py).
            content: Full text content of the file.
        """
        content = (content or "").replace("\u00a0", " ").replace("\r\n", "\n").replace("\r", "\n")

        if "\n" not in content and "\\n" in content:
            content = content.replace("\\n", "\n").replace("\\t", "\t")

        if file_path.endswith(".py"):
            content = re.sub(r"^#!.*\n?", "", content)

        if not file_path.startswith("/"):
            file_path = posixpath.join("/tmp", file_path)
        file_path = posixpath.normpath(file_path)
        if not file_path.startswith("/tmp/"):
            file_path = posixpath.join("/tmp", posixpath.basename(file_path))

        refusal = check_file(file_path, content)
        if refusal:
            return f"Error writing file (exit code 1): {refusal}"

        logger.info("Écriture dans le sandbox : %s (%d caractères)", file_path, len(content))

        encoded_path = base64.b64encode(file_path.encode("utf-8")).decode("ascii")
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
        cmd = (
            'python3 -c "'
            "import base64, pathlib; "
            f"pathlib.Path(base64.b64decode('{encoded_path}').decode('utf-8'))"
            f".write_bytes(base64.b64decode('{encoded_content}'))"
            '"'
        )
        exit_code, output = sandbox.execute(cmd)
        if exit_code == 0:
            return f"Successfully wrote file to {file_path}"

        logger.error("Échec d'écriture %s (code %s) : %s", file_path, exit_code, output.strip())
        return f"Error writing file (exit code {exit_code}): {output}"

    return write_file