import sqlite3

from sightline import audit


def test_chain_verifies_and_detects_tampering(db_path):
    for i in range(3):
        audit.append("decision", {"verdict": "BLOCK", "n": i})
    assert audit.verify() == (True, audit.verify()[1]) and audit.verify()[0]
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE audit SET data = ? WHERE seq = 2", ('{"verdict":"ALLOW","n":1}',))
    conn.commit()
    ok, msg = audit.verify()
    assert not ok and "#2" in msg


def test_deleting_an_entry_breaks_the_chain(db_path):
    for i in range(3):
        audit.append("decision", {"n": i})
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM audit WHERE seq = 2")
    conn.commit()
    assert not audit.verify()[0]


def test_entries_in_order_with_limit():
    for i in range(5):
        audit.append("decision", {"n": i})
    assert [e["data"]["n"] for e in audit.entries(limit=2)] == [3, 4]
