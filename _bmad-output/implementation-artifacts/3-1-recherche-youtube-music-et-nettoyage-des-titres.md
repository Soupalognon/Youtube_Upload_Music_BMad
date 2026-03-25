# Story 3.1 : Recherche YouTube Music et nettoyage des titres

Status: review

<!-- Note: Validation est optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant qu'utilisateur,
je veux que le matcher recherche chaque morceau dans YouTube Music en nettoyant les titres des annotations parasites,
afin d'obtenir des résultats de recherche pertinents malgré les variations de nommage.

## Critères d'acceptation

### AC1 — Recherche YouTube Music par artiste + titre nettoyé

**Given** une ligne `pending` avec `artist` et `title` dans `library.csv`
**When** `matcher.py` traite cette ligne
**Then** une requête de recherche est envoyée à YouTube Music avec `artist + title` (nettoyé)
**And** les résultats sont retournés pour évaluation dans les critères suivants

### AC2 — Nettoyage des annotations parasites avant recherche

**Given** un titre contenant des annotations parasites (`(Remastered)`, `[Live]`, `feat. X`, `- Radio Edit`, etc.)
**When** le nettoyage est appliqué via `clean_title()`
**Then** ces annotations sont supprimées du titre
**And** la requête de recherche YouTube Music utilise le titre nettoyé

### AC3 — Gestion des morceaux "Various Artists"

**Given** un morceau avec `artist = "Various Artists"` (ou variantes : "VA", etc.)
**When** `matcher.py` le rencontre
**Then** il est directement marqué `manual_review` sans tentative de recherche
**And** `yt_video_id`, `yt_url`, `yt_score` restent vides
**And** le CSV est mis à jour immédiatement

## Tâches / Sous-tâches

- [x] Implémenter la détection et marquage des "Various Artists" (AC: 3)
  - [x] Identifier les variantes (va, various, compilation, etc.)
  - [x] Marquer directement comme `manual_review`
  - [x] Éviter la requête YouTube Music

- [x] Construire la requête de recherche YouTube Music (AC: 1)
  - [x] Charger `browser.json` et initialiser `YTMusic` avec retry
  - [x] Nettoyer le titre via `clean_title()` depuis utils
  - [x] Construire la requête : `f"{artist} {title}"`
  - [x] Envoyer vers `ytmusic.search(query)`
  - [x] Capturer les résultats pour évaluation (AC2, AC3 des stories suivantes)

- [x] Tester les expressions régulières de nettoyage (AC: 2)
  - [x] Vérifier que `(Remastered)`, `[Live]`, `feat. X` sont supprimés
  - [x] Vérifier que les tirets inutiles (`- Radio Edit`) sont supprimés
  - [x] Vérifier que les parenthèses/crochets vides sont supprimés
  - [x] Vérifier que les espaces excédentaires sont normalisés

- [x] Intégrer dans la boucle principale de matcher (AC: 1)
  - [x] Charger library.csv (idempotence matcher.py : skip lignes non-`pending` ou avec `yt_video_id`)
  - [x] Itérer sur les lignes `pending` sans `yt_video_id`
  - [x] Pour chaque ligne : appliquer AC1, AC2, AC3
  - [x] Préparer les résultats pour Story 3.2 (scoring)

## Notes développeur

### Contexte critique : Point d'entrée de l'enrichissement YouTube Music

Cette story **marque le début de la Phase 2 (Matching)** du pipeline. C'est le moment où le fichier `library.csv` commence à se remplir d'informations YouTube Music.

**Dépendances absolues :**
- ✅ Story 1.1 — `utils.py` avec `clean_title()` et `score_match()` déjà implémentés
- ✅ Story 1.4 — Validation préemptive de `browser.json` au démarrage du matcher
- ✅ Story 2.4 — `library.csv` existe avec colonnes figées (FIELDNAMES de utils)

### Architecture décisionnelle — Recherche YouTube Music

#### Question 1 : Initialisation de YTMusic

**Décision :** Initialiser `YTMusic` une seule fois au démarrage de `main()`, avant la boucle.

**Rationale :**
- `YTMusic` charge `browser.json` et établit un contexte de session
- Créer une instance par ligne serait inefficace (overhead I/O)
- Une seule instance est réutilisée pour toute la boucle
- L'instance est validée préemptivement (Story 1.4)

**Implémentation :**
```python
def main():
    config = load_config()  # Validation config avant tout
    ytmusic = YTMusic(auth="browser.json")  # Charge browser.json ici
    # Boucle sur library.csv
```

**Note :** Si `browser.json` est absent ou expiré, cette ligne lève une exception — Story 1.4 garantit que ce n'arrive pas (appel test au démarrage).

#### Question 2 : Construction et formatage de la requête

