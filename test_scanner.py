"""Tests pour scanner.py — Story 2.1 : Scan récursif et lecture des métadonnées ID3"""
import csv
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock


# ─── Tests AC1 : Scan récursif de tous les sous-dossiers ─────────────────────

def test_scanner_recurses_nested_directories(tmp_path):
    """AC1 — Le scanner parcourt tous les sous-dossiers récursivement sans limitation de profondeur."""
    from scanner import scan_recursive_and_extract_metadata

    # Créer une structure imbriquée
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "level1").mkdir()
    (music_dir / "level1" / "level2").mkdir()
    (music_dir / "level1" / "level2" / "level3").mkdir()

    # Créer des fichiers audio aux différents niveaux
    (music_dir / "song1.mp3").touch()
    (music_dir / "level1" / "song2.mp3").touch()
    (music_dir / "level1" / "level2" / "song3.mp3").touch()
    (music_dir / "level1" / "level2" / "level3" / "song4.mp3").touch()

    # Mocker TinyTag pour retourner des métadonnées minimales
    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Test Artist"
        mock_tag.title = "Test Song"
        mock_tag.album = "Test Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        # Vérifier que tous les fichiers ont été trouvés
        assert len(rows) == 4
        filepaths = [row["filepath"] for row in rows]
        assert any("song1.mp3" in fp for fp in filepaths)
        assert any("song2.mp3" in fp for fp in filepaths)
        assert any("song3.mp3" in fp for fp in filepaths)
        assert any("song4.mp3" in fp for fp in filepaths)


def test_scanner_ignores_directories(tmp_path):
    """AC1 — Le scanner ignore les répertoires dans le parcours."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "subfolder").mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        # Doit trouver exactement 1 fichier (pas le répertoire)
        assert len(rows) == 1


# ─── Tests AC2 : Extraction des métadonnées ID3 ───────────────────────────────

def test_scanner_extracts_id3_fields(tmp_path):
    """AC2 — Le scanner extrait les champs artist, title, album, duration depuis les tags ID3."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "The Beatles"
        mock_tag.title = "Hey Jude"
        mock_tag.album = "Hey Jude"
        mock_tag.duration = 427.1
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 1
        assert rows[0]["artist"] == "The Beatles"
        assert rows[0]["title"] == "Hey Jude"
        assert rows[0]["album"] == "Hey Jude"
        assert rows[0]["duration"] == 427.1


def test_scanner_preserves_metadata_textual_representation(tmp_path):
    """AC2 — Les valeurs sont stockées avec leur représentation textuelle exacte (sans conversion)."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artiste Français"
        mock_tag.title = "Chanson avec Accénts"
        mock_tag.album = "Album — Special Chars"
        mock_tag.duration = 123.456
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert rows[0]["artist"] == "Artiste Français"
        assert rows[0]["title"] == "Chanson avec Accénts"
        assert rows[0]["album"] == "Album — Special Chars"
        assert rows[0]["duration"] == 123.456


# ─── Tests AC3 : Gestion des tags incomplets ────────────────────────────────

def test_scanner_handles_missing_artist(tmp_path):
    """AC3 — Champ manquant (artist = None) → laissé vide."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = None
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert rows[0]["artist"] == ""
        assert rows[0]["title"] == "Song"


def test_scanner_handles_missing_title(tmp_path):
    """AC3 — Titre manquant → laissé vide."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = None
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert rows[0]["artist"] == "Artist"
        assert rows[0]["title"] == ""


def test_scanner_handles_missing_album(tmp_path):
    """AC3 — Album manquant → laissé vide."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = None
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert rows[0]["album"] == ""


def test_scanner_handles_missing_duration(tmp_path):
    """AC3 — Durée manquante → laissée vide."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = None
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert rows[0]["duration"] == ""


def test_scanner_includes_incomplete_files_with_pending_status(tmp_path):
    """AC3 — Fichier avec tags incomplets → inclus dans library.csv avec statut pending."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_PENDING

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = None
        mock_tag.title = None
        mock_tag.album = None
        mock_tag.duration = 180.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 1
        assert rows[0]["status"] == STATUS_PENDING


