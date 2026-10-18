from datetime import date

import pytest

import timeline

AS_OF = date(2026, 10, 18)


@pytest.mark.parametrize("choice,expected", [
    ("Last 7 days", (date(2026, 10, 12), date(2026, 10, 18))),
    ("Last 30 days", (date(2026, 9, 19), date(2026, 10, 18))),
    ("Last 90 days", (date(2026, 7, 21), date(2026, 10, 18))),
    ("This month", (date(2026, 10, 1), date(2026, 10, 18))),
    ("Last month", (date(2026, 9, 1), date(2026, 9, 30))),
])
def test_each_preset_resolves(choice, expected):
    assert timeline.resolve(choice, AS_OF) == expected


def test_last_month_crosses_a_year_boundary():
    assert timeline.resolve("Last month", date(2027, 1, 15)) == (date(2026, 12, 1), date(2026, 12, 31))


def test_custom_range_is_returned_as_given():
    assert timeline.resolve("Custom", AS_OF, (date(2026, 8, 1), date(2026, 8, 31))) == (date(2026, 8, 1), date(2026, 8, 31))


@pytest.mark.parametrize("custom", [None, (date(2026, 9, 10), date(2026, 9, 1)), (date(2026, 10, 1), date(2026, 10, 19))])
def test_invalid_custom_range_is_rejected(custom):
    with pytest.raises(ValueError):
        timeline.resolve("Custom", AS_OF, custom)


def test_unknown_choice_is_rejected():
    with pytest.raises(ValueError, match="Last decade"):
        timeline.resolve("Last decade", AS_OF)


def test_choices_lists_every_preset_and_custom():
    assert timeline.CHOICES == ["Last 7 days", "Last 30 days", "Last 90 days", "This month", "Last month", "Custom"]
