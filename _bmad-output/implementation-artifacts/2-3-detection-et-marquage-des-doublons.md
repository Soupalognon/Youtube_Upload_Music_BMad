# Story 2.3 : Détection et marquage des doublons

Status: review

<!-- Note: Validation optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant qu'utilisateur,
je veux que les morceaux en double soient identifiés automatiquement,
afin de ne pas importer plusieurs fois le même morceau dans YouTube Music.

## Critères d'acceptation

**AC1 — Détection des doublons par normalisation artist + title**

**Given** deux fichiers avec le même `artist` + `title` (après normalisation : lowercase, trim)
**When** le scanner traite ces fichiers
**Then** le premier est marqué `pending`, le second est marqué `duplicate`

**AC2 — Pas de faux positifs sur les doublons**

**Given** deux fichiers avec le même titre mais des artistes différents
**When** le scanner les traite
**Then** ils sont tous les deux marqués `pending` (pas de faux positif sur les doublons)

**AC3 — Idempotence du scanner après marquage doublons**

**Given** `library.csv` contient déjà des lignes avec le même artist + title normalisé
**When** je relance `python scanner.py`
**Then** les doublons ne sont pas re-marqués — seules les nouvelles lignes qui ne sont pas dans le CSV sont ajoutées

**AC4 — Stabilité mémoire avec déduplication**

**Given** 50 000+ fichiers à scanner avec possibles doublons (2–5% du volume)
**When** le scan s'exécute avec déduplication
**Then** la consommation mémoire reste stable (structure de tracking des duplicates reste O(n) en mémoire)

## Tâches / Sous-tâches

- [x] Implémenter la détection des doublons dans scanner.py (AC: 1, 2)
  - [x] Créer un dictionnaire de track clés normalisées (lowercase(artist + title))
  - [x] À chaque fichier, vérifier si la clé normalisée existe déjà
  - [x] Si oui → assigner `STATUS_DUPLICATE` et ne pas relancer de recherche
  - [x] Si non → assigner `STATUS_PENDING` et ajouter la clé au dictionnaire

- [x] Implémenter l'idempotence dans scanner.py (AC: 3, 4)
  - [x] Charger le CSV existant au démarrage du scanner
  - [x] Construire le dictionnaire de clés normalisées à partir du CSV existant
  - [x] Lors du scan des fichiers : si le filepath existe déjà dans le CSV, le sauter complètement
  - [x] Nouveau fichier ? Vérifier la clé normalisée et appliquer la logique doublons

- [x] Ajouter les utilitaires de normalisation dans utils.py (AC: 1, 2)
  - [x] Fonction `normalize_key(artist: str, title: str) -> str`
  - [x] Logique : lowercase, trim whitespace, remove None values

- [x] Valider qu'aucun doublon n'apparaît après plusieurs runs (AC: 3, 4)
  - [x] Tester sur un sous-ensemble de dossier avec des fichiers dupliqués
  - [x] Vérifier que les doublons sont correctement marqués au premier run
  - [x] Relancer le scanner et vérifier que le statut des doublons n'est pas changé

## Notes développeur

### Contexte architectural critique

Cette story **ajoute la déduplication à la Phase 1 du scanner**, en s'appuyant sur Story 2.1 (scan récursif) et Story 2.2 (gestion erreurs).

**Séquence des stories du scanner :**
- Story 2.1 : Scan récursif + métadonnées (tinytag) → library.csv avec statut `pending`
- Story 2.2 : Gestion des fichiers corrompus → statut `error_read`
- **Story 2.3 : Détection doublons** → statut `duplicate` pour le 2e et suivants
- Story 2.4 : Idempotence complète + Export Excel-compatible

**Intégration dans scanner.py :**

Le scanner doit maintenant implémenter deux phases :

1. **Phase 1 — Charger le CSV existant (idempotence)**
   ```python
   # Au démarrage du scanner
   existing_rows = read_csv(CSV_PATH)
   existing_paths = {r["filepath"] for r in existing_rows}

   # Construire le dictionnaire de clés normalisées existantes
   # pour identifier les doublons lors du scan
   ```

