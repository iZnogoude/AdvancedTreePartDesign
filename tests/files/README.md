# Fichiers de référence

Ces 5 fichiers `.FCStd` sont la vérité terrain pour les tests de non-régression (voir [`CLAUDE.md`](../../CLAUDE.md) et [`docs/CDC_ATPD_v1.0.md`](../../docs/CDC_ATPD_v1.0.md) §10). **Ne jamais les modifier sans issue dédiée.**

## 01_simple.FCStd

Pièce simple (5-10 features). Cas nominal : sert de base pour vérifier qu'une chaîne de features standard se charge, s'affiche dans l'arbre et se reconstruit sans erreur.

## 02_complex.FCStd

Pièce complexe (30+ features). Sert à vérifier la performance et la lisibilité de l'arbre custom sur un historique long, plutôt que la correction géométrique elle-même.

## 03_cross_deps.FCStd

Pièce à dépendances croisées : des sketches sont attachés à des faces d'autres features plutôt qu'à des plans. Sert à tester la cascade suppress/rollback quand une feature dont dépendent d'autres est désactivée ou déplacée dans l'arbre.

## 04_sweep_loft.FCStd

Pièce avec Balayage (Sweep) et Lissage (Loft). Ce sont les fonctions de modeling les plus susceptibles de faire échouer le kernel OCCT ; sert à couvrir ces cas limites.

## 05_text_dressup.FCStd

Pièce avec texte extrudé (Sketcher) et Congés/Chanfreins. Couvre la fonction Texte (seule exception au scope "Sketcher non touché") ainsi que le Dressup.
