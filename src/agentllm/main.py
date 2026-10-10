import sys
import docker
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# 1. Initialisation du client Docker
docker_client = docker.from_env()
try:
    container = docker_client.containers.get("agent-sandbox")
except docker.errors.NotFound:
    print("Erreur: Le conteneur 'agent-sandbox' n'est pas démarré.")
    sys.exit(1)

# 2. Modèle de réponse structurée Pydantic
class AgentDecision(BaseModel):
    thought: str = Field(description="Explication de ton raisonnement et de l'état d'avancement de la tâche.")
    command: str = Field(description="La commande Bash exacte à exécuter dans la sandbox. Laisse vide si la tâche est terminée.")
    is_finished: bool = Field(description="Passe à True UNIQUEMENT quand la tâche globale demandée par l'utilisateur est totalement accomplie.")

# 3. Initialisation du LLM avec Structured Output
llm = ChatOllama(
    model="maternion/mimo-v2.6-heretic:9b",
    temperature=0,
    base_url="http://localhost:11434"
).with_structured_output(AgentDecision)

# 4. System Prompt orienté Autonomie
SYSTEM_PROMPT = """Tu es un agent autonome d'exécution Linux opérant dans un conteneur Ubuntu de sandbox.
Ton objectif est de mener à bien la tâche transmise par l'utilisateur, même si elle nécessite plusieurs étapes.

RÈGLES D'EXÉCUTION :
1. Le dossier partagé par l'hôte est situé dans '/mnt/shared' en LECTURE SEULE.
2. Si tu dois modifier ou traiter des fichiers de '/mnt/shared', COPIE-LES d'abord dans le répertoire courant ou dans '/tmp'.
3. Analyse attentivement la sortie des commandes précédentes (STDOUT/STDERR) :
   - Si une commande échoue, analyse l'erreur et propose une commande de correction.
   - Ne répète pas en boucle une commande qui a échoué sans modifier ton approche.
4. Génère des commandes non-interactives (ajoute -y pour apt, -p pour mkdir, etc.).
5. Lorsque la tâche globale est entièrement terminée, définis 'is_finished' à True et laisse 'command' vide.
"""

def execute_in_sandbox(cmd: str) -> tuple[int, str]:
    """Exécute la commande dans la sandbox Docker et renvoie le code de sortie et la sortie texte."""
    exec_res = container.exec_run(f"bash -c '{cmd}'")
    exit_code = exec_res.exit_code
    output = exec_res.output.decode("utf-8", errors="ignore").strip()
    return exit_code, output if output else "(Aucune sortie)"

def run_autonomous_agent(task: str, max_steps: int = 15):
    print(f"\n🚀 DÉMARRAGE DE LA TÂCHE AUTONOME : {task}\n" + "="*60)
    
    # Historique de la conversation pour maintenir le contexte multi-étapes
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Tâche à accomplir : {task}")
    ]
    
    step = 1
    while step <= max_steps:
        print(f"\n📍 --- ÉTAPE {step}/{max_steps} ---")
        
        try:
            # Appel au LLM
            decision: AgentDecision = llm.invoke(messages)
        except Exception as e:
            print(f"❌ Erreur lors de l'appel au LLM : {e}")
            break

        print(f"🧠 Réflexion : {decision.thought}")
        
        # Vérification si l'agent considère la tâche terminée
        if decision.is_finished:
            print("\n✅ TÂCHE TERMINÉE AVEC SUCCÈS PAR L'AGENT !")
            break
            
        if not decision.command:
            print("⚠️ Aucune commande fournie mais tâche marquée non terminée. Arrêt de sécurité.")
            break

        print(f"💻 Commande  : {decision.command}")
        
        # Exécution de la commande dans la sandbox
        exit_code, output = execute_in_sandbox(decision.command)
        print(f"📊 Exit Code : {exit_code}")
        print(f"📝 Sortie    :\n{output}")
        
        # Formatage du feedback pour le tour suivant
        step_feedback = (
            f"Commande exécutée : {decision.command}\n"
            f"Code de sortie : {exit_code}\n"
            f"Résultat :\n{output}"
        )
        
        # Mise à jour de l'historique LangChain
        messages.append(AIMessage(content=f"Pensée: {decision.thought}\nCommande: {decision.command}"))
        messages.append(HumanMessage(content=step_feedback))
        
        step += 1
        
    if step > max_steps:
        print("\n⚠️ Limite maximale d'étapes atteinte. La tâche a été interrompue par sécurité.")

if __name__ == "__main__":
    while True:
        user_task = input("\nEntrez une tâche autonome (ou 'exit' pour quitter) : ")
        if user_task.lower() in ["exit", "quit"]:
            break
        if user_task.strip():
            run_autonomous_agent(user_task)