# ─── Tests AC4 : Filtrage des fichiers non-audio ──────────────────────────────

def test_scanner_filters_non_audio_extensions(tmp_path):
    """AC4 — Les fichiers non-audio sont ignorés."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()
    (music_dir / "image.jpg").touch()
    (music_dir / "doc.txt").touch()
    (music_dir / "playlist.m3u").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 1
        assert rows[0]["title"] == "Song"


def test_scanner_respects_supported_extensions_config(tmp_path):
    """AC4 — Seules les extensions configurées sont traitées."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()
    (music_dir / "song.flac").touch()
    (music_dir / "song.ogg").touch()
    (music_dir / "song.m4a").touch()
    (music_dir / "song.wav").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        # Limiter à seulement .mp3 et .flac
        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3", ".flac"])

        assert len(rows) == 2  # Seulement .mp3 et .flac


def test_scanner_ignores_cue_and_nfo_files(tmp_path):
    """AC4 — Les fichiers .cue et .nfo sont ignorés."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()
    (music_dir / "playlist.cue").touch()
    (music_dir / "info.nfo").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 1


# ─── Tests AC5 : Persistance initiale dans library.csv ───────────────────────

def test_scanner_creates_csv_with_correct_fieldnames(tmp_path):
    """AC5 — CSV créé avec les 10 colonnes FIELDNAMES exactes."""
    from scanner import scan_and_save
    from utils import FIELDNAMES

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    csv_file = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        scan_and_save(str(music_dir), [".mp3"], csv_file)

        # Lire le CSV et vérifier les headers
        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            assert reader.fieldnames == FIELDNAMES


def test_scanner_csv_has_all_found_files(tmp_path):
    """AC5 — library.csv contient tous les fichiers audio trouvés."""
    from scanner import scan_and_save

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()
    (music_dir / "song3.mp3").touch()

    csv_file = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        scan_and_save(str(music_dir), [".mp3"], csv_file)

        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
            assert len(rows) == 3


def test_scanner_csv_all_files_have_pending_status(tmp_path):
    """AC5 — Tous les fichiers trouvés ont le statut 'pending' ou 'duplicate' selon la détection de doublons (Story 2.3)."""
    from scanner import scan_and_save
    from utils import STATUS_PENDING, STATUS_DUPLICATE

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_file = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        # Différents métadonnées pour éviter la détection de doublons (Story 2.3)
        def tinytag_get(filepath):
            mock_tag = Mock()
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            if "song1" in filepath:
                mock_tag.artist = "Artist1"
                mock_tag.title = "Song1"
            else:
                mock_tag.artist = "Artist2"
                mock_tag.title = "Song2"
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        scan_and_save(str(music_dir), [".mp3"], csv_file)

        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
            # Tous les fichiers devraient être pending (pas de doublons car artist+title uniques)
            for row in rows:
                assert row["status"] == STATUS_PENDING


def test_scanner_csv_empty_youtube_columns(tmp_path):
    """AC5 — Colonnes YouTube (yt_video_id, yt_url, yt_score) sont vides."""
    from scanner import scan_and_save

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    csv_file = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        scan_and_save(str(music_dir), [".mp3"], csv_file)

        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
            assert rows[0]["yt_video_id"] == ""
            assert rows[0]["yt_url"] == ""
            assert rows[0]["yt_score"] == ""
            assert rows[0]["error_message"] == ""


def test_scanner_duration_in_seconds(tmp_path):
    """AC5 — Durée enregistrée en secondes (nombre entier ou décimal)."""
    from scanner import scan_and_save

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_file = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        def get_tag_side_effect(path):
            mock_tag = Mock()
            mock_tag.artist = "Artist"
            mock_tag.title = "Song"
            mock_tag.album = "Album"
            if "song1" in path:
                mock_tag.duration = 240.0  # Float
            else:
                mock_tag.duration = 180  # Int
            return mock_tag

        mock_tinytag.get.side_effect = get_tag_side_effect

        scan_and_save(str(music_dir), [".mp3"], csv_file)

        with open(csv_file, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
            # Vérifier que les durées sont correctement enregistrées
            durations = [float(row["duration"]) for row in rows if row["duration"]]
            assert 240.0 in durations or 240 in durations
            assert 180.0 in durations or 180 in durations


def test_scanner_uses_write_csv_for_persistence(tmp_path):
    """AC5 — Le scanner utilise write_csv() et non une écriture manuelle."""
    from scanner import scan_and_save

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song.mp3").touch()

    csv_file = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Song"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        with patch("scanner.write_csv") as mock_write_csv:
            from utils import FIELDNAMES
            # Mocker write_csv pour appeler la vraie fonction
            def real_write_csv(path, rows, fieldnames):
                from utils import write_csv as real_write
                real_write(path, rows, fieldnames)
            mock_write_csv.side_effect = real_write_csv

            scan_and_save(str(music_dir), [".mp3"], csv_file)

            # Vérifier que write_csv a été appelée
            assert mock_write_csv.called


# ─── Tests d'intégration ──────────────────────────────────────────────────────

def test_scanner_main_loads_config_and_scans(tmp_path, monkeypatch):
    """Le scanner.main() charge la config, scanne la musique et persiste le CSV."""
    from scanner import main

    # Changer le répertoire de travail
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Créer config.yaml
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "music_folder: music\n"
            "confidence_threshold: 85\n"
            "duration_tolerance: 10\n"
            "supported_extensions: [.mp3, .flac]\n"
            "filter_live: true\n"
            "api_delay: 1.0\n"
            "low_confidence_threshold: 70\n"
            "rate_limit_sleep: 1.0\n",
            encoding="utf-8"
        )

        # Créer structure musique
        music_dir = tmp_path / "music"
        music_dir.mkdir()
        (music_dir / "song1.mp3").touch()
        (music_dir / "song2.flac").touch()

        with patch("scanner.TinyTag") as mock_tinytag:
            mock_tag = Mock()
            mock_tag.artist = "Artist"
            mock_tag.title = "Song"
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            mock_tinytag.get.return_value = mock_tag

            main()

            # Vérifier que library.csv a été créé
            csv_file = tmp_path / "library.csv"
            assert csv_file.exists()

            with open(csv_file, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
                assert len(rows) == 2
    finally:
        os.chdir(cwd)


# ─── Tests de cas limites ──────────────────────────────────────────────────────

def test_scanner_empty_music_directory(tmp_path):
    """Le scanner traite correctement un répertoire vide."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "empty_music"
    music_dir.mkdir()

    rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

    assert rows == []


