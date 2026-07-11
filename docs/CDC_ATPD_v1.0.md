# Cahier des Charges — **Advanced Tree Part Design** (ATPD)
### Atelier Part Design modernisé pour FreeCAD

**Version :** 1.0 (validée — document de référence)
**Date :** 11 juillet 2026
**Auteur :** John (concepteur / prototypiste) — assisté par Claude
**Statut :** ✅ Validé — toutes les décisions du §10 sont tranchées. Ce document fait foi pour le développement.

---

## 1. Contexte et vision

FreeCAD 1.x dispose d'un kernel géométrique solide (OCCT) et d'un Sketcher de qualité, mais son expérience de modélisation pièce souffre de trois défauts majeurs :

1. **Deux ateliers redondants** (Part et Part Design) aux paradigmes incompatibles, source de confusion et de workflows cassés.
2. **Un arbre de modèle pauvre** : simple liste d'objets, sans états visuels clairs, sans activation/désactivation fiable, sans barre de reprise (rollback bar), sans groupement logique.
3. **Des fonctions éclatées et trop basiques** : là où Onshape ou SolidWorks offrent UNE fonction Extrusion qui fait tout (ajouter, enlever, nouveau corps, fonction mince), FreeCAD en propose plusieurs, dispersées, incomplètes.

**Vision :** un atelier unique de conception de pièce, construit comme une **couche Python (UX + orchestration) au-dessus du kernel FreeCAD existant**, s'inspirant de la mécanique éprouvée de SolidWorks/Onshape sans la copier. Pas de réécriture du kernel. Pas d'usine à gaz.

**Références d'inspiration :** SolidWorks (FeatureManager, rollback bar, états de features), Onshape (fonctions unifiées, simplicité).

---

## 2. Objectifs

| # | Objectif | Mesurable par |
|---|----------|---------------|
| O1 | Un arbre de features moderne, lisible et robuste | Un utilisateur SolidWorks comprend l'arbre sans documentation |
| O2 | Activer/désactiver/modifier une feature sans casser la pièce | Suite de tests de non-régression sur fichiers de référence |
| O3 | Barre de reprise fonctionnelle | Reprise à n'importe quelle étape + édition + retour sans corruption |
| O4 | Fonctions unifiées (Extrusion tout-en-un en premier) | 1 dialogue = ajout / retrait / nouveau corps / fonction mince |
| O5 | Réduire la confusion Part vs Part Design | L'utilisateur ne quitte jamais l'atelier pour une opération courante |

---

## 3. Périmètre (IN SCOPE)

### 3.1 — L'arbre de features (module central, priorité 1)

