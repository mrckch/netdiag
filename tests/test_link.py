from app.collectors.link import parse_ethtool

ETHTOOL_OUT = """Settings for enp0s25:
\tSupported ports: [ TP ]
\tSupported link modes:   10baseT/Half 10baseT/Full
\t                        1000baseT/Full
\tSpeed: 1000Mb/s
\tDuplex: Full
\tAuto-negotiation: on
\tPort: Twisted Pair
\tLink detected: yes
"""


def test_parse_ethtool_full():
    p = parse_ethtool(ETHTOOL_OUT)
    assert p["speed"] == "1000Mb/s"
    assert p["duplex"] == "Full"
    assert p["auto_negotiation"] == "on"
    assert p["link_detected"] is True


def test_parse_ethtool_no_link():
    p = parse_ethtool("Settings for eth0:\n\tSpeed: Unknown!\n\tLink detected: no\n")
    assert p["link_detected"] is False
    assert p["speed"] == "Unknown!"


def test_parse_ethtool_empty():
    p = parse_ethtool("")
    assert p == {"speed": None, "duplex": None, "auto_negotiation": None,
                 "link_detected": None}
