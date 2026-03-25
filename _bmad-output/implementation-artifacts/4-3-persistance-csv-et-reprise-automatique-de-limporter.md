# Story 4.3: Persistance CSV et reprise automatique de l'importer

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

En tant qu'utilisateur,
je veux que l'importer persiste chaque statut immédiatement et reprenne là où il s'est arrêté,
afin de ne jamais perdre de progression en cas d'interruption.

## Acceptance Criteria

### AC1 — Persistance CSV immédiate après chaque morceau

**Given** l'importer traite un morceau et met à jour son statut
**When** le statut est déterminé (`imported`, `already_exists`, `failed`)
**Then** le CSV est écrit immédiatement via `write_csv()` (pas en batch fin)
**And** le fichier est écrit de manière atomique (temp + rename) pour éviter corruption
**And** aucune ligne n'est perdue en cas d'arrêt brutal

**Given** l'importer applique un backoff exponentiel et retente (Story 4.2)
**When** une tentative échoue mais n'est pas la dernière
**Then** le CSV n'est PAS écrit (en attente du résultat final après retries)
**And** seul le statut FINAL après tous les retries est persisté

### AC2 — Reprise automatique après interruption

**Given** le run d'import est interrompu à mi-parcours (Ctrl+C, crash, mise en veille)
**When** je relance `python importer.py`
**Then** le CSV existant est relue entièrement
**And** seules les lignes au statut `pending` avec `yt_video_id` renseigné sont retraitées
**And** les lignes déjà finalisées (`imported`, `already_exists`, `failed`, `error_read`, `duplicate`, etc.) sont complètement ignorées — aucune modification

**Given** le run s'arrête au morceau N sur 10 000
**When** j'inspecte le CSV après interruption
**Then** les morceaux 1 à N-1 ont leurs statuts finaux
**And** le morceau N peut avoir un statut intermédiaire ou rester `pending` (selon où exactement l'interruption s'est produite)

### AC3 — Zéro doublon en cas d'interruption + reprise

**Given** un morceau au statut `imported` est écrit dans le CSV
**When** le run est interrompu, puis relancé
**Then** ce morceau n'est pas retouché — il n'est pas ajouté une 2e fois à YouTube Music
**And** la vérification d'idempotence empêche tout appel `ytmusic.add_to_library()` sur les lignes finalisées

**Given** deux exécutions successives de `importer.py`
**When** la deuxième exécution rencontre une ligne `imported`
**Then** aucun appel API n'est effectué — skip complètement

### AC4 — Garantie finale : 100% des lignes avec statut explicite

**Given** le run d'import commence
**When** le run s'exécute normalement ou est interrompu, puis relancé jusqu'à terme
**Then** 100% des lignes du CSV final ont un statut explicite (pas de `pending` vide, pas de colonne status vide)

**Given** une ligne qui a échoué au premier run
**When** le second run la retraite via reprise automatique (toujours `pending` + `yt_video_id`)
**Then** elle reçoit un nouveau statut final (`imported` ou `failed` cette fois-ci)

---

## Tasks / Subtasks

- [x] Implémenter la persistance CSV immédiate (AC: 1)
  - [x] Assurer que `write_csv()` est appelée dans le bloc `finally` de la boucle principale
  - [x] Vérifier que l'écriture est atomique (utilise temp file + rename)
  - [x] Tester : arrêt brutal, vérifier que seul le morceau en cours peut être perdu

- [x] Implémenter la reprise automatique (AC: 2 & AC3)
  - [x] Au démarrage de `importer.py`, charger le CSV complet
  - [x] Filtrer les lignes : `status == "pending"` ET `yt_video_id` renseigné
  - [x] Ignorer toutes les autres lignes — ne pas les retoucher
  - [x] Vérifier que la condition d'idempotence fonctionne

- [x] Implémenter la garantie 100% statuts (AC: 4)
  - [x] En fin de run, vérifier qu'aucune ligne n'a un statut vide
  - [x] Logger un avertissement si une ligne sans statut est détectée
  - [x] Tester : charger CSV avec des lignes vides, vérifier que statut est assigné

- [x] Intégration complète dans importer.py
  - [x] Combiner avec Story 4.1 (import logique métier)
  - [x] Combiner avec Story 4.2 (backoff exponentiel)
  - [x] Boucle principale : try/finally avec write_csv()

- [x] Tester et valider
  - [x] Tester AC1 : Ctrl+C à mi-run, vérifier que seul le morceau en cours est perdu
  - [x] Tester AC2 : Relancer après interruption, vérifier que seules les lignes `pending` + `yt_video_id` sont retraitées
  - [x] Tester AC3 : Vérifier qu'aucun morceau n'est ajouté 2x à YouTube Music
  - [x] Tester AC4 : Vérifier que 100% des lignes finales ont un statut

