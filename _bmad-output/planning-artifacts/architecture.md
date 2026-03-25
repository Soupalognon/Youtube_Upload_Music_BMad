---
stepsCompleted: ['step-01-init', 'step-02-context', 'step-03-starter', 'step-04-decisions', 'step-05-patterns', 'step-06-structure', 'step-07-validation', 'step-08-complete']
lastStep: 8
status: 'complete'
completedAt: '2026-02-22'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/epics.md'
workflowType: 'architecture'
project_name: 'Youtube_upload_playlists'
user_name: 'Gabriel'
date: '2026-02-22'
---

# Architecture Decision Document

_Ce document se construit collaborativement, étape par étape. Les sections sont ajoutées au fil des décisions architecturales prises ensemble._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (37) :**
Pipeline en 3 phases : scanner.py (FR9–FR15) produit library.csv ;
matcher.py (FR16–FR21, FR37) l'enrichit d'URLs YouTube Music et de
scores ; importer.py (FR22–FR29) finalise les imports. FR1–FR8 couvrent
la configuration et l'authentification. FR30–FR36 couvrent le reporting
temps réel et la review manuelle.

**Non-Functional Requirements (13) :**
- Performance : traitement streaming 50k+ fichiers sans saturation mémoire (NFR1), stabilité multi-heures (NFR2), progression non-bloquante (NFR3)
- Résilience : persistance CSV immédiate (NFR4), isolation des erreurs unitaires (NFR5), retry réseau avec backoff (NFR6), reprise idempotente (NFR7)
- Sécurité : browser.json exclu du git (NFR8), aucune donnée musicale transmise (NFR9)
- Intégration : version ytmusicapi fixée (NFR10), CSV Excel-compatible UTF-8 BOM (NFR11)
- Maintenabilité : config centralisée sans valeur hardcodée (NFR12), fonctions de scoring isolées (NFR13)

**Scale & Complexity :**
- Primary domain : Pipeline CLI local / data processing
- Complexity level : Faible (outil personnel single-user, greenfield)
- Estimated architectural components : 3 (scanner, matcher, importer) + 1 artefact central (library.csv) + 1 config (config.yaml)

### Technical Constraints & Dependencies

- **ytmusicapi** : bibliothèque non-officielle (risque de rupture), version fixée dans requirements.txt comme mitigation. Isolation recommandée.
- **browser.json** : authentification à durée de vie limitée, détection préemptive requise au démarrage de matcher et importer.
- **50 000+ fichiers** : impose un traitement streaming (pas de chargement batch en mémoire).
- **CSV comme interface** : format partagé entre phases ET interface de review humaine — encodage UTF-8 BOM, compatibilité Excel non-négociable.
- **Exécution locale uniquement** : pas de réseau, pas de base de données, pas de serveur — outil terminal Python standard.

### Cross-Cutting Concerns Identified

- **Persistance CSV immédiate** : chaque phase doit écrire ligne par ligne, jamais en batch
- **Machine à états des statuts** : 8 statuts explicites traversent les 3 phases — transitions définies et contrôlées
- **Idempotence** : chaque phase relit le CSV existant et ignore les lignes déjà finalisées
- **Rate limiting & résilience réseau** : backoff exponentiel partagé entre matcher et importer
- **Configuration centralisée** : tous les paramètres via config.yaml, accessible dans les 3 scripts

## Starter Template Evaluation

### Primary Technology Domain

Pipeline CLI local Python — exécution directe de scripts, sans framework web, API ou interface graphique.

### Starter Options Considered

- **Cookiecutter Python CLI** : écarté — conçu pour distribution pip, hors scope v1
- **Poetry / pyproject.toml** : écarté — surengineering pour outil personnel local sans packaging
- **Structure plate minimale** : retenue — correspond exactement aux exigences du PRD et au niveau d'ambition v1

### Selected Starter: Structure plate Python standard

**Rationale for Selection :**
Le PRD définit déjà la structure complète du projet. Aucun argument CLI n'est requis (tout passe par config.yaml). Le projet n'a pas vocation à être distribué ou packagé en v1. La structure plate minimise la friction de mise en place et maximise la lisibilité.