**Décision :** Requête = `artist + " " + titre_nettoyé` (espace simple entre les deux).

**Rationale :**
- YouTube Music API accepte les requêtes libres (pas de champs structurés)
- L'ordre artiste-titre améliore la pertinence
- Le nettoyage via `clean_title()` élimine déjà le bruit
- Exemple : `"Daft Punk Get Lucky"` (vs `"Daft Punk Get Lucky (Remastered)"`)

**Implémentation :**
```python
from utils import clean_title

cleaned_title = clean_title(row["title"])
query = f"{row['artist']} {cleaned_title}".strip()
results = ytmusic.search(query, filter="songs")
```

#### Question 3 : Gestion des "Various Artists"

**Décision :** Pattern de détection stricte, avec fallback conservateur.

**Rationale :**
- "Various Artists" est un cas limite bien connu (compilations, bandes sonores)
- Searching "Various Artists" + titre générique produit des faux positifs massifs
- Préférer l'escalade en `manual_review` que d'importer la mauvaise chanson
- NFR2 (confiance totale) > NFR7 (automatisation max)

**Implémentation :**
```python
# Détection conservatrice des Various Artists
VARIOUS_ARTIST_PATTERNS = [
    "Various Artists",
    "VA", "V.A.",
    "Compilation",
    "Unknown Artist",
    "Artist Unknown"
]

if any(v.lower() in row["artist"].lower() for v in VARIOUS_ARTIST_PATTERNS):
    row["status"] = STATUS_MANUAL_REVIEW
    row["yt_video_id"] = ""
    row["yt_url"] = ""
    row["yt_score"] = ""
    write_csv(CSV_PATH, rows, FIELDNAMES)  # Persistance immédiate
    continue  # Passer à la ligne suivante
```

**Anti-pattern :** Ne PAS chercher "Various Artists + titre". Cela crée des doublons dans YouTube Music et viole la confiance utilisateur.

#### Question 4 : Persistance CSV (idempotence matcher.py)

**Décision :** Idempotence = traiter uniquement les lignes `pending` sans `yt_video_id`.

**Rationale :**
- Cette story (3.1) ne remplit que la requête ; les résultats arrivent plus tard (3.2/3.3)
- Mais l'architecture exige déjà une persistance CSV pour isolation des erreurs (NFR4)
- Donc : même si on n'écrit que des requêtes (étape intermédiaire), on écrit immédiatement

**Implémentation :**
```python
# En début de boucle : skip si la ligne est déjà traitée
for row in rows:
    if row["status"] != STATUS_PENDING or row["yt_video_id"]:
        continue  # Cette ligne a déjà un yt_video_id → skip

    # Traiter cette ligne (AC1, AC2, AC3)
    ...

    # Écrire immédiatement (finally block ou dans le traitement)
    write_csv(CSV_PATH, rows, FIELDNAMES)
```

**Note :** Cette condition assure qu'un re-run du matcher ne re-envoie pas de requêtes YouTube Music pour les morceaux déjà enrichis.

### Gestion des erreurs — Contexte pour Story 3.4

Cette story (3.1) **ne gère pas les erreurs réseau**. Les erreurs seront traitées dans Story 3.4 (résilience). Donc :
- Si `ytmusic.search()` lève une exception → laisser remonter (crash contrôlé, ajouté dans Story 3.4 avec retry/backoff)
- Pas de `try/except` ici
- Story 3.4 enveloppera tout dans un bloc `try/except` avec backoff exponentiel

### Validations à respecter

**AC1 — Critique :** Chaque ligne `pending` sans `yt_video_id` doit au minimum recevoir une tentative de requête YouTube Music.

**AC2 — Critique :** Les patterns regex de `clean_title()` doivent supprimer au minimum : `(Remastered)`, `[Live]`, `feat. X`, `- Radio Edit`.

**AC3 — Critique :** "Various Artists" doit être détecté ET marquer directement en `manual_review` sans recherche.

---

## Contexte architecturale détaillé

### Flux de données — Phase 2, Step 1

```
library.csv (lignes pending, sans yt_video_id)
    │
    ├─ AC1: Nettoyer le titre via clean_title()
    │
    ├─ AC2: Construire requête "artist + titre_nettoyé"
    │
    ├─ AC3: Détecter "Various Artists" → manual_review (sortie directe)
    │
    └─ AC1: Envoyer vers ytmusic.search(query, filter="songs")
         │
         → Résultats (détails dans Story 3.2)
         → library.csv mis à jour immédiatement
```

**Colonnes concernées dans cette story :**
- `status` : reste `pending` pour les morceaux traités (changé en 3.2 via scoring)
- `yt_video_id` : reste vide pour l'instant (renseigné en 3.2 après scoring)
- `yt_url` : reste vide (construit en 3.3)
- `yt_score` : reste vide (calculé en 3.2)

