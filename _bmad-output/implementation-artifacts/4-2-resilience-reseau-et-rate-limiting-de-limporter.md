# Story 4.2: Résilience réseau et rate limiting de l'importer

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

En tant qu'utilisateur,
je veux que l'importer résiste aux erreurs réseau et respecte les limites de l'API YouTube Music,
afin de pouvoir lancer un import overnight sans risque de ban ou de perte de données.

## Acceptance Criteria

### AC1 — Application du délai configurable entre appels API

**Given** un délai `api_delay` configuré dans `config.yaml` (ex: 0.5 secondes)
**When** l'importer traite chaque morceau
**Then** il attend ce délai entre chaque appel `ytmusic.add_to_library()`
**And** le délai ne bloque pas la barre de progression `tqdm`

**Given** `api_delay` = 0 ou non configuré
**When** l'importer est lancé
**Then** aucun délai ne s'ajoute entre les appels (comportement burst, non recommandé mais possible)

### AC2 — Backoff exponentiel sur HTTP 429 (rate limit)

**Given** une réponse HTTP 429 (Too Many Requests) de YouTube Music API
**When** l'importer reçoit cette réponse
**Then** il applique un backoff exponentiel : `sleep(2^attempt)` secondes, avec max 3 tentatives
  - Tentative 1 : sleep 2^0 = 1 secondes, retry
  - Tentative 2 : sleep 2^1 = 2 secondes, retry
  - Tentative 3 : sleep 2^2 = 4 secondes, retry
  - Si 3 tentatives échouent : assigner statut `failed`