2. **Phase 2 — Scanner le dossier et tracker les doublons**
   ```python
   seen_keys = {}  # {normalized_key: (filepath, status)}
   for audio_file in walk_recursively(music_folder):
       # Skip if already in CSV
       if str(audio_file) in existing_paths:
           continue

       # Lire les métadonnées (avec try/except de Story 2.2)
       # Créer la clé normalisée
       normalized_key = normalize_key(artist, title)

       # Vérifier si doublon (dans le CSV existant OU dans le scan courant)
       if normalized_key in existing_keys_from_csv or normalized_key in seen_keys:
           status = STATUS_DUPLICATE
       else:
           status = STATUS_PENDING
           seen_keys[normalized_key] = str(audio_file)

       # Écrire la ligne
       row = {..., "status": status, ...}
       rows.append(row)
   ```

### Fonction de normalisation — À ajouter dans utils.py

```python
def normalize_key(artist: str, title: str) -> str:
    """
    Normalise artist + title pour détection de doublons.
    Retourne une clé insensible à la casse et aux espaces.

    Exemples:
    - ("The Beatles", "Let It Be") → "the beatles|let it be"
    - ("the BEATLES", "  Let It Be  ") → "the beatles|let it be"
    - ("", "Untitled") → "|untitled"  # artiste vide accepté
    """
    artist_norm = (artist or "").lower().strip()
    title_norm = (title or "").lower().strip()
    return f"{artist_norm}|{title_norm}"
```

### Dépendances et ordre d'implémentation

**Prérequis :**
- Story 1.1 : `utils.py` avec `STATUS_DUPLICATE` et autres constantes
- Story 1.2 : `config.yaml` avec `music_folder`, `supported_extensions`
- Story 2.1 : `scanner.py` avec scan récursif + `TinyTag`
- Story 2.2 : `scanner.py` enrichi avec try/except

**Dépendants :**
- Story 2.4 : L'idempotence complète du scanner repose sur cette story pour la déduplication

### Pattern d'idempotence du scanner

Après cette story, le scanner subit une transformation importante :

**Avant (simple, Story 2.1) :**
```python
for filepath in walk(music_folder):
    rows.append({..., "status": STATUS_PENDING})
write_csv(CSV_PATH, rows, FIELDNAMES)
```

**Après (Story 2.3 + 2.4) :**
```python
# Charger l'état existant
existing_rows = read_csv(CSV_PATH)
existing_paths = {r["filepath"] for r in existing_rows}
existing_keys = build_key_index(existing_rows)  # doublons

# Scanner uniquement les nouveaux fichiers
for filepath in walk(music_folder):
    if filepath in existing_paths:
        continue  # Déjà dans le CSV, skip

    # Appliquer logique doublons sur les nouvelles lignes
    key = normalize_key(artist, title)
    if key in existing_keys or key in current_scan_keys:
        status = STATUS_DUPLICATE
    else:
        status = STATUS_PENDING

    rows.append({..., "status": status, ...})

# Fusionner avec les lignes existantes
all_rows = existing_rows + rows
write_csv(CSV_PATH, all_rows, FIELDNAMES)
```

**Impact :** Cette pattern est fondamentale pour NFR7 (reprise sans perte ni doublon).

### Anti-patterns à éviter

```python
# ❌ Ne pas marquer un doublon deux fois
if first_occurrence:
    status = STATUS_PENDING
elif second_occurrence:
    status = STATUS_DUPLICATE
    # PUIS modifiez la ligne du premier pour le marquer aussi ?
    # → NON ! Le premier reste PENDING

# ❌ Ne pas recharger le CSV complet à chaque nouveau fichier
for filepath in files:
    rows = read_csv(CSV_PATH)  # Mauvais ! Trop lent
    # ...
# → Charger une seule fois au démarrage

# ❌ Chaîne de statut au lieu de constante
status = "duplicate"  # → status = STATUS_DUPLICATE

# ❌ Oublier la normalisation
if artist == song["artist"] and title == song["title"]:  # Sensible à la casse !
# → Utiliser normalize_key()

# ✅ Bon pattern
normalized_key = normalize_key(artist, title)
if normalized_key in seen_keys:
    status = STATUS_DUPLICATE
else:
    status = STATUS_PENDING
    seen_keys[normalized_key] = filepath
```

### Références architecturales

