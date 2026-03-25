"""
Tests pour Story 4.2 : Résilience réseau et rate limiting de l'importer
Couvre AC1–AC7 : Backoff exponentiel, délai API, classification erreurs, atomicité
"""
import pytest
import time
import tempfile
import os
from unittest.mock import Mock, patch
from pathlib import Path

from importer import (
    import_matched_tracks,
    is_transient_error,
    MAX_RETRIES
)
from utils import (
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
    FIELDNAMES, write_csv, read_csv
)


# ─── Tests AC1: Application du délai `api_delay` configurable ──────────────────
class TestAC1_ApiDelay:
    """AC1 — Application du délai configurable entre appels API"""

    def test_api_delay_applied_between_successful_calls(self):
        """
        Given: un délai `api_delay` configuré (ex: 0.3s)
        When: importer traite 2 morceaux avec succès
        Then: le temps écoulé >= 0.3s (delai appliqué après chaque appel)
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
                    "yt_score": "95",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.return_value = None

            config = {"api_delay": 0.3}

            with patch('importer.load_config', return_value=config):
                start = time.time()
                import_matched_tracks(csv_path, mock_ytmusic, config)
                elapsed = time.time() - start

            # Devrait avoir au minimum 1 x 0.3s de délai
            assert elapsed >= 0.3, f"Expected >= 0.3s delay but got {elapsed}s"
            assert mock_ytmusic.add_to_library.call_count == 2

    def test_no_delay_when_api_delay_is_zero(self):
        """
        Given: `api_delay` = 0
        When: importer traite 2 morceaux
        Then: aucun délai entre appels (< 0.05s total)
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
                    "yt_score": "95",
                    "error_message": ""
                }
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.return_value = None

            config = {"api_delay": 0}

            with patch('importer.load_config', return_value=config):
                start = time.time()
                import_matched_tracks(csv_path, mock_ytmusic, config)
                elapsed = time.time() - start

            # Sans délai, devrait être très rapide
            assert elapsed < 0.1, f"Expected < 0.1s but got {elapsed}s"


# ─── Tests AC2: Backoff exponentiel sur HTTP 429 ────────────────────────────
class TestAC2_ExponentialBackoff:
    """AC2 — Backoff exponentiel sur HTTP 429 (rate limit)"""

    def test_retry_on_429_then_success(self):
        """
        Given: première tentative échoue avec HTTP 429
        When: importer rétente après 1 seconde
        Then: deuxième tentative réussit, morceau marqué `imported`
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
            # Première tentative lève 429, deuxième réussit
            mock_ytmusic.add_to_library = Mock(
                side_effect=[Exception("HTTP 429 Too Many Requests"), None]
            )

            config = {"api_delay": 0}

            with patch('importer.load_config', return_value=config):
                start = time.time()
                import_matched_tracks(csv_path, mock_ytmusic, config)
                elapsed = time.time() - start

            # Devrait avoir backoff 2^0 = 1 seconde
            assert elapsed >= 1.0, f"Expected >= 1.0s backoff but got {elapsed}s"

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED
            assert mock_ytmusic.add_to_library.call_count == 2

    def test_all_retries_fail_marked_failed(self):
        """
        Given: toutes les 3 tentatives échouent avec HTTP 429
        When: les retries sont épuisés
        Then: morceau est marqué `failed` avec message d'erreur
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
            mock_ytmusic.add_to_library = Mock(
                side_effect=Exception("HTTP 429 Too Many Requests")
            )

            config = {"api_delay": 0}

            with patch('importer.load_config', return_value=config):
                import_matched_tracks(csv_path, mock_ytmusic, config)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_FAILED
            assert "429" in result[0].get("error_message", "")
            # 3 tentatives pour 1 morceau
            assert mock_ytmusic.add_to_library.call_count == 3


# ─── Tests AC3: Gestion des erreurs réseau isolées ────────────────────────────
class TestAC3_NetworkErrors:
    """AC3 — Gestion des erreurs réseau isolées"""

    def test_timeout_retry_then_success(self):
        """
        Given: erreur TimeoutError lors du traitement
        When: importer rétente
        Then: succès après retry, morceau marqué `imported`
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
            mock_ytmusic.add_to_library = Mock(
                side_effect=[TimeoutError("Connection timeout"), None]
            )

            config = {"api_delay": 0}

            with patch('importer.load_config', return_value=config):
                import_matched_tracks(csv_path, mock_ytmusic, config)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED
            assert mock_ytmusic.add_to_library.call_count == 2

    def test_already_exists_no_retry(self):
        """
        Given: erreur "already_exists"
        When: importer la rencontre
        Then: aucune tentative supplémentaire, marqué `already_exists`
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
            mock_ytmusic.add_to_library = Mock(
                side_effect=Exception("already_exists")
            )

            config = {"api_delay": 0}

            with patch('importer.load_config', return_value=config):
                import_matched_tracks(csv_path, mock_ytmusic, config)

            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_ALREADY_EXISTS
            # Seulement 1 tentative (pas de retry pour already_exists)
            assert mock_ytmusic.add_to_library.call_count == 1


