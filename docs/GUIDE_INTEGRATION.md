# Guide d'Intégration Multi-Agents
## Comment adapter DevTeamAutomated vers un système multi-agents

---

## 🎯 Vue d'ensemble

Ce guide vous accompagne pour transformer votre système actuel en une architecture multi-agents complète, étape par étape.

**Durée estimée :** 2-4 semaines selon la complexité

---

## 📦 Fichiers fournis

Vous avez reçu 4 fichiers clés :

1. **`MULTI_AGENT_ARCHITECTURE.md`** : Documentation complète de l'architecture
2. **`intelligent_orchestrator.py`** : Nouvel orchestrateur intelligent
3. **`agent_team_framework.py`** : Framework de base pour les équipes
4. **`analysis_team_implementation.py`** : Exemple complet d'une équipe (Team 1)
5. **`multi_agent_demo.py`** : Démonstration interactive du système

---

## 🚀 Plan d'implémentation

### Phase 1 : Préparation (Jour 1-2)

#### Étape 1.1 : Comprendre l'existant
```bash
# Examinez l'architecture actuelle
cd /path/to/DevTeamAutomated-main

# Services existants
ls services/
# orchestrator/
# dev_worker/
# test_worker/
# requirements_manager_worker/
# etc.

# Regardez comment un worker fonctionne
cat services/dev_worker/main.py
```

**Points clés à noter :**
- ✅ Redis Streams pour communication
- ✅ Événements avec schémas JSON
- ✅ Consumer groups
- ✅ DLQ pour erreurs
- ✅ Idempotence

#### Étape 1.2 : Installer les nouveaux composants
```bash
# Créer un dossier pour les nouveaux composants
mkdir -p services/intelligent_orchestrator
mkdir -p services/teams
mkdir -p core/multi_agent

# Copier les fichiers fournis
cp intelligent_orchestrator.py services/intelligent_orchestrator/main.py
cp agent_team_framework.py core/multi_agent/framework.py
cp analysis_team_implementation.py services/teams/analysis_team.py
```

---

### Phase 2 : Orchestrateur Intelligent (Jour 3-5)

#### Étape 2.1 : Adapter l'orchestrateur
```python
# services/intelligent_orchestrator/main.py

# Ajustez les imports selon votre structure
from core.config import Settings
from core.redis_streams import build_redis_client
# ... etc.

# Personnalisez la détection d'équipes
def analyze_request(self, request_text: str, project_id: str):
    # Ajoutez vos propres patterns de détection
    if "votre_pattern_custom" in request_text.lower():
        teams.append(TeamType.YOUR_CUSTOM_TEAM)
    
    # ... reste du code
```

#### Étape 2.2 : Nouveaux schémas d'événements
```bash
# Créer les schémas pour les nouveaux événements
mkdir -p schemas/events/multi_agent
```

**Fichier :** `schemas/events/multi_agent/team_dispatched.json`
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "project_id": {"type": "string"},
    "plan_id": {"type": "string"},
    "step_id": {"type": "string"},
    "team": {"type": "string"},
    "agent_name": {"type": "string"},
    "agent_target": {"type": "string"},
    "inputs": {"type": "object"},
    "context": {"type": "object"},
    "expected_outputs": {"type": "array"}
  },
  "required": ["project_id", "plan_id", "team", "agent_target"]
}
```

#### Étape 2.3 : Docker Compose
```yaml
# Ajouter dans docker-compose.yml

  intelligent_orchestrator:
    build:
      context: .
      dockerfile: services/intelligent_orchestrator/Dockerfile
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - LOG_LEVEL=INFO
    volumes:
      - ./schemas:/app/schemas
```

**Créer :** `services/intelligent_orchestrator/Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "services.intelligent_orchestrator.main"]
```

---

### Phase 3 : Framework d'Équipes (Jour 6-8)

#### Étape 3.1 : Intégrer le framework
```python
# core/multi_agent/framework.py est déjà fourni

# Testez-le
python -c "from core.multi_agent.framework import AgentTeam, TeamAgent; print('✓ Framework OK')"
```

#### Étape 3.2 : Créer votre première équipe (Analysis Team)
```bash
# Le fichier est déjà fourni comme exemple
cp analysis_team_implementation.py services/teams/analysis_team.py

# Créer le Dockerfile
cat > services/teams/analysis_team.Dockerfile <<EOF
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "services.teams.analysis_team"]
EOF
```

#### Étape 3.3 : Ajouter au Docker Compose
```yaml
  analysis_team:
    build:
      context: .
      dockerfile: services/teams/analysis_team.Dockerfile
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
```

---

### Phase 4 : Mémoire Partagée (Jour 9-10)

#### Étape 4.1 : Implémenter la couche de mémoire
```python
# core/multi_agent/memory.py

