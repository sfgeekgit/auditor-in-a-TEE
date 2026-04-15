"""
Byte-for-byte contract test between the CLI's vendored canonical.py and the
server's webapp/canonical.py. If this fails, the two copies have drifted —
signatures made by the CLI will not verify on the server.
"""

import canonical as server_canonical  # from webapp/ via conftest sys.path
from auditor_cli import canonical as cli_canonical


def test_canonical_bytes_identical(fixture_plan_dict):
    assert cli_canonical.canonical_plan_bytes(fixture_plan_dict) == \
        server_canonical.canonical_plan_bytes(fixture_plan_dict)


def test_plan_hash_identical(fixture_plan_dict):
    assert cli_canonical.plan_hash_hex(fixture_plan_dict) == \
        server_canonical.plan_hash_hex(fixture_plan_dict)


def test_submit_message_identical(fixture_plan_dict):
    ph = cli_canonical.plan_hash_hex(fixture_plan_dict)
    data = '{"x": 1}'
    assert cli_canonical.submit_message(ph, data) == \
        server_canonical.submit_message(ph, data)


def test_domain_separator_matches():
    assert cli_canonical.SUBMIT_DOMAIN_SEP == server_canonical.SUBMIT_DOMAIN_SEP
