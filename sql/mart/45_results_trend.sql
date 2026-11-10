-- mart.results_trend
-- Grain: one row per Managing for Results measure with at least three actual years and positive endpoint values.
-- What: the measure's first and last actual outcome next to the agency's real (CPI-adjusted) budget change over the
-- same window (recommendation 6, "spending to results"). Side by side, not cause and effect: the budget is the
-- agency's whole budget, so this is not a unit cost. outcome_minus_spend is the outcome change minus the real
-- budget change (both as shares of the first year); positive means outcomes grew faster than real spending.
-- Check: every row has years_actual >= 3, first_fy < last_fy, positive endpoints, last_fy no later than the last
-- confirmed actual budget year.
-- Guard: endpoint ratios beyond 20x growth or a 95% collapse are dropped. The measure text is scraped from MFR
-- documents, and ratios that extreme are almost always unit or parse artifacts (a stray "0" parsed as the first
-- actual), not real trends; they would swamp every ranking on the dashboard.
CREATE OR REPLACE TABLE mart.results_trend AS
WITH act AS (
  SELECT agency_code, agency_name, goal, objective, measure, fiscal_year, value,
         budget * to_latest_dollars AS budget_real
  FROM mart.agency_results
  WHERE kind = 'Actual' AND value IS NOT NULL AND value > 0 AND budget IS NOT NULL
    AND fiscal_year <= (SELECT max(fiscal_year) FROM ref.dim_stage WHERE stage = 'Actual')
),
ends AS (
  SELECT agency_code, measure,
         count(*) AS years_actual,
         min(fiscal_year) AS first_fy, max(fiscal_year) AS last_fy,
         arg_min(value, fiscal_year) AS first_value, arg_max(value, fiscal_year) AS last_value,
         arg_min(budget_real, fiscal_year) AS first_budget_real, arg_max(budget_real, fiscal_year) AS last_budget_real,
         arg_max(agency_name, fiscal_year) AS agency_name,
         arg_max(goal, fiscal_year) AS goal, arg_max(objective, fiscal_year) AS objective
  FROM act
  GROUP BY agency_code, measure
  HAVING count(*) >= 3 AND max(fiscal_year) > min(fiscal_year)
)
SELECT agency_code, agency_name, goal, objective, measure, years_actual, first_fy, last_fy,
       round(first_value, 4) AS first_value, round(last_value, 4) AS last_value,
       round(last_value / first_value - 1, 4) AS value_change,
       round(first_budget_real, 0) AS first_budget_real, round(last_budget_real, 0) AS last_budget_real,
       round(last_budget_real / first_budget_real - 1, 4) AS budget_change_real,
       round((last_value / first_value - 1) - (last_budget_real / first_budget_real - 1), 4) AS outcome_minus_spend
FROM ends
WHERE first_value > 0 AND first_budget_real > 0
  AND last_value / first_value BETWEEN 0.05 AND 20;
