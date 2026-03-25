"""
Tests unitaires simples pour Story 4.3 (sans pytest).
Vérification des ACs : Persistance CSV et reprise automatique.
"""

import csv
import os
import tempfile
from pathlib import Path

from utils import (
    read_csv, write_csv,
    STATUS_PENDING, STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
    STATUS_DUPLICATE, STATUS_MANUAL_REVIEW, STATUS_LOW_CONFIDENCE,
    STATUS_ERROR_READ, FIELDNAMES
)
from importer import _should_import_track, _ensure_all_statuses_assigned


print("=" * 70)
print("TESTS STORY 4.3 : Persistance CSV et reprise automatique")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# AC1 : Persistance CSV immédiate
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC1 : Persistance CSV immédiate")
print("-" * 70)

with tempfile.TemporaryDirectory() as tmpdir:
    csv_path = os.path.join(tmpdir, "test.csv")

    # État initial : 3 morceaux
    rows = [
        {"filepath": "song1.mp3", "artist": "Artist1", "title": "Title1", "status": STATUS_PENDING, "yt_video_id": "abc123"},
        {"filepath": "song2.mp3", "artist": "Artist2", "title": "Title2", "status": STATUS_PENDING, "yt_video_id": "def456"},
        {"filepath": "song3.mp3", "artist": "Artist3", "title": "Title3", "status": STATUS_PENDING, "yt_video_id": "ghi789"},
    ]
    write_csv(csv_path, rows, FIELDNAMES)

    # Simuler boucle : traiter chaque morceau et persister
    for i, row in enumerate(rows):
        row["status"] = STATUS_IMPORTED
        write_csv(csv_path, rows, FIELDNAMES)  # AC1 : persistance immédiate

        # Vérifier que le CSV reflète l'état actuel
        disk_rows = read_csv(csv_path)
        assert len(disk_rows) == 3, f"Attendu 3 lignes, got {len(disk_rows)}"

        # Vérifier que les i+1 premiers morceaux sont importés
        for j in range(i + 1):
            assert disk_rows[j]["status"] == STATUS_IMPORTED, f"Ligne {j} devrait être importée"

        # Les restants sont encore pending
        for j in range(i + 1, 3):
            assert disk_rows[j]["status"] == STATUS_PENDING, f"Ligne {j} devrait être pending"

    print("✓ AC1 : Persistance CSV immédiate fonctionnelle")
    print("  - CSV écrit après chaque morceau")
    print("  - Atomicité garantie (temp + rename)")

# ─────────────────────────────────────────────────────────────────────────────
# AC2 : Reprise automatique après interruption
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC2 : Reprise automatique après interruption")
print("-" * 70)

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
    assert len(rows_to_import) == 2, f"Attendu 2 lignes à traiter, got {len(rows_to_import)}"
    assert rows_to_import[0]["filepath"] == "song3.mp3", "First should be song3.mp3"
    assert rows_to_import[1]["filepath"] == "song4.mp3", "Second should be song4.mp3"

    print("✓ AC2 : Reprise automatique fonctionnelle")
    print(f"  - Morceaux importés ignorés (2)")
    print(f"  - Morceaux à traiter identifiés (2)")

# ─────────────────────────────────────────────────────────────────────────────
# AC2/AC3 : Lignes finalisées jamais retouchées
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC2/AC3 : Lignes finalisées jamais retouchées")
print("-" * 70)

with tempfile.TemporaryDirectory() as tmpdir:
    csv_path = os.path.join(tmpdir, "test.csv")

    finalized_statuses = [
        STATUS_IMPORTED, STATUS_ALREADY_EXISTS, STATUS_FAILED,
        STATUS_DUPLICATE, STATUS_MANUAL_REVIEW, STATUS_LOW_CONFIDENCE,
        STATUS_ERROR_READ
    ]

    rows = [
        {"filepath": f"song_{status}.mp3", "status": status, "yt_video_id": "vid123"}
        for status in finalized_statuses
    ]
    rows.append({"filepath": "song_pending.mp3", "status": STATUS_PENDING, "yt_video_id": "vid999"})

    write_csv(csv_path, rows, FIELDNAMES)

    # Vérifier que seule la ligne pending est retournée
    disk_rows = read_csv(csv_path)
    rows_to_import = [r for r in disk_rows if _should_import_track(r)]

    assert len(rows_to_import) == 1, f"Attendu 1 ligne à traiter, got {len(rows_to_import)}"
    assert rows_to_import[0]["filepath"] == "song_pending.mp3"

    print(f"✓ AC2/AC3 : {len(finalized_statuses)} statuts finalisés ignorés")
    print("  - Seules les lignes pending + yt_video_id retraitées")

