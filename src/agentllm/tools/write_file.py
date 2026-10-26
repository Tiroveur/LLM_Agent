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
            content = content.replace("\u00a0", " ").replace("\xa0", " ")
            content = content.replace("\r\n", "\n").replace("\r", "\n")

            if "\\n" in content and content.count("\n") < content.count("\\n"):
                content = content.replace("\\n", "\n")
            if "\\t" in content:
                content = content.replace("\\t", "\t")

            if file_path.endswith(".py"):
                content = re.sub(r"^#!.*\n?", "", content)

        if not file_path.startswith("/"):
            file_path = os.path.join("/tmp", file_path)
        elif not file_path.startswith("/tmp/"):
            file_path = os.path.join("/tmp", os.path.basename(file_path))

        is_script = file_path.endswith(".sh")
        is_destructive_content = bool(re.search(r"\brm\b", content)) or "mkfs" in content

        if is_script or is_destructive_content:
            print("\n" + "=" * 60)
            print("[ALERTE SECURITE] L'agent souhaite ecrire un fichier critique ou un script bash :")
            print(f"-> Fichier : {file_path}")
            print(f"-> Contenu :\n{content}")
            print("=" * 60)

            choice = (
                input("Voulez-vous autoriser l'ecriture de ce fichier ? (yes/no) : ")
                .strip()
                .lower()
            )

            if choice not in ["o", "oui", "y", "yes"]:
                logger.warning("Ecriture de fichier bloquee par l'utilisateur : %s", file_path)
                return (
                    "Error writing file (exit code 1): "
                    "Action annulee et bloquee par l'utilisateur (validation de securite refusee)."
                )

        logger.info(
            "Tentative d'écriture dans le fichier sandbox : %s (%d caractères)",
            file_path,
            len(content),
        )

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
            logger.info("Fichier écrit avec succès : %s", file_path)
            return f"Successfully wrote file to {file_path}"

        logger.error(
            "Échec de l'écriture pour %s (code de sortie %s) : %s",
            file_path,
            exit_code,
            output.strip(),
        )
        return f"Error writing file (exit code {exit_code}): {output}"

    return write_file