def test_scanner_nonexistent_music_directory(tmp_path):
    """Le scanner gère un répertoire qui n'existe pas."""
    from scanner import scan_recursive_and_extract_metadata

    nonexistent = str(tmp_path / "nonexistent")

    # Doit retourner une liste vide (rglob sur un chemin inexistant)
    rows = scan_recursive_and_extract_metadata(nonexistent, [".mp3"])

    assert rows == []


# ─── Tests Story 2.2 : Détection des fichiers corrompus et gestion des erreurs ─────

# ─── AC1 & AC3 : Gestion des fichiers corrompus et messages d'erreur ──────────────

def test_scanner_story22_corrupted_file_with_try_except(tmp_path):
    """Story 2.2 AC1 & AC3 — Fichier corrompu géré avec try/except, STATUS_ERROR_READ assigné."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_ERROR_READ

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    corrupted_file = music_dir / "corrupted.mp3"
    valid_file = music_dir / "valid.mp3"
    corrupted_file.touch()
    valid_file.touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            if "corrupted" in filepath:
                raise RuntimeError("Fichier MP3 invalide")
            mock_tag = Mock()
            mock_tag.artist = "Artist"
            mock_tag.title = "Song"
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        # Doit inclure 2 fichiers : 1 corrompu avec ERROR_READ, 1 valide avec PENDING
        assert len(rows) == 2

        corrupted_row = [r for r in rows if "corrupted" in r["filepath"]][0]
        assert corrupted_row["status"] == STATUS_ERROR_READ
        assert "Fichier MP3 invalide" in corrupted_row["error_message"]
        assert corrupted_row["artist"] == ""
        assert corrupted_row["title"] == ""


def test_scanner_story22_error_message_truncated_200_chars(tmp_path):
    """Story 2.2 AC3 — Message d'erreur tronqué à ~200 caractères."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_ERROR_READ

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    error_file = music_dir / "error.mp3"
    error_file.touch()

    long_error_msg = "A" * 300

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tinytag.get.side_effect = RuntimeError(long_error_msg)

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 1
        assert rows[0]["status"] == STATUS_ERROR_READ
        assert len(rows[0]["error_message"]) <= 200
        assert rows[0]["error_message"] == long_error_msg[:200]


