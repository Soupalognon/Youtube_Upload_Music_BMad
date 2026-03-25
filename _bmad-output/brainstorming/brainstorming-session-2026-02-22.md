---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: []
session_topic: "Développement d'un outil d'import musique locale → YouTube Music"
session_goals: "Créer un programme qui lit un dossier de musique local et fait des appels API pour ajouter les morceaux à la bibliothèque YouTube Music"
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Morphological Analysis', 'Reverse Brainstorming']
ideas_generated: 25
session_active: false
workflow_completed: true
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Gabriel
**Date:** 2026-02-22

## Session Overview

**Sujet :** Développement d'un outil d'import musique locale → YouTube Music
**Objectifs :** Créer un programme qui lit un dossier de musique local et fait des appels API pour ajouter les morceaux à la bibliothèque YouTube Music

### Mise en place de la session

_Session initialisée le 2026-02-22. Sujet confirmé par Gabriel._

## Sélection des Techniques

**Approche :** Techniques recommandées par l'IA
**Contexte d'analyse :** Outil d'import de bibliothèque musicale locale vers YouTube Music via API

**Techniques recommandées :**

- **First Principles Thinking :** Démanteler les suppositions pour définir le vrai problème (upload de fichiers ? matching de métadonnées ?)
- **Morphological Analysis :** Cartographier toutes les dimensions techniques (formats, API, matching, auth, erreurs)
- **Reverse Brainstorming :** Anticiper les cas limites en imaginant comment faire échouer le programme

**Raisonnement IA :** Séquence conçue pour un projet technique concret — comprendre le problème en profondeur → explorer toutes les dimensions → durcir la solution contre les cas problématiques.

## Technique 1 : First Principles Thinking — Résultats

