"""Protocol and API latency (Section 6.2, Figure 6a,c,d). All values SIMULATED."""
import json

REST_MS = {"p50": 2.1, "p95": 4.8, "p99": 6.5}
LOAD_RPM = {"mean": 50, "peak": 112, "configured_rate_limit": 200}
OPCUA_MS = {"read": [4.2, 7.5, 12], "write": [4.5, 8.1, 13], "subscribe": [5.8, 9.2, 15],
            "method_call": [6.3, 10.5, 17], "bulk_read_20": [8.7, 14.2, 22]}
MODBUS_MS = {"fc03_10reg": [7.1, 11.8, 18], "fc06": [7.8, 12.2, 19],
             "fc16_10reg": [9.2, 15.1, 23], "fc01_16coil": [6.5, 10.3, 16], "fc05": [7.2, 11.5, 17]}
ETHERCAT = {"cycle_ms": 1.0, "jitter_us_max": 10, "dc_sync_ns": 100, "slaves": 32, "sdo_config_ms": 15}


def main():
    return {"rest_ms": REST_MS, "load_rpm": LOAD_RPM, "opcua_ms_p50_p95_p99": OPCUA_MS,
            "modbus_ms_p50_p95_p99": MODBUS_MS, "ethercat": ETHERCAT,
            "caveat": "vendor software simulators on a laboratory network"}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
