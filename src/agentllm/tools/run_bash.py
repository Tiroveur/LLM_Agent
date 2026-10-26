from langchain_core.tools import tool
import logging
import re

logger = logging.getLogger(__name__)

def get_run_bash_tool(sandbox):
    @tool
    def run_bash(command: str) -> str:
        """Executes a bash command inside the sandbox container.

        Args:
            command: The bash command line to run.
        """
        is_destructive = (
            bool(re.search(r"\brm\b", command))
            or "mkfs" in command
            or "dd if=" in command
        )

        if is_destructive:
            print("\n" + "=" * 60)
            print("[ALERTE SECURITE] L'agent souhaite executer une commande critique :")
            print(f"-> {command}")
            print("=" * 60)

            choice = (
                input("Voulez-vous autoriser l'execution de cette commande ? (yes/no) : ")
                .strip()
                .lower()
            )

            if choice not in ["o", "oui", "y", "yes"]:
                logger.warning("Commande bloquee par l'utilisateur : %s", command)
                return (
                    "Exit code: 1\nOutput:\nAction annulee et bloquee par "
                    "l'utilisateur (validation de securite refusee)."
                )

        logger.info("Execution de la commande bash : %s", command)

        exit_code, output = sandbox.execute(command)

        if exit_code == 0:
            logger.info("Commande executee avec succes (code 0)")
            return f"Exit code: {exit_code}\nOutput:\n{output}"

        logger.error(
            "Commande terminee avec un code de sortie non nul (%s) : %s",
            exit_code,
            output.strip(),
        )
        return f"Exit code: {exit_code}\nOutput:\n{output}"

    return run_bash