"""Central configuration for the Content Dashboard automation.

To run against another Eduport channel, change only BASE_URL below.
Every page object, API client and test builds its URLs from it.
"""

BASE_URL = "https://shah.eduport.in"

# Normalised so a trailing "/" in BASE_URL does not produce "//" in paths
BASE_URL = BASE_URL.rstrip("/")
