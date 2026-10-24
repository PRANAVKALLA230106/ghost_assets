"""Unknown institutions get readable names from their own messages, with no hand-added aliases."""
from resolve import _expand_code


def test_sender_codes_expand_from_message_text():
    assert _expand_code("STRHLT", ["premium for policy XXXXX3360 (Star Health Smart ULIP) is due"]) == "Star Health"
    assert _expand_code("ADTYMF", ["Rs 6000 debited for SIP ADITYA MF Folio XXXXXX7701"]) == "Aditya Mutual Fund"
    assert _expand_code("BJAJAL", ["Premium of Rs 9,000 for policy XXXX1122 Bajaj Allianz Life is due"]) == "Bajaj Allianz"


def test_email_domain_label_expands():
    assert _expand_code("Veltextiles", ["Vel Textiles Ltd - Notice of 18th AGM, Folio No.: VT55120"]) == "Vel Textiles"


def test_no_match_keeps_code():
    assert _expand_code("XYZQWT", ["Your account XX1234 credited by Rs 500"]) is None


def test_shared_generic_word_is_not_a_match():
    from resolve import normalise_institution
    assert normalise_institution("Max Life") == "Max Life"
    assert normalise_institution("VM-SURKSH") == "Suraksha Life Insurance"
    assert normalise_institution("STATE BANK OF INDIA (A/C XX8812)") == "State Bank of India"
    assert normalise_institution("Kaveri MF") == "Kaveri Mutual Fund"
