from synonyms import parse_synonyms, normalize_names

def test_parse_synonyms_handles_common_separators():
    raw = "St John's wort, hypericum | Hypericum perforatum;  SJW / STJW"
    out = set(parse_synonyms(raw))
    assert {"st john's wort", "hypericum", "hypericum perforatum", "sjw", "stjw"} <= out

def test_normalize_names_dedupes_and_trims():
    names = [" Hypericum ", "hypericum", "SJW", "sjw", ""]
    out = normalize_names(names)
    assert out == ["hypericum", "sjw"]
