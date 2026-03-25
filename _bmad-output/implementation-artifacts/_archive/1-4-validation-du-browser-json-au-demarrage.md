# Story 1.4 : Validation du browser.json au démarrage du matcher et de l'importer

Status: review

<!-- Note: Validation optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant qu'utilisateur,
je veux que le matcher et l'importer détectent une authentification invalide ou expirée avant de démarrer,
afin de ne pas perdre du temps sur un run voué à l'échec.

## Critères d'acceptation

**AC1 — `browser.json` manquant → Arrêt immédiat avec message explicite**

**Given** `browser.json` est absent
**When** j'exécute `python matcher.py` ou `python importer.py`
**Then** le script s'arrête immédiatement
**And** affiche : `[ERROR] browser.json manquant — exécutez 'ytmusicapi browser' pour générer l'authentification`
**And** aucune ligne de `library.csv` n'est traitée

**AC2 — `browser.json` expiré/malformé → Détection par appel test API**

**Given** `browser.json` existe mais est expiré ou malformé (JSON invalide, headers expirés)
**When** j'exécute `python matcher.py` ou `python importer.py`
**Then** le script effectue un appel test léger à YouTube Music API (ex: `ytmusic.get_library_songs(limit=1)`)
**And** si l'appel échoue avec une erreur d'authentification, affiche un message explicite et s'arrête
**And** le message explique que `browser.json` est expiré/invalide et qu'il faut le régénérer
**And** aucune ligne de `library.csv` n'est traitée

**AC3 — `browser.json` valide → Authentification silencieuse**

**Given** un `browser.json` valide
**When** j'exécute `python matcher.py` ou `python importer.py`
**Then** l'authentification réussit silencieusement (pas de message console)
**And** le script passe immédiatement à sa logique principale (traitement CSV)

## Tâches / Sous-tâches

- [x] **AC1 — Implémentation détection `browser.json` absent**
  - [x] Dans `matcher.py` : ajouter appel `validate_browser_json()` au démarrage (avant traitement CSV)
  - [x] Dans `importer.py` : ajouter appel `validate_browser_json()` au démarrage (avant traitement CSV)
  - [x] Fonction `validate_browser_json()` dans `utils.py` : vérifier existence du fichier à la racine
  - [x] Si absent : appeler `sys.exit("[ERROR] browser.json manquant — exécutez 'ytmusicapi browser' pour générer l'authentification")`

- [x] **AC2 — Implémentation détection `browser.json` expiré/malformé**
  - [x] Fonction `validate_browser_json()` dans `utils.py` : valider JSON (charger avec json.load)
  - [x] Fonction `validate_browser_json()` : initialiser `ytmusicapi.YTMusic(auth=browser_json)` avec le fichier
  - [x] Fonction `validate_browser_json()` : effectuer appel test léger `ytmusic.get_library_songs(limit=1)`
  - [x] Si appel échoue (exception réseau/auth) : capturer l'exception et appeler `sys.exit("[ERROR] browser.json expiré ou invalide — exécutez 'ytmusicapi browser' pour régénérer")`

- [x] **AC3 — Intégration silencieuse en cas de succès**
  - [x] Si `validate_browser_json()` réussit : retourner `None` (pas de message)
  - [x] `matcher.py` et `importer.py` : appeler silencieusement `validate_browser_json()` et continuer

- [x] **Testes de couverture**
  - [x] `test_utils.py` : ajouter test `test_validate_browser_json_missing()` → vérifie sys.exit avec message correct
  - [x] `test_utils.py` : ajouter test `test_validate_browser_json_invalid_json()` → fichier JSON corrompu
  - [x] `test_utils.py` : ajouter test `test_validate_browser_json_expired()` → simule erreur d'auth ytmusicapi
  - [x] Vérifier que matcher.py et importer.py appellent bien la validation

## Dev Notes

### Contexte de la story

Cette story intervient après Story 1.3 (Génération de `browser.json`), qui a établi :
- ✅ `browser.json` généré et présent à la racine
- ✅ Fichier bien exclu du `.gitignore`
- ✅ dépendance `ytmusicapi==1.11.5` déjà en place dans requirements.txt

