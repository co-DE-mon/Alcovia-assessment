-- GTM tracker schema (DuckDB). All data is dummy; ids start DEMO-. Dates are IST calendar days.

-- Revenue ------------------------------------------------------------------------------------------------
CREATE TABLE enrollments (
    enrollment_id VARCHAR PRIMARY KEY,
    student_id    VARCHAR NOT NULL,
    lead_id       VARCHAR,                                  -- the funnel lead that signed, when known
    kind          VARCHAR NOT NULL CHECK (kind IN ('program', 'trial_3m')),
    started_on    DATE NOT NULL,
    renewal_on    DATE,                                     -- trial only: when the 3-month trial ends and must renew
    amount        INTEGER NOT NULL                          -- rupees, the contract value
);
CREATE TABLE invoices (
    invoice_id    VARCHAR PRIMARY KEY,
    enrollment_id VARCHAR NOT NULL REFERENCES enrollments (enrollment_id),
    issued_on     DATE NOT NULL,
    due_on        DATE NOT NULL,
    amount        INTEGER NOT NULL,
    paid_on       DATE                                      -- NULL while unpaid
);
CREATE TABLE workshops (
    workshop_id   VARCHAR PRIMARY KEY,
    campaign_id   VARCHAR,
    title         VARCHAR NOT NULL,
    held_on       DATE NOT NULL
);
CREATE TABLE workshop_payments (                            -- Razorpay-shaped
    payment_id    VARCHAR PRIMARY KEY,
    workshop_id   VARCHAR NOT NULL REFERENCES workshops (workshop_id),
    lead_id       VARCHAR,
    paid_at       TIMESTAMP NOT NULL,
    seats         INTEGER NOT NULL,
    amount        INTEGER NOT NULL                          -- seats x price per seat
);
CREATE TABLE revenue_targets (
    month         DATE PRIMARY KEY,                         -- first day of the month
    target        INTEGER NOT NULL
);

-- Campaigns ----------------------------------------------------------------------------------------------
CREATE TABLE campaigns (
    campaign_id   VARCHAR PRIMARY KEY,
    name          VARCHAR NOT NULL,
    kind          VARCHAR NOT NULL CHECK (kind IN ('program', 'workshop'))
);
CREATE TABLE ad_sets (
    ad_set_id     VARCHAR PRIMARY KEY,
    campaign_id   VARCHAR NOT NULL REFERENCES campaigns (campaign_id),
    name          VARCHAR NOT NULL
);
CREATE TABLE ads (
    ad_id         VARCHAR PRIMARY KEY,
    ad_set_id     VARCHAR NOT NULL REFERENCES ad_sets (ad_set_id),
    asset_name    VARCHAR NOT NULL
);
CREATE TABLE ad_daily (
    ad_id         VARCHAR NOT NULL REFERENCES ads (ad_id),
    day           DATE NOT NULL,
    spend         DOUBLE NOT NULL,                          -- rupees
    impressions   INTEGER NOT NULL,
    clicks        INTEGER NOT NULL,
    PRIMARY KEY (ad_id, day)
);
CREATE TABLE ad_set_daily (
    ad_set_id     VARCHAR NOT NULL REFERENCES ad_sets (ad_set_id),
    day           DATE NOT NULL,
    reach         INTEGER NOT NULL,
    frequency     DOUBLE NOT NULL,                          -- average impressions per person reached, as Meta reports it
    PRIMARY KEY (ad_set_id, day)
);
CREATE TABLE landing_page_daily (
    campaign_id       VARCHAR NOT NULL REFERENCES campaigns (campaign_id),
    day               DATE NOT NULL,
    sessions          INTEGER NOT NULL,
    bounces           INTEGER NOT NULL,
    avg_load_seconds  DOUBLE NOT NULL,
    PRIMARY KEY (campaign_id, day)
);

-- Funnel -------------------------------------------------------------------------------------------------
CREATE TABLE leads (                                        -- one row per ClickUp lead task; the attribute columns mirror the ClickUp fields
    lead_id       VARCHAR PRIMARY KEY,
    source_lead   VARCHAR NOT NULL CHECK (source_lead IN ('paid_ads', 'brochure', 'organic')),   -- ClickUp "Source lead"; only paid_ads leads carry a campaign
    campaign_id   VARCHAR REFERENCES campaigns (campaign_id),   -- NULL unless paid_ads
    ad_set_id     VARCHAR REFERENCES ad_sets (ad_set_id),
    ad_id         VARCHAR REFERENCES ads (ad_id),
    created_at    TIMESTAMP NOT NULL,                       -- ClickUp "Date created"
    parent_name   VARCHAR,
    student_name  VARCHAR,
    grade         INTEGER,
    school        VARCHAR,
    phone         VARCHAR,
    city          VARCHAR,
    utm_source    VARCHAR CHECK (utm_source IN ('instagram', 'meta')),    -- ClickUp "UTM source"; set for paid ads
    traffic_source VARCHAR CHECK (traffic_source IN ('instagram', 'facebook', 'google', 'direct'))
);
-- ClickUp stage names map to: Form Filled = lead, Under Review = review, Qualified = qualified, Qualification Conveyed = conveyed,
-- Discovery Call Scheduled = discovery_set, Discovery Call Completed = discovery_attended, Ambition Call = ambition_interview,
-- Architect Call = architect_session, Conversion = signed. Two exits: Rejected (after review) and Move to Nurture Database (after the discovery call).
CREATE TABLE lead_stages (                                  -- one row per stage a lead reached; a lead has a prefix of the path, then at most one exit
    lead_id       VARCHAR NOT NULL REFERENCES leads (lead_id),
    stage         VARCHAR NOT NULL CHECK (stage IN ('lead', 'review', 'qualified', 'conveyed', 'discovery_set', 'discovery_attended', 'ambition_interview',
                                                    'architect_session', 'signed', 'rejected', 'nurture')),
    reached_at    TIMESTAMP NOT NULL,
    PRIMARY KEY (lead_id, stage)
);

CREATE TABLE snapshot_meta (demo BOOLEAN NOT NULL, as_of DATE NOT NULL, seed INTEGER NOT NULL);
