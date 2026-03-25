---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
workflowComplete: true
completedAt: '2026-02-22'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
---

# Youtube_upload_playlists - Epic Breakdown

## Overview

Ce document décompose les exigences du PRD de `Youtube_upload_playlists` en epics et stories implémentables, couvrant la migration d'une bibliothèque musicale locale (120 Go, ~50 000 morceaux) vers YouTube Music via `ytmusicapi`.

## Requirements Inventory

### Functional Requirements

- **FR1 :** L'utilisateur peut configurer le chemin du dossier musique source via `config.yaml`
- **FR2 :** L'utilisateur peut configurer le seuil de confiance de matching (0–100)
- **FR3 :** L'utilisateur peut configurer la tolérance de durée pour la vérification (en secondes)
- **FR4 :** L'utilisateur peut configurer la liste des extensions de fichiers supportées
- **FR5 :** L'utilisateur peut activer/désactiver le filtre des versions live
- **FR6 :** L'utilisateur peut configurer la pause entre les appels API
- **FR7 :** L'utilisateur peut générer un fichier d'authentification `browser.json` via une commande dédiée
- **FR8 :** Le système détecte un `browser.json` expiré ou invalide et interrompt le run proprement avec un message explicite
- **FR9 :** Le système parcourt récursivement un dossier de musique et tous ses sous-dossiers
- **FR10 :** Le système lit les métadonnées ID3 (artiste, titre, album, durée) des fichiers audio
- **FR11 :** Le système filtre les fichiers non-audio selon les extensions configurées
- **FR12 :** Le système détecte et marque les doublons par normalisation artiste + titre
- **FR13 :** Le système isole les fichiers corrompus sans interrompre le scan global
- **FR14 :** Le système exporte les résultats dans `library.csv` avec statut initial `pending`
- **FR15 :** Le système peut être relancé sur un dossier existant sans écraser les statuts déjà traités
- **FR16 :** Le système recherche un morceau dans YouTube Music par artiste et titre
- **FR17 :** Le système calcule un score de similarité textuelle entre le morceau local et les résultats YouTube Music
- **FR18 :** Le système vérifie la durée du résultat YouTube Music par rapport à la durée locale
- **FR19 :** Le système filtre les résultats live des recherches si configuré
- **FR20 :** Le système nettoie les annotations parasites du titre avant la recherche
- **FR21 :** Le système escalade automatiquement les morceaux `Various Artists` en `manual_review` sans tentative de recherche
- **FR22 :** Le système ajoute un morceau matché à la bibliothèque YouTube Music de l'utilisateur
- **FR23 :** Le système détecte les morceaux déjà présents dans la bibliothèque YouTube Music et leur assigne le statut `already_exists`
- **FR24 :** Le système traite uniquement les lignes au statut `pending` (reprise automatique)
- **FR25 :** Le système assigne l'un des statuts suivants à chaque morceau : `pending`, `imported`, `low_confidence`, `failed`, `duplicate`, `manual_review`, `already_exists`, `error_read`
- **FR26 :** Le système applique un délai configurable entre chaque appel API
- **FR27 :** Le système applique un backoff exponentiel sur les erreurs de rate limit (HTTP 429)
- **FR28 :** Le système met à jour le statut dans le CSV immédiatement après chaque traitement
- **FR29 :** Le système garantit que 100% des morceaux scannés ont un statut explicite à la fin du run
- **FR30 :** L'utilisateur voit en temps réel le pourcentage de progression du run
- **FR31 :** L'utilisateur voit en temps réel le morceau actuellement traité
- **FR32 :** L'utilisateur voit les erreurs et statuts non-standard au fil du run
- **FR33 :** L'utilisateur reçoit un résumé des compteurs par statut à la fin de chaque run
- **FR34 :** L'utilisateur peut modifier manuellement les statuts dans le CSV
- **FR35 :** L'utilisateur peut relancer l'importer après modification manuelle du CSV pour re-traiter les lignes `pending`
- **FR36 :** L'utilisateur peut filtrer le CSV par statut pour identifier les morceaux nécessitant une intervention manuelle
- **FR37 :** Le système enregistre une URL YouTube Music cliquable (`https://music.youtube.com/watch?v={yt_video_id}`) dans la colonne `yt_url` du CSV pour chaque morceau ayant obtenu un résultat de matching (bonne correspondance ou faible confiance)

