"""Constants for Family Tasks."""

DOMAIN = "family_tasks"

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1

EVENT_POINTS_CHANGED = f"{DOMAIN}_points_changed"
SIGNAL_UPDATED = f"{DOMAIN}_updated"

SERVICE_AWARD = "award"
SERVICE_REVOKE = "revoke"
SERVICE_REDEEM = "redeem"
SERVICE_ADJUST = "adjust"

ATTR_KEY = "key"
ATTR_PERSON = "person"
ATTR_POINTS = "points"
ATTR_TASK = "task"
ATTR_REWARD = "reward"
ATTR_REASON = "reason"
