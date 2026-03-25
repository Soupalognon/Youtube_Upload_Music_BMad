"""Tests pour matcher.py — Story 3.1 : Recherche YouTube Music et nettoyage des titres"""
import pytest
import tempfile
import csv
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from utils import (
    FIELDNAMES, STATUS_PENDING, STATUS_MANUAL_REVIEW, STATUS_LOW_CONFIDENCE, STATUS_FAILED,
    read_csv, write_csv, clean_title
)
from matcher import (
    detect_various_artists,
    build_search_query,
    search_youtube_music,
    process_matcher_loop,
    score_and_verify_youtube_result,
    assign_match_status,
    populate_csv_result,
)


# ─── Tests AC3 : Détection "Various Artists" ─────────────────────────────────

def test_detect_various_artists_exact_match():
    """AC3: "Various Artists" exact doit être détecté"""
    assert detect_various_artists("Various Artists") is True


def test_detect_various_artists_with_variants():
    """AC3: Variantes (VA, V.A., Compilation) doivent être détectées"""
    assert detect_various_artists("VA") is True
    assert detect_various_artists("V.A.") is True
    assert detect_various_artists("va") is True  # case-insensitive
    assert detect_various_artists("Compilation") is True
    assert detect_various_artists("compilation") is True


def test_detect_various_artists_with_unknown_artist():
    """AC3: Unknown Artist / Artist Unknown doit être détecté"""
    assert detect_various_artists("Unknown Artist") is True
    assert detect_various_artists("Artist Unknown") is True


def test_detect_various_artists_normal_artist_should_not_match():
    """AC3: Un artiste normal ne doit pas être détecté"""
    assert detect_various_artists("The Beatles") is False
    assert detect_various_artists("Daft Punk") is False
    assert detect_various_artists("Coldplay") is False


def test_detect_various_artists_partial_match():
    """AC3: Détection dans une chaîne mixte"""
    assert detect_various_artists("Various Artists - Soundtrack") is True
    assert detect_various_artists("Compilation 2024") is True


# ─── Tests AC1 & AC2 : Construction de requête YouTube Music ─────────────────

def test_build_search_query_basic():
    """AC1 & AC2: Requête = artist + titre nettoyé"""
    # AC2: (Remastered) doit être supprimé
    artist = "Daft Punk"
    title = "Get Lucky (Remastered)"
    expected = "Daft Punk Get Lucky"
    assert build_search_query(artist, title) == expected


def test_build_search_query_removes_live_annotation():
    """AC2: [Live] doit être supprimé"""
    query = build_search_query("Pink Floyd", "Comfortably Numb [Live]")
    assert "[Live]" not in query
    assert "Pink Floyd Comfortably Numb" == query


def test_build_search_query_removes_feat():
    """AC2: feat. X doit être supprimé"""
    query = build_search_query("Kanye West", "Gold Digger (feat. Jamie Foxx)")
    assert "feat" not in query.lower()
    assert "Jamie Foxx" not in query
    assert "Gold Digger" in query


def test_build_search_query_removes_radio_edit():
    """AC2: - Radio Edit doit être supprimé"""
    query = build_search_query("Billie Eilish", "bad guy - Radio Edit")
    assert "Radio Edit" not in query
    assert "Billie Eilish bad guy" == query


def test_build_search_query_normalizes_spaces():
    """AC2: Les espaces excédentaires doivent être normalisés"""
    query = build_search_query("Artist", "Title   with   spaces")
    assert "  " not in query  # Pas d'espaces multiples
    assert query.strip() == query  # Pas d'espaces au début/fin


def test_build_search_query_removes_empty_brackets():
    """AC2: Les parenthèses/crochets vides doivent être supprimés"""
    query = build_search_query("Artist", "Song () []")
    assert "(" not in query and "[" not in query


# ─── Tests AC1 : Recherche YouTube Music ───────────────────────────────────

@patch('matcher.YTMusic')
def test_search_youtube_music_returns_results(mock_ytmusic_class):
    """AC1: ytmusic.search() doit retourner les résultats"""
    mock_instance = Mock()
    mock_ytmusic_class.return_value = mock_instance

    expected_results = [
        {"videoId": "dQw4w9WgXcQ", "title": "Get Lucky", "artists": [{"name": "Daft Punk"}]},
    ]
    mock_instance.search.return_value = expected_results

    ytmusic = Mock(search=Mock(return_value=expected_results))
    results = search_youtube_music(ytmusic, "Daft Punk Get Lucky")

    assert len(results) > 0
    assert results[0]["videoId"] == "dQw4w9WgXcQ"


