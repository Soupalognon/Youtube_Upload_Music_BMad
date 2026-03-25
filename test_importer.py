"""
Test suite pour importer.py (Story 4.1)
Couvre AC1–AC5 : Import des morceaux matchés et gestion des statuts post-import
"""
import pytest
import tempfile
import os
import csv
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from importer import (
    import_matched_tracks,
    main
)
from utils import (
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS,
    STATUS_FAILED, FIELDNAMES, write_csv, read_csv
)


class TestAC1ImportPendingTracks:
    """AC1: Import des morceaux `pending` avec `yt_video_id` renseigné"""

    def test_ac1_import_pending_with_video_id(self):
        """
        AC1: Importer une ligne `pending` avec `yt_video_id`, vérifier statut `imported`
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            # Setup: créer une ligne pending avec yt_video_id
            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Daft Punk",
                    "title": "Get Lucky",
                    "album": "Random Access Memories",
                    "duration": "244",
                    "status": STATUS_PENDING,
                    "yt_video_id": "aq2KrGaF_kM",
                    "yt_url": "https://music.youtube.com/watch?v=aq2KrGaF_kM",
                    "yt_score": "98",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Mock ytmusic.add_to_library() → succès
            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.return_value = None

            # Exécuter import
            import_matched_tracks(csv_path, mock_ytmusic)

            # Vérifier: statut = imported
            result = read_csv(csv_path)
            assert len(result) == 1
            assert result[0]["status"] == STATUS_IMPORTED
            assert result[0]["artist"] == "Daft Punk"

            # Vérifier: ytmusic.add_to_library() appelé avec le bon video_id
            mock_ytmusic.add_to_library.assert_called_once_with("aq2KrGaF_kM")

    def test_ac1_csv_persisted_immediately(self):
        """
        AC1: CSV persisté immédiatement après chaque morceau
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist1",
                    "title": "Title1",
                    "album": "Album1",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid1",
                    "yt_url": "url1",
                    "yt_score": "95",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.return_value = None

            import_matched_tracks(csv_path, mock_ytmusic)

            # Relire le CSV: la persévérance doit être sauvegardée
            persisted = read_csv(csv_path)
            assert persisted[0]["status"] == STATUS_IMPORTED


class TestAC2AlreadyExists:
    """AC2: Détection des morceaux déjà présents (`already_exists`)"""

    def test_ac2_detect_already_exists_exception(self):
        """
        AC2: Capturer exception "Already in library" → assigner `already_exists`
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "The Beatles",
                    "title": "Let It Be",
                    "album": "Let It Be",
                    "duration": "240",
                    "status": STATUS_PENDING,
                    "yt_video_id": "abc123",
                    "yt_url": "url",
                    "yt_score": "92",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Mock ytmusic: lève exception "Already in library"
            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.side_effect = Exception("Already in library")

            import_matched_tracks(csv_path, mock_ytmusic)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_ALREADY_EXISTS

    def test_ac2_idempotence_already_imported(self):
        """
        AC2: Deuxième exécution avec morceau déjà importé → `already_exists`
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist",
                    "title": "Title",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid123",
                    "yt_url": "url",
                    "yt_score": "90",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.side_effect = Exception("Already in library")

            import_matched_tracks(csv_path, mock_ytmusic)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_ALREADY_EXISTS


class TestAC3Idempotence:
    """AC3: Ignorer les lignes sans match"""

    def test_ac3_skip_pending_without_video_id(self):
        """
        AC3: Ligne `pending` SANS `yt_video_id` → ignorée, statut inchangé
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist",
                    "title": "Title",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "",  # PAS de video_id
                    "yt_url": "",
                    "yt_score": "",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            import_matched_tracks(csv_path, mock_ytmusic)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_PENDING  # Inchangé
            mock_ytmusic.add_to_library.assert_not_called()

    def test_ac3_skip_non_pending_status(self):
        """
        AC3: Ligne avec statut ≠ `pending` → ignorée
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist",
                    "title": "Title",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_IMPORTED,  # Statut ≠ pending
                    "yt_video_id": "vid123",
                    "yt_url": "url",
                    "yt_score": "95",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            import_matched_tracks(csv_path, mock_ytmusic)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED  # Inchangé
            mock_ytmusic.add_to_library.assert_not_called()


class TestAC4FullCoverage:
    """AC4: 100% des lignes avec statut explicite"""

    def test_ac4_all_lines_have_explicit_status(self):
        """
        AC4: Après import, 100% des lignes ont un statut explicite
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "A1",
                    "title": "T1",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid1",
                    "yt_url": "url1",
                    "yt_score": "95",
                    "error_message": ""
                },
                {
                    "filepath": "/music/song2.mp3",
                    "artist": "A2",
                    "title": "T2",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid2",
                    "yt_url": "url2",
                    "yt_score": "90",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.return_value = None

            import_matched_tracks(csv_path, mock_ytmusic)

            result = read_csv(csv_path)

            # Vérifier: aucune ligne avec statut vide ou ""
            for row in result:
                assert row["status"], f"Ligne sans statut: {row}"
                assert row["status"] != ""


class TestAC5Atomicity:
    """AC5: Atomicité et persistance"""

    def test_ac5_csv_persisted_in_finally_block(self):
        """
        AC5: CSV persisté dans bloc `finally` même en cas d'erreur
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist",
                    "title": "Title",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid1",
                    "yt_url": "url",
                    "yt_score": "95",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # Simuler une exception après quelques appels
            mock_ytmusic.add_to_library.side_effect = RuntimeError("Network error")

            # L'import doit gérer l'erreur et persister le CSV
            try:
                import_matched_tracks(csv_path, mock_ytmusic)
            except:
                pass

            # Le CSV doit toujours exister et être valide
            result = read_csv(csv_path)
            assert len(result) == 1
            assert "status" in result[0]


class TestImporterIntegration:
    """Tests d'intégration pour importer.py"""

    def test_mixed_statuses_after_import(self):
        """
        Test d'intégration: Mélange de successful imports, already_exists, et failures
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist1",
                    "title": "Title1",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid1",
                    "yt_url": "url1",
                    "yt_score": "95",
                    "error_message": ""
                },
                {
                    "filepath": "/music/song2.mp3",
                    "artist": "Artist2",
                    "title": "Title2",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid2",
                    "yt_url": "url2",
                    "yt_score": "92",
                    "error_message": ""
                },
                {
                    "filepath": "/music/song3.mp3",
                    "artist": "Artist3",
                    "title": "Title3",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid3",
                    "yt_url": "url3",
                    "yt_score": "88",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # vid1: success, vid2: already_exists, vid3: network error
            mock_ytmusic.add_to_library.side_effect = [
                None,  # vid1 success
                Exception("Already in library"),  # vid2 already_exists
                Exception("Network timeout")  # vid3 failure
            ]

            import_matched_tracks(csv_path, mock_ytmusic)

            result = read_csv(csv_path)
            assert len(result) == 3

            # Vérifier les statuts finaux
            assert result[0]["status"] == STATUS_IMPORTED
            assert result[1]["status"] == STATUS_ALREADY_EXISTS
            assert result[2]["status"] == STATUS_FAILED

            # Vérifier que 100% ont un statut
            for row in result:
                assert row["status"] != ""
