# Story 1.2 : Configuration des paramètres via config.yaml

Status: review

<!-- Note: Validation optionnelle. Exécuter validate-create-story pour contrôle qualité avant dev-story. -->

## Story

En tant qu'utilisateur,
je veux configurer tous les paramètres de scan et d'import dans `config.yaml`,
afin de personnaliser le comportement de l'outil sans modifier le code source.

## Critères d'acceptation

**AC1 — Chargement du dossier musique**

**Given** `config.yaml` existe avec `music_folder: "/path/to/music"`
**When** `scanner.py` démarre
**Then** il charge ce chemin comme dossier racine à scanner, accessible via `config["music_folder"]`

**AC2 — Accessibilité des paramètres dans chaque module**

**Given** `config.yaml` contient `confidence_threshold`, `duration_tolerance`, `supported_extensions`, `filter_live`, `api_delay`
**When** `scanner.py`, `matcher.py` ou `importer.py` est lancé
**Then** chaque paramètre est accessible dans le module correspondant via l'objet `config` chargé par `load_config()`

**AC3 — Arrêt sur paramètre manquant**

**Given** un `config.yaml` avec un paramètre manquant
**When** `scanner.py`, `matcher.py` ou `importer.py` est lancé
**Then** le script s'arrête immédiatement via `sys.exit()` avec un message indiquant le paramètre manquant

**AC4 — Arrêt sur paramètre invalide**

**Given** un `config.yaml` avec un paramètre de type incorrect ou de valeur hors plage
**When** `scanner.py`, `matcher.py` ou `importer.py` est lancé
**Then** le script s'arrête immédiatement via `sys.exit()` avec un message indiquant le paramètre invalide et la raison

## Tâches / Sous-tâches

- [x] Ajouter la validation de type et de valeur dans `load_config()` de `utils.py` (AC4)
  - [x] `music_folder` : `str` non vide
  - [x] `confidence_threshold` : `int` entre 0 et 100 (non booléen)
  - [x] `low_confidence_threshold` : `int` entre 0 et 100 (non booléen) ET strictement < `confidence_threshold`
  - [x] `duration_tolerance` : `int` ou `float` ≥ 0
  - [x] `supported_extensions` : liste non vide
  - [x] `filter_live` : `bool` explicite
  - [x] `api_delay` : `int` ou `float` ≥ 0
  - [x] `rate_limit_sleep` : `int` ou `float` ≥ 0
- [x] Extraire `music_folder` explicitement dans `scanner.py` (AC1)
  - [x] Ajouter `music_folder = config["music_folder"]` après `config = load_config()` dans `main()`
- [x] Ajouter les tests de validation dans `test_utils.py` (AC3, AC4)
  - [x] Test : paramètre manquant → `SystemExit` avec le nom du paramètre dans le message
  - [x] Test : `confidence_threshold = 150` (hors plage) → `SystemExit`
  - [x] Test : `supported_extensions: []` (liste vide) → `SystemExit`
  - [x] Test : `filter_live: yes_please` (non-booléen) → `SystemExit`
  - [x] Test : `low_confidence_threshold >= confidence_threshold` → `SystemExit`
  - [x] Test : `music_folder: ""` (chaîne vide) → `SystemExit`
- [x] Vérifier que tous les tests passent (`py -3.11 -m pytest test_utils.py -v`)

## Notes développeur

### Ce qui est DÉJÀ EN PLACE (Story 1.1 — ne pas re-implémenter)

> ⚠️ **CRITIQUE : Story 1.1 a déjà fourni une base quasi-complète. Ne pas toucher ce qui fonctionne.**

| Composant | État | Action |
|---|---|---|
| `utils.py` — `load_config()` | Validation de **présence** des 8 clés | Ajouter validation de **type/valeur** uniquement |
| `config.yaml` | Complet avec 8 paramètres valides | Aucune modification |
| `scanner.py` | `config = load_config()` + `pass` | Ajouter extraction `music_folder` |
| `matcher.py` | `config = load_config()` + `pass` | Aucune modification (AC2 déjà satisfait) |
| `importer.py` | `config = load_config()` + `pass` | Aucune modification (AC2 déjà satisfait) |
| `test_utils.py` | 26 tests sur utils — tous passants | Ajouter tests de validation de type/valeur |

**Résumé :** Cette story ne touche que `utils.py` (validation) + `scanner.py` (extraction mineure) + `test_utils.py` (nouveaux tests).

---

### Implémentation complète de `load_config()` v2 dans `utils.py`

Remplacer la fonction `load_config()` existante par cette version avec validation de type :

