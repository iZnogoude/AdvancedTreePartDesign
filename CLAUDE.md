# CLAUDE.md — Advanced Tree Part Design (ATPD)

Instructions projet pour l'agent. Lues à chaque session. Le document de référence est `docs/CDC_ATPD_v1.0.md` — en cas de doute sur le scope, c'est le CDC qui fait foi.

## Le projet en une phrase

Addon FreeCAD (Python pur) qui remplace l'expérience Part Design par un atelier unique : arbre de features moderne à la SolidWorks (états visuels, suppress/unsuppress, barre de reprise, groupes) + fonctions de modélisation unifiées à la Onshape (une Extrusion qui fait ajout/retrait/nouveau corps/fonction mince).

## Règles d'or (non négociables)

1. **Jamais de modification du kernel** — ATPD est une couche Python au-dessus de l'API FreeCAD. Les features créées sont de VRAIS objets PartDesign standards.
2. **Compatibilité vanilla (ENF3)** — tout document créé/modifié par ATPD doit rester ouvrable dans FreeCAD standard sans ATPD. Les métadonnées ATPD (groupes, états) vont dans des propriétés custom, jamais dans un format propriétaire.
3. **Pas d'usine à gaz** — défauts intelligents, minimum d'options exposées. En cas d'hésitation entre simple et configurable : simple. Les idées hors scope → issue `v2-backlog`, pas de code.
4. **Robustesse** — toute opération modifiant le document est wrappée dans une transaction FreeCAD (`doc.openTransaction()` / `commitTransaction()` / `abortTransaction()` en cas d'erreur). Rien ne doit pouvoir corrompre un document.
5. **Scope** : le Sketcher n'est PAS touché (exception unique : la fonction Texte). Smart Fasteners = projet séparé, hors repo.

## Environnement cible

- FreeCAD **1.0+** uniquement (Flatpak inclus). Environnement de dev de référence : Linux Mint 22.3, FreeCAD Flatpak dans `~/.var/app/org.freecad.FreeCAD/`, addon dans `.../data/FreeCAD/v1-1/Mod/`.
- **PySide6** obligatoire — jamais PySide2. Import pattern : `from PySide6 import QtWidgets, QtCore, QtGui` avec fallback `from PySide import ...` interdit.
- Python 3.11+, aucun code compilé, aucune dépendance externe non incluse dans FreeCAD.

## Pièges connus de l'API FreeCAD (acquis de projets précédents)

- Contraintes Sketcher : la propriété est `.Type`, PAS `.ConstraintType`.
- Joints Assembly : objets `App::FeaturePython` avec propriété string `JointType` (pas de TypeId distinct). Conteneur : `Assembly::JointGroup`.
- Flatpak : sandbox filesystem — si un processus externe est invoqué, wrapper dans `~/.local/bin/` + `flatpak override --filesystem=home`. Attention à la pollution `PYTHONHOME`.
- La propriété `Suppressed` des features PartDesign existe depuis 1.0 mais son comportement en cascade est fragile : toujours analyser les dépendances (`obj.InList` / `obj.OutList`) avant de suppress, et tester sur les fichiers de référence.
- `App.ActiveDocument` peut être `None` — toujours vérifier.

## Structure du repo

```
AdvancedTreePartDesign/
├── CLAUDE.md                  # ce fichier
├── LICENSE                    # LGPL-2.1+
├── README.md
├── package.xml                # métadonnées Addon Manager FreeCAD
├── InitGui.py                 # enregistrement du workbench
├── atpd/
│   ├── tree/                  # arbre custom (QDockWidget, modèle, états)
│   ├── features/              # dialogues unifiés (extrusion, révolution…)
│   ├── core/                  # orchestration : dépendances, rollback, transactions, métadonnées
│   └── resources/             # icônes SVG, traductions
├── tests/
│   ├── files/                 # les 5 .FCStd de référence (voir CDC §10)
│   └── test_*.py              # tests exécutés via FreeCADCmd
└── docs/
    └── CDC_ATPD_v1.0.md
```

## Workflow Git (strict)

- `main` est protégée. **Aucun commit direct sur main.**
- 1 issue = 1 branche = 1 PR. Nommage branche : `feat/<n°issue>-description-courte`, `fix/<n°issue>-...`, `chore/...`.
- Messages de commit : impératif, en anglais, référencer l'issue (`Fixes #12` pour fermer, `Refs #12` sinon).
- Toute PR doit : passer le lint (ruff), passer les tests, être relue et approuvée par John avant merge.
- Milestones GitHub = jalons M0→M6 du CDC. Toute nouvelle idée = issue labellisée, jamais du code spontané.

## Conventions de code

- Anglais pour le code, les commentaires, les commits et les issues (projet public, communauté internationale). Français OK dans les discussions PR avec John.
- Docstrings sur toute fonction publique. Type hints systématiques.
- UI : textes utilisateur passés par le mécanisme de traduction Qt (`QT_TRANSLATE_NOOP` / `translate()`) dès le départ — anglais par défaut, français fourni.
- Logging via `FreeCAD.Console.PrintMessage/PrintWarning/PrintError` — jamais de `print()` en production.
- Pas de variable globale d'état ; l'état vit dans les propriétés du document ou dans les objets du workbench.

## Tests

- Les 5 fichiers `.FCStd` de `tests/files/` sont la vérité terrain. Ne JAMAIS les modifier sans issue dédiée.
- Tout bug corrigé = un test de non-régression ajouté.
- Les tests s'exécutent en headless : `FreeCADCmd tests/run_tests.py` (ou via l'AppImage/Flatpak en CI).
- Critère de merge M2+ : suite verte sur les 5 fichiers.

## Jalons (rappel — détail dans le CDC §8)

M0 Fondations → M1 Audit + arbre lecture seule → M2 Arbre interactif → M3 Barre de reprise (spike de faisabilité AVANT de s'engager) → M4 Extrusion unifiée + Texte (**MVP**) → M5 Modeling complet → M6 Dressup & Transformations (**v1.0**).

## Ce que l'agent ne doit JAMAIS faire

- Toucher au kernel, proposer du C++, ou suggérer de forker FreeCAD.
- Casser la compatibilité vanilla des documents.
- Ajouter des options/préférences non demandées.
- Committer sur main ou merger sans revue humaine.
- Modifier les fichiers de test de référence.
- Étendre le scope sans issue validée par John.
