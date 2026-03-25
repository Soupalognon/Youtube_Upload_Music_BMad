# Story 3.2 : Scoring de similarité et vérification de durée

Status: review

<!-- Note: Validation est optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant qu'utilisateur,
je veux que le matcher calcule un score précis sur artiste + titre et vérifie la durée,
afin d'identifier les vraies correspondances et distinguer les versions alternatives.

## Critères d'acceptation

### AC1 — Calcul du score rapidfuzz sur artiste + titre normalisés

**Given** des résultats de recherche retournés par YouTube Music (Story 3.1)
**When** le scoring est calculé
**Then** un score `rapidfuzz` (0–100) est calculé sur `artist + title` normalisés entre le morceau local et le meilleur résultat YouTube Music
**And** le score reflète la similarité textuelle précise (pas de seuil binaire simple)

### AC2 — Vérification de la durée avec tolérance configurable

**Given** le résultat YouTube Music retourné et sa durée en secondes
**When** la vérification de durée est exécutée
**Then** la durée du résultat est comparée à la durée locale avec la tolérance `duration_tolerance` configurée (défaut 5 secondes)
**And** un match de durée est considéré valide si : `|durée_yt - durée_locale| ≤ duration_tolerance`

### AC3 — Filtrage des versions live (si activé)

**Given** le filtre live est activé (`exclude_live: true` dans `config.yaml`)
**When** des résultats de recherche contiennent des versions live
**Then** ces résultats sont exclus de la liste avant le calcul du score
**And** seuls les résultats non-live sont évalués

### AC4 — Attribution du statut selon le score et la durée

**Given** le score rapidfuzz calculé et la durée vérifiée
**When** le matching évalue les résultats
**Then** :
- Si score ≥ `confidence_threshold` (défaut 85) ET durée valide → statut reste `pending` (bon match)
- Si score entre `low_confidence_threshold` (défaut 70) et `confidence_threshold` ET durée valide → statut = `low_confidence` (match incertain)
- Si aucun résultat satisfaisant (score < `low_confidence_threshold` OU durée invalide) → statut = `failed` (pas de bon match)

### AC5 — Renseignement des colonnes `yt_video_id` et `yt_score`

**Given** le meilleur résultat validé (score ≥ `low_confidence_threshold` ET durée ok)
**When** les colonnes CSV sont renseignées
**Then** :
- `yt_video_id` = identifiant YouTube Music unique du morceau (fourni par `ytmusic.search()`)
- `yt_score` = score rapidfuzz arrondi (entier 0–100)
**And** ces colonnes restent **vides** si le score est < `low_confidence_threshold` ou durée invalide

---

## Tâches / Sous-tâches

- [x] Implémenter le calcul du score rapidfuzz (AC: 1)
  - [x] Extraire le meilleur résultat de la liste retournée par `ytmusic.search()` (généralement le premier)
  - [x] Normaliser artiste + titre local (`artist + " " + title`)
  - [x] Normaliser artiste + titre YouTube Music depuis les résultats
  - [x] Appeler `score_match(local_query, yt_query)` depuis utils
  - [x] Capturer le score numérique (0–100)

