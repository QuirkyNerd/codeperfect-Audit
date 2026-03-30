from services.selection_engine import SelectionEngine

engine = SelectionEngine()


def run_test(name, note, expected_codes, forbidden_codes=None):
    print(f"\n===== TEST: {name} =====")

    try:
        result = engine.select([], note_text=note)
        output_codes = [c["code"] for c in result]
    except Exception as e:
        print("ERROR:", str(e))
        return

    print("NOTE:", note)
    print("OUTPUT:", output_codes)
    print("EXPECTED:", expected_codes)

    success = True

    for code in expected_codes:
        if code not in output_codes:
            print(f"MISSING: {code}")
            success = False
        else:
            print(f"FOUND: {code}")

    if forbidden_codes:
        for code in forbidden_codes:
            if any(c.startswith(code) for c in output_codes):
                print(f"FORBIDDEN PRESENT: {code}")
                success = False
            else:
                print(f"NOT PRESENT: {code}")

    if success:
        print("TEST PASSED")
    else:
        print("TEST FAILED")

if __name__ == "__main__":

    run_test(
        "DM2 + Neuropathy",
        "Patient has Type 2 diabetes mellitus with peripheral neuropathy",
        expected_codes=["E11.42"],
        forbidden_codes=["G62", "E10", "E13"]
    )

    run_test(
        "DM2 + CKD",
        "Patient has diabetes with chronic kidney disease stage 3",
        expected_codes=["E11.22", "N18.30"],
        forbidden_codes=["N18.9"]
    )
    run_test(
        "HF Priority",
        "Patient has acute on chronic systolic heart failure",
        expected_codes=["I50.23"],
        forbidden_codes=["I50.22", "I50.21"]
    )

    run_test(
        "Negation",
        "No evidence of heart failure. Patient has diabetes",
        expected_codes=["E11.9"],
        forbidden_codes=["I50"]
    )

    run_test(
        "False Positive",
        "Patient has diabetes, CKD stage 3, and hypertension",
        expected_codes=["E11.22", "N18.30", "I10"],
        forbidden_codes=["I21"]
    )

    run_test(
        "Basic Conditions",
        "Patient has hypertension and obesity",
        expected_codes=["I10", "E66.9"],
        forbidden_codes=["Z", "O"]
    )

    run_test(
        "Pregnancy Filter",
        "Patient has hypertension and diabetes",
        expected_codes=["I10", "E11.9"],
        forbidden_codes=["O"]
    )

    run_test(
        "Screening Filter",
        "Patient diagnosed with obesity",
        expected_codes=["E66.9"],
        forbidden_codes=["Z", "V"]
    )

    run_test(
        "Type 1 Diabetes",
        "Patient has Type 1 diabetes mellitus",
        expected_codes=["E10.9"],
        forbidden_codes=["E11"]
    )

    run_test(
        "Complex Case",
        """Patient has Type 2 diabetes mellitus with peripheral neuropathy,
        chronic kidney disease stage 3, hypertension, and obesity""",
        expected_codes=["E11.42", "E11.22", "N18.30", "I10", "E66.9"],
        forbidden_codes=["G62", "E10", "I21"]
    )