from langchain_core.tools import tool
import base64
import logging

logger = logging.getLogger(__name__)

def get_extract_archive_tool(sandbox):
    @tool
    def extract_archive(archive_path: str, extract_to: str) -> str:
        """Extracts an archive file (zip, tar, tar.gz, tgz, etc.) into a target directory inside the container.
        
        Args:
            archive_path: The absolute path of the archive file inside the container.
            extract_to: The absolute path of the destination directory where contents should be extracted.
        """

        logger.info(f"Tentative d'extraction de l'archive : {archive_path} vers {extract_to}")

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
            logger.info(f"Archive extraite avec succès : {archive_path}")
            return f"Successfully extracted {archive_path} to {extract_to}.\nOutput:\n{output}"
            
        logger.error(f"Échec de l'extraction pour {archive_path} (code de sortie {exit_code}) : {output.strip()}")
        return f"Error extracting archive (exit code {exit_code}): {output}"
        
    return extract_archive