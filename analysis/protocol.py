"""Protocol and API latency (Section 6.2, Figure 6a,c,d), recomputed from
data/protocol_samples.parquet. All values SIMULATED (vendor software simulators on
a laboratory network).

Long format: one row per transaction. `value` is in `unit`: milliseconds for
latencies, microseconds for the EtherCAT cycle jitter, nanoseconds for the
distributed-clock offset, milliseconds for the WebSocket interval deviation.
"""
import json
import numpy as np
import pyarrow.parquet as pq

PATH = "data/protocol_samples.parquet"
RATE_LIMIT_RPM = 200            # configured in the API gateway (Section 11.2), not a measurement


def _pcts(x):
    return [round(float(np.quantile(x, q)), 2) for q in (0.5, 0.95, 0.99)]


def main(path=PATH):
    d = pq.read_table(path).to_pandas()
    rest = d[d["protocol"] == "rest"]
    p50, p95, p99 = _pcts(rest["value"])
    # load is a per-minute series; its mean is taken over minutes, not over requests
    per_min = rest.assign(minute=(rest["t_s"] // 60).astype(int)).groupby("minute")["load_rpm"].first()
    ops = lambda proto: {op: _pcts(g["value"]) for op, g in d[d["protocol"] == proto].groupby("operation", sort=False)}
    ec = d[d["protocol"] == "ethercat"]
    jit = ec.loc[ec["operation"] == "cycle_jitter", "value"]
    dc = ec.loc[ec["operation"] == "dc_sync_offset", "value"]
    sdo = ec.loc[ec["operation"] == "sdo_config", "value"]
    ws = d.loc[d["protocol"] == "websocket", "value"]
    return {
        "source": path, "rows": int(len(d)),
        "rest_ms": {"p50": p50, "p95": p95, "p99": p99, "requests": int(len(rest))},
        "load_rpm": {"mean": round(float(per_min.mean()), 2), "peak": int(per_min.max()),
                     "minutes": int(per_min.size), "configured_rate_limit": RATE_LIMIT_RPM},
        "opcua_ms_p50_p95_p99": ops("opcua"),
        "modbus_ms_p50_p95_p99": ops("modbus"),
        "ethercat": {"cycle_ms": 1.0,
                     "jitter_us_max": round(float(jit.abs().max()), 2),
                     "dc_sync_ns_max": round(float(dc.abs().max()), 1),
                     "slaves": int(ec["node"].max()),
                     "sdo_config_ms": round(float(sdo.median()), 2)},
        "websocket": {"max_interval_deviation_ms": round(float(ws.abs().max()), 4),
                      "max_deviation_pct_of_period": round(float(ws.abs().max()) / 20.0 * 100, 3),
                      "period_ms": 20.0},
        "caveat": "vendor software simulators on a laboratory network",
    }


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
