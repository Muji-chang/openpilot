from types import SimpleNamespace

from cereal import car
from openpilot.common.realtime import DT_MDL
from dragonpilot.selfdrive.controls.lib.lead_departure_alert import LeadDepartureAlert, LeadDepartureState


class FakeParams:
  def __init__(self, enabled=True):
    self.enabled = enabled

  def get_bool(self, key):
    assert key == "dp_ui_lead_depart_alert"
    return self.enabled


def make_messages(*, moving=False, gas_pressed=False, controls_enabled=False, lead_status=True, lead_distance=5.0,
                  gear_shifter=car.CarState.GearShifter.drive):
  car_state = SimpleNamespace(
    standstill=not moving,
    vEgo=1.0 if moving else 0.0,
    gasPressed=gas_pressed,
    gearShifter=gear_shifter,
  )
  car_control = SimpleNamespace(enabled=controls_enabled)
  radar_state = SimpleNamespace(leadOne=SimpleNamespace(status=lead_status, dRel=lead_distance))
  return car_state, car_control, radar_state


def update(alert, count=1, **kwargs):
  triggered = False
  for _ in range(count):
    triggered = alert.update(*make_messages(**kwargs)) or triggered
  return triggered


def arm_alert(alert):
  update(alert, count=2, moving=True)
  update(alert, count=int(2.0 / DT_MDL) + int(1.0 / DT_MDL) + 2)
  assert alert.state == LeadDepartureState.ARMED


def test_lead_departure_triggers_once():
  alert = LeadDepartureAlert(FakeParams())
  arm_alert(alert)

  trigger_frames = int(0.3 / DT_MDL) + 2
  assert update(alert, count=trigger_frames, lead_distance=6.1)
  assert alert.state == LeadDepartureState.CONSUMED
  assert not update(alert, count=trigger_frames, lead_distance=7.0)


def test_lead_departure_requires_enabled_disengaged_controls():
  disabled_alert = LeadDepartureAlert(FakeParams(enabled=False))
  update(disabled_alert, count=2, moving=True)
  update(disabled_alert, count=int(4.0 / DT_MDL))
  assert disabled_alert.state == LeadDepartureState.INACTIVE

  engaged_alert = LeadDepartureAlert(FakeParams())
  update(engaged_alert, count=2, moving=True)
  update(engaged_alert, count=int(4.0 / DT_MDL), controls_enabled=True)
  assert engaged_alert.state == LeadDepartureState.INACTIVE


def test_lead_departure_requires_drive_gear():
  alert = LeadDepartureAlert(FakeParams())
  update(alert, count=2, moving=True, gear_shifter=car.CarState.GearShifter.neutral)
  update(alert, count=int(4.0 / DT_MDL), gear_shifter=car.CarState.GearShifter.neutral)
  assert alert.state == LeadDepartureState.INACTIVE

  update(alert, count=int(4.0 / DT_MDL), gear_shifter=car.CarState.GearShifter.drive)
  assert alert.state == LeadDepartureState.ARMED

  update(alert, gear_shifter=car.CarState.GearShifter.reverse)
  assert alert.state == LeadDepartureState.INACTIVE


def test_lead_departure_requires_continuous_distance_change():
  alert = LeadDepartureAlert(FakeParams())
  arm_alert(alert)

  short_pulse_frames = max(1, int(0.3 / DT_MDL) - 1)
  assert not update(alert, count=short_pulse_frames, lead_distance=6.1)
  assert not update(alert, lead_distance=5.5)
  assert alert.state == LeadDepartureState.ARMED