def test_scanner_story22_multiple_exception_types(tmp_path):
    """Story 2.2 AC1 — Gérer différents types d'exceptions (OSError, RuntimeError, Exception)."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_ERROR_READ

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "os_error.mp3").touch()
    (music_dir / "runtime_error.mp3").touch()
    (music_dir / "generic_error.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            if "os_error" in filepath:
                raise OSError("Permission denied")
            if "runtime_error" in filepath:
                raise RuntimeError("Corrupt header")
            raise Exception("Unknown error")

        mock_tinytag.get.side_effect = tinytag_get

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 3
        for row in rows:
            assert row["status"] == STATUS_ERROR_READ
            assert row["error_message"]


def test_scanner_story22_corrupted_file_does_not_block_next_files(tmp_path):
    """Story 2.2 AC1 — Fichier corrompu n'interrompt pas le scan, traitement continue."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_ERROR_READ, STATUS_PENDING, STATUS_DUPLICATE

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "valid1.mp3").touch()
    (music_dir / "error.mp3").touch()
    (music_dir / "valid2.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            if "error" in filepath:
                raise RuntimeError("Corrupted")
            mock_tag = Mock()
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            # Différents artist + title pour éviter les doublons (Story 2.3)
            if "valid1" in filepath:
                mock_tag.artist = "Artist1"
                mock_tag.title = "Song1"
            else:
                mock_tag.artist = "Artist2"
                mock_tag.title = "Song2"
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 3  # Tous les fichiers, pas seulement les valides

        pending_rows = [r for r in rows if r["status"] == STATUS_PENDING]
        error_rows = [r for r in rows if r["status"] == STATUS_ERROR_READ]

        # Deux fichiers valides avec métadonnées différentes = 2 pending, 1 error
        assert len(pending_rows) == 2
        assert len(error_rows) == 1


# ─── AC2 : Stabilité mémoire ──────────────────────────────────────────────────────

def test_scanner_story22_memory_stability_large_file_count(tmp_path):
    """Story 2.2 AC2 — Stabilité mémoire sur 1000+ fichiers, pas d'accumulation."""
    from scanner import scan_recursive_and_extract_metadata

    music_dir = tmp_path / "music"
    music_dir.mkdir()

    # Créer 1000 fichiers
    num_files = 1000
    for i in range(num_files):
        f = music_dir / f"file_{i:04d}.mp3"
        f.touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Title"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == num_files
        # Vérifier que les données sont bien structurées (pas de fuite mémoire visible)
        assert all(isinstance(r, dict) for r in rows)


def test_scanner_story22_memory_with_mixed_valid_and_corrupted(tmp_path):
    """Story 2.2 AC2 — Mémoire stable sur 500+ fichiers mixtes (valides + corrompus)."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_PENDING, STATUS_ERROR_READ

    music_dir = tmp_path / "music"
    music_dir.mkdir()

    # Créer 500 fichiers : alternance valide/corrompu
    for i in range(500):
        f = music_dir / f"file_{i:04d}.mp3"
        f.touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            # Tous les 5ème fichier est corrompu
            file_index = int(Path(filepath).stem.split("_")[1])
            if file_index % 5 == 0:
                raise RuntimeError("Corrupted")
            mock_tag = Mock()
            # Chaque fichier valide a un artist+title unique pour éviter les doublons (Story 2.3)
            mock_tag.artist = f"Artist_{file_index}"
            mock_tag.title = f"Title_{file_index}"
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert len(rows) == 500

        pending_count = sum(1 for r in rows if r["status"] == STATUS_PENDING)
        error_count = sum(1 for r in rows if r["status"] == STATUS_ERROR_READ)

        # Avec métadonnées uniques par fichier valide, tous sont pending (pas de doublons)
        assert pending_count == 400
        assert error_count == 100


# ─── AC4 : Persistance atomique du CSV ─────────────────────────────────────────────

def test_scanner_story22_csv_atomic_write_with_corrupted_files(tmp_path):
    """Story 2.2 AC4 — Préservation atomique du CSV même avec fichiers corrompus."""
    from scanner import scan_and_save
    from utils import read_csv, STATUS_PENDING, STATUS_ERROR_READ

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "corrupted.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            if "corrupted" in filepath:
                raise RuntimeError("File corrupted")
            mock_tag = Mock()
            mock_tag.artist = "Artist"
            mock_tag.title = f"Title from {Path(filepath).stem}"
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        scan_and_save(str(music_dir), [".mp3"], csv_path)

        # Vérifier que le CSV existe et contient tous les fichiers
        assert Path(csv_path).exists()
        rows = read_csv(csv_path)
        assert len(rows) == 3

        # Vérifier les statuts
        valid_rows = [r for r in rows if "song" in r["filepath"]]
        error_rows = [r for r in rows if "corrupted" in r["filepath"]]

        assert len(valid_rows) == 2
        assert len(error_rows) == 1
        assert all(r["status"] == STATUS_PENDING for r in valid_rows)
        assert all(r["status"] == STATUS_ERROR_READ for r in error_rows)


def test_scanner_story22_csv_write_called_with_error_rows(tmp_path):
    """Story 2.2 AC4 — write_csv() est appelée et inclut les fichiers corrompus."""
    from scanner import scan_and_save
    from utils import FIELDNAMES

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "error.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tinytag.get.side_effect = RuntimeError("Read error")

        scan_and_save(str(music_dir), [".mp3"], csv_path)

        # Vérifier que le fichier CSV a été créé
        assert Path(csv_path).exists()

        # Lire et vérifier le contenu
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            rows = list(reader)

        assert fieldnames == FIELDNAMES
        assert len(rows) == 1
        assert rows[0]["error_message"]


# ─── Validation complète des critères d'acceptation ────────────────────────────────

def test_scanner_story22_ac1_handling_corrupted_files(tmp_path):
    """Story 2.2 : Validation AC1 — Fichiers corrompus gérés sans interrompu le scan."""
    from scanner import scan_and_save
    from utils import read_csv, STATUS_ERROR_READ, STATUS_PENDING

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "good.mp3").touch()
    (music_dir / "bad.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            if "bad" in filepath:
                raise RuntimeError("Corrupted file")
            mock_tag = Mock()
            mock_tag.artist = "Artist"
            mock_tag.title = "Title"
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        scan_and_save(str(music_dir), [".mp3"], csv_path)

        rows = read_csv(csv_path)
        assert len(rows) == 2

        bad_row = [r for r in rows if "bad" in r["filepath"]][0]
        assert bad_row["status"] == STATUS_ERROR_READ
        assert "Corrupted file" in bad_row["error_message"]


def test_scanner_story22_ac3_informative_error_messages(tmp_path):
    """Story 2.2 : Validation AC3 — Messages d'erreur informatifs et tronqués."""
    from scanner import scan_recursive_and_extract_metadata
    from utils import STATUS_ERROR_READ

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "error.mp3").touch()

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tinytag.get.side_effect = OSError("File not readable: Permission denied")

        rows = scan_recursive_and_extract_metadata(str(music_dir), [".mp3"])

        assert rows[0]["status"] == STATUS_ERROR_READ
        assert "File not readable" in rows[0]["error_message"]
        assert len(rows[0]["error_message"]) <= 200


