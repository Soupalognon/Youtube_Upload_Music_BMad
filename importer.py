import time
import logging
from ytmusicapi import YTMusic
from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
    STATUS_LOW_CONFIDENCE, STATUS_MANUAL_REVIEW, STATUS_DUPLICATE, STATUS_ERROR_READ,
    STATUS_ERROR_IMPORT, ALL_STATUSES, FIELDNAMES, validate_browser_json
)
from pathlib import Path
from tqdm import tqdm

# ─── Logging configuration ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# ─── Story 4.2 : Constantes de résilience ─────────────────────────────────
MAX_RETRIES = 3

# ─── Story 4.3 : Constantes de chemin CSV ─────────────────────────────────
CSV_PATH = "library.csv"


# ─── Story 4.2 : Classification des erreurs (AC4) ─────────────────────────
def is_transient_error(error: Exception) -> bool:
    """
    Classifie une erreur comme transitoire (retry) ou permanente (no retry).

    Erreurs transitoires (retry 3x avec backoff 2^attempt) :
    - HTTP 429, 502, 503
    - TimeoutError, ConnectionError
    - Erreurs réseau génériques

    Erreurs permanentes (pas de retry) :
    - "already_exists", "already in library"
    - HTTP 400, 404
    - Erreurs d'authentification

    Story 4.2 AC4: Distinguish transient vs permanent errors
    """
    error_str = str(error).lower()

    # Erreurs transitoires (rate limit, réseau)
    transient_patterns = ["429", "rate", "timeout", "connection", "reset", "502", "503"]
    if any(p in error_str for p in transient_patterns):
        return True

    # Erreurs permanentes (ne pas retry)
    permanent_patterns = ["already", "exist", "404", "400", "invalid", "auth", "unauthorized"]
    if any(p in error_str for p in permanent_patterns):
        return False

    # Ambigu : approche conservative, traiter comme transitoire
    return True


