# Story 1.1 : Initialisation de la structure du projet

Status: review

<!-- Note: Validation optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant que développeur,
je veux un projet scaffoldé avec tous les fichiers requis,
afin de pouvoir démarrer le développement sans friction de mise en place.

## Critères d'acceptation

**AC1 — Installation des dépendances**

**Given** je clone le dépôt sur une machine vierge
**When** j'exécute `pip install -r requirements.txt`
**Then** toutes les dépendances (`ytmusicapi`, `tinytag`, `rapidfuzz`, `pyyaml`, `tqdm`) s'installent sans erreur
**And** les versions sont fixées dans `requirements.txt`

**AC2 — Structure des fichiers**

**Given** le projet est initialisé
**When** j'inspecte la structure du projet
**Then** les fichiers `scanner.py`, `matcher.py`, `importer.py`, `notebook.ipynb`, `config.yaml`, `requirements.txt`, `.gitignore` existent à la racine
**And** `browser.json` et `library.csv` sont listés dans `.gitignore`

**AC3 — Exécution sans erreur d'import**

**Given** les fichiers sont créés
**When** j'exécute `python scanner.py`, `python matcher.py` ou `python importer.py`
**Then** les scripts s'exécutent sans erreur d'import (même avec une logique vide)

## Tâches / Sous-tâches

- [x] Créer `utils.py` avec toutes les constantes, types et fonctions partagées (AC: 1, 2, 3)
  - [x] Définir les 8 constantes `STATUS_*` et `ALL_STATUSES`
  - [x] Définir `FIELDNAMES` (10 colonnes CSV)
  - [x] Implémenter `load_config()` avec validation des clés requises
  - [x] Implémenter `read_csv()` avec encodage UTF-8 BOM (`utf-8-sig`)
  - [x] Implémenter `write_csv()` avec écriture atomique (fichier temporaire + rename)
  - [x] Implémenter `clean_title()` (suppression des annotations parasites)
  - [x] Implémenter `score_match()` (utilise `rapidfuzz.fuzz.token_sort_ratio`)
- [x] Créer `scanner.py` avec imports depuis `utils` et bloc `main()` vide (AC: 3)
- [x] Créer `matcher.py` avec imports depuis `utils` et bloc `main()` vide (AC: 3)
- [x] Créer `importer.py` avec imports depuis `utils` et bloc `main()` vide (AC: 3)
- [x] Créer `config.yaml` avec tous les paramètres initiaux (AC: 2)
- [x] Créer `requirements.txt` avec versions fixées (AC: 1)
- [x] Créer `.gitignore` avec les exclusions requises (AC: 2)
- [x] Créer `notebook.ipynb` (notebook Jupyter vide ou minimal) (AC: 2)
- [x] Vérifier que `python scanner.py`, `python matcher.py`, `python importer.py` s'exécutent sans erreur d'import (AC: 3)

## Notes développeur

### Contexte architectural critique

Cette story est le **fondement absolu de toutes les stories suivantes**. L'ordre de priorité est strict :

1. **`utils.py` EN PREMIER** — Prérequis absolu de tous les autres scripts. Toutes les stories 1.2 à 5.2 l'importent.
2. **Scripts squelettes** (`scanner.py`, `matcher.py`, `importer.py`) — Imports + `main()` vide uniquement.
3. **Fichiers de support** (`config.yaml`, `requirements.txt`, `.gitignore`, `notebook.ipynb`).

> ⚠️ **CRITICAL :** Ne pas commencer `scanner.py`, `matcher.py` ou `importer.py` avant que `utils.py` soit complet et fonctionnel. `utils.py` est le contrat partagé entre toutes les phases.

---

### Implémentation complète de `utils.py`

`utils.py` doit être **complet et définitif dès cette story**. Il ne sera pas refactorisé — toutes les stories suivantes l'utilisent tel quel. Voici l'implémentation attendue :

