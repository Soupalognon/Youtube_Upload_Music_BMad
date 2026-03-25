import time
import logging
import sys
from datetime import datetime
from tqdm import tqdm
from ytmusicapi import YTMusic
import requests.exceptions
from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_LOW_CONFIDENCE, STATUS_FAILED, STATUS_MANUAL_REVIEW,
    FIELDNAMES, clean_title, score_match, validate_browser_json
)


# ─── Story 3.4 : Configuration du logging ────────────────────────────────────
def setup_logging(log_file: str = "matcher.log") -> logging.Logger:
    """
    Configure le logging structuré.

    Implémente AC4 :
    - Format : [TIMESTAMP] [LEVEL] [Artist - Title] Message
    - Niveaux : ERROR, WARNING, DEBUG
    - Sortie : fichier + console
    """
    logger = logging.getLogger("matcher")
    logger.setLevel(logging.DEBUG)

    # Formateur
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler fichier
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Handler console (pour éviter conflits avec tqdm, utiliser stderr)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)  # Console affiche seulement WARNING+
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# ─── Story 3.4 : Retry avec backoff exponentiel ──────────────────────────────────
def search_youtube_music_with_retry(ytmusic: YTMusic, query: str, logger: logging.Logger = None) -> tuple:
    """
    Envoie une requête à YouTube Music API avec retry et backoff exponentiel.

    Implémente AC1 de Story 3.4 :
    - Max 3 tentatives
    - Backoff exponentiel : sleep(2^attempt) = 2s, 4s, 8s
    - Capture erreurs réseau et HTTP 429
    - Logging sur chaque retry

    Args:
        ytmusic: Instance YTMusic initialisée
        query: Requête de recherche
        logger: Logger pour les messages de retry

    Returns:
        Tuple (results, retries_count) où :
        - results : Liste des résultats (ou [] si échec après 3 tentatives)
        - retries_count : Nombre de retries effectués
    """
    if logger is None:
        logger = logging.getLogger("matcher")

    MAX_RETRIES = 3
    retries_count = 0

    for attempt in range(MAX_RETRIES):
        try:
            results = ytmusic.search(query, filter="songs")
            # Succès - retourner immédiatement
            return results if results else [], retries_count
        except (requests.exceptions.RequestException, requests.exceptions.Timeout, Exception) as e:
            # Erreur réseau ou API
            if attempt < MAX_RETRIES - 1:
                retries_count += 1
                sleep_time = 2 ** attempt  # 2, 4, 8 secondes
                logger.warning(f"[RETRY {attempt + 1}/{MAX_RETRIES}] Erreur réseau : {str(e)[:50]} | "
                             f"Attente {sleep_time}s avant nouvelle tentative...")
                time.sleep(sleep_time)
            else:
                # 3ème tentative échouée
                logger.error(f"[FAILED] Après 3 tentatives : {str(e)[:50]}")
                return [], retries_count

    return [], retries_count


# ─── AC3 : Détection des "Various Artists" ──────────────────────────────────────
VARIOUS_ARTIST_PATTERNS = [
    "Various Artists",
    "VA",
    "V.A.",
    "Compilation",
    "Unknown Artist",
    "Artist Unknown"
]


def detect_various_artists(artist: str) -> bool:
    """
    Détecte si un artiste est "Various Artists" ou variante.

    Retourne True si l'artiste correspond à l'un des patterns, False sinon.
    """
    if not artist:
        return False
    artist_lower = artist.lower()
    return any(pattern.lower() in artist_lower for pattern in VARIOUS_ARTIST_PATTERNS)


# ─── AC1 & AC2 : Construction de la requête YouTube Music ─────────────────────
def build_search_query(artist: str, title: str) -> str:
    """
    Construit une requête de recherche YouTube Music.

    Nettoie le titre via clean_title() et combine avec artiste.
    Retourne "artiste titre_nettoyé" (espace simple).
    """
    cleaned_title = clean_title(title)
    query = f"{artist} {cleaned_title}".strip()
    return query