### Dépendances technologiques critiques

| Bibliothèque | Rôle | Note |
|---|---|---|
| `ytmusicapi` | Recherche YouTube Music via API non-officielle | Version 1.11.5 (fixée) — non-officielle, risque rupture |
| `utils.clean_title()` | Nettoyage annotations (déjà impl. en 1.1) | Regex patterns figés — NE PAS modifier |
| `browser.json` | Authentification (généré manuellement en 1.3) | Durée de vie limitée — validation préemptive en 1.4 |

**Vérification du chargement YTMusic :**
```python
# À tester manuellement en premier
from ytmusicapi import YTMusic
ytmusic = YTMusic(auth="browser.json")
results = ytmusic.search("Daft Punk Get Lucky", filter="songs")
print(results)  # Doit retourner une liste non-vide (ou vide si pas de résultats, mais pas d'erreur)
```

### Configuration — Paramètres utilisés dans cette story

Aucun paramètre de configuration n'affecte cette story directement. Cependant, `config.yaml` est chargé pour validation (Story 1.2 + 1.4 garantissent sa présence).

**Paramètres affectant les stories ultérieures (3.2) :**
- `confidence_threshold` (défaut 85) → seuil de match validé
- `low_confidence_threshold` (défaut 70) → seuil de faible confiance
- `duration_tolerance` (défaut 10) → tolérance durée en secondes

### État de la codebase avant cette story

**Fichiers existants et figés :**
- ✅ `utils.py` (complet, stable depuis 1.1)
  - ✅ `clean_title()` — regex patterns, utiliser tel quel
  - ✅ `score_match()` — sera utilisé en 3.2, pas ici
  - ✅ `load_config()` — déjà appelé
  - ✅ `read_csv()` / `write_csv()` — utiliser pour I/O CSV
  - ✅ `STATUS_*` constants — importer toutes les variantes pertinentes

- ✅ `config.yaml` (structure fixe depuis 1.2)
  - ✅ Tous les paramètres
  - ✅ `music_folder` — pas utilisé en matcher.py
  - ✅ `confidence_threshold`, `low_confidence_threshold`, `duration_tolerance` — utilisés en 3.2/3.3

- ✅ `requirements.txt` (versions fixées depuis 1.1)
  - ✅ `ytmusicapi==1.11.5` — utiliser cette version exacte
  - ✅ Autres dépendances

- ✅ `.gitignore` (figé depuis 1.1)
  - ✅ `browser.json` listée
  - ✅ `library.csv` listée

- ✅ `scanner.py` (squelette depuis 1.1, complété en épics 2)
  - ✅ Produit `library.csv` avec lignes `pending`, `duplicate`, `error_read`

- ✅ `matcher.py` (squelette depuis 1.1, en cours de construction)
  - [ ] Story 3.1 : recherche YouTube Music + nettoyage titres (CETTE STORY)
  - [ ] Story 3.2 : scoring de similarité + vérification durée
  - [ ] Story 3.3 : génération URLs + persistance CSV
  - [ ] Story 3.4 : résilience réseau + progression

### Bonne pratique — Éviter les anti-patterns

```python
# ❌ Ne pas initialiser YTMusic dans la boucle
for row in rows:
    ytmusic = YTMusic(auth="browser.json")  # ← MAUVAIS (overhead)
    results = ytmusic.search(...)

# ✅ Initialiser une fois avant la boucle
ytmusic = YTMusic(auth="browser.json")
for row in rows:
    results = ytmusic.search(...)  # ← BON

# ❌ Ne pas utiliser yaml.load() (risque sécurité)
config = yaml.load(f)  # ← MAUVAIS

# ✅ Utiliser yaml.safe_load()
config = yaml.safe_load(f)  # ← BON (déjà impl. en utils)

# ❌ Ne pas vérifier "Various Artists" après la recherche
results = ytmusic.search("Various Artists Song Title")  # ← MAUVAIS (faux positifs)

# ✅ Vérifier AVANT la recherche
if "Various Artists" in artist:
    row["status"] = STATUS_MANUAL_REVIEW
    continue  # ← BON

# ❌ Ne pas modifier FIELDNAMES ou les noms de colonnes
row["yt_video_id_temp"] = "..."  # ← MAUVAIS (casse le contrat)

# ✅ Utiliser FIELDNAMES depuis utils.py
FIELDNAMES = [
    "filepath", "artist", "title", "album", "duration",
    "status", "yt_video_id", "yt_url", "yt_score", "error_message"
]
# ← BON (ces 10 colonnes sont le contrat figé)
```

---

