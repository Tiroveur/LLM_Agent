"""Entry point for the autonomous AI agent."""

import argparse
from agentllm.sandbox import DockerSandbox
from agentllm.agent import AutonomousAgent


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

    sandbox = DockerSandbox(container_name=args.container)
    
    # On passe la limite max_steps à l'agent s'il l'accepte dans son __init__ 
    # (ou on l'ajuste selon la signature de ton AutonomousAgent)
    agent = AutonomousAgent(sandbox=sandbox)

    while True:
        try:
            user_task = input("\nQue souhaitez-vous faire ? (exit pour quitter) : ")
        except (KeyboardInterrupt, EOFError):
            print("\nAu revoir !")
            break

        if user_task.lower().replace(" ", "") in ["exit", "quit"]:
            break
        
        if user_task.strip():
            agent.run(user_task,max_steps=args.max_steps)


if __name__ == "__main__":
    main()