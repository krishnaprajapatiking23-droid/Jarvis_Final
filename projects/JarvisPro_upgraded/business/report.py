from datetime import datetime

def generate_report():

    today = datetime.now().strftime("%d-%m-%Y")

    return f"""
========== BUSINESS REPORT ==========

Date : {today}

Today's Progress

✓ Product Research
✓ Meta Ads
✓ Audience Research
✓ Profit Analysis
✓ Strategy

=====================================
"""