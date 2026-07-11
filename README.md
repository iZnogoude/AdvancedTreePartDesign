# Advanced Tree Part Design (ATPD)

> Un atelier FreeCAD qui modernise Part Design : arbre de features à la SolidWorks (états visuels, suppress/unsuppress robuste, barre de reprise) et fonctions de modélisation unifiées à la Onshape (une Extrusion qui fait ajout/retrait/nouveau corps/fonction mince).

**Statut :** 🚧 En développement — Jalon M0 (Fondations)

## Pourquoi ce projet ?

FreeCAD dispose d'un excellent kernel géométrique et d'un bon Sketcher, mais :
- Le Model Tree est une simple liste d'objets, sans états visuels clairs, sans barre de reprise, sans groupement logique.
- Les ateliers Part et Part Design sont redondants et incompatibles entre eux.
- Des fonctions essentielles (Extrusion, Révolution, Balayage, Lissage) sont éclatées en plusieurs commandes au lieu d'un dialogue unifié comme sur Onshape ou SolidWorks.

ATPD est une **couche Python au-dessus du kernel FreeCAD existant** — aucune modification du kernel, aucun fork. Les features créées restent de vrais objets Part Design standards, ouvrables dans n'importe quel FreeCAD vanilla.

## Scope du projet

Le détail complet est dans [`docs/CDC_ATPD_v1.0.md`](docs/CDC_ATPD_v1.0.md). En résumé :

**Dans le scope :**
- Arbre de features custom (états, suppress/unsuppress, barre de reprise, groupes)
- Modeling unifié : Extrusion, Révolution, Balayage, Lissage
- Dressup amélioré : Chanfrein, Dépouille, nouvelle fonction Congés (Fillets)
- Transformations (symétries, répétitions) — traitées en fin de projet
- Fonction Texte native dans le Sketcher

**Hors scope :**
- Le Sketcher (sauf fonction Texte)
- Le module d'assemblage mécanique intelligent (Smart Fasteners) — projet séparé
- Toute modification du kernel OCCT/C++

## Jalons

| Jalon | Contenu |
|---|---|
| M0 | Fondations (ce jalon) |
| M1 | Audit Part/PartDesign + arbre en lecture seule |
| M2 | Arbre interactif (suppress, renommage, groupes) |
| M3 | Barre de reprise |
| M4 | Extrusion unifiée + Texte (**MVP**) |
| M5 | Modeling complet (Révolution, Balayage, Lissage) |
| M6 | Dressup & Transformations (**v1.0**) |

## Installation (à venir)

L'addon sera installable via l'Addon Manager de FreeCAD une fois le jalon M6 atteint. En attendant, pour tester en développement :

```bash
git clone https://github.com/<ton-user>/AdvancedTreePartDesign.git
ln -s $(pwd)/AdvancedTreePartDesign ~/.var/app/org.freecad.FreeCAD/data/FreeCAD/v1-1/Mod/ATPD
```

## Compatibilité

- FreeCAD 1.0+ (testé sur Flatpak, Linux Mint 22.3)
- PySide6

## Contribuer

Le projet fonctionne en branches + Pull Requests. Voir [`CLAUDE.md`](CLAUDE.md) pour les conventions de code et le workflow.

## Licence

LGPL-2.1+ — voir [`LICENSE`](LICENSE).
