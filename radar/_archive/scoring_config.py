"""Rule weights + thresholds. Tunable in one place."""

BARK_THRESHOLD = 80
MAX_SCORE = 100

WEIGHTS = {
    "fundraise_age_12_18": 15,
    "fundraise_age_18_36": 30,
    "fundraise_age_36_60": 22,
    "fundraise_age_over_60": 14,
    "price_drift_20plus": 15,
    "price_drift_10_20": 8,
    "drhp_filed_90d": 25,
    "employee_pressure_3plus": 10,
    "employee_pressure_1_2": 4,
    "employee_count_500plus": 7,
}