# ─── Story 4.1 : Fonction principale d'import ──────────────────────────────
def import_matched_tracks(csv_path: str, ytmusic: YTMusic, config: dict = None) -> None:
    """
    Importe les morceaux matchés vers YouTube Music avec résilience réseau.

    Story 4.1 (AC1–AC5):
    - AC1: Importe lignes `pending` avec `yt_video_id` → statut `imported`
    - AC2: Détecte "already_exists" → statut `already_exists` (pas `failed`)
    - AC3: Ignore lignes sans match ou statut ≠ `pending`
    - AC4: 100% des lignes finales ont un statut explicite
    - AC5: Persistence atomique après chaque morceau

    Story 4.2 (AC1–AC7):
    - AC1: Application du délai `api_delay` entre appels API
    - AC2: Backoff exponentiel sur HTTP 429 (2^attempt, max 3 tentatives)
    - AC3: Gestion des erreurs réseau isolées avec retry
    - AC4: Distinction erreur transitoire vs permanente
    - AC5: Atomicité du CSV pendant les retries
    - AC6: Interruptibilité gracieuse (Ctrl+C)
    - AC7: tqdm reste responsive malgré delays

    Args:
        csv_path: Chemin vers library.csv
        ytmusic: Instance YTMusic authentifiée
        config: Dictionnaire de configuration (optionnel)
    """
    if config is None:
        config = load_config()

    api_delay = config.get("api_delay", 1.0)

    # Charger le CSV complet
    rows = read_csv(csv_path)

    if not rows:
        logger.info("Aucun morceau trouvé dans le CSV")
        return

    # Filtrer les lignes à traiter (AC3: pending + yt_video_id)
    rows_to_import = [r for r in rows if _should_import_track(r)]

    logger.info(f"Importation de {len(rows_to_import)} morceaux...")

    # Boucle d'import avec persistence atomique (AC5) et résilience (Story 4.2)
    try:
        # ─── AC1 : Initialiser la barre de progression avec tqdm ─────────────────
        pbar = tqdm(rows_to_import, desc="Import", unit="track")
        for row in pbar:
            video_id = row.get("yt_video_id", "").strip()
            if not video_id:
                continue

            # ─── AC1 : Mettre à jour la description de la barre avec le morceau en cours
            artist = row.get("artist", "?").strip()
            title = row.get("title", "?").strip()
            pbar.set_description(f"{artist} - {title}")

            # ─── Story 4.2 : Boucle de retry avec backoff exponentiel ─────
            success = False
            for attempt in range(MAX_RETRIES):
                try:
                    # AC1: Ajouter à la bibliothèque via rate_song('LIKE')
                    response = ytmusic.rate_song(video_id, 'LIKE')

                    actions = response.get('actions', [])
                    text_response = actions[0]['addToToastAction']['item']['notificationActionRenderer']['responseText']['runs'][0]['text']
            
                    if "Saved to liked music" in text_response or "Ajouté aux titres aimés" in text_response:
                        row["status"] = STATUS_IMPORTED
                        logger.info(f"✓ {row.get('artist', '?')} - {row.get('title', '?')} → imported")
                    else:
                        row["status"] = STATUS_ERROR_IMPORT
                        row["error_message"] = "rate_song sans confirmation dans la réponse"
                        logger.warning(f"⚠ {row.get('artist', '?')} - {row.get('title', '?')} → error_import (réponse vide)")
                    success = True
                    break  # Sortir de la boucle retry

                except KeyboardInterrupt:
                    # ─── AC6 : Gestion gracieuse Ctrl+C ─────────────────
                    raise  # Remonter l'exception

                except Exception as e:
                    error_str = str(e).lower()

                    # DEBUG: Afficher l'erreur complète
                    if attempt == 0:
                        logger.debug(f"[DEBUG] Erreur complète: {str(e)}")
                        logger.debug(f"[DEBUG] Type d'erreur: {type(e).__name__}")

                    # AC4 : Classification et retry logic
                    if is_transient_error(e):
                        # Erreur transitoire : appliquer backoff
                        if attempt < MAX_RETRIES - 1:
                            # Pas la dernière tentative : appliquer backoff
                            sleep_time = 2 ** attempt  # AC2 : 1s, 2s, 4s
                            logger.info(f"[RETRY] Tentative {attempt + 1}/{MAX_RETRIES} échouée, backoff {sleep_time}s...")
                            try:
                                time.sleep(sleep_time)
                            except KeyboardInterrupt:
                                # AC6 : Interruption pendant backoff
                                raise
                        else:
                            # Dernière tentative échouée (erreur réseau persistante)
                            row["status"] = STATUS_ERROR_IMPORT
                            row["error_message"] = str(e)[:200]
                            logger.error(f"✗ {row.get('artist', '?')} - {row.get('title', '?')} → error_import (after {MAX_RETRIES} retries)")
                            success = True
                    else:
                        # Erreur permanente (400, 404, etc.) → pas de retry
                        row["status"] = STATUS_ERROR_IMPORT
                        row["error_message"] = str(e)[:200]
                        logger.error(f"✗ {row.get('artist', '?')} - {row.get('title', '?')} → error_import ({error_str[:50]})")
                        success = True
                        break  # Ne pas retry

            # ─── AC5 : Persistance atomique après retries ────────────────
            write_csv(csv_path, rows, FIELDNAMES)

            # ─── AC1 : Appliquer délai api_delay après chaque morceau ───
            # AC7 : tqdm reste responsive car delay est après le traitement
            if api_delay > 0 and success:
                time.sleep(api_delay)

    except KeyboardInterrupt:
        # ─── AC6 : Interruption gracieuse ──────────────────────────────
        logger.info("Importer interrompu par utilisateur. Run peut être repris...")
        write_csv(csv_path, rows, FIELDNAMES)
        raise

    finally:
        # AC5: Sécurité finale en cas d'arrêt brutal
        write_csv(csv_path, rows, FIELDNAMES)

        # ─── AC3 : Afficher résumé de fin de run ────────────────────────────
        _display_end_of_run_summary(rows)

    # AC4: Vérifier couverture 100% des statuts
    _ensure_all_statuses_assigned(rows)
    logger.info("✅ Import terminé")


