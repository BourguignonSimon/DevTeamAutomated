# Architecture Multi-Agents pour DevTeamAutomated

## 📊 Analyse du système actuel

### Structure existante
Ton package actuel a déjà une excellente base événementielle :

**Composants clés :**
- **Orchestrateur** (`services/orchestrator/main.py`) : Gère le backlog, dispatch les tâches
- **Workers spécialisés** : `dev_worker`, `test_worker`, `requirements_manager`, etc.
- **Redis Streams** : Communication asynchrone
- **Schémas stricts** : Validation des événements
- **DLQ (Dead Letter Queue)** : Gestion des erreurs

**Points forts :**
✅ Architecture événementielle robuste
✅ Séparation claire des responsabilités  
✅ Gestion d'erreurs avec DLQ
✅ Idempotence et locks
✅ Traçabilité et métriques

**Limitations actuelles :**
❌ Orchestration simple (dispatcher basique)
❌ Pas de collaboration entre agents
❌ Pas de planification dynamique
❌ Agents isolés sans contexte partagé
❌ Pas de gestion de conversation/mémoire

## 🎯 Transformation en système multi-agents

### Architecture proposée

```
┌─────────────────────────────────────────────────────────────┐
│                    ORCHESTRATEUR INTELLIGENT                │
│  - Planification dynamique                                  │
│  - Sélection d'équipe                                       │
│  - Coordination multi-agents                                │
│  - Synthèse des résultats                                   │
└──────────────────┬──────────────────────────────────────────┘
                   │
       ┌───────────┼───────────┐
       │           │           │
   ┌───▼───┐   ┌──▼───┐   ┌──▼───────┐
   │ Équipe│   │Équipe│   │  Équipe  │
   │   1   │   │  2   │   │    3     │
   └───┬───┘   └──┬───┘   └──┬───────┘
       │          │           │
   ┌───▼──────────▼───────────▼────────┐
   │     MÉMOIRE PARTAGÉE               │
   │  - Contexte projet                 │
   │  - Historique conversations        │
   │  - État global                     │
   └────────────────────────────────────┘
```

### Composants à ajouter

#### 1. Agent Orchestrator (Intelligent)
Remplace l'orchestrateur simple actuel par un orchestrateur IA qui :
- Analyse la requête initiale
- Détermine quelle équipe appeler
- Décompose en sous-tâches
- Coordonne l'exécution
- Synthétise les résultats

#### 2. Agent Teams (selon EPIC5)
Chaque équipe = groupe d'agents spécialisés qui collaborent :
- **Team 1 - Analyse/Diagnostic** : 5 agents (Pattern, Extraction, Classification, Remediation, Report)
- **Team 2 - Admin Tasks** : 2 agents (Classifier, Executor)
- **Team 3 - Email Management** : 2 agents (Parser, Writer)
- **Team 4 - Rédaction** : 2 agents (Editor, Style Keeper)
- **Team 5 - Support** : 3 agents (Context, Answer, Analytics)

#### 3. Shared Memory Layer
- Contexte de conversation par projet
- Historique des décisions
- Knowledge base partagée
- État global des tâches

#### 4. Communication Inter-Agents
- Messages directs via Redis
- Contexte partagé
- Notifications d'événements

## 🏗️ Plan d'implémentation

### Phase 1 : Orchestrateur Intelligent (core)
**Fichier :** `services/intelligent_orchestrator/main.py`

Fonctionnalités :
1. Analyse de requête avec LLM
2. Sélection d'équipe appropriée
3. Planification de tâches
4. Coordination des agents
5. Synthèse finale

### Phase 2 : Framework d'équipes
**Fichier :** `core/agent_team.py`

Classes de base :
- `AgentTeam` : Classe abstraite pour toutes les équipes
- `TeamMember` : Agent individuel dans une équipe
- `TeamCoordinator` : Coordination intra-équipe
- `SharedContext` : Contexte partagé

### Phase 3 : Implémentation des équipes
**Dossier :** `services/teams/`

Structure :
```
services/teams/
├── analysis_team/
│   ├── pattern_agent.py
│   ├── extraction_agent.py
│   ├── classifier_agent.py
│   ├── remediation_agent.py
│   └── report_agent.py
├── admin_team/
│   ├── classifier_agent.py
│   └── executor_agent.py
└── ...
```

### Phase 4 : Mémoire partagée
**Fichier :** `core/shared_memory.py`

Fonctionnalités :
- Stockage contexte conversation
- Historique décisions
- Cache de résultats
- État global synchronisé

### Phase 5 : Patterns de collaboration
**Fichier :** `core/collaboration_patterns.py`

Patterns :
- Pipeline séquentiel
- Parallèle avec fusion
- Hiérarchique
- Itératif avec feedback

## 📝 Modifications nécessaires

### 1. Orchestrateur actuel → Agent Manager
Transformer `services/orchestrator/main.py` en gestionnaire d'agents plus intelligent.

### 2. Workers → Team Members
Chaque worker devient membre d'une équipe avec capacité de collaboration.

### 3. Événements
Ajouter de nouveaux types d'événements :
- `TEAM.SELECTED`
- `AGENT.COLLABORATION_REQUEST`
- `AGENT.RESULT_SHARED`
- `TEAM.SYNTHESIS_COMPLETE`

### 4. Schémas
Nouveaux schémas pour :
- Contexte partagé
- Messages inter-agents
- Plans d'exécution
- Résultats d'équipe

## 🔧 Avantages de l'approche

1. **Rétrocompatibilité** : L'architecture actuelle reste fonctionnelle
2. **Progressif** : Peut être implémenté étape par étape
3. **Scalable** : Facile d'ajouter de nouvelles équipes
4. **Robuste** : Garde les mécanismes existants (DLQ, idempotence, etc.)
5. **Flexible** : S'adapte selon les besoins

## 📋 Étapes suivantes recommandées

1. ✅ Créer l'orchestrateur intelligent
2. ✅ Implémenter le framework d'équipes
3. ✅ Développer Team 1 (Analyse) comme POC
4. ✅ Ajouter la mémoire partagée
5. ✅ Implémenter les patterns de collaboration
6. ✅ Migrer les workers existants
7. ✅ Tests et validation

## 💡 Exemples concrets

### Scénario 1 : Analyse de document
```
User: "Analyse ce document et trouve les risques"
  ↓
Orchestrateur: Sélectionne Team 1 (Analysis)
  ↓
Team 1 exécute en séquence:
  1. Pattern Agent → identifie type de document
  2. Extraction Agent → extrait les données
  3. Classifier Agent → classe les risques
  4. Remediation Agent → suggère solutions
  5. Report Agent → génère le rapport
  ↓
Orchestrateur: Synthétise et retourne résultat
```

### Scénario 2 : Tâche complexe (multi-équipes)
```
User: "Analyse le document ET rédige un email de synthèse"
  ↓
Orchestrateur: Plan en 2 phases
  Phase 1: Team 1 (Analysis)
  Phase 2: Team 3 (Email) avec résultats de Team 1
  ↓
Exécution coordonnée avec partage de contexte
  ↓
Résultat: Document analysé + Email rédigé
```

## 🎨 Code exemple

Voir les fichiers suivants pour l'implémentation :
- `intelligent_orchestrator.py` : Nouvel orchestrateur
- `agent_team_framework.py` : Framework de base
- `analysis_team_implementation.py` : Exemple d'équipe complète
- `multi_agent_demo.py` : Démo du système complet
