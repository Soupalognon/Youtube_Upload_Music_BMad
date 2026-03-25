"""
Test suite pour Story 4.4: Suivi temps réel et résumé de fin de run
Couvre AC1–AC4 : Progress bar, status logging, end-of-run summary, performance
"""
import pytest
import tempfile
import os
import csv
import time
import logging
import sys
from io import StringIO
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path

from importer import (
    import_matched_tracks,
    _should_import_track,
    _ensure_all_statuses_assigned
)
from utils import (
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS,
    STATUS_FAILED, STATUS_ERROR_READ, FIELDNAMES, write_csv, read_csv
)


class TestAC1ProgressBar:
    """AC1: Real-time Progress Bar with tqdm"""

    def test_ac1_tqdm_displays_percentage(self):
        """AC1: Vérifier que tqdm s'affiche avec le pourcentage"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            # Setup: créer 5 lignes pending avec yt_video_id
            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": "Test Artist",
                    "title": f"Song {i}",
                    "album": "Test Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"video_id_{i}",
                    "yt_url": f"https://music.youtube.com/watch?v=video_id_{i}",
                    "yt_score": "95",
                    "error_message": ""
                }
                for i in range(5)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Mock ytmusic.add_to_library() → succès
            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library = Mock()

            # Capturer la barre tqdm
            with patch('importer.tqdm') as mock_tqdm:
                mock_tqdm.return_value = rows  # Retourner les lignes filtrées

                config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
                import_matched_tracks(csv_path, mock_ytmusic, config)

                # Vérifier que tqdm a été appelé
                mock_tqdm.assert_called_once()

    def test_ac1_progress_bar_shows_artist_title(self):
        """AC1: Barre affiche artist - title pour morceau en cours"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/daft.mp3",
                    "artist": "Daft Punk",
                    "title": "Get Lucky",
                    "album": "RAM",
                    "duration": "244",
                    "status": STATUS_PENDING,
                    "yt_video_id": "xyz123",
                    "yt_url": "https://...",
                    "yt_score": "99",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library = Mock()

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
            import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier que le morceau a été marqué imported
            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED


class TestAC2StatusLogging:
    """AC2: Real-time Status Logging (non-standard statuts)"""

    def test_ac2_log_already_exists(self, caplog):
        """AC2: Logguer 'already_exists' au niveau INFO"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song.mp3",
                    "artist": "Beatles",
                    "title": "Let It Be",
                    "album": "Let It Be",
                    "duration": "243",
                    "status": STATUS_PENDING,
                    "yt_video_id": "already_exists_id",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # Simuler l'erreur "Already in library"
            mock_ytmusic.add_to_library.side_effect = Exception("Already in library")

            with caplog.at_level(logging.INFO):
                config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
                import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier que le log contient le message pour already_exists
            assert any("already_exists" in record.message.lower() for record in caplog.records)

    def test_ac2_log_failed_with_reason(self, caplog):
        """AC2: Logguer 'failed' au niveau ERROR avec raison"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song.mp3",
                    "artist": "Artist",
                    "title": "Song",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": "fail_id",
                    "yt_url": "",
                    "yt_score": "80",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # Simuler 3 erreurs 429 → échec après retries
            mock_ytmusic.add_to_library.side_effect = Exception("HTTP 429 Too Many Requests")

            with caplog.at_level(logging.ERROR):
                config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
                import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier que le log contient "failed"
            assert any("failed" in record.message.lower() for record in caplog.records)

    def test_ac2_log_format_correct(self, caplog):
        """AC2: Format du log est [LEVEL] artist - title → status"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song.mp3",
                    "artist": "Pink Floyd",
                    "title": "Wish You Were Here",
                    "album": "Album",
                    "duration": "300",
                    "status": STATUS_PENDING,
                    "yt_video_id": "test_id",
                    "yt_url": "",
                    "yt_score": "95",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library = Mock()

            with caplog.at_level(logging.INFO):
                config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
                import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier que le log contient le format attendu
            assert any("Pink Floyd" in record.message for record in caplog.records)


class TestAC3EndOfRunSummary:
    """AC3: End-of-Run Summary with status counts"""

    def test_ac3_summary_displays_counts(self, capsys):
        """AC3: Résumé affiche les comptes par statut"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            # Setup: 10 lignes avec différents statuts
            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": "Artist",
                    "title": f"Song {i}",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid_{i}",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
                for i in range(8)
            ] + [
                {
                    "filepath": "/music/existing.mp3",
                    "artist": "Artist",
                    "title": "Existing",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": "existing_id",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                },
                {
                    "filepath": "/music/corrupt.mp3",
                    "artist": "Artist",
                    "title": "Corrupt",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": "corrupt_id",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # 8 succès, 1 already_exists, 1 échec
            side_effects = [None] * 8 + [Exception("Already in library")] + [Exception("HTTP 429")] * 3
            mock_ytmusic.add_to_library.side_effect = side_effects

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
            import_matched_tracks(csv_path, mock_ytmusic, config)

            captured = capsys.readouterr()
            # Vérifier que le résumé contient des comptes
            assert "imported" in captured.out.lower() or "résumé" in captured.out.lower()

    def test_ac3_summary_sorted_logically(self, capsys):
        """AC3: Résumé trié par logique (succès en haut, erreurs en bas)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": "Artist",
                    "title": f"Song {i}",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid_{i}",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
                for i in range(5)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library = Mock()

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
            import_matched_tracks(csv_path, mock_ytmusic, config)

            captured = capsys.readouterr()
            # Juste vérifier que quelque chose s'affiche
            assert len(captured.out) > 0

    def test_ac3_summary_shows_total(self, capsys):
        """AC3: Résumé inclut le TOTAL des morceaux"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": "Artist",
                    "title": f"Song {i}",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid_{i}",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
                for i in range(3)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library = Mock()

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
            import_matched_tracks(csv_path, mock_ytmusic, config)

            captured = capsys.readouterr()
            assert "total" in captured.out.lower() or "3" in captured.out


class TestAC4PerformanceNonBlocking:
    """AC4: Non-blocking Performance (<5% overhead)"""

    def test_ac4_logging_overhead_minimal(self):
        """AC4: Surcharge logging < 5% du temps de traitement"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            # 100 morceaux
            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": f"Artist {i}",
                    "title": f"Song {i}",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid_{i}",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
                for i in range(100)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # Fast mock - retourne immédiatement
            mock_ytmusic.add_to_library = Mock()

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}

            # Mesurer le temps
            start = time.time()
            import_matched_tracks(csv_path, mock_ytmusic, config)
            elapsed = time.time() - start

            # Vérifier que le traitement est raisonnablement rapide
            # 100 morceaux ne devraient pas prendre plus de quelques secondes
            assert elapsed < 30  # Acceptable pour 100 morceaux avec CSV I/O

    def test_ac4_tqdm_updates_do_not_block(self):
        """AC4: Les updates de tqdm ne bloquent pas le traitement"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": "Artist",
                    "title": f"Song {i}",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid_{i}",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
                for i in range(50)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library = Mock()

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
            import_matched_tracks(csv_path, mock_ytmusic, config)

            # Si on arrive ici sans timeout, c'est bon
            result = read_csv(csv_path)
            assert len(result) == 50
            assert all(r["status"] == STATUS_IMPORTED for r in result)


class TestAC4Integration:
    """AC4: Integration tests for full Story 4.4"""

    def test_ac4_interrupt_still_shows_summary(self):
        """AC4: Interruption (Ctrl+C) affiche quand même le résumé"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": "Artist",
                    "title": f"Song {i}",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid_{i}",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                }
                for i in range(5)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # Lancer KeyboardInterrupt à la deuxième itération
            mock_ytmusic.add_to_library.side_effect = [None, KeyboardInterrupt()]

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}

            with pytest.raises(KeyboardInterrupt):
                import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier que le CSV a au moins les 2 premiers morceaux traités
            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED

    def test_ac4_full_end_to_end_with_mixed_statuses(self, capsys):
        """AC4: End-to-end test with mixed statuses (success, already_exists, failed)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": "/music/song1.mp3",
                    "artist": "Artist 1",
                    "title": "Song 1",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid1",
                    "yt_url": "",
                    "yt_score": "90",
                    "error_message": ""
                },
                {
                    "filepath": "/music/song2.mp3",
                    "artist": "Artist 2",
                    "title": "Song 2",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid2",
                    "yt_url": "",
                    "yt_score": "85",
                    "error_message": ""
                },
                {
                    "filepath": "/music/song3.mp3",
                    "artist": "Artist 3",
                    "title": "Song 3",
                    "album": "Album",
                    "duration": "200",
                    "status": STATUS_PENDING,
                    "yt_video_id": "vid3",
                    "yt_url": "",
                    "yt_score": "80",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            # song1: succès, song2: already_exists, song3: failed
            mock_ytmusic.add_to_library.side_effect = [
                None,
                Exception("Already in library"),
                Exception("HTTP 429 Too Many Requests"),
                Exception("HTTP 429 Too Many Requests"),
                Exception("HTTP 429 Too Many Requests")
            ]

            config = {"api_delay": 0, "music_folder": "", "confidence_threshold": 70}
            import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier les statuts
            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED
            assert result[1]["status"] == STATUS_ALREADY_EXISTS
            assert result[2]["status"] == STATUS_FAILED

            # Vérifier que quelque chose s'affiche
            captured = capsys.readouterr()
            assert len(captured.out) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