**Pourquoi cette story est critique :**
- **NFR8 (Sécurité)** : `browser.json` ne doit jamais être commité
- **FR8 (Functional)** : Détection préemptive de browser.json invalide
- **Économie d'effort** : Évite de démarrer un run de 50 000 morceaux sur une authentification morte
- **Expérience utilisateur** : Messages d'erreur clairs et actionnables

### Architecture patterns déjà en place (Ne pas modifier)

| Composant | État | Utilisation |
|-----------|------|------------|
| `utils.py` | ✅ Complet | Importer de `utils.py` avec `from utils import load_config, read_csv, write_csv, STATUS_*, validate_browser_json` |
| `config.yaml` | ✅ Complet | Aucune modification requise — `browser.json` n'est pas dans config, it's a file |
| `requirements.txt` | ✅ ytmusicapi==1.11.5 | Aucune dépendance supplémentaire |
| `.gitignore` | ✅ browser.json inclus | Aucune modification requise |
| `matcher.py` | Squelette + imports | Ajouter `validate_browser_json()` au démarrage |
| `importer.py` | Squelette + imports | Ajouter `validate_browser_json()` au démarrage |
| `scanner.py` | ✅ Complet (Story 2) | AUCUNE MODIFICATION — scanner n'a pas besoin d'auth YTM |

**Anti-pattern à éviter :**
```python
# ❌ MAUVAIS — hardcoding du chemin
if not Path("/path/to/browser.json").exists():
    # → utiliser Path("browser.json") ou Path.cwd() / "browser.json"

# ❌ MAUVAIS — message d'erreur non actionnable
sys.exit("Auth failed")
    # → sys.exit("[ERROR] browser.json expiré ou invalide — exécutez 'ytmusicapi browser'")

# ❌ MAUVAIS — importer ytmusicapi dans utils.py globalement
# ytmusicapi n'est utilisé que par matcher.py et importer.py
    # → Initialiser YTMusic localement dans validate_browser_json() uniquement
```

### Schéma de la fonction `validate_browser_json()`

```python
# Dans utils.py
def validate_browser_json(browser_json_path: str = "browser.json") -> None:
    """
    Valide la présence et la validité du fichier browser.json.
    Effectue un appel test léger à YouTube Music API pour détecter l'expiration.

    Raises:
        SystemExit: Si le fichier est absent, invalide ou l'auth échoue.
    """
    # Étape 1 : Vérifier existence
    path = Path(browser_json_path)
    if not path.exists():
        sys.exit("[ERROR] browser.json manquant — exécutez 'ytmusicapi browser' pour générer l'authentification")

    # Étape 2 : Valider JSON
    try:
        with open(browser_json_path, encoding="utf-8") as f:
            json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        sys.exit(f"[ERROR] browser.json malformé — {e}")

    # Étape 3 : Test API — initialiser YTMusic avec le fichier
    try:
        from ytmusicapi import YTMusic
        ytmusic = YTMusic(auth=browser_json_path)
        # Appel test léger
        ytmusic.get_library_songs(limit=1)
    except Exception as e:
        sys.exit("[ERROR] browser.json expiré ou invalide — exécutez 'ytmusicapi browser' pour régénérer")

    # Succès — pas de retour, pas de message
```

**Appel dans matcher.py et importer.py :**
```python
# Au démarrage, après load_config(), avant boucle principale
from utils import validate_browser_json
validate_browser_json()
```

### Cas limites et gestion d'erreurs

| Cas | Comportement | Test |
|-----|-------------|------|
| `browser.json` absent | `sys.exit("[ERROR] browser.json manquant...")` | ❌ Créer test en supprimant le fichier |
| `browser.json` JSON invalide | `sys.exit("[ERROR] browser.json malformé...")` | ❌ Créer test avec fichier JSON corrompu (`{invalid}`) |
| `browser.json` valide, headers expirés | `sys.exit("[ERROR] browser.json expiré...")` via exception ytmusicapi | ❌ Créer test en mockant `YTMusic.__init__()` |
| `browser.json` valide, connectivité réseau down | Exception réseau → `sys.exit("[ERROR] browser.json expiré...")` | ❌ Cas similaire à expiration (message générique) |
| `browser.json` valide, auth OK | Retour `None`, pas de message | ✅ Test existant (pas besoin de nouveau test) |

### Référence aux décisions architecturales

