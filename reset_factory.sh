#!/bin/bash

# ============================================================
# 🧨 SCRIPT DE RÉINITIALISATION TOTALE (RESET FACTORY)
# ============================================================

echo ""
echo "💣 INITIALISATION DE LA PROCÉDURE DE RESET..."
echo "---------------------------------------------"

# 1. ARRÊT DES PROCESSUS (KILL)
echo "🛑 1. Arrêt forcé des agents Python..."
# On tue tout ce qui contient "agent_" ou "client_" lancé avec python3
pkill -f "python3 agent_" || true
pkill -f "python3 client_" || true
echo "   -> Processus terminés."

# 2. NETTOYAGE DES FICHIERS (LOGS & LIVRABLES)
echo "🧹 2. Suppression des fichiers temporaires..."
# On vide les dossiers sans supprimer les dossiers eux-mêmes
rm -f logs/*.log 2>/dev/null
rm -f project_logs/*.jsonl 2>/dev/null
rm -f livrables/*.py 2>/dev/null

# On supprime les caches Python (__pycache__) qui peuvent traîner
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
echo "   -> Disque nettoyé."

# 3. VIDAGE DE LA MÉMOIRE (REDIS FLUSH)
echo "🧠 3. Lavage de cerveau (Redis FLUSHALL)..."
if [ "$(docker ps -q -f name=redis-lab)" ]; then
    docker exec redis-lab redis-cli FLUSHALL > /dev/null
    echo "   -> Mémoire Redis vidée avec succès."
else
    echo "   ⚠️ ATTENTION : Le conteneur 'redis-lab' ne tourne pas."
    echo "      (Si c'est la première fois, lancez ./start_wsl.sh d'abord)"
fi

echo "---------------------------------------------"
echo "✨ SYSTÈME REMIS À NEUF (TABULA RASA)."
echo "   Vous pouvez relancer : ./start_wsl.sh"
echo ""
