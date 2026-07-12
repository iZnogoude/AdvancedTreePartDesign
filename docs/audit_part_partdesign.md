# Audit des commandes Part / Part Design (FreeCAD 1.1.1)

Source : code source officiel FreeCAD, tag `1.1.1` (`src/Mod/Part/Gui/Workbench.cpp`, `src/Mod/PartDesign/Gui/Workbench.cpp` et fichiers `Command*.cpp`/`.py` associés). Liste exhaustive des commandes réellement présentes dans les barres d'outils (pas le menu complet — certaines commandes menu-only comme `Part_BoxSelection` ou `Materials_InspectMaterial` n'apparaissent dans aucune barre d'outils et sont donc exclues).

Note : dans le CDC, les 4 barres Part Design attendues (Modeling, Dressup, Transformation, Helpers) correspondent exactement aux 4 barres réelles de FreeCAD 1.1 : *Part Design Modeling Features*, *Part Design Dress-Up Features*, *Part Design Transformation Features*, *Part Design Helper Features*. Pour Part, les 3 barres réelles s'appellent *Solids*, *Part Tools*, *Boolean Tools* (et non "Modeling/Sketch-based/Dressup/Transform/Boolean" — cette dernière nomenclature ne correspond à aucune barre d'outils réelle de Part 1.1).

Certains boutons sont des menus déroulants regroupant plusieurs commandes distinctes (ex. `Part_CompOffset` → Offset 3D / Offset 2D) ; chaque sous-commande est listée individuellement avec une note technique le signalant.

Points à noter :
- `PartDesign_InvoluteGear` et `PartDesign_Sprocket` apparaissent dans le menu Part Design mais **pas** dans une barre d'outils (confirmé dans `Workbench.cpp`) → exclus du tableau.
- Plusieurs commandes affichées dans les barres Part/Part Design appartiennent en réalité au module **Sketcher** (`Sketcher_NewSketch`, `Sketcher_MapSketch`, `Sketcher_EditSketch`, `Sketcher_ValidateSketch`) — elles sont incluses puisqu'elles sont physiquement dans ces barres, avec une note technique le signalant (rappel CLAUDE.md : Sketcher hors scope sauf fonction Texte).
- `Part_CheckGeometry` apparaît dans les deux barres (Part "Boolean Tools" et Part Design "Helper") — listé deux fois avec note.

## Part Workbench — barre "Solids"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part | Part_Box | Creates a solid cube | | | | | |
| Part | Part_Cylinder | Creates a solid cylinder | | | | | |
| Part | Part_Sphere | Creates a solid sphere | | | | | |
| Part | Part_Cone | Creates a solid cone | | | | | |
| Part | Part_Torus | Creates a solid torus | | | | | |
| Part | Part_Tube | Creates a tube | | | | | |
| Part | Part_Primitives | Creates solid geometric primitives parametrically | Dialogue avancé multi-formes (ellipsoïde, prisme, hélice, spirale, polygone régulier, etc.) | | | | |
| Part | Part_Builder | Advanced utility to create shapes | Outil bas niveau de construction (vertex/edge/wire/face) | | | | |

## Part Workbench — barre "Part Tools"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part | Sketcher_NewSketch | Creates a new sketch | Commande du module Sketcher (visible seulement si Sketcher est chargé) | | | | |
| Part | Part_Extrude | Extrudes the selected sketch or profile | | | | | |
| Part | Part_Revolve | Revolves the selected shape | | | | | |
| Part | Part_Mirror | Mirrors the selected shape | | | | | |
| Part | Part_Scale | Scales the selected shape | | | | | |
| Part | Part_Fillet | Fillets the selected edges of a shape | | | | | |
| Part | Part_Chamfer | Chamfers the selected edges of a shape | | | | | |
| Part | Part_MakeFace | Creates a face from the selected wires (e.g. from a sketch) | | | | | |
| Part | Part_RuledSurface | Creates a ruled surface between 2 selected wires | | | | | |
| Part | Part_Loft | Lofts the selected profiles | | | | | |
| Part | Part_Sweep | Sweeps profiles along a wire | | | | | |
| Part | Part_Section | Sections 2 selected shapes | | | | | |
| Part | Part_CrossSections | Creates cross-sections | | | | | |
| Part | Part_Offset | Offsets shapes in 3D | Sous-commande du bouton groupé Part_CompOffset | | | | |
| Part | Part_Offset2D | Offsets planar shapes in 2D | Sous-commande du bouton groupé Part_CompOffset | | | | |
| Part | Part_Thickness | Removes the selected faces and offsets the remaining shape outward to add thickness | | | | | |
| Part | Part_ProjectionOnSurface | Projects edges, wires, or faces of one shape onto a face of another shape | | | | | |
| Part | Part_ColorPerFace | Sets the appearance of individual faces of the selected object | Commande d'apparence/affichage, pas de modeling | | | | |

