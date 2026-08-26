from app.collectors.lldp import LLDP_STALE_AFTER, parse_age, parse_lldp_json

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


# ------------------------------------------------- Alter / Stale-Erkennung

def test_parse_age():
    assert parse_age("0 day, 00:00:12") == 12
    assert parse_age("0 day, 00:02:05") == 125
    assert parse_age("1 day, 01:00:00") == 90000
    assert parse_age(None) is None
    assert parse_age("keine Ahnung") is None


def _json0_with_age(age):
    import copy
    data = copy.deepcopy(JSON0)
    data["lldp"][0]["interface"][0]["age"] = age
    return data


def test_frischer_nachbar_ist_nicht_stale():
    n = parse_lldp_json(_json0_with_age("0 day, 00:00:12"))[0]
    assert n["age_seconds"] == 12
    assert n["stale"] is False


def test_alter_nachbar_wird_als_stale_markiert():
    """Nach dem Umstecken haelt lldpd den alten Nachbarn bis zum TTL-Ablauf vor."""
    n = parse_lldp_json(_json0_with_age(f"0 day, 00:0{LLDP_STALE_AFTER // 60 + 1}:30"))[0]
    assert n["age_seconds"] > LLDP_STALE_AFTER
    assert n["stale"] is True


def test_ohne_age_kein_stale():
    n = parse_lldp_json(JSON0)[0]
    assert n["age_seconds"] is None
    assert n["stale"] is False
