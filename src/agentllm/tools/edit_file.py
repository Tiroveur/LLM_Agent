from langchain_core.tools import tool
import base64
import logging
import os

logger = logging.getLogger(__name__)

def get_edit_file_tool(sandbox):
    @tool
    def edit_file(file_path: str, search_str: str, replace_str: str) -> str:
        """Surgically edits an existing file by replacing a specific string (search_str) with a new string (replace_str) safely using Base64 encoding with sanitization.
        
        Args:
            file_path: The absolute path of the file inside the container.
            search_str: The exact text snippet to look for and replace.
            replace_str: The new text snippet to replace it with.
        """
        # 1. Nettoyage des espaces insécables et normalisation des retours à la ligne
        if search_str:
            search_str = search_str.replace("\u00a0", " ").replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
        if replace_str:
            replace_str = replace_str.replace("\u00a0", " ").replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")

        if not file_path.startswith("/"):
            file_path = os.path.join("/tmp", file_path)
        elif not file_path.startswith("/tmp/"):
            file_path = os.path.join("/tmp", os.path.basename(file_path))

        logger.info(f"Tentative d'édition du fichier sandbox : {file_path}")

        encoded_path = base64.b64encode(file_path.encode("utf-8")).decode("utf-8")
        encoded_search = base64.b64encode(search_str.encode("utf-8")).decode("utf-8")
        encoded_replace = base64.b64encode(replace_str.encode("utf-8")).decode("utf-8")
        
        cmd = (
            "python3 -c \""
            "import base64, pathlib, sys; "
            f"path = pathlib.Path(base64.b64decode('{encoded_path}').decode('utf-8')); "
            "content = path.read_text(encoding='utf-8', errors='replace').replace('\\u00a0', ' ').replace('\\xa0', ' ').replace('\\r\\n', '\\n'); "
            f"search = base64.b64decode('{encoded_search}').decode('utf-8'); "
            f"replace = base64.b64decode('{encoded_replace}').decode('utf-8'); "
            "if search not in content: "
            "    print('ERROR: search_str not found in file'); "
            "    sys.exit(1); "
            "new_content = content.replace(search, replace); "
            "path.write_text(new_content, encoding='utf-8'); "
            "print('SUCCESS'); "
            "\""
        )
        
        exit_code, output = sandbox.execute(cmd)
        if exit_code == 0 and "SUCCESS" in output:
            logger.info(f"Fichier édité avec succès : {file_path}")
            return f"Successfully edited file {file_path}"
            
        logger.error(f"Échec de l'édition pour {file_path} (code de sortie {exit_code}) : {output.strip()}")
        return f"Error editing file (exit code {exit_code}): {output}"
        
    return edit_file