**Given** la première tentative échoue avec HTTP 429
**When** l'importer rétente après 1 seconde
**Then** si succès, le morceau est marqué `imported` (pas d'erreur consignée)
**And** le CSV est mis à jour immédiatement

**Given** les 3 tentatives échouent toutes avec HTTP 429
**When** les retries sont épuisés
**Then** le morceau est marqué `failed`
**And** `error_message` contient "HTTP 429 after 3 retries" ou similaire

### AC3 — Gestion des erreurs réseau isolées

**Given** une erreur réseau isolée (timeout, connexion interrompue) lors du traitement d'un morceau
**When** l'importer rencontre cette erreur
**Then** il applique le même backoff exponentiel (max 3 tentatives)
**And** sur succès après retry : marquer `imported` sans erreur
**And** sur échec après 3 retries : marquer `failed` avec message d'erreur

**Given** une erreur qui n'est PAS rate limit ni erreur réseau (ex: `already_exists`, code API invalide)
**When** l'importer la rencontre
**Then** aucune tentative supplémentaire (pas de backoff)
**And** traiter immédiatement (ex: `already_exists` assigné, pas `failed`)

### AC4 — Distinction erreur transitoire vs erreur permanente

**Given** différents codes HTTP et exceptions possibles
**When** l'importer évalue chaque erreur
**Then** classifier comme suit :
  - **Erreur transitoire (RETRY avec backoff) :** HTTP 429, 502, 503, TimeoutError, ConnectionError
  - **Erreur permanente (SKIP backoff, assigner statut spécifique) :** "already_exists", HTTP 400, 404, invalid auth
  - **Erreur réseau générique :** Traiter comme transitoire (retry 3x)

**Given** une erreur dont le type est ambigu
**When** l'importer la rencontre
**Then** approche prudente : essayer 3 retries, puis `failed` si persistant

### AC5 — Atomicité et persistance pendant les retries

**Given** un morceau en cours de retry (backoff)
**When** l'importer applique le delay
**Then** aucune modification du CSV ne survient pendant le delay (attendre, puis retry)
**And** le CSV n'est écrit que APRÈS la dernière tentative (succès ou dernier échec)

**Given** un morceau atteint succès après retry
**When** le statut est finalisé à `imported`
**Then** le CSV est écrit atomiquement une seule fois

### AC6 — Comportement en présence d'interruption (Ctrl+C) pendant retry

**Given** l'importer exécute un backoff sleep (en attente avant retry)
**When** l'utilisateur presse Ctrl+C
**Then** le signal `KeyboardInterrupt` arrête immédiatement le sleep
**And** le morceau EN COURS reste `pending` (aucune écriture CSV n'a eu lieu)
**And** le CSV précédent est préservé — relance reprend au morceau suivant

**Given** l'importer interrompu pendant retry
**When** l'utilisateur relance `importer.py`
**Then** le morceau interrompu est retraité (3 retries à nouveau)
**And** aucune perte de données

### AC7 — Rate limiting vs Performance — Pas de blocage de la progression

**Given** `api_delay` appliqué entre chaque appel
**When** la barre `tqdm` est affichée
**Then** la mise à jour progress bar n'est pas bloquée par le delay
**And** l'utilisateur voit le pourcentage s'incrémenter même pendant les delays

---

## Tasks / Subtasks

- [x] Implémenter le délai `api_delay` de config.yaml (AC: 1)
  - [x] Charger paramètre `api_delay` depuis config
  - [x] Ajouter `time.sleep(api_delay)` après chaque appel API réussi
  - [x] Tester avec `api_delay` = 0, 0.5, 1.0 secondes
  - [x] Vérifier que tqdm reste responsive

- [x] Implémenter backoff exponentiel (AC: 2 & AC4)
  - [x] Définir `MAX_RETRIES = 3` au top du script
  - [x] Implémenter boucle retry : `for attempt in range(MAX_RETRIES):`
  - [x] Appliquer `time.sleep(2 ** attempt)` entre tentatives
  - [x] Distinguer HTTP 429 des autres erreurs (retry vs no-retry)
  - [x] Détecter codes transitoires : 429, 502, 503, TimeoutError, ConnectionError
  - [x] Détecter erreurs permanentes : "already_exists", 400, 404

- [x] Implémenter gestion des erreurs réseau (AC: 3 & AC4)
  - [x] Envelopper chaque appel `ytmusic.add_to_library()` de backoff
  - [x] Capturer `Exception` générique pour erreurs réseau
  - [x] Classifier automatiquement par regex sur message d'erreur
  - [x] Retry 3 fois si transitoire, sinon assigner statut final immédiatement

- [x] Implémenter distinction erreur transitoire vs permanente (AC: 4)
  - [x] Créer fonction helper : `is_transient_error(error) -> bool`
  - [x] Mapper codes HTTP et messages d'exception
  - [x] Éviter retries inutiles sur erreurs permanentes
  - [x] Log distinct pour chaque type : `[RETRY]`, `[SKIP_RETRY]`, `[FAIL]`

- [x] Implémenter atomicité pendant retries (AC: 5)
  - [x] Écrire CSV UNIQUEMENT après dernier retry (succès ou échec final)
  - [x] Aucune modification CSV pendant le sleep
  - [x] Test : vérifier le CSV après interruption mi-retry

- [x] Implémenter interruptibilité gracieuse (AC: 6)
  - [x] Envelopper backoff sleep dans bloc `try/except KeyboardInterrupt`
  - [x] Sur interruption : abandon du morceau EN COURS, pas de write_csv
  - [x] Relance reprend au morceau suivant (grâce à idempotence Story 4.1)

- [x] Intégration complète avec Story 4.1 et 4.3 (AC: 1–7)
  - [x] Adapter importer.py : ajouter retry logic dans la boucle de Story 4.1
  - [x] Préserver atomicité and persistence (Story 4.3)
  - [x] Tqdm reste responsive malgré delays et retries

- [x] Valider et tester
  - [x] Test AC1 : Lancer avec `api_delay=1`, chronomètre, vérifier ~1s entre appels
  - [x] Test AC2 : Simuler HTTP 429 (mock ou vrai rate limit), vérifier backoff 1s, 2s, 4s
  - [x] Test AC3 : Simuler timeout réseau, vérifier retry + succès après
  - [x] Test AC4 : Vérifier "already_exists" n'est pas retraitée, erreurs 429 oui
  - [x] Test AC5 : Vérifier CSV écrit une fois, pas à chaque retry
  - [x] Test AC6 : Ctrl+C pendant sleep, relancer, vérifier reprise correcte
  - [x] Test AC7 : tqdm responsive même avec `api_delay=1`, pas congelé

---

## Dev Notes

### Contexte critique : Deuxième étape de la Phase 3 (Import)

Story 4.2 **enrichit Story 4.1 avec résilience réseau**. Elle assume que Story 4.1 est complète et fonctionnelle (import basique, détection `already_exists`, idempotence).

**Dépendances absolues :**
- ✅ Story 4.1 — Logique métier d'import et détection `already_exists`
- ✅ Story 4.3 — Persistance atomique du CSV (déjà définie dans architecture)
- ✅ Story 4.4 — Boucle `tqdm` et affichage progress (existant)
- ✅ `utils.py` — `read_csv()`, `write_csv()`, constantes STATUS_*

**Flux d'exécution :**
1. Story 4.1 charge config, valide browser.json, charge CSV
2. Story 4.1 filtre lignes `pending` + `yt_video_id`
3. **Story 4.2 ← CETTE STORY** enveloppe chaque `ytmusic.add_to_library()` avec retry + backoff
4. Story 4.3 gère persistance et reprise idempotente
5. Story 4.4 affiche progression et résumé

### Architecture décisionnelle — Résilience

#### Question 1 : Quand appliquer le délai `api_delay` ?

**Décision :** Après CHAQUE appel API réussi (pas avant, pas pendant).

**Rationale :**
- AC1 : "attend ce délai entre chaque appel API"
- Minimise les pics de trafic vers YouTube Music
- Délai s'ajoute APRÈS le traitement → progression globale ralentit mais persiste
- AC7 : tqdm ne doit pas être bloqué → implémenter sleep hors de la boucle tqdm elle-même

**Implémentation :**
```python
import time
from config import api_delay

for row in rows_to_import:
    try:
        ytmusic.add_to_library(row["yt_video_id"])
        row["status"] = STATUS_IMPORTED
    except Exception as e:
        # Story 4.2 : gérer erreur
        pass
    finally:
        write_csv(CSV_PATH, rows, FIELDNAMES)

    # AC1 : délai APRÈS écriture
    time.sleep(api_delay)
```

#### Question 2 : Comment implémenter le backoff exponentiel ?

**Décision :** Boucle retry manuelle avec `time.sleep(2 ** attempt)`, max 3 tentatives.

**Rationale :**
- AC2 : "sleep(2^attempt)" explicitement
- Pas de dépendances externes (tenacity, backoff)
- Transparent et auditable → idéal pour LLM dev
- 3 tentatives = compromis : pas trop long (9 secondes max), assez pour transient

**Implémentation :**
```python
MAX_RETRIES = 3

for row in rows_to_import:
    success = False
    for attempt in range(MAX_RETRIES):
        try:
            ytmusic.add_to_library(row["yt_video_id"])
            row["status"] = STATUS_IMPORTED
            success = True
            break  # Sortir de la boucle retry
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                # Dernier essai échoué
                row["status"] = STATUS_FAILED
                row["error_message"] = str(e)[:200]
            else:
                # Retry : appliquer backoff
                sleep_time = 2 ** attempt
                time.sleep(sleep_time)
        finally:
            # Écrire CSV UNIQUEMENT après chaque tentative finale
            if attempt == MAX_RETRIES - 1:
                write_csv(CSV_PATH, rows, FIELDNAMES)
```

#### Question 3 : Comment distinguer erreur transitoire vs permanente ?

**Décision :** Classifier par regex sur message d'erreur et code HTTP.

**Rationale :**
- AC4 : distinction explicite
- ytmusicapi non-officiel → pas de codes d'erreur standar
- Approche pragmatique : scanner message pour patterns connus
- "already_exists" = ne JAMAIS retry (AC2)
- "429", "timeout", "connection" = TOUJOURS retry

**Implémentation :**
```python
def is_transient_error(error):
    """Retourner True si l'erreur mérite un retry."""
    error_str = str(error).lower()

    # Erreurs transitoires (rate limit, réseau)
    transient_patterns = ["429", "rate", "timeout", "connection", "reset", "502", "503"]
    if any(p in error_str for p in transient_patterns):
        return True

    # Erreurs permanentes (ne pas retry)
    permanent_patterns = ["already", "exist", "404", "400", "invalid", "auth"]
    if any(p in error_str for p in permanent_patterns):
        return False

    # Ambigu : traiter comme transitoire (approche conservative)
    return True
```

#### Question 4 : Comment maintenir l'atomicité pendant les retries ?

**Décision :** Écrire CSV UNIQUEMENT après la dernière tentative (succès ou dernier échec).

**Rationale :**
- AC5 : "Aucune modification du CSV ne survient pendant le delay"
- Préserve Story 4.1 idempotence : si crash mid-retry, morceau repris complètement
- Évite "corruption" du CSV (ligne partiellement mise à jour)

**Implémentation :**
```python
for attempt in range(MAX_RETRIES):
    try:
        ytmusic.add_to_library(row["yt_video_id"])
        row["status"] = STATUS_IMPORTED
        break
    except Exception as e:
        if not is_transient_error(e):
            # Erreur permanente : ne pas retry, marquer `failed` ou `already_exists`
            if "already" in str(e).lower():
                row["status"] = STATUS_ALREADY_EXISTS
            else:
                row["status"] = STATUS_FAILED
            break

        if attempt == MAX_RETRIES - 1:
            row["status"] = STATUS_FAILED
        else:
            time.sleep(2 ** attempt)

# Écrire APRÈS que tous les retries sont épuisés
write_csv(CSV_PATH, rows, FIELDNAMES)
```

#### Question 5 : Comment gérer l'interruption (Ctrl+C) pendant les retries ?

**Décision :** Envelopper backoff sleep dans `try/except KeyboardInterrupt`.

**Rationale :**
- AC6 : "arrête immédiatement le sleep"
- Permet à l'utilisateur d'interrompre l'export overnight
- Aucune write_csv pendant KeyboardInterrupt → morceau EN COURS reste `pending`
- Relance reprend au morceau suivant (grâce à idempotence)

**Implémentation :**
```python
try:
    for row in rows_to_import:
        for attempt in range(MAX_RETRIES):
            try:
                ytmusic.add_to_library(row["yt_video_id"])
                row["status"] = STATUS_IMPORTED
                break
            except KeyboardInterrupt:
                raise  # Remonter l'exception
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    try:
                        time.sleep(2 ** attempt)
                    except KeyboardInterrupt:
                        raise  # Interruption pendant sleep
                # ... traitement erreur
        write_csv(CSV_PATH, rows, FIELDNAMES)
except KeyboardInterrupt:
    print("\n⏹  Import interrompu. Relancez pour continuer.")
    sys.exit(0)
```

### Dépendances technologiques critiques

| Composant | Rôle | Note |
|---|---|---|
| `time.sleep()` | Implémentation backoff et délai | Module Python standard |
| `ytmusicapi` exceptions | Détection erreurs API | Nécessite classification manuelle |
| `is_transient_error()` | Classification erreur | Fonction helper locale |
| `config.api_delay` | Paramètre délai | De Story 1.2 |
| `MAX_RETRIES` | Constante max retries | Défini à 3 en top du script |
| `tqdm` | Barre de progression | Non-bloquée par les sleeps |

### Configuration — Paramètres utilisés dans cette story

Story 4.2 introduit UN nouveau paramètre dans config.yaml :
- **`api_delay`** : délai en secondes entre chaque appel API (ex: 0.5, 1.0, 2.0)
  - Valeur suggérée : 0.5–1.0 pour YouTube Music (courtois, pas agressif)
  - Peut être 0 (burst, non recommandé)

Les autres paramètres viennent de Story 1.2 :
- `music_folder`
- `confidence_threshold`
- `duration_tolerance`
- `supported_extensions`
- `exclude_live`

### État de la codebase avant cette story

**Fichiers existants :**
- ✅ `importer.py` (de Story 4.1)
  - ✅ Boucle principale avec filtrage `pending` + `yt_video_id`
  - ✅ Appels `ytmusic.add_to_library()`
  - ✅ Gestion `already_exists` vs `failed`
  - ✅ Persistance CSV avec write_csv()
  - ⚠️ **SANS** retry/backoff (ajouté par Story 4.2)

- ✅ `config.yaml` (figé)
  - ⚠️ **AJOUTER** paramètre `api_delay` (optionnel avec défaut 0.5)

- ✅ `utils.py`
  - ✅ `is_transient_error()` — NOUVEAU pour cette story (peut être dans utils ou importer)

### Schéma conceptuel — Logique d'importer.py après Story 4.2

```
┌──────────────────────────────────────────────────────────┐
│ importer.py — Phase 3 : Import avec résilience           │
└──────────────────────────────────────────────────────────┘

1. Validation browser.json (Story 1.4)
2. Chargement et validation config (Story 1.2)
3. Authentification YTMusic
4. Chargement CSV
5. Filtrage : lignes pending AVEC yt_video_id
6. BOUCLE PRINCIPALE (Story 4.1) :
   │
   ├─ Pour chaque ligne filtrée :
   │  │
   │  ├─ BOUCLE RETRY (Story 4.2 — CETTE STORY) :
   │  │  │
   │  │  ├─ Tentative 1 : appel ytmusic.add_to_library()
   │  │  │  └─ Si succès : statut `imported`, break
   │  │  │  └─ Si erreur transitoire : sleep(2^0=1s), retry
   │  │  │  └─ Si erreur permanente : assigner statut final, break
   │  │  │
   │  │  ├─ Tentative 2 : sleep(2^1=2s) puis retry
   │  │  ├─ Tentative 3 : sleep(2^2=4s) puis retry
   │  │  │
   │  │  └─ Si tous les retries échouent : statut `failed`
   │  │
   │  ├─ Écrire CSV atomiquement (après tous les retries)
   │  ├─ Appliquer délai `api_delay` (AC1)
   │
   └─ Fin de boucle : tous les morceaux ont un statut

7. FINALLY :
   └─ Écrire CSV une dernière fois (sécurité)
   └─ Afficher résumé par statut (Story 4.4)
```

### Exemple concret — Morceau avec retry réussi

**Morceau : "Pink Floyd — Wish You Were Here"**
- `yt_video_id` = "xyz789" (de matcher)
- `status` = "pending"
- **Scénario :** Première tentative échoue (rate limit), deuxième réussit

**Traitement :**
```
Tentative 1 :
  - Appel ytmusic.add_to_library("xyz789")
  - Erreur : HTTP 429 Too Many Requests
  - Classification : transitoire (429) → retry

Backoff 1 : sleep(2^0 = 1 seconde)

Tentative 2 :
  - Appel ytmusic.add_to_library("xyz789")
  - Succès !
  - row["status"] = "imported"
  - break

Écrire CSV : ligne mise à jour avec status="imported"
Appliquer délai : time.sleep(0.5)  # api_delay de config
Morceau suivant
```

**Résultat CSV :**
```
filepath,artist,title,...,status,yt_video_id,yt_url,yt_score,...
/music/Pink Floyd - WYWH.mp3,Pink Floyd,Wish You Were Here,...,imported,xyz789,https://music.youtube.com/watch?v=xyz789,...
```

### Exemple concret — Morceau avec 3 retries échoués

**Morceau : "Unknown Artist — Unknown Track"**
- `yt_video_id` = "abc999"
- `status` = "pending"
- **Scénario :** Tous les retries échouent (erreur réseau persistante)

**Traitement :**
```
Tentative 1 :
  - Appel ytmusic.add_to_library("abc999")
  - Erreur : TimeoutError (connexion interrompue)
  - Classification : transitoire → retry

Backoff 1 : sleep(2^0 = 1 seconde)

Tentative 2 :
  - Appel ytmusic.add_to_library("abc999")
  - Erreur : ConnectionError
  - Classification : transitoire → retry

Backoff 2 : sleep(2^1 = 2 secondes)

Tentative 3 :
  - Appel ytmusic.add_to_library("abc999")
  - Erreur : TimeoutError
  - Classification : transitoire MAIS dernier essai
  - row["status"] = "failed"
  - row["error_message"] = "TimeoutError after 3 retries"
  - break

Écrire CSV : ligne mise à jour avec status="failed"
Appliquer délai : time.sleep(0.5)
Morceau suivant
```

**Résultat CSV :**
```
filepath,artist,title,...,status,yt_video_id,error_message,...
/music/Unknown.mp3,Unknown,Unknown,...,failed,abc999,TimeoutError after 3 retries,...
```

### Intégration avec Story 4.3 et 4.4

**Story 4.3 (Idempotence & reprise) :**
- Assume que chaque morceau aura un statut final après Story 4.2
- Reprise exacte : relit le CSV, traite uniquement `pending` sans `yt_video_id` renseigné
- Story 4.2 garantit que morceau interrompu mid-retry reste `pending` (pas écrit)

**Story 4.4 (Progression & Reporting) :**
- Affiche progression avec tqdm
- Logs de statuts non-standard : `[RETRY] Morceau X tentative 2`, `[FAIL] Morceau X`
- Résumé final avec compteurs : imported, failed, already_exists, etc.

---

## Dev Notes supplémentaires — Architecture Décisionnelle

### Interaction avec patterns d'architecture

#### Backoff exponentiel — Justification

La décision de `sleep(2 ** attempt)` (1s, 2s, 4s) vient de :
- **Architecture.md — Section "API & Communication Patterns"** : recommande backoff exponentiel manuel
- **NFR6 (PRD)** : "Une erreur réseau isolée n'interrompt pas le run — retry avec backoff, puis statut `failed` si échec persistant"
- **Équilibre :** pas trop agressif (ne pas spammer YouTube Music), pas trop long (9s total acceptable)

#### Délai `api_delay` — Pattern rate limiting

La décision d'appliquer `api_delay` APRÈS chaque appel vient de :
- **Architecture.md — Section "API & Communication Patterns"** : "Rate limiting : pause configurable"
- **NFR2 (PRD)** : "L'importer s'exécute plusieurs heures consécutives sans dégradation"
- **Courtoisie API** : évite les bans temporaires en respectant une pause entre appels

#### Classification erreur — Pragmatisme

La décision de classifier par regex plutôt que par code d'erreur numérique vient de :
- **Réalité ytmusicapi** : non-officiel → pas de codes d'erreur standar
- **Transparence :** regex visible et auditable par les développeurs
- **Robustesse** : "already" couvre multiples variations d'erreur similaire

### Cas limites avancés couverts par Story 4.2

| Cas | Condition | Action | Statut Final |
|-----|-----------|--------|--------------|
| Rate limit HTTP 429 | Première tentative échoue avec 429 | Retry avec backoff 1s, 2s, 4s | `imported` (si succès) ou `failed` (si 3x 429) |
| Timeout réseau | Tentative 1 timeout | Retry avec backoff | `imported` ou `failed` |
| Already exists | `ytmusic.add_to_library()` lève "already exists" | NE PAS RETRY, assigner `already_exists` | `already_exists` |
| Erreur API permanente | Code 400, 404, auth invalid | NE PAS RETRY, assigner `failed` | `failed` |
| Interruption mid-retry | Ctrl+C pendant sleep | Arrêter sleep, aucune write_csv | `pending` (inchangé) |
| Interruption post-écriture | Ctrl+C après write_csv du morceau précédent | Morceau courant non écrit | Relance reprend au courant |
| Délai configurable zéro | `api_delay = 0` | Pas de sleep entre appels (burst) | N/A (fonctionnel mais risqué) |

### Références architecturales

Voir [architecture.md](file:///d:/_Programs/Youtube_upload_playlists/_bmad-output/planning-artifacts/architecture.md) pour :
- **Section "API & Communication Patterns"** : Backoff exponentiel, rate limiting, isolation des erreurs
- **Section "Process Patterns"** : Pattern de backoff exact avec code (`for attempt in range(MAX_RETRIES): time.sleep(2 ** attempt)`)
- **Section "Enforcement Guidelines"** : MAX_RETRIES = 3, toujours `2 ** attempt`

Voir [epics.md](file:/_Programs/Youtube_upload_playlists/_bmad-output/planning-artifacts/epics.md) pour :
- **Story 4.2 BDD complet** : Acceptance Criteria brutes
- **Story 4.3** : Idempotence et reprise (dépend de Story 4.2)
- **Story 4.4** : Progression et résumé final

Voir [prd.md](file:/_Programs/Youtube_upload_playlists/_bmad-output/planning-artifacts/prd.md) pour :
- **NFR2** : Stabilité multi-heures
- **NFR6** : Réseau resilience avec retry + backoff
- **FR26–FR27** : Délai API + backoff rate limit

---

## Références

- [Source: epics.md — Epic 4, Story 4.2 (User Story & AC BDD)]
- [Source: prd.md — FR26–FR27 (Rate limiting & backoff)]
- [Source: prd.md — NFR2 (Stabilité multi-heures)]
- [Source: prd.md — NFR6 (Réseau resilience)]
- [Source: architecture.md — API & Communication Patterns (Backoff design)]
- [Source: architecture.md — Process Patterns (Backoff implementation code)]
- [Source: Story 4.1 — Logique métier base d'import]
- [Source: Story 4.3 — Idempotence et persistance]
- [Source: Story 4.4 — Progression et reporting]

---

## Dev Agent Record

### Agent Model Used

claude-haiku-4-5-20251001

### Implementation Notes

**Story 4.2** enveloppe la logique basique d'import de Story 4.1 avec résilience réseau : backoff exponentiel pour rate limits, délai configurable entre appels API, classification intelligente des erreurs transitoires vs permanentes.

**Implémentation complètement réalisée et testée :**

1. **Application du délai `api_delay` configurable** (AC1) ✅
   - Chargé depuis config.yaml (déjà présent avec valeur 1.0)
   - Appliqué `time.sleep(api_delay)` après chaque appel API réussi
   - Aucun sleep si `api_delay` = 0 (2 tests couvrent ce cas)
   - Testé avec delays 0, 0.3, 1.0 secondes

2. **Backoff exponentiel sur HTTP 429 et erreurs transitoires** (AC2) ✅
   - Boucle retry : `for attempt in range(MAX_RETRIES):`
   - Sleep avant retry : `time.sleep(2 ** attempt)` (1s, 2s, 4s)
   - Distinction 429 (rate limit) des autres erreurs permanentes
   - Testé avec 429 + retry successful

3. **Gestion des erreurs réseau isolées** (AC3) ✅
   - TimeoutError, ConnectionError → retry avec backoff
   - Succès après retry → marquer `imported` (pas d'erreur)
   - Échec après 3 retries → marquer `failed`
   - Testé avec TimeoutError → succès

4. **Classification erreur transitoire vs permanente** (AC4) ✅
   - Fonction `is_transient_error(error) -> bool` implémentée
   - Transient : 429, timeout, connection, 502, 503, reset
   - Permanent : already_exists, 400, 404, invalid auth
   - Erreurs ambiguës → approche conservative (retry)
   - 7 tests de classification d'erreurs all pass

5. **Atomicité et persistance pendant retries** (AC5) ✅
   - Écrire CSV UNIQUEMENT après dernier retry (dans la boucle attempt)
   - Aucune modification CSV pendant sleep (write_csv appelé après retries)
   - Crash mid-retry → morceau reste `pending`, repris intégralement
   - Testé et validé

6. **Interruptibilité gracieuse (Ctrl+C)** (AC6) ✅
   - Envelopper sleep dans `try/except KeyboardInterrupt`
   - Interruption pendant sleep → arrêt immédiat, aucune write_csv
   - Relance reprend morceau suivant (grâce à idempotence Story 4.1)
   - Testé avec KeyboardInterrupt

7. **tqdm reste responsive** (AC7) ✅
   - Barre de progression s'incrémente même pendant delays
   - Sleep hors boucle tqdm (appliqué APRÈS write_csv, pas dans la boucle tqdm)
   - Testé avec 3 morceaux et api_delay=0.1

### Files Affected

- `importer.py` (modification majeure — ajout retry/backoff à Story 4.1 + fonction is_transient_error)
- `test_importer_story42.py` (nouveau — 16 tests pour Story 4.2 AC1-AC7)
- `config.yaml` (aucune modification — `api_delay` déjà présent depuis Story 1.2)
- `utils.py` (aucune modification — pas besoin de partager is_transient_error)

### Completion Checklist

- [x] AC1 : Délai `api_delay` appliqué entre appels
- [x] AC2 : Backoff exponentiel sur HTTP 429, max 3 tentatives
- [x] AC3 : Erreurs réseau isolées gérées avec retry
- [x] AC4 : Distinction transitoire vs permanente implémentée
- [x] AC5 : CSV écrit atomiquement après retries
- [x] AC6 : Ctrl+C gracieux, aucune perte mid-retry
- [x] AC7 : tqdm responsive malgré delays
- [x] Test AC1 : Chronométrer, vérifier délai entre appels (2 tests)
- [x] Test AC2 : Simuler 429, vérifier backoff + retries (2 tests)
- [x] Test AC3 : Simuler timeout, vérifier retry + succès (2 tests)
- [x] Test AC4 : Vérifier `already_exists` pas retraitée, 429 retraitée (7 tests)
- [x] Test AC5 : Vérifier CSV écrit après retries (1 test)
- [x] Test AC6 : Ctrl+C pendant sleep, relancer, vérifier reprise (1 test)
- [x] Test AC7 : tqdm affiche progression, pas congelé (1 test)

---

## File List

### Modified Files

- `importer.py`
  - Ajout : `MAX_RETRIES = 3` constant
  - Ajout : `is_transient_error(error)` function (AC4 error classification)
  - Modification : `import_matched_tracks()` enhanced with retry/backoff logic
  - Ajout : Try/except KeyboardInterrupt for AC6 graceful interruption
  - Ajout : `time.sleep(api_delay)` after each successful track (AC1)
  - Ajout : Exponential backoff loop `for attempt in range(MAX_RETRIES)` (AC2)
  - Ajout : Logging for [RETRY] and error classification
  - Modification : Config parameter passed to function for testing

### New Files

- `test_importer_story42.py`
  - 16 comprehensive tests covering AC1-AC7
  - Tests for AC1: api_delay timing (2 tests)
  - Tests for AC2: exponential backoff (2 tests)
  - Tests for AC3: network errors with retry (2 tests)
  - Tests for AC4: error classification (7 tests)
  - Tests for AC5: atomicity (1 test)
  - Tests for AC6: keyboard interrupt (1 test)
  - Tests for AC7: performance/progress bar (1 test)

### Unchanged Files

- `config.yaml` — `api_delay` was already present (1.0 seconds, from Story 1.2)
- `utils.py` — No changes needed
- `test_importer.py` — All 9 existing Story 4.1 tests still pass

## Change Log

**2026-02-24** — Story 4.2 Implementation Complete
- Implemented exponential backoff for transient errors (AC2)
- Added configurable api_delay between API calls (AC1)
- Created error classification function is_transient_error() (AC4)
- Ensured CSV atomicity during retries (AC5)
- Added graceful Ctrl+C handling during backoff (AC6)
- Verified tqdm progress bar remains responsive (AC7)
- All network errors properly handled with retry logic (AC3)
- Created comprehensive test suite: 16 tests for AC1-AC7
- All 25 tests pass (9 Story 4.1 + 16 Story 4.2)

## Commentary & Reflections

### Pourquoi Story 4.2 est critique

Story 4.2 transforme l'importer de "fonctionne une fois sur environnement stable" à "fonctionne overnight en production". YouTube Music API est non-officiel et imprévisible — les bans temporaires (HTTP 429), timeouts réseau, et connexions interrompues sont **normaux** pour un run de 50k morceaux.

**Sans Story 4.2 :** Un morceau échoue → tout le run s'arrête.
**Avec Story 4.2 :** Des centaines de morceaux essuient des erreurs transitoires → le run continue, toutes les erreurs sont retraitées.

### Distinction cette story vs suivantes

- **Story 4.1** = Logique métier : "Ajoute-t-on ce morceau ?"
- **Story 4.2** = Résilience : "Et si l'API nous rejette ?"
- **Story 4.3** = Idempotence : "Et si on relance ?"
- **Story 4.4** = UX : "Que voit l'utilisateur ?"

Cette progression respecte le **Domain-Driven Design** : d'abord la logique métier, puis la robustesse, puis la reproductibilité, puis l'expérience utilisateur.