```python
def load_config(path: str = "config.yaml") -> dict:
    """Charge config.yaml et valide les clés requises et leurs types. sys.exit() si manquant ou invalide."""
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # ─── Validation de présence ─────────────────────────────────────────────────
    required = [
        "music_folder", "confidence_threshold", "duration_tolerance",
        "supported_extensions", "filter_live", "api_delay",
        "low_confidence_threshold", "rate_limit_sleep"
    ]
    for key in required:
        if key not in config:
            sys.exit(f"[CONFIG ERROR] Paramètre manquant dans config.yaml : '{key}'")

    # ─── Validation de type et de valeur ────────────────────────────────────────
    v = config

    if not isinstance(v["music_folder"], str) or not v["music_folder"].strip():
        sys.exit("[CONFIG ERROR] 'music_folder' doit être une chaîne non vide")

    # isinstance(True, int) → True en Python ; exclure les bool des champs entiers
    if isinstance(v["confidence_threshold"], bool) or \
       not isinstance(v["confidence_threshold"], int) or \
       not (0 <= v["confidence_threshold"] <= 100):
        sys.exit("[CONFIG ERROR] 'confidence_threshold' doit être un entier entre 0 et 100")

    if isinstance(v["low_confidence_threshold"], bool) or \
       not isinstance(v["low_confidence_threshold"], int) or \
       not (0 <= v["low_confidence_threshold"] <= 100):
        sys.exit("[CONFIG ERROR] 'low_confidence_threshold' doit être un entier entre 0 et 100")

    if v["low_confidence_threshold"] >= v["confidence_threshold"]:
        sys.exit(
            f"[CONFIG ERROR] 'low_confidence_threshold' ({v['low_confidence_threshold']}) "
            f"doit être strictement inférieur à 'confidence_threshold' ({v['confidence_threshold']})"
        )

    if isinstance(v["duration_tolerance"], bool) or \
       not isinstance(v["duration_tolerance"], (int, float)) or \
       v["duration_tolerance"] < 0:
        sys.exit("[CONFIG ERROR] 'duration_tolerance' doit être un nombre >= 0")

    if not isinstance(v["supported_extensions"], list) or len(v["supported_extensions"]) == 0:
        sys.exit("[CONFIG ERROR] 'supported_extensions' doit être une liste non vide")

    if not isinstance(v["filter_live"], bool):
        sys.exit("[CONFIG ERROR] 'filter_live' doit être un booléen (true ou false)")

    if isinstance(v["api_delay"], bool) or \
       not isinstance(v["api_delay"], (int, float)) or \
       v["api_delay"] < 0:
        sys.exit("[CONFIG ERROR] 'api_delay' doit être un nombre >= 0")

    if isinstance(v["rate_limit_sleep"], bool) or \
       not isinstance(v["rate_limit_sleep"], (int, float)) or \
       v["rate_limit_sleep"] < 0:
        sys.exit("[CONFIG ERROR] 'rate_limit_sleep' doit être un nombre >= 0")

    return config
```

---

### Modification de `scanner.py` — extraction explicite de `music_folder`

```python
def main():
    config = load_config()
    music_folder = config["music_folder"]  # AC1 — Story 1.2 : dossier racine du scan
    # TODO Story 2.1 : scan récursif et lecture ID3 (utiliser music_folder)
    # TODO Story 2.2 : gestion des fichiers corrompus
    # TODO Story 2.3 : détection des doublons
    # TODO Story 2.4 : export CSV et idempotence
    pass
```

---

### Tests à ajouter dans `test_utils.py`

Ajouter après les tests existants. Utiliser `pytest.raises(SystemExit)` car `sys.exit()` lève `SystemExit` :

```python
# ─── Tests Story 1.2 : Validation de type/valeur dans load_config() ──────────

def _write_valid_config(tmp_path: Path, overrides: dict = None) -> str:
    """Helper : config valide de base, avec overrides optionnels."""
    cfg = {
        "music_folder": "/test/music",
        "confidence_threshold": 85,
        "low_confidence_threshold": 70,
        "duration_tolerance": 10,
        "supported_extensions": [".mp3", ".flac"],
        "filter_live": True,
        "api_delay": 1.0,
        "rate_limit_sleep": 1.0,
    }
    if overrides:
        cfg.update(overrides)
    path = tmp_path / "config.yaml"
    import yaml
    path.write_text(yaml.dump(cfg), encoding="utf-8")
    return str(path)


def test_load_config_missing_key(tmp_path):
    """AC3 — Paramètre manquant → SystemExit avec nom du paramètre."""
    path = tmp_path / "config.yaml"
    path.write_text("music_folder: /test\nconfidence_threshold: 85\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_config(str(path))
    assert "duration_tolerance" in str(exc.value)


def test_load_config_confidence_threshold_out_of_range(tmp_path):
    """AC4 — confidence_threshold hors plage (150) → SystemExit."""
    path = _write_valid_config(tmp_path, {"confidence_threshold": 150})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "confidence_threshold" in str(exc.value)


def test_load_config_empty_extensions(tmp_path):
    """AC4 — supported_extensions liste vide → SystemExit."""
    path = _write_valid_config(tmp_path, {"supported_extensions": []})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "supported_extensions" in str(exc.value)


def test_load_config_filter_live_not_bool(tmp_path):
    """AC4 — filter_live non-booléen (chaîne) → SystemExit."""
    # Note : yaml.dump encode True en 'true' — passer un int pour simuler une valeur invalide
    path = _write_valid_config(tmp_path, {"filter_live": 1})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "filter_live" in str(exc.value)


def test_load_config_low_confidence_greater_than_confidence(tmp_path):
    """AC4 — low_confidence_threshold >= confidence_threshold → SystemExit."""
    path = _write_valid_config(tmp_path, {
        "confidence_threshold": 70,
        "low_confidence_threshold": 85
    })
    with pytest.raises(SystemExit):
        load_config(path)


def test_load_config_empty_music_folder(tmp_path):
    """AC4 — music_folder chaîne vide → SystemExit."""
    path = _write_valid_config(tmp_path, {"music_folder": ""})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "music_folder" in str(exc.value)


def test_load_config_valid_config_passes(tmp_path):
    """Vérification positive — config valide complète → aucune erreur."""
    path = _write_valid_config(tmp_path)
    config = load_config(path)
    assert config["confidence_threshold"] == 85
    assert config["low_confidence_threshold"] == 70
    assert config["filter_live"] is True
    assert len(config["supported_extensions"]) == 2
```