# ─── AC1 : Recherche YouTube Music ────────────────────────────────────────────
def search_youtube_music(ytmusic: YTMusic, query: str) -> list:
    """
    Envoie une requête à YouTube Music API.

    Args:
        ytmusic: Instance YTMusic initialisée
        query: Requête de recherche (artist + titre nettoyé)

    Returns:
        Liste des résultats (ou [] si pas de résultats)
    """
    results = ytmusic.search(query, filter="songs")
    return results if results else []


def find_best_match_by_common_chars(results: list, local_artist: str, local_title: str) -> dict | None:
    """
    Trouve le meilleur résultat basé sur le nombre de caractères en commun
    entre la requête locale et les résultats YouTube Music.

    Compaire chaque caractère du texte local (artiste + titre) avec le texte
    de chaque résultat YouTube et retourne celui avec le maximum de
    caractères en commun.

    Args:
        results: Liste des résultats YouTube Music
        local_artist: Artiste local
        local_title: Titre local

    Returns:
        Le meilleur résultat ou None si liste vide
    """
    if not results:
        return None

    local_text = f"{local_artist} {local_title}".lower()

    best_result = None
    best_score = -1

    for result in results:
        # Extraire l'artiste YouTube
        yt_artist = ""
        if "artists" in result and isinstance(result["artists"], list) and len(result["artists"]) > 0:
            if isinstance(result["artists"][0], dict):
                yt_artist = result["artists"][0].get("name", "")
            else:
                yt_artist = str(result["artists"][0])
        else:
            yt_artist = result.get("artist", "")

        yt_title = result.get("title", "")
        yt_text = f"{yt_artist} {yt_title}".lower()

        # Compter les caractères en commun
        common_chars = sum(1 for char in local_text if char in yt_text)

        if common_chars > best_score:
            best_score = common_chars
            best_result = result

    return best_result


# ─── Story 3.2 : Helper functions for scoring, verification, and status assignment ───

def parse_duration_to_seconds(duration: str | int | float) -> int:
    """
    Convertit une durée en secondes.

    Accepte les formats:
    - Entier/Float : retourné en entier (arrondi)
    - String "MM:SS" ou "HH:MM:SS" : converti en secondes
    - String avec nombre décimal ("149.12457") : converti en entier

    Args:
        duration: String au format "MM:SS", "HH:MM:SS", nombre décimal, ou entier/float

    Returns:
        Durée en secondes (entier)
    """
    if isinstance(duration, (int, float)):
        return int(round(duration))

    if not isinstance(duration, str) or not duration.strip():
        return 0

    # Essayer de parser comme nombre décimal d'abord
    try:
        return int(round(float(duration)))
    except ValueError:
        pass

    # Sinon essayer le format MM:SS ou HH:MM:SS
    try:
        parts = duration.split(':')
        if len(parts) == 2:  # MM:SS
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        elif len(parts) == 3:  # HH:MM:SS
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
    except (ValueError, AttributeError):
        pass

    return 0


def is_live(title: str) -> bool:
    """
    Détecte si un titre contient des markers de version live.

    Patterns : "live", "[live]", "live version", "live at", "(live)"
    """
    if not title:
        return False
    title_lower = title.lower()
    live_patterns = ["live", "[live]", "live version", "live at", "(live)"]
    return any(pattern in title_lower for pattern in live_patterns)


