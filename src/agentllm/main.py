"""Entry point for the autonomous AI agent."""

import argparse
import logging

from agentllm.sandbox import DockerSandbox
from agentllm.agent import AutonomousAgent
from agentllm.multi_agent import MultiAgentSystem

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler()
    ]
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(
        description="Lance l'agent autonome dans un bac à sable Docker."
    )
    parser.add_argument(
        "--max-steps",
        "-m",
        type=int,
        default=15,
        help="Nombre maximum d'itérations (boucles) autorisées pour l'agent par tâche (défaut : 15).",
    )
    parser.add_argument(
        "--container",
        "-c",
        type=str,
        default="agent-sandbox",
        help="Nom du conteneur Docker à utiliser (défaut : agent-sandbox).",
    )
    args = parser.parse_args()

    print("Bienvenue dans l'agent autonome AutonomousAgent !")

    agent = None
    multi_agent = None

    while True:
        try:
            user_task = input("\nQue souhaitez-vous faire ? (exit pour quitter) : ")
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !")
            break

        if user_task.lower().replace(" ", "") in ["exit", "quit"]:
            break

        if user_task.strip():
            if agent is None:
                print("[Initialisation] Connexion au bac à sable Docker et chargement des modèles LLM...", flush=True)
                try:
                    sandbox = DockerSandbox(container_name=args.container)
                    agent = AutonomousAgent(sandbox=sandbox)
                    multi_agent = MultiAgentSystem()
                    print("[Initialisation] Prêt !\n")
                except Exception as e:
                    print(f"\n[Erreur d'initialisation] Impossible de démarrer l'agent ou Docker : {e}")
                    continue

            try:
                refined_task = multi_agent.process_task(user_task)
                multi_agent.supervised_run(agent, refined_task, max_rounds=3, max_steps=args.max_steps)
                
            except (KeyboardInterrupt, EOFError):
                print("\nArrêt de la tâche en cours.")
                continue


if __name__ == "__main__":
    main()