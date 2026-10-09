# ⭐ Family Tasks

> 🌐 **English** (this page) · [Deutsch](README.de.md)

![Family Tasks icon](custom_components/family_tasks/brand/icon.png)

A **persistent points ledger** for the
[Family Task Card](https://github.com/renespeaker/ha-family-task-card) in
[Home Assistant](https://www.home-assistant.io/). Without it, the card works out
points live from checked-off tasks — simple, but points disappear when a list is
cleared, and chores that reopen every round can't earn any. With Family Tasks,
**every point is booked and kept**, and each person gets a points sensor.

> **Status: v0.1.0 — phase 1 (points ledger).** Card support follows in the
> Family Task Card. Planned next: reward approval by push, statistics.

## What you get

- **A points sensor per person**, e.g. `sensor.lina_points` — spendable points as
  the state, plus `earned` and `redeemed`. Works with history graphs,
  statistics and automations.
- **Bookings that never count twice.** Every award has a unique key (the card uses
  list + task, plus the round for rotating chores). When phone and wall tablet
  both report the same task, it is booked once.
- **Services** for the card and your own automations:

  | Service | What it does |
  |---|---|
  | `family_tasks.award` | book points for a task (`key`, `person`, `points`, `task`) |
  | `family_tasks.revoke` | take an award back, e.g. when a task is unchecked (`key`) |
  | `family_tasks.redeem` | spend points on a reward; refuses if there are too few (`person`, `points`, `reward`) |
  | `family_tasks.adjust` | bonus (positive) or deduction (negative) by a parent (`person`, `points`, `reason`) |

  All return the new balance (`return_response`).
- **An event** `family_tasks_points_changed` for every booking — e.g. to flash a
  light when someone earns points.
- Stored inside Home Assistant (`.storage/family_tasks`), no cloud, nothing to
  configure.

## Installation

### Via HACS (custom repository)

1. HACS → ⋮ → **Custom repositories** → add
   `https://github.com/renespeaker/ha-family-tasks`, type **Integration**.
2. Search **Family Tasks** → **Download** → restart Home Assistant.
3. **Settings → Devices & services → Add integration → Family Tasks** → Submit.
   There is nothing to fill in.

People appear with their first booking. Use the `person.*` entity as `person`
(e.g. `person.lina`) and the device is named after the person.

### Manual

Copy `custom_components/family_tasks` into your `config/custom_components/`,
restart, then add the integration as above.

## Examples

```yaml
# Bonus for helping without being asked
action: family_tasks.adjust
data:
  person: person.lina
  points: 20
  reason: Helped without being asked
```

```yaml
# Flash the kids' room light green on every booking for Lina
triggers:
  - trigger: event
    event_type: family_tasks_points_changed
    event_data:
      person: person.lina
actions:
  - action: light.turn_on
    target: { entity_id: light.kids_room }
    data: { rgb_color: [0, 255, 0], flash: short }
```

## Development

```bash
uv venv -p 3.13 .venv
uv pip install -p .venv/bin/python -r requirements_test.txt
.venv/bin/python -m pytest -q
uvx ruff check . && uvx ruff format --check .
```

## License

MIT
