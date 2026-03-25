# Story 2.1 : Scan récursif et lecture des métadonnées ID3

Status: review

<!-- Note: Validation optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant qu'utilisateur,
je veux que le scanner parcoure récursivement mon dossier musique et lise les métadonnées de chaque fichier audio,
afin d'obtenir un inventaire complet avec artiste, titre, album et durée.

## Critères d'acceptation

**AC1 — Scan récursif de tous les sous-dossiers**

**Given** `music_folder` est configuré avec un dossier contenant des sous-dossiers imbriqués
**When** j'exécute `python scanner.py`
**Then** le scanner parcourt tous les sous-dossiers récursivement sans limitation de profondeur
**And** aucun fichier audio n'est ignoré à cause de la structure des dossiers

**AC2 — Extraction des métadonnées ID3**

**Given** un fichier audio avec tags ID3 complets
**When** le scanner traite ce fichier
**Then** les champs `artist`, `title`, `album`, `duration` sont extraits depuis les tags ID3
**And** chaque valeur est stockée avec la représentation textuelle exacte (sans conversion)

**AC3 — Gestion des tags incomplets**

**Given** un fichier audio avec tags ID3 incomplets (ex : titre manquant, album vide)
**When** le scanner traite ce fichier
**Then** le champ manquant est laissé vide (chaîne vide `""`) sans erreur
**And** le fichier est quand même inclusdans `library.csv` avec le statut `pending`

**AC4 — Filtrage des fichiers non-audio**

**Given** un dossier contenant des fichiers non-audio (ex : `.jpg`, `.txt`, `.nfo`, `.cue`, `.m3u`)
**When** le scanner rencontre ces fichiers
**Then** ils sont ignorés, conformément aux extensions configurées dans `supported_extensions` (config.yaml)
**And** seuls les fichiers `.mp3`, `.flac`, `.m4a`, `.ogg`, `.wav`, `.aac`, `.wma` sont traités

**AC5 — Persistance initiale dans library.csv**

**Given** le scan récursif est terminé
**When** j'inspecte `library.csv`
**Then** chaque ligne contient les colonnes FIELDNAMES exactement : `filepath`, `artist`, `title`, `album`, `duration`, `status`, `yt_video_id`, `yt_url`, `yt_score`, `error_message`
**And** tous les fichiers audio trouvés ont le statut `pending` (sauf cas spéciaux traités en 2.2–2.4)
**And** les colonnes `yt_video_id`, `yt_url`, `yt_score`, `error_message` sont vides
**And** la durée est enregistrée en secondes (nombre entier ou décimal selon tinytag)

## Tâches / Sous-tâches

- [x] Implémenter le scan récursif avec `pathlib` (AC: 1)
  - [x] Utiliser `Path.rglob()` pour itérer tous les fichiers récursivement
  - [x] Filtrer par extensions configurées `supported_extensions` depuis config.yaml
  - [x] Tester avec dossiers imbriqués à plusieurs niveaux (prof. 3+)

- [x] Intégrer `tinytag` pour lire les métadonnées ID3 (AC: 2, 3)
  - [x] Pour chaque fichier audio trouvé : appeler `TinyTag.get(filepath)`
  - [x] Extraire les champs : `tag.artist`, `tag.title`, `tag.album`, `tag.duration`
  - [x] Gérer les valeurs `None` ou manquantes → convertir en `""`
  - [x] Vérifier la gestion des cas limites (fichier avec seulement le titre, sans artiste, etc.)

- [x] Initialiser `library.csv` avec le schéma correct (AC: 5)
  - [x] Utiliser `FIELDNAMES` depuis `utils.FIELDNAMES` (10 colonnes)
  - [x] Écrire la première ligne avec les headers
  - [x] Pour chaque fichier audio trouvé, créer une ligne avec :
    - `filepath` : chemin absolu ou relatif (à décider — voir architecture notes)
    - `artist`, `title`, `album` : valeurs depuis tinytag ou `""`
    - `duration` : en secondes (valeur numérique)
    - `status` : `STATUS_PENDING` (constant depuis utils)
    - `yt_video_id`, `yt_url`, `yt_score`, `error_message` : vides

- [x] Utiliser `utils.write_csv()` pour la persistance atomique (AC: 5)
  - [x] Ne pas écrire manuellement le CSV — toujours via `write_csv()`
  - [x] Vérifier l'encodage UTF-8 BOM (Excel-compatible) — déjà géré par write_csv()

