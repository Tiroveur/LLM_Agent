import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

logger = logging.getLogger(__name__)

MODEL = "maternion/mimo-v2.6-heretic:9b"
NUM_CTX = 8192

REVIEW_PROMPT = """You are a strict reviewer supervising an autonomous Linux agent.
You receive the original request, the instructions given to the agent, its final summary
and a log of every tool call with its result.
Approve ONLY if the log shows evidence that the task was really done: files written,
commands executed with exit code 0, outputs actually checked. A claim in the summary
without proof in the log is not enough.
Reply with JSON only: {"approved": true or false, "feedback": "precise, actionable issues to fix, empty if approved"}"""


def _parse_json(raw: str) -> dict | None:
    """Parse du JSON, avec repli sur le plus grand bloc {...} du texte."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


class MultiAgentSystem:
    def __init__(self, model_name: str = MODEL) -> None:
        common = dict(
            model=model_name,
            num_ctx=NUM_CTX,
            reasoning=False,
            keep_alive="10m",
            base_url="http://localhost:11434",
        )
        self.strategist_llm = ChatOllama(temperature=0.3, format="json", **common)
        self.reviewer_llm = ChatOllama(temperature=0, format="json", **common)
        self.raw_task = ""

    def process_task(self, raw_task: str) -> str:
        print("[Stratège] Analyse de la tâche...")
        self.raw_task = raw_task

        strategy_prompt = f"""Tu es un assistant de planification technique.
            Reformule la tâche suivante en consignes courtes, directes, va à l'essentiel pour un agent Linux.
            Ne donne pas la logique de codage, donne uniquement ce que tu veux en entrée et ce que tu veux en sortie.
            Tâche originale : {raw_task}

            Réponds EXCLUSIVEMENT au format JSON strict avec les clés "entree" et "sortie"."""

        raw_content = self.strategist_llm.invoke([HumanMessage(content=strategy_prompt)]).content
        parsed = _parse_json(raw_content)

        if parsed:
            instructions = (
                f"Entrée attendue : {parsed.get('entree', 'Non spécifié')} | "
                f"Sortie attendue : {parsed.get('sortie', 'Non spécifié')}"
            )
        else:
            instructions = raw_content

        print(f"[Stratège] Instructions générées :\n{instructions}\n")
        return instructions

    def review(self, task: str, report: dict) -> dict:
        """Le superviseur juge le rapport de l'exécuteur."""
        if not report["finished"]:
            return {"approved": False, "feedback": report["summary"]}

        log_text = "\n".join(report["log"]) or "(empty log)"
        message = (
            f"ORIGINAL REQUEST:\n{self.raw_task}\n\nINSTRUCTIONS GIVEN TO THE AGENT:\n{task}\n\n"
            f"AGENT SUMMARY:\n{report['summary']}\n\nTOOL LOG:\n{log_text}"
        )
        try:
            raw = self.reviewer_llm.invoke(
                [SystemMessage(content=REVIEW_PROMPT), HumanMessage(content=message)]
            ).content
            verdict = _parse_json(raw)
            if verdict is None:
                raise ValueError(f"réponse non JSON : {raw[:200]}")
            return {
                "approved": bool(verdict.get("approved")),
                "feedback": str(verdict.get("feedback", "")),
            }
        except Exception as error:
            logger.error("Supervisor failure: %s", error)
            return {"approved": False, "feedback": f"Supervisor error: {error}"}

    def supervised_run(self, agent, task: str, max_rounds: int = 3, max_steps: int = 15) -> bool:
        feedback = None
        for round_number in range(1, max_rounds + 1):
            print(f"\n===== ROUND {round_number}/{max_rounds} =====")
            report = agent.run(task, max_steps=max_steps, feedback=feedback)
            verdict = self.review(task, report)

            if verdict["approved"]:
                print("\n[Superviseur] Tâche validée.")
                return True

            feedback = verdict["feedback"]
            print(f"\n[Superviseur] Refusé : {feedback}")

        print("\n[Superviseur] Nombre maximum de tours atteint sans validation.")
        return False