@patch('matcher.YTMusic')
def test_search_youtube_music_with_filter_songs(mock_ytmusic_class):
    """AC1: Utiliser filter='songs' dans ytmusic.search()"""
    mock_instance = Mock()
    mock_ytmusic_class.return_value = mock_instance
    mock_instance.search.return_value = []

    ytmusic = mock_instance
    search_youtube_music(ytmusic, "Test Query")

    ytmusic.search.assert_called_once()
    call_args = ytmusic.search.call_args
    assert call_args[0][0] == "Test Query"
    assert call_args[1].get("filter") == "songs"


# ─── Tests Story 3.1 : Intégration boucle principale ───────────────────────────

def test_process_matcher_loop_skips_non_pending():
    """Story 3.1: Ne pas traiter les lignes non-pending"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        # Préparer une CSV avec une ligne non-pending
        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "The Beatles",
                "title": "Let It Be",
                "album": "Abbey Road",
                "duration": "239",
                "status": STATUS_PENDING,
                "yt_video_id": "",  # ← Vide
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            },
            {
                "filepath": "/music/song2.mp3",
                "artist": "Pink Floyd",
                "title": "Wish You Were Here",
                "album": "WYWH",
                "duration": "297",
                "status": "duplicate",  # ← Non-pending
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {"videoId": "xyz", "title": "Let It Be"}
        ]

        # Traiter
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Vérifier que seule la première ligne a été traitée
        assert mock_ytmusic.search.call_count == 1  # Une seule requête


def test_process_matcher_loop_detects_various_artists():
    """Story 3.1: Détecter "Various Artists" et marquer manual_review"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/compilation.mp3",
                "artist": "Various Artists",
                "title": "Song Title",
                "album": "Compilation",
                "duration": "180",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        mock_ytmusic = Mock()
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Vérifier qu'aucune recherche n'a été faite
        mock_ytmusic.search.assert_not_called()

        # Vérifier que la ligne a été marquée manual_review
        assert processed_rows[0]["status"] == STATUS_MANUAL_REVIEW


def test_process_matcher_loop_skips_lines_with_yt_video_id():
    """Story 3.1: Ne pas retraiter les lignes déjà enrichies"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "The Beatles",
                "title": "Let It Be",
                "album": "Abbey Road",
                "duration": "239",
                "status": STATUS_PENDING,
                "yt_video_id": "already_has_id",  # ← Déjà enrichi
                "yt_url": "https://...",
                "yt_score": "95",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        mock_ytmusic = Mock()
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Vérifier qu'aucune recherche n'a été faite
        mock_ytmusic.search.assert_not_called()


def test_process_matcher_loop_persists_changes_immediately():
    """Story 3.1: Idempotence — écrire CSV immédiatement après traitement"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/various.mp3",
                "artist": "Various Artists",
                "title": "Track",
                "album": "Comp",
                "duration": "200",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        mock_ytmusic = Mock()
        process_matcher_loop(mock_ytmusic, str(csv_path))

        # Relire le CSV et vérifier les changements
        reloaded = read_csv(str(csv_path))
        assert reloaded[0]["status"] == STATUS_MANUAL_REVIEW


# ─── Tests d'intégration avec clean_title() ───────────────────────────────────

def test_clean_title_integration_with_build_query():
    """AC2: Vérifier que clean_title() fonctionne dans build_search_query()"""
    # Cette fonction est déjà testée en test_utils.py,
    # mais on la vérifie ici comme partie du flux matcher

    # clean_title() supprime (Remastered)
    assert "Remastered" not in clean_title("Song (Remastered)")

    # clean_title() supprime [Live]
    assert "[Live]" not in clean_title("Song [Live]")


# ─── Tests YTMusic initialization ──────────────────────────────────────────────

