"""Protective separation distance (Section 9.3). New in v2.0.0.

A reviewer asked where the 26.9 ms maximum sensor-state age enters the safety
distance. It did not enter anywhere, which was a gap in the method and not
merely in the write-up. It now enters additively, as its own term.

The separation the controller tests is computed from an estimate formed up to
t_age earlier, so both bodies may have closed on each other by that much before
the test is applied:

    S_age = (v_h + v_r) * t_age

The MAXIMUM age is used, not the 4.5 ms median: a separation monitor that
budgets for the typical case is budgeting for the wrong one. The term is kept
separate rather than folded into the reaction time - the arithmetic is identical,
giving an effective T_r of 0.177 s - so that it cannot be lost when any other
parameter is revised.

Note on S_s: it is the robot STOPPING DISTANCE taken from the manipulator's
stopping characteristic, not the product v_r * T_s, which understates it by
ignoring the deceleration ramp.
"""
import json

V_H = 1.6          # m/s, human speed
V_R = 0.3          # m/s, robot transit speed in the collaborative phases
T_R = 0.15         # s, reaction time
T_S = 0.25         # s, stopping time
S_S = 0.093        # m, robot stopping distance (characteristic, not v_r * T_s)
C = 0.20           # m, intrusion distance
Z_D = 0.04         # m, human position uncertainty
Z_R = 0.001        # m, robot position uncertainty
T_AGE_MAX = 0.0269      # s, maximum observed sensor-state age
T_AGE_MEDIAN = 0.0045   # s, reported for contrast only; NOT used


def terms(t_age=T_AGE_MAX):
    return {"S_h": V_H * (T_R + T_S), "S_r": V_R * T_R, "S_s": S_S,
            "C": C, "Z_d": Z_D, "Z_r": Z_R, "S_age": (V_H + V_R) * t_age}


def main():
    t = terms()
    s_p = sum(t.values())
    without_age = s_p - t["S_age"]
    return {
        "terms_m": {k: round(v, 4) for k, v in t.items()},
        "S_p_m": round(s_p, 3),
        "S_p_without_age_term_m": round(without_age, 3),
        "contribution_of_data_age_mm": round(1000 * t["S_age"], 1),
        "t_age_used_s": T_AGE_MAX,
        "t_age_median_s_not_used": T_AGE_MEDIAN,
        "equivalent_effective_reaction_time_s": round(T_R + T_AGE_MAX, 4),
        "note": "S_s is the stopping distance from the manipulator's stopping "
                f"characteristic ({S_S} m), not v_r * T_s ({round(V_R * T_S, 3)} m)",
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
