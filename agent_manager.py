import time
import uuid
import os
import re
import json
from utils import r, STREAM_KEY, publish_message, get_ai_response, build_smart_context

def save_artifacts(content, request_id):
    """
    Extrait et sauvegarde le code Python final.
    Cherche les blocs ```python ... ```
    """
    pattern = r"```python(.*?)```"
    matches = re.findall(pattern, content, re.DOTALL)
    saved_files = []
    
    if matches:
        if not os.path.exists("livrables"): 
            os.makedirs("livrables")
            
        for idx, code in enumerate(matches):
            # Nommage propre avec GUID partiel
            filename = f"livrables/projet_{request_id[:8]}_script_{idx+1}.py"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(code.strip())
            saved_files.append(filename)
            
    return saved_files

def decide_next_step(sender, content, request_id):
    """
    CERVEAU DU MANAGER : 
    Analyse le contexte global et décide de la prochaine action.
    Gère : Phases Projet + Questions Utilisateur.
    """
    
    # 1. Récupération de l'histoire complète (Résumé + Récents)
    smart_context = build_smart_context(request_id)
    
    # Détection de fin absolue (Reviewer valide)
    if sender == 'reviewer' and "VALIDATED" in content:
        return "FINISH", "Projet validé."

    # 2. Le Prompt Système qui définit les règles du jeu
    system_prompt = """
    Tu es le Manager Agile d'une équipe de développeurs IA autonomes.
    
    TES RESSOURCES :
    - @Analyst (Besoin)
    - @Architect (Technique)
    - @Coder (Code)
    - @Reviewer (Qualité)
    - @User (Le Client humain)

    RÈGLE D'OR - INTERACTION CLIENT :
    Si l'équipe est bloquée par un manque d'information (ex: choix de tech, API key manquante, règle métier floue), TU DOIS POSER LA QUESTION AU CLIENT.
    -> JSON : {"target": "@User", "instruction": "Votre question précise..."}

    LES PHASES DU PROJET (Guidées par le Contexte) :
    
    PHASE 1 : CONCEPTION (@Analyst + @Architect)
    - Ils doivent débattre. L'Analyste pose le besoin, l'Architecte valide la tech.
    - Tant qu'il n'y a pas d'accord explicite ("Plan validé", "D'accord"), relance le débat.
    
    PHASE 2 : DÉVELOPPEMENT (@Coder + @Analyst)
    - Le @Coder écrit le script.
    - Il peut poser des questions à l'@Analyst.
    
    PHASE 3 : REVIEW (@Reviewer)
    - Le @Reviewer valide ou rejette. Si rejet -> retour @Coder.

    TA DÉCISION (JSON STRICT) :
    Analyse le dernier message et le contexte. Qui doit parler maintenant ?
    {"target": "@Role", "instruction": "L'ordre ou la question à transmettre"}
    """

    user_prompt = f"""
    === CONTEXTE MÉMOIRE (RÉSUMÉ) ===
    {smart_context}
    
    === DERNIER ÉVÉNEMENT ===
    De : {sender}
    Message : {content[:2500]}
    
    Quelle est la suite logique ?
    """

    try:
        # Appel IA Manager
        response_text = get_ai_response("manager", user_prompt, system_prompt)
        
        # Nettoyage JSON (Sécurité parsing)
        cleaned_json = response_text.replace("```json", "").replace("```", "").strip()
        decision = json.loads(cleaned_json)
        
        return decision['target'], decision['instruction']

    except Exception as e:
        print(f"⚠️ Erreur Cerveau Manager : {e}")
        # En cas de panique, on demande à l'Analyste de refaire le point
        return "@Analyst", "Je n'ai pas compris la situation. Peux-tu faire un résumé de l'état actuel ?"

def run_manager():
    print("🤖 MANAGER AGILE en ligne (Smart Memory + User Interaction).")
    last_id = '$'

    while True:
        try:
            # Lecture bloquante pour économiser le CPU
            messages = r.xread({STREAM_KEY: last_id}, count=1, block=5000)
            
            if messages:
                stream, msgs = messages[0]
                last_id = msgs[0][0]
                data = msgs[0][1]
                
                sender = data['sender']
                content = data['content']
                request_id = data.get('request_id')
                status = data.get('status', 'DONE')

                # On respecte le protocole de politesse
                if status != 'DONE': continue

                # --- CAS 1 : LANCEMENT (User sans GUID) ---
                if sender == 'user' and not request_id:
                    new_guid = str(uuid.uuid4())
                    print(f"✨ NOUVEAU PROJET : {new_guid}")
                    # Lancement de la Phase 1
                    msg = "Bien reçu. @Analyst et @Architect, initialisez la conception. @Analyst commence."
                    publish_message('manager', msg, "command", request_id=new_guid, status="DONE")

                # --- CAS 2 : ORCHESTRATION ---
                elif request_id and sender != 'manager':
                    print(f"🤔 Analyse intervention de {sender}...")
                    
                    target, instruction = decide_next_step(sender, content, request_id)

                    if target == "FINISH":
                        # Sauvegarde et Fin
                        files = save_artifacts(content, request_id)
                        publish_message('manager', f"✅ PROJET TERMINÉ. Fichiers : {files}", "finished", request_id, status="DONE")
                    
                    else:
                        # Routage vers un Agent ou vers le User
                        print(f"👉 Décision : {target}")
                        publish_message('manager', instruction, "command", request_id, status="DONE")

        except Exception as e:
            print(f"🔥 Crash Manager : {e}")
            time.sleep(1)

if __name__ == "__main__":
    run_manager()