from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)

def get_run_bash_tool(sandbox):
    @tool
    def run_bash(command: str) -> str:
        """Executes a bash command inside the sandbox container.
        
        Args:
            command: The bash command line to run.
        """
        logger.info(f"Exécution de la commande bash : {command}")
        
        exit_code, output = sandbox.execute(command)
        
        if exit_code == 0:
            logger.info(f"Commande exécutée avec succès (code 0)")
            return f"Exit code: {exit_code}\nOutput:\n{output}"
            
        logger.error(f"Commande terminée avec un code de sortie non nul ({exit_code}) : {output.strip()}")
        return f"Exit code: {exit_code}\nOutput:\n{output}"
        
    return run_bash