## Part Workbench — barre "Boolean Tools"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part | Part_Compound | Compounds the selected shapes | Sous-commande du bouton groupé Part_CompCompoundTools | | | | |
| Part | Part_ExplodeCompound | Splits up a compound of shapes into separate objects, creating a compound filter for each shape | Sous-commande du bouton groupé Part_CompCompoundTools | | | | |
| Part | Part_CompoundFilter | Filters out objects from the selected compound by characteristics like volume, area, or length | Sous-commande du bouton groupé Part_CompCompoundTools | | | | |
| Part | Part_Boolean | Applies a boolean operations with the selected shapes | | | | | |
| Part | Part_Cut | Cuts 2 selected shapes | | | | | |
| Part | Part_Fuse | Unites the selected shapes | | | | | |
| Part | Part_Common | Intersects the selected shapes | | | | | |
| Part | Part_JoinConnect | Fuses shapes, taking care to preserve voids | Sous-commande du bouton groupé Part_CompJoinFeatures | | | | |
| Part | Part_JoinEmbed | Fuses one shape into another, taking care to preserve voids | Sous-commande du bouton groupé Part_CompJoinFeatures | | | | |
| Part | Part_JoinCutout | Creates a cutout in the selected shape to fit another shape | Sous-commande du bouton groupé Part_CompJoinFeatures | | | | |
| Part | Part_BooleanFragments | Creates a boolean union sliced at the intersections of the selected shapes | Sous-commande du bouton groupé Part_CompSplitFeatures | | | | |
| Part | Part_SliceApart | Slices the selected object by other objects, and splits it apart | Sous-commande du bouton groupé Part_CompSplitFeatures | | | | |
| Part | Part_Slice | Slices the selected object using other objects as cutting tools, storing results in one compound | Sous-commande du bouton groupé Part_CompSplitFeatures | | | | |
| Part | Part_XOR | Performs an exclusive-OR boolean operation with two or more selected objects | Sous-commande du bouton groupé Part_CompSplitFeatures | | | | |
| Part | Part_CheckGeometry | Analyzes the selected shapes for errors | | | | | |
| Part | Part_Defeaturing | Removes the selected features from a shape | | | | | |

## Part Design Workbench — barre "Part Design Helper Features"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part Design | PartDesign_Body | Creates a new body and activates it | | | | | |
| Part Design | PartDesign_NewSketch | Creates a new sketch | Sous-commande du bouton groupé PartDesign_CompSketches | | | | |
| Part Design | Sketcher_MapSketch | Attaches a sketch to the selected geometry element | Sous-commande du bouton groupé PartDesign_CompSketches ; commande du module Sketcher | | | | |
| Part Design | Sketcher_EditSketch | Opens the selected sketch for editing | Sous-commande du bouton groupé PartDesign_CompSketches ; commande du module Sketcher | | | | |
| Part Design | Sketcher_ValidateSketch | Validates a sketch by checking for missing coincidences, redundant constraints, etc. | Commande du module Sketcher | | | | |
| Part Design | Part_CheckGeometry | Analyzes the selected shapes for errors | Commande partagée avec le module Part | | | | |
| Part Design | PartDesign_SubShapeBinder | Creates a reference to geometry from one or more objects, usable inside or outside a body (tracks placement, cross-document) | | | | | |
| Part Design | PartDesign_Clone | Copies a solid object parametrically as the base feature of a new body | | | | | |

## Part Design Workbench — barre "Part Design Modeling Features"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part Design | PartDesign_Pad | Extrudes the selected sketch or profile and adds it to the body | | | | | |
| Part Design | PartDesign_Revolution | Revolves the selected sketch or profile around a line or axis and adds it to the body | | | | | |
| Part Design | PartDesign_AdditiveLoft | Lofts the selected sketch or profile along a path and adds it to the body | | | | | |
| Part Design | PartDesign_AdditivePipe | Sweeps the selected sketch or profile along a path and adds it to the body | | | | | |
| Part Design | PartDesign_AdditiveHelix | Sweeps the selected sketch or profile along a helix and adds it to the body | | | | | |
| Part Design | PartDesign_CompPrimitiveAdditive | Creates an additive primitive | Dialogue multi-formes (box/cylindre/sphère/cône/tore/coin), pas un dropdown de sous-commandes | | | | |
| Part Design | PartDesign_Pocket | Extrudes the selected sketch or profile and removes it from the body | | | | | |
| Part Design | PartDesign_Hole | Creates holes in the active body at the center points of circles or arcs of the selected sketch or profile | | | | | |
| Part Design | PartDesign_Groove | Revolves the sketch or profile around a line or axis and removes it from the body | | | | | |
| Part Design | PartDesign_SubtractiveLoft | Lofts the selected sketch or profile along a path and removes it from the body | | | | | |
| Part Design | PartDesign_SubtractivePipe | Sweeps the selected sketch or profile along a path and removes it from the body | | | | | |
| Part Design | PartDesign_SubtractiveHelix | Sweeps the selected sketch or profile along a helix and removes it from the body | | | | | |
| Part Design | PartDesign_CompPrimitiveSubtractive | Creates a subtractive primitive | Dialogue multi-formes, pas un dropdown de sous-commandes | | | | |
| Part Design | PartDesign_Boolean | Applies boolean operations with the selected objects and the active body | | | | | |

## Part Design Workbench — barre "Part Design Dress-Up Features"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part Design | PartDesign_Fillet | Applies a fillet to the selected edges or faces | | | | | |
| Part Design | PartDesign_Chamfer | Applies a chamfer to the selected edges or faces | | | | | |
| Part Design | PartDesign_Draft | Applies a draft to the selected faces | | | | | |
| Part Design | PartDesign_Thickness | Applies thickness and removes the selected faces | | | | | |

## Part Design Workbench — barre "Part Design Transformation Features"

| Atelier | Commande | Description courte | Notes techniques | Garder | Améliorer | Wrapper | Exclure |
|---|---|---|---|---|---|---|---|
| Part Design | PartDesign_Mirrored | Mirrors the selected features or active body | | | | | |
| Part Design | PartDesign_LinearPattern | Duplicates the selected features or the active body in a linear pattern | | | | | |
| Part Design | PartDesign_PolarPattern | Duplicates the selected features or the active body in a circular pattern | | | | | |
| Part Design | PartDesign_MultiTransform | Applies multiple transformations to the selected features or active body | | | | | |

---

**Total : 42 commandes Part + 30 commandes Part Design = 72 lignes.**
