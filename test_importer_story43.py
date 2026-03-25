"""
Tests pour Story 4.3 : Persistance CSV et reprise automatique de l'importer

Couvre les Acceptance Criteria :
- AC1 : Persistance CSV immédiate après chaque morceau
- AC2 : Reprise automatique après interruption
- AC3 : Zéro doublon en cas d'interruption + reprise
- AC4 : Garantie finale : 100% des lignes avec statut explicite
"""

import csv
import os
import tempfile
from pathlib import Path
from unittest import mock

from utils import (
    read_csv, write_csv,
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
    STATUS_DUPLICATE, STATUS_MANUAL_REVIEW, STATUS_LOW_CONFIDENCE,
    STATUS_ERROR_READ, FIELDNAMES
)
from importer import _should_import_track, _ensure_all_statuses_assigned


class TestStory43_AC1_PersistenceCSV:
    """AC1 : Persistance CSV immédiate après chaque morceau"""

    def test_ac1_write_csv_atomique(self):
        """Vérifier que write_csv utilise temp file + rename pour atomicité"""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")
            rows = [
                {"filepath": "song1.mp3", "status": "pending", "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": "imported", "yt_video_id": "def456"},
            ]

            write_csv(csv_path, rows, FIELDNAMES)

            # Vérifier que le fichier existe et est accessible
            assert Path(csv_path).exists(), "CSV non écrit"
            assert not Path(csv_path + ".tmp").exists(), "Fichier tmp non nettoyé"

            # Vérifier le contenu
            read_rows = read_csv(csv_path)
            assert len(read_rows) == 2
            assert read_rows[0]["filepath"] == "song1.mp3"

    def test_ac1_csv_corruption_avoidance(self):
        """
        Simuler un crash durant l'écriture.
        Vérifier que le fichier CSV reste intact.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            # État initial
            initial_rows = [
                {"filepath": "song1.mp3", "status": "imported", "yt_video_id": "abc123"},
            ]
            write_csv(csv_path, initial_rows, FIELDNAMES)

            # Simuler une exception lors d'une écriture ultérieure
            problematic_rows = [
                {"filepath": "song1.mp3", "status": "imported", "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": "imported", "yt_video_id": "def456"},
            ]

            try:
                with mock.patch("os.replace", side_effect=OSError("Simulated write failure")):
                    write_csv(csv_path, problematic_rows, FIELDNAMES)
            except OSError:
                pass  # Attendu

            # Vérifier que le CSV initial n'est pas corrompu
            read_rows = read_csv(csv_path)
            assert len(read_rows) == 1, "CSV corrompu lors de la tentative d'écriture"
            assert read_rows[0]["filepath"] == "song1.mp3"

    def test_ac1_immediate_persistence_in_loop(self):
        """
        Simuler une boucle d'import avec persistance après chaque morceau.
        Vérifier que le CSV est à jour après chaque itération.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            # État initial : 3 morceaux à traiter
            rows = [
                {"filepath": "song1.mp3", "status": STATUS_PENDING, "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": STATUS_PENDING, "yt_video_id": "def456"},
                {"filepath": "song3.mp3", "status": STATUS_PENDING, "yt_video_id": "ghi789"},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Simuler boucle : traiter chaque morceau et persister
            for i, row in enumerate(rows):
                row["status"] = STATUS_IMPORTED
                write_csv(csv_path, rows, FIELDNAMES)  # AC1 : persistance immédiate

                # Vérifier que le CSV reflète l'état actuel
                disk_rows = read_csv(csv_path)
                assert len(disk_rows) == 3
                # Vérifier que les i+1 premiers morceaux sont importés
                for j in range(i + 1):
                    assert disk_rows[j]["status"] == STATUS_IMPORTED
                # Les restants sont encore pending
                for j in range(i + 1, 3):
                    assert disk_rows[j]["status"] == STATUS_PENDING


class TestStory43_AC2_AutomaticResume:
    """AC2 : Reprise automatique après interruption"""

    def test_ac2_resume_after_interruption(self):
        """
        Scénario : Import interrompu à mi-parcours.
        Après relance, seules les lignes pending + yt_video_id doivent être retraitées.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            # État après interruption : morceaux 1-2 importés, 3+ pending
            rows = [
                {"filepath": "song1.mp3", "status": STATUS_IMPORTED, "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": STATUS_IMPORTED, "yt_video_id": "def456"},
                {"filepath": "song3.mp3", "status": STATUS_PENDING, "yt_video_id": "ghi789"},
                {"filepath": "song4.mp3", "status": STATUS_PENDING, "yt_video_id": "jkl012"},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Relance : lire CSV et filtrer seules les lignes à traiter
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]

            # AC2 : Seuls les morceaux 3-4 doivent être retraitées (pending + yt_video_id)
            assert len(rows_to_import) == 2
            assert rows_to_import[0]["filepath"] == "song3.mp3"
            assert rows_to_import[1]["filepath"] == "song4.mp3"

    def test_ac2_finalized_lines_never_touched(self):
        """
        AC2 : Les lignes finalisées (imported, failed, duplicate, etc.)
        doivent être complètement ignorées — aucune modification.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            finalized_statuses = [
                STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
                STATUS_DUPLICATE, STATUS_MANUAL_REVIEW, STATUS_LOW_CONFIDENCE,
                STATUS_ERROR_READ
            ]

            rows = [
                {
                    "filepath": f"song_{status}.mp3",
                    "status": status,
                    "yt_video_id": "vid123"
                }
                for status in finalized_statuses
            ]
            rows.append({
                "filepath": "song_pending.mp3",
                "status": STATUS_PENDING,
                "yt_video_id": "vid999"
            })

            write_csv(csv_path, rows, FIELDNAMES)

            # Vérifier que seule la ligne pending est retournée
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]

            assert len(rows_to_import) == 1
            assert rows_to_import[0]["filepath"] == "song_pending.mp3"

    def test_ac2_pending_without_yt_video_id_skipped(self):
        """
        AC2 : Une ligne pending SANS yt_video_id doit être ignorée.
        (Cela signifie qu'elle n'a pas encore été matchée par le matcher)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            rows = [
                {"filepath": "song1.mp3", "status": STATUS_PENDING, "yt_video_id": ""},
                {"filepath": "song2.mp3", "status": STATUS_PENDING, "yt_video_id": "abc123"},
                {"filepath": "song3.mp3", "status": STATUS_PENDING, "yt_video_id": None},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]

            # Seule la ligne 2 (avec yt_video_id) doit être retraitée
            assert len(rows_to_import) == 1
            assert rows_to_import[0]["filepath"] == "song2.mp3"


class TestStory43_AC3_ZeroDuplication:
    """AC3 : Zéro doublon en cas d'interruption + reprise"""

    def test_ac3_imported_line_never_retouched(self):
        """
        Scénario : Une ligne marquée 'imported' après interruption + reprise.
        Elle ne doit JAMAIS être retouched (vérification idempotence).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            rows = [
                {"filepath": "song1.mp3", "status": STATUS_IMPORTED, "yt_video_id": "abc123"},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Relancer l'import
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]

            # Vérifier qu'aucun appel API ne sera effectué sur cette ligne
            assert len(rows_to_import) == 0, "Ligne importée ne doit pas être retraitée"

    def test_ac3_multiple_runs_no_duplication(self):
        """
        Scénario : Trois exécutions successives du importer.
        Vérifier que les lignes importées ne sont jamais retouchées.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            rows = [
                {"filepath": "song1.mp3", "status": STATUS_PENDING, "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": STATUS_PENDING, "yt_video_id": "def456"},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Run 1 : Traiter song1
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]
            assert len(rows_to_import) == 2

            disk_rows[0]["status"] = STATUS_IMPORTED
            write_csv(csv_path, disk_rows, FIELDNAMES)

            # Run 2 : Relance - seule song2 doit être retraitée
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]
            assert len(rows_to_import) == 1
            assert rows_to_import[0]["filepath"] == "song2.mp3"

            disk_rows[1]["status"] = STATUS_IMPORTED
            write_csv(csv_path, disk_rows, FIELDNAMES)

            # Run 3 : Relance - aucun morceau à traiter
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]
            assert len(rows_to_import) == 0


