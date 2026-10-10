import sys
import docker

class DockerSandbox:
    def __init__(self, container_name: str = "agent-sandbox"):
        self.client = docker.from_env()
        self.container_name = container_name
        self.container = self._get_container()

    def _get_container(self):
        try:
            return self.client.containers.get(self.container_name)
        except docker.errors.NotFound:
            print(f"Erreur : Le conteneur '{self.container_name}' n'a pas été trouvé.")
            sys.exit(1)

    def execute(self, command: str) -> tuple[int, str]:
        """Exécute une commande dans le conteneur avec DEBIAN_FRONTEND=noninteractive par sécurité."""
        exec_res = self.container.exec_run(["bash", "-c", command])
        exit_code = exec_res.exit_code
        output = exec_res.output.decode("utf-8", errors="ignore").strip()
        return exit_code, output if output else "(Aucune sortie)"