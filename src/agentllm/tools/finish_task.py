from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)

def get_finish_task_tool(sandbox):
    @tool
    def finish_task(summary: str) -> str:
        """Call this tool when you have successfully completed the task, found all requested flags, or finished your investigation.
        
        Args:
            summary: A detailed summary of your investigations, steps taken, and final results/flags found.
        """
        logger.info(f"Tâche terminée avec succès par l'agent. Résumé : {summary}")
        return f"TASK_COMPLETED_SUCCESSFULLY: {summary}"
        
    return finish_task