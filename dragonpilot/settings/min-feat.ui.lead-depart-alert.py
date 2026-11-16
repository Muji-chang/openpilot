from dragonpilot.settings import tr

ITEMS = [
  {
    "section": "UI",
    "key": "dp_ui_lead_depart_alert",
    "type": "toggle_item",
    "title": lambda: tr("Lead Departure Alert"),
    "description": lambda: tr("Play a chime and show an alert when the lead vehicle drives away while your vehicle is stopped."),
    "default": "1",
    "flags": "PERSISTENT",
    "param_type": "BOOL",
  },
]
