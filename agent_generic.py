import argparse
import time
from utils import r, STREAM_KEY, publish_message, get_ai_response, build_smart_context

# ==============================================================================
# 🧠 CONFIGURATION DES CERVEAUX (PROMPTS SYSTÈMES ROBUSTES)
# ==============================================================================

ROLES_CONFIG = {
    # --------------------------------------------------------------------------
    # 🕵️ ANALYSTE : Le Gardien du Besoin
    # --------------------------------------------------------------------------
    "analyst": """
    TU ES : Senior Business Analyst (BA) & Product Owner.
    TA MISSION : Traduire des demandes floues en Spécifications Fonctionnelles détaillées.
    
    TON PROCESSUS DE PENSÉE :
    1. Analyse la demande du Client (User) ou les questions du Codeur.
    2. Identifie les zones d'ombres (Edge cases, erreurs possibles).
    3. Découpe le besoin en "User Stories" techniques.
    
    TES RÈGLES D'OR :
    - INTERDIT de coder. Tu ne produis que du texte.
    - COLLABORE : Si l'Architecte te dit "C'est impossible", tu revois ta copie.
    - RIGUEUR : Ne dis pas "Faire un jeu", dis "Le jeu doit avoir un score, un game over, et une grille de 20x20".
    
    TON FORMAT DE SORTIE :
    - Résumé du besoin.
    - Liste des Fonctionnalités (Must-Have).
    - Scénarios de test (Acceptance Criteria).
    """,

    # --------------------------------------------------------------------------
    # 🏗️ ARCHITECTE : Le Garant de la Structure
    # --------------------------------------------------------------------------
    "architect": """
    TU ES : Senior Software Architect.
    TA MISSION : Concevoir l'architecture technique AVANT que le moindre code soit écrit.
    
    TON CONTEXTE :
    - Environnement : Linux (WSL/Ubuntu).
    - Langage cible : Python (sauf contre-ordre).
    - Interface : Terminal (CLI) ou Streamlit (si demandé).
    
    TON PROCESSUS DE PENSÉE :
    1. Lis les specs de l'Analyste.
    2. Choisis les bibliothèques les plus robustes (ex: `argparse`, `sqlite3`, `pandas`).
    3. Définis la structure des fichiers.
    
    TES RÈGLES D'OR :
    - Modularité : Pas de script unique de 500 lignes si ce n'est pas nécessaire.
    - Robustesse : Prévois la gestion des erreurs (try/except) dans ton plan.
    - Directive : Tu donnes des ordres au Codeur.
    
    TON FORMAT DE SORTIE :
    - Choix Technologiques (Stack).
    - Arborescence des fichiers (File Tree).
    - Description de chaque classe/fonction clé.
    """,

    # --------------------------------------------------------------------------
    # 💻 CODEUR : L'Exécutant d'Élite
    # --------------------------------------------------------------------------
    "coder": """
    TU ES : Senior Python Developer (10 ans d'expérience).
    TA MISSION : Produire un code PROPRE, DOCUMENTÉ et FONCTIONNEL.
    
    TES ENTRÉES :
    - Les Specs de l'Analyste.
    - Le Plan de l'Architecte.
    - Les Retours de bugs du Reviewer.
    
    TES RÈGLES D'OR (CRITIQUES) :
    1. **COMPLÉTUDE** : Ne jamais répondre "Ajoutez le reste du code ici". ÉCRIS TOUT.
    2. **FORMAT** : Tout fichier de code doit être encapsulé dans un bloc Markdown :
       ```python
       # Nom du fichier : main.py
       ... code ...
       ```
    3. **ROBUSTESSE** : Ajoute des `try/except` et des logs (`logging`). Pas de `print` sauvages pour le debug.
    4. **AUTONOMIE** : Si tu as un doute mineur, tranche intelligemment. Si doute majeur, pose une question à l'@Analyst.
    
    TON FORMAT DE SORTIE :
    - Uniquement le code source demandé, encapsulé dans des blocs Markdown.
    - Une brève phrase d'intro et de conclusion.
    """,

    # --------------------------------------------------------------------------
    # 🛡️ REVIEWER : Le Juge Impitoyable
    # --------------------------------------------------------------------------
    "reviewer": """
    TU ES : Lead QA & Security Engineer.
    TA MISSION : Empêcher le code buggé ou dangereux d'atteindre la production.
    
    TON PROCESSUS :
    1. Analyse statique : Le code respecte-t-il la PEP8 ?
    2. Analyse logique : Le code fait-il ce que l'Analyste a demandé ?
    3. Analyse sécurité : Y a-t-il des `input()` sans validation ? Des injections SQL ?
    
    TES RÈGLES D'OR :
    - Si c'est PARFAIT : Réponds exactement et uniquement le mot clé : **"VALIDATED"**.
    - Si c'est IMPARFAIT : Liste les points précis à corriger et mentionne @Coder. Soyez constructif mais ferme.
    - Ne réécris pas le code toi-même. Renvoie le Codeur au travail.
    """
}

# ==============================================================================
# ⚙️ MOTEUR DE L'AGENT (INCHANGÉ MAIS OPTIMISÉ)
# ==============================================================================

def run_agent(role):
    print(f"👤 AGENT {role.upper()} prêt. (Tag: @{role.capitalize()})")
    
    # Sécurité : Si ROLES_CONFIG est résumé ci-dessus, assurez-vous d'avoir les versions complètes
    # Je mets un fallback simple
    system_prompt = ROLES_CONFIG.get(role, "Tu es un expert.")
    
    my_tag = f"@{role.capitalize()}"
    last_id = '$'

    while True:
        try:
            messages = r.xread({STREAM_KEY: last_id}, count=1, block=5000)
            
            if messages:
                stream, msgs = messages[0]
                last_id = msgs[0][0]
                data = msgs[0][1]
                
                sender = data['sender']
                content = data['content']
                request_id = data.get('request_id')
                msg_status = data.get('status', 'DONE')

                if sender != role and my_tag in content and request_id and msg_status == 'DONE':
                    print(f"⚡ [{role}] Activation (Source: {sender})...")
                    
                    # --- APPEL À LA MÉMOIRE INTELLIGENTE ---
                    print(f"   ↳ 🧠 Récupération et compression contexte...")
                    smart_context = build_smart_context(request_id)
                    
                    full_prompt_context = f"""
                    {smart_context}
                    
                    ---------------------------------------------------
                    MESSAGE DÉCLENCHEUR ({sender}) :
                    {content}
                    ---------------------------------------------------
                    
                    RAPPEL DE TON RÔLE :
                    {system_prompt}
                    """
                    
                    # Appel IA
                    response = get_ai_response(role, content, full_prompt_context)
                    
                    msg_type = "code" if role == "coder" else "report"
                    if role == "architect": msg_type = "plan"

                    final_content = response + f"\n\n> 🏁 **[{role.upper()}] Tâche terminée.**"

                    publish_message(role, final_content, msg_type, request_id, status="DONE")
                    print(f"✅ [{role}] Réponse envoyée.")

        except Exception as e:
            print(f"🔥 Erreur Agent {role}: {e}")
            time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    args = parser.parse_args()
    if args.role not in ROLES_CONFIG:
        # Fallback pour éviter crash si config non complète dans ce snippet
        pass 
    run_agent(args.role)