---

### Points de vigilance architecturale

**🔴 Piège Python : `bool` est une sous-classe de `int`**

```python
isinstance(True, int)   # → True  ← PIÈGE !
isinstance(False, int)  # → True  ← PIÈGE !
isinstance(True, bool)  # → True  ← correct
```

Pour `confidence_threshold`, `low_confidence_threshold`, `duration_tolerance`, `api_delay`, `rate_limit_sleep` :
**Toujours vérifier `isinstance(v, bool)` EN PREMIER** pour exclure les booléens avant de vérifier `isinstance(v, int)` ou `isinstance(v, (int, float))`.

```python
# ✅ Correct
if isinstance(v, bool) or not isinstance(v, int):
    sys.exit(...)

# ❌ Incorrect — accepterait True (== 1) comme valeur de seuil valide
if not isinstance(v, int):
    sys.exit(...)
```

**🔴 Piège YAML — formes équivalentes de booléens**

`yaml.safe_load` reconnaît `true`, `false`, `yes`, `no`, `on`, `off` comme booléens. Tous sont convertis en `bool` Python → `isinstance(v, bool)` fonctionne correctement pour tous.

**🟡 Anti-patterns à éviter**

```python
# ❌ raise au lieu de sys.exit()
raise ValueError("invalid")             # → sys.exit("[CONFIG ERROR] ...")

# ❌ print seul sans arrêt
print("config invalide")               # → sys.exit("[CONFIG ERROR] ...")

# ❌ yaml.load() sans safe
yaml.load(f)                           # → yaml.safe_load(f)

# ❌ Vérification de présence uniquement (Story 1.1 — cette story complète la validation)
if key not in config: sys.exit(...)    # ✅ déjà là — ajouter la validation de type/valeur après
```

---

### Notes de structure du projet

- **Structure inchangée** — aucun nouveau fichier créé dans cette story
- `utils.py` : modification de `load_config()` uniquement (ajout de 30 lignes environ)
- `scanner.py` : ajout d'une seule ligne (`music_folder = config["music_folder"]`)
- `test_utils.py` : ajout de ~60 lignes de tests (7 nouveaux tests)
- Aucune dépendance externe ajoutée — tout est en Python standard

### Références

- [Source: epics.md — Epic 1, Story 1.2 (Acceptance Criteria BDD)]
- [Source: architecture.md — "Shared Module Architecture" (`load_config()` pattern, `sys.exit()` obligatoire)]
- [Source: architecture.md — "Enforcement Guidelines" (anti-patterns — `raise`, `print` seul, `yaml.load()`)]
- [Source: architecture.md — "Format Patterns" — "Chargement de config — Pattern obligatoire"]
- [Source: architecture.md — "Core Architectural Decisions" — Data Architecture (`yaml.safe_load`)]
- [Source: 1-1-initialisation-de-la-structure-du-projet.md — Notes de complétion (utils.py complet, squelettes en place, 26 tests passants)]

## Enregistrement de l'agent dev

### Modèle d'agent utilisé

claude-sonnet-4-6

### Références de log de débogage

_(aucun blocage — implémentation directe conforme aux specs de la story)_

### Notes de complétion

- ✅ `load_config()` dans `utils.py` étendue avec validation complète de type et de valeur pour les 8 paramètres requis (AC4)
- ✅ `scanner.py` mis à jour avec extraction explicite `music_folder = config["music_folder"]` (AC1)
- ✅ 7 nouveaux tests ajoutés dans `test_utils.py` — tous passants (AC3, AC4)
- ✅ 33/33 tests passent sans aucune régression
- ✅ Cycle red-green-refactor respecté : tests ajoutés avant l'implémentation, 5 échecs confirmés en phase RED, puis tous verts en phase GREEN
- ✅ Piège Python `isinstance(True, int) == True` correctement géré avec vérification `bool` préalable

### Liste des fichiers

- `utils.py` (modifié — `load_config()` avec validation de type/valeur)
- `scanner.py` (modifié — extraction `music_folder`)
- `test_utils.py` (modifié — 7 nouveaux tests de validation)

## Journal des modifications

- 2026-02-22 : Story 1.2 — Ajout validation type/valeur dans `load_config()`, extraction `music_folder` dans `scanner.py`, 7 nouveaux tests (33 tests au total, 0 régression)