class TestStory43_AC4_StatusCoverage:
    """AC4 : Garantie finale : 100% des lignes avec statut explicite"""

    def test_ac4_all_lines_have_status(self):
        """
        Vérifier qu'aucune ligne n'a un statut vide ou manquant.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            rows = [
                {"filepath": "song1.mp3", "status": STATUS_IMPORTED, "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": STATUS_FAILED, "yt_video_id": "def456"},
                {"filepath": "song3.mp3", "status": STATUS_DUPLICATE, "yt_video_id": ""},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            disk_rows = read_csv(csv_path)

            # Appeler la validation AC4
            _ensure_all_statuses_assigned(disk_rows)  # Ne doit pas lever d'exception

            # Vérifier manuellement
            for row in disk_rows:
                assert row.get("status", "").strip(), f"Ligne sans statut : {row}"

    def test_ac4_empty_status_warning(self, capsys):
        """
        Vérifier que _ensure_all_statuses_assigned affiche un avertissement
        si une ligne a un statut vide.
        """
        rows = [
            {"filepath": "song1.mp3", "status": STATUS_IMPORTED, "yt_video_id": "abc123"},
            {"filepath": "song2.mp3", "status": "", "yt_video_id": "def456"},  # Status vide
            {"filepath": "song3.mp3", "status": STATUS_FAILED, "yt_video_id": "ghi789"},
        ]

        _ensure_all_statuses_assigned(rows)
        captured = capsys.readouterr()

        assert "ATTENTION" in captured.out
        assert "sans statut" in captured.out
        assert "song2.mp3" in captured.out

    def test_ac4_all_pending_lines_assigned_status_after_import(self):
        """
        Scénario : Boucle d'import complète.
        Vérifier qu'aucune ligne ne reste pending à la fin.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            rows = [
                {"filepath": "song1.mp3", "status": STATUS_PENDING, "yt_video_id": "abc123"},
                {"filepath": "song2.mp3", "status": STATUS_PENDING, "yt_video_id": "def456"},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Simuler boucle d'import
            disk_rows = read_csv(csv_path)
            for row in disk_rows:
                if row.get("status") == STATUS_PENDING and row.get("yt_video_id"):
                    row["status"] = STATUS_IMPORTED
            write_csv(csv_path, disk_rows, FIELDNAMES)

            # Vérifier AC4
            final_rows = read_csv(csv_path)
            _ensure_all_statuses_assigned(final_rows)

            # Vérifier qu'aucune ligne n'est plus pending
            for row in final_rows:
                assert row.get("status") != STATUS_PENDING or not row.get("yt_video_id")


