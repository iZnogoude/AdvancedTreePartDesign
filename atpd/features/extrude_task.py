"""FreeCAD-native Task Panel and command for the unified Extrusion dialog.

Selection reading (FreeCADGui.Selection) lives here, not in
extrude_model.py, which stays Qt/Gui-free.
"""

import FreeCAD as App
import FreeCADGui as Gui
from PySide6 import QtWidgets

from atpd.tree.panel import (
    _active_body,
    get_panel,
    show_only_tip_feature,
    warn_downstream_dressup_risk,
)

from .extrude_model import ADD_MATERIAL, REMOVE_MATERIAL, create_extrusion


def resolve_profile():
    """Read the current FreeCADGui selection for an extrusion profile.

    Returns a (profile, sketch, error_message) tuple:
    - profile: the object to assign to Pad/Pocket.Profile - either the
      selected sketch, or a (face_object, (subelement_name,)) tuple.
    - sketch: the sketch to add to the Body's Group, or None when the
      profile is a face on an existing solid (nothing new to add).
    - error_message: None on success, else a string to show the user.
    """
    selection = Gui.Selection.getSelectionEx()
    if not selection:
        return None, None, "Select a sketch or a planar face to extrude."

    sel = selection[0]
    obj = sel.Object
    if obj.TypeId == "Sketcher::SketchObject":
        return obj, obj, None

    sub_names = sel.SubElementNames
    if sub_names and sub_names[0].startswith("Face"):
        return (obj, (sub_names[0],)), None, None

    return None, None, "Select a sketch or a planar face to extrude."


class ExtrudeTaskPanel:
    """Task Panel offering Add/Remove material and Existing/New body modes.

    Only borgne (simple length) and symmetric directions are offered -
    two-directions and up-to-face are deferred to a later iteration, and
    the thin/reinforce option is deferred to a separate PR (see the M4
    tracking issue).
    """

    def __init__(self, profile, sketch):
        self.profile = profile
        self.sketch = sketch

        self.form = QtWidgets.QWidget()
        self.form.setWindowTitle("Extrusion")
        layout = QtWidgets.QVBoxLayout(self.form)

        layout.addWidget(QtWidgets.QLabel(self._profile_description()))

        body_group = QtWidgets.QGroupBox("Target")
        body_layout = QtWidgets.QVBoxLayout(body_group)
        self.existing_body_radio = QtWidgets.QRadioButton("Add to existing body")
        self.new_body_radio = QtWidgets.QRadioButton("New body")
        self.existing_body_radio.setChecked(True)
        body_layout.addWidget(self.existing_body_radio)
        body_layout.addWidget(self.new_body_radio)
        layout.addWidget(body_group)

        mode_group = QtWidgets.QGroupBox("Mode")
        mode_layout = QtWidgets.QVBoxLayout(mode_group)
        self.add_material_radio = QtWidgets.QRadioButton("Add material")
        self.remove_material_radio = QtWidgets.QRadioButton("Remove material")
        self.add_material_radio.setChecked(True)
        mode_layout.addWidget(self.add_material_radio)
        mode_layout.addWidget(self.remove_material_radio)
        layout.addWidget(mode_group)

        length_form = QtWidgets.QFormLayout()
        self.length_spin = QtWidgets.QDoubleSpinBox()
        self.length_spin.setDecimals(2)
        self.length_spin.setRange(0.01, 1_000_000.0)
        self.length_spin.setValue(10.0)
        self.length_spin.setSuffix(" mm")
        length_form.addRow("Length", self.length_spin)
        layout.addLayout(length_form)

        self.symmetric_check = QtWidgets.QCheckBox("Symmetric (both directions)")
        layout.addWidget(self.symmetric_check)
        layout.addStretch()

        self.new_body_radio.toggled.connect(self._on_body_target_changed)
        self._on_body_target_changed()

    def _profile_description(self) -> str:
        if self.profile is self.sketch:
            return f'Profile: sketch "{self.profile.Label}"'
        face_obj, sub_names = self.profile
        return f'Profile: face "{sub_names[0]}" of "{face_obj.Label}"'

    def _on_body_target_changed(self) -> None:
        """A new Body's first feature can only add material (there's
        nothing yet to remove it from) - disable and force that choice
        while "New body" is selected."""
        is_new_body = self.new_body_radio.isChecked()
        self.add_material_radio.setEnabled(not is_new_body)
        self.remove_material_radio.setEnabled(not is_new_body)
        if is_new_body:
            self.add_material_radio.setChecked(True)

    def gather_inputs(self):
        """Read the widget state into the plain values create_extrusion()
        needs - split out from accept() so it can be exercised in a test
        without touching Gui.Control (unavailable under FreeCADCmd)."""
        mode = REMOVE_MATERIAL if self.remove_material_radio.isChecked() else ADD_MATERIAL
        return {
            "mode": mode,
            "length": self.length_spin.value(),
            "midplane": self.symmetric_check.isChecked(),
            "body_is_new": self.new_body_radio.isChecked(),
        }

    def getStandardButtons(self):
        return int(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )

    def accept(self) -> bool:
        doc = App.ActiveDocument
        inputs = self.gather_inputs()
        body_is_new = inputs.pop("body_is_new")

        if body_is_new:
            body = doc.addObject("PartDesign::Body", "Body")
        else:
            body = _active_body()
            if body is None:
                QtWidgets.QMessageBox.critical(
                    Gui.getMainWindow(), "Extrusion", "No active PartDesign Body found."
                )
                Gui.Control.closeDialog()
                return True
            if not warn_downstream_dressup_risk(Gui.getMainWindow(), body):
                Gui.Control.closeDialog()
                return True

        try:
            feature = create_extrusion(
                doc, body, self.profile, sketch=self.sketch, body_is_new=body_is_new, **inputs
            )
        except Exception as exc:
            App.Console.PrintError(f"ATPD extrude: failed to create feature: {exc}\n")
            QtWidgets.QMessageBox.critical(
                Gui.getMainWindow(), "Extrusion", f"Failed to create extrusion:\n{exc}"
            )
            Gui.Control.closeDialog()
            return True

        show_only_tip_feature(feature)
        panel = get_panel()
        if panel is not None:
            panel.refresh()

        Gui.Control.closeDialog()
        return True

    def reject(self) -> bool:
        Gui.Control.closeDialog()
        return True