from typing import Any, Dict, Optional
import json

class SharedMemoryManager:
    """Gestionnaire de mémoire partagée"""
    
    def __init__(self, redis_client, prefix="shared_memory"):
        self.r = redis_client
        self.prefix = prefix
    
    def save_conversation(self, project_id: str, message: str, role: str):
        """Sauvegarde un message de conversation"""
        key = f"{self.prefix}:conversation:{project_id}"
        
        entry = {
            "timestamp": time.time(),
            "role": role,
            "message": message
        }
        
        self.r.rpush(key, json.dumps(entry))
        self.r.expire(key, 86400)  # 24h TTL
    
    def get_conversation(self, project_id: str, limit: int = 10):
        """Récupère l'historique de conversation"""
        key = f"{self.prefix}:conversation:{project_id}"
        messages = self.r.lrange(key, -limit, -1)
        return [json.loads(m) for m in messages]
```

---

### Phase 5 : Créer d'Autres Équipes (Jour 11-15)

#### Exemple : Email Team
```python
# services/teams/email_team.py

from core.multi_agent.framework import AgentTeam, TeamAgent, AgentRole

class EmailParserAgent(TeamAgent):
    """Parse et analyse les emails"""
    
    def __init__(self, redis_client, settings):
        super().__init__(
            name="email_parser",
            role=AgentRole.ANALYZER,
            team_name="email_team",
            redis_client=redis_client,
            settings=settings,
        )
    
    def execute(self, inputs, context):
        # Votre logique ici
        email_text = inputs.get("email_text", "")
        
        # Parse l'email
        parsed = {
            "subject": self._extract_subject(email_text),
            "intent": self._detect_intent(email_text),
            "priority": self._assess_priority(email_text),
        }
        
        return AgentResult(
            agent_name=self.name,
            success=True,
            outputs=parsed,
            confidence=0.85,
        )

class EmailWriterAgent(TeamAgent):
    """Rédige des emails"""
    # ... implémentation similaire

class EmailTeam(AgentTeam):
    """Équipe de gestion des emails"""
    
    def _init_agents(self):
        self.add_agent(EmailParserAgent(self.r, self.settings))
        self.add_agent(EmailWriterAgent(self.r, self.settings))
```

---

### Phase 6 : Tests et Validation (Jour 16-20)

#### Étape 6.1 : Tests unitaires
```python
# tests/test_multi_agent_orchestrator.py

import pytest
from services.intelligent_orchestrator.main import IntelligentOrchestrator

def test_analyze_simple_request(redis_client):
    """Test d'analyse d'une requête simple"""
    settings = Settings()
    orch = IntelligentOrchestrator(redis_client, settings)
    
    plan = orch.analyze_request(
        "Analyse ce document d'audit",
        project_id="test_123"
    )
    
    assert plan.teams == [TeamType.ANALYSIS]
    assert plan.strategy == ExecutionStrategy.SEQUENTIAL
    assert len(plan.steps) == 1

def test_multi_team_detection(redis_client):
    """Test de détection multi-équipes"""
    settings = Settings()
    orch = IntelligentOrchestrator(redis_client, settings)
    
    plan = orch.analyze_request(
        "Analyse le document ET rédige un email",
        project_id="test_456"
    )
    
    assert TeamType.ANALYSIS in plan.teams
    assert TeamType.EMAIL in plan.teams
    assert len(plan.steps) == 2
```

#### Étape 6.2 : Tests d'intégration
```python
# tests/test_analysis_team_integration.py

def test_full_team_execution(redis_client):
    """Test d'exécution complète d'une équipe"""
    settings = Settings()
    team = AnalysisTeam("analysis_team", redis_client, settings)
    
    inputs = {
        "request": "Analyse complète des risques",
    }
    
    result = team.execute(
        inputs=inputs,
        project_id="test_789",
        plan_id="plan_abc",
        step_id="step_1",
        correlation_id="corr_xyz",
    )
    
    assert result["team"] == "analysis_team"
    assert "outputs" in result
    assert result["confidence"] > 0.7
```

---

### Phase 7 : Déploiement (Jour 21+)

#### Étape 7.1 : Lancer le système complet
```bash
# Arrêter l'ancien système
docker compose down

# Construire les nouveaux services
docker compose build

# Lancer tout
docker compose up -d \
  redis \
  intelligent_orchestrator \
  analysis_team \
  email_team

# Vérifier les logs
docker compose logs -f intelligent_orchestrator
```

#### Étape 7.2 : Test de bout en bout
```bash
# Envoyer une requête test
python - <<'PY'
import json, uuid, redis
from core.event_utils import envelope

