from app.collectors.snmp import _port_in_bitmap, _set_port_in_bitmap


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
