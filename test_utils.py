"""Tests pour utils.py — Story 1.1 : Initialisation de la structure du projet"""
import csv
import os
import sys
import tempfile
import pytest

# ─── Tests des constantes ──────────────────────────────────────────────────────

def test_status_constants_are_strings():
    from utils import (
        STATUS_PENDING, STATUS_IMPORTED, STATUS_LOW_CONFIDENCE,
        STATUS_FAILED, STATUS_DUPLICATE, STATUS_MANUAL_REVIEW,
        STATUS_ALREADY_EXISTS, STATUS_ERROR_READ
    )
    assert STATUS_PENDING        == "pending"
    assert STATUS_IMPORTED       == "imported"
    assert STATUS_LOW_CONFIDENCE == "low_confidence"
    assert STATUS_FAILED         == "failed"
    assert STATUS_DUPLICATE      == "duplicate"
    assert STATUS_MANUAL_REVIEW  == "manual_review"
    assert STATUS_ALREADY_EXISTS == "already_exists"
    assert STATUS_ERROR_READ     == "error_read"


def test_all_statuses_has_eight_items():
    from utils import ALL_STATUSES
    assert len(ALL_STATUSES) == 8


def test_all_statuses_contains_each_status():
    from utils import (
        ALL_STATUSES,
        STATUS_PENDING, STATUS_IMPORTED, STATUS_LOW_CONFIDENCE,
        STATUS_FAILED, STATUS_DUPLICATE, STATUS_MANUAL_REVIEW,
        STATUS_ALREADY_EXISTS, STATUS_ERROR_READ
    )
    for s in [STATUS_PENDING, STATUS_IMPORTED, STATUS_LOW_CONFIDENCE,
              STATUS_FAILED, STATUS_DUPLICATE, STATUS_MANUAL_REVIEW,
              STATUS_ALREADY_EXISTS, STATUS_ERROR_READ]:
        assert s in ALL_STATUSES


def test_fieldnames_has_ten_columns():
    from utils import FIELDNAMES
    assert len(FIELDNAMES) == 10


def test_fieldnames_content():
    from utils import FIELDNAMES
    expected = [
        "filepath", "artist", "title", "album", "duration",
        "status", "yt_video_id", "yt_url", "yt_score", "error_message"
    ]
    assert FIELDNAMES == expected


# ─── Tests load_config ─────────────────────────────────────────────────────────

def test_load_config_returns_dict(tmp_path):
    """load_config() charge un config.yaml valide et retourne un dict."""
    from utils import load_config
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "music_folder: /music\n"
        "confidence_threshold: 85\n"
        "duration_tolerance: 10\n"
        "supported_extensions: [.mp3]\n"
        "filter_live: true\n"
        "api_delay: 1.0\n"
        "low_confidence_threshold: 70\n"
        "rate_limit_sleep: 1.0\n",
        encoding="utf-8"
    )
    config = load_config(str(config_file))
    assert isinstance(config, dict)
    assert config["music_folder"] == "/music"
    assert config["confidence_threshold"] == 85


def test_load_config_exits_on_missing_key(tmp_path):
    """load_config() appelle sys.exit() si une clé requise manque."""
    from utils import load_config
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "music_folder: /music\n"
        "confidence_threshold: 85\n",
        encoding="utf-8"
    )
    with pytest.raises(SystemExit):
        load_config(str(config_file))


# ─── Tests read_csv ────────────────────────────────────────────────────────────

def test_read_csv_returns_empty_list_if_file_missing():
    from utils import read_csv
    result = read_csv("/nonexistent/path/file.csv")
    assert result == []