r = redis.Redis(host="localhost", port=6380)
env = envelope(
    event_type="PROJECT.INITIAL_REQUEST_RECEIVED",
    source="demo",
    payload={
        "project_id": str(uuid.uuid4()),
        "request_text": "Analyse ce document d'audit et identifie les risques"
    },
    correlation_id=str(uuid.uuid4()),
    causation_id=None,
)
r.xadd("audit:events", {"event": json.dumps(env)})
print("✓ Requête envoyée")
PY

# Observer les événements
redis-cli -p 6380 XREAD COUNT 10 STREAMS audit:events 0
```

---

## 🔧 Configuration Avancée

### Variables d'environnement
```bash
# .env
NAMESPACE=audit
REDIS_HOST=redis
REDIS_PORT=6379
LOG_LEVEL=INFO

# Multi-agent specific
ORCHESTRATOR_MODE=intelligent  # vs 'simple'
ENABLE_TEAMS=analysis,email,admin,writing,support
MEMORY_TTL=7200  # 2 heures
```

### Monitoring
```python
# core/multi_agent/metrics.py

class MultiAgentMetrics:
    """Métriques spécifiques multi-agents"""
    
    def record_team_execution(self, team_name, duration, success):
        key = f"metrics:team:{team_name}"
        self.r.hincrby(key, "executions", 1)
        if success:
            self.r.hincrby(key, "successes", 1)
        self.r.hincrbyfloat(key, "total_duration", duration)
```

---

## 📊 Migration Progressive

### Option 1 : Big Bang (tout d'un coup)
- Jour 1 : Arrêt de l'ancien système
- Jour 2-3 : Déploiement du nouveau
- Jour 4+ : Stabilisation

**Avantages :** Rapide
**Inconvénients :** Risqué

### Option 2 : Cohabitation (recommandé)
```python
# Les deux orchestrateurs cohabitent

# Ancien orchestrateur : groupe "orchestrators"
# Nouveau orchestrateur : groupe "intelligent_orchestrators"

# Router selon un flag
if project_config.get("use_multi_agent"):
    # Envoyer vers intelligent orchestrator
else:
    # Garder l'ancien système
```

---

## ✅ Checklist de Validation

### Fonctionnalités de base
- [ ] Orchestrateur intelligent démarre
- [ ] Analyse correcte des requêtes
- [ ] Sélection d'équipe appropriée
- [ ] Création de plans d'exécution
- [ ] Dispatch vers les équipes

### Équipes
- [ ] Analysis Team fonctionne
- [ ] Les 5 agents s'exécutent en séquence
- [ ] Contexte partagé entre agents
- [ ] Résultats agrégés correctement

### Robustesse
- [ ] Gestion des erreurs
- [ ] DLQ pour événements invalides
- [ ] Idempotence respectée
- [ ] Retry automatique
- [ ] Clarifications demandées quand nécessaire

### Performance
- [ ] Temps de réponse < 30s pour analyse simple
- [ ] Exécution parallèle fonctionne
- [ ] Pas de memory leak
- [ ] Redis stable sous charge

---

## 🆘 Dépannage

### Problème : L'orchestrateur ne démarre pas
```bash
# Vérifier les logs
docker compose logs intelligent_orchestrator

# Vérifier Redis
redis-cli -p 6380 PING

# Vérifier les schemas
ls -la schemas/events/
```

### Problème : Les équipes ne reçoivent pas les tâches
```bash
# Vérifier le consumer group
redis-cli -p 6380 XINFO GROUPS audit:events

# Vérifier les événements
redis-cli -p 6380 XLEN audit:events

# Suivre le stream
redis-cli -p 6380 XREAD COUNT 5 STREAMS audit:events 0
```

### Problème : Contexte partagé vide
```python
# Vérifier dans Redis
redis-cli -p 6380 KEYS "shared_memory:*"

# Debug dans le code
self.logger.info(f"Context: {json.dumps(context.__dict__, indent=2)}")
```

---

## 📚 Ressources Supplémentaires

### Documentation
- `MULTI_AGENT_ARCHITECTURE.md` : Architecture complète
- `docs/EPIC5_AI_AGENT_TEAMS.md` : Spécifications des équipes

### Exemples
- `multi_agent_demo.py` : Démonstration interactive
- `analysis_team_implementation.py` : Exemple complet d'équipe

### Communauté
- Issues GitHub du projet original
- Forums de discussion sur l'IA agentique

---

## 🎯 Prochaines Étapes

Une fois le système en place :

1. **Ajouter plus d'équipes** selon EPIC5
2. **Intégrer des LLMs réels** (OpenAI, Anthropic)
3. **Améliorer l'orchestration** avec ML
4. **Ajouter de la mémoire long-terme**
5. **Implémenter l'apprentissage supervisé**

---

**🎉 Félicitations ! Vous avez maintenant un système multi-agents complet !**