- [Source: epics.md — Epic 2, Story 2.3]
- [Source: architecture.md — Data Architecture, Idempotence Pattern, Shared Module]
- [Source: prd.md — FR12 (détection doublons), FR15 (idempotence), NFR1 (stabilité mémoire)]
- [Source: 2-1-scan-recursif-et-lecture-des-metadonnees-id3.md — Pattern scanner.py]
- [Source: 2-2-detection-des-fichiers-corrompus-et-gestion-des-erreurs.md — Pattern try/except + write_csv]

## Enregistrement de l'agent dev

### Modèle d'agent utilisé

Claude Haiku 4.5

### Plan d'implémentation

**Phase 1 — RED (Tests)**
- Ajout de tests pour `normalize_key()` dans test_utils.py (9 tests couvrant tous les cas : case-insensitive, trim, None handling, séparateur)
- Ajout de tests pour détection de doublons dans test_scanner.py (4 tests : AC1 basic, AC1 case-insensitive, AC2 no false positives, AC3 idempotence)

**Phase 2 — GREEN (Implémentation)**
- Implémentation de `normalize_key(artist: str, title: str) -> str` dans utils.py
  - Normalise en minuscules avec trim des espaces
  - Traite None comme chaîne vide
  - Retourne "artist|title" comme clé
- Refactor de `scan_recursive_and_extract_metadata()` pour supporter duplicate detection
  - Ajout paramètre `existing_csv_path` optionnel
  - Phase 1 : Charger CSV existant, extraire clés normalisées et filepaths
  - Phase 2 : Scanner les fichiers, tracker doublons, assigner status
  - Implémentation idempotence : skip filepaths existants
- Refactor de `scan_and_save()` pour implémenter fusion CSV
  - Charge le CSV existant
  - Scanne les nouveaux fichiers
  - Fusionne les lignes avant écriture

**Phase 3 — REFACTOR & Tests**
- Exécution de tous les tests : 83 tests passent (sans régression)
- Mise à jour de 3 tests existants pour refléter le nouveau comportement avec doublons :
  - test_scanner_csv_all_files_have_pending_status : métadonnées différentes par fichier
  - test_scanner_story22_corrupted_file_does_not_block_next_files : artist+title uniques par fichier
  - test_scanner_story22_memory_with_mixed_valid_and_corrupted : artist+title uniques par index

### Notes de complétion

✅ Tous les Acceptance Criteria satisfaits :
- **AC1 (Détection normalisation)** : normalize_key() applique lowercase + trim. Tests validant case-insensitive et space-trim.
- **AC2 (No false positives)** : Artistes différents → status pending pour tous (test_scanner_story23_ac2_no_false_positives)
- **AC3 (Idempotence)** : Fichiers existants skippés, CSV fusionné, relances stables (test_scanner_story23_ac3_idempotence_no_reprocessing)
- **AC4 (Mémoire O(n))** : seen_keys dict + existing_keys set = O(n) space. Test 500 fichiers réussit.

✅ Tests complets :
- 9 tests normalize_key() — tous passent
- 4 tests Story 2.3 — tous passent
- 83 tests totaux — aucune régression (3 tests existants mis à jour)

✅ Code quality :
- Imports corrigés (ajout normalize_key à scanner.py)
- Documentation docstrings mise à jour
- Patterns conformes à l'architecture (Story 2.1/2.2)

### Liste des fichiers

Fichiers modifiés (relative to repo root) :
- `scanner.py` : Refactor scan_recursive_and_extract_metadata + scan_and_save pour duplicate detection et idempotence
- `utils.py` : Ajout fonction normalize_key(artist, title) -> str
- `test_scanner.py` : Ajout 4 tests Story 2.3 (AC1-3), mise à jour 3 tests existants (AC5, story22)
- `test_utils.py` : Ajout 9 tests normalize_key()

Fichiers lus/modifiés au runtime :
- `library.csv` : Lecture au démarrage du scanner pour idempotence, fusion des résultats

## Journal des modifications

- 2026-02-22 : Story 2.3 — Détection et marquage des doublons (ready-for-dev).
- 2026-02-22 : ✅ Story 2.3 — Implémentation complète. Duplicate detection + idempotence, 83 tests passant.
