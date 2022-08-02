from app_utils.django import clean_setting

# minimum standing a character needs to have in order to get alliance contacts
# Any char with a standing smaller than this value will be rejected
STANDINGSSYNC_CHAR_MIN_STANDING = clean_setting(
    "STANDINGSSYNC_CHAR_MIN_STANDING", default_value=0.1, min_value=-10, max_value=10
)

# When enabled will automatically add or set war targets
# with standing = -10 to synced characters
STANDINGSSYNC_ADD_WAR_TARGETS = clean_setting("STANDINGSSYNC_ADD_WAR_TARGETS", False)

# Name of contacts label for war targets
STANDINGSSYNC_WAR_TARGETS_LABEL_NAME = clean_setting(
    "STANDINGSSYNC_WAR_TARGETS_LABEL_NAME", "WAR TARGETS"
)

# When enabled will replace contacts of synced characters with alliance contacts
STANDINGSSYNC_REPLACE_CONTACTS = clean_setting("STANDINGSSYNC_REPLACE_CONTACTS", True)

# Smallest war ID to fetch from ESI. All wars with smaller IDs are known to be already finished. This is an optimization to avoid having to fetch >700K wars from ESI.
STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID = clean_setting(
    "STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID", 719979
)

# IDs of unfinished wars, with IDs below the above minimum threshold
STANDINGSSYNC_SPECIAL_WAR_IDS = clean_setting(
    "STANDINGSSYNC_SPECIAL_WAR_IDS",
    [
        693125,
        716071,
        716072,
        716073,
        716864,
        717695,
        718307,
        718387,
        718575,
        718576,
        718619,
        718637,
        718638,
        718639,
        718640,
        718941,
        719186,
        719187,
        719188,
        719189,
        719226,
        719331,
        719336,
        719337,
        719423,
        719745,
        719751,
        719854,
        719890,
    ],
)