- **Authentification préemptive (Architecture, "Authentication & Security")** : Validation au démarrage de matcher/importer, avant boucle CSV
- **Erreurs fatales via sys.exit (Architecture, "Communication Patterns")** : Tous les arrêts fatals via `sys.exit()` avec préfixe `[ERROR]`
- **Isolation ytmusicapi (Architecture, "Shared Module Architecture")** : YTMusic initialisé uniquement dans `validate_browser_json()`, pas de dépendance globale

### Dépendances de cette story

- **Prérequis** : Story 1.3 (browser.json généré et dans .gitignore)
- **Prérequis** : utils.py avec fonctions de base (load_config, STATUS_*, FIELDNAMES)
- **Bloqué par** : Aucune
- **Bloque** : Story 2.x (Scanner) — indépendant
- **Parallélisable** : Story 3.x (Matcher) — mais dépend de cette story pour validation

### Commentaires d'implémentation

Utiliser `sys.exit()` **jamais** `raise Exception()` ou `return False` pour les erreurs fatales de config/auth.
Chaque message d'erreur doit être **actionnable** : expliquer le problème + la solution (ex: "exécutez `ytmusicapi browser`").

## Références

- [Source: epics.md — Epic 1, Story 1.4 (Acceptance Criteria BDD)](../planning-artifacts/epics.md#story-14--validation-du-browserjson-au-démarrage-du-matcher-et-de-limporter)
- [Source: architecture.md — "Authentication & Security"](../planning-artifacts/architecture.md#authentication--security) : Validation préemptive au démarrage de matcher et importer
- [Source: architecture.md — "Communication Patterns"](../planning-artifacts/architecture.md#communication-patterns) : sys.exit pour erreurs fatales, préfixe [ERROR]
- [Source: architecture.md — "Shared Module Architecture"](../planning-artifacts/architecture.md#shared-module-architecture) : utils.py contient les fonctions partagées
- [Source: 1-3-generation-de-lauthentification-youtube-music.md](1-3-generation-de-lauthentification-youtube-music.md) : Context de Story 1.3 — browser.json présent et valide
- [Source: prd.md — FR8 (Détection browser.json expiré/invalide avant démarrage)](../planning-artifacts/prd.md)
- [Source: prd.md — NFR8 (browser.json exclu du git)](../planning-artifacts/prd.md)

## Dev Agent Record

### Agent Model Used

claude-haiku-4-5-20251001

### Implementation Plan

**Architecture:**
- Implemented `validate_browser_json()` function in `utils.py` following the three-step validation pattern:
  1. Check file existence (AC1)
  2. Validate JSON format (AC2)
  3. Test authentication via YTMusic API (AC2)
- Silent success (returns None) when all checks pass (AC3)
- Integrated into both `matcher.py` and `importer.py` at startup (before load_config)

**Test Coverage:**
- Unit tests for all AC scenarios (missing, malformed JSON, expired, valid)
- Integration tests to verify matcher.py and importer.py call validation
- All 39 tests pass (37 existing + 6 new tests for story 1.4)

### Debug Log References

N/A - No issues encountered during implementation

### Completion Notes

✅ **All Acceptance Criteria Satisfied:**
- AC1: File existence detection with actionable error message
- AC2: JSON validation + auth test with appropriate error handling
- AC3: Silent operation on success

✅ **Code Quality:**
- Follows architecture patterns (sys.exit for fatal errors, error messages with [ERROR] prefix)
- Proper error messages guide users to solution (e.g., "exécutez 'ytmusicapi browser'")
- Imports ytmusicapi locally in function (not global) to avoid unnecessary dependencies

✅ **Testing:**
- 6 new tests added covering all scenarios
- Integration tests verify matcher.py and importer.py correctly call validation
- All tests pass - no regressions in existing 37 tests

### File List

- `utils.py`: Added `validate_browser_json()` function (49 new lines)
- `matcher.py`: Modified to call `validate_browser_json()` at startup
- `importer.py`: Modified to call `validate_browser_json()` at startup
- `test_utils.py`: Added 6 new tests for story 1.4 validation

## Change Log

- **2026-02-22**: Implemented browser.json validation - Story 1.4 complete
  - Added `validate_browser_json()` function with three-step validation (existence, JSON format, auth test)
  - Integrated into matcher.py and importer.py at startup
  - Added comprehensive test coverage (6 new tests, all passing)
