"""
Copyright (c) 2025, Rick Lan

Overtaking and early coasting adapted from the previous mujitest branch.
"""

import math
import time

import numpy as np

from openpilot.common.constants import CV

MIN_SPEED_ENABLE = 50.0 * CV.KPH_TO_MS
MIN_SPEED_DISABLE = 40.0 * CV.KPH_TO_MS
OVERTAKE_THRESHOLD = 2.0 * CV.KPH_TO_MS
HYSTERESIS_OFFSET = 1.0 * CV.KPH_TO_MS
OVERSPEED_INACTIVE_MARGIN = 20.0 * CV.KPH_TO_MS
OVERSPEED_ACTIVE_MARGIN = 25.0 * CV.KPH_TO_MS

TTC_THRESHOLD = 3.0
LEAD_COOLDOWN_TIME = 0.5
EMERGENCY_RELATIVE_SPEED = 10.0
EMERGENCY_DECEL_THRESHOLD = -1.5
COASTABLE_DECEL = -1.0
SPEED_BP = [0., 10., 20., 30.]
MIN_DIST_V = [5., 10., 15., 20.]

PITCH_SMOOTH_ALPHA_UP = 0.30
PITCH_SMOOTH_ALPHA_DOWN = 0.15
PITCH_DOWNHILL_THRESHOLD = -0.030

COAST_DEADBAND = 0.8  # m/s from set speed
RAMP_OFF_RANGE = 5.0  # m/s below set speed


class OCM:
  def __init__(self):
    self.active = False
    self._speed_allowed = False
    self._last_lead_time = float('-inf')
    self._pitch: float | None = None

  def update(self, allowed, orientation_ned, lead, v_ego, v_cruise):
    if v_ego >= MIN_SPEED_ENABLE:
      self._speed_allowed = True
    elif v_ego <= MIN_SPEED_DISABLE:
      self._speed_allowed = False

    if not allowed or len(orientation_ned) != 3 or not math.isfinite(orientation_ned[1]):
      self.active = False
      self._pitch = None
      return

    pitch = orientation_ned[1]
    if self._pitch is None:
      self._pitch = pitch
    else:
      alpha = PITCH_SMOOTH_ALPHA_UP if pitch > self._pitch else PITCH_SMOOTH_ALPHA_DOWN
      self._pitch += alpha * (pitch - self._pitch)

    now = time.monotonic()
    if lead.status:
      closing_speed = v_ego - lead.vLead
      ttc = lead.dRel / max(closing_speed, 0.1)
      min_distance = np.interp(v_ego, SPEED_BP, MIN_DIST_V)
      if (ttc < TTC_THRESHOLD or closing_speed > EMERGENCY_RELATIVE_SPEED or
          (closing_speed > 0.0 and lead.dRel < min_distance)):
        self._last_lead_time = now

    speed_over_cruise = (v_ego > v_cruise + HYSTERESIS_OFFSET if self.active
                         else v_ego >= v_cruise + OVERTAKE_THRESHOLD)
    max_overspeed = OVERSPEED_ACTIVE_MARGIN if self.active else OVERSPEED_INACTIVE_MARGIN
    self.active = (self._speed_allowed and speed_over_cruise and
                   v_ego <= v_cruise + max_overspeed and self._pitch >= PITCH_DOWNHILL_THRESHOLD and
                   now - self._last_lead_time >= LEAD_COOLDOWN_TIME)

  def get_accel_target(self, a_target, planned_accels, coast_accel):
    if not self.active:
      return a_target
    if a_target <= COASTABLE_DECEL or np.min(planned_accels) < EMERGENCY_DECEL_THRESHOLD:
      self.active = False
      return a_target

    # Target the planner's estimate of free rolling acceleration instead of holding speed.
    return float(np.clip(coast_accel, COASTABLE_DECEL, 0.0))


def limit_accel_for_early_coast(v_ego, v_cruise, accel_limit, lead):
  """Taper throttle near set speed or when catching a slower lead."""
  if lead.status and lead.dRel > 10.0:
    closing_threshold = np.interp(v_ego, [16.0, 22.0], [0.5, 1.0])
    if lead.vRel < -closing_threshold:
      return min(accel_limit, -0.001)

  speed_error = v_cruise - v_ego
  ramp = np.clip(speed_error / RAMP_OFF_RANGE, 0.0, 1.0)
  limit = max(0.0, accel_limit) * ramp
  if abs(speed_error) < COAST_DEADBAND:
    limit = max(0.05, limit * 0.25)
  return min(accel_limit, limit)
