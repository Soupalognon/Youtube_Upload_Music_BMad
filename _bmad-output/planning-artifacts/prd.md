---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
workflowComplete: true
completedAt: '2026-02-22'
inputDocuments:
  - '_bmad-output/brainstorming/brainstorming-session-2026-02-22.md'
workflowType: 'prd'
briefCount: 0
researchCount: 0
brainstormingCount: 1
projectDocsCount: 0
classification:
  projectType: 'cli_tool'
  domain: 'general'
  complexity: 'low'
  projectContext: 'greenfield'
---

# Product Requirements Document - Youtube_upload_playlists

**Auteur :** Gabriel
**Date :** 2026-02-22
**Type :** Outil CLI Python local | Domaine : Général | Complexité : Faible | Greenfield

---

## Executive Summary

`Youtube_upload_playlists` est un outil Python local qui migre une bibliothèque musicale personnelle (120 Go, ~50 000 morceaux) vers YouTube Music en matchant chaque morceau local contre le catalogue YouTube Music et en l'ajoutant à la bibliothèque utilisateur — sans upload de fichiers, sans coût de stockage supplémentaire.

**Utilisateur cible :** Propriétaire d'une large bibliothèque musicale locale (iTunes/iPod) dont la taille dépasse la capacité de stockage mobile, souhaitant retrouver l'accès à l'ensemble de sa collection via YouTube Music.

**Problème résolu :** Une bibliothèque de 120 Go est physiquement inutilisable sur mobile. YouTube Music contient ~99% de ce catalogue. L'écart n'est pas un problème de contenu — c'est un problème d'import. Aucun service existant ne le résout gratuitement avec un contrôle total sur le processus.

### Ce qui rend ce projet unique

**L'insight clé :** `ytmusicapi` (bibliothèque Python non-officielle imitant les appels navigateur) permet de rechercher et d'ajouter des morceaux à la bibliothèque YouTube Music sans quota API — là où l'API officielle Google limiterait l'opération à ~500 jours. Ce verrou levé, le problème devient trivial.

**Architecture découplée en 3 phases :** `scanner.py` → `library.csv` → `matcher.py` → `library.csv` → `importer.py`. Le CSV central est l'artefact pivot enrichi progressivement : scan → URLs YouTube + scores de matching → import confirmé. Éditable dans Excel entre les phases pour correction manuelle. Chaque phase est rejouable indépendamment.

**Matching précis :** Score `rapidfuzz` sur artiste + titre + vérification de durée ±5s. Huit statuts explicites (`pending`, `imported`, `low_confidence`, `failed`, `duplicate`, `manual_review`, `already_exists`, `error_read`) donnent une visibilité totale et éliminent les imports silencieux incorrects.

**Résistance aux cas limites :** Ban temporaire (backoff exponentiel), titres annotés (regex de nettoyage), `browser.json` expiré (arrêt propre), fichiers corrompus (isolation par `try/except`), `Various Artists` (escalade directe en `manual_review`).

---

## Success Criteria

### User Success

- **Fidélité bibliothèque :** La collection YouTube Music reflète très fidèlement la bibliothèque locale de 120 Go — artistes, albums, morceaux clés présents.
- **Confiance totale :** Chaque morceau `imported` est garanti correct — pas de mauvaise version, pas de mauvais artiste. Préférence `manual_review` sur import incertain.
- **Visibilité complète :** Le CSV reflète l'état exact de chaque morceau local. Zéro morceau silencieusement perdu.

### Technical Success

- **Baseline v1 :** Taux de match mesuré après le premier run complet (~50 000 morceaux). Pas de cible fixée a priori — la v1 établit la référence.
- **Précision over rappel :** Seuil de confiance ≥85% par défaut (score `rapidfuzz` + vérification durée ±5s) — minimise les faux positifs, maximise les `manual_review` explicites.
- **Statut universel :** 100% des morceaux scannés ont un statut explicite à la fin du run.
- **Reprise sans perte :** Un run interrompu reprend exactement où il s'est arrêté — aucune donnée perdue.

### Measurable Outcomes

| Critère | Cible v1 |
|---------|----------|
| Morceaux avec statut explicite | 100% |
| Faux positifs dans `imported` | ~0 (tolérance nulle) |
| Taux de match global | À mesurer (baseline v1) |
| Reprise après interruption | Oui, via statuts CSV |

---

## Product Scope & Development Roadmap

### Phase 1 — MVP

**Approche :** Problem-solving MVP — outil personnel à usage unique. Succès = problème résolu pour Gabriel.