```python
# utils.py — Module partagé (Source: architecture.md — "Shared Module Architecture")
import csv
import re
import sys
import yaml
from pathlib import Path

from rapidfuzz import fuzz

# ─── Constantes de statuts (source unique de vérité — NFR12) ─────────────────
# JAMAIS de chaîne de statut inline dans les autres scripts
STATUS_PENDING        = "pending"
STATUS_IMPORTED       = "imported"
STATUS_LOW_CONFIDENCE = "low_confidence"
STATUS_FAILED         = "failed"
STATUS_DUPLICATE      = "duplicate"
STATUS_MANUAL_REVIEW  = "manual_review"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_ERROR_READ     = "error_read"

ALL_STATUSES = [
    STATUS_PENDING, STATUS_IMPORTED, STATUS_LOW_CONFIDENCE,
    STATUS_FAILED, STATUS_DUPLICATE, STATUS_MANUAL_REVIEW,
    STATUS_ALREADY_EXISTS, STATUS_ERROR_READ
]

# ─── Schéma CSV — contrat figé entre les 3 phases (Source: architecture.md — "Architectural Boundaries") ──
# NE JAMAIS modifier sans mettre à jour les 3 scripts
FIELDNAMES = [
    "filepath", "artist", "title", "album", "duration",
    "status", "yt_video_id", "yt_url", "yt_score", "error_message"
]

# ─── Chargement et validation de la configuration ────────────────────────────
def load_config(path: str = "config.yaml") -> dict:
    """Charge config.yaml et valide les clés requises. sys.exit() si manquant."""
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    required = [
        "music_folder", "confidence_threshold", "duration_tolerance",
        "supported_extensions", "filter_live", "api_delay",
        "low_confidence_threshold", "rate_limit_sleep"
    ]
    for key in required:
        if key not in config:
            sys.exit(f"[CONFIG ERROR] Paramètre manquant dans config.yaml : '{key}'")
    return config

# ─── Lecture CSV ──────────────────────────────────────────────────────────────
def read_csv(filepath: str) -> list[dict]:
    """Retourne [] si le fichier n'existe pas. Décode UTF-8 BOM (Excel-compatible)."""
    if not Path(filepath).exists():
        return []
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

# ─── Écriture atomique CSV ────────────────────────────────────────────────────
def write_csv(filepath: str, rows: list[dict], fieldnames: list[str] = None) -> None:
    """Réécriture atomique via fichier temporaire + rename. NFR4 : aucune perte en cas d'arrêt brutal."""
    if fieldnames is None:
        fieldnames = FIELDNAMES
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    Path(tmp).replace(filepath)  # rename atomique

# ─── Nettoyage des titres (isolé — NFR13) ─────────────────────────────────────
_NOISE_PATTERNS = [
    r'\(remaster(?:ed|ing)?\b[^)]*\)',
    r'\[remaster[^\]]*\]',
    r'\(live\b[^)]*\)',
    r'\[live[^\]]*\]',
    r'\bfeat\.?\s+[^,)([\]]+',
    r'\s*-\s*radio edit\b',
    r'\s*-\s*single version\b',
    r'\s*-\s*album version\b',
    r'\s*-\s*explicit\b',
    r'\s*[\(\[].*?[\)\]]',  # tout contenu entre parenthèses/crochets restant
]
_NOISE_RE = re.compile('|'.join(_NOISE_PATTERNS), re.IGNORECASE)

def clean_title(title: str) -> str:
    """Supprime les annotations parasites d'un titre avant recherche YouTube Music."""
    cleaned = _NOISE_RE.sub('', title)
    return ' '.join(cleaned.split()).strip()

# ─── Score de similarité (isolé — NFR13) ──────────────────────────────────────
def score_match(local_artist: str, local_title: str,
                yt_artist: str, yt_title: str) -> int:
    """
    Calcule un score 0–100 de similarité entre morceau local et résultat YouTube Music.
    Utilise token_sort_ratio pour gérer les variations d'ordre des mots.
    """
    local_str = f"{local_artist} {local_title}".lower().strip()
    yt_str    = f"{yt_artist} {yt_title}".lower().strip()
    return int(fuzz.token_sort_ratio(local_str, yt_str))
```

---

### Scripts squelettes attendus

Ces scripts doivent **uniquement** contenir les imports et un `main()` vide pour l'instant. La logique métier sera ajoutée dans les stories suivantes.

**`scanner.py`** :
```python
from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_DUPLICATE, STATUS_ERROR_READ, FIELDNAMES
)

def main():
    config = load_config()
    # TODO Story 2.1 : scan récursif et lecture ID3
    # TODO Story 2.2 : gestion des fichiers corrompus
    # TODO Story 2.3 : détection des doublons
    # TODO Story 2.4 : export CSV et idempotence
    pass

if __name__ == "__main__":
    main()
```

**`matcher.py`** :
```python
from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_LOW_CONFIDENCE, STATUS_FAILED, STATUS_MANUAL_REVIEW,
    FIELDNAMES, clean_title, score_match
)

def main():
    config = load_config()
    # TODO Story 3.1 : recherche YouTube Music + nettoyage titres
    # TODO Story 3.2 : scoring de similarité + vérification durée
    # TODO Story 3.3 : génération URLs + persistance CSV
    # TODO Story 3.4 : résilience réseau + progression
    pass

if __name__ == "__main__":
    main()
```