### NonFunctional Requirements

- **NFR1 :** Le scanner traite l'ensemble du dossier source (50k+ fichiers) sans saturation mémoire
- **NFR2 :** L'importer s'exécute plusieurs heures consécutives sans dégradation de performance ni fuite mémoire
- **NFR3 :** La mise à jour de la barre de progression ne bloque pas le traitement des morceaux
- **NFR4 :** Le CSV est persisté après chaque morceau traité — aucune perte de données en cas d'arrêt brutal
- **NFR5 :** Une erreur sur un fichier individuel (corrompu, illisible) n'interrompt pas le run global
- **NFR6 :** Une erreur réseau isolée n'interrompt pas le run — retry avec backoff, puis statut `failed` si échec persistant
- **NFR7 :** Le run peut être interrompu à tout moment (Ctrl+C, mise en veille) et repris sans perte ni doublon
- **NFR8 :** Le fichier `browser.json` est listé dans `.gitignore` — ne doit jamais être commité ou partagé
- **NFR9 :** L'outil ne transmet aucune donnée musicale à des services tiers
- **NFR10 :** La version de `ytmusicapi` est fixée dans `requirements.txt`
- **NFR11 :** Le CSV est compatible avec Microsoft Excel (encodage UTF-8 BOM, séparateur virgule)
- **NFR12 :** Aucune valeur de configuration hardcodée — tous les paramètres passent par `config.yaml`
- **NFR13 :** Les fonctions de nettoyage de titres et de scoring sont isolées et modifiables indépendamment

### Additional Requirements

