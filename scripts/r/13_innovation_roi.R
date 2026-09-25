# 13_innovation_roi.R
# Stage 13: Innovation Hub forecast path for demoted Polish cities.
# Reads nuts3_gsynth_gaps.parquet (GDP baseline) and pvar_forecasts.parquet
# (status_quo / counterfactual paths, plus 480 all-null innovation_hub
# placeholder rows from Stage 09). Produces the innovation_hub path with a
# three-estimate (A/B/C) bracket, written back into pvar_forecasts.parquet.
#
# This is the Poland implementation of the same methodology first built and
# validated in RO-Administrative-Reform/scripts/r/13_innovation_roi.R -- see
# docs/superpowers/specs/2026-09-25-stage13-innovation-roi-design.md.

library(arrow)
library(dplyr)
library(tidyr)
library(readr)
library(stringr)

set.seed(42)

ROOT <- tryCatch({
  wd <- getwd()
  if (dir.exists(file.path(wd, "data", "processed"))) {
    wd
  } else {
    script_path <- tryCatch(normalizePath(sys.frame(1)$ofile), error = function(e) NULL)
    if (!is.null(script_path)) {
      normalizePath(file.path(dirname(script_path), "..", ".."))
    } else {
      here::here()
    }
  }
}, error = function(e) getwd())
DATA_PROC <- file.path(ROOT, "data", "processed")
SIBLING_ROOT <- normalizePath(file.path(ROOT, ".."))

FCST_PATH       <- file.path(DATA_PROC, "pvar_forecasts.parquet")
ESTIMATE_A_PATH <- file.path(SIBLING_ROOT, "EU-Innovation-Panel", "analysis",
                              "p11_archetype_growth_premium.csv")
ESTIMATE_C_PATH <- file.path(ROOT, "analysis", "retained_capital_benchmark.csv")

# Forecast horizon here is 2024-2035 (Poland's 1999 reform is long in the past;
# this path models a hypothetical innovation-hub investment starting now, at
# the beginning of the forecast horizon -- unlike RO-Administrative-Reform,
# where REFORM_YEAR=2025 coincides with the still-prospective Romanian reform
# itself). REFORM_YEAR here means "investment start," not "reform year."
REFORM_YEAR <- 2024
RAMP_YEARS  <- 5

check_sibling_path <- function(path, label) {
  if (!file.exists(path)) {
    stop(sprintf(
      "Missing dependency for %s: expected file at %s. %s",
      label, path,
      "Run that project's Stage 13 input script first (see docs/superpowers/specs/2026-09-25-stage13-innovation-roi-design.md)."
    ))
  }
  path
}
check_sibling_path(ESTIMATE_A_PATH, "Estimate A (archetype growth premium)")
check_sibling_path(ESTIMATE_C_PATH, "Estimate C (retained-capital benchmark)")

# Same corrected Estimate B table as RO-Administrative-Reform's Stage 13.
MORETTI_MULTIPLIERS <- c(
  T1 = 0.025, T2 = 0.020, T3 = 0.015, T4 = 0.012, T5 = 0.010,
  T6 = 0.014, T7 = 0.015, T8 = 0.018
)

# ── Load inputs ──────────────────────────────────────────────────────────────
fcst_raw <- read_parquet(FCST_PATH)
fcst <- fcst_raw |> filter(path != "innovation_hub")

cat("Forecast rows (excl. placeholder innovation_hub):", nrow(fcst), "\n")
cat("Variables:", paste(unique(fcst$variable), collapse = ", "), "\n")
cat("Years:", min(fcst$year), "-", max(fcst$year), "\n")

estimate_a <- read_csv(ESTIMATE_A_PATH, show_col_types = FALSE) |>
  select(archetype_id, growth_premium_pp) |>
  mutate(estimate_a_annual = growth_premium_pp / 100)

estimate_c_annual <- read_csv(ESTIMATE_C_PATH, show_col_types = FALSE) |>
  filter(city_en == "AVERAGE") |>
  pull(annual_growth_ln)