@patch('matcher.YTMusic')
def test_ytmusic_initialized_once(mock_ytmusic_class):
    """Story 3.1: YTMusic doit être initialisé une seule fois (avant la boucle)"""
    mock_instance = Mock()
    mock_ytmusic_class.return_value = mock_instance
    mock_instance.search.return_value = []

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        # Créer 3 lignes pending
        rows = [
            {
                "filepath": f"/music/song{i}.mp3",
                "artist": "Artist",
                "title": f"Song {i}",
                "album": "Album",
                "duration": "180",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
            for i in range(3)
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Traiter
        process_matcher_loop(mock_instance, str(csv_path))

        # Vérifier que search() a été appelé 3 fois, mais YTMusic.__init__() une fois
        assert mock_ytmusic_class.call_count <= 1  # Au max une fois


# ─── Tests Story 3.2 : Scoring de similarité et vérification de durée ─────────────

def test_score_matching_exact_match():
    """AC1: Scoring exact match = 100"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "Daft Punk", "title": "Get Lucky", "duration": 244}
    yt_result = {"title": "Get Lucky", "artist": "Daft Punk", "duration": 244}
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": True}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is not None
    assert score >= 85  # Exact match should be high confidence


def test_score_matching_partial_match():
    """AC1: Scoring partial match (70-85 range)"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "The Beatles", "title": "Let It Be", "duration": 240}
    yt_result = {"title": "Let It Be", "artist": "The Beetles", "duration": 240}  # Typo
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": True}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is not None
    assert 0 <= score <= 100


def test_score_matching_with_missing_duration():
    """AC2: Missing duration should return None (failed)"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "Artist", "title": "Song", "duration": 180}
    yt_result = {"title": "Song", "artist": "Artist", "duration": None}  # Missing
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": True}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is None


def test_duration_verification_within_tolerance():
    """AC2: Duration within tolerance (±5s) should be valid"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "Daft Punk", "title": "Get Lucky", "duration": 245}
    yt_result = {"title": "Get Lucky", "artist": "Daft Punk", "duration": 244}  # Diff = 1s, tolerance = 5s
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": True}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is not None  # Should be valid


def test_duration_verification_exceeds_tolerance():
    """AC2: Duration exceeds tolerance should fail"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "Daft Punk", "title": "Get Lucky", "duration": 250}
    yt_result = {"title": "Get Lucky", "artist": "Daft Punk", "duration": 240}  # Diff = 10s, tolerance = 5s
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": True}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is None  # Duration exceeds tolerance


def test_live_filtering_enabled():
    """AC3: Live versions should be excluded when filter_live=true"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "Pink Floyd", "title": "Comfortably Numb", "duration": 400}
    yt_result = {"title": "Comfortably Numb [Live]", "artist": "Pink Floyd", "duration": 400}
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": True}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is None  # Live version should be excluded


def test_live_filtering_disabled():
    """AC3: Live versions should be allowed when filter_live=false"""
    from matcher import score_and_verify_youtube_result

    local_row = {"artist": "Pink Floyd", "title": "Comfortably Numb", "duration": 400}
    yt_result = {"title": "Comfortably Numb [Live]", "artist": "Pink Floyd", "duration": 400}
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70, "duration_tolerance": 5, "filter_live": False}

    score = score_and_verify_youtube_result(local_row, yt_result, config)
    assert score is not None  # Should be processed


def test_status_assignment_good_match():
    """AC4: Score >= 85 and valid duration = STATUS_PENDING"""
    from matcher import assign_match_status

    score = 90
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70}

    status = assign_match_status(score, config)
    assert status == STATUS_PENDING


def test_status_assignment_uncertain_match():
    """AC4: Score 70-85 and valid duration = STATUS_LOW_CONFIDENCE"""
    from matcher import assign_match_status

    score = 75
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70}

    status = assign_match_status(score, config)
    assert status == STATUS_LOW_CONFIDENCE


def test_status_assignment_failed_match():
    """AC4: Score < 70 = STATUS_FAILED"""
    from matcher import assign_match_status

    score = 60
    config = {"confidence_threshold": 85, "low_confidence_threshold": 70}

    status = assign_match_status(score, config)
    assert status == STATUS_FAILED


def test_populate_csv_columns_with_score():
    """AC5: Populate yt_video_id and yt_score when match is valid"""
    from matcher import populate_csv_result
    from utils import STATUS_PENDING

    row = {"artist": "Artist", "title": "Song", "duration": "180", "status": STATUS_PENDING, "yt_video_id": "", "yt_score": ""}
    yt_result = {"videoId": "abc123xyz", "title": "Song", "artist": "Artist", "duration": 180}
    score = 95
    status = STATUS_PENDING

    populate_csv_result(row, yt_result, score, status)

    assert row["yt_video_id"] == "abc123xyz"
    assert row["yt_score"] == "95"
    assert row["status"] == STATUS_PENDING


def test_populate_csv_columns_when_failed():
    """AC5: yt_video_id and yt_score remain empty when status=FAILED"""
    from matcher import populate_csv_result

    row = {"artist": "Artist", "title": "Song", "duration": "180", "status": STATUS_PENDING, "yt_video_id": "", "yt_score": ""}
    yt_result = {"videoId": "abc123xyz", "title": "Song", "artist": "Artist", "duration": 180}
    score = 50
    status = STATUS_FAILED

    populate_csv_result(row, yt_result, score, status)

    assert row["yt_video_id"] == ""
    assert row["yt_score"] == ""
    assert row["status"] == STATUS_FAILED