*Extraits de la section "CLI Tool — Architecture & Configuration" du PRD (remplace le document d'architecture absent) :*

- Structure des modules : `scanner.py` (Phase 1), `matcher.py` (Phase 2), `importer.py` (Phase 3), `library.csv` (artefact central), `config.yaml` (config), `notebook.ipynb` (test/debug)
- Exécution via `python scanner.py` → `python matcher.py` → `python importer.py` depuis le terminal
- Schéma CSV : colonnes `filepath`, `artist`, `title`, `album`, `duration`, `status`, `yt_video_id`, `yt_url`, `yt_score`, `error_message`
- Dépendances : `ytmusicapi`, `tinytag`, `rapidfuzz`, `pyyaml`, `tqdm`
- Authentification : `browser.json` généré via `ytmusicapi browser`
- Fichier `.gitignore` requis pour exclure `browser.json` et `library.csv`
- Fichier `requirements.txt` avec versions fixées

### FR Coverage Map

| FR | Epic | Domaine |
|----|------|---------|
| FR1–FR7 | Epic 1 | Configuration & Authentification |
| FR8 | Epic 1 | Détection browser.json expiré |
| FR9–FR15 | Epic 2 | Scan Phase 1 — Bibliothèque locale |
| FR16–FR21, FR37 | Epic 3 | Matching & Scoring Phase 2 — matcher.py |
| FR22–FR29 | Epic 4 | Import Phase 3 — importer.py |
| FR30–FR33 | Epic 4 | Progression & Reporting |
| FR34–FR36 | Epic 5 | Review manuelle des orphelins |

## Epic List

### Epic 1 : Setup & Authentification
L'utilisateur dispose d'un environnement configuré et authentifié, prêt à lancer le scan et l'import.
**FRs couverts :** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8
**Exigences additionnelles :** `requirements.txt`, `.gitignore`, structure du projet

### Epic 2 : Scan de la Bibliothèque Locale
L'utilisateur génère un inventaire CSV complet de sa bibliothèque musicale locale, avec déduplication et gestion des cas limites.
**FRs couverts :** FR9, FR10, FR11, FR12, FR13, FR14, FR15
**NFRs :** NFR1 (mémoire), NFR5 (fichiers corrompus)

### Epic 3 : Matching & Scoring de la Bibliothèque
L'utilisateur génère les propositions de correspondance YouTube Music pour chaque morceau, avec URLs cliquables pour vérification visuelle avant import.
**FRs couverts :** FR16, FR17, FR18, FR19, FR20, FR21, FR37
**NFRs :** NFR2 (stabilité multi-heures), NFR6 (résilience réseau), NFR13 (fonctions scoring isolées)

### Epic 4 : Import vers YouTube Music
L'utilisateur importe les morceaux matchés dans sa bibliothèque YouTube Music, avec suivi temps réel, résilience et reprise automatique.
**FRs couverts :** FR22, FR23, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR31, FR32, FR33
**NFRs :** NFR2, NFR3, NFR4, NFR6, NFR7

### Epic 5 : Review Manuelle des Orphelins
L'utilisateur identifie, évalue et traite manuellement les morceaux non importés automatiquement (`low_confidence`, `manual_review`).
**FRs couverts :** FR34, FR35, FR36
**NFRs :** NFR11 (compatibilité Excel)

---

## Epic 1 : Setup & Authentification

L'utilisateur dispose d'un environnement configuré et authentifié, prêt à lancer le scan et l'import.

### Story 1.1 : Initialisation de la structure du projet

En tant que développeur,
je veux un projet scaffoldé avec tous les fichiers requis,
afin de pouvoir démarrer le développement sans friction de mise en place.

**Acceptance Criteria :**

**Given** je clone le dépôt sur une machine vierge
**When** j'exécute `pip install -r requirements.txt`
**Then** toutes les dépendances (`ytmusicapi`, `tinytag`, `rapidfuzz`, `pyyaml`, `tqdm`) s'installent sans erreur
**And** les versions sont fixées dans `requirements.txt`

**Given** le projet est initialisé
**When** j'inspecte la structure du projet
**Then** les fichiers `scanner.py`, `matcher.py`, `importer.py`, `notebook.ipynb`, `config.yaml`, `requirements.txt`, `.gitignore` existent à la racine
**And** `browser.json` et `library.csv` sont listés dans `.gitignore`

**Given** les fichiers sont créés
**When** j'exécute `python scanner.py`, `python matcher.py` ou `python importer.py`
**Then** les scripts s'exécutent sans erreur d'import (même avec une logique vide)

### Story 1.2 : Configuration des paramètres via config.yaml

En tant qu'utilisateur,
je veux configurer tous les paramètres de scan et d'import dans `config.yaml`,
afin de personnaliser le comportement de l'outil sans modifier le code source.

**Acceptance Criteria :**

**Given** `config.yaml` existe avec `music_folder: "/path/to/music"`
**When** `scanner.py` démarre
**Then** il charge ce chemin comme dossier racine à scanner

**Given** `config.yaml` contient `confidence_threshold`, `duration_tolerance`, `supported_extensions`, `filter_live`, `api_delay`
**When** `scanner.py`, `matcher.py` ou `importer.py` est lancé
**Then** chaque paramètre est accessible dans le module correspondant via un objet config chargé

**Given** un `config.yaml` avec un paramètre manquant ou invalide
**When** `scanner.py`, `matcher.py` ou `importer.py` est lancé
**Then** le script s'arrête immédiatement avec un message précisant le paramètre manquant ou invalide

### Story 1.3 : Génération de l'authentification YouTube Music

En tant qu'utilisateur,
je veux générer un fichier `browser.json` via une commande dédiée,
afin que l'importer puisse accéder à ma bibliothèque YouTube Music personnelle.

**Acceptance Criteria :**

**Given** `ytmusicapi` est installé
**When** j'exécute `ytmusicapi browser` dans le terminal
**Then** le système me demande de coller mes headers navigateur
**And** un fichier `browser.json` est créé à la racine du projet

**Given** `browser.json` a été généré
**When** j'inspecte le `.gitignore`
**Then** `browser.json` y figure et n'est pas tracké par git

### Story 1.4 : Validation du browser.json au démarrage du matcher et de l'importer

En tant qu'utilisateur,
je veux que le matcher et l'importer détectent une authentification invalide ou expirée avant de démarrer,
afin de ne pas perdre du temps sur un run voué à l'échec.

**Acceptance Criteria :**

**Given** `browser.json` est absent
**When** j'exécute `python matcher.py` ou `python importer.py`
**Then** le script s'arrête immédiatement
**And** affiche : "browser.json manquant — exécutez `ytmusicapi browser` pour générer l'authentification"

**Given** `browser.json` existe mais est expiré ou malformé
**When** j'exécute `python matcher.py` ou `python importer.py`
**Then** le script effectue un appel test léger à YouTube Music API
**And** si l'appel échoue avec une erreur d'auth, affiche un message explicite et s'arrête
**And** aucune ligne de `library.csv` n'est traitée

**Given** un `browser.json` valide
**When** j'exécute `python matcher.py` ou `python importer.py`
**Then** l'authentification réussit silencieusement et le script passe à sa logique principale

---

## Epic 2 : Scan de la Bibliothèque Locale

L'utilisateur génère un inventaire CSV complet de sa bibliothèque musicale locale, avec déduplication et gestion des cas limites.

### Story 2.1 : Scan récursif et lecture des métadonnées ID3

En tant qu'utilisateur,
je veux que le scanner parcoure récursivement mon dossier musique et lise les métadonnées de chaque fichier audio,
afin d'obtenir un inventaire complet avec artiste, titre, album et durée.

**Acceptance Criteria :**

**Given** `music_folder` est configuré avec un dossier contenant des sous-dossiers
**When** j'exécute `python scanner.py`
**Then** le scanner parcourt tous les sous-dossiers récursivement
**And** extrait `artist`, `title`, `album`, `duration` depuis les tags ID3 de chaque fichier

**Given** un fichier audio avec tags ID3 incomplets (ex : titre manquant)
**When** le scanner traite ce fichier
**Then** le champ manquant est laissé vide sans erreur

**Given** un fichier non-audio (ex : `.jpg`, `.txt`) dans le dossier
**When** le scanner le rencontre
**Then** il est ignoré, conformément aux extensions configurées dans `supported_extensions`

### Story 2.2 : Détection des fichiers corrompus et gestion des erreurs de lecture

En tant qu'utilisateur,
je veux que les fichiers illisibles soient isolés sans interrompre le scan global,
afin de garantir que tous les autres fichiers sont quand même inventoriés.

**Acceptance Criteria :**

**Given** un fichier audio corrompu ou illisible par `tinytag`
**When** le scanner tente de lire ses métadonnées
**Then** le fichier est inclus dans `library.csv` avec le statut `error_read` et un message dans `error_message`
**And** le scan continue sur les fichiers suivants sans interruption

**Given** 50 000+ fichiers à scanner
**When** le scan s'exécute
**Then** la consommation mémoire reste stable (pas de chargement de tous les fichiers en RAM simultanément)

### Story 2.3 : Détection et marquage des doublons

En tant qu'utilisateur,
je veux que les morceaux en double soient identifiés automatiquement,
afin de ne pas importer plusieurs fois le même morceau dans YouTube Music.

**Acceptance Criteria :**

**Given** deux fichiers avec le même `artist` + `title` (après normalisation : lowercase, trim)
**When** le scanner traite ces fichiers
**Then** le premier est marqué `pending`, le second est marqué `duplicate`

**Given** deux fichiers avec le même titre mais des artistes différents
**When** le scanner les traite
**Then** ils sont tous les deux marqués `pending` (pas de faux positif sur les doublons)

### Story 2.4 : Export CSV et idempotence du scanner

En tant qu'utilisateur,
je veux que les résultats soient exportés dans `library.csv` et que le scanner puisse être relancé sans écraser les statuts existants,
afin de protéger le travail déjà effectué en cas de relance.

**Acceptance Criteria :**

**Given** le scan est terminé
**When** j'inspecte `library.csv`
**Then** chaque ligne contient les colonnes : `filepath`, `artist`, `title`, `album`, `duration`, `status`, `yt_video_id`, `yt_url`, `yt_score`, `error_message`
**And** tous les fichiers scannés ont le statut `pending` (sauf doublons → `duplicate`, corrompus → `error_read`)
**And** les colonnes `yt_video_id`, `yt_url`, `yt_score` sont vides (renseignées par `matcher.py` à l'étape suivante)

**Given** `library.csv` existe avec des lignes au statut `imported` ou `failed`
**When** je relance `python scanner.py`
**Then** les lignes dont le statut n'est pas `pending` sont conservées telles quelles
**And** seuls les nouveaux fichiers (absents du CSV) sont ajoutés avec le statut `pending`

**Given** le fichier CSV est créé
**When** je l'ouvre dans Microsoft Excel
**Then** les caractères accentués s'affichent correctement (encodage UTF-8 BOM)

---

## Epic 3 : Matching & Scoring de la Bibliothèque

L'utilisateur génère les propositions de correspondance YouTube Music pour chaque morceau, avec URLs cliquables pour vérification visuelle avant import.

### Story 3.1 : Recherche YouTube Music et nettoyage des titres

En tant qu'utilisateur,
je veux que le matcher recherche chaque morceau dans YouTube Music en nettoyant les titres des annotations parasites,
afin d'obtenir des résultats de recherche pertinents malgré les variations de nommage.

**Acceptance Criteria :**

**Given** une ligne `pending` avec `artist` et `title`
**When** `matcher.py` traite cette ligne
**Then** une requête de recherche est envoyée à YouTube Music avec `artist + title` nettoyé

**Given** un titre contenant des annotations parasites (`(Remastered)`, `[Live]`, `feat. X`, `- Radio Edit`)
**When** la requête est construite
**Then** ces annotations sont supprimées du titre avant la recherche

**Given** un morceau avec `artist = "Various Artists"`
**When** `matcher.py` le rencontre
**Then** il est directement marqué `manual_review` sans tentative de recherche
**And** `yt_video_id`, `yt_url`, `yt_score` restent vides

### Story 3.2 : Scoring de similarité et vérification de durée

En tant qu'utilisateur,
je veux que le matcher calcule un score précis sur artiste + titre et vérifie la durée,
afin d'identifier les vraies correspondances et distinguer les versions alternatives.

**Acceptance Criteria :**

**Given** des résultats de recherche retournés par YouTube Music
**When** le scoring est calculé
**Then** un score `rapidfuzz` (0–100) est calculé sur `artist + title` normalisés entre le morceau local et le meilleur résultat
**And** la durée du résultat est comparée à la durée locale avec la tolérance `duration_tolerance` configurée

**Given** le filtre live est activé (`exclude_live: true`)
**When** des résultats de recherche contiennent des versions live
**Then** ces résultats sont exclus avant le scoring

**Given** un score ≥ `confidence_threshold` et durée dans la tolérance
**When** le scoring valide le match
**Then** `yt_video_id` et `yt_score` sont renseignés, le statut reste `pending`

**Given** un score entre un seuil bas et `confidence_threshold`
**When** le scoring évalue le match
**Then** le statut est mis à `low_confidence`, `yt_video_id` et `yt_score` renseignés

**Given** aucun résultat satisfaisant
**When** le matching échoue
**Then** le statut est mis à `failed`, `yt_video_id` reste vide

### Story 3.3 : Génération des URLs de vérification et persistance CSV

En tant qu'utilisateur,
je veux que chaque morceau matché ait une URL YouTube Music cliquable dans le CSV et que le matching soit persisté au fil du run,
afin de pouvoir vérifier rapidement les correspondances dans Excel avant de lancer l'import.

**Acceptance Criteria :**

**Given** un morceau avec `yt_video_id` renseigné (statut `pending` ou `low_confidence`)
**When** `matcher.py` finalise le traitement du morceau
**Then** `yt_url` = `https://music.youtube.com/watch?v={yt_video_id}` est enregistré dans le CSV

**Given** le matcher traite un morceau
**When** le statut est déterminé
**Then** le CSV est mis à jour immédiatement (pas en batch) — aucune perte en cas d'arrêt brutal

**Given** `library.csv` contient déjà des lignes avec `yt_video_id` renseigné
**When** je relance `python matcher.py`
**Then** ces lignes sont ignorées — seules les lignes `pending` sans `yt_video_id` sont traitées

### Story 3.4 : Résilience réseau et progression du matcher

En tant qu'utilisateur,
je veux que le matcher résiste aux erreurs réseau et affiche sa progression,
afin de pouvoir lancer un matching overnight sur 50 000 morceaux sans surveillance.

**Acceptance Criteria :**

**Given** une erreur réseau isolée ou un HTTP 429 (rate limit)
**When** le matcher rencontre cette erreur
**Then** il applique un backoff exponentiel avant de retenter
**And** si l'erreur persiste, le morceau est marqué `failed` et le run continue

**Given** le run est démarré
**When** le matcher traite les morceaux
**Then** une barre de progression `tqdm` affiche le pourcentage et le morceau en cours

**Given** 50 000+ morceaux à matcher sur plusieurs heures
**When** le run s'exécute en continu
**Then** la consommation mémoire reste stable

---

## Epic 4 : Import vers YouTube Music

L'utilisateur importe les morceaux matchés dans sa bibliothèque YouTube Music, avec suivi temps réel, résilience et reprise automatique.

### Story 4.1 : Import des morceaux matchés et gestion des statuts post-import

En tant qu'utilisateur,
je veux que l'importer ajoute à ma bibliothèque YouTube Music tous les morceaux `pending` ayant un match validé,
afin de compléter la migration sans intervention manuelle.

**Acceptance Criteria :**

**Given** une ligne `pending` avec `yt_video_id` renseigné
**When** `importer.py` traite cette ligne
**Then** le morceau est ajouté à la bibliothèque YouTube Music via `ytmusicapi`
**And** le statut est mis à `imported`

**Given** un morceau dont `yt_video_id` est déjà présent dans la bibliothèque YouTube Music
**When** l'importer tente de l'ajouter
**Then** le statut est mis à `already_exists` sans erreur

**Given** une ligne `pending` sans `yt_video_id` (pas encore matchée)
**When** l'importer la rencontre
**Then** elle est ignorée sans modification de statut

**Given** toutes les lignes traitées
**When** le run se termine
**Then** 100% des lignes ont un statut explicite — aucune ligne reste sans statut

### Story 4.2 : Résilience réseau et rate limiting de l'importer

En tant qu'utilisateur,
je veux que l'importer résiste aux erreurs réseau et respecte les limites de l'API YouTube Music,
afin de pouvoir lancer un import overnight sans risque de ban ou de perte de données.

**Acceptance Criteria :**

**Given** un délai `rate_limit_sleep` configuré
**When** l'importer traite chaque morceau
**Then** il attend ce délai entre chaque appel API

**Given** une réponse HTTP 429 (rate limit)
**When** l'importer reçoit cette réponse
**Then** il applique un backoff exponentiel avant de retenter

**Given** une erreur réseau isolée persistante après retries
**When** les retries sont épuisés
**Then** le morceau est marqué `failed` et l'import continue sur la ligne suivante

### Story 4.3 : Persistance CSV et reprise automatique de l'importer

En tant qu'utilisateur,
je veux que l'importer persiste chaque statut immédiatement et reprenne là où il s'est arrêté,
afin de ne jamais perdre de progression en cas d'interruption.

**Acceptance Criteria :**

**Given** l'importer traite un morceau
**When** le statut est déterminé (`imported`, `already_exists`, `failed`)
**Then** le CSV est mis à jour immédiatement
**And** en cas d'arrêt brutal, seul le morceau en cours de traitement peut être perdu

**Given** le run est interrompu (Ctrl+C, mise en veille)
**When** je relance `python importer.py`
**Then** seules les lignes `pending` avec `yt_video_id` sont retraitées
**And** les lignes déjà finalisées (`imported`, `already_exists`, `failed`, etc.) sont ignorées

### Story 4.4 : Suivi temps réel et résumé de fin de run

En tant qu'utilisateur,
je veux voir la progression en temps réel et un résumé complet à la fin du run,
afin de suivre l'import sans avoir à ouvrir le CSV.

**Acceptance Criteria :**

**Given** le run est démarré
**When** l'importer traite les morceaux
**Then** une barre de progression `tqdm` affiche le pourcentage et le morceau en cours (artiste + titre)
**And** la mise à jour de la barre ne bloque pas le traitement

**Given** un statut non-standard (`failed`, `already_exists`, `error_read`)
**When** ce statut est assigné
**Then** une ligne de log est affichée dans la console avec le morceau et la raison

**Given** le run est terminé
**When** tous les morceaux ont été traités
**Then** un résumé affiche le compte par statut : `imported: X`, `low_confidence: X`, `failed: X`, `duplicate: X`, `manual_review: X`, `already_exists: X`, `error_read: X`

---

## Epic 5 : Review Manuelle des Orphelins

L'utilisateur identifie, évalue et traite manuellement les morceaux non importés automatiquement (`low_confidence`, `manual_review`).

### Story 5.1 : Filtrage et identification des morceaux à traiter manuellement

En tant qu'utilisateur,
je veux filtrer le CSV par statut pour isoler les morceaux nécessitant une intervention,
afin d'évaluer rapidement les `low_confidence` via leur URL YouTube et corriger les statuts.

**Acceptance Criteria :**

**Given** le run de matching et d'import est terminé
**When** j'ouvre `library.csv` dans Microsoft Excel
**Then** je peux filtrer la colonne `status` sur `low_confidence` pour voir les morceaux sous le seuil de confiance
**And** je peux filtrer sur `manual_review` pour voir les morceaux sans correspondance automatique (Various Artists, tags vides)

**Given** une ligne avec statut `low_confidence` et `yt_url` renseigné
**When** je clique sur le lien dans Excel
**Then** le navigateur ouvre la page YouTube Music du morceau proposé
**And** je peux vérifier visuellement si la correspondance est correcte

**Given** j'ai évalué un morceau `low_confidence` comme correct
**When** je modifie manuellement son statut en `pending` dans le CSV et sauvegarde
**Then** le fichier CSV est modifié sans corruption (encodage UTF-8 BOM préservé)

### Story 5.2 : Relance de l'import après correction manuelle

En tant qu'utilisateur,
je veux relancer l'importer après avoir corrigé des statuts manuellement dans le CSV,
afin d'importer les morceaux que j'ai validés sans re-traiter ceux déjà finalisés.

**Acceptance Criteria :**

**Given** j'ai remis en `pending` des lignes `low_confidence` validées dans Excel
**When** je relance `python importer.py`
**Then** seules les lignes `pending` avec `yt_video_id` renseigné sont traitées
**And** les lignes `imported`, `duplicate`, `error_read` restent intactes

**Given** j'ai laissé des lignes `manual_review` sans les modifier
**When** je relance `python importer.py`
**Then** ces lignes sont ignorées (pas de `yt_video_id`) et leur statut reste `manual_review`

**Given** le re-run est terminé
**When** j'inspecte le résumé console
**Then** les nouvelles lignes importées apparaissent dans le compteur `imported`
**And** un nouveau résumé complet des statuts est affiché
