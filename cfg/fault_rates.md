# Fault rates used by the campaigns

The rates in `cfg/base_sim_ur5e.json` (`faults.rates_per_h`) and in the generated campaigns
are **design parameters of the test campaign**, not estimates of how often these faults occur
in an installed cell. They were chosen so that every detection and degradation path is
exercised during the campaign. No external failure statistic is cited for them, and the paper
must not present them as field rates.

| Category | Rate in the 200 h timing campaign (h⁻¹) | Dedicated injection campaign |
|---|---|---|
| tracking loss | 0.35 | equal rate for all 8 categories, 480 injections over 10 h |
| sensor timeout (one camera stream) | 0.18 | " |
| computational overrun (22–36 ms of extra work in one cycle) | 0.12 | " |
| hardware communication (1–5 consecutive responses failing validation) | 0.08 | " |
| configuration inconsistency | 0.05 | " |
| network partition (0.5–3 s with no robot state) | 0.03 | " |
| constraint violation (operator lunge at 2.0 m/s towards the TCP) | 0.02 | " |
| memory allocation | 0.0 | " |

Because the availability and reliability figures depend on these choices, the sensitivity
campaign (`cfg/campaigns/sensitivity`) repeats the measurement with:

* rate scale 0.5×, 1.0×, 1.5×;
* four arrival models with the same long-run rate: Poisson; clustered (Neyman–Scott, mean
  cluster size 3, spread 30 s); Weibull renewal with shape 0.7 (bursty) and 1.5 (regular).

Operator response times after a latched stop are drawn from a log-normal distribution with
median `operator.ack_median_s` (default 60 s) and log-σ 0.5. They are simulated; the
availability results must say so, and should be reported for several medians.
