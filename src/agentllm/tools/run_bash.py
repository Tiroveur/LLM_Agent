import logging
from langchain_core.tools import tool
from agentllm.tools.securite import check_command

logger = logging.getLogger(__name__)

def get_run_bash_tool(sandbox):
    @tool
    def run_bash(command: str) -> str:
        """Execute a bash command inside the sandbox container.

        Args:
            command: The bash command line to run.
        """
        refusal = check_command(sandbox, command)
        if refusal:
            return f"Exit code: 1\nOutput:\n{refusal}"

        logger.info("Exécution de la commande bash : %s", command)
        exit_code, output = sandbox.execute(command)

        if exit_code == 0:
            logger.info("Commande exécutée avec succès (code 0)")
        else:
            logger.error(
                "Commande terminée avec un code de sortie non nul (%s) : %s",
                exit_code,
                output.strip(),
            )
        return f"Exit code: {exit_code}\nOutput:\n{output}"

    return run_bash