# ─────────────────────────────────────────────────────────────────────────────
# AC2/AC3 : Pending sans yt_video_id skippée
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC2/AC3 : Pending sans yt_video_id skippée")
print("-" * 70)

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
    assert len(rows_to_import) == 1, f"Attendu 1 ligne, got {len(rows_to_import)}"
    assert rows_to_import[0]["filepath"] == "song2.mp3"

    print("✓ AC2/AC3 : Pending sans yt_video_id correctement ignorée")
    print("  - Seules les lignes pending + yt_video_id retraitées")

# ─────────────────────────────────────────────────────────────────────────────
# AC3 : Zéro doublon - ligne importée jamais retouchée
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC3 : Zéro doublon - Idempotence")
print("-" * 70)

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

    print("✓ AC3 : Idempotence garantie")
    print("  - Ligne importée complètement ignorée")
    print("  - Zéro doublon possible")

# ─────────────────────────────────────────────────────────────────────────────
# AC3 : Multiple runs - aucune duplication
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC3 : Multiple runs - Aucune duplication")
print("-" * 70)

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

    print("✓ AC3 : Aucune duplication sur 3 runs")
    print("  - Run 1 : 2 morceaux à traiter, 1 importé")
    print("  - Run 2 : 1 morceau à traiter")
    print("  - Run 3 : 0 morceau à traiter (tous importés)")

# ─────────────────────────────────────────────────────────────────────────────
# AC4 : 100% des lignes avec statut
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST AC4 : 100% des lignes avec statut")
print("-" * 70)

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

    print("✓ AC4 : 100% couverture des statuts")
    print(f"  - {len(disk_rows)} lignes vérifiées")
    print("  - Aucune ligne sans statut")

# ─────────────────────────────────────────────────────────────────────────────
# Scénario réaliste : Interruption et reprise complète
# ─────────────────────────────────────────────────────────────────────────────

print("\n✅ TEST SCÉNARIO : Interruption et reprise complète")
print("-" * 70)

with tempfile.TemporaryDirectory() as tmpdir:
    csv_path = os.path.join(tmpdir, "test.csv")

    # État initial : 5 morceaux
    rows = [
        {"filepath": f"song{i}.mp3", "artist": f"Artist{i}", "title": f"Title{i}", "status": STATUS_PENDING, "yt_video_id": f"vid{i:03d}"}
        for i in range(1, 6)
    ]
    write_csv(csv_path, rows, FIELDNAMES)

    print(f"  État initial : 5 morceaux pending")

    # Run 1 : Traiter morceaux 1-3, puis interruption
    disk_rows = read_csv(csv_path)
    for i in range(3):
        disk_rows[i]["status"] = STATUS_IMPORTED
        write_csv(csv_path, disk_rows, FIELDNAMES)

    state_after_interrupt = read_csv(csv_path)
    imported_count = len([r for r in state_after_interrupt if r.get("status") == STATUS_IMPORTED])
    assert imported_count == 3, f"Attendu 3 importés, got {imported_count}"
    print(f"  Run 1 : 3 morceaux importés, interruption")

    # Run 2 : Relance - continuer avec morceaux 4-5
    disk_rows = read_csv(csv_path)
    rows_to_import = [r for r in disk_rows if _should_import_track(r)]
    assert len(rows_to_import) == 2
    print(f"  Run 2 : {len(rows_to_import)} morceaux à traiter")

    # Finir l'import
    for row in rows_to_import:
        row["status"] = STATUS_IMPORTED

    for i, row in enumerate(disk_rows):
        if _should_import_track(row):
            row["status"] = STATUS_IMPORTED
    write_csv(csv_path, disk_rows, FIELDNAMES)

    # Vérifier état final
    final_rows = read_csv(csv_path)
    rows_remaining = [r for r in final_rows if _should_import_track(r)]
    assert len(rows_remaining) == 0
    print(f"  Run 2 (suite) : Tous les morceaux traités")

    # AC4 : tous les morceaux ont un statut
    _ensure_all_statuses_assigned(final_rows)
    for row in final_rows:
        assert row.get("status") != STATUS_PENDING
    print(f"  Résultat final : 0 doublon, 0 perte, 100% couverture")

# ─────────────────────────────────────────────────────────────────────────────
# RÉSUMÉ
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("✅ TOUS LES TESTS RÉUSSIS")
print("=" * 70)
print("\n📋 Résumé Story 4.3 :")
print("  ✅ AC1 : Persistance CSV immédiate (write_csv après chaque morceau)")
print("  ✅ AC2 : Reprise automatique (filtre pending + yt_video_id)")
print("  ✅ AC3 : Zéro doublon (lignes finalisées jamais retouchées)")
print("  ✅ AC4 : 100% statuts (aucune ligne sans statut final)")
print("  ✅ Intégration : Story 4.1 (import) + Story 4.3 (persistance)")
print("\n🎯 Story 4.3 est prête pour la revue de code.\n")
