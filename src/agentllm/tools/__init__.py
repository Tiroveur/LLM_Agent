from .write_file import get_write_file_tool
from .edit_file import get_edit_file_tool
from .extract_archive import get_extract_archive_tool
from .run_bash import get_run_bash_tool
from .finish_task import get_finish_task_tool

def create_agent_tools(sandbox) -> list:
    """Factory function that collects and binds all tools to the sandbox."""
    return [
        get_write_file_tool(sandbox),
        get_edit_file_tool(sandbox),
        get_extract_archive_tool(sandbox),
        get_run_bash_tool(sandbox),
        get_finish_task_tool(sandbox),
    ]