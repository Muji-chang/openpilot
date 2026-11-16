from dragonpilot.settings import tr

ITEMS = [
  {
    "section": "Longitudinal",
    "key": "dp_lon_ocm",
    "type": "toggle_item",
    "title": lambda: tr("Overtaking Coasting Mode (OCM)"),
    "description": lambda: tr("Coast toward the set speed after overtaking. Starts at 50 km/h or above and at least 2 km/h over the set speed."),
    "condition": "openpilotLongitudinalControl",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
  },
  {
    "section": "Longitudinal",
    "key": "dp_lon_early_coast",
    "type": "toggle_item",
    "title": lambda: tr("Early Coasting"),
    "description": lambda: tr("Ease off the accelerator near the set speed or when approaching a slower vehicle ahead."),
    "condition": "openpilotLongitudinalControl",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
    "default": "0",
  },
]
