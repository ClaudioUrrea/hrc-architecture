"""Interface conformance and simulator fidelity (Section 3.3, Table 4). New in v2.0.0.

The first submission asserted that the simulators were "vendor-conformant" and
left the reader to decide what that covered. A reviewer asked, reasonably, which
behaviours are reproduced, which are approximated and which are simply absent.

Each adapter was exercised against a conformance checklist derived clause by
clause from the vendor document cited for it. A checklist item passes when the
simulator's observable response to a call matches the response the document
specifies - in value, in type and in ordering. The checklists, the 47
behavioural-equivalence tests that implement them, and their pass/fail logs are
under `tests/conformance/`.

WHAT A PASS DOES NOT ESTABLISH, stated here because it is the central residual
risk of a simulation-only evaluation: the simulator and the adapter were both
built from the same vendor document, so a misreading of that document would be
invisible to the test. A passing checklist shows that the adapter speaks the
protocol the document describes. It does not show that the adapter will
interoperate with a physical controller.
"""
import json

VENDOR_DOCUMENTS = {
 "universal_robots": {"interface": "RTDE / URScript", "document": "UR RTDE guide",
                      "state_rate_hz": 125},
 "kuka":             {"interface": "Fast Robot Interface (FRI)",
                      "document": "KUKA FRI manual", "state_rate_hz": 200},
 "abb_rws":          {"interface": "Robot Web Services",
                      "document": "ABB 3HAC073675-001 Rev. F", "state_rate_hz": 125},
 "abb_egm":          {"interface": "Externally Guided Motion",
                      "document": "ABB 3HAC066554-001 Rev. M", "state_rate_hz": 250},
}

# status: reproduced | simplified | absent
FEATURES = {
 "command_syntax_and_argument_semantics": {
    "status": "reproduced",
    "checked": "every cyclic call issued; the simulator's acknowledgement compared "
               "against the document's specified reply",
    "gap": None},
 "state_field_layout_units_frame_convention": {
    "status": "reproduced",
    "checked": "field-by-field comparison of decoded state against the documented "
               "layout; frame conventions verified by round-tripping known poses",
    "gap": None},
 "nominal_state_publication_rate": {
    "status": "reproduced",
    "checked": "rate measured at the adapter boundary",
    "gap": "rate is held exactly; a physical controller drifts and drops frames"},
 "error_and_status_codes": {
    "status": "reproduced",
    "checked": "each documented code triggered through the simulator's injection "
               "hooks and mapped to the adapter's exception taxonomy",
    "gap": "vendor-specific codes outside the documented set cannot be produced"},
 "communication_delay": {
    "status": "simplified",
    "checked": "loopback transport with a fixed additive delay drawn from the "
               "vendor's published cycle budget",
    "gap": "no switch queueing, media contention, EMI or bursty delay distribution"},
 "command_acceptance_and_rejection": {
    "status": "simplified",
    "checked": "limit violations, unreachable targets and out-of-mode commands "
               "rejected as documented",
    "gap": "controller-internal trajectory blending, look-ahead buffering and "
           "motion-queue back-pressure are not modelled"},
 "sensor_noise": {
    "status": "simplified",
    "checked": "depth images perturbed with the manufacturer's published depth-error "
               "model; keypoint confidence modulated by occlusion",
    "gap": "noise is stationary and spatially uncorrelated; multipath, reflective "
           "surfaces and illumination transients are absent"},
 "disconnection_and_reconnection": {
    "status": "simplified",
    "checked": "socket teardown and restoration driven by the injection harness; "
               "adapter reconnection logic exercised end to end",
    "gap": "controller-side session state after a real power cycle, and "
           "vendor-specific re-homing requirements, are not reproduced"},
 "safety_rated_channel_behaviour": {
    "status": "absent",
    "checked": None,
    "gap": "no dual-channel architecture, safety relay or safety-rated input was "
           "present; the emergency-stop path was exercised only as software"},
 "actuation_and_mechanical_response": {
    "status": "absent",
    "checked": None,
    "gap": "drive dynamics, brake engagement time, joint compliance and wear are "
           "outside the model"},
}

TESTS = {"checklist_items": 52,
         "behavioural_equivalence_tests_executed": 47,
         "failed": 0,
         "not_applicable_absent_features": 5,
         "checklists": "tests/conformance/*_checklist.yaml",
         "log": "data/conformance_log.csv"}

RESIDUAL_RISK = ("simulator and adapter derive from the same vendor document, so "
                 "a misreading of that document is invisible to the conformance "
                 "test; this is why the portability result is stated as measured "
                 "engineering effort, not as demonstrated interoperability")


def main():
    counts = {s: sum(1 for f in FEATURES.values() if f["status"] == s)
              for s in ("reproduced", "simplified", "absent")}
    return {"vendor_documents": VENDOR_DOCUMENTS,
            "features": FEATURES, "feature_counts": counts,
            "tests": TESTS,
            "claims_made_about_absent_features": [],
            "residual_risk": RESIDUAL_RISK}


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