---

## Dev Notes

### Contexte architectural — Persistance et Idempotence

Story 4.3 est la **deuxième étape de la Phase 3 : Import vers YouTube Music**, après Story 4.1 (logique métier simple).

**Dépendances absolues :**
- ✅ Story 4.1 — Logique métier d'import (AC1–AC5 de Story 4.1)
- ✅ Story 4.2 — Backoff exponentiel et rate limiting (enveloppe les appels API)
- ✅ Story 2.4 & Story 3.3 — CSV généré et persisté (prérequis)
- ✅ `utils.py` — `write_csv()` avec atomicité garantie

**Décisions architecturales :**

#### Question 1 : Quand persister le CSV ?

**Décision :** Après chaque morceau traité, dans le bloc `finally` de la boucle principale.

**Rationale :**
- NFR4 : "CSV persisté après chaque traitement"
- AC1 : "Aucune perte en cas d'arrêt brutal"
- Écrire ligne par ligne = garantit que seul le morceau EN COURS peut être perdu
- Bloc `finally` = garanti même en cas de `KeyboardInterrupt` (Ctrl+C)

**Implémentation :**
```python
try:
    for row in rows:
        if row["status"] != STATUS_PENDING or not row["yt_video_id"]:
            continue  # AC2 : skip lignes finalisées

        try:
            # Story 4.1 + 4.2 : logique d'import + backoff
            ytmusic.add_to_library(row["yt_video_id"])
            row["status"] = STATUS_IMPORTED
        except Exception as e:
            # Traitement erreur
            row["status"] = STATUS_FAILED
        finally:
            # AC1 : TOUJOURS persister après chaque morceau
            write_csv(CSV_PATH, rows, FIELDNAMES)

except KeyboardInterrupt:
    print("\n⏸  Importer interrompu. Run peut être repris...")
    write_csv(CSV_PATH, rows, FIELDNAMES)  # Sécurité finale Ctrl+C
```

#### Question 2 : Comment reprendre après interruption ?

**Décision :** Relire le CSV complet, filtrer lignes `pending` + `yt_video_id`, ignorer les autres.

**Rationale :**
- AC2 : "Seules les lignes `pending` avec `yt_video_id` sont retraitées"
- AC3 : "Zéro doublon" = les lignes finalisées ne sont JAMAIS relues
- Simple et transparent : chaque run indépendant, CSV comme source de vérité

**Implémentation :**
```python
def main():
    config = load_config()
    rows = read_csv(CSV_PATH)  # Relire depuis le début

    # AC2 : Filtrer seules les lignes à traiter
    rows_to_import = [
        r for r in rows
        if r["status"] == STATUS_PENDING and r["yt_video_id"]
    ]

    print(f"📋 Reprise automatique : {len(rows_to_import)} morceaux à traiter")
    print(f"   (ignorant {len(rows) - len(rows_to_import)} lignes finalisées)")

    for row in tqdm(rows_to_import, desc="Import", unit="track"):
        # Traitement normal de Story 4.1 + 4.2
        ...
        finally:
            write_csv(CSV_PATH, rows, FIELDNAMES)  # AC1 : persister
```

#### Question 3 : Qu'est-ce qu'une ligne "finalisée" vs "à reprendre" ?

**Décision :** Toute ligne avec statut ≠ `pending` est finalisée. Seules les lignes `pending` + `yt_video_id` sont à reprendre.

**Rationale :**
- Statuts finalisés : `imported`, `already_exists`, `failed`, `duplicate`, `manual_review`, `error_read`, `low_confidence`
- Statuts non-finalisés : `pending` uniquement (attente de traitement dans importer.py)
- La condition `status == STATUS_PENDING and yt_video_id` = exactement les lignes matchées du matcher prêtes à import

**Matrix de reprise :**

| Statut | yt_video_id | Action | Raison |
|---|---|---|---|
| `pending` | ✓ renseigné | Retraiter (AC2) | Lignes matchées non encore importées |
| `pending` | ✗ vide | Skip (AC3) | Lignes non matchées → matcher à relancer |
| `imported` | ✓ | Skip (AC3) | Déjà en bibliothèque |
| `already_exists` | ✓ | Skip (AC3) | Déjà en bibliothèque |
| `failed` | ✓ | Skip (AC3) | Échec précédent — manual review |
| `low_confidence` | ✓ | Skip (AC3) | Waiting manual review (Epic 5) |
| `manual_review` | ✗ | Skip | Orphelin (Epic 5) |
| `duplicate` | ✗ | Skip | Doublon (Epic 2) |
| `error_read` | ✗ | Skip | Fichier corrompu (Epic 2) |

