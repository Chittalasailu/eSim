import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from chatbot.error_solutions import get_error_solution

PASS = "PASS"
FAIL = "FAIL"

def print_separator():
    print("-" * 60)


# ------------------------------------------------------------
# BUG-001 -- None Input Crash
# ------------------------------------------------------------
def test_none_input():
    print_separator()
    print("BUG-001 -- None Input Crash")
    print_separator()

    result = get_error_solution(None)

    if result is None or result == "":
        print(f"[{PASS}] None input handled gracefully")
    else:
        print(f"[{FAIL}] Unexpected result returned: {result}")

    print()


# ------------------------------------------------------------
# BUG-003 -- Weak Substring Matching (Word Order)
# ------------------------------------------------------------
def test_weak_matching():
    print_separator()
    print("BUG-003 -- Weak Substring Matching")
    print_separator()

    test_cases = [
        ("singular matrix",       "exact key word order"),
        ("matrix is singular",    "flipped word order"),
        ("import error",          "exact key word order"),
        ("error in import",       "flipped word order"),
        ("connection refused",    "exact key word order"),
        ("refused the connection","flipped word order"),
    ]

    for inp, label in test_cases:
        result = get_error_solution(inp)
        is_generic = (
            result is None or
            result.get("severity") == "unknown"
        )
        status = FAIL if is_generic else PASS
        print(f"[{status}] [{label}]")
        print(f"        Input    : {inp!r}")
        print(f"        Severity : {result.get('severity') if result else 'None'}")
        print(f"        Desc     : {result.get('description') if result else 'None'}")
        print()


# ------------------------------------------------------------
# BUG-006 -- Generic Fallback Masking Real Errors
# ------------------------------------------------------------
def test_generic_fallback():
    print_separator()
    print("BUG-006 -- Generic Fallback Masking Real Errors")
    print_separator()

    # These are inputs that should NOT silently return generic fallback
    unknown_inputs = [
        "some completely random error xyz",
        "404 not found",
        "kernel panic",
    ]

    for inp in unknown_inputs:
        result = get_error_solution(inp)
        is_generic = (
            result is not None and
            result.get("severity") == "unknown"
        )
        status = FAIL if is_generic else PASS
        print(f"[{status}] Input    : {inp!r}")
        print(f"        Severity : {result.get('severity') if result else 'None'}")
        print(f"        Desc     : {result.get('description') if result else 'None'}")
        print()


# ------------------------------------------------------------
# BUG-008 -- Limited Error Coverage
# ------------------------------------------------------------
def test_limited_coverage():
    print_separator()
    print("BUG-008 -- Limited Error Coverage")
    print_separator()

    # Common errors that should ideally be in the knowledge base
    missing_errors = [
        "import error",
        "connection refused",
        "segmentation fault",
        "permission denied",
        "memory overflow",
    ]

    for inp in missing_errors:
        result = get_error_solution(inp)
        in_kb = (
            result is not None and
            result.get("severity") != "unknown"
        )
        status = PASS if in_kb else FAIL
        print(f"[{status}] Input : {inp!r}")
        print(f"        In knowledge base : {in_kb}")
        print()


# ------------------------------------------------------------
# Run All Tests
# ------------------------------------------------------------
if __name__ == "__main__":
    print()
    print("=" * 60)
    print("Test Suite -- error_solutions.py")
    print("=" * 60)
    print()

    test_none_input()
    test_weak_matching()
    test_generic_fallback()
    test_limited_coverage()

    print("=" * 60)
    print("All tests completed")
    print("=" * 60)

# ------------------------------------------------------------
# Known ngspice errors, as ngspice prints them
# ------------------------------------------------------------
from chatbot.error_solutions import known_errors, known_errors_text  # noqa: E402


def test_real_ngspice_messages_are_recognised():
    log = (
        "Warning: singular matrix:  check node v1#branch\n"
        "doAnalyses: TRAN:  Timestep too small; time = 1e-06\n"
        "Error: Could not find a valid modelname\n"
        "Error: unknown subckt: x1 0 out lm555n\n"
        "Warning: gmin stepping failed\n"
        "Error: no such vector v(out)\n"
    )

    descriptions = [s["description"] for s in known_errors(log)]

    assert len(descriptions) == 6


def test_unknown_errors_get_no_generic_fix():
    assert known_errors("Error: something nobody has seen before") == []
    assert known_errors_text("Error: something nobody has seen before") == ""
    assert known_errors_text("") == ""


def test_known_fix_text_names_the_esim_step():
    text = known_errors_text("Error: unknown subckt: x1 0 out lm555n")

    assert "subcircuit" in text
    assert "In eSim: KiCad to Ngspice" in text
