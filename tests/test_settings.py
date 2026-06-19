from src.config.settings import slugify


def test_slugify_lowercases_and_hyphenates_spaces():
    assert slugify("Vandelay Industries") == "vandelay-industries"


def test_slugify_single_word():
    assert slugify("ACME") == "acme"


def test_slugify_collapses_non_alphanumerics_to_single_hyphen():
    assert slugify("Cyberdyne   Systems!!") == "cyberdyne-systems"


def test_slugify_trims_leading_trailing_separators():
    assert slugify("  ACME, Inc.  ") == "acme-inc"
