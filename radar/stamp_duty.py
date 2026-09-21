"""Stamp duty matrix — 5 jurisdictions aligned with SEA-weighted roster.

Rates as of FY26. Cite the act + section in every output.
"""

DUTY_TABLE = {
    "Karnataka": {
        "rate": 0.00015,  # 0.015%
        "citation": "Karnataka Stamp Act 1957 — Article 37 (transfer of shares of a company)",
        "currency": "INR",
    },
    "Maharashtra": {
        "rate": 0.00005,  # 0.005% under MSA 1958 after 2020 amendment
        "citation": "Maharashtra Stamp Act 1958 — Schedule I Article 25 (transfer of shares)",
        "currency": "INR",
    },
    "Delhi": {
        "rate": 0.0025,
        "citation": "Indian Stamp Act 1899 (Delhi) — Article 62(a)",
        "currency": "INR",
    },
    "Singapore": {
        "rate": 0.002,  # 0.2% ad valorem on share transfer
        "citation": "Singapore Stamp Duties Act 1929 — Third Schedule §11",
        "currency": "SGD",
    },
    "Jakarta": {
        "rate": 0.001,  # PPh final 0.1% for listed (proxy used for unlisted demo)
        "citation": "Indonesia Income Tax Law — PPh Article 4(2) (transfer of shares)",
        "currency": "IDR",
    },
    "Ho Chi Minh City": {
        "rate": 0.001,  # 0.1% securities transfer tax
        "citation": "Vietnam Personal Income Tax Law 2007 — Article 13 (transfer of securities)",
        "currency": "VND",
    },
}


def lookup(state: str) -> dict:
    return DUTY_TABLE.get(state, {
        "rate": 0.001,
        "citation": f"No published rate for {state} — using 0.1% conservative proxy",
        "currency": "USD",
    })