**Initialisation du projet (Story 1.1) :**

```bash
mkdir Youtube_upload_playlists && cd Youtube_upload_playlists
touch scanner.py matcher.py importer.py config.yaml requirements.txt .gitignore
# notebook.ipynb : créé depuis Jupyter
```

**Architectural Decisions Provided by Starter :**

**Language & Runtime :** Python 3.x, exécution directe via interpréteur

**Dépendances :** requirements.txt avec versions fixées — ytmusicapi, tinytag, rapidfuzz, pyyaml, tqdm

**Configuration :** config.yaml (pyyaml) — aucune valeur hardcodée

**Tests & Debug :** notebook.ipynb pour tests sur sous-ensemble avant full run

**Code Organization :** 3 scripts indépendants + 1 CSV central + 1 config. Séparation stricte des responsabilités par phase.

**Sécurité :** .gitignore excluant browser.json et library.csv

**Note :** L'initialisation de la structure est la Story 1.1 — première story à implémenter.

## Core Architectural Decisions

### Decision Priority Analysis

**Décisions critiques (bloquent l'implémentation) :**
- CSV I/O strategy (impacte chaque phase)
- Shared module structure (impacte tous les scripts)
- Python version cible

**Décisions importantes (façonnent l'architecture) :**
- Stratégie de mise à jour CSV (persistance immédiate NFR4)
- Backoff exponentiel manuel

**Décisions différées (post-MVP) :**
- Interface de review interactive (Phase 2 PRD)
- Support playlists locales (Phase 2 PRD)

### Data Architecture

**Bibliothèque CSV I/O :** `csv` module standard Python
- Rationale : streaming natif, empreinte mémoire minimale, aucune dépendance externe, parfaitement adapté à 50k+ lignes
- Décision écartée : pandas (charge tout le CSV en RAM, surengineering pour ce cas d'usage)

**Stratégie de persistance CSV (NFR4) :**
- Au démarrage de chaque phase : chargement complet du CSV en mémoire (liste de dicts)
- Après chaque morceau traité : modification de la ligne en mémoire + réécriture complète du fichier via fichier temporaire + rename atomique
- Rationale : garantit l'atomicité de chaque écriture — en cas d'arrêt brutal, seul le morceau en cours peut être perdu. Taille max du CSV estimée à ~5–10 Mo (données texte) : le chargement initial en mémoire est négligeable.

**Encodage CSV :** UTF-8 BOM (`utf-8-sig` en Python)
- Requis par NFR11 pour compatibilité Microsoft Excel

**Constantes de statuts :** définies dans `utils.py`
- 8 statuts : `pending`, `imported`, `low_confidence`, `failed`, `duplicate`, `manual_review`, `already_exists`, `error_read`
- Source unique de vérité partagée entre les 3 scripts

### Authentication & Security

**Authentification YouTube Music :** browser.json
- Généré une seule fois via `ytmusicapi browser`
- Validation préemptive au démarrage de matcher et importer (appel test léger avant de traiter la première ligne CSV)
- Exclu du git via `.gitignore` (NFR8)
- Aucune credential hardcodée (NFR12)

### API & Communication Patterns

**Résilience réseau — Backoff exponentiel :** implémentation manuelle
- Pattern : `time.sleep(2 ** attempt)` dans un `try/except`, max 3 tentatives, puis statut `failed` si échec persistant
- Décision écartée : `tenacity` (overhead injustifié pour 5 lignes de code transparent)
- Appliqué dans : `matcher.py` et `importer.py`

**Rate limiting :** pause configurable `rate_limit_sleep` (config.yaml)
- Appliquée entre chaque appel API dans matcher et importer

### Infrastructure & Deployment

**Runtime :** Python 3.12.11
- Syntaxe `str | None` (PEP 604), `match/case` (PEP 634) disponibles — utilisables pour la machine à états des statuts
- Exécution locale uniquement, aucun déploiement requis

**Dépendances :** requirements.txt avec versions fixées (NFR10)
- ytmusicapi, tinytag, rapidfuzz, pyyaml, tqdm

**Pas de CI/CD, pas de conteneurisation** — outil personnel local.

### Shared Module Architecture

**`utils.py` — Module partagé** (NFR12, NFR13)
Contient :
- `load_config()` : chargement et validation de config.yaml
- `read_csv()` : lecture du CSV → liste de dicts
- `write_csv()` : réécriture atomique (temp file + rename)
- `STATUS_*` : constantes des 8 statuts
- `clean_title()` : nettoyage des annotations parasites (isolé, NFR13)

### Decision Impact Analysis

**Séquence d'implémentation :**
1. Story 1.1 — Structure projet + utils.py (STATUS constants, load_config)
2. Story 1.2 — config.yaml complet + validation au démarrage
3. Story 1.3/1.4 — Authentification browser.json
4. Story 2.x — scanner.py (csv read/write via utils)
5. Story 3.x — matcher.py (csv + ytmusicapi + backoff)
6. Story 4.x — importer.py (csv + ytmusicapi + backoff)

**Dépendances croisées :**
- `utils.py` est un prérequis de tous les autres scripts
- `library.csv` est l'interface contractuelle entre les 3 phases — son schéma (10 colonnes) est figé dès Story 2.4

## Implementation Patterns & Consistency Rules

### Critical Conflict Points Identified

7 zones où des agents IA pourraient faire des choix incompatibles :
naming Python, idiome CSV I/O, conditions d'idempotence, gestion des erreurs, validation de config, console output, backoff.

### Naming Patterns

**Code Python — Convention unique : snake_case partout**
- Fonctions : `load_config()`, `read_csv()`, `clean_title()`
- Variables : `music_folder`, `confidence_threshold`, `yt_video_id`
- Constantes de statuts : chaînes minuscules littérales (`"pending"`, `"imported"`, `"failed"`) — pas d'enum, pas de caps
- Fichiers : `scanner.py`, `matcher.py`, `importer.py`, `utils.py`

**Constantes de statuts — Source unique dans utils.py :**
```python
# utils.py — SEULE source de vérité
STATUS_PENDING        = "pending"
STATUS_IMPORTED       = "imported"
STATUS_LOW_CONFIDENCE = "low_confidence"
STATUS_FAILED         = "failed"
STATUS_DUPLICATE      = "duplicate"
STATUS_MANUAL_REVIEW  = "manual_review"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_ERROR_READ     = "error_read"
```
Tous les scripts importent ces constantes. Jamais de chaîne littérale de statut hors de utils.py.

**Colonnes CSV — Noms figés (schéma contrat) :**
`filepath`, `artist`, `title`, `album`, `duration`, `status`, `yt_video_id`, `yt_url`, `yt_score`, `error_message`
Ces noms ne doivent JAMAIS varier entre les scripts.

### Structure Patterns

**Organisation du projet (plate, à la racine) :**
```
Youtube_upload_playlists/
  utils.py          ← prérequis de tout le reste
  scanner.py
  matcher.py
  importer.py
  config.yaml
  library.csv       ← généré, dans .gitignore
  browser.json      ← généré, dans .gitignore
  requirements.txt
  .gitignore
  notebook.ipynb
```
Aucun sous-dossier, aucun package Python (pas de `__init__.py`).
Les imports se font avec `from utils import ...` (pas `import utils`).

**Imports dans chaque script :**
```python
from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_IMPORTED, ...  # importer uniquement ce qui est utilisé
)
```

### Format Patterns

**Idiome CSV — Lecture (via utils.read_csv) :**
```python
def read_csv(filepath: str) -> list[dict]:
    if not Path(filepath).exists():
        return []
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))
```

**Idiome CSV — Écriture atomique (via utils.write_csv) :**
```python
def write_csv(filepath: str, rows: list[dict], fieldnames: list[str]) -> None:
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    Path(tmp).replace(filepath)  # rename atomique
```
Toujours passer par `write_csv()`. Jamais d'écriture CSV directe dans scanner/matcher/importer.

**Chargement de config — Pattern obligatoire :**
```python
def load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    required = ["music_folder", "confidence_threshold", ...]
    for key in required:
        if key not in config:
            sys.exit(f"[CONFIG ERROR] Paramètre manquant : '{key}'")
    return config
```
Appel en première ligne de `main()` dans chaque script.
Toujours `sys.exit()` (pas `raise`, pas `print` seul) sur erreur de config.

### Communication Patterns

**Console output — Règles de format :**
```python
# Progression : toujours via tqdm (jamais print dans la boucle principale)
for row in tqdm(rows, desc="Matching", unit="track"):
    ...

# Statut non-standard : print AVANT mise à jour tqdm
print(f"⚠  {row['artist']} — {row['title']} → {new_status}")

# Erreur critique (arrêt) : sys.exit avec préfixe [ERROR]
sys.exit("[ERROR] browser.json manquant — exécutez `ytmusicapi browser`")
```

**Résumé de fin de run — Format obligatoire :**
```python
counts = {s: sum(1 for r in rows if r["status"] == s) for s in ALL_STATUSES}
print(f"\n✅ imported:       {counts[STATUS_IMPORTED]}")
print(f"⚠  low_confidence:  {counts[STATUS_LOW_CONFIDENCE]}")
print(f"📋 manual_review:   {counts[STATUS_MANUAL_REVIEW]}")
# ... tous les statuts
```

### Process Patterns

**Pattern d'idempotence par phase :**

scanner.py — skip si filepath déjà dans le CSV (quel que soit le statut) :
```python
existing_paths = {r["filepath"] for r in existing_rows}
if filepath in existing_paths:
    continue
```

matcher.py — traite uniquement `pending` sans `yt_video_id` :
```python
if row["status"] != STATUS_PENDING or row["yt_video_id"]:
    continue
```

importer.py — traite uniquement `pending` avec `yt_video_id` :
```python
if row["status"] != STATUS_PENDING or not row["yt_video_id"]:
    continue
```

**Pattern de backoff exponentiel (matcher & importer) :**
```python
MAX_RETRIES = 3
for attempt in range(MAX_RETRIES):
    try:
        result = ytmusic.some_call(...)
        break
    except Exception as e:
        if attempt == MAX_RETRIES - 1:
            row["status"] = STATUS_FAILED
            row["error_message"] = str(e)
        else:
            time.sleep(2 ** attempt)
```
Toujours `MAX_RETRIES = 3`, toujours `2 ** attempt` (0s, 2s, 4s).
Jamais de retry infini. Défini comme constante en haut du fichier.

**Gestion des erreurs unitaires (isolation NFR5) :**
```python
try:
    # traitement d'un morceau
except Exception as e:
    row["status"] = STATUS_ERROR_READ  # ou STATUS_FAILED selon le contexte
    row["error_message"] = str(e)[:200]  # tronqué pour lisibilité CSV
    print(f"⚠  Erreur : {row['filepath']} — {e}")
finally:
    write_csv(CSV_PATH, rows, FIELDNAMES)  # toujours persister
```

### Enforcement Guidelines

**Tous les agents IA DOIVENT :**
- Importer `STATUS_*` depuis `utils.py` — jamais de chaîne de statut inline
- Passer par `read_csv()` et `write_csv()` de utils — jamais d'accès CSV direct
- Appeler `load_config()` en première ligne de `main()`
- Respecter la condition d'idempotence exacte de chaque phase
- Utiliser `sys.exit()` pour les erreurs fatales (config, browser.json)
- Écrire le CSV via `write_csv()` dans le bloc `finally` de la boucle principale
- Utiliser `MAX_RETRIES = 3` et `time.sleep(2 ** attempt)` pour le backoff

**Anti-patterns à éviter :**
```python
# ❌ Chaîne de statut inline
row["status"] = "imported"          # → row["status"] = STATUS_IMPORTED

# ❌ Écriture CSV directe
with open("library.csv", "w") as f: # → write_csv(CSV_PATH, rows, FIELDNAMES)
    ...

# ❌ raise sur erreur de config
raise ValueError("missing key")     # → sys.exit("[CONFIG ERROR] ...")

# ❌ Retry infini
while True: ...                     # → for attempt in range(MAX_RETRIES):

# ❌ print dans la boucle principale (casse tqdm)
print(f"Processing {title}")        # → utiliser tqdm desc ou log hors boucle
```

## Project Structure & Boundaries

### Complete Project Directory Structure

```
Youtube_upload_playlists/
├── utils.py          ← Module partagé (prérequis de tout le reste)
├── scanner.py        ← Phase 1 : scan local → library.csv
├── matcher.py        ← Phase 2 : library.csv → enrichissement YTM
├── importer.py       ← Phase 3 : library.csv → import YTM
├── config.yaml       ← Configuration centralisée
├── requirements.txt  ← Dépendances avec versions fixées
├── .gitignore        ← Exclut : browser.json, library.csv, *.tmp, __pycache__/
├── notebook.ipynb    ← Tests sur sous-ensemble avant full run
├── library.csv       ← [GÉNÉRÉ] Artefact central (dans .gitignore)
└── browser.json      ← [GÉNÉRÉ] Auth YTMusic (dans .gitignore)
```

Aucun sous-dossier. Aucun package Python (`__init__.py`).
Aucun fichier de test formel en v1 (couvert par notebook.ipynb).

### Architectural Boundaries

**Frontières d'accès par composant :**

| Composant | Lit | Écrit | Dépendances externes |
|---|---|---|---|
| `utils.py` | config.yaml, library.csv | library.csv | pyyaml, csv, pathlib |
| `scanner.py` | dossier musique, library.csv | library.csv | tinytag, tqdm + utils |
| `matcher.py` | library.csv, browser.json | library.csv | ytmusicapi, rapidfuzz, tqdm + utils |
| `importer.py` | library.csv, browser.json | library.csv | ytmusicapi, tqdm + utils |
| `notebook.ipynb` | tout | expérimental | tous |

**Règle d'isolation :**
- `tinytag` : encapsulé dans `scanner.py` uniquement
- `ytmusicapi` : encapsulé dans `matcher.py` et `importer.py` uniquement
- `rapidfuzz` : encapsulé dans `utils.py` (`score_match()`) — importé par matcher
- `browser.json` : jamais lu par `scanner.py`

**Frontière du schéma CSV (figée dès Story 2.4) :**
```python
FIELDNAMES = [
    "filepath", "artist", "title", "album", "duration",
    "status", "yt_video_id", "yt_url", "yt_score", "error_message"
]
```
Cette liste est définie dans `utils.py` et importée par les 3 scripts.
Toute modification du schéma casse le contrat inter-phases.

### Requirements to Structure Mapping

**Epic 1 — Setup & Authentification**
- Story 1.1 → tous les fichiers (scaffolding initial)
- Story 1.2 → `config.yaml` + `utils.py` (`load_config()`, validation)
- Story 1.3 → `.gitignore` (browser.json, library.csv)
- Story 1.4 → `matcher.py` + `importer.py` (validation préemptive browser.json)

**Epic 2 — Scan Bibliothèque Locale**
- Story 2.1 → `scanner.py` (scan récursif, tinytag, filtrage extensions)
- Story 2.2 → `scanner.py` (try/except fichiers corrompus → STATUS_ERROR_READ)
- Story 2.3 → `scanner.py` (déduplication par artist+title normalisés)
- Story 2.4 → `scanner.py` + `utils.py` (write_csv, FIELDNAMES, encodage utf-8-sig)

**Epic 3 — Matching & Scoring**
- Story 3.1 → `matcher.py` + `utils.py` (`clean_title()`, STATUS_MANUAL_REVIEW)
- Story 3.2 → `matcher.py` + `utils.py` (`score_match()`, vérification durée)
- Story 3.3 → `matcher.py` + `utils.py` (write_csv atomique, yt_url)
- Story 3.4 → `matcher.py` (backoff exponentiel, tqdm, stabilité mémoire)

**Epic 4 — Import YouTube Music**
- Story 4.1 → `importer.py` (import YTM, STATUS_IMPORTED, STATUS_ALREADY_EXISTS)
- Story 4.2 → `importer.py` (backoff, rate_limit_sleep)
- Story 4.3 → `importer.py` + `utils.py` (write_csv finally, idempotence)
- Story 4.4 → `importer.py` (tqdm, résumé par statut)

**Epic 5 — Review Manuelle**
- Story 5.1 → `library.csv` (workflow Excel, pas de code)
- Story 5.2 → `importer.py` (re-run idempotent, couvert par Story 4.3)

**Préoccupations transversales → utils.py :**
- `load_config()` : Epic 1 → utilisé par Epic 2, 3, 4
- `read_csv()` / `write_csv()` / `FIELDNAMES` : Epic 2 → utilisé par Epic 3, 4
- `STATUS_*` : Epic 2 → utilisé par Epic 3, 4, 5
- `clean_title()` / `score_match()` : Epic 3 → utilisé par matcher uniquement

### Integration Points

**Flux de données (pipeline séquentiel) :**
```
[Dossier musique local]
        │ tinytag
        ▼
   scanner.py ──write──► library.csv (pending / duplicate / error_read)
                                │
                          read ─┤ ytmusicapi + rapidfuzz
                                ▼
   matcher.py ──write──► library.csv (+ yt_video_id, yt_url, yt_score
                                       pending / low_confidence /
                                       manual_review / failed)
                                │
                          read ─┤ ytmusicapi
                                ▼
  importer.py ──write──► library.csv (imported / already_exists / failed)
                                │
                         [Excel — review manuelle]
                                │ statuts corrigés → pending
                                ▼
  importer.py ──write──► library.csv (final)
```

**Intégrations externes :**
- `ytmusicapi` : HTTP vers YouTube Music (non-officiel, navigateur-based)
- `browser.json` : headers navigateur → auth YTMusic (durée de vie limitée)
- Aucune autre intégration réseau ou base de données

### Development Workflow Integration

**Workflow d'exécution :**
```bash
pip install -r requirements.txt      # installation
ytmusicapi browser                   # auth (une seule fois)
python scanner.py                    # Phase 1
python matcher.py                    # Phase 2
python importer.py                   # Phase 3
# [review Excel sur library.csv]
python importer.py                   # re-run après corrections manuelles
```

Pas de build, pas de compilation, pas de déploiement.
L'environnement de développement = l'environnement d'exécution.

## Architecture Validation Results

### Coherence Validation ✅

**Decision Compatibility :** Aucun conflit entre les décisions.
Stack Python 3.12.11 entièrement compatible. csv module cohérent avec contrainte mémoire. utils.py cohérent avec NFR12/NFR13. Backoff manuel cohérent avec la décision zéro-dépendance-supplémentaire.

**Pattern Consistency :** snake_case, STATUS_*, sys.exit(), tqdm — patterns alignés avec Python standard et type d'outil CLI. Pas de contradiction identifiée.

**Structure Alignment :** Structure plate cohérente avec no-packaging. FIELDNAMES partagé depuis utils.py correct. Frontières d'accès respectées par composant.

### Requirements Coverage Validation ✅

**Epic Coverage :** 5/5 epics couverts, 18/18 stories mappées à des fichiers spécifiques.

**Functional Requirements :** 37/37 FR couverts architecturalement.
- FR1–FR8 : config.yaml + utils.load_config() + browser.json validation préemptive
- FR9–FR15 : scanner.py (tinytag, dédup, error_read, idempotence filepath)
- FR16–FR21, FR37 : matcher.py + utils (clean_title, score_match, yt_url)
- FR22–FR29 : importer.py (ytmusicapi, backoff, rate_limit, write_csv finally)
- FR30–FR33 : importer.py (tqdm, print statuts non-standard, résumé final)
- FR34–FR36 : library.csv Excel + re-run idempotent importer.py

**Non-Functional Requirements :** 13/13 NFR couverts.
- NFR1 : csv streaming, aucun chargement audio en RAM
- NFR2 : streaming par morceau, pas d'accumulation mémoire
- NFR3 : tqdm non-bloquant
- NFR4 : write_csv dans bloc finally après chaque morceau
- NFR5 : try/except par morceau, isolation totale des erreurs unitaires
- NFR6 : backoff exponentiel MAX_RETRIES=3
- NFR7 : conditions d'idempotence strictes et différenciées par phase
- NFR8 : .gitignore excluant browser.json
- NFR9 : pas d'upload, matching uniquement
- NFR10 : requirements.txt avec versions fixées
- NFR11 : encodage utf-8-sig (UTF-8 BOM)
- NFR12 : zéro valeur hardcodée, tout via config.yaml
- NFR13 : clean_title() et score_match() isolés dans utils.py

### Gap Analysis Results

**Gaps mineurs résolus dans ce document :**

Gap 1 — `ALL_STATUSES` : ajouter dans utils.py :
```python
ALL_STATUSES = [
    STATUS_PENDING, STATUS_IMPORTED, STATUS_LOW_CONFIDENCE,
    STATUS_FAILED, STATUS_DUPLICATE, STATUS_MANUAL_REVIEW,
    STATUS_ALREADY_EXISTS, STATUS_ERROR_READ
]
```

Gap 2 — Seuil bas `low_confidence` : ajouter dans config.yaml :
```yaml
low_confidence_threshold: 70  # score rapidfuzz entre 70 et confidence_threshold
```
Valeur 70 issue du Parcours 3 du PRD. Configurable pour ajustement post-run.

**Aucun gap critique identifié.**

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] Contexte projet analysé (37 FR, 13 NFR, 5 epics, 18 stories)
- [x] Échelle et complexité évaluées (faible, outil local single-user)
- [x] Contraintes techniques identifiées (ytmusicapi non-officiel, browser.json, volume 50k+)
- [x] Préoccupations transversales mappées (CSV, statuts, idempotence, rate limiting)

**✅ Architectural Decisions**
- [x] Décisions critiques documentées avec rationale (csv module, utils.py, Python 3.12.11)
- [x] Stack technologique entièrement spécifié (5 dépendances, versions à fixer)
- [x] Patterns d'intégration définis (flux pipeline, frontières par composant)
- [x] Considérations de performance adressées (streaming, mémoire stable, tqdm)

**✅ Implementation Patterns**
- [x] Conventions de nommage établies (snake_case, STATUS_* constants, FIELDNAMES)
- [x] Patterns de structure définis (utils.py prérequis, imports explicites)
- [x] Patterns de communication spécifiés (tqdm, print hors boucle, sys.exit)
- [x] Patterns de process documentés avec code (idempotence, backoff, gestion erreurs)

**✅ Project Structure**
- [x] Structure de répertoire complète définie (10 fichiers, 0 sous-dossier)
- [x] Frontières de composants établies (tableau accès par composant)
- [x] Points d'intégration mappés (flux de données, schéma CSV contrat)
- [x] Mapping requirements → structure complet (story par story, epic par epic)

### Architecture Readiness Assessment

**Overall Status : PRÊT POUR IMPLÉMENTATION**

**Confidence Level : Haute** — architecture simple, décisions sans ambiguïté, patterns concrets avec exemples de code, tous les FR/NFR couverts, gaps mineurs résolus.

**Points forts :**
- Patterns avec code concret → zéro ambiguïté pour les agents IA
- Conditions d'idempotence exactes et différenciées par phase → pas de conflit entre runs
- Schéma CSV figé dès Story 2.4 → interface contractuelle stable entre phases
- utils.py comme prérequis explicite → ordre d'implémentation clair

**Axes d'amélioration futurs (post-MVP) :**
- Interface de review interactive pour low_confidence / manual_review (Phase 2 PRD)
- Support des playlists locales (Phase 2 PRD)
- Tests formels pytest si l'outil évolue vers distribution publique (Phase 3 PRD)

### Implementation Handoff

**Premier pas d'implémentation : Story 1.1**
```bash
mkdir Youtube_upload_playlists && cd Youtube_upload_playlists
touch utils.py scanner.py matcher.py importer.py
touch config.yaml requirements.txt .gitignore
```
Implémenter `utils.py` en premier (STATUS_*, ALL_STATUSES, FIELDNAMES, load_config, read_csv, write_csv, clean_title, score_match) — prérequis de toutes les autres stories.

**AI Agent Guidelines :**
- Suivre toutes les décisions architecturales exactement telles que documentées
- Utiliser les patterns d'implémentation de manière cohérente entre tous les scripts
- Respecter la structure du projet et les frontières des composants
- Référencer ce document pour toutes les questions architecturales
- Commencer par `utils.py` avant tout autre script
- Ne jamais modifier le schéma FIELDNAMES du CSV sans mettre à jour les 3 scripts