**Capacités incluses :**
- `scanner.py` : scan récursif, tags ID3, déduplication, export CSV (`pending`)
- `matcher.py` : recherche ytmusicapi, scoring rapidfuzz + durée, génération URL YouTube Music, gestion des cas limites (Various Artists, titres annotés), attribution des statuts pre-import
- `importer.py` : import des morceaux `pending` matchés, détection `already_exists`, gestion statuts post-import, rate limiting + backoff exponentiel
- `config.yaml` : chemin, seuil de confiance, extensions, `exclude_live`, tolérance durée, rate limit sleep
- Sortie console temps réel : barre de progression, morceau en cours, erreurs inline, résumé final
- Gestion des cas limites : `Various Artists`, titres annotés, fichiers corrompus, `browser.json` expiré, `already_exists`
- Jupyter Notebook pour test sur sous-ensemble (100 morceaux) avant full run

**Risques :**
- `ytmusicapi` non-officiel : bibliothèque activement maintenue. En cas de rupture : attendre fix community. Mitigation : version fixée dans `requirements.txt`.
- Volume `manual_review` inconnu avant le premier run. Mitigation : review par lot via filtre Excel, sans pression temporelle.

### Phase 2 — Post-MVP

- Interface de review interactive pour `low_confidence` et `manual_review`
- Support des playlists locales
- Rapport enrichi (stats par artiste / album / statut)

### Phase 3 — Vision

- Packaging pip + documentation publique
- Support multi-services (Spotify, Deezer)

---

## User Journeys

### Parcours 1 — Premier lancement : De zéro à la bibliothèque importée

**Gabriel, un dimanche soir.** Il a 120 Go de musique sur un vieux disque — une bibliothèque construite depuis les années iPod, intouchable depuis 10 ans mais irremplaçable. Son téléphone n'a plus la place. YouTube Music existe. Le pont entre les deux, c'est ce soir qu'il le construit.

Il installe les dépendances, génère son `browser.json` depuis le navigateur — une seule fois. Il édite `config.yaml` : chemin du dossier, seuil à 85%, `exclude_live: true`.

Il lance `scanner.py` sur 100 morceaux. Le CSV apparaît : 94 `pending`, 6 `duplicate`. Il lance `matcher.py` : le CSV se remplit d'URLs YouTube Music et de scores. Il jette un œil — les URLs ont l'air correctes. Il lance `importer.py` : 87 `imported`, 5 `low_confidence`, 2 `manual_review`. Il ouvre YouTube Music — les 87 morceaux sont là. Il relance sur les 50 000.

Quelques heures plus tard : un CSV complet, baseline v1 établie.

**Capacités révélées :** installation, config, test sous-ensemble, scan récursif, déduplication, matching avec URLs de vérification, statuts, résumé final.

---

### Parcours 2 — Run interrompu : La reprise sans douleur

**Gabriel, à 23h.** L'importer tourne depuis 2 heures — 31 000 traités. Le PC se met en veille.

Le lendemain matin : 31 000 lignes avec statut final, 19 000 à `pending`. Il relance `importer.py`. Le programme repart exactement là où il s'était arrêté. Aucune ligne traitée deux fois.

Si c'était le `browser.json` expiré : le programme avait stoppé proprement avec un message explicite. Régénération depuis le navigateur, relance. Même résultat.

**Capacités révélées :** détection `browser.json` expiré, reprise sur `pending` uniquement, idempotence complète.

---

### Parcours 3 — Traitement des orphelins : La review manuelle

**Quelques jours après le run complet.** Gabriel filtre le CSV sur `manual_review` : 800 lignes (`Various Artists`, tags vides, compilations). Filtre sur `low_confidence` : 1 200 lignes (score entre 70–85%).

Pour les `low_confidence` : il vérifie, remet en `pending` ceux qu'il valide, relance `importer.py`. Pour les `manual_review` : il ignore les compilations sans intérêt, ajoute les autres manuellement dans YouTube Music.

**Capacités révélées :** CSV éditable dans Excel, re-traitement sélectif par statut, séparation décision humaine / exécution automatique.

---

### Parcours 4 — Mise à jour incrémentale *(théorique)*

Si Gabriel ajoutait des albums au dossier local : `scanner.py` détecte les nouveaux fichiers, les existants restent `duplicate`. Seuls les nouveaux passent en `pending`. `importer.py` ne traite que ces nouvelles lignes.

*Note : Dossier source figé depuis plus de 10 ans — scénario quasi-théorique.*

