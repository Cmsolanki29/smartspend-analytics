"""25+ realistic Indian urban personas for corpus filtering and assignment."""

from __future__ import annotations

from typing import Any

_KEYS: tuple[str, ...] = (
    "persona_key",
    "name",
    "age",
    "occupation",
    "city",
    "city_tier",
    "monthly_income",
    "lifestyle",
    "age_group",
    "has_home_loan",
    "home_loan_emi",
    "has_vehicle_loan",
    "vehicle_loan_emi",
    "has_personal_loan",
    "personal_loan_emi",
    "food_delivery_freq",
    "shopping_style",
    "subscription_count",
)

# (persona_key, name, age, occupation, city, tier, income, lifestyle, age_grp,
#  home_loan, home_emi, veh_loan, veh_emi, pers_loan, pers_emi, food_freq, shop_style, sub_cnt)
_RAW: tuple[tuple[Any, ...], ...] = (
    ("rahul_sw_blr", "Rahul Sharma", 27, "Software Engineer", "Bangalore", 1, 75_000, "moderate", "22-28", False, 0, True, 4_500, False, 0, "frequent", "impulsive", 4),
    ("priya_mkt_mum", "Priya Mehta", 32, "Marketing Manager", "Mumbai", 1, 120_000, "premium", "28-35", True, 42_000, True, 15_000, False, 0, "frequent", "planned", 6),
    ("arjun_ca_ahm", "Arjun Patel", 35, "Chartered Accountant", "Ahmedabad", 2, 180_000, "premium", "35-45", True, 55_000, False, 0, False, 0, "occasional", "minimal", 5),
    ("kavya_analyst_del", "Kavya Singh", 26, "Data Analyst", "Delhi", 1, 48_000, "budget", "22-28", False, 0, True, 3_200, True, 6_500, "daily", "impulsive", 3),
    ("vikram_sales_pune", "Vikram Desai", 29, "B2B Sales", "Pune", 2, 68_000, "moderate", "22-28", False, 0, False, 0, True, 8_200, "frequent", "planned", 3),
    ("neha_ux_hyd", "Neha Reddy", 28, "UX Designer", "Hyderabad", 1, 82_000, "moderate", "22-28", False, 0, False, 0, False, 0, "frequent", "planned", 4),
    ("amit_bank_kol", "Amit Banerjee", 41, "Bank Branch Manager", "Kolkata", 2, 140_000, "premium", "35-45", True, 38_000, True, 12_000, False, 0, "occasional", "minimal", 4),
    ("sunita_teacher_jaipur", "Sunita Choudhary", 38, "School Teacher", "Jaipur", 2, 42_000, "budget", "35-45", False, 0, False, 0, True, 4_200, "occasional", "minimal", 2),
    ("rohan_fresher_noida", "Rohan Verma", 23, "Graduate Trainee IT", "Noida", 1, 32_000, "budget", "22-28", False, 0, False, 0, True, 3_800, "daily", "impulsive", 2),
    ("deepa_nurse_blr", "Deepa Nair", 34, "Staff Nurse", "Bangalore", 1, 55_000, "moderate", "28-35", False, 0, True, 5_500, False, 0, "occasional", "planned", 2),
    ("manish_sme_indore", "Manish Jain", 44, "Retail Shop Owner", "Indore", 3, 95_000, "moderate", "35-45", True, 22_000, False, 0, True, 12_000, "occasional", "planned", 3),
    ("anjali_lawyer_mum", "Anjali Kapoor", 36, "Corporate Lawyer", "Mumbai", 1, 220_000, "premium", "35-45", True, 65_000, True, 18_000, False, 0, "frequent", "planned", 7),
    ("farhan_freelance_blr", "Farhan Siddiqui", 31, "Freelance Video Editor", "Bangalore", 1, 58_000, "moderate", "28-35", False, 0, False, 0, False, 0, "frequent", "impulsive", 5),
    ("lakshmi_homemaker_cbe", "Lakshmi Iyer", 40, "Homemaker", "Coimbatore", 3, 35_000, "budget", "35-45", False, 0, False, 0, False, 0, "occasional", "planned", 2),
    ("tarun_engg_chd", "Tarun Bhatia", 45, "Civil Engineer", "Chandigarh", 2, 110_000, "moderate", "45-55", True, 48_000, False, 0, False, 0, "occasional", "minimal", 3),
    ("ishita_student_pune", "Ishita Kulkarni", 21, "Engineering Student", "Pune", 2, 12_000, "budget", "22-28", False, 0, False, 0, False, 0, "daily", "impulsive", 2),
    ("harish_logistics_lko", "Harish Yadav", 48, "Logistics Supervisor", "Lucknow", 3, 52_000, "budget", "45-55", False, 0, True, 6_800, False, 0, "occasional", "minimal", 2),
    ("meera_consultant_del", "Meera Khanna", 33, "Management Consultant", "Delhi", 1, 185_000, "premium", "28-35", True, 52_000, True, 14_500, False, 0, "frequent", "planned", 6),
    ("naveen_startup_hyd", "Naveen Rao", 30, "Startup Founder", "Hyderabad", 1, 95_000, "moderate", "28-35", False, 0, False, 0, True, 15_000, "frequent", "impulsive", 4),
    ("pooja_singleparent_mum", "Pooja Nair", 37, "HR Manager", "Mumbai", 1, 92_000, "moderate", "35-45", False, 0, True, 9_000, True, 7_500, "frequent", "planned", 4),
    ("karthik_techlead_blr", "Karthik Murthy", 39, "Engineering Manager", "Bangalore", 1, 195_000, "premium", "35-45", True, 72_000, True, 16_000, False, 0, "occasional", "planned", 5),
    ("divya_content_ahm", "Divya Shah", 25, "Content Writer", "Ahmedabad", 2, 38_000, "budget", "22-28", False, 0, False, 0, True, 4_500, "frequent", "impulsive", 3),
    ("suresh_govt_bbsr", "Suresh Patnaik", 52, "Government Officer", "Bhubaneswar", 3, 88_000, "moderate", "45-55", True, 18_000, False, 0, False, 0, "occasional", "minimal", 2),
    ("ritu_designer_del", "Ritu Malhotra", 29, "Interior Designer", "Delhi", 1, 72_000, "moderate", "22-28", False, 0, False, 0, True, 9_500, "occasional", "planned", 4),
    ("aditya_bankexec_mum", "Aditya Kulkarni", 46, "VP Operations Bank", "Mumbai", 1, 280_000, "premium", "45-55", True, 85_000, True, 22_000, False, 0, "occasional", "minimal", 6),
    ("sneha_biotech_blr", "Sneha Thomas", 31, "Biotech Researcher", "Bangalore", 1, 78_000, "moderate", "28-35", False, 0, True, 4_800, True, 5_200, "occasional", "planned", 3),
    ("yusuf_trader_surat", "Yusuf Pathan", 34, "Textile Trader", "Surat", 2, 65_000, "moderate", "28-35", False, 0, False, 0, True, 11_000, "occasional", "planned", 2),
    ("geeta_retired_del", "Geeta Sharma", 58, "Retired Teacher", "Delhi", 1, 45_000, "budget", "45-55", False, 0, False, 0, False, 0, "occasional", "minimal", 1),
    ("bilal_delivery_blr", "Bilal Hussain", 24, "Delivery Partner", "Bangalore", 1, 28_000, "budget", "22-28", False, 0, True, 2_800, False, 0, "daily", "minimal", 1),
    ("chitra_pharm_chen", "Chitra Raman", 43, "Pharmacist", "Chennai", 1, 62_000, "moderate", "35-45", False, 0, False, 0, False, 0, "occasional", "planned", 2),
)

PERSONAS: list[dict[str, Any]] = [dict(zip(_KEYS, row)) for row in _RAW]


def persona_by_key(key: str) -> dict[str, Any] | None:
    k = key.strip().lower()
    for p in PERSONAS:
        if str(p["persona_key"]).lower() == k:
            return p
    return None