**`importer.py`** :
```python
from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
    ALL_STATUSES, FIELDNAMES
)

def main():
    config = load_config()
    # TODO Story 4.1 : import morceaux matchés + gestion statuts
    # TODO Story 4.2 : résilience réseau + rate limiting
    # TODO Story 4.3 : persistance CSV + reprise automatique
    # TODO Story 4.4 : suivi temps réel + résumé de fin de run
    pass

if __name__ == "__main__":
    main()
```

---

### `config.yaml` — Contenu initial complet

```yaml
# Configuration de Youtube_upload_playlists
# Tous les paramètres passent par ce fichier — aucune valeur hardcodée (NFR12)

music_folder: "/path/to/your/music"        # À modifier : chemin vers le dossier musique local

confidence_threshold: 85                   # Score minimum pour accepter un match (0–100)
low_confidence_threshold: 70               # Score minimum pour low_confidence (valeur PRD Parcours 3)
duration_tolerance: 10                     # Tolérance en secondes pour vérification de durée

supported_extensions:                      # Filtrage des fichiers non-audio
  - .mp3
  - .flac
  - .m4a
  - .ogg
  - .wav
  - .aac
  - .wma

filter_live: true                          # Exclure les versions live des résultats YouTube Music

api_delay: 1.0                             # Pause en secondes entre appels API (matcher & importer)
rate_limit_sleep: 1.0                      # Délai supplémentaire sur HTTP 429 (importer)
```

---

### `requirements.txt` — Versions fixées (NFR10)

```
ytmusicapi==1.11.5
tinytag==2.2.0
rapidfuzz==3.14.3
pyyaml==6.0.3
tqdm==4.67.3
```

> ⚠️ **Note versions :** Versions vérifiées et actualisées au 2026-02-22. Le principe de verrouillage reste impératif (NFR10).

> 🚨 **BREAKING CHANGE tinytag 2.x** (vs 1.x) — Impact sur Story 2.2 :
> - Le paramètre `ignore_errors=True` de `TinyTag.get()` est **déprécié** → utiliser `try/except TinyTagException` pour isoler les fichiers corrompus
> - `disc`, `track` retournent maintenant des `int` (plus des `str`) — pas d'impact sur notre usage (on lit `artist`, `title`, `album`, `duration`)
> - L'API de base reste identique : `tag = TinyTag.get(filepath)` → `tag.artist`, `tag.title`, `tag.album`, `tag.duration`

---

### `.gitignore` — Contenu obligatoire (NFR8)

```gitignore
# Authentification YouTube Music (contient des credentials navigateur — JAMAIS commiter)
browser.json

# Artefact généré — peut contenir des données personnelles musicales
library.csv

# Fichiers temporaires d'écriture atomique CSV
*.tmp

# Python
__pycache__/
*.pyc
*.pyo
.env
venv/
.venv/
```

---

### `notebook.ipynb` — Notebook minimal

Créer un notebook Jupyter valide (JSON bien formé) avec au minimum :
- Une cellule markdown de présentation du projet
- Une cellule de code vide (import des utils pour tester)

Si Jupyter n'est pas installé dans l'environnement, un fichier `.ipynb` JSON minimal suffit pour satisfaire l'AC2. Exemple de structure minimale :

```json
{
 "cells": [
  {
   "cell_type": "markdown",
   "metadata": {},
   "source": ["# Youtube_upload_playlists — Notebook de test\n", "Utiliser ce notebook pour tester les fonctions sur un sous-ensemble de la bibliothèque avant un full run."]
  },
  {
   "cell_type": "code",
   "execution_count": null,
   "metadata": {},
   "outputs": [],
   "source": ["from utils import load_config, read_csv, write_csv, STATUS_PENDING\n", "# config = load_config()\n", "# rows = read_csv('library.csv')\n", "print('utils importés avec succès')"]
  }
 ],
 "metadata": {
  "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
  "language_info": {"name": "python", "version": "3.12.11"}
 },
 "nbformat": 4,
 "nbformat_minor": 5
}
```

---

### Notes de structure du projet

**Structure plate à la racine (aucun sous-dossier) :**
```
Youtube_upload_playlists/
├── utils.py          ← CRÉER EN PREMIER (prérequis de tout le reste)
├── scanner.py        ← Phase 1 (squelette uniquement dans cette story)
├── matcher.py        ← Phase 2 (squelette uniquement dans cette story)
├── importer.py       ← Phase 3 (squelette uniquement dans cette story)
├── config.yaml       ← Configuration centralisée
├── requirements.txt  ← Dépendances avec versions fixées
├── .gitignore        ← Exclut browser.json, library.csv, *.tmp, __pycache__/
├── notebook.ipynb    ← Tests sur sous-ensemble (debug/validation manuelle)
├── library.csv       ← [SERA GÉNÉRÉ par scanner.py — dans .gitignore]
└── browser.json      ← [SERA GÉNÉRÉ par ytmusicapi browser — dans .gitignore]
```

