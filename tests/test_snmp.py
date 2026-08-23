from app.collectors.snmp import (
    PORT_ERROR_FIELDS, _port_in_bitmap, _set_port_in_bitmap, parse_port_error_output,
)


def test_bit_positions():
    # Bit 1 = MSB von Byte 0 (Q-BRIDGE PortList-Konvention)
    assert _port_in_bitmap(b"\x80", 1) is True
    assert _port_in_bitmap(b"\x80", 2) is False
    assert _port_in_bitmap(b"\x01", 8) is True
    assert _port_in_bitmap(b"\x00\x40", 10) is True


def test_out_of_range():
    assert _port_in_bitmap(b"\xff", 9) is False


def test_set_and_clear():
    bm = _set_port_in_bitmap(b"\x00\x00", 3, True)
    assert bm == b"\x20\x00"
    assert _port_in_bitmap(bm, 3)
    bm = _set_port_in_bitmap(bm, 3, False)
    assert bm == b"\x00\x00"


def test_set_extends_bitmap():
    bm = _set_port_in_bitmap(b"", 24, True)
    assert len(bm) == 3
    assert _port_in_bitmap(bm, 24)


def test_roundtrip_all_ports():
    bm = b"\x00" * 6
    for port in range(1, 49):
        bm = _set_port_in_bitmap(bm, port, port % 2 == 0)
    for port in range(1, 49):
        assert _port_in_bitmap(bm, port) == (port % 2 == 0)


def test_parse_port_error_output_all_present():
    lines = "\n".join(str(i) for i in range(len(PORT_ERROR_FIELDS)))
    counters = parse_port_error_output(lines)
    keys = [k for k, _ in PORT_ERROR_FIELDS]
    assert counters == {k: i for i, k in enumerate(keys)}


def test_parse_port_error_output_partial_no_such_instance():
    # Manche Switches unterstuetzen die EtherLike-MIB nicht vollstaendig —
    # snmpget liefert dann "No Such Instance ..." statt einer Zahl.
    lines = [
        "0",  # fcs_errors
        "No Such Instance currently exists at this OID",  # alignment_errors
        "0", "0", "0", "0",
        "5",  # if_in_errors
        "0",  # if_out_errors
    ]
    counters = parse_port_error_output("\n".join(lines))
    assert counters["fcs_errors"] == 0
    assert counters["alignment_errors"] is None
    assert counters["if_in_errors"] == 5


def test_parse_port_error_output_empty():
    counters = parse_port_error_output("")
    assert all(v is None for v in counters.values())
    assert set(counters.keys()) == {k for k, _ in PORT_ERROR_FIELDS}


def test_parse_port_error_output_too_few_lines():
    # snmpget-Aufruf bricht z.B. wegen Timeout mitten drin ab
    counters = parse_port_error_output("12\n3")
    assert counters["fcs_errors"] == 12
    assert counters["alignment_errors"] == 3
    assert counters["symbol_errors"] is None