def score_and_verify_youtube_result(local_row: dict, yt_result: dict, config: dict) -> int | None:
    """
    Vérifie et score un résultat YouTube Music par rapport à un morceau local.

    Implémente AC1-AC3 :
    1. Vérifie si le résultat est live et le filtre si nécessaire (AC3)
    2. Vérifie la durée avec tolérance (AC2)
    3. Calcule le score rapidfuzz sur artiste + titre (AC1)

    Args:
        local_row: Dictionnaire avec keys "artist", "title", "duration"
        yt_result: Dictionnaire avec keys "artist", "title", "duration"
        config: Configuration avec keys "filter_live", "duration_tolerance"

    Returns:
        Score 0-100 si valide, None si invalide
    """
    # AC3 : Filtrer les versions live si nécessaire
    if config.get("filter_live", True):
        yt_title = yt_result.get("title", "")
        if is_live(yt_title):
            return None

    # AC2 : Vérifier la durée
    yt_duration = parse_duration_to_seconds(yt_result.get("duration", 0))
    if yt_duration == 0:
        return None

    local_duration = parse_duration_to_seconds(local_row.get("duration", 0))
    if local_duration == 0:
        return None

    duration_tolerance = config.get("duration_tolerance", 5)
    duration_diff = abs(yt_duration - local_duration)
    if duration_diff > duration_tolerance:
        return None

    # AC1 : Calculer le score rapidfuzz
    local_artist = local_row.get("artist", "").strip()
    local_title = local_row.get("title", "").strip()
    yt_artist = yt_result.get("artist", "").strip()
    yt_title = yt_result.get("title", "").strip()

    score = score_match(local_artist, local_title, yt_artist, yt_title)
    return score


def assign_match_status(score: int, config: dict) -> str:
    """
    Assigne un statut basé sur le score.

    Implémente AC4 :
    - score >= confidence_threshold → STATUS_PENDING
    - low_confidence_threshold <= score < confidence_threshold → STATUS_LOW_CONFIDENCE
    - score < low_confidence_threshold → STATUS_FAILED

    Args:
        score: Score 0-100
        config: Configuration avec keys "confidence_threshold", "low_confidence_threshold"

    Returns:
        STATUS_PENDING, STATUS_LOW_CONFIDENCE, ou STATUS_FAILED
    """
    confidence_threshold = config.get("confidence_threshold", 85)
    low_confidence_threshold = config.get("low_confidence_threshold", 70)

    if score >= confidence_threshold:
        return STATUS_PENDING
    elif score >= low_confidence_threshold:
        return STATUS_LOW_CONFIDENCE
    else:
        return STATUS_FAILED


def populate_csv_result(row: dict, yt_result: dict, score: int, status: str) -> None:
    """
    Populate CSV row avec résultats du matching.

    Implémente AC5 :
    - Si status != FAILED : yt_video_id et yt_score renseignés
    - Si status == FAILED : yt_video_id et yt_score restent vides

    Args:
        row: Ligne CSV à modifier
        yt_result: Résultat YouTube Music
        score: Score calculé
        status: Statut assigné
    """
    row["status"] = status

    if status != STATUS_FAILED:
        row["yt_video_id"] = yt_result.get("videoId", "")
        row["yt_score"] = str(int(score))
    else:
        if(yt_result.get("videoId", "") != None):
            row["yt_video_id"] = yt_result.get("videoId", "")
        else:
            row["yt_video_id"] = ""
            
        if(score != None):
            row["yt_score"] = str(int(score))
        else:
            row["yt_score"] = ""


# ─── Story 3.3 : Génération d'URLs cliquables ─────────────────────────────────

def generate_youtube_music_url(video_id: str) -> str:
    """
    Génère une URL YouTube Music cliquable à partir d'un videoId.

    Implémente AC1 de Story 3.3 :
    - Format : https://music.youtube.com/watch?v={video_id}
    - Valide pour Excel/Sheets

    Args:
        video_id: ID de la vidéo YouTube Music

    Returns:
        URL cliquable ou chaîne vide si video_id est invalide
    """
    if not video_id or not isinstance(video_id, str) or not video_id.strip():
        return ""

    video_id_clean = video_id.strip()
    return f"https://music.youtube.com/watch?v={video_id_clean}"