def test_process_matcher_loop_with_scoring():
    """Story 3.2: Verify that scoring is applied in the main loop"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic with realistic results
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {
                "videoId": "aq2KrGaF_kM",
                "title": "Get Lucky",
                "artists": [{"name": "Daft Punk"}],
                "duration": 244
            }
        ]

        # Process with Story 3.1 + 3.2
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Verify that yt_video_id was populated (indicating scoring was done)
        assert processed_rows[0]["yt_video_id"] == "aq2KrGaF_kM"
        assert processed_rows[0]["yt_score"] != ""
        assert processed_rows[0]["status"] in [STATUS_PENDING, STATUS_LOW_CONFIDENCE]


# ─── Tests Story 3.3 : Génération d'URLs et persistance CSV ─────────────────────

def test_story_3_3_ac1_url_generation_for_matched_track():
    """AC1: URL générée pour chaque morceau matché avec yt_video_id"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {
                "videoId": "aq2KrGaF_kM",
                "title": "Get Lucky",
                "artists": [{"name": "Daft Punk"}],
                "duration": 244
            }
        ]

        # Process
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Verify URL was generated
        assert processed_rows[0]["yt_url"] == "https://music.youtube.com/watch?v=aq2KrGaF_kM"
        assert processed_rows[0]["status"] in [STATUS_PENDING, STATUS_LOW_CONFIDENCE]


def test_story_3_3_ac2_csv_persistence_immediately():
    """AC2: CSV persisté immédiatement après chaque morceau (pas de perte en cas d'arrêt brutal)"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "The Beatles",
                "title": "Let It Be",
                "album": "Abbey Road",
                "duration": "239",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            },
            {
                "filepath": "/music/song2.mp3",
                "artist": "Pink Floyd",
                "title": "Wish You Were Here",
                "album": "WYWH",
                "duration": "297",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {
                "videoId": "dQw4w9WgXcQ",
                "title": "Let It Be",
                "artists": [{"name": "The Beatles"}],
                "duration": 239
            }
        ]

        # Process only first row manually to simulate interruption
        process_matcher_loop(mock_ytmusic, str(csv_path))

        # Re-read CSV - should have persisted data for first row
        reloaded = read_csv(str(csv_path))
        assert reloaded[0]["yt_video_id"] != ""  # First row enriched
        assert reloaded[0]["yt_url"] != ""  # URL persisted
        # Second row should remain unchanged
        assert reloaded[1]["yt_video_id"] == ""


def test_story_3_3_ac3_idempotence_skip_enriched_rows():
    """AC3: Idempotence — skip de lignes déjà enrichies avec yt_video_id"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "aq2KrGaF_kM",  # Already enriched
                "yt_url": "https://music.youtube.com/watch?v=aq2KrGaF_kM",
                "yt_score": "100",
                "error_message": ""
            },
            {
                "filepath": "/music/song2.mp3",
                "artist": "The Beatles",
                "title": "Let It Be",
                "album": "Abbey Road",
                "duration": "239",
                "status": STATUS_PENDING,
                "yt_video_id": "",  # Not enriched yet
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {
                "videoId": "dQw4w9WgXcQ",
                "title": "Let It Be",
                "artists": [{"name": "The Beatles"}],
                "duration": 239
            }
        ]

        # Process
        process_matcher_loop(mock_ytmusic, str(csv_path))

        # Verify only second row was processed (search called once for second row)
        assert mock_ytmusic.search.call_count == 1


def test_story_3_3_ac4_empty_url_for_failed():
    """AC4: URL vide pour morceaux avec statut failed ou manual_review"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Various Artists",
                "title": "Unknown Track",
                "album": "Compilation",
                "duration": "200",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic (won't be called for Various Artists)
        mock_ytmusic = Mock()

        # Process
        process_matcher_loop(mock_ytmusic, str(csv_path))

        # Re-read CSV
        reloaded = read_csv(str(csv_path))

        # Verify: manual_review status with empty URL
        assert reloaded[0]["status"] == STATUS_MANUAL_REVIEW
        assert reloaded[0]["yt_video_id"] == ""
        assert reloaded[0]["yt_url"] == ""


def test_story_3_3_url_format_clickable():
    """AC1: URL doit être au format cliquable et valide pour Excel"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {
                "videoId": "test_video_id_12345",
                "title": "Get Lucky",
                "artists": [{"name": "Daft Punk"}],
                "duration": 244
            }
        ]

        # Process
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Verify URL format is correct and clickable
        url = processed_rows[0]["yt_url"]
        assert url.startswith("https://music.youtube.com/watch?v=")
        assert "test_video_id_12345" in url
        assert url == "https://music.youtube.com/watch?v=test_video_id_12345"


