import os
import redis
import google.generativeai as genai
from dotenv import load_dotenv
import json
import uuid
from datetime import datetime

load_dotenv()

r = redis.Redis(host=os.getenv('REDIS_HOST'), port=int(os.getenv('REDIS_PORT')), decode_responses=True)
STREAM_KEY = "table_ronde_stream"

genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))

# --- GESTION DU LOGGING & SÉQUENCE ---
def get_next_sequence(request_id):
    if not request_id: return 0
    return r.incr(f"project:{request_id}:sequence")

def log_to_disk(request_id, sequence_id, sender, content, msg_type, status):
    if not request_id: return
    log_dir = "project_logs"
    if not os.path.exists(log_dir): os.makedirs(log_dir)
    filename = f"{log_dir}/project_{request_id}.jsonl"
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "sequence": sequence_id,
        "sender": sender,
        "type": msg_type,
        "status": status,
        "content": content
    }
    with open(filename, "a", encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def publish_message(sender, content, msg_type="message", request_id=None, status="DONE"):
    """
    Version corrigée pour gérer les erreurs d'encodage (Accents Windows/WSL).
    """
    seq_id = get_next_sequence(request_id)
    
    # --- FIX CRITIQUE : Nettoyage des caractères invalides ---
    if isinstance(content, str):
        # On force l'encodage en ignorant les erreurs (remplacement par des ?)
        # Cela élimine les "surrogates" \udcc3 qui font planter Redis
        content = content.encode('utf-8', 'replace').decode('utf-8')
    # ---------------------------------------------------------

    message = {
        "request_id": request_id if request_id else "",
        "sequence_id": seq_id,
        "sender": sender,
        "content": content,
        "type": msg_type,
        "status": status
    }
    
    r.xadd(STREAM_KEY, message)
    log_to_disk(request_id, seq_id, sender, content, msg_type, status)

# --- MOTEUR IA & MÉMOIRE INTELLIGENTE ---

def compress_history(current_summary, new_messages_text):
    """Demande à Gemini de fusionner le vieux résumé avec les nouveaux messages."""
    model = genai.GenerativeModel(os.getenv('MODEL_FAST')) # On utilise le modèle rapide pour résumer
    prompt = f"""
    Tu es le Gardien de la Mémoire du projet.
    
    ANCIEN RÉSUMÉ :
    {current_summary}
    
    NOUVEAUX ÉVÉNEMENTS RÉCENTS :
    {new_messages_text}
    
    TÂCHE :
    Produis un nouveau résumé consolidé qui intègre les faits marquants des nouveaux événements à l'ancien résumé.
    Sois concis mais ne perds aucune information technique critique (stack, noms de fichiers, décisions).
    """
    try:
        return model.generate_content(prompt).text
    except:
        return current_summary + "\n[Erreur compression]"

def build_smart_context(request_id):
    """
    Construit le contexte pour l'agent.
    Gère automatiquement le résumé tous les 10 messages (Rolling Window).
    """
    if not request_id: return "Pas de contexte projet."

    # 1. Récupération des clés Redis
    summary_key = f"project:{request_id}:summary"
    last_read_key = f"project:{request_id}:last_read_id"
    
    stored_summary = r.get(summary_key) or "Début du projet."
    last_read_id = r.get(last_read_key) or "0-0"

    # 2. Lecture des NOUVEAUX messages depuis le dernier point de contrôle
    # On lit tout ce qui est nouveau
    new_stream_data = r.xread({STREAM_KEY: last_read_id}, count=100) 
    
    new_messages = []
    last_id_in_batch = last_read_id

    if new_stream_data:
        for msg in new_stream_data[0][1]:
            msg_id = msg[0]
            data = msg[1]
            if data.get('request_id') == request_id:
                formatted = f"[{data['sender'].upper()}]: {data['content']}"
                new_messages.append(formatted)
                last_id_in_batch = msg_id # On garde trace du dernier ID pertinent

    # 3. Logique de Compression (Seuil de 10 messages en attente)
    # Si on a plus de 10 nouveaux messages "frais", on met à jour le résumé
    # et on ne garde que les 5 derniers en "messages récents" pour l'affichage immédiat
    
    final_context = ""
    
    if len(new_messages) > 10:
        print(f"📚 [MÉMOIRE] Compression de l'historique ({len(new_messages)} messages)...")
        
        # On coupe : Tout sauf les 5 derniers partent au résumé
        to_summarize = new_messages[:-5]
        to_keep_fresh = new_messages[-5:]
        
        # Mise à jour du résumé via IA
        text_to_compress = "\n".join(to_summarize)
        new_summary = compress_history(stored_summary, text_to_compress)
        
        # Sauvegarde dans Redis
        r.set(summary_key, new_summary)
        
        # On avance le curseur (approximatif pour cette démo, idéalement on gère l'ID précis)
        # Ici on garde le curseur tel quel pour que la prochaine lecture reprenne la suite, 
        # mais on considère que le résumé est à jour.
        
        # Construction du contexte pour l'agent
        final_context = f"""
        === 🗂️ MÉMOIRE LONG TERME (RÉSUMÉ) ===
        {new_summary}
        
        === 🆕 DERNIERS ÉCHANGES (LIVE) ===
        {chr(10).join(to_keep_fresh)}
        """
        
        # Pour simplifier la prochaine lecture, on pourrait mettre à jour last_read_key
        # Mais attention à ne pas perdre de messages.
        # Dans cette implémentation simple, on relit tout depuis Redis à chaque fois 
        # mais on ne "compresse" que si on a accumulé beaucoup.
        
    else:
        # Pas assez de messages pour compresser, on envoie tout
        # Mais on inclut le résumé existant s'il y en a un
        final_context = f"""
        === 🗂️ MÉMOIRE LONG TERME (RÉSUMÉ) ===
        {stored_summary}
        
        === 🆕 ÉCHANGES RÉCENTS ===
        {chr(10).join(new_messages)}
        """

    return final_context

def get_ai_response(role, prompt, full_context=""):
    model_name = os.getenv('MODEL_SMART') if role in ['manager', 'analyst', 'architect'] else os.getenv('MODEL_FAST')
    try:
        model = genai.GenerativeModel(model_name)
        # On injecte le contexte construit intelligemment
        final_prompt = f"{full_context}\n\n🤖 TÂCHE POUR {role.upper()} : {prompt}"
        response = model.generate_content(final_prompt)
        return response.text
    except Exception as e:
        return f"[ERREUR IA] {e}"