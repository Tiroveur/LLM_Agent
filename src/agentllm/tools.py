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

    @tool
    def finish_task(summary: str) -> str:
        """Call this tool when you have successfully completed the task, found all requested flags, or finished your investigation.
        
        Args:
            summary: A detailed summary of your investigations, steps taken, and final results/flags found.
        """
        return f"TASK_COMPLETED_SUCCESSFULLY: {summary}"

    @tool
    def read_file(file_path: str, max_lines: int = 150) -> str:
        """Reads the content of a file inside the sandbox safely, with a line limit to protect context.
        
        Args:
            file_path: The absolute path of the file inside the container.
            max_lines: Maximum number of lines to read (default 150).
        """
        encoded_path = base64.b64encode(file_path.encode("utf-8")).decode("utf-8")
        cmd = (
            "python3 -c \""
            "import base64, pathlib; "
            f"path = pathlib.Path(base64.b64decode('{encoded_path}').decode('utf-8')); "
            "lines = path.read_text(errors='replace').splitlines(); "
            f"print('\n'.join(lines[:{max_lines}])); "
            "print(f'\n[Total lines: {{len(lines)}}]') if len(lines) > {max_lines} else None"
            "\""
        )
        exit_code, output = sandbox.execute(cmd)
        if exit_code == 0:
            return output
        return f"Error reading file (exit code {exit_code}): {output}"

    @tool
    def edit_file(file_path: str, search_str: str, replace_str: str) -> str:
        """Surgically edits an existing file by replacing a specific string (search_str) with a new string (replace_str) safely using Base64 encoding.
        
        Args:
            file_path: The absolute path of the file inside the container.
            search_str: The exact text snippet to look for and replace.
            replace_str: The new text snippet to replace it with.
        """
        encoded_path = base64.b64encode(file_path.encode("utf-8")).decode("utf-8")
        encoded_search = base64.b64encode(search_str.encode("utf-8")).decode("utf-8")
        encoded_replace = base64.b64encode(replace_str.encode("utf-8")).decode("utf-8")
        
        cmd = (
            "python3 -c \""
            "import base64, pathlib, sys; "
            f"path = pathlib.Path(base64.b64decode('{encoded_path}').decode('utf-8')); "
            "content = path.read_text(encoding='utf-8', errors='replace'); "
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
            return f"Successfully edited file {file_path}"
        return f"Error editing file (exit code {exit_code}): {output}"

    @tool
    def extract_archive(archive_path: str, extract_to: str) -> str:
        """Extracts an archive file (zip, tar, tar.gz, tgz, etc.) into a target directory inside the container.
        
        Args:
            archive_path: The absolute path of the archive file inside the container.
            extract_to: The absolute path of the destination directory where contents should be extracted.
        """
        encoded_archive = base64.b64encode(archive_path.encode("utf-8")).decode("utf-8")
        encoded_dest = base64.b64encode(extract_to.encode("utf-8")).decode("utf-8")
        
        cmd = (
            "python3 -c \""
            "import base64, pathlib, zipfile, tarfile; "
            f"archive = pathlib.Path(base64.b64decode('{encoded_archive}').decode('utf-8')); "
            f"dest = pathlib.Path(base64.b64decode('{encoded_dest}').decode('utf-8')); "
            "dest.mkdir(parents=True, exist_ok=True); "
            "if zipfile.is_zipfile(archive): "
            "    with zipfile.ZipFile(archive, 'r') as zf: "
            "        zf.extractall(dest); "
            "    print(f'SUCCESS: Extracted zip to {dest}'); "
            "elif tarfile.is_tarfile(archive): "
            "    with tarfile.open(archive, 'r:*') as tf: "
            "        tf.extractall(dest); "
            "    print(f'SUCCESS: Extracted tar to {dest}'); "
            "else: "
            "    print('ERROR: Unsupported or invalid archive format'); "
            "    exit(1); "
            "\""
        )
        
        exit_code, output = sandbox.execute(cmd)
        if exit_code == 0 and "SUCCESS" in output:
            return f"Successfully extracted {archive_path} to {extract_to}.\nOutput:\n{output}"
        return f"Error extracting archive (exit code {exit_code}): {output}"

    return [write_file, run_bash, finish_task, read_file, edit_file, extract_archive]