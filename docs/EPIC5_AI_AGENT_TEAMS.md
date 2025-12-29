# Audit Flash OS — EPIC 5: AI Agent Teams (Document de cadrage)

## 1. Rôle de l'EPIC 5

EPIC 5 vise à industrialiser la production d'équipes d'agents IA fonctionnant comme de véritables équipes métier sur des tâches d'audit. Chaque équipe agit comme si elle était dédiée à une personne et couvre des domaines métiers spécifiques avec un cadrage strict (scope, mission, mode de fonctionnement). Une seule équipe répond à chaque demande utilisateur, afin de couvrir les besoins de Charlez sans chevauchement inutile.

## 2. Principes communs à toutes les équipes

### 2.1 Cadrage précis

- Mission et scope clairement délimités.
- Réponses factuelles et succinctes.
- Apprentissage contrôlé.

### 2.2 Apprentissage contrôlé

#### 2.2.1 À noter

- Validation des réponses par un utilisateur humain (O) requise.

#### 2.2.2 Mode d'apprentissage

- Le feedback utilisateur est utilisé en mode supervisé (V ou O).
- Pas de mode de réflexion libre ni de recopie des messages utilisateurs.
- Élargissement du contexte limité au scope défini.
- Pas d'interaction entre agents.
- Chaque agent suit le pattern classique : consommation d'entrée, prise de contexte, mode de réponse.

### 2.3 Collaborations

- Les agents ne collaborent pas entre eux.
- Ils peuvent recevoir les réponses d'autres agents, mais pas l'inverse.

## 3. Fondations transverses (Agent Team Framework)

### 3.1 Shared services

- Data layer : connecteurs (à compléter). Apprentissage supervisé en option.
- Document, email, logging, mémoire court et long terme, entrepôt des erreurs/rejets.

### 3.2 Observability

- Compteurs d'erreurs.
- Confidence score.
- Logs et traces.
- Navigation de chat historisée.

### 3.3 Metrics

- Volume / vitesse / qualité.

### 3.4 Phases

- Ask to Bricol : augmentation du user prompt.
- Ask to Contrain : demande de contexte à l'utilisateur.

### 3.5 Architecture initiale

- Chaque équipe utilise les services de l'Agent Team Framework.
- Les questions distantes (mails, autres systèmes) sont gérées comme des tasks.

## 4. Équipe 1 — Analyser / Diagnostic Team

- **Mission** : catégoriser par type et niveau des risques.
- **Scope initial** : tous documents.
- **Q&A base** : Charlez Base + contexte utilisateur.
- **Rapports** : format standardisé.
- **Agents** :
  - Agent 1.1 — Process Pattern Analyzer : analyse le pattern des demandes et groupe celles qui sont similaires.
  - Agent 1.2 — Document Extraction Agent : extrait les données et les structure par catégories de risques ; sortie : données structurées.
  - Agent 1.3 — Risk Classifier Agent : classe les risques et leurs priorités.
  - Agent 1.4 — Remediation Suggestions Agent : suggère des réponses et remédiations par type de risque.
  - Agent 1.5 — Rapport Generator Agent : génère des rapports standard, avec mise en forme pour Doc/CEO.

## 5. Équipe 2 — Small Administrative Task Team

- **Mission** : aide pour les tâches administratives simples.
- **Scope initial** : email, note, système d'administration.
- **Agents** :
  - Agent 2.1 — Task Classifier : classe les tâches à partir de mails/notes et par type d'action.
  - Agent 2.2 — Task Executor : complète les tâches simples du scope (ex. mise à jour d'un email/doc).
- **Validation** : apprentissage supervisé avec logs.

## 6. Équipe 3 — Email Management Team

- **Mission** : gérer les emails pour l'audit.
- **Scope initial** : email, agenda, logging.
- **Agents** :
  - Agent 3.1 — Email Parser Agent : analyse le mail et extrait intention, date, priorité, utilisateur.
  - Agent 3.2 — Email Writer Agent : rédige les mails en suivant un style standard.
- **Validation** : réponse fournie en mode draft, l'utilisateur valide la rédaction.

## 7. Équipe 4 — Rédaction Team

- **Mission** : rédiger les documents.
- **Scope initial** : Word.
- **Agents** :
  - Agent 4.1 — Word Editing Agent : copy/translate/clean ; gère le processus de "clean house".
  - Agent 4.2 — Doc Style Keeper Agent : maintient le style global du document (points centraux, intro, transitions, actions).

## 8. Équipe 5 — User Support Management Team

- **Mission** : aide utilisateur / support.
- **Scope initial** : chat, email.
- **Agents** :
  - Agent 5.1 — Context Handler Agent : reconstitue le contexte (utilisateur/fichier/jour/urgence) et fournit les hints aux autres agents.
  - Agent 5.2 — Answer Draft Agent : propose des réponses en citant systématiquement les sources.
  - Agent 5.3 — Support Analytics Agent : analyse la récurrence et le potentiel d'automatisation.
- **Validation** : apprentissage uniquement sur réponses validées.

## 9. Reporting transverse (clé de la valeur)

- Chaque équipe produit :
  - un résumé périodique ;
  - un score de confiance ;
  - la liste des erreurs ;
  - la validation mesurée ;
  - les propositions d'extension.
- Chaque reporting décrit précisément ces éléments.

## 10. Définition du succès

- Mesure du volume traité et de la vitesse.
- Précision augmentée sur les tâches répétées.
- Suivi des erreurs critiques et de la satisfaction utilisateur.
- Trajectoire claire pour l'équipe.

## 11. Instruction finale

- Les équipes doivent être conçues comme robustes, opérantes, cohérentes.
- Une seule équipe répond à un prompt.
- Systématisation du triptyque demande/mission/scope.
- Enrichir l'IA par des datasets validés.
- Visée : construire une trajectoire, pas une promesse magique.