- **Panneau dockable custom** remplaçant (ou complétant) le Model tree natif pour le Body actif.
- **États visuels clairs** par feature : ✅ active · ⏸️ supprimée (suppressed) · ❌ en erreur · 🔒 verrouillée · sous la barre de reprise (grisée).
- **Activation / désactivation (suppress/unsuppress)** fiable, avec gestion des dépendances en cascade (avertissement avant de désactiver une feature dont d'autres dépendent).
- **Barre de reprise (rollback bar)** : positionner la barre à n'importe quel point de l'arbre, le modèle 3D reflète l'état à ce point, insertion de nouvelles features au point de reprise.
- **Groupement logique** : dossiers/groupes de features nommés (comme les dossiers du FeatureManager SW).
- **Renommage rapide** (F2, double-clic) — réutilisation des acquis du macro Constraint Renamer.
- **Menu contextuel riche** : éditer, supprimer (avec analyse d'impact), supprimer les enfants, aller au sketch parent, isoler.
- **Affichage des dépendances** : au survol/sélection d'une feature, mise en évidence de ses parents et enfants.

### 3.2 — Fonctions de modélisation unifiées (priorité 2)

L'atelier reprend le principe des **4 barres d'icônes** de FreeCAD, chacune avec un niveau de retravail différent :

**Barre 1 — Modeling** *(fonctions à reconstruire en profondeur — cœur du projet)*
- **Extrusion / Cavité unifiée** (LE cas d'école, à livrer en premier) : un seul dialogue avec modes *Ajouter / Enlever / Nouveau corps / Intersection* + option **fonction mince (thin feature)** + directions (borgne, symétrique, deux directions, jusqu'à face/plan). Orchestration des features Pad/Pocket/Part existantes en interne.
- **Révolution unifiée** (même logique de dialogue tout-en-un).
- **Balayage (Sweep) unifié** : à revoir en profondeur — même paradigme add/remove/new body + fonction mince.
- **Lissage (Loft) unifié** : à revoir en profondeur — même paradigme.

**Barre 2 — Dressup** *(fonctions à améliorer)*
- **Chanfrein, dépouille** : fonctionnent à peu près bien — reprises avec améliorations ciblées.
- **Congés (Fillets) : fonction complète à ajouter** — périmètre exact (congé variable, congé face-face, etc.) à préciser lors de l'audit M1.

**Barre 3 — Transformation features** *(scope différé en fin de projet)*
- Symétries, répétitions linéaires et polaires : **dans le scope**, mais traitées en dernier — décision « reprise à l'identique ou refonte » prise après l'audit et le retour d'usage sur les barres 1 et 2.

**Barre 4 — Helpers** *(fonctions de base)*
- Créer corps, créer esquisse, plans/axes/points de référence, etc. — reprises et intégrées à l'atelier.

### 3.3 — Tri des fonctions existantes

- **Audit Part + Part Design** : tableau de toutes les commandes des deux ateliers, classées *Garder tel quel / Améliorer / Wrapper dans fonction unifiée / Exclure de l'atelier*.
- Ce tableau est un **livrable du jalon M1** (c'est TOI qui tranches, sur la base de ton usage réel).

### 3.4 — Conservé à l'identique (à une exception près)

- **Le Sketcher** : intégré tel quel, **avec un seul ajout : une fonction Texte native dans l'esquisse** (saisie du texte, police, taille, position directement dans le sketch — remplace le workflow ShapeString actuel, pénible et hors sketch). Aucun autre développement sur le Sketcher.
- Le kernel géométrique, le système d'expressions, les Bodies/Parts/Links.

---

## 4. Hors périmètre (OUT OF SCOPE)

| Exclu | Raison | Reporté à |
|-------|--------|-----------|
| Module Smart Fasteners (boulonnerie automatique) | Projet distinct, déjà identifié | Projet séparé |
| Modifications du kernel C++ / OCCT | Hors stratégie (couche Python only) | Jamais |
| Refonte du Sketcher | Jugé bon en l'état (seul ajout : fonction Texte, voir §3.4) | Jamais |
| Assemblage (joints, contraintes d'assemblage) | Autre atelier | Éventuel projet futur |
| Configurations multi-pièces avancées | Le macro Configuration Manager existe déjà ; intégration possible plus tard | v2+ |
| Support FreeCAD < 1.0 | Simplification majeure (Suppressed natif, PySide6) | Jamais |
| Multi-langue au lancement | Français + anglais suffisent en v1 | v1.1 |
| TechDraw, FEM, CAM | Autres domaines | Jamais |

---

## 5. Exigences non fonctionnelles

- **ENF1 — Robustesse avant tout** : aucune opération de l'atelier ne doit pouvoir corrompre un document. Toute opération risquée = transaction FreeCAD (undo-able) + sauvegarde d'état.
- **ENF2 — Performance** : arbre réactif jusqu'à 200 features par Body (rafraîchissement < 100 ms).
- **ENF3 — Non-invasif** : l'atelier ne modifie pas les fichiers `.FCStd` de façon incompatible — un document créé avec l'atelier reste ouvrable dans FreeCAD vanilla (les features restent des objets Part Design standards + métadonnées additionnelles).
- **ENF4 — Sobriété** ("pas d'usine à gaz") : défauts intelligents, minimum d'options exposées, pas de panneau de préférences tentaculaire.
- **ENF5 — Compatibilité** : FreeCAD 1.0+ (Flatpak inclus), PySide6, Linux/Windows/macOS.

---

## 6. Contraintes et environnement technique

- **Langage :** Python 3.11+ (API FreeCAD + PySide6). Aucun code compilé.
- **Forme :** addon FreeCAD standard (répertoire dans `Mod/`), installable via Addon Manager à terme.
- **Environnement de dev de référence :** Linux Mint 22.3, FreeCAD 1.x Flatpak (`~/.var/app/org.freecad.FreeCAD/`).
- **Pièges connus (acquis des projets précédents) :** PySide6 obligatoire (pas PySide2) · sandbox Flatpak (`flatpak override --filesystem=home` si processus externes) · constraints Sketcher = `.Type` · joints Assembly = `App::FeaturePython` avec propriété `JointType`.
- **Gestion de projet :** GitHub — Issues + Labels + Milestones + Projects (kanban), workflow branches + Pull Requests, revue humaine avant merge. `CLAUDE.md` à la racine (dérivé de ce CDC après validation).

---

## 7. Architecture cible (haut niveau)

```
┌─────────────────────────────────────────────┐
│  ATELIER (addon Python)                     │
│                                             │
│  ┌───────────────┐  ┌────────────────────┐  │
│  │ Arbre custom  │  │ Dialogues unifiés  │  │
│  │ (QDockWidget) │  │ (Extrusion, Révo…) │  │
│  └──────┬────────┘  └─────────┬──────────┘  │
│         │                     │             │
│  ┌──────┴─────────────────────┴──────────┐  │
│  │ Couche orchestration                  │  │
│  │ (état, dépendances, rollback,         │  │
│  │  transactions, métadonnées)           │  │
│  └──────────────────┬────────────────────┘  │
└─────────────────────┼───────────────────────┘
                      │ API Python FreeCAD
┌─────────────────────┴───────────────────────┐
│  FREECAD (inchangé) : PartDesign features,  │
│  Sketcher, expressions, kernel OCCT         │
└─────────────────────────────────────────────┘
```

Principe clé : **les features créées sont de vrais objets Part Design standards.** L'atelier ajoute une couche de métadonnées (groupes, états) stockée dans des propriétés custom du document — jamais dans un format propriétaire.

---

## 8. Jalons proposés (plan de dev)

| Jalon | Contenu | Livrable | Critère de sortie |
|-------|---------|----------|-------------------|
| **M0 — Fondations** | Repo GitHub, licence, CLAUDE.md, squelette d'addon (workbench vide qui se charge), CI lint, **5 fichiers `.FCStd` de test** (voir §10) | Addon installable qui affiche un panneau vide | L'atelier apparaît dans FreeCAD Flatpak |
| **M1 — Audit & arbre lecture seule** | Tableau d'audit Part/PartDesign + arbre custom affichant les features du Body actif avec états visuels | Arbre dockable en lecture | L'arbre reflète fidèlement les 5 pièces de test |
| **M2 — Arbre interactif** | Suppress/unsuppress avec cascade, renommage, menu contextuel, groupes | Arbre pilotable | Tests de non-régression verts sur les fichiers de référence |
| **M3 — Barre de reprise** | Rollback bar + insertion au point de reprise | Le jalon le plus risqué techniquement | Reprise/édition/retour sans corruption sur les 5 pièces |
| **M4 — Extrusion unifiée + Texte** | Dialogue Extrusion/Cavité tout-en-un + fonction mince + fonction Texte dans le Sketcher | **= MVP publiable** | Modéliser une pièce réelle de A à Z (texte inclus) sans quitter l'atelier |
| **M5 — Modeling complet** | Révolution, Balayage et Lissage unifiés (même paradigme que M4) | Barre 1 terminée | Les 4 fonctions partagent la même logique de dialogue |
| **M6 — Dressup & Transformations** | Congés complets (nouvelle fonction), chanfrein/dépouille améliorés, audit des Transformations (reprise ou refonte), Helpers finalisés, publication Addon Manager | **v1.0 publique** | Barres 2, 3 et 4 opérationnelles |

Chaque jalon = 1 Milestone GitHub, découpé en issues. 1 issue = 1 branche = 1 PR relue par toi avant merge.

---

## 9. Risques identifiés

| Risque | Impact | Mitigation |
|--------|--------|------------|
| Le rollback natif de FreeCAD a des limites internes (kernel) | M3 partiel voire dégradé | Spike technique en début de M3 : prototype jetable 2-3 jours pour valider la faisabilité AVANT de s'engager. Plan B : rollback "visuel" (suppress en masse) au lieu d'un vrai rollback kernel |
| Suppress en cascade casse des références | Corruption de design | Analyse de dépendances systématique + transaction + tests de référence |
| Scope creep ("et si on ajoutait…") | Projet jamais fini | Ce CDC fait foi. Toute idée nouvelle → issue étiquetée `v2-backlog`, pas de dev |
| Évolution de l'API FreeCAD entre versions 1.x | Maintenance | Cibler l'API stable documentée, CI de test sur version de référence |
| Concurrence/redondance avec les efforts UX officiels (grant Design System FPA) | Travail dupliqué | Veille sur le repo FreeCAD ; l'addon reste complémentaire, pas un fork |

---

## 10. ✅ Décisions fondatrices (toutes validées le 11/07/2026)

- [x] **Nom du projet : Advanced Tree Part Design (ATPD)** — repo GitHub proposé : `AdvancedTreePartDesign`
- [x] **Licence : LGPL-2.1+** (cohérente avec l'écosystème FreeCAD, compatible intégration upstream)
- [x] **Périmètre des fonctions v1** : Modeling (Extrusion, Révolution, Balayage, Lissage à reconstruire), Dressup (Congés à créer, chanfrein/dépouille à améliorer), Transformations en fin de projet, Helpers repris, fonction Texte dans le Sketcher (§3.2, §3.4)
- [x] **Barre de reprise avant Extrusion** (M3 avant M4) — spike de faisabilité en début de M3
- [x] **ENF3 — compatibilité vanilla** : les documents restent ouvrables dans FreeCAD standard
- [x] **Repo public dès M0** (visibilité communauté, éligibilité grant FPA)
- [x] **5 fichiers `.FCStd` de référence** pour les tests de non-régression :
  1. Pièce simple (5-10 features) — cas nominal
  2. Pièce complexe (30+ features) — performance et lisibilité de l'arbre
  3. Pièce à dépendances croisées (sketches attachés à des faces de features) — cascade suppress/rollback
  4. Pièce avec Balayage + Lissage — cas limites kernel
  5. Pièce avec texte extrudé + congés/chanfreins — Dressup et fonction Texte

---

*Prochaine étape : rédaction du `CLAUDE.md` (dérivé de ce document) + création du repo + découpage de M0 en issues.*