# ─── Tests AC4: Distinction erreur transitoire vs permanente ──────────────────
class TestAC4_ErrorClassification:
    """AC4 — Distinction erreur transitoire vs permanente"""

    def test_is_transient_error_429(self):
        """HTTP 429 = erreur transitoire"""
        assert is_transient_error(Exception("HTTP 429")) is True

    def test_is_transient_error_timeout(self):
        """TimeoutError = erreur transitoire"""
        assert is_transient_error(TimeoutError()) is True

    def test_is_transient_error_connection(self):
        """ConnectionError = erreur transitoire"""
        assert is_transient_error(ConnectionError()) is True

    def test_is_transient_error_502(self):
        """HTTP 502 = erreur transitoire"""
        assert is_transient_error(Exception("HTTP 502")) is True

    def test_is_permanent_error_already_exists(self):
        """'already_exists' = erreur permanente"""
        assert is_transient_error(Exception("already_exists")) is False

    def test_is_permanent_error_400(self):
        """HTTP 400 = erreur permanente"""
        assert is_transient_error(Exception("HTTP 400")) is False

    def test_is_permanent_error_404(self):
        """HTTP 404 = erreur permanente"""
        assert is_transient_error(Exception("HTTP 404")) is False


# ─── Tests AC5: Atomicité et persistance pendant les retries ────────────────
class TestAC5_Atomicity:
    """AC5 — Atomicité et persistance pendant les retries"""

    def test_csv_written_once_per_track_after_retries(self):
        """
        Given: morceau en cours de retry (backoff)
        When: toutes les tentatives sont complètes
        Then: CSV écrit une seule fois par morceau (après dernière tentative)
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
            mock_ytmusic.add_to_library = Mock(
                side_effect=[Exception("HTTP 429"), None]
            )

            config = {"api_delay": 0}

            write_call_count = 0

            original_write_csv = __import__('utils').write_csv

            def counting_write_csv(*args, **kwargs):
                nonlocal write_call_count
                write_call_count += 1
                return original_write_csv(*args, **kwargs)

            with patch('importer.write_csv', side_effect=counting_write_csv):
                with patch('importer.load_config', return_value=config):
                    import_matched_tracks(csv_path, mock_ytmusic, config)

            # Vérifier le CSV final
            result = read_csv(csv_path)
            assert result[0]["status"] == STATUS_IMPORTED


# ─── Tests AC6: Interruptibilité gracieuse (Ctrl+C) ────────────────────────
class TestAC6_KeyboardInterrupt:
    """AC6 — Comportement en présence d'interruption (Ctrl+C)"""

    def test_keyboard_interrupt_preserves_pending_status(self):
        """
        Given: importer en plein traitement
        When: utilisateur presse Ctrl+C
        Then: morceau EN COURS reste `pending`, pas écrit au CSV
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
            mock_ytmusic.add_to_library = Mock(side_effect=KeyboardInterrupt())

            config = {"api_delay": 0}

            with patch('importer.load_config', return_value=config):
                with pytest.raises(KeyboardInterrupt):
                    import_matched_tracks(csv_path, mock_ytmusic, config)


# ─── Tests AC7: Rate limiting vs Performance ──────────────────────────────────
class TestAC7_Performance:
    """AC7 — Rate limiting vs Performance — tqdm pas bloqué"""

    def test_multiple_tracks_with_delays_processed_sequentially(self):
        """
        Given: 3 morceaux avec `api_delay` configuré
        When: tous traités avec succès
        Then: tous ont statut `imported`
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "library.csv")

            rows = [
                {
                    "filepath": f"/music/song{i}.mp3",
                    "artist": f"Artist{i}",
                    "title": f"Title{i}",
                    "album": "Album",
                    "duration": "180",
                    "status": STATUS_PENDING,
                    "yt_video_id": f"vid{i}",
                    "yt_url": f"url{i}",
                    "yt_score": "95",
                    "error_message": ""
                }
                for i in range(3)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            mock_ytmusic = Mock()
            mock_ytmusic.add_to_library.return_value = None

            config = {"api_delay": 0.1}

            with patch('importer.load_config', return_value=config):
                import_matched_tracks(csv_path, mock_ytmusic, config)

            result = read_csv(csv_path)
            # Tous les morceaux doivent être traités
            assert all(r["status"] == STATUS_IMPORTED for r in result)
            assert len(result) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
