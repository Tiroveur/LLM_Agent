from langchain_core.tools import tool
import base64
import logging
import os
import re

logger = logging.getLogger(__name__)

def get_write_file_tool(sandbox):
    @tool
    def write_file(file_path: str, content: str) -> str:
        """Writes text content to a file inside the sandbox container safely using Base64 with sanitization."""

        if content:
            # Remplacement des espaces insécables (fréquents chez les LLMs) par des espaces standards
            content = content.replace("\u00a0", " ").replace("\xa0", " ")
            content = content.replace("\r\n", "\n").replace("\r", "\n")
            if file_path.endswith(".py"):
                content = re.sub(r'^#!.*\n?', '', content)

        # 2. Gestion propre du chemin
        if not file_path.startswith("/"):
            file_path = os.path.join("/tmp", file_path)
        elif not file_path.startswith("/tmp/"):
            file_path = os.path.join("/tmp", os.path.basename(file_path))

        logger.info(f"Tentative d'écriture dans le fichier sandbox : {file_path} ({len(content)} caractères)")
        
        encoded_path = base64.b64encode(file_path.encode("utf-8")).decode("utf-8")
        encoded_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        
        cmd = (
            "python3 -c \""
            "import base64, pathlib; "
            f"pathlib.Path(base64.b64decode('{encoded_path}').decode('utf-8'))"
            f".write_bytes(base64.b64decode('{encoded_content}'))"
            "\""
        )
        exit_code, output = sandbox.execute(cmd)
        if exit_code == 0:
            logger.info(f"Fichier écrit avec succès : {file_path}")
            return f"Successfully wrote file to {file_path}"
            
        logger.error(f"Échec de l'écriture pour {file_path} (code de sortie {exit_code}) : {output.strip()}")
        return f"Error writing file (exit code {exit_code}): {output}"
        
    return write_file