def test_read_csv_returns_list_of_dicts(tmp_path):
    """read_csv() lit un fichier CSV encodé UTF-8 BOM correctement."""
    from utils import read_csv, FIELDNAMES
    csv_file = tmp_path / "test.csv"
    with open(csv_file, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerow({
            "filepath": "/music/song.mp3", "artist": "Artist", "title": "Title",
            "album": "Album", "duration": "240", "status": "pending",
            "yt_video_id": "", "yt_url": "", "yt_score": "", "error_message": ""
        })
    rows = read_csv(str(csv_file))
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["artist"] == "Artist"
    assert rows[0]["status"] == "pending"


# ─── Tests write_csv ───────────────────────────────────────────────────────────

def test_write_csv_creates_file(tmp_path):
    """write_csv() crée un fichier CSV avec encodage UTF-8 BOM."""
    from utils import write_csv, FIELDNAMES
    csv_file = str(tmp_path / "output.csv")
    rows = [{
        "filepath": "/music/song.mp3", "artist": "Test Artist", "title": "Test Song",
        "album": "Test Album", "duration": "180", "status": "pending",
        "yt_video_id": "", "yt_url": "", "yt_score": "", "error_message": ""
    }]
    write_csv(csv_file, rows)
    assert os.path.exists(csv_file)


def test_write_csv_roundtrip(tmp_path):
    """write_csv() + read_csv() préserve les données (cycle idempotent)."""
    from utils import write_csv, read_csv, FIELDNAMES
    csv_file = str(tmp_path / "output.csv")
    original = [{
        "filepath": "/music/chanson.flac", "artist": "Artiste", "title": "Chanson",
        "album": "Album", "duration": "210.5", "status": "imported",
        "yt_video_id": "abc123", "yt_url": "https://music.youtube.com/watch?v=abc123",
        "yt_score": "92", "error_message": ""
    }]
    write_csv(csv_file, original)
    result = read_csv(csv_file)
    assert len(result) == 1
    assert result[0]["artist"] == "Artiste"
    assert result[0]["yt_video_id"] == "abc123"


def test_write_csv_no_tmp_file_after_write(tmp_path):
    """Aucun fichier .tmp ne reste après écriture atomique."""
    from utils import write_csv, FIELDNAMES
    csv_file = str(tmp_path / "output.csv")
    write_csv(csv_file, [])
    assert not os.path.exists(csv_file + ".tmp")


# ─── Tests clean_title ─────────────────────────────────────────────────────────

def test_clean_title_removes_remaster():
    from utils import clean_title
    assert clean_title("Song (Remastered 2021)") == "Song"


def test_clean_title_removes_live():
    from utils import clean_title
    assert clean_title("Song (Live at Wembley)") == "Song"


def test_clean_title_removes_feat():
    from utils import clean_title
    result = clean_title("Song feat. Other Artist")
    assert "feat" not in result.lower()


def test_clean_title_removes_radio_edit():
    from utils import clean_title
    result = clean_title("Song - Radio Edit")
    assert "radio edit" not in result.lower()


def test_clean_title_preserves_base_title():
    from utils import clean_title
    assert clean_title("Simple Song") == "Simple Song"


def test_clean_title_strips_whitespace():
    from utils import clean_title
    result = clean_title("  Song  ")
    assert result == "Song"


# ─── Tests score_match ─────────────────────────────────────────────────────────

def test_score_match_returns_int():
    from utils import score_match
    result = score_match("Artist", "Song", "Artist", "Song")
    assert isinstance(result, int)


def test_score_match_perfect_match_is_100():
    from utils import score_match
    score = score_match("Daft Punk", "Get Lucky", "Daft Punk", "Get Lucky")
    assert score == 100


def test_score_match_different_returns_low_score():
    from utils import score_match
    score = score_match("Artist A", "Song A", "Artist B", "Song B")
    assert score < 100


def test_score_match_in_range():
    from utils import score_match
    score = score_match("Beatles", "Hey Jude", "Rolling Stones", "Paint It Black")
    assert 0 <= score <= 100


def test_score_match_case_insensitive():
    from utils import score_match
    score1 = score_match("Artist", "Song", "ARTIST", "SONG")
    score2 = score_match("Artist", "Song", "artist", "song")
    assert score1 == score2 == 100


# ─── Tests d'import des scripts squelettes (AC3) ──────────────────────────────

def test_scanner_imports_without_error():
    """scanner.py doit s'importer sans erreur d'import (AC3)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("scanner", "scanner.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_matcher_imports_without_error():
    """matcher.py doit s'importer sans erreur d'import (AC3)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("matcher", "matcher.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


def test_importer_imports_without_error():
    """importer.py doit s'importer sans erreur d'import (AC3)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("importer", "importer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert hasattr(module, "main")


# ─── Tests Story 1.2 : Validation de type/valeur dans load_config() ──────────

from pathlib import Path


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
    from utils import load_config
    path = tmp_path / "config.yaml"
    path.write_text("music_folder: /test\nconfidence_threshold: 85\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_config(str(path))
    assert "duration_tolerance" in str(exc.value)


def test_load_config_confidence_threshold_out_of_range(tmp_path):
    """AC4 — confidence_threshold hors plage (150) → SystemExit."""
    from utils import load_config
    path = _write_valid_config(tmp_path, {"confidence_threshold": 150})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "confidence_threshold" in str(exc.value)


def test_load_config_empty_extensions(tmp_path):
    """AC4 — supported_extensions liste vide → SystemExit."""
    from utils import load_config
    path = _write_valid_config(tmp_path, {"supported_extensions": []})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "supported_extensions" in str(exc.value)


def test_load_config_filter_live_not_bool(tmp_path):
    """AC4 — filter_live non-booléen (entier) → SystemExit."""
    from utils import load_config
    # Note : yaml.dump encode True en 'true' — passer un int pour simuler une valeur invalide
    path = _write_valid_config(tmp_path, {"filter_live": 1})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "filter_live" in str(exc.value)


def test_load_config_low_confidence_greater_than_confidence(tmp_path):
    """AC4 — low_confidence_threshold >= confidence_threshold → SystemExit."""
    from utils import load_config
    path = _write_valid_config(tmp_path, {
        "confidence_threshold": 70,
        "low_confidence_threshold": 85
    })
    with pytest.raises(SystemExit):
        load_config(path)


def test_load_config_empty_music_folder(tmp_path):
    """AC4 — music_folder chaîne vide → SystemExit."""
    from utils import load_config
    path = _write_valid_config(tmp_path, {"music_folder": ""})
    with pytest.raises(SystemExit) as exc:
        load_config(path)
    assert "music_folder" in str(exc.value)


def test_load_config_valid_config_passes(tmp_path):
    """Vérification positive — config valide complète → aucune erreur."""
    from utils import load_config
    path = _write_valid_config(tmp_path)
    config = load_config(path)
    assert config["confidence_threshold"] == 85
    assert config["low_confidence_threshold"] == 70
    assert config["filter_live"] is True
    assert len(config["supported_extensions"]) == 2


# ─── Tests Story 1.4 : Validation du browser.json au démarrage ──────────────

def test_validate_browser_json_missing(tmp_path):
    """AC1 — browser.json manquant → sys.exit avec message explicite."""
    from utils import validate_browser_json
    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            validate_browser_json()
        assert "browser.json manquant" in str(exc.value)
    finally:
        os.chdir(cwd)


def test_validate_browser_json_invalid_json(tmp_path):
    """AC2 — browser.json malformé (JSON invalide) → sys.exit."""
    from utils import validate_browser_json
    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        browser_file = tmp_path / "browser.json"
        browser_file.write_text("{invalid json}", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            validate_browser_json()
        assert "malformé" in str(exc.value) or "ERROR" in str(exc.value)
    finally:
        os.chdir(cwd)


def test_validate_browser_json_expired(tmp_path, monkeypatch):
    """AC2 — browser.json valide mais authentification expirée → sys.exit."""
    from utils import validate_browser_json
    import os
    import sys
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        browser_file = tmp_path / "browser.json"
        browser_file.write_text('{"test": "valid json"}', encoding="utf-8")

        # Mock ytmusicapi.YTMusic to raise an exception
        class MockYTMusic:
            def __init__(self, auth=None):
                raise Exception("Auth failed")

        import sys
        import types
        mock_module = types.ModuleType("ytmusicapi")
        mock_module.YTMusic = MockYTMusic
        monkeypatch.setitem(sys.modules, "ytmusicapi", mock_module)

        with pytest.raises(SystemExit) as exc:
            validate_browser_json()
        assert "expiré" in str(exc.value) or "invalide" in str(exc.value)
    finally:
        os.chdir(cwd)


def test_validate_browser_json_valid_returns_none(tmp_path, monkeypatch):
    """AC3 — browser.json valide et authentification réussit → retourne None silencieusement."""
    from utils import validate_browser_json
    import os
    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        browser_file = tmp_path / "browser.json"
        browser_file.write_text('{"test": "valid json"}', encoding="utf-8")

        # Mock YTMusic to succeed
        class MockYTMusic:
            def __init__(self, auth=None):
                pass
            def get_library_songs(self, limit=1):
                return []

        import sys
        import types
        mock_module = types.ModuleType("ytmusicapi")
        mock_module.YTMusic = MockYTMusic
        monkeypatch.setitem(sys.modules, "ytmusicapi", mock_module)

        result = validate_browser_json()
        assert result is None
    finally:
        os.chdir(cwd)


# ─── Tests Story 1.4 : Intégration dans matcher.py et importer.py ──────────

def test_matcher_calls_validate_browser_json(tmp_path, monkeypatch):
    """Vérification que matcher.py appelle validate_browser_json() au démarrage."""
    import os
    import importlib.util

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Créer un config.yaml valide
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "music_folder: /music\n"
            "confidence_threshold: 85\n"
            "duration_tolerance: 10\n"
            "supported_extensions: [.mp3]\n"
            "filter_live: true\n"
            "api_delay: 1.0\n"
            "low_confidence_threshold: 70\n"
            "rate_limit_sleep: 1.0\n",
            encoding="utf-8"
        )

        # Créer browser.json
        browser_file = tmp_path / "browser.json"
        browser_file.write_text('{"test": "valid json"}', encoding="utf-8")

        # Mock YTMusic to succeed
        class MockYTMusic:
            def __init__(self, auth=None):
                pass
            def get_library_songs(self, limit=1):
                return []

        import sys
        import types
        mock_module = types.ModuleType("ytmusicapi")
        mock_module.YTMusic = MockYTMusic
        monkeypatch.setitem(sys.modules, "ytmusicapi", mock_module)

        # Import matcher et appeler main
        matcher_path = os.path.join(cwd, "matcher.py")
        spec = importlib.util.spec_from_file_location("matcher", matcher_path)
        matcher_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(matcher_module)

        # Si on arrive ici sans SystemExit, c'est que validate_browser_json a réussi
        matcher_module.main()

    finally:
        os.chdir(cwd)


def test_importer_calls_validate_browser_json(tmp_path, monkeypatch):
    """Vérification que importer.py appelle validate_browser_json() au démarrage."""
    import os
    import importlib.util

    cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Créer un config.yaml valide
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "music_folder: /music\n"
            "confidence_threshold: 85\n"
            "duration_tolerance: 10\n"
            "supported_extensions: [.mp3]\n"
            "filter_live: true\n"
            "api_delay: 1.0\n"
            "low_confidence_threshold: 70\n"
            "rate_limit_sleep: 1.0\n",
            encoding="utf-8"
        )

        # Créer browser.json
        browser_file = tmp_path / "browser.json"
        browser_file.write_text('{"test": "valid json"}', encoding="utf-8")

        # Mock YTMusic to succeed
        class MockYTMusic:
            def __init__(self, auth=None):
                pass
            def get_library_songs(self, limit=1):
                return []

        import sys
        import types
        mock_module = types.ModuleType("ytmusicapi")
        mock_module.YTMusic = MockYTMusic
        monkeypatch.setitem(sys.modules, "ytmusicapi", mock_module)

        # Import importer et appeler main
        importer_path = os.path.join(cwd, "importer.py")
        spec = importlib.util.spec_from_file_location("importer", importer_path)
        importer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(importer_module)

        # Si on arrive ici sans SystemExit, c'est que validate_browser_json a réussi
        importer_module.main()

    finally:
        os.chdir(cwd)


# ─── Tests Story 2.3 : Détection et marquage des doublons ─────────────────────

def test_normalize_key_basic():
    """AC1 — normalize_key() retourne une clé en minuscules."""
    from utils import normalize_key
    result = normalize_key("The Beatles", "Let It Be")
    assert result == "the beatles|let it be"


def test_normalize_key_case_insensitive():
    """AC1 — normalize_key() est insensible à la casse (minuscules appliquées)."""
    from utils import normalize_key
    result1 = normalize_key("The Beatles", "Let It Be")
    result2 = normalize_key("the beatles", "let it be")
    result3 = normalize_key("THE BEATLES", "LET IT BE")
    assert result1 == result2 == result3 == "the beatles|let it be"


def test_normalize_key_strips_whitespace():
    """AC1 — normalize_key() supprime les espaces au début/fin."""
    from utils import normalize_key
    result = normalize_key("  The Beatles  ", "  Let It Be  ")
    assert result == "the beatles|let it be"


def test_normalize_key_empty_artist():
    """AC1 — normalize_key() accepte artiste vide (avant le |)."""
    from utils import normalize_key
    result = normalize_key("", "Untitled")
    assert result == "|untitled"


def test_normalize_key_none_artist():
    """AC1 — normalize_key() traite None comme chaîne vide."""
    from utils import normalize_key
    result = normalize_key(None, "Untitled")
    assert result == "|untitled"


def test_normalize_key_none_title():
    """AC1 — normalize_key() traite None titre comme chaîne vide."""
    from utils import normalize_key
    result = normalize_key("Artist", None)
    assert result == "artist|"


def test_normalize_key_both_none():
    """AC1 — normalize_key() retourne '|' si artist et title sont None."""
    from utils import normalize_key
    result = normalize_key(None, None)
    assert result == "|"


def test_normalize_key_special_characters():
    """AC1 — normalize_key() préserve les caractères spéciaux mais normalise la casse."""
    from utils import normalize_key
    result = normalize_key("Künstler", "Lied — Spezial")
    assert result == "künstler|lied — spezial"


def test_normalize_key_separator_consistency():
    """AC1 — normalize_key() utilise toujours '|' comme séparateur."""
    from utils import normalize_key
    result = normalize_key("Artist A", "Title B")
    assert "|" in result
    assert result.count("|") == 1
    artist_part, title_part = result.split("|")
    assert artist_part == "artist a"
    assert title_part == "title b"