**[Fondement #1] : MATCH + ÉPINGLE, pas upload**
_Concept :_ Le programme trouve la chanson dans le catalogue YouTube Music et l'ajoute à la bibliothèque. Aucun fichier ne bouge.
_Nouveauté :_ Zéro problème de droits, zéro stockage.

**[Fondement #2] : ytmusicapi comme moteur unique**
_Concept :_ Bibliothèque Python non-officielle qui imite les appels navigateur. Recherche + ajout à la bibliothèque sans quota. Remplace totalement l'API officielle Google pour ce cas d'usage.
_Nouveauté :_ 50 000 chansons en quelques heures vs 500 jours avec l'API officielle.

**[Fondement #3] : Tags ID3 comme source primaire de métadonnées**
_Concept :_ On lit les tags des fichiers locaux (artiste + titre) pour la recherche. Simple, direct, suffisant pour une bibliothèque iTunes/iPod bien entretenue.
_Nouveauté :_ Pas besoin de fingerprint audio pour ce cas d'usage.

**[Fondement #4] : Fichier de tri manuel pour les orphelins**
_Concept :_ Tags insuffisants ou aucun résultat ytmusicapi → isolé dans le CSV avec statut `manual_review`.
_Nouveauté :_ Le programme ne bloque jamais sur un cas difficile.

## Technique 2 : Morphological Analysis — Carte complète

**[Dimension #1] : Architecture deux phases découplées**
_Concept :_ `scanner.py` produit `library.csv`, `importer.py` consomme `library.csv`. Les deux sont indépendants et rejouables.
_Nouveauté :_ Le CSV devient l'artefact central — éditable manuellement dans Excel avant l'import.

```
music_importer/
  config.yaml     ← chemins, seuils, options
  scanner.py      ← Phase 1 : scan + tags → library.csv
  importer.py     ← Phase 2 : lit library.csv → ytmusicapi
  library.csv     ← ARTEFACT CENTRAL (éditable)
```

**[Dimension #2] : tinytag pour lecture des métadonnées**
_Concept :_ Bibliothèque Python ultra-simple, lecture seule, multi-formats. Parfaite pour 99% MP3.
_Nouveauté :_ 5 lignes pour lire artiste + titre + album + durée.

**[Dimension #3] : Déduplication par normalisation douce**
_Concept :_ Lowercase + strip ponctuation sur artiste + titre. Doublons → statut `duplicate` dans le CSV.
_Nouveauté :_ Efficace pour 95% des cas sans sur-ingénierie.

**[Dimension #4] : Recherche ytmusicapi par Artiste + Titre**
_Concept :_ Requête `"Artiste Titre"` vers ytmusicapi, filtre `resultType: song`.
_Nouveauté :_ Simple et précis, évite le bruit de l'album dans la requête.

**[Dimension #5] : Scoring rapidfuzz + vérification durée**
_Concept :_ Score de similarité textuelle (seuil configurable, ex: 80%) + vérification durée ±5s. Résultat : `imported` si confiant, `low_confidence` sinon.
_Nouveauté :_ Combinaison redoutable qui élimine les faux positifs sans complexité excessive.

**[Dimension #6] : CSV comme fichier de progression (reprise gratuite)**
_Concept :_ L'importeur ne traite que les lignes `pending`. Relancer = reprendre exactement où on s'est arrêté.
_Nouveauté :_ Résolu gratuitement par l'architecture découplée.

**[Dimension #7] : Rate limiting time.sleep(0.5)**
_Concept :_ Pause de 0.5s entre chaque appel ytmusicapi pour éviter un ban temporaire.
_Nouveauté :_ Simple, suffisant, configurable.

**[Dimension #8] : Authentification via browser.json manuel**
_Concept :_ Fichier de cookies/headers généré une fois depuis le navigateur. Étape unique de setup.
_Nouveauté :_ Stable dans le temps, pas besoin de re-authentification fréquente.

**Statuts possibles dans library.csv :**
`pending` | `imported` | `low_confidence` | `failed` | `duplicate` | `manual_review`

## Technique 3 : Reverse Brainstorming — Risques identifiés et contre-mesures

**[Risque #1] : Flood ytmusicapi → ban temporaire**
_Contre-mesure :_ `time.sleep(0.5)` + backoff exponentiel sur erreur 429.

**[Risque #2] : Titres avec annotations parasites**
_Contre-mesure :_ Regex qui strip `(...)` et `[...]` avant recherche. Config `exclude_live: true` pour filtrer les résultats live côté YouTube Music.

**[Risque #3] : browser.json expiré en cours de run**
_Contre-mesure :_ Détecter l'erreur d'authentification → arrêt propre avec message explicite, statuts préservés dans le CSV.

**[Risque #4] : Chanson déjà dans la bibliothèque YouTube Music**
_Contre-mesure :_ Capturer l'erreur → statut `already_exists`, pas `failed`.

**[Risque #5] : Sous-dossiers imbriqués non parcourus**
_Contre-mesure :_ `os.walk()` récursif, pas `os.listdir()`.

**[Risque #6] : Fichiers non-musicaux dans le dossier**
_Contre-mesure :_ Filtrer par extension : `['.mp3', '.flac', '.m4a', '.aac']`.

**[Risque #7] : Artiste = "Various Artists"**
_Contre-mesure :_ Détecter ce pattern → statut `manual_review` directement, sans tenter une recherche inutile.

**[Risque #8] : Fichier MP3 corrompu**
_Contre-mesure :_ `try/except` sur chaque lecture tinytag → statut `error_read` dans le CSV, le scan continue.

**[Risque #9] : Faux positif de similarité (même titre, mauvais artiste)**
_Contre-mesure :_ Score calculé sur artiste + titre ensemble. La vérification de durée ±5s ajoute une couche de sécurité supplémentaire.

## Organisation et Prioritisation

### Thème 1 : Fondations architecturales
- Match + épingle (pas upload) — zéro problème de droits
- ytmusicapi comme moteur unique — sans quota
- Jupyter Notebook 3 phases indépendantes — jetable mais lisible
- CSV comme artefact central — éditable dans Excel, pont entre phases

### Thème 2 : Lecture et préparation des données locales (Phase 1)
- tinytag pour lire les métadonnées MP3
- Filtrage par extension (`.mp3`, `.flac`, `.m4a`)
- Scan récursif `os.walk()`
- Déduplication par normalisation douce (lowercase + strip ponctuation)
- `try/except` sur chaque lecture — un fichier corrompu ne bloque pas tout
- Nettoyage des titres — strip `(Remastered)`, `[Live]`, `feat. X` avant recherche

### Thème 3 : Matching et qualité des résultats (Phase 2)
- Requête Artiste + Titre vers ytmusicapi
- Score rapidfuzz sur artiste + titre ensemble + vérification durée ±5s
- Filtre `exclude_live` dans config
- Gestion `Various Artists` → `manual_review` directement
- Seuil de confiance configurable dans `config.yaml`

### Thème 4 : Robustesse et résilience
- `time.sleep(0.5)` entre chaque appel
- Backoff exponentiel sur erreur 429
- Détection expiration `browser.json` → arrêt propre
- Gestion `already_exists` → statut dédié
- Reprise automatique via statuts CSV

### Thème 5 : Configuration et observabilité
- `config.yaml` : chemin dossier, seuil similarité, `exclude_live`, extensions
- 6 statuts dans le CSV : `pending` / `imported` / `low_confidence` / `failed` / `duplicate` / `manual_review`
- Authentification `browser.json` — étape unique de setup
- Résumé des statuts affiché en fin de run

## Plan de développement

| Étape | Ce qu'on construit | Priorité |
|-------|--------------------|----------|
| **1** | Setup : `config.yaml` + `browser.json` + install deps (`ytmusicapi`, `tinytag`, `rapidfuzz`) | Immédiat |
| **2** | Cellule 1 : scanner + tags + déduplication + export CSV | Fondation |
| **3** | Cellule 2 : recherche ytmusicapi + scoring + filtres + update CSV | Cœur |
| **4** | Cellule 3 : import bibliothèque + gestion erreurs + résumé final | Final |
| **5** | Test sur sous-dossier (100 chansons) avant full run 50k | Validation |

## Résumé de session et insights

**Réalisations clés :**
- 25 décisions techniques concrètes prises en une session
- Architecture complète définie : Jupyter Notebook 3 phases + CSV central
- Découverte majeure : l'API officielle Google est inutilisable pour 50k chansons → ytmusicapi est la vraie solution
- Tous les cas limites critiques anticipés et adressés

**Percées créatives :**
- L'idée de découpler scan/matching/import en 3 phases rejouables indépendamment a émergé naturellement de la contrainte "je veux relancer plusieurs fois"
- Le CSV comme fichier de progression résout gratuitement la reprise après interruption
- Le filtre `exclude_live` comme paramètre de config ouvre la porte à d'autres filtres futurs (remixes, instrumentals, etc.)

**Prochaine étape concrète :**
Installer les dépendances et générer le `browser.json` depuis YouTube Music dans le navigateur, puis commencer la Cellule 1 du notebook.

```bash
pip install ytmusicapi tinytag rapidfuzz pyyaml
ytmusicapi browser
```

_Session de brainstorming complétée le 2026-02-22 par Gabriel._
