from app.collectors.lldp import parse_lldp_json

# lldpcli -f json0: alles Listen, Blattwerte als {"value": ...}
JSON0 = {
    "lldp": [{
        "interface": [{
            "name": "enp0s25", "via": "LLDP",
            "chassis": [{
                "id": [{"type": "mac", "value": "aa:bb:cc:dd:ee:ff"}],
                "name": [{"value": "sw-core-01"}],
                "descr": [{"value": "HP ProCurve 2530"}],
                "mgmt-ip": [{"value": "10.0.0.2"}, {"value": "fe80::1"}],
            }],
            "port": [{
                "id": [{"type": "ifname", "value": "GigabitEthernet1/0/24"}],
                "descr": [{"value": "Port 24"}],
            }],
            "vlan": [{"vlan-id": "100", "pvid": True, "value": "MGMT"}],
        }],
    }],
}

# lldpcli -f json: verschachtelte Dicts, chassis nach Switch-Namen gekeyt
JSON1 = {
    "lldp": {
        "interface": {
            "enp0s25": {
                "chassis": {
                    "sw-core-01": {
                        "id": {"type": "mac", "value": "aa:bb:cc:dd:ee:ff"},
                        "descr": "HP ProCurve 2530",
                        "mgmt-ip": "10.0.0.2",
                    },
                },
                "port": {"id": {"type": "ifname", "value": "24"}, "descr": "Port 24"},
                "vlan": {"vlan-id": "100"},
            },
        },
    },
}


def test_parse_json0():
    n = parse_lldp_json(JSON0)
    assert len(n) == 1
    assert n[0]["switch_name"] == "sw-core-01"
    assert n[0]["switch_mgmt_ip"] == "10.0.0.2"
    assert n[0]["port_id"] == "GigabitEthernet1/0/24"
    assert n[0]["port_descr"] == "Port 24"
    assert n[0]["vlan"] == "100"


def test_parse_json_variant():
    n = parse_lldp_json(JSON1)
    assert len(n) == 1
    assert n[0]["switch_name"] == "sw-core-01"
    assert n[0]["switch_mgmt_ip"] == "10.0.0.2"
    assert n[0]["port_id"] == "24"
    assert n[0]["port_descr"] == "Port 24"


def test_parse_empty():
    assert parse_lldp_json({}) == []
    assert parse_lldp_json({"lldp": {}}) == []
    assert parse_lldp_json({"lldp": [{}]}) == []