**Règles d'import :**
- Toujours : `from utils import ...` (jamais `import utils`)
- Importer uniquement ce qui est utilisé dans chaque script
- Aucun `__init__.py` — pas de package Python

**Runtime cible :** Python 3.12.11 (syntaxe `list[dict]`, `str | None` disponibles)

---

### Points de vigilance architecturale — Anti-patterns à éviter absolument

```python
# ❌ Chaîne de statut inline — TOUJOURS utiliser STATUS_*
row["status"] = "imported"          # → row["status"] = STATUS_IMPORTED

# ❌ Écriture CSV directe — TOUJOURS passer par write_csv()
with open("library.csv", "w") as f: # → write_csv(CSV_PATH, rows, FIELDNAMES)
    ...

# ❌ raise ou print seul sur erreur de config
raise ValueError("missing key")     # → sys.exit("[CONFIG ERROR] ...")
print("missing key")                # → sys.exit("[CONFIG ERROR] ...")

# ❌ yaml.load() — risque de sécurité
yaml.load(f)                        # → yaml.safe_load(f)

# ❌ Appel API sans load_config() en première ligne de main()
def main():
    ytmusic = YTMusic(...)           # → config = load_config() AVANT TOUT
```

---

### Contexte technologique — Bibliothèques clés

| Bibliothèque | Rôle | Note critique |
|---|---|---|
| `ytmusicapi` | Client YouTube Music non-officiel | Version fixée — risque de rupture API |
| `tinytag` | Lecture tags ID3 légers | Faible empreinte mémoire (NFR1) |
| `rapidfuzz` | Scoring similarité textuelle | `fuzz.token_sort_ratio` recommandé |
| `pyyaml` | Config YAML | Toujours `yaml.safe_load()` |
| `tqdm` | Barre de progression | Non-bloquante dans les boucles longues |
| `csv` (stdlib) | I/O CSV streaming | Pas pandas — pour NFR1 (mémoire stable) |
| `pathlib` | Manipulation chemins | `Path(tmp).replace(filepath)` pour rename atomique |

### Références

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 1, Story 1.1 (Acceptance Criteria BDD)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Starter Template Evaluation" (structure plate, choix Python)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Shared Module Architecture" (contenu complet de utils.py)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Core Architectural Decisions" — Data Architecture (CSV I/O, persistance atomique, encodage utf-8-sig)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Naming Patterns" (snake_case, STATUS_* constants, FIELDNAMES figé)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Format Patterns" (idiomes read_csv, write_csv, load_config)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Enforcement Guidelines" (anti-patterns à éviter)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Project Structure & Boundaries" (structure répertoire, frontières composants)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Gap Analysis Results" (ALL_STATUSES, low_confidence_threshold: 70)]

## Enregistrement de l'agent dev

### Modèle d'agent utilisé

claude-sonnet-4-6

### Références de log de débogage

- Python 3.11.9 utilisé (py launcher Windows) — dépendances installées dans cet environnement
- Python 3.12.11 (MSYS2) présent mais sans les packages ; py -3.11 requis pour lancer les tests
- `pip install -r requirements.txt` : toutes dépendances déjà présentes sauf tqdm 4.67.3 (installé)

### Notes de complétion

- `utils.py` créé complet et définitif : 8 constantes STATUS_*, ALL_STATUSES, FIELDNAMES (10 colonnes), load_config(), read_csv(), write_csv() atomique, clean_title(), score_match()
- Scripts squelettes créés : scanner.py, matcher.py, importer.py — imports depuis utils + main() vide
- Fichiers de support créés : config.yaml, requirements.txt (versions fixées), .gitignore, notebook.ipynb
- AC1 validé : `pip install -r requirements.txt` sans erreur
- AC2 validé : tous les fichiers requis à la racine, browser.json et library.csv dans .gitignore
- AC3 validé : `py -3.11 scanner.py`, `py -3.11 matcher.py`, `py -3.11 importer.py` sans erreur d'import
- 26 tests unitaires (test_utils.py) : 26/26 passent

### Liste des fichiers

- `utils.py`
- `scanner.py`
- `matcher.py`
- `importer.py`
- `config.yaml`
- `requirements.txt`
- `.gitignore`
- `notebook.ipynb`
- `test_utils.py`

## Journal des modifications

- 2026-02-22 : Story 1.1 — Initialisation complète de la structure du projet. Création de utils.py (module partagé définitif), scripts squelettes (scanner, matcher, importer), fichiers de configuration (config.yaml, requirements.txt, .gitignore, notebook.ipynb). 26 tests unitaires ajoutés et passants. Tous les AC satisfaits.