stopifnot(length(estimate_c_annual) == 1, !is.na(estimate_c_annual))

# Poland doesn't currently carry an archetype_id or MegaCampus Tier-1 type per
# city in this repo's processed data; without a per-city ecosystem type,
# Estimate B falls back to a flat central multiplier (advanced-manufacturing
# tier, T3) for every demoted city. A Poland-specific MegaCampus overlay
# (mirroring RO-Administrative-Reform's build_nuts3_suitability.py) is future
# work -- see docs/superpowers/plans/2026-09-25-stage13-innovation-roi.md
# Task 6 Step 3 / VISION.md "Next concrete actions".
estimate_b_annual <- unname(MORETTI_MULTIPLIERS["T3"])
central_archetype_premium <- estimate_a |>
  summarise(mean_a = mean(estimate_a_annual, na.rm = TRUE)) |>
  pull(mean_a)

bracket_pessimistic <- min(central_archetype_premium, estimate_b_annual, estimate_c_annual, na.rm = TRUE)
bracket_central      <- estimate_b_annual
bracket_optimistic   <- max(central_archetype_premium, estimate_b_annual, estimate_c_annual, na.rm = TRUE)

cat("Estimate A (mean archetype premium):", central_archetype_premium, "\n")
cat("Estimate B (Moretti, T3 flat):", estimate_b_annual, "\n")
cat("Estimate C (retained-capital benchmark):", estimate_c_annual, "\n")
cat("Bracket: pessimistic =", bracket_pessimistic,
    ", central =", bracket_central,
    ", optimistic =", bracket_optimistic, "\n")

# ── Build innovation_hub path ────────────────────────────────────────────────
counterfactual_rows <- fcst |> filter(path == "counterfactual")

compute_ramp <- function(bracket_bound, year) {
  case_when(
    year < REFORM_YEAR ~ 0,
    year >= REFORM_YEAR & year < REFORM_YEAR + RAMP_YEARS ~
      bracket_bound * (year - REFORM_YEAR + 1) / RAMP_YEARS,
    TRUE ~ bracket_bound
  )
}

innovation_rows <- counterfactual_rows |>
  mutate(
    ramp_factor = compute_ramp(bracket_central, year),
    ramp_factor_pessimistic = compute_ramp(bracket_pessimistic, year),
    ramp_factor_optimistic  = compute_ramp(bracket_optimistic, year),
    value_orig = value,
    value = if_else(
      variable == "ln_population",
      value + ramp_factor * (year - REFORM_YEAR + 1),
      value
    ),
    value_pessimistic = if_else(
      variable == "ln_population",
      value_orig + ramp_factor_pessimistic * (year - REFORM_YEAR + 1),
      NA_real_
    ),
    value_optimistic = if_else(
      variable == "ln_population",
      value_orig + ramp_factor_optimistic * (year - REFORM_YEAR + 1),
      NA_real_
    ),
    lo80 = if_else(variable == "ln_population", lo80 - abs(value_orig - lo80) * 0.05, lo80),
    hi80 = if_else(variable == "ln_population", hi80 + abs(hi80 - value_orig) * 0.05, hi80),
    lo95 = if_else(variable == "ln_population", lo95 - abs(value_orig - lo95) * 0.05, lo95),
    hi95 = if_else(variable == "ln_population", hi95 + abs(hi95 - value_orig) * 0.05, hi95),
    path = "innovation_hub"
  ) |>
  select(-ramp_factor, -ramp_factor_pessimistic, -ramp_factor_optimistic, -value_orig)

fcst_out <- bind_rows(fcst, innovation_rows) |>
  arrange(across(any_of(c("teryt_powiat", "city_en"))), variable, path, year)

write_parquet(fcst_out, FCST_PATH)
cat("Written:", FCST_PATH, "\n")
cat("Rows:", nrow(fcst_out), "(added", nrow(innovation_rows), "innovation_hub rows)\n")
