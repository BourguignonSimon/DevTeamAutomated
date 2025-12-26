#!/bin/bash

# ==============================================================================
# 🧹 FONCTION DE NETTOYAGE ROBUSTE
# ==============================================================================
cleanup() {
    echo ""
    echo "🛑 ARRÊT D'URGENCE DE L'USINE..."

    # 1. Tuer les jobs d'arrière-plan liés à ce script (Méthode douce)
    if [ -n "$(jobs -p)" ]; then
        kill $(jobs -p) 2>/dev/null
    fi

    # 2. Tuer spécifiquement les scripts Python par leur nom (Méthode forte)
    # Le "|| true" évite d'afficher une erreur si le processus est déjà mort
    echo "   - Terminaison du Manager..."
    pkill -f "python3 agent_manager.py" || true

    echo "   - Terminaison des Agents (Analyst, Archi, Coder, Reviewer)..."
    pkill -f "python3 agent_generic.py" || true

    echo "   - Terminaison du Terminal Client..."
    pkill -f "python3 client_terminal.py" || true

    # 3. Petit temps de pause pour laisser l'OS libérer les ressources
    sleep 1

    # 4. Vider la base de données Redis (La Mémoire)
    # C'est cette ligne qui supprime les messages !
    if [ "$(docker ps -q -f name=redis-lab)" ]; then
        echo "   - Vidage de la mémoire Redis..."
        docker exec redis-lab redis-cli FLUSHALL > /dev/null
    fi
    
    echo "✅ Fermeture complète. Tous les processus Python sont éteints."
}

# Piège les signaux : 
# EXIT (Fin normale), SIGINT (Ctrl+C), SIGTERM (Kill externe)
trap cleanup EXIT SIGINT SIGTERM

echo "🚀 Démarrage de 'La Table Ronde'..."

# Création des dossiers nécessaires
mkdir -p logs livrables project_logs

# Lancement des Agents (en mode silencieux background)
echo "   - Manager..."
python3 agent_manager.py > logs/manager.log 2>&1 &

echo "   - Analyste..."
python3 agent_generic.py --role analyst > logs/analyst.log 2>&1 &

echo "   - Architecte..."
python3 agent_generic.py --role architect > logs/architect.log 2>&1 &

echo "   - Codeur..."
python3 agent_generic.py --role coder > logs/coder.log 2>&1 &

echo "   - Reviewer..."
python3 agent_generic.py --role reviewer > logs/reviewer.log 2>&1 &

echo "⏳ Initialisation des connexions..."
sleep 2

# Lancement de l'interface
python3 client_terminal.py