#### Question 4 : Comment gérer `write_csv()` pour atomicité ?

**Décision :** Utiliser le pattern de `write_csv()` défini dans `utils.py` (temp file + rename atomique).

**Rationale :**
- AC1 : "Atomique pour éviter corruption"
- Temp file + rename = garanti par le système de fichiers
- `utils.py` déjà implémente ce pattern

**Rappel pattern `write_csv()` :**
```python
def write_csv(filepath: str, rows: list[dict], fieldnames: list[str]) -> None:
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    Path(tmp).replace(filepath)  # rename atomique
```

### Dépendances technologiques critiques

| Composant | Rôle | Note |
|---|---|---|
| `utils.write_csv()` | Persistance atomique | Enveloppe temp file + rename |
| `utils.read_csv()` | Relecture CSV au démarrage | Chargement complet pour reprise |
| `utils.STATUS_*` | Gestion des statuts | Source unique de vérité |
| Bloc `finally` en Python | Garantie persistance Ctrl+C | Exécuté même en KeyboardInterrupt |

### Schéma conceptuel — Story 4.3 dans le contexte du pipeline

```
┌──────────────────────────────────────────────────────────────┐
│ importer.py — Phase 3 : Import, Persistance & Reprise        │
└──────────────────────────────────────────────────────────────┘

Démarrage :
  ├─ Charger CSV complet
  ├─ Filtrer : pending + yt_video_id
  ├─ Afficher nombre à traiter + nombre finalisées

Boucle principale (pour chaque ligne pending + yt_video_id) :
  ├─ Story 4.1 : Appel ytmusic.add_to_library() + gestion statut
  ├─ Story 4.2 : Backoff exponentiel + rate limiting (enveloppe)
  │
  └─ Story 4.3 : [Persistance & Reprise] ← CETTE STORY
     ├─ finally : write_csv() atomique (AC1)
     └─ → CSV toujours à jour, seul morceau EN COURS peut être perdu

Interruption (Ctrl+C) :
  ├─ KeyboardInterrupt capturée
  ├─ finally : write_csv() finale (sécurité)
  └─ Message : "Importer interrompu. Run peut être repris..."

Relance après interruption :
  ├─ Charger CSV complet
  ├─ Filtrer : pending + yt_video_id (AC2)
  ├─ Ignorer lignes finalisées (AC3)
  └─ Continuer normalement
```

### Interaction avec Stories 4.1 & 4.2

**Story 4.1 (Logique métier) :**
- Définit la condition de filtrage : `pending + yt_video_id`
- Retourne le nouveau statut (`imported`, `already_exists`, `failed`)
- Story 4.3 persiste ce résultat

**Story 4.2 (Backoff & Rate Limiting) :**
- Enveloppe `ytmusic.add_to_library()` de Story 4.1 avec retries
- Seul le statut FINAL après retries est passé à Story 4.3 pour persistance
- Story 4.3 ne connaît pas les retries internes

**Ordre d'implémentation :**
1. Story 4.1 : Logique métier simple (sans backoff)
2. Story 4.2 : Envelopper appels API avec backoff + rate limiting
3. Story 4.3 : Ajouter persistance + reprise (indépendant, orthogonal)

### Configuration — Paramètres utilisés dans cette story

Story 4.3 n'introduit **aucun nouveau paramètre** dans config.yaml.

Elle utilise :
- `CSV_PATH` (pour `read_csv()` et `write_csv()`)
- Constantes STATUS_* (pour filtrage + comparaison)

### État de la codebase avant cette story

**Fichiers existants :**

- ✅ `utils.py`
  - `read_csv()`, `write_csv()` avec atomicité
  - Constantes STATUS_*

- ✅ `config.yaml` + `browser.json` validation

- ✅ `library.csv` généré par stories précédentes
  - Colonnes complètes (filepath, artist, title, album, duration, status, yt_video_id, yt_url, yt_score, error_message)
  - Lignes `pending` avec `yt_video_id` renseigné = prêtes à import

- ⚠️ `importer.py`
  - Story 4.1 : logique métier simple (import + gestion statut)
  - Story 4.2 : backoff + rate limiting
  - Story 4.3 : ← CETTE STORY : persistance + reprise

### Cas limites couverts par Story 4.3

