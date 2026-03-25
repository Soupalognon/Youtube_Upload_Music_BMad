from pathlib import Path
from tinytag import TinyTag

from utils import (
    load_config, read_csv, write_csv,
    STATUS_PENDING, STATUS_DUPLICATE, STATUS_ERROR_READ, FIELDNAMES,
    normalize_key
)


def scan_recursive_and_extract_metadata(
    music_folder: str,
    supported_extensions: list[str],
    existing_csv_path: str = None
) -> list[dict]:
    """
    Scanne récursivement un dossier musique et extrait les métadonnées ID3 de chaque fichier audio.

    Implémente Story 2.3 (détection de doublons) et idempotence :
    - Charge le CSV existant s'il existe
    - Saute les fichiers déjà dans le CSV
    - Détecte les doublons (même artist + title normalisé)
    - Marque le premier comme STATUS_PENDING, les suivants comme STATUS_DUPLICATE

    Args:
        music_folder: Chemin vers le dossier musique
        supported_extensions: Liste des extensions supportées (ex: ['.mp3', '.flac'])
        existing_csv_path: Chemin du CSV existant pour idempotence (optionnel)

    Returns:
        Liste de dictionnaires contenant les métadonnées extraites et statut (pending/duplicate/error_read)
    """
    rows = []
    music_path = Path(music_folder)

    # Si le dossier n'existe pas, retourner une liste vide
    if not music_path.exists():
        return rows

    # Phase 1 : Charger le CSV existant pour idempotence (Story 2.3 AC3)
    existing_paths = set()
    existing_keys = set()
    if existing_csv_path:
        existing_rows = read_csv(existing_csv_path)
        existing_paths = {r["filepath"] for r in existing_rows if r.get("filepath")}
        for row in existing_rows:
            if row.get("status") not in [STATUS_ERROR_READ]:  # On considère les clés existantes sauf erreurs
                key = normalize_key(row.get("artist", ""), row.get("title", ""))
                existing_keys.add(key)

    # Phase 2 : Scanner les fichiers (Story 2.3)
    seen_keys = {}  # {normalized_key: filepath} pour tracker les doublons dans ce scan

    # itr = 0
    for audio_file in music_path.rglob("*"):
        # if(itr > 10):
        #     break
        # itr += 1

        # Ignorer les répertoires
        if audio_file.is_dir():
            continue

        # Filtrer par extensions autorisées (case-insensitive)
        if audio_file.suffix.lower() not in supported_extensions:
            continue

        filepath = str(audio_file)

        # Story 2.3 AC3 : Idempotence — sauter les fichiers déjà dans le CSV
        if filepath in existing_paths:
            continue

        # Lire les métadonnées ID3 avec TinyTag (Story 2.2: gestion des erreurs)
        try:
            tag = TinyTag.get(filepath)
            status = STATUS_PENDING
            error_msg = ""
        except Exception as e:
            # Story 2.2: Fichiers corrompus sont inclus avec STATUS_ERROR_READ
            tag = None
            status = STATUS_ERROR_READ
            error_msg = str(e)[:200]

        # Extraire artist et title pour détection de doublons
        artist = tag.artist or "" if tag else ""
        title = tag.title or "" if tag else ""

        # Story 2.3 AC1 : Détection des doublons avec normalisation (case-insensitive, trim)
        if status != STATUS_ERROR_READ:  # Ne pas appliquer la logique doublons aux fichiers corrompus
            normalized_key = normalize_key(artist, title)

            # Vérifier si doublon (dans CSV existant OU dans le scan courant)
            if normalized_key in existing_keys or normalized_key in seen_keys:
                status = STATUS_DUPLICATE
            else:
                status = STATUS_PENDING
                seen_keys[normalized_key] = filepath

        # Créer une ligne CSV
        row = {
            "filepath": filepath,
            "artist": artist,
            "title": title,
            "album": tag.album or "" if tag else "",
            "duration": tag.duration or "" if tag else "",
            "status": status,
            "yt_video_id": "",
            "yt_url": "",
            "yt_score": "",
            "error_message": error_msg
        }
        rows.append(row)

        print(row)

    return rows


def scan_and_save(music_folder: str, supported_extensions: list[str], csv_path: str = "library.csv", log_errors: bool = True) -> None:
    """
    Scanne le dossier musique et sauvegarde les résultats dans un CSV avec idempotence.

    Implémente Story 2.3 (détection de doublons et idempotence) :
    - Charge le CSV existant s'il existe
    - Scanne les nouveaux fichiers
    - Fusionne les résultats
    - Sauvegarde le CSV complet

    Args:
        music_folder: Chemin vers le dossier musique
        supported_extensions: Liste des extensions supportées
        csv_path: Chemin du fichier CSV de sortie (par défaut: library.csv)
        log_errors: Si True, affiche un message court pour chaque erreur rencontrée (Story 2.2 AC3)
    """
    # Story 2.3 AC3 : Charger le CSV existant
    existing_rows = read_csv(csv_path)

    # Scanne les nouveaux fichiers (passant le csv_path pour idempotence)
    new_rows = scan_recursive_and_extract_metadata(music_folder, supported_extensions, csv_path)

    # Story 2.3 AC3 : Fusionner les résultats (existants + nouveaux)
    all_rows = existing_rows + new_rows

    # Story 2.2 AC3: Logs informatifs des erreurs
    if log_errors:
        for row in new_rows:
            if row["status"] == STATUS_ERROR_READ:
                print(f"⚠️  Erreur lecture : {row['filepath']} — {row['error_message']}")

    write_csv(csv_path, all_rows, FIELDNAMES)


def main():
    config = load_config()
    music_folder = config["music_folder"]
    supported_extensions = config["supported_extensions"]

    # Valider que le dossier existe
    if not Path(music_folder).exists():
        print(f"[ERROR] Dossier musique introuvable : {music_folder}")
        return

    # Scan récursif et extraction ID3
    scan_and_save(music_folder, supported_extensions, "library.csv")

    # Message de confirmation
    rows = scan_recursive_and_extract_metadata(music_folder, supported_extensions)
    print(f"[OK] Scan terminé : {len(rows)} fichiers trouvés, sauvés dans library.csv")


if __name__ == "__main__":
    main()
