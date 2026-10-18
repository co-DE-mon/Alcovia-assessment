import pandas as pd
import pytest

from views import leads


@pytest.fixture
def frame():
    return pd.DataFrame([
        dict(lead_id="DEMO-L-00001", student_name="Demo Student 00001", parent_name="Demo Parent 00001", phone="+91 00000 00001", city="Delhi", grade=10,
             source_lead="paid_ads", furthest_stage="signed", status="Signed up"),
        dict(lead_id="DEMO-L-00002", student_name="Demo Student 00002", parent_name="Demo Parent 00002", phone="+91 00000 00002", city="Mumbai", grade=11,
             source_lead="organic", furthest_stage="review", status="Rejected"),
        dict(lead_id="DEMO-L-00003", student_name="Demo Student 00003", parent_name="Demo Parent 00003", phone="+91 00000 00003", city="Delhi", grade=11,
             source_lead="brochure", furthest_stage="qualified", status="In progress"),
    ])


def ids(df):
    return list(df["lead_id"])


def test_all_means_no_filter(frame):
    assert ids(leads.apply_filters(frame)) == ["DEMO-L-00001", "DEMO-L-00002", "DEMO-L-00003"]


def test_each_filter_narrows_and_they_combine_with_and(frame):
    assert ids(leads.apply_filters(frame, status="Rejected")) == ["DEMO-L-00002"]
    assert ids(leads.apply_filters(frame, source="Brochure")) == ["DEMO-L-00003"]
    assert ids(leads.apply_filters(frame, city="Delhi")) == ["DEMO-L-00001", "DEMO-L-00003"]
    assert ids(leads.apply_filters(frame, grade="11")) == ["DEMO-L-00002", "DEMO-L-00003"]
    assert ids(leads.apply_filters(frame, stage="Qualified")) == ["DEMO-L-00003"]
    assert ids(leads.apply_filters(frame, city="Delhi", grade="11")) == ["DEMO-L-00003"]
    assert leads.apply_filters(frame, city="Mumbai", status="Signed up").empty


def test_search_matches_id_student_parent_and_phone_ignoring_case_and_spaces(frame):
    assert ids(leads.apply_filters(frame, search="demo-l-00002")) == ["DEMO-L-00002"]
    assert ids(leads.apply_filters(frame, search="  student 00003 ")) == ["DEMO-L-00003"]
    assert ids(leads.apply_filters(frame, search="parent 00001")) == ["DEMO-L-00001"]
    assert ids(leads.apply_filters(frame, search="+91 00000 00002")) == ["DEMO-L-00002"]
    assert ids(leads.apply_filters(frame, search="Demo")) == ["DEMO-L-00001", "DEMO-L-00002", "DEMO-L-00003"]
    assert leads.apply_filters(frame, search="nobody").empty


def test_filters_never_change_the_input_frame(frame):
    before = frame.copy()
    leads.apply_filters(frame, status="Rejected", search="x")
    pd.testing.assert_frame_equal(frame, before)