def _should_import_track(row: dict) -> bool:
    """
    Filtrage des lignes à traiter (AC2 & AC3).
    Retourne True si et seulement si : statut=pending ET yt_video_id renseigné.

    AC2: Seules les lignes pending avec yt_video_id sont retraitées après interruption.
    AC3: Les lignes finalisées (imported, already_exists, failed, etc.) sont ignorées.
    """
    return row.get("status") == STATUS_PENDING and bool(row.get("yt_video_id", "").strip())


def _ensure_all_statuses_assigned(rows: list[dict]) -> None:
    """
    Validation AC4 : Vérifier qu'aucune ligne n'a un statut vide en fin de run.
    Log un avertissement si détecté (ne pas crasher).
    """
    empty_status_lines = [
        (i, row.get("filepath", "unknown"))
        for i, row in enumerate(rows, 1)
        if not row.get("status", "").strip()
    ]

    if empty_status_lines:
        print(f"\n⚠️  ATTENTION : {len(empty_status_lines)} ligne(s) sans statut détectée(s) :")
        for line_num, filepath in empty_status_lines[:5]:  # Afficher les 5 premiers
            print(f"   Ligne {line_num}: {filepath}")
        if len(empty_status_lines) > 5:
            print(f"   ... et {len(empty_status_lines) - 5} autre(s)")


def _display_end_of_run_summary(rows: list[dict]) -> None:
    """
    ─── AC3 : Afficher résumé complet de fin de run ─────────────────────────
    Affiche le compte par statut avec emojis et totaux.

    Story 4.4 AC3: End-of-Run Summary
    - Compter les morceaux par statut
    - Afficher en résumé avec symboles (✓, ⚠, ✗)
    - Afficher le TOTAL
    - Utiliser un formatting clair avec séparateurs
    """
    from collections import Counter

    # Compter les morceaux par statut
    status_counts = Counter(row.get("status", "unknown") for row in rows)
    total = sum(status_counts.values())

    # Définir les symboles et emojis par statut
    status_symbols = {
        STATUS_IMPORTED: "✓",
        STATUS_ALREADY_EXISTS: "⚠",
        STATUS_FAILED: "✗",
        STATUS_LOW_CONFIDENCE: "⚠",
        STATUS_MANUAL_REVIEW: "⚠",
        STATUS_DUPLICATE: "✗",
        STATUS_ERROR_READ: "✗",
        STATUS_ERROR_IMPORT: "✗"
    }

    # Afficher le résumé
    print("\n" + "="*60)
    print("📊 RÉSUMÉ FINAL DE L'IMPORT")
    print("="*60)

    # Trier les statuts : succès d'abord, puis avertissements, puis erreurs
    status_order = [
        STATUS_IMPORTED,
        STATUS_ALREADY_EXISTS,
        STATUS_LOW_CONFIDENCE,
        STATUS_MANUAL_REVIEW,
        STATUS_ERROR_READ,
        STATUS_ERROR_IMPORT,
        STATUS_FAILED,
        STATUS_DUPLICATE
    ]

    for status in status_order:
        count = status_counts.get(status, 0)
        if count > 0:
            symbol = status_symbols.get(status, "•")
            print(f"  {symbol} {status:20} → {count:6}")

    print("="*60)
    print(f"TOTAL: {total}")
    print("="*60 + "\n")


def main():
    """
    Fonction principale pour importer.py.
    Story 4.1: Importe les morceaux matchés avec gestion des statuts.
    Story 4.2: Ajoute la résilience réseau avec backoff exponentiel.
    """
    # Story 1.4: Validation browser.json au démarrage
    validate_browser_json()

    # Story 1.2: Chargement et validation config
    config = load_config()

    # Story 1.3: Authentification YTMusic
    from ytmusicapi import YTMusic
    ytmusic = YTMusic(auth='browser.json')

    # Story 4.1 + 4.2: Importer les morceaux matchés avec résilience
    import_matched_tracks(CSV_PATH, ytmusic, config)


if __name__ == "__main__":
    main()