- [x] Tester le scan sur un sous-ensemble de dossier (AC: 1–5)
  - [x] Créer un dossier de test avec structure imbriquée
  - [x] Vérifier que `library.csv` contient les bonnes lignes
  - [x] Vérifier qu'aucun fichier audio n'est omis
  - [x] Vérifier que les fichiers non-audio sont ignorés

## Notes développeur

### Contexte architectural critique

Cette story **ne crée que la phase d'inventaire initiale** du scanner. Elle ne gère pas encore :
- **Détection des fichiers corrompus** (reléguée à Story 2.2)
- **Détection des doublons** (reléguée à Story 2.3)
- **Idempotence du scanner** (reléguée à Story 2.4)

La story 2.1 supposera que :
- `library.csv` n'existe pas en entrée (première exécution) — Story 2.4 gérera le cas d'une relance sur un CSV existant
- Tous les fichiers sont lisibles par `tinytag` — Story 2.2 gérera les fichiers corrompus avec try/except
- Tous les doublons seront traités après en Story 2.3

---

### Implémentation attendue : `scanner.py` (Phase 1 — Story 2.1 uniquement)

```python
from pathlib import Path
from tinytag import TinyTag

from utils import (
    load_config, write_csv,
    STATUS_PENDING, FIELDNAMES
)

def main():
    config = load_config()
    music_folder = Path(config["music_folder"])
    supported_extensions = config["supported_extensions"]

    # Valider que le dossier existe
    if not music_folder.exists():
        print(f"[ERROR] Dossier musique introuvable : {music_folder}")
        return

    # Scan récursif et extraction ID3
    rows = []
    for audio_file in music_folder.rglob("*"):
        # Filtrer les répertoires
        if audio_file.is_dir():
            continue

        # Filtrer par extensions autorisées
        if audio_file.suffix.lower() not in supported_extensions:
            continue

        # Lire les métadonnées ID3
        tag = TinyTag.get(str(audio_file))

        # Créer une ligne CSV
        row = {
            "filepath": str(audio_file),
            "artist": tag.artist or "",
            "title": tag.title or "",
            "album": tag.album or "",
            "duration": tag.duration or "",  # tinytag retourne float (secondes) ou None
            "status": STATUS_PENDING,
            "yt_video_id": "",
            "yt_url": "",
            "yt_score": "",
            "error_message": ""
        }
        rows.append(row)

    # Exporter dans library.csv
    write_csv("library.csv", rows, FIELDNAMES)
    print(f"[OK] Scan terminé : {len(rows)} fichiers trouvés, sauvés dans library.csv")

if __name__ == "__main__":
    main()
```

---

### Points de vigilance architecturale — Anti-patterns à éviter

```python
# ❌ Écrire manuellement le CSV — TOUJOURS passer par write_csv()
with open("library.csv", "w") as f:  # → write_csv("library.csv", rows, FIELDNAMES)
    csv.DictWriter(f, fieldnames=["filepath", ...])

# ❌ Statut en chaîne inline — TOUJOURS utiliser STATUS_PENDING
row["status"] = "pending"  # → row["status"] = STATUS_PENDING

# ❌ Ignorer les fichiers à cause de la structure des dossiers
if "." in audio_file.name:  # → Problématique ! Filtrer par extensions seulement

# ❌ Ne pas gérer les valeurs None de tinytag
tag.artist  # → tag.artist or ""

# ❌ Utiliser glob au lieu de rglob (limitation de profondeur)
for f in music_folder.glob("*.mp3"):  # → for f in music_folder.rglob("*.mp3")
```

---

### Contexte technologique — tinytag

| Aspect | Détail |
|---|---|
| **Import** | `from tinytag import TinyTag` |
| **Lecture** | `tag = TinyTag.get(filepath)` |
| **Champs disponibles** | `tag.artist`, `tag.title`, `tag.album`, `tag.duration` |
| **Durée** | Retourné en **secondes** (float) — ex: `240.5` pour 4:00.5 |
| **Valeurs manquantes** | Retournées comme `None` → convertir en `""` pour CSV |
| **Performance** | Léger et rapide — pas de chargement du fichier entier (lit seulement les tags) |
| **Erreurs** | Fichiers corrompus → levés en exception (Story 2.2 les gérera) |
| **Note version** | tinytag 2.x (tinytag 1.x déprecié) — impact: plus d'`ignore_errors=True`, utiliser try/except |

