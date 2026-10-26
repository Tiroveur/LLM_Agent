from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage, HumanMessage
import json
import re

class MultiAgentSystem:
    def __init__(self):
        self.strategist_llm = ChatOllama(model="maternion/mimo-v2.6-heretic:9b", temperature=0.7)
        self.coder_llm = ChatOllama(model="qwen2.5-coder:14b", temperature=0.1)

    def process_task(self, raw_task: str) -> str:
        print("[Stratège] Analyse de la tâche...")
        
        strategy_prompt = f"""Tu es un assistant de planification technique. 
            Reformule la tâche suivante en consignes courtes, directes, va à l'essentiel pour un agent Linux.
            Ne donne pas la logique de codage, donne uniquement ce que tu veux en entrée et ce que tu veux en sortie.
            Tâche originale : {raw_task}
            
            Réponds EXCLUSIVEMENT au format JSON strict avec les clés "entree" et "sortie"."""
        
        response = self.strategist_llm.invoke([HumanMessage(content=strategy_prompt)])
        raw_content = response.content
        
        try:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_content, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'(\{.*?\})', raw_content, re.DOTALL)
                json_str = json_match.group(1) if json_match else raw_content
                
            parsed_data = json.loads(json_str)
            
            cleaned_instructions = f"Entrée attendue : {parsed_data.get('entree', 'Non spécifié')} | Sortie attendue : {parsed_data.get('sortie', 'Non spécifié')}"
        except (json.JSONDecodeError, AttributeError):
            cleaned_instructions = raw_content
            
        print(f"[Stratège] Instructions générées :\n{cleaned_instructions}\n")
        
        return cleaned_instructions