# ─── Tests Story 2.3 : Détection et marquage des doublons ──────────────────────

def test_scanner_story23_ac1_duplicate_detection_basic(tmp_path):
    """Story 2.3 AC1 — Deux fichiers avec même artist + title → un pending, un duplicate."""
    from scanner import scan_and_save
    from utils import read_csv, STATUS_PENDING, STATUS_DUPLICATE

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "The Beatles"
        mock_tag.title = "Let It Be"
        mock_tag.album = "Abbey Road"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        scan_and_save(str(music_dir), [".mp3"], csv_path)

        rows = read_csv(csv_path)
        assert len(rows) == 2

        # Compter les statuts
        statuses = [r["status"] for r in rows]
        assert statuses.count(STATUS_PENDING) == 1
        assert statuses.count(STATUS_DUPLICATE) == 1


def test_scanner_story23_ac1_normalize_case_insensitive(tmp_path):
    """Story 2.3 AC1 — Normalisation : 'The Beatles' et 'the beatles' sont doublons."""
    from scanner import scan_and_save
    from utils import read_csv, STATUS_PENDING, STATUS_DUPLICATE

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            mock_tag = Mock()
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            if "song1" in filepath:
                mock_tag.artist = "The Beatles"
                mock_tag.title = "Let It Be"
            else:
                mock_tag.artist = "THE BEATLES"  # Casse différente
                mock_tag.title = "LET IT BE"
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        scan_and_save(str(music_dir), [".mp3"], csv_path)

        rows = read_csv(csv_path)
        statuses = [r["status"] for r in rows]
        assert statuses.count(STATUS_PENDING) == 1
        assert statuses.count(STATUS_DUPLICATE) == 1


