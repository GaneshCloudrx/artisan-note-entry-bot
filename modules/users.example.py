"""
Clinic users template.

Copy this file to `modules/users.py` (gitignored) and replace the placeholder
credentials with the real per-clinic values. The bot calls `get_users()` and
expects a pandas DataFrame back.
"""

import pandas as pd


def get_users():
    """Return a DataFrame describing every clinic the bot should service."""
    user_data = [
        {
            "Clinic_Id": 0,
            "Clinic_Name": "<Clinic display name>",
            "EMR_System": "ARTISAN",
            "URL": "https://artisancw.com/index.html",
            "Username": "<emr username>",
            "Password1": "<emr password>",
            "Digital_Sig": "<digital signature>",
            "Color": None,
        },
        # Add one dict per clinic ...
    ]
    return pd.DataFrame(user_data)
