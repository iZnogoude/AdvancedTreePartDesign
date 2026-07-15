# Spike : faisabilité technique de la barre de reprise

Prototype jetable (voir [`spike_rollback_experiment.py`](spike_rollback_experiment.py)) exécuté sur une **copie temporaire** de `tests/files/02_complex.FCStd` (15 features, le fichier de référence avec le plus de features) via `flatpak run --command=FreeCADCmd org.freecad.FreeCAD docs/spike_rollback_experiment.py`. Le fichier de référence n'a jamais été ouvert en écriture — vérifié (`git status` propre après exécution).

## Verdict

> **Rollback natif partiel avec limitations suivantes** : la mécanique de repositionnement du Tip et d'insertion de feature est robuste et gérée nativement par FreeCAD (aucune corruption, aucun crash, aucune perte de données). Mais insérer une feature en amont d'une feature de Dressup (Fillet/Chamfer/Draft) qui référence des edges/faces spécifiques **peut invalider cette feature aval**, à cause du Topological Naming Problem — une limitation connue et documentée du kernel FreeCAD, pas un bug introduit par ATPD. C'est le même risque que rencontre un utilisateur de FreeCAD natif utilisant sa propre barre de reprise. ATPD doit **avertir l'utilisateur** avant une insertion à un point de reprise qui a des features Dressup en aval (réutilisation du pattern d'avertissement déjà en place pour Suppress/Delete), pas empêcher l'opération.

## Question 1 — Positionner un point de reprise au milieu d'un Body et y insérer une nouvelle feature

**Réponse : oui.**

- `PartDesign::Body.insertObject(feature, target, after=False)` existe bien en FreeCAD 1.1.1 (`src/Mod/PartDesign/App/Body.pyi`) et fonctionne exactement comme documenté : insère `feature` dans `Body.Group` juste après (ou avant) `target`.
- Confirmé dans le code source (`Body.cpp`, méthode `setBaseProperty`) et **vérifié empiriquement** : `insertObject` relie automatiquement la chaîne `BaseFeature` des deux côtés de l'insertion — la nouvelle feature reçoit `BaseFeature = target`, et la feature qui suivait `target` voit son propre `BaseFeature` **automatiquement rerouté** vers la nouvelle feature. Pas besoin de relinker manuellement.
- Test réel : Tip déplacé sur `Pocket` (feature intermédiaire), une nouvelle `Sketch`+`Pad` (`SpikeSketch`/`SpikePad`) insérées juste après via `body.insertObject(pad, pocket, True)`. Résultat : `Body.Group` passe de `[..., Pocket, Chamfer, ...]` à `[..., Pocket, SpikePad, SpikeSketch, Chamfer, ...]`, et `Chamfer.BaseFeature` passe automatiquement de `Pocket` à `SpikePad`.
- **Limitation notée** : `insertObject` ne déplace PAS le Tip automatiquement (documenté explicitement dans le docstring C++ : *"the method doesn't modify the Tip unlike addObject()"*) — ATPD doit gérer `Body.Tip = nouvelle_feature` lui-même si l'insertion doit devenir le nouveau point de reprise actif.
- **Limitation notée** : les méthodes C++ `isAfterInsertPoint()`, `getPrevSolidFeature()`, `getNextSolidFeature()` existent dans `Body.h` mais ne sont **pas exposées en Python** (seule `insertObject` l'est, vérifié dans `BodyPyImp.cpp`). ATPD devra réimplémenter cette logique en Python (parcours de `Body.Group`, filtrage par `TypeId`) plutôt que réutiliser ces helpers natifs.

## Question 2 — Que deviennent les features après un Tip reculé ?

**Réponse : elles restent dans le document, inchangées, simplement non "actives".**

Après `body.Tip = Pocket` (recul depuis `Fillet`, la dernière feature) puis `doc.recompute()` :
- Toutes les features situées après `Pocket` dans la chaîne (`Chamfer`, `Pad003`, `Chamfer001`, `PolarPattern`, `Fillet`, etc.) restent présentes dans `Body.Group`, avec **leur dernier état calculé intact** : `State=['Up-to-date']`, `isValid()=True`, `Shape` toujours non-nul.
- FreeCAD ne les supprime pas, ne les invalide pas, ne les recalcule pas non plus pour refléter "comme si la chaîne s'arrêtait à Pocket" — elles gardent simplement leur shape mise en cache de *avant* le déplacement du Tip.
- Aucune perte de données observée à cette étape.

## Question 3 — Recalcul propre en ramenant le Tip à la fin ?

**Réponse : oui pour l'intégrité du graphe de document, mais avec la casse réelle du Topological Naming Problem.**

Après avoir inséré `SpikePad` entre `Pocket` et `Chamfer`, puis ramené `Body.Tip` à la feature d'origine (`Fillet`) et recalculé :
- Aucune exception fatale, aucun crash, `doc.recompute()` se termine normalement.
- `Body.Group` reste cohérent : 17 objets (15 d'origine + 2 nouveaux), ordre correct.
- **Mais** : `Chamfer` (qui référençait un edge spécifique de la shape produite par `Pocket`, avant l'insertion) devient invalide : `State=['Touched', 'Invalid']`, `isValid()=False`. La shape produite par `SpikePad` (le nouveau feature inséré) a une numérotation de topologie différente de celle de `Pocket`, donc la référence d'edge stockée par `Chamfer` (`Edge48`) ne pointe plus vers la bonne géométrie.
- Toutes les features **après** `Chamfer` dans la chaîne restent `Up-to-date` (elles héritent de la shape invalide de `Chamfer` en cascade côté kernel, mais FreeCAD ne les marque pas explicitement invalides tant qu'elles n'ont pas elles-mêmes une référence cassée — comportement à surveiller/tester davantage si on va plus loin que ce spike).

## Question 4 — Limitations exactes rencontrées

1. **Topological Naming Problem (TNP)** — la limitation principale. Message d'erreur exact obtenu :
   ```
   <PropertyLinks> PropertyLinks.cpp(514): copy#Chamfer.Base missing element reference copy#SpikePad ;#258:1;:He43,E.Edge48
   <Exception> FeatureDressUp.cpp(217): Invalid edge link: ;#258:1;:He43,E.Edge48
   Chamfer: Invalid edge link: ;#258:1;:He43,E.Edge48
   ```
   C'est un problème connu et documenté de FreeCAD (voir `TestTopologicalNamingProblem.py` dans la suite de tests native de FreeCAD, tag 1.1.1) — pas spécifique à ATPD, pas spécifique à `insertObject`. Un utilisateur FreeCAD natif utilisant la barre de reprise native rencontre exactement le même risque.
2. **`insertObject` ne déplace pas le Tip** — omission facile à manquer, doit être gérée explicitement côté ATPD.
3. **API d'introspection C++ non exposée en Python** (`isAfterInsertPoint`, `getPrevSolidFeature`, `getNextSolidFeature`) — ATPD devra les réimplémenter en Python.
4. Aucune corruption, perte de données, ou crash observé à aucune étape — le risque est localisé et prévisible (features Dressup référençant des edges/faces en aval du point d'insertion), pas systémique.

## Recommandation pour la suite de M3

- Implémenter la barre de reprise via `Body.Tip` + `Body.insertObject`, en gérant nous-mêmes le déplacement du Tip après insertion.
- Réimplémenter en Python un équivalent simple de `getNextSolidFeature`/`getPrevSolidFeature` (filtrer `Body.Group` sur les TypeId de features solides, réutilisable avec la logique déjà en place dans `atpd/tree/model.py`).
- **Avant** d'insérer une feature à un point de reprise, analyser (via `find_dependents`, déjà existant) si des features Dressup se trouvent en aval, et avertir l'utilisateur du risque de casse topologique — même pattern que l'avertissement Suppress/Delete déjà implémenté, pas de blocage strict.
- Ne pas chercher à "résoudre" le TNP nous-mêmes (hors scope, problème kernel amont) — juste le rendre visible et gérable pour l'utilisateur.