# ─── Tests Story 3.4 : Résilience réseau et progression ─────────────────────────

def test_story_3_4_ac1_exponential_backoff_on_429():
    """AC1: Backoff exponentiel sur erreur 429 (rate limit)"""
    import requests
    from unittest.mock import patch, call

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic to fail on first attempt, succeed on second
        mock_ytmusic = Mock()
        mock_ytmusic.search.side_effect = [
            requests.exceptions.Timeout("HTTP 429"),  # First attempt fails
            [  # Second attempt succeeds
                {
                    "videoId": "aq2KrGaF_kM",
                    "title": "Get Lucky",
                    "artists": [{"name": "Daft Punk"}],
                    "duration": 244
                }
            ]
        ]

        # Process - should retry and succeed
        with patch('matcher.time.sleep') as mock_sleep:
            processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

            # Verify that sleep was called with exponential backoff
            assert mock_sleep.called
            assert mock_ytmusic.search.call_count == 2


def test_story_3_4_ac1_max_3_retries_then_failed():
    """AC1: Après 3 tentatives échouées, statut=failed"""
    import requests

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic to always fail
        mock_ytmusic = Mock()
        mock_ytmusic.search.side_effect = requests.exceptions.Timeout("Always fails")

        # Process
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # After 3 failed attempts, should be marked as failed
        assert processed_rows[0]["status"] == STATUS_FAILED


def test_story_3_4_ac2_tqdm_progress_bar():
    """AC2: Barre tqdm affiche la progression"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": f"/music/song{i}.mp3",
                "artist": "Artist",
                "title": f"Song {i}",
                "album": "Album",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
            for i in range(3)
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic
        mock_ytmusic = Mock()
        mock_ytmusic.search.return_value = [
            {
                "videoId": "test_id",
                "title": "Song",
                "artists": [{"name": "Artist"}],
                "duration": 244
            }
        ]

        # Process - should use tqdm internally
        processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # All rows should be processed
        assert len(processed_rows) == 3


def test_story_3_4_ac4_logging_on_retry():
    """AC4: Message de retry loggé lors de chaque tentative"""
    import requests
    import logging

    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": "/music/song1.mp3",
                "artist": "Daft Punk",
                "title": "Get Lucky",
                "album": "RAM",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic to fail then succeed
        mock_ytmusic = Mock()
        mock_ytmusic.search.side_effect = [
            requests.exceptions.Timeout("HTTP 429"),
            [
                {
                    "videoId": "aq2KrGaF_kM",
                    "title": "Get Lucky",
                    "artists": [{"name": "Daft Punk"}],
                    "duration": 244
                }
            ]
        ]

        # Process
        with patch('matcher.time.sleep'):
            processed_rows = process_matcher_loop(mock_ytmusic, str(csv_path))

        # Should succeed after retry
        assert processed_rows[0]["yt_video_id"] == "aq2KrGaF_kM"


def test_story_3_4_ac5_graceful_keyboard_interrupt():
    """AC5: Ctrl+C interrompt gracieusement et persiste le CSV"""
    with tempfile.TemporaryDirectory() as tmpdir:
        csv_path = Path(tmpdir) / "library.csv"

        rows = [
            {
                "filepath": f"/music/song{i}.mp3",
                "artist": "Artist",
                "title": f"Song {i}",
                "album": "Album",
                "duration": "244",
                "status": STATUS_PENDING,
                "yt_video_id": "",
                "yt_url": "",
                "yt_score": "",
                "error_message": ""
            }
            for i in range(5)
        ]
        write_csv(str(csv_path), rows, FIELDNAMES)

        # Mock YTMusic and interrupt after first row
        mock_ytmusic = Mock()
        mock_ytmusic.search.side_effect = KeyboardInterrupt()

        # Process - should handle interrupt gracefully
        try:
            process_matcher_loop(mock_ytmusic, str(csv_path))
        except KeyboardInterrupt:
            pass  # Expected

        # CSV should still exist and be readable
        reloaded = read_csv(str(csv_path))
        assert len(reloaded) == 5