- [x] Implémenter la vérification de durée (AC: 2)
  - [x] Extraire `duration` du résultat YouTube Music (format : secondes ou millisecondes selon l'API)
  - [x] Convertir si nécessaire en secondes
  - [x] Charger `duration_tolerance` depuis `config` (défaut 5)
  - [x] Calculer la différence : `abs(duration_yt - duration_local)`
  - [x] Valider : `diff ≤ duration_tolerance`

- [x] Implémenter le filtrage live (AC: 3)
  - [x] Charger `exclude_live` depuis `config` (défaut `true`)
  - [x] Vérifier si le titre du résultat contient "Live", "[Live]", "Live Version", etc.
  - [x] Filtrer les résultats avant le scoring (créer une liste `filtered_results`)
  - [x] Tester sur des résultats connus contenant "Live"

- [x] Implémenter la machine à états des statuts (AC: 4)
  - [x] Charger seuils depuis `config` : `confidence_threshold` (85), `low_confidence_threshold` (70)
  - [x] Écrire la logique : if-elif-else sur score + durée valide
  - [x] Assigner `STATUS_PENDING`, `STATUS_LOW_CONFIDENCE`, ou `STATUS_FAILED`
  - [x] Respecter la hiérarchie : confiance d'abord, durée second

- [x] Renseigner les colonnes CSV (AC: 5)
  - [x] Si statut = `pending` ou `low_confidence` : `yt_video_id` = ID du résultat, `yt_score` = score
  - [x] Si statut = `failed` : `yt_video_id` et `yt_score` restent vides (`""`)
  - [x] Persister immédiatement via `write_csv()`

- [x] Intégrer dans la boucle principale de matcher.py
  - [x] Après Story 3.1 (recherche + nettoyage), appliquer le scoring
  - [x] Respecter l'idempotence : skip lignes avec `yt_video_id` déjà renseigné
  - [x] Gérer les cas limites (résultats vides, durée manquante)
  - [x] Persister CSV après chaque morceau traité (bloc `finally`)

- [x] Valider et tester en isolation
  - [x] Tester `score_match()` sur 5-10 paires (locale, YouTube) : exact, partiel, mauvais match
  - [x] Tester durée : cas valides, cas limites (±tolerance), cas invalides
  - [x] Tester filtrage live : vérifier "Live" élimine les résultats attendus
  - [x] Tester machine à états : score ≥85 → `pending`, 70-85 → `low_confidence`, <70 → `failed`

---

## Notes développeur

### Contexte critique : Enrichissement des résultats YouTube Music

Cette story **complète la recherche initiale (3.1)** en transformant des résultats bruts en décisions d'import. C'est le cœur du matching :
1. Les résultats de 3.1 contiennent la liste brute YouTube Music
2. Cette story (3.2) évalue chaque résultat via score + durée
3. La meilleure correspondance valide est marquée (pending/low_confidence)
4. Story 3.3 en génère l'URL cliquable
5. Story 3.4 ajoute la résilience réseau

**Dépendances absolues :**
- ✅ Story 3.1 — Recherche YouTube Music fonctionne, résultats disponibles
- ✅ utils.py — `score_match()` implémenté et testé
- ✅ config.yaml — Seuils (`confidence_threshold`, `low_confidence_threshold`, `duration_tolerance`, `exclude_live`)

### Architecture décisionnelle — Scoring & Durée

#### Question 1 : Quel résultat évaluer ?

**Décision :** Utiliser le **premier résultat** retourné par `ytmusic.search()` (par défaut, YouTube Music classe par pertinence décroissante).

**Rationale :**
- YouTube Music retourne une liste, classée par pertinence (l'API non-officielle préserve ce classement)
- Le premier résultat est statistiquement le meilleur match
- Évaluer tous les résultats serait coûteux en API calls (YouTube Music applique rate limiting)
- NFR6 (résilience) recommande de minimiser les appels — un seul résultat suffit
- Si le premier échoue le scoring, `failed` est la conclusion correcte (pas de "deuxième chance" automatique)

**Implémentation :**
```python
if not results or len(results) == 0:
    row["status"] = STATUS_FAILED
    row["error_message"] = "Aucun résultat YouTube Music"
    continue

best_result = results[0]  # Utiliser le premier (meilleur par pertinence)
```

#### Question 2 : Format de la durée YouTube Music

**Décision :** La durée retournée par `ytmusic.search()` est en **secondes** (entier). Pas de conversion nécessaire.

**Rationale :**
- `ytmusic` normalise les durées en secondes dans tous ses endpoints
- Vérifier avec un test simple (Story 3.1 log)

**Vérification :**
```python
from ytmusicapi import YTMusic
ytmusic = YTMusic(auth="browser.json")
results = ytmusic.search("Daft Punk Get Lucky", filter="songs")
print(results[0])  # Inspecter le champ "duration" ou "videoDetails"
```

**Structre attendue :** `best_result` contient une clé `duration` (secondes) ou `videoDetails["duration"]`.

#### Question 3 : Normalisation des chaînes avant scoring

**Décision :** Normaliser avant `score_match()` : minuscules, trimming, suppression accents.

**Rationale :**
- `rapidfuzz` est sensible à la casse et aux espaces
- Normliser = améliorer la pertinence du score
- `score_match()` encapsule déjà la normalisation — utiliser tel quel

**Implémentation :**
```python
from utils import score_match

local_query = f"{row['artist']} {row['title']}".lower().strip()
yt_query = f"{best_result['artist']} {best_result['title']}".lower().strip()
score = score_match(local_query, yt_query)  # Retourne 0–100
```

**Note :** `score_match()` est implémenté dans utils.py (Story 1.1). NE PAS modifier son implémentation.

#### Question 4 : Gestion des résultats sans durée

**Décision :** Si la durée YouTube Music est manquante, assigner le statut `failed`.

**Rationale :**
- Un match sans durée ne peut pas être validé → impossible de vérifier AC2
- Préférer un `failed` explicite qu'un `pending` incertain
- NFR2 (confiance totale) > NFR7 (automatisation max)

**Implémentation :**
```python
try:
    yt_duration = int(best_result.get("duration", 0))
    if yt_duration == 0:
        raise ValueError("Durée manquante")
except (ValueError, TypeError):
    row["status"] = STATUS_FAILED
    row["error_message"] = "Durée YouTube Music indisponible"
    continue
```

#### Question 5 : Filtrage live — avant ou après scoring ?

**Décision :** Filtrer **avant** d'évaluer le score (pré-traiter la liste).

**Rationale :**
- Si "Live" est présent, on ne veut pas le scorer du tout (résultat invalide)
- Exclure avant = plus clair et plus efficace qu'exclure après sur la base d'un score bas
- Patterns à filtrer : "Live", "[Live]", "Live Version", "Live at ...", "(Live)"

**Implémentation :**
```python
LIVE_PATTERNS = ["live", "[live]", "live version", "live at"]

def is_live(title: str) -> bool:
    title_lower = title.lower()
    return any(pattern in title_lower for pattern in LIVE_PATTERNS)

# Avant scoring :
if exclude_live and is_live(best_result.get("title", "")):
    row["status"] = STATUS_FAILED
    row["error_message"] = "Résultat live (exclu par config)"
    continue
```

#### Question 6 : Seuil bas "low_confidence" — valeur recommandée

**Décision :** Seuil bas = **70** (fourni en config.yaml, déjà défini en Story 1.2).

**Rationale :**
- Entre 70 et 85, la correspondance est acceptable mais incertaine (homophones, variantes légères)
- Au-dessous de 70, trop de risque (faux positif)
- Parcours 3 du PRD (review manuelle) préfère les `low_confidence` explicites plutôt que les matches silencieux faux

**Vérification :**
```yaml
# config.yaml
confidence_threshold: 85          # ≥ = good match
low_confidence_threshold: 70      # 70–85 = uncertain
```

### Gestion des erreurs — Contexte pour Story 3.4

Cette story (3.2) **ne gère pas les erreurs réseau**. Les erreurs seront traitées dans Story 3.4 (résilience). Donc :
- Si `ytmusic.search()` lève une exception → laisser remonter (crash contrôlé, ajouté en 3.4)
- Seules les erreurs métier (résultat manquant, durée invalide) sont traitées ici
- Story 3.4 enveloppera avec `try/except` + backoff exponentiel

### Validations à respecter

**AC1 — Critique :** Le score rapidfuzz doit être calculé sur artiste + titre normalisés (minuscules, sans accents).

**AC2 — Critique :** La vérification de durée doit respecter `duration_tolerance` (défaut 5s). Formule : `|duration_yt - duration_local| ≤ duration_tolerance`.

**AC3 — Critique :** Si `exclude_live: true`, les résultats contenant "Live" (variantes) doivent être exclus **avant** le scoring.

**AC4 — Critique :** La machine à états doit respecter l'ordre : score d'abord, durée second. Pas d'import si l'une échoue.

**AC5 — Critique :** `yt_video_id` et `yt_score` doivent rester vides (""`) si le statut est `failed`.

---

## Contexte architecturale détaillé

### Flux de données — Phase 2, Step 2

```
library.csv (lignes pending, avec résultats YouTube Music de 3.1)
    │
    ├─ AC1: Extraire le meilleur résultat (index 0)
    │
    ├─ AC3: Filtrer live si `exclude_live: true`
    │        → Si live → STATUS_FAILED, sortie directe
    │
    ├─ AC2: Vérifier durée YouTube Music vs durée locale
    │        → Si invalid → STATUS_FAILED, sortie directe
    │        → Si valide → continuer
    │
    ├─ AC1: Calculer score rapidfuzz (artist + title normalisés)
    │
    ├─ AC4: Assigner statut selon score
    │        - score ≥ 85 → STATUS_PENDING (bon match)
    │        - 70 ≤ score < 85 → STATUS_LOW_CONFIDENCE
    │        - score < 70 → STATUS_FAILED
    │
    └─ AC5: Renseigner yt_video_id, yt_score (si statut ≠ FAILED)
         → Persister immédiatement via write_csv()
```

**Colonnes concernées dans cette story :**
- `status` : changé de `pending` → { `pending`, `low_confidence`, `failed` }
- `yt_video_id` : renseigné si statut ≠ `failed`, sinon reste vide
- `yt_score` : renseigné avec score (0–100) si statut ≠ `failed`, sinon reste vide
- `error_message` : renseigné si un cas d'erreur métier (durée invalide, résultats vides)

### Dépendances technologiques critiques

| Bibliothèque | Rôle | Note |
|---|---|---|
| `rapidfuzz` | Calcul du score de similarité textuelle | Version 3.x — importé via `score_match()` dans utils.py |
| `utils.score_match()` | Wrapper autour de rapidfuzz + normalisation | Déjà implémenté en Story 1.1 — NE PAS modifier |
| `ytmusicapi` | Source des résultats et durées YouTube Music | Non-officiel, version 1.11.5 (fixée) |

### Configuration — Paramètres utilisés dans cette story

| Paramètre | Défaut | Rôle | Source |
|---|---|---|---|
| `confidence_threshold` | 85 | Seuil bon match (score ≥) | config.yaml (Story 1.2) |
| `low_confidence_threshold` | 70 | Seuil match incertain | config.yaml (Story 1.2) |
| `duration_tolerance` | 5 | Tolérance durée ±Xs | config.yaml (Story 1.2) |
| `exclude_live` | true | Filtrer versions live | config.yaml (Story 1.2) |

**Chargement :**
```python
config = load_config()  # Valide tous les paramètres
confidence_threshold = config.get("confidence_threshold", 85)
low_confidence_threshold = config.get("low_confidence_threshold", 70)
duration_tolerance = config.get("duration_tolerance", 5)
exclude_live = config.get("exclude_live", True)
```

### État de la codebase avant cette story

**Fichiers existants et figés :**
- ✅ `utils.py`
  - ✅ `score_match(local, yt) → int (0–100)` — importé via `from utils import score_match`
  - ✅ `load_config()` — déjà appelé
  - ✅ `read_csv()` / `write_csv()` / `FIELDNAMES`
  - ✅ `STATUS_PENDING`, `STATUS_LOW_CONFIDENCE`, `STATUS_FAILED` constants

- ✅ `config.yaml` (structure fixe depuis Story 1.2)
  - ✅ `confidence_threshold: 85`
  - ✅ `low_confidence_threshold: 70`
  - ✅ `duration_tolerance: 5`
  - ✅ `exclude_live: true`

- ✅ `matcher.py` (en construction)
  - ✅ Story 3.1 — Recherche YouTube Music + nettoyage titres (complétée)
  - [ ] Story 3.2 — Scoring + vérification durée (CETTE STORY)
  - [ ] Story 3.3 — Génération URLs + persistance
  - [ ] Story 3.4 — Résilience réseau + progression

- ✅ `library.csv`
  - Produit par `scanner.py` (Epic 2)
  - Enrichi par Story 3.1 avec résultats YouTube Music bruts
  - Sera enrichi par cette story avec scores et statuts

### Bonne pratique — Éviter les anti-patterns

```python
# ❌ Ne pas modifier score_match() ou l'appeler différemment
custom_score = my_custom_scoring_function(...)  # ← MAUVAIS

# ✅ Utiliser score_match() depuis utils
from utils import score_match
score = score_match(local_query, yt_query)  # ← BON

# ❌ Ne pas hardcoder les seuils
if score >= 85:  # ← MAUVAIS (hardcodé)

# ✅ Charger depuis config
confidence_threshold = config["confidence_threshold"]
if score >= confidence_threshold:  # ← BON

# ❌ Ne pas filtrer live après scoring
if score < 70:
    ...
if is_live(title):  # ← MAUVAIS (ordre)

# ✅ Filtrer avant scoring
if exclude_live and is_live(title):  # ← BON (ordre : exclusion d'abord)
    ...

# ❌ Ne pas utiliser des noms de colonnes différents
row["yt_score_value"] = score  # ← MAUVAIS (casse le contrat FIELDNAMES)

# ✅ Respecter les noms FIELDNAMES
row["yt_score"] = score  # ← BON

# ❌ Ne pas oublier de persister le CSV
row["yt_score"] = score
# (pas d'écriture)  ← MAUVAIS (perte de données)

# ✅ Toujours persister dans un bloc finally
try:
    ...
finally:
    write_csv(CSV_PATH, rows, FIELDNAMES)  # ← BON
```

---

## Contexte architecturale avancé : Chaîne complète de matching

### Exemple concret : Morceau "Daft Punk — Get Lucky (Remastered)"

**Étape 1 — Story 3.1 : Recherche**
```
Fichier local : title = "Get Lucky (Remastered)", artist = "Daft Punk"
Nettoyage : clean_title() → "Get Lucky"
Requête : "Daft Punk Get Lucky"
Résultats YouTube Music : [
  {
    "videoId": "aq2KrGaF_kM",
    "title": "Get Lucky",
    "artist": "Daft Punk",
    "duration": 244  # secondes
  },
  { ... autres résultats ... }
]
CSV après 3.1 :
  | artist     | title    | duration | status  | yt_video_id | yt_score |
  | Daft Punk  | Get...   | 245      | pending |  (raw data) |          |  (résultats bruts, pas encore scoring)
```

**Étape 2 — Story 3.2 : Scoring (CETTE STORY)**
```
Meilleur résultat : { videoId: "aq2KrGaF_kM", title: "Get Lucky", artist: "Daft Punk", duration: 244 }

Vérif. durée :
  - duration_tolerance = 5
  - |244 - 245| = 1 ≤ 5 ✓ Valide

Scoring :
  - local_query = "daft punk get lucky"
  - yt_query = "daft punk get lucky"
  - score_match() → 100 (exact match)
  - score ≥ confidence_threshold (100 ≥ 85) ✓

Statut : STATUS_PENDING (bon match)

CSV après 3.2 :
  | artist     | title    | duration | status  | yt_video_id  | yt_score |
  | Daft Punk  | Get...   | 245      | pending | aq2KrGaF_kM  | 100      |
```

**Étape 3 — Story 3.3 : Génération d'URLs**
```
yt_url = f"https://music.youtube.com/watch?v={yt_video_id}"
       = "https://music.youtube.com/watch?v=aq2KrGaF_kM"

CSV après 3.3 :
  | artist     | title    | duration | status  | yt_video_id  | yt_url                                         | yt_score |
  | Daft Punk  | Get...   | 245      | pending | aq2KrGaF_kM  | https://music.youtube.com/watch?v=aq2KrGaF_kM | 100      |
```

### Exemple concret : Morceau "Various Artists — Track 04" (Low Confidence)

**Étape 1 — Story 3.1 : Recherche** (skippée, va directement en manual_review)
→ Story 3.1 détecte "Various Artists" et marque directement en STATUS_MANUAL_REVIEW

**CSV après 3.1 :**
```
| artist          | title     | duration | status         | yt_video_id | yt_score |
| Various Artists | Track 04  | 180      | manual_review  |             |          |
```

**Story 3.2 : Scoring**
→ Cette story **ignore** les lignes qui ne sont pas `pending` (condition d'idempotence)
→ CSV reste inchangé après 3.2 (pas de processing)

---

## Intégration avec les Stories précédentes et suivantes

### Dépendance vers Story 3.1 : Résultats bruts

Story 3.1 retourne une liste brute de résultats YouTube Music. Cette story (3.2) les évalue.

**Interface entre 3.1 et 3.2 :**
- **Entrée :** Résultats bruts dans une variable ou stockés temporairement
- **Sortie :** Scores calculés, statuts assignés, colonnes `yt_video_id` et `yt_score` renseignées

**Astuce d'implémentation :**
Si Story 3.1 retourne une liste `results = ytmusic.search(...)`, Story 3.2 peut évaluer directement dans la même boucle :
```python
results = ytmusic.search(query)
best_result = results[0] if results else None
# ... appliquer AC1–AC5 sur best_result
```

### Dépendance vers Story 3.3 : Génération d'URLs

Story 3.3 utilise les `yt_video_id` assignés en 3.2 pour générer les URLs cliquables.

**Interface entre 3.2 et 3.3 :**
- **Entrée :** CSV avec `yt_video_id` renseigné
- **Sortie :** Colonne `yt_url` renseignée pour chaque morceau avec un `yt_video_id` valide

### Dépendance vers Story 3.4 : Résilience

Story 3.4 encapsule la recherche + scoring avec retry/backoff exponentiel.

**Interface entre 3.2 et 3.4 :**
- **Entrée :** Logique de scoring (3.2)
- **Sortie :** Logique enveloppée dans try/except avec MAX_RETRIES=3, time.sleep(2**attempt)

---

## Références

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3, Story 3.2 (User Story & AC BDD)]
- [Source: `_bmad-output/planning-artifacts/prd.md` — Success Criteria (Precision over Rappel, Baseline v1)]
- [Source: `_bmad-output/planning-artifacts/prd.md` — Parcours 1 (Matching + URLs de vérification)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Core Architectural Decisions (rapidfuzz scoring, durée tolerance)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — Implementation Patterns (STATUS_*, snake_case, CSV I/O)]
- [Source: Story 3.1 — Dev notes sur recherche YouTube Music et gestion Various Artists]
- [Source: Story 1.1 — dev notes sur `utils.score_match()` et normalisation]

---

## Dev Agent Record

### Modèle d'agent utilisé

claude-haiku-4-5-20251001

### Références de log de débogage

*À remplir par l'agent dev lors de l'implémentation*

### Notes de complétion

- [x] AC1 — Scoring rapidfuzz fonctionnel avec normalisation
  - Implémentation dans `score_and_verify_youtube_result()` qui appelle `score_match()` via utils
  - Normalisation artist + title effectuée avant scoring

- [x] AC2 — Vérification durée avec tolérance configurable
  - Durée extraite et convertie en entiers (secondes)
  - Tolérance configurable via `config['duration_tolerance']`
  - Retourne None si durée invalide ou hors tolérance

- [x] AC3 — Filtrage live (si `filter_live: true`)
  - Implémentation dans `is_live()` qui détecte patterns : "live", "[live]", "live version", "live at", "(live)"
  - Filtrage effectué avant scoring (early return None)
  - Respects `config['filter_live']` setting

- [x] AC4 — Machine à états scores (pending/low_confidence/failed)
  - Implémentation dans `assign_match_status()` avec logique if-elif-else
  - Seuils respectés : confidence_threshold (85), low_confidence_threshold (70)
  - Hiérarchie : score d'abord, durée valide d'abord

- [x] AC5 — Colonnes `yt_video_id` et `yt_score` renseignées correctement
  - Implémentation dans `populate_csv_result()`
  - yt_video_id et yt_score remplis si statut != FAILED
  - Restent vides si statut == FAILED

- [x] Idempotence matcher.py validée (skip lignes avec `yt_video_id` renseigné)
  - Vérifiée dans `process_matcher_loop()` ligne 205

- [x] Tests unitaires : 32 tests passent
  - Tests de scoring : exact match, partial match, missing duration
  - Tests de durée : within tolerance, exceeds tolerance
  - Tests de filtrage live : enabled, disabled
  - Tests de statut : good/uncertain/failed matches
  - Tests CSV : populate with score, populate when failed
  - Tests d'intégration : scoring applied in main loop

- [x] Tests de filtrage live sur résultats connus contenant "Live"
  - `is_live("Song [Live]")` → True
  - `is_live("Song (Live)")` → True
  - `is_live("Live Version")` → True
  - `is_live("Song at Live")` → True

- [x] Tests de vérification durée sur cas limites (±tolerance)
  - Tolérance (5s) : 244s vs 245s → valide
  - Hors tolérance (5s) : 240s vs 250s → invalide

### Liste des fichiers

**Modifiés :**
- `matcher.py` - Ajout de 3 nouvelles fonctions (is_live, score_and_verify_youtube_result, assign_match_status, populate_csv_result) et intégration du scoring dans process_matcher_loop()
- `test_matcher.py` - Ajout de 13 tests pour Story 3.2 (tous passants)

**Générés/Modifiés par matcher après Story 3.2 :**
- `library.csv` - Enrichissement avec yt_video_id, yt_score, et statuts (pending/low_confidence/failed)

---

## Journal des modifications

- 2026-02-23 : Story 3.2 — Scoring de similarité et vérification de durée. Contexte exhaustif fourni : workflow complet de scoring, architecture décisionnelle pour seuils/durée/filtrage live, gestion des cas limites, dépendances technologiques, intégration avec Story 3.1 (recherche) et 3.3 (URLs). Prêt pour implémentation par agent dev.

- 2026-02-23 : Story 3.2 — IMPLÉMENTATION COMPLÈTE par agent dev (claude-haiku-4-5-20251001)
  - Implémentation : 4 fonctions ajoutées à matcher.py (is_live, score_and_verify_youtube_result, assign_match_status, populate_csv_result)
  - Intégration : scoring appliqué dans process_matcher_loop() après recherche YouTube Music
  - Tests : 13 nouveaux tests ajoutés à test_matcher.py, tous passants (32/32 matcher tests passent)
  - Acceptance Criteria : AC1-AC5 tous complètement implémentés et validés
  - Idempotence : respektée (skip lignes avec yt_video_id déjà renseigné)
  - Configuration : tous les seuils et paramètres chargés depuis config.yaml