**Capacités révélées :** déduplication robuste, idempotence du scanner, architecture incrémentale.

---

### Tableau de traçabilité Parcours → Capacités

| Capacité | Parcours |
|----------|----------|
| Config centralisée | 1 |
| Scan récursif + déduplication | 1, 4 |
| Test sur sous-ensemble | 1 |
| Matching + scoring + statuts CSV | 1, 2, 3 |
| Résumé des statuts en fin de run | 1, 2 |
| Reprise sur `pending` uniquement | 2, 3, 4 |
| Arrêt propre sur `browser.json` expiré | 2 |
| CSV éditable (Excel-compatible) | 3 |
| Idempotence complète | 2, 3, 4 |

---

## CLI Tool — Architecture & Configuration

### Structure des modules

```
music_importer/
  config.yaml       ← configuration centralisée
  scanner.py        ← Phase 1 : scan + tags + dédup → library.csv
  matcher.py        ← Phase 2 : library.csv → recherche YTM + scoring + URLs → library.csv
  importer.py       ← Phase 3 : library.csv (matchés) → import YouTube Music
  library.csv       ← artefact central (enrichi progressivement par chaque phase)
  notebook.ipynb    ← environnement de test/debug
```

### Exécution

```bash
python scanner.py     # Phase 1 : scan → library.csv
python matcher.py     # Phase 2 : library.csv → recherche + scoring + URLs YouTube
python importer.py    # Phase 3 : library.csv (matchés) → import YouTube Music
```

Tout paramètre ajustable passe par `config.yaml`. Aucun argument CLI requis. Comportement déterministe et scriptable. Run complet depuis le terminal ; développement et tests via Jupyter Notebook.

### Schéma de configuration

```yaml
music_folder: "/path/to/music"     # chemin du dossier source
confidence_threshold: 85           # seuil rapidfuzz (0–100)
duration_tolerance: 5              # tolérance durée ±Xs
exclude_live: true                 # filtrer les versions live
supported_extensions: [.mp3, .flac, .m4a, .aac]
rate_limit_sleep: 0.5              # pause entre appels API (secondes)
```

### Schéma du CSV de sortie

Colonnes : `filepath`, `artist`, `title`, `album`, `duration`, `status`, `yt_video_id`, `yt_url`, `yt_score`, `error_message`

> `yt_url` = `https://music.youtube.com/watch?v={yt_video_id}` — renseigné par `matcher.py` pour permettre la vérification visuelle dans Excel avant import.

### Sortie console temps réel

```
[████████░░] 68% — 34 127 / 50 000
▶ Processing: Daft Punk — Get Lucky
⚠ [ERROR] Various Artists — Track 04 → manual_review

✅ imported:       43 200
⚠  low_confidence:  4 100
📋 manual_review:   1 800
❌ failed:            300
🔁 duplicate:         600
Total:             50 000
```

### Dépendances

`ytmusicapi`, `tinytag`, `rapidfuzz`, `pyyaml`, `tqdm`

Authentification : `browser.json` généré une fois via `ytmusicapi browser`.

---

## Functional Requirements

### Configuration & Authentification

- **FR1 :** L'utilisateur peut configurer le chemin du dossier musique source via `config.yaml`
- **FR2 :** L'utilisateur peut configurer le seuil de confiance de matching (0–100)
- **FR3 :** L'utilisateur peut configurer la tolérance de durée pour la vérification (en secondes)
- **FR4 :** L'utilisateur peut configurer la liste des extensions de fichiers supportées
- **FR5 :** L'utilisateur peut activer/désactiver le filtre des versions live
- **FR6 :** L'utilisateur peut configurer la pause entre les appels API
- **FR7 :** L'utilisateur peut générer un fichier d'authentification `browser.json` via une commande dédiée
- **FR8 :** Le système détecte un `browser.json` expiré ou invalide et interrompt le run proprement avec un message explicite

### Scan de la Bibliothèque Locale

- **FR9 :** Le système parcourt récursivement un dossier de musique et tous ses sous-dossiers
- **FR10 :** Le système lit les métadonnées ID3 (artiste, titre, album, durée) des fichiers audio
- **FR11 :** Le système filtre les fichiers non-audio selon les extensions configurées
- **FR12 :** Le système détecte et marque les doublons par normalisation artiste + titre
- **FR13 :** Le système isole les fichiers corrompus sans interrompre le scan global
- **FR14 :** Le système exporte les résultats dans `library.csv` avec statut initial `pending`
- **FR15 :** Le système peut être relancé sur un dossier existant sans écraser les statuts déjà traités