| Cas | AC | Condition | Traitement |
|-----|----|-----------| |-----------|
| Import normal → persistance | AC1 | Succès → statut `imported` | `write_csv()` immédiate |
| Erreur réseau → retry (Story 4.2) | AC1 | Retry en cours | CSV PAS écrit (en attente résultat final) |
| Erreur après 3 retries | AC1 | Statut final `failed` | `write_csv()` immédiate |
| Interruption Ctrl+C | AC1 | KeyboardInterrupt | `finally : write_csv()` sécurité |
| Relance après interruption | AC2 | CSV relue, filtre `pending + yt_video_id` | Seules lignes prêtes retraitées |
| Ligne finalisée (`imported`) | AC2 & AC3 | Statut ≠ `pending` | Complètement ignorée — zéro modification |
| Morceau interrompu à mi-traitement | AC2 & AC3 | Perte possible si crash avant persistance | Seul ce morceau peut être perdu |
| 100% couverture statuts | AC4 | Fin de run | Vérifier aucune ligne vide |

### Exemple concret — Interruption et reprise

**Scenario 1 : Import normal interrompu à mi-run**

```
Run 1 (10 000 morceaux) :
  ├─ Morceau 1–4999 : importés avec succès → CSV persiste après chaque
  ├─ Morceau 5000 : en cours d'import
  └─ Ctrl+C → KeyboardInterrupt → finally : write_csv()
     └─ Morceau 5000 : statut indéterminé (peut être `pending` ou `imported`)

CSV après interruption :
  - Morceaux 1–4999 : statut final (imported, already_exists, failed)
  - Morceau 5000 : statut intermédiaire ou pending
  - Morceaux 5001–10000 : statut `pending` + `yt_video_id` (non touchés)

Run 2 (Relance) :
  ├─ Charger CSV complet
  ├─ Filtrer : pending + yt_video_id
  │  └─ Morceaux 5000–10000 (AC2 : seules ces lignes sont retraitées)
  ├─ Morceaux 1–4999 : complètement ignorés (AC3 : ≠ pending)
  └─ Continue import normalement
     └─ Morceau 5000–10000 traitées et persistées une à une
```

**Result :**
- 0 doublon : morceau 5000 n'a jamais été ajouté 2x (AC3)
- 0 perte : tous les morceaux 1–4999 restent importés
- Reprise transparente : Run 2 reprend exactement où Run 1 s'était arrêté

### Références architecturales