## Notes de développement ultérieures

### Story 3.2 : Scoring & Vérification de durée

Les résultats retournés par `ytmusic.search()` dans cette story seront évalués dans 3.2 pour :
1. Extraire le meilleur résultat (1er résultat par défaut)
2. Calculer un score `rapidfuzz` via `score_match()`
3. Vérifier la durée YouTube Music vs durée locale
4. Assigner un statut : `pending` (bon score) / `low_confidence` (score intermédiaire) / `failed` (pas de bon match)

**Préparation :** Cette story (3.1) retourne les résultats bruts de YouTube Music. Story 3.2 les enrichira avec scores et durées.

### Story 3.3 : Génération d'URLs

Les `yt_video_id` assignés en Story 3.2 seront convertis en URLs cliquables `https://music.youtube.com/watch?v={yt_video_id}` dans Story 3.3.

### Story 3.4 : Résilience réseau

Les appels `ytmusic.search()` peuvent lever des exceptions (rate limit HTTP 429, timeout, etc.). Story 3.4 enveloppera avec retry/backoff exponentiel.

---

## Références

- [Source: `_bmad-output/planning-artifacts/epics.md` — Epic 3, Story 3.1 (User Story & AC BDD)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Core Architectural Decisions" (ytmusicapi, authentification browser.json)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Implementation Patterns" (idempotence matcher, backoff, gestion erreurs)]
- [Source: `_bmad-output/planning-artifacts/architecture.md` — "Naming Patterns" (STATUS_* constants, snake_case)]
- [Source: `_bmad-output/planning-artifacts/prd.md` — "User Journeys — Parcours 1" (matching + URLs de vérification)]
- [Source: Story 1.1 — dev notes sur `utils.py` (clean_title, score_match)]

## Dev Agent Record

### Modèle d'agent utilisé

claude-haiku-4-5-20251001

### Références de log de débogage

Story 3.1 implementation completed with full test coverage.

### Notes de complétion

- [x] AC1 — Recherche YouTube Music fonctionnelle
  - Fonction `search_youtube_music(ytmusic, query)` implémentée avec `filter="songs"`
  - Retourne liste des résultats ou [] si pas de résultats

- [x] AC2 — Nettoyage des annotations parasites validé
  - Fonction `build_search_query(artist, title)` utilise `clean_title()` depuis utils.py
  - Tests validant suppression de (Remastered), [Live], feat., - Radio Edit
  - Espaces et parenthèses vides normalisés correctement

- [x] AC3 — Détection "Various Artists" → manual_review
  - Fonction `detect_various_artists(artist)` implémentée avec 6 patterns
  - Détecte: "Various Artists", "VA", "V.A.", "Compilation", "Unknown Artist", "Artist Unknown"
  - Marque immédiatement comme `manual_review` sans faire requête YouTube Music

- [x] Idempotence matcher.py validée
  - `process_matcher_loop()` skip lignes avec statut != pending ou yt_video_id rempli
  - CSV persisté immédiatement après chaque changement
  - Tests validant le comportement d'idempotence

- [x] Tests unitaires et d'intégration
  - 19 tests créés dans test_matcher.py, tous passants (100% pass rate)
  - Tests couvrant AC1, AC2, AC3, idempotence, intégration avec clean_title()
  - Mocks appropriés pour YTMusic et CSV I/O

### Liste des fichiers

- `matcher.py` (complet, 119 lignes)
  - `detect_various_artists()` — détection AC3
  - `build_search_query()` — construction requête AC1+AC2
  - `search_youtube_music()` — appel API YouTube Music AC1
  - `process_matcher_loop()` — intégration boucle principale
  - `main()` — point d'entrée avec initialisation YTMusic

- `test_matcher.py` (nouveau, 241 lignes)
  - 19 tests pour AC1, AC2, AC3, idempotence, intégration
  - Mocks appropriés pour YTMusic et filesystem CSV

---

## Journal des modifications

- 2026-02-23 : Story 3.1 — Recherche YouTube Music et nettoyage des titres. Contexte exhaustif fourni : architecture de recherche YouTube Music, gestion des "Various Artists", idempotence matcher, dépendances technologiques, anti-patterns à éviter. Prêt pour implémentation par agent dev.

- 2026-02-23 : Story 3.1 TERMINÉE — Implementation complète avec tests
  - Fonction `detect_various_artists()` pour AC3
  - Fonction `build_search_query()` intégrant `clean_title()` pour AC1+AC2
  - Fonction `search_youtube_music()` pour appel YouTube Music API
  - Boucle principale `process_matcher_loop()` avec idempotence
  - 19 tests unitaires et d'intégration (100% pass rate)
  - Code prêt pour Story 3.2 (scoring & vérification durée)