---

### CSV Pathlib et extensions

**`Path.rglob()`** vs **`glob()`**:
- `rglob()` : récursif, tous les niveaux — ✅ À utiliser
- `glob()` : pas de récursion — ❌ À éviter pour ce cas d'usage

**Extensions configurées** (depuis config.yaml `supported_extensions`) :
```
- .mp3
- .flac
- .m4a
- .ogg
- .wav
- .aac
- .wma
```

**Vérification d'extension** :
```python
audio_file.suffix.lower() in config["supported_extensions"]
```

---

### Dépendances de Story 2.1

**Prérequis absolus :**
- Story 1.1 **COMPLÈTEMENT TERMINÉE** : `utils.py` doit exister avec `load_config()`, `write_csv()`, `STATUS_PENDING`, `FIELDNAMES`
- `config.yaml` rempli avec les paramètres (Story 1.2)
- `tinytag` installé via `requirements.txt` (Story 1.1)

**Pas de dépendance sur** :
- Story 2.2 (gestion des fichiers corrompus) — sera ajoutée plus tard
- Story 2.3 (détection des doublons) — sera ajoutée plus tard
- Story 2.4 (idempotence) — sera ajoutée plus tard

---

### Références

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 2, Story 2.1 (Acceptance Criteria BDD)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Data Architecture" (CSV I/O, FIELDNAMES figé)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Shared Module Architecture" (utils.py contrats)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Naming Patterns" (snake_case, STATUS_* constants)]
- [Source: `_bmad-output/implementation-artifacts/1-1-initialisation-de-la-structure-du-projet.md` — Format story et pattern code]

## Enregistrement de l'agent dev

### Modèle d'agent utilisé

claude-haiku-4-5

### Plan d'implémentation

**RED Phase :** Écriture de tests complets avant l'implémentation
- Créé `test_scanner.py` avec tests pour tous les critères d'acceptation
- Tests couvrent: scan récursif, extraction ID3, gestion des tags incomplets, filtrage des extensions, persistance CSV

**GREEN Phase :** Implémentation minimale pour passer tous les tests
- Implémenté `scan_recursive_and_extract_metadata()` : parcourt récursivement avec `Path.rglob()`, filtre extensions, lit ID3 avec TinyTag
- Implémenté `scan_and_save()` : wrapper utilisant `write_csv()` pour persistance atomique
- Implémenté `main()` : charge config, valide dossier, appelle scan_and_save

**REFACTOR Phase :** Code compliant avec architecture
- Structure de code suit le pattern architecture.md : isolation des responsabilités, réutilisation de utils
- Gestion des valeurs None → chaîne vide pour tous les champs metadata
- Encodage UTF-8 BOM géré par `write_csv()` (déjà conforme)
- Messages de log clairs pour débogage utilisateur

### Références de log de débogage

- Epic 1 (Setup & Authentification) complètement terminée avec 3 stories en review
- Story 1.4 (Validation browser.json) en backlog — peut être créée après Story 2.1
- Epic 2 est première fonctionnalité majeure : scan local library, foundation pour matcher/importer
- Story 2.1 complétée : tous les AC satisfaits, tous les tests passent

### Notes de complétion

- Story 2.1 : Scan récursif et lecture des métadonnées ID3 ✅
- Accepte tous les sous-dossiers imbriqués sans limite de profondeur (AC1)
- Lit artist, title, album, duration via tinytag (AC2)
- Gère les tags incomplets en les laissant vides (AC3)
- Filtre les fichiers non-audio selon supported_extensions (AC4)
- Exporte dans library.csv avec encodage UTF-8 BOM et tous les fields corrects (AC5)
- Tous les tests présents et passent ✅

### Liste des fichiers

- Modification de : `scanner.py` (implémentation du scan récursif)
- Lecture de : `config.yaml` (music_folder, supported_extensions)
- Lecture de : `utils.py` (load_config, write_csv, STATUS_PENDING, FIELDNAMES)
- Création de : `library.csv` (artefact central, en .gitignore)

## Journal des modifications

- 2026-02-22 : Story 2.1 — Scan récursif et lecture des métadonnées ID3. Implémentation du scan de la bibliothèque musicale locale avec extraction ID3 via tinytag. Gestion des tags incomplets, filtrage des extensions, persistance atomique du CSV. Tous les AC satisfaits.