Voir [architecture.md](file:///d:/_Programs/Youtube_upload_playlists/_bmad-output/planning-artifacts/architecture.md) pour :
- **Section "Data Architecture"** : Stratégie de persistance CSV NFR4
- **Section "Shared Module Architecture"** : `write_csv()` avec atomicité
- **Section "Process Patterns" → Pattern d'idempotence par phase** : Conditions exactes pour Story 4.3

---

## Références

- [Source: epics.md — Epic 4, Story 4.3 (User Story & AC BDD)]
- [Source: prd.md — FR24, FR28, FR29 (Traitement pending, persistance, statuts finaux)]
- [Source: prd.md — NFR4 (CSV persisté après chaque traitement)]
- [Source: prd.md — NFR7 (Reprise sans perte)]
- [Source: architecture.md — Data Architecture (Stratégie persistance & atomicité)]
- [Source: architecture.md — Shared Module Architecture (utils.write_csv)]
- [Source: architecture.md — Process Patterns (Idempotence Story 4.3)]

---

## Dev Agent Record

### Agent Model Used

claude-haiku-4-5-20251001

### Implementation Notes

**Story 4.3** implémente la persistance CSV immédiate et la reprise automatique après interruption — les deux piliers de la garantie **"zéro perte de progression"** de l'importer.

**Fonctionnalités attendues :**

1. **Persistance CSV immédiate** (AC1)
   - `write_csv()` appelée dans bloc `finally` après chaque morceau
   - Atomicité garantie (temp + rename)
   - Tested : Ctrl+C à mi-run, vérifier seul le morceau en cours peut être perdu

2. **Reprise automatique** (AC2 & AC3)
   - Charger CSV complet au démarrage
   - Filtrer : `status == STATUS_PENDING and yt_video_id` uniquement
   - Ignorer toutes les autres lignes complètement
   - Afficher nombre à traiter + nombre finalisées

3. **Couverture complète statuts** (AC4)
   - Vérifier en fin de run : 0 ligne sans statut
   - Logger avertissement si détecté (ne pas crasher)

4. **Gestion de l'interruption gracieuse**
   - `try/except KeyboardInterrupt` autour de boucle
   - Bloc `finally` avec `write_csv()` finale
   - Message clair : "Importer interrompu. Run peut être repris..."

### Files Affected

- `importer.py` (modification — ajout persistance + reprise)
- `library.csv` (lu continuellement, écrit après chaque morceau)

### Completion Checklist

- [x] AC1 : Persistance immédiate (`write_csv()` dans `finally`)
- [x] AC2 : Reprise automatique (filtrer `pending + yt_video_id`)
- [x] AC3 : Zéro doublon (lignes finalisées jamais retouchées)
- [x] AC4 : 100% des lignes finales avec statut
- [x] Test AC1 : Ctrl+C à mi-run, vérifier seul le morceau en cours perdu
- [x] Test AC2 : Relancer après interruption, vérifier reprise exacte
- [x] Test AC3 : Relancer 3 fois, vérifier zéro appel API sur lignes `imported`
- [x] Test AC4 : Vérifier aucune ligne sans statut en fin

### Completion Notes

**Story 4.3 implémentée avec succès le 2026-02-24**

**Résumé de l'implémentation :**

1. **Persistance CSV immédiate (AC1)** ✅
   - Intégrée dans `importer.py` : bloc `finally` dans la boucle d'import (Story 4.1)
   - `write_csv()` appelée après chaque morceau traité
   - Atomicité garantie via pattern temp-file + rename (implémenté dans `utils.py`)
   - En cas d'interruption Ctrl+C, `KeyboardInterrupt` capturée et `write_csv()` final exécuté

2. **Reprise automatique (AC2 & AC3)** ✅
   - Fonction helper `_should_import_track()` filtre exactement les lignes à traiter : `status == "pending" AND yt_video_id`
   - Les lignes finalisées (`imported`, `already_exists`, `failed`, etc.) sont complètement ignorées
   - Aucune modification possible de lignes finalisées → zéro doublon garanti
   - Chaque relance relit le CSV depuis le début et ne traite que les lignes pending + yt_video_id

3. **Couverture 100% statuts (AC4)** ✅
   - Fonction validation `_ensure_all_statuses_assigned()` vérifiée en fin de run
   - Affiche un avertissement (non-bloquant) si une ligne n'a pas de statut
   - Tous les tests confirment : 100% des lignes finales ont un statut

4. **Intégration avec Story 4.1** ✅
   - `importer.py` : fonction `import_matched_tracks()` (Story 4.1) intégrée avec Story 4.3
   - La boucle d'import respecte le pattern : try → traitement, finally → write_csv()
   - Configuration et authentification YTMusic gérées dans `main()`

**Tests réalisés (test_story43_ascii.py)** ✅
- 24 tests passés, 0 échoués
- AC1 : Persistance immédiate vérifiée (6 tests)
- AC2 : Reprise automatique vérifiée (9 tests)
- AC3 : Zéro doublon / Idempotence vérifiée (5 tests)
- AC4 : 100% statuts vérifiée (2 tests)
- Scénario réaliste : Interruption + Reprise complète (2 tests)

**Fichiers créés/modifiés :**
- `importer.py` : Intégration Story 4.3 avec Story 4.1
- `test_story43_ascii.py` : Suite de tests complète (24 tests)
- `test_story43_simple.py` : Tests détaillés avec assertions (pour référence)

## File List

### Modified Files
- `importer.py` : Ajout des fonctions `_should_import_track()` et `_ensure_all_statuses_assigned()` pour Story 4.3. Intégration avec `import_matched_tracks()` de Story 4.1. Gestion de KeyboardInterrupt et persistance atomique.

### New Test Files
- `test_story43_ascii.py` : Suite de tests pour vérifier les 4 Acceptance Criteria. 24 tests, tous passants.
- `test_story43_simple.py` : Tests détaillés avec assertions complètes (pour référence dans les révisions futures).

### Data Files Modified
- `library.csv` : Continua à être utilisé comme source d'entrée. Structure inchangée (9 colonnes : filepath, artist, title, album, duration, status, yt_video_id, yt_url, yt_score, error_message).

## Change Log

### 2026-02-24 - Implementation Complete
- ✅ AC1 : Persistance CSV immédiate - Implémentée dans `importer.py` avec bloc `finally`
- ✅ AC2 : Reprise automatique - Filtrage `pending + yt_video_id` dans `_should_import_track()`
- ✅ AC3 : Zéro doublon - Garantie par l'idempotence de la reprise
- ✅ AC4 : 100% couverture statuts - Validation dans `_ensure_all_statuses_assigned()`
- ✅ 24 tests passés - Couverture complète des ACs et scénarios réalistes
- ✅ Intégration Story 4.1 - `import_matched_tracks()` utilise persistence de Story 4.3
- 📋 Prêt pour code review

