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
STATUS_ERROR_IMPORT   = "error_import"

ALL_STATUSES = [
    STATUS_PENDING, STATUS_IMPORTED, STATUS_LOW_CONFIDENCE,
    STATUS_FAILED, STATUS_DUPLICATE, STATUS_MANUAL_REVIEW,
    STATUS_ALREADY_EXISTS, STATUS_ERROR_READ, STATUS_ERROR_IMPORT
]

# ─── Schéma CSV — contrat figé entre les 3 phases (Source: architecture.md — "Architectural Boundaries") ──
# NE JAMAIS modifier sans mettre à jour les 3 scripts
FIELDNAMES = [
    "filepath", "artist", "title", "album", "duration",
    "status", "yt_video_id", "yt_url", "yt_score", "error_message"
]

# ─── Chargement et validation de la configuration ────────────────────────────
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

# ─── Lecture CSV ──────────────────────────────────────────────────────────────
def read_csv(filepath: str) -> list[dict]:
    """Retourne [] si le fichier n'existe pas. Décode UTF-8 BOM (Excel-compatible)."""
    if not Path(filepath).exists():
        return []
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=';'))

# ─── Écriture atomique CSV ────────────────────────────────────────────────────
def write_csv(filepath: str, rows: list[dict], fieldnames: list[str] = None) -> None:
    """Réécriture atomique via fichier temporaire + rename. NFR4 : aucune perte en cas d'arrêt brutal."""
    import time
    import os

    if fieldnames is None:
        fieldnames = FIELDNAMES
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)

    # Retry avec backoff exponentiel pour gérer les verrous fichier sur Windows
    max_retries = 3
    for attempt in range(max_retries):
        try:
            os.replace(tmp, filepath)
            return
        except (OSError, PermissionError) as e:
            if attempt < max_retries - 1:
                sleep_time = 2 ** attempt  # 1s, 2s, 4s
                time.sleep(sleep_time)
            else:
                raise

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

# ─── Normalisation de clé pour détection de doublons (Story 2.3) ──────────────
def normalize_key(artist: str, title: str) -> str:
    """
    Normalise artist + title pour détection de doublons.
    Retourne une clé insensible à la casse et aux espaces.

    Exemples:
    - ("The Beatles", "Let It Be") → "the beatles|let it be"
    - ("the BEATLES", "  Let It Be  ") → "the beatles|let it be"
    - ("", "Untitled") → "|untitled"  # artiste vide accepté
    - (None, "Song") → "|song"  # None traité comme chaîne vide
    """
    artist_norm = (artist or "").lower().strip()
    title_norm = (title or "").lower().strip()
    return f"{artist_norm}|{title_norm}"

# ─── Validation de browser.json (Story 1.4) ─────────────────────────────────
import json

def validate_browser_json(browser_json_path: str = "browser.json") -> None:
    """
    Valide la présence et la validité du fichier browser.json.
    Effectue un appel test léger à YouTube Music API pour détecter l'expiration.

    Args:
        browser_json_path: Chemin du fichier browser.json (par défaut: "browser.json" à la racine)

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