class TestStory43_IntegrationScenarios:
    """Tests d'intégration scénarios réalistes"""

    def test_scenario_interruption_and_recovery(self):
        """
        Scénario réaliste : Import de 5 morceaux interrompu à 3,
        puis relancé et complété.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            # État initial : 5 morceaux
            rows = [
                {"filepath": f"song{i}.mp3", "status": STATUS_PENDING, "yt_video_id": f"vid{i:03d}"}
                for i in range(1, 6)
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Run 1 : Traiter morceaux 1-3, puis interruption
            disk_rows = read_csv(csv_path)
            for i in range(3):
                disk_rows[i]["status"] = STATUS_IMPORTED
                write_csv(csv_path, disk_rows, FIELDNAMES)

            # Simuler interruption ici (Ctrl+C)
            state_after_interrupt = read_csv(csv_path)
            assert len([r for r in state_after_interrupt if r.get("status") == STATUS_IMPORTED]) == 3

            # Run 2 : Relance - continuer avec morceaux 4-5
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]
            assert len(rows_to_import) == 2  # Morceaux 4-5

            # Finir le import
            for row in rows_to_import:
                row["status"] = STATUS_IMPORTED

            # Mettre à jour le CSV avec les modifications
            for i, row in enumerate(disk_rows):
                if _should_import_track(row):
                    row["status"] = STATUS_IMPORTED
            write_csv(csv_path, disk_rows, FIELDNAMES)

            # Vérifier état final : 0 morceau pending avec yt_video_id
            final_rows = read_csv(csv_path)
            rows_remaining = [r for r in final_rows if _should_import_track(r)]
            assert len(rows_remaining) == 0

            # AC4 : tous les morceaux ont un statut
            _ensure_all_statuses_assigned(final_rows)
            for row in final_rows:
                assert row.get("status") != STATUS_PENDING

    def test_scenario_mixed_statuses_resume(self):
        """
        Scénario : CSV avec mélange de statuts.
        Reprise ne doit affecter que les lignes pending + yt_video_id.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = os.path.join(tmpdir, "test.csv")

            rows = [
                {"filepath": "song_imported.mp3", "status": STATUS_IMPORTED, "yt_video_id": "abc123"},
                {"filepath": "song_failed.mp3", "status": STATUS_FAILED, "yt_video_id": "def456"},
                {"filepath": "song_low_conf.mp3", "status": STATUS_LOW_CONFIDENCE, "yt_video_id": "ghi789"},
                {"filepath": "song_pending_with_id.mp3", "status": STATUS_PENDING, "yt_video_id": "jkl012"},
                {"filepath": "song_pending_no_id.mp3", "status": STATUS_PENDING, "yt_video_id": ""},
            ]
            write_csv(csv_path, rows, FIELDNAMES)

            # Reprise
            disk_rows = read_csv(csv_path)
            rows_to_import = [r for r in disk_rows if _should_import_track(r)]

            # Seul song_pending_with_id doit être retraité
            assert len(rows_to_import) == 1
            assert rows_to_import[0]["filepath"] == "song_pending_with_id.mp3"

            # Les autres lignes doivent garder leur statut
            original_statuses = {r["filepath"]: r["status"] for r in rows}
            for row in disk_rows:
                if row["filepath"] != "song_pending_with_id.mp3":
                    assert row["status"] == original_statuses[row["filepath"]]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