def assign_url_to_row(row: dict) -> None:
    """
    Assigne une URL YouTube Music à une ligne CSV basée sur son statut et yt_video_id.

    Implémente AC1 et AC4 de Story 3.3 :
    - Si status in ["pending", "low_confidence"] ET yt_video_id non-vide → générer URL
    - Sinon → yt_url = "" (failed, manual_review, etc.)

    Args:
        row: Ligne CSV à modifier (doit avoir "status" et "yt_video_id")
    """
    status = row.get("status", "")
    video_id = row.get("yt_video_id", "")

    # AC4 : URL vide pour statuts finals
    if status not in [STATUS_PENDING, STATUS_LOW_CONFIDENCE]:
        row["yt_url"] = ""
        return

    # AC1 : Générer URL si video_id présent
    if video_id and video_id.strip():
        row["yt_url"] = generate_youtube_music_url(video_id)
    else:
        row["yt_url"] = ""


# ─── Story 3.1–3.4 : Intégration boucle principale avec résilience ─────────────
def process_matcher_loop(ytmusic: YTMusic, csv_path: str, config: dict = None) -> list:
    """
    Traite la boucle principale du matcher pour Stories 3.1–3.4.

    Stories 3.1–3.3 : Recherche, scoring, génération URLs
    Story 3.4 : Résilience réseau, barre de progression, logging structuré, interruptibilité

    Args:
        ytmusic: Instance YTMusic
        csv_path: Chemin vers library.csv
        config: Configuration (optionnelle, chargée automatiquement si non fournie)

    Returns:
        Liste des lignes traitées
    """
    # ─── Setup logging (AC4) ────────────────────────────────────────────────────
    logger = setup_logging("matcher.log")

    # Charger CSV
    rows = read_csv(csv_path)
    if not rows:
        return []

    # Charger config si non fournie
    if config is None:
        config = load_config()

    # ─── Filtrer les lignes à traiter (idempotence) ──────────────────────────────
    pending_unmatched = [
        (idx, row) for idx, row in enumerate(rows)
        if (row.get("status") == STATUS_PENDING and not row.get("yt_video_id")) or row.get("status") == STATUS_FAILED
    ]

    if not pending_unmatched:
        logger.info(f"Aucune ligne à traiter. Tous les morceaux sont déjà enrichis.")
        return rows

    # ─── Statistics tracking pour résumé final ─────────────────────────────────
    stats = {
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "manual_review": 0,
        "network_errors": 0,
        "retries": 0,
        "start_time": datetime.now()
    }

    # ─── Boucle principale avec tqdm (AC2) ──────────────────────────────────────
    try:
        for row_idx, (original_idx, row) in enumerate(tqdm(pending_unmatched, desc="Matching", unit="morceaux")):
            artist = row.get("artist", "").strip()
            title = row.get("title", "").strip()

            # print("artist: ", artist, " / title:", title)
            # raise ""

            # Mise à jour description pour afficher morceau courant
            current_track = f"{artist} - {title}"[:50]
            tqdm.write(f"Traitement: {current_track}")

            # AC3 : Détecter "Various Artists" → marquer manual_review directement
            if detect_various_artists(artist):
                row["status"] = STATUS_MANUAL_REVIEW
                row["yt_video_id"] = ""
                row["yt_score"] = ""
                assign_url_to_row(row)
                write_csv(csv_path, rows, FIELDNAMES)
                stats["manual_review"] += 1
                stats["total_processed"] += 1
                continue

            # AC1 & AC2 : Construire requête et envoyer recherche avec retry
            query = build_search_query(artist, title)

            # Story 3.4 : Utiliser search_youtube_music_with_retry (AC1)
            results, retries_count = search_youtube_music_with_retry(ytmusic, query, logger)

            if retries_count > 0:
                stats["retries"] += retries_count

            # Gérer les résultats vides
            if not results or len(results) == 0:
                row["status"] = STATUS_FAILED
                row["error_message"] = "Aucun résultat YouTube Music"
                assign_url_to_row(row)
                write_csv(csv_path, rows, FIELDNAMES)
                stats["failed"] += 1
                stats["total_processed"] += 1
                continue

            # Trouver le meilleur résultat en comparant les caractères en commun
            best_result = find_best_match_by_common_chars(results, artist, title)

            if best_result is None:
                best_result = results[0]

            # Adapter le résultat YouTube Music à notre format
            yt_artist = ""
            if "artists" in best_result and isinstance(best_result["artists"], list) and len(best_result["artists"]) > 0:
                if isinstance(best_result["artists"][0], dict):
                    yt_artist = best_result["artists"][0].get("name", "")
                else:
                    yt_artist = str(best_result["artists"][0])
            else:
                yt_artist = best_result.get("artist", "")

            yt_result_adapted = {
                "title": best_result.get("title", ""),
                "artist": yt_artist,
                "duration": best_result.get("duration", 0),
                "videoId": best_result.get("videoId", "")
            }

            # Story 3.2 : Scorer et vérifier
            score = score_and_verify_youtube_result(row, yt_result_adapted, config)

            if score is None:
                row["status"] = STATUS_FAILED
                row["error_message"] = "Résultat YouTube Music invalide (durée ou version live)"
                stats["failed"] += 1
            else:
                status = assign_match_status(score, config)
                populate_csv_result(row, yt_result_adapted, score, status)
                if status == STATUS_PENDING:
                    stats["successful"] += 1
                else:
                    stats["failed"] += 1

            # Story 3.3 : Générer URL cliquable
            assign_url_to_row(row)

            # Persister immédiatement (idempotence)
            write_csv(csv_path, rows, FIELDNAMES)
            stats["total_processed"] += 1

    except KeyboardInterrupt:
        # AC5 : Interruptibilité gracieuse
        logger.info("⏸  Matcher interrompu gracieusement via Ctrl+C")
        tqdm.write("\n⏸  Interruption détectée. Persistance du CSV en cours...")
    finally:
        # AC5 : Persister CSV dans tous les cas
        write_csv(csv_path, rows, FIELDNAMES)

        # ─── Afficher résumé final (AC4) ─────────────────────────────────────────
        elapsed = datetime.now() - stats["start_time"]
        tqdm.write("\n" + "=" * 60)
        tqdm.write("📊 RÉSUMÉ DE FIN DE RUN")
        tqdm.write("=" * 60)
        tqdm.write(f"⏱️  Temps total écoulé: {elapsed}")
        tqdm.write(f"📝 Morceaux traités: {stats['total_processed']}")
        tqdm.write(f"✅ Succès: {stats['successful']}")
        tqdm.write(f"❌ Échecs: {stats['failed']}")
        tqdm.write(f"👤 Révision manuelle: {stats['manual_review']}")
        tqdm.write(f"🔄 Retries effectués: {stats['retries']}")

        if stats["total_processed"] > 0:
            success_rate = (stats["successful"] / stats["total_processed"]) * 100
            tqdm.write(f"📈 Taux de réussite: {success_rate:.1f}%")
        tqdm.write("=" * 60)
        logger.info(f"Matcher terminé. {stats['successful']} succès, {stats['failed']} échecs, "
                   f"{stats['manual_review']} révisions manuelles")

    return rows


def main():
    """
    Point d'entrée du matcher.

    Story 3.1 : Recherche YouTube Music et nettoyage des titres
    """
    validate_browser_json()
    config = load_config()

    # Initialiser YTMusic une seule fois (avant la boucle)
    ytmusic = YTMusic(auth="browser.json")

    # Traiter library.csv
    # Story 3.1 : recherche YouTube Music + nettoyage titres
    process_matcher_loop(ytmusic, "library.csv")

    # TODO Story 3.2 : scoring de similarité + vérification durée
    # TODO Story 3.3 : génération URLs + persistance CSV
    # TODO Story 3.4 : résilience réseau + progression


if __name__ == "__main__":
    main()
