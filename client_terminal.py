import os
import time
import sys
from utils import r, STREAM_KEY, publish_message

# ==========================================
# 🎨 COULEURS ANSI (POUR LE STYLE)
# ==========================================
C_MGR = "\033[94m" # Bleu (Manager)
C_USR = "\033[97m" # Blanc (User)
C_ANL = "\033[96m" # Cyan (Analyste)
C_ARC = "\033[95m" # Magenta (Architecte)
C_COD = "\033[92m" # Vert (Codeur)
C_REV = "\033[93m" # Jaune (Reviewer)
C_RST = "\033[0m"  # Reset

# ==========================================
# 🛠️ FONCTION UTILITAIRE (La correction est ici)
# ==========================================
def get_color(sender):
    """Retourne la couleur associée au rôle."""
    if sender == 'manager': return C_MGR
    if sender == 'analyst': return C_ANL
    if sender == 'architect': return C_ARC
    if sender == 'coder': return C_COD
    if sender == 'reviewer': return C_REV
    return C_RST

# ==========================================
# 👂 L'ÉCOUTEUR DE FLUX (LISTENER)
# ==========================================
def listener(last_id='$'):
    """
    Écoute le flux Redis en continu.
    Affiche les messages en entier avec un formatage cadre.
    """
    print(f"\n{C_MGR}--- DÉBUT DE LA SÉQUENCE (Flux complet) ---{C_RST}\n")
    
    try:
        while True:
            # Lecture par lot de 10 messages pour ne rien rater
            messages = r.xread({STREAM_KEY: last_id}, count=10, block=1000)
            
            if messages:
                stream, msgs = messages[0]
                
                for msg in msgs:
                    msg_id = msg[0]
                    data = msg[1]
                    last_id = msg_id # Mise à jour du curseur
                    
                    sender = data['sender']
                    content = data['content']
                    req_id = data.get('request_id', 'N/A')
                    
                    if sender == 'user': continue # On masque nos propres messages en double

                    # 1. En-tête du message
                    color = get_color(sender)
                    print(f"{color}┌─ [{sender.upper()}] (GUID:{req_id[:4]}..)")
                    
                    # 2. Le Contenu (Sans coupure !)
                    # On ajoute une indentation pour la lisibilité
                    clean_content = content.replace("\n", "\n│  ")
                    print(f"│  {clean_content}")
                    
                    # 3. Pied de message
                    print(f"└──────────────────────────────────────────────────{C_RST}")
                    
                    # Détection de fin
                    if "PROJET TERMINÉ" in content or "TERMINÉ" in content:
                        print(f"\n{C_COD}✅ CYCLE FINI. Fichiers disponibles dans /livrables.{C_RST}\n")
                        return

    except KeyboardInterrupt:
        return

# ==========================================
# 🚀 POINT D'ENTRÉE PRINCIPAL
# ==========================================
def main():
    os.system('clear')
    print(f"{C_MGR}=== USINE LOGICIELLE 'LA TABLE RONDE' (FULL VIEW) ==={C_RST}")
    
    while True:
        try:
            user_input = input(f"\n{C_USR}Votre commande ('q' pour quitter) > {C_RST}")
            if user_input.lower() in ['q', 'exit']: break
            if not user_input.strip(): continue

            # Envoi commande
            print(f"{C_USR}Cmd envoyée...{C_RST}")
            publish_message("user", user_input, "order", status="DONE")
            
            # Écoute
            listener(last_id='$')
            
        except KeyboardInterrupt:
            print("\nAu revoir.")
            break

if __name__ == "__main__":
    main()