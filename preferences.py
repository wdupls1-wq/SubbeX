from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from Foundation import NSUserDefaults

from .models import DEFAULT_MODEL_ID, MODEL_BY_ID, Preferences


DEFAULT_OUTPUT_ROOT = Path.home() / "Movies" / "SubbeX Exports"


class PreferenceStore:
    KEY_MODEL_ID = "model_id"
    KEY_OFFSET_SECONDS = "offset_seconds"
    KEY_OUTPUT_ROOT = "output_root"
    KEY_MOVE_ORIGINAL = "move_original"

    def __init__(self) -> None:
        self.defaults = NSUserDefaults.standardUserDefaults()

    def load(self) -> Preferences:
        model_id = self.defaults.stringForKey_(self.KEY_MODEL_ID) or DEFAULT_MODEL_ID
        if model_id not in MODEL_BY_ID:
            model_id = DEFAULT_MODEL_ID

        offset_value = self.defaults.objectForKey_(self.KEY_OFFSET_SECONDS)
        offset_seconds = float(offset_value) if offset_value is not None else 0.0

        output_root_value = self.defaults.stringForKey_(self.KEY_OUTPUT_ROOT)
        output_root = Path(output_root_value).expanduser() if output_root_value else DEFAULT_OUTPUT_ROOT

        move_original = bool(self.defaults.boolForKey_(self.KEY_MOVE_ORIGINAL))
        return Preferences(
            model_id=model_id,
            offset_seconds=offset_seconds,
            output_root=output_root,
            move_original=move_original,
        )

    def save(self, preferences: Preferences) -> Preferences:
        self.defaults.setObject_forKey_(preferences.model_id, self.KEY_MODEL_ID)
        self.defaults.setDouble_forKey_(preferences.offset_seconds, self.KEY_OFFSET_SECONDS)
        self.defaults.setObject_forKey_(str(preferences.output_root), self.KEY_OUTPUT_ROOT)
        self.defaults.setBool_forKey_(preferences.move_original, self.KEY_MOVE_ORIGINAL)
        self.defaults.synchronize()
        return preferences

    def update_model(self, preferences: Preferences, model_id: str) -> Preferences:
        return self.save(replace(preferences, model_id=model_id))

    def update_offset(self, preferences: Preferences, offset_seconds: float) -> Preferences:
        return self.save(replace(preferences, offset_seconds=offset_seconds))

    def update_output_root(self, preferences: Preferences, output_root: Path) -> Preferences:
        return self.save(replace(preferences, output_root=output_root.expanduser()))

    def update_move_original(self, preferences: Preferences, move_original: bool) -> Preferences:
        return self.save(replace(preferences, move_original=move_original))