### Matching & Scoring — matcher.py

- **FR16 :** Le système recherche un morceau dans YouTube Music par artiste et titre
- **FR17 :** Le système calcule un score de similarité textuelle entre le morceau local et les résultats YouTube Music
- **FR18 :** Le système vérifie la durée du résultat YouTube Music par rapport à la durée locale
- **FR19 :** Le système filtre les résultats live des recherches si configuré
- **FR20 :** Le système nettoie les annotations parasites du titre avant la recherche
- **FR21 :** Le système escalade automatiquement les morceaux `Various Artists` en `manual_review` sans tentative de recherche
- **FR37 :** Le système enregistre une URL YouTube Music cliquable (`https://music.youtube.com/watch?v={yt_video_id}`) dans la colonne `yt_url` du CSV pour chaque morceau ayant obtenu un résultat (bonne correspondance ou faible confiance)

### Import YouTube Music — importer.py

- **FR22 :** Le système ajoute un morceau matché à la bibliothèque YouTube Music de l'utilisateur
- **FR23 :** Le système détecte les morceaux déjà présents dans la bibliothèque YouTube Music et leur assigne le statut `already_exists`
- **FR24 :** Le système traite uniquement les lignes au statut `pending` ayant un `yt_video_id` renseigné (reprise automatique après matching)

### Gestion des Statuts & Résilience

- **FR25 :** Le système assigne l'un des statuts suivants à chaque morceau : `pending`, `imported`, `low_confidence`, `failed`, `duplicate`, `manual_review`, `already_exists`, `error_read`
- **FR26 :** Le système applique un délai configurable entre chaque appel API
- **FR27 :** Le système applique un backoff exponentiel sur les erreurs de rate limit (HTTP 429)
- **FR28 :** Le système met à jour le statut dans le CSV immédiatement après chaque traitement
- **FR29 :** Le système garantit que 100% des morceaux scannés ont un statut explicite à la fin du run

### Progression & Reporting

- **FR30 :** L'utilisateur voit en temps réel le pourcentage de progression du run
- **FR31 :** L'utilisateur voit en temps réel le morceau actuellement traité
- **FR32 :** L'utilisateur voit les erreurs et statuts non-standard au fil du run
- **FR33 :** L'utilisateur reçoit un résumé des compteurs par statut à la fin de chaque run

### Review Manuelle & Correction

- **FR34 :** L'utilisateur peut modifier manuellement les statuts dans le CSV
- **FR35 :** L'utilisateur peut relancer l'importer après modification manuelle du CSV pour re-traiter les lignes `pending`
- **FR36 :** L'utilisateur peut filtrer le CSV par statut pour identifier les morceaux nécessitant une intervention manuelle

---

## Non-Functional Requirements

### Performance

- **NFR1 :** Le scanner traite l'ensemble du dossier source (50k+ fichiers) sans saturation mémoire
- **NFR2 :** Le matcher et l'importer s'exécutent plusieurs heures consécutives sans dégradation de performance ni fuite mémoire
- **NFR3 :** La mise à jour de la barre de progression ne bloque pas le traitement des morceaux

### Fiabilité & Résilience

- **NFR4 :** Le CSV est persisté après chaque morceau traité — aucune perte de données en cas d'arrêt brutal
- **NFR5 :** Une erreur sur un fichier individuel (corrompu, illisible) n'interrompt pas le run global
- **NFR6 :** Une erreur réseau isolée n'interrompt pas le run — retry avec backoff, puis statut `failed` si échec persistant
- **NFR7 :** Le run peut être interrompu à tout moment (Ctrl+C, mise en veille) et repris sans perte ni doublon

### Sécurité

- **NFR8 :** Le fichier `browser.json` est listé dans `.gitignore` — ne doit jamais être commité ou partagé
- **NFR9 :** L'outil ne transmet aucune donnée musicale à des services tiers — seules les requêtes de recherche partent vers YouTube Music

### Intégration

- **NFR10 :** La version de `ytmusicapi` est fixée dans `requirements.txt`
- **NFR11 :** Le CSV est compatible avec Microsoft Excel (encodage UTF-8 BOM, séparateur virgule)

### Maintenabilité

- **NFR12 :** Aucune valeur de configuration hardcodée — tous les paramètres passent par `config.yaml`
- **NFR13 :** Les fonctions de nettoyage de titres et de scoring sont isolées et modifiables indépendamment de la logique principale