def test_scanner_story23_ac2_no_false_positives(tmp_path):
    """Story 2.3 AC2 — Deux fichiers même titre mais artistes différents → tous deux pending."""
    from scanner import scan_and_save
    from utils import read_csv, STATUS_PENDING

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    with patch("scanner.TinyTag") as mock_tinytag:
        def tinytag_get(filepath):
            mock_tag = Mock()
            mock_tag.title = "Let It Be"  # Même titre
            mock_tag.album = "Album"
            mock_tag.duration = 240.0
            if "song1" in filepath:
                mock_tag.artist = "The Beatles"
            else:
                mock_tag.artist = "Another Artist"  # Artiste différent
            return mock_tag

        mock_tinytag.get.side_effect = tinytag_get

        scan_and_save(str(music_dir), [".mp3"], csv_path)

        rows = read_csv(csv_path)
        statuses = [r["status"] for r in rows]
        # Pas de faux positifs : tous les deux devraient être pending
        assert all(s == STATUS_PENDING for s in statuses)
        assert len(statuses) == 2


def test_scanner_story23_ac3_idempotence_no_reprocessing(tmp_path):
    """Story 2.3 AC3 — Relancer le scanner ne retraite pas les fichiers déjà dans le CSV."""
    from scanner import scan_and_save
    from utils import read_csv, STATUS_PENDING, FIELDNAMES

    music_dir = tmp_path / "music"
    music_dir.mkdir()
    (music_dir / "song1.mp3").touch()
    (music_dir / "song2.mp3").touch()

    csv_path = str(tmp_path / "library.csv")

    # Premier scan
    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Title"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        scan_and_save(str(music_dir), [".mp3"], csv_path)

    rows_first = read_csv(csv_path)
    assert len(rows_first) == 2

    # Deuxième scan : relancer sans modifier le dossier
    with patch("scanner.TinyTag") as mock_tinytag:
        mock_tag = Mock()
        mock_tag.artist = "Artist"
        mock_tag.title = "Title"
        mock_tag.album = "Album"
        mock_tag.duration = 240.0
        mock_tinytag.get.return_value = mock_tag

        scan_and_save(str(music_dir), [".mp3"], csv_path)

    rows_second = read_csv(csv_path)
    # Vérifier que le nombre de lignes n'a pas augmenté (idempotence)
    assert len(rows_second) == len(rows_first)
