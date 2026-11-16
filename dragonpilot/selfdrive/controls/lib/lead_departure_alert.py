"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and other contributors.

Lead vehicle departure alert adapted for dragonpilot under the MIT License.
"""

from cereal import car
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL

LEAD_DEPART_DIST_THRESHOLD = 1.0
LEAD_DEPART_TRIGGER_TIME = 0.3
LEAD_DEPART_ARM_TIME = 1.0
LEAD_DEPART_MAX_DISTANCE = 8.0
STOPPED_CONFIRMATION_TIME = 2.0
PARAM_REFRESH_FRAMES = round(3.0 / DT_MDL)


class LeadDepartureState:
  INACTIVE = 0
  ARMED = 1
  CONSUMED = 2


class LeadDepartureAlert:
  def __init__(self, params=None):
    self._params = params if params is not None else Params()
    self.enabled = self._params.get_bool("dp_ui_lead_depart_alert")
    self.frame = 0
    self.last_moving_frame = None
    self._reset()

  def _reset(self):
    self.state = LeadDepartureState.INACTIVE
    self.last_allowed = False
    self.confirmed_lead = False
    self.arm_timer = 0
    self.trigger_timer = 0
    self.last_lead_distance = 0.0

  def update(self, car_state, car_control, radar_state, *, inputs_valid=True) -> bool:
    self.frame += 1
    if self.frame % PARAM_REFRESH_FRAMES == 0:
      self.enabled = self._params.get_bool("dp_ui_lead_depart_alert")

    moving = not car_state.standstill and car_state.vEgo > 0.1
    if inputs_valid and moving:
      self.last_moving_frame = self.frame

    stopped_long_enough = (self.last_moving_frame is not None and
                          (self.frame - self.last_moving_frame) * DT_MDL >= STOPPED_CONFIRMATION_TIME)
    in_drive = car_state.gearShifter == car.CarState.GearShifter.drive
    allowed = (self.enabled and inputs_valid and in_drive and not moving and
               not car_state.gasPressed and not car_control.enabled and stopped_long_enough)
    if not allowed:
      self._reset()
      return False

    if self.state == LeadDepartureState.CONSUMED:
      return False

    lead = radar_state.leadOne
    has_lead = lead.status and lead.dRel > 0.0
    close_lead = has_lead and lead.dRel < LEAD_DEPART_MAX_DISTANCE
    if not self.last_allowed:
      self.last_allowed = True
      self.confirmed_lead = close_lead

    if self.state == LeadDepartureState.INACTIVE:
      self.arm_timer = self.arm_timer + 1 if self.confirmed_lead and close_lead else 0
      if self.arm_timer * DT_MDL >= LEAD_DEPART_ARM_TIME:
        self.state = LeadDepartureState.ARMED
        self.last_lead_distance = lead.dRel
      return False

    if not has_lead:
      # A dropped track must not be mistaken for a lead driving away.
      self._reset()
      self.last_allowed = True
      return False

    self.last_lead_distance = min(self.last_lead_distance, lead.dRel)
    if lead.dRel - self.last_lead_distance > LEAD_DEPART_DIST_THRESHOLD:
      self.trigger_timer += 1
    else:
      self.trigger_timer = 0

    if self.trigger_timer * DT_MDL >= LEAD_DEPART_TRIGGER_TIME:
      self.state = LeadDepartureState.CONSUMED
      return True
    return False
