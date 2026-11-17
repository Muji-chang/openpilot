import math

from openpilot.common.constants import CV
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import (
  get_safe_obstacle_distance, get_stopped_equivalence_factor, get_T_FOLLOW,
)

MIN_COAST_SPEED = 15.0 * CV.KPH_TO_MS
MAX_COAST_SPEED = 50.0 * CV.KPH_TO_MS
MIN_MOVING_LEAD_SPEED = 10.0 * CV.KPH_TO_MS
MAX_APPROACH_SPEED_DROP = 3.0 * CV.KPH_TO_MS
MIN_COAST_ACCEL = -0.50  # m/s²
MAX_COAST_ACCEL = -0.18
MIN_HEADWAY = 2.5  # s
MIN_TTC = 8.0
EXTRA_FOLLOW_GAP = 3.0  # m beyond the MPC following distance
MIN_LEAD_ACCEL = -0.4  # m/s²
CLOSING_SPEED_DEADBAND = 0.3  # m/s


def get_low_speed_coast_profile(v_ego, v_cruise, coast_accel, radar_state, personality) -> tuple[float, float] | None:
  """Return a coasting cruise reference when approaching a moving lead with room to spare."""
  if (not MIN_COAST_SPEED <= v_ego < MAX_COAST_SPEED or
      not MIN_COAST_ACCEL <= coast_accel <= MAX_COAST_ACCEL or
      not math.isfinite(v_cruise) or v_ego > v_cruise):
    return None

  leads = [lead for lead in (radar_state.leadOne, radar_state.leadTwo) if lead.status]
  if not leads:
    return None

  safe_obstacle_distance = get_safe_obstacle_distance(v_ego, get_T_FOLLOW(personality))
  speed_drop = 0.0
  for lead in leads:
    if (not all(math.isfinite(x) for x in (lead.dRel, lead.vLead, lead.aLeadK)) or
        lead.vLead < MIN_MOVING_LEAD_SPEED or lead.aLeadK < MIN_LEAD_ACCEL):
      return None

    min_gap = max(v_ego * MIN_HEADWAY,
                  safe_obstacle_distance - get_stopped_equivalence_factor(lead.vLead) + EXTRA_FOLLOW_GAP)
    closing_speed = v_ego - lead.vLead
    if lead.dRel < max(min_gap, closing_speed * MIN_TTC):
      return None
    speed_drop = max(speed_drop, closing_speed - CLOSING_SPEED_DEADBAND)

  if speed_drop <= 0.0:
    return None
  return v_ego - min(speed_drop, MAX_APPROACH_SPEED_DROP), coast_accel
