#!/usr/bin/env Rscript
# Stage 11b — NUTS-3 Parallel GDP Analysis
# Reads:  data/processed/nuts3_panel.parquet
# Writes: data/processed/nuts3_lp_irfs.parquet
#         data/processed/nuts3_gsynth_gaps.parquet
#         figures/f11_nuts3_lp_gdp.png
#         figures/f11_nuts3_gsynth_gdp.png
#
# NOTE: Eurostat NUTS-3 GDP data begins 2000 — no pre-1999 periods available.
# LP horizons are measured from 2000 (base year = 1 yr post-reform).
# GSC uses T0=1 (2000 as single pre-treatment year) — acknowledged limitation.

suppressPackageStartupMessages({
  library(arrow)
  library(gsynth)
  library(tidyverse)
  library(sandwich)   # HC robust SEs
  library(lmtest)     # coeftest
})

source("scripts/r/utils.R")
cat("=== Stage 11b: NUTS-3 Parallel GDP Analysis ===\n\n")

# ── 0. Load & clean ────────────────────────────────────────────────────────────
n3 <- read_parquet("data/processed/nuts3_panel.parquet") |>
  filter(year <= 2023, !is.na(gdp_pps_hab)) |>
  mutate(
    n_demoted  = if_else(is.na(n_demoted), 0L, as.integer(n_demoted)),
    n_old_caps = if_else(is.na(n_old_caps), 0L, as.integer(n_old_caps)),
    treatment_intensity = if_else(n_old_caps == 0L, 0, n_demoted / n_old_caps),
    any_demoted = as.integer(any_demoted),
    post        = as.integer(year >= 1999)   # all years in data are post
  )

# Balanced: keep units with data in ALL years 2000-2023
year_set <- 2000:2023
n_yrs    <- length(year_set)
complete_nuts3 <- n3 |>
  group_by(nuts3) |>
  summarise(n = n(), .groups = "drop") |>
  filter(n == n_yrs) |>
  pull(nuts3)

n3 <- n3 |> filter(nuts3 %in% complete_nuts3)

n_treated <- n_distinct(n3[n3$any_demoted == 1, "nuts3"])
n_control <- n_distinct(n3[n3$any_demoted == 0, "nuts3"])
cat(sprintf("Balanced panel: %d NUTS-3 units (%d treated, %d control), %d years\n\n",
    n_treated + n_control, n_treated, n_control, n_yrs))

# ── 1. Local Projections ────────────────────────────────────────────────────────
# Cross-sectional LP at each horizon h = 0, ..., 22
# Y_{i,2000+h} - Y_{i,2000} = alpha + beta_h * any_demoted_i + eps_i
# OLS with HC2 robust SEs (N=73, cross-sectional)
cat("--- LP: cross-sectional at each horizon ---\n")

base_year <- 2000
horizons  <- 0:22  # 2000-2022

base_gdp <- n3 |>
  filter(year == base_year) |>
  select(nuts3, ln_gdp_base = ln_gdp_pps_hab, any_demoted)

lp_results <- vector("list", length(horizons))
for (h in horizons) {
  target_yr <- base_year + h
  outcome   <- n3 |>
    filter(year == target_yr) |>
    select(nuts3, ln_gdp_target = ln_gdp_pps_hab)

  df_h <- base_gdp |>
    left_join(outcome, by = "nuts3") |>
    mutate(dep = ln_gdp_target - ln_gdp_base) |>
    filter(!is.na(dep))

  if (nrow(df_h) < 10) next

  fit <- lm(dep ~ any_demoted, data = df_h)
  ct  <- coeftest(fit, vcov = vcovHC(fit, type = "HC2"))

  coef_row <- ct["any_demoted", , drop = FALSE]
  lp_results[[h + 1]] <- tibble(
    horizon   = h,
    coef      = coef_row[1, "Estimate"],
    se        = coef_row[1, "Std. Error"],
    ci_lo_90  = coef_row[1, "Estimate"] - 1.645 * coef_row[1, "Std. Error"],
    ci_hi_90  = coef_row[1, "Estimate"] + 1.645 * coef_row[1, "Std. Error"],
    ci_lo_95  = coef_row[1, "Estimate"] - 1.960 * coef_row[1, "Std. Error"],
    ci_hi_95  = coef_row[1, "Estimate"] + 1.960 * coef_row[1, "Std. Error"],
    n_units   = nrow(df_h)
  )
}

lp_irfs <- bind_rows(lp_results)
write_processed(lp_irfs, "nuts3_lp_irfs.parquet")
cat(sprintf("LP complete: %d horizons estimated\n", nrow(lp_irfs)))

# LP figure
tryCatch({
  p_lp <- ggplot(lp_irfs, aes(x = horizon + base_year, y = coef)) +
    geom_hline(yintercept = 0, colour = "grey60") +
    geom_ribbon(aes(ymin = ci_lo_95, ymax = ci_hi_95), alpha = 0.15, fill = "#4d7cff") +
    geom_ribbon(aes(ymin = ci_lo_90, ymax = ci_hi_90), alpha = 0.25, fill = "#4d7cff") +
    geom_line(colour = "#4d7cff", linewidth = 1) +
    geom_point(colour = "#4d7cff", size = 2) +
    labs(
      title    = "NUTS-3 LP: GDP per capita gap (demoted vs control regions)",
      subtitle = "Baseline = 2000 (year 1 post-reform); outcome = ln GDP/cap PPS. HC2 SEs.",
      x = "Year", y = expression(Delta * " ln GDP/cap (demoted - control)"),
      caption  = "Source: Eurostat nama_10r_3gdp. Note: pre-1999 data unavailable at NUTS-3."
    ) +
    theme_minimal()
  ggsave(file.path(figures_dir(), "f11_nuts3_lp_gdp.png"),
         p_lp, width = 10, height = 5, dpi = 150)
  cat("Saved: f11_nuts3_lp_gdp.png\n")
}, error = function(e) cat(sprintf("  [WARN] LP plot: %s\n", e$message)))

# ── 2. GSC at NUTS-3 ────────────────────────────────────────────────────────────
# T0=1 (2000 as single pre-treatment year; treatment indicator switches 2001+)
# Acknowledged limitation: factor model is thin with T0=1. Reported in methods.
cat("\n--- GSC at NUTS-3 (T0=1, treating 2001 as post-treatment start) ---\n")
cat("[NOTE] Eurostat GDP data starts 2000; T0=1 is the max feasible pre-period.\n")
cat("       Cross-sectional identification (large N_control=", n_control, ") partially compensates.\n\n", sep="")

# Treatment indicator: 0 in 2000 (pre), 1 in 2001-2023 (post) for treated units
gsynth_panel <- n3 |>
  mutate(treated_post = any_demoted * as.integer(year >= 2001)) |>
  select(nuts3, year, ln_gdp_pps_hab, any_demoted, treated_post)

set.seed(42)
gsynth_out <- tryCatch({
  gsynth(
    ln_gdp_pps_hab ~ treated_post,
    data      = as.data.frame(gsynth_panel),
    index     = c("nuts3", "year"),
    force     = "two-way",
    CV        = TRUE,
    r         = c(0, 3),
    se        = TRUE,
    inference = "parametric",
    nboots    = 500,
    seed      = 42,
    min.T0    = 1,
    estimator = "ife"
  )
}, error = function(e) {
  cat(sprintf("[ERROR] gsynth failed: %s\n", e$message)); NULL
})

if (!is.null(gsynth_out)) {
  cat(sprintf("Optimal r = %d\n", gsynth_out$r.cv))
  cat(sprintf("Average ATT (post-2001): %.4f\n", mean(gsynth_out$att, na.rm = TRUE)))

  # Sensitivity: r=1 fixed
  gsynth_r1 <- tryCatch(
    gsynth(ln_gdp_pps_hab ~ treated_post, data=as.data.frame(gsynth_panel),
           index=c("nuts3","year"), force="two-way", CV=FALSE, r=1,
           se=TRUE, inference="parametric", nboots=500, seed=42, min.T0=1, estimator="ife"),
    error = function(e) { cat(sprintf("[WARN] r=1 sensitivity failed: %s\n", e$message)); NULL }
  )
  if (!is.null(gsynth_r1)) {
    cat(sprintf("Sensitivity r=1 ATT: %.4f\n", mean(gsynth_r1$att, na.rm=TRUE)))
  }

  # Build gaps parquet from eff matrix
  all_yrs  <- as.integer(rownames(gsynth_out$eff))
  eff_mat  <- gsynth_out$eff

  treated_ids <- gsynth_panel |> filter(any_demoted == 1) |>
    distinct(nuts3) |> pull(nuts3)

  gaps_list <- lapply(treated_ids, function(uid) {
    if (!uid %in% colnames(eff_mat)) return(NULL)
    gap_vec    <- as.numeric(eff_mat[, uid])
    actual_vec <- gsynth_panel[gsynth_panel$nuts3 == uid,
                               c("year","ln_gdp_pps_hab")] |>
                    dplyr::arrange(year) |> dplyr::pull(ln_gdp_pps_hab)
    data.frame(
      nuts3          = uid,
      year           = all_yrs,
      actual         = actual_vec,
      counterfactual = actual_vec - gap_vec,
      gap            = gap_vec,
      stringsAsFactors = FALSE
    )
  })

  nuts3_gaps <- as_tibble(do.call(rbind, Filter(Negate(is.null), gaps_list)))
  nuts3_gaps$year <- as.integer(nuts3_gaps$year)

  # att_avg per region
  att_avg_n3 <- nuts3_gaps[nuts3_gaps$year >= 2001, ] |>
    group_by(nuts3) |>
    summarise(att_avg = mean(gap, na.rm=TRUE), .groups="drop")
  nuts3_gaps <- left_join(nuts3_gaps, att_avg_n3, by="nuts3")

  write_processed(nuts3_gaps, "nuts3_gsynth_gaps.parquet")
  cat(sprintf("nuts3_gsynth_gaps.parquet: %d rows, %d units\n",
      nrow(nuts3_gaps), n_distinct(nuts3_gaps$nuts3)))

  # GSC figure
  tryCatch({
    agg_gap <- nuts3_gaps[nuts3_gaps$nuts3 %in% treated_ids, ] |>
      group_by(year) |>
      summarise(gap_mean = mean(gap, na.rm=TRUE), .groups="drop")

    p_gsc <- ggplot(agg_gap, aes(x=year, y=gap_mean)) +
      geom_hline(yintercept=0, colour="grey60") +
      geom_vline(xintercept=2001, linetype="dashed", colour="#e8a800") +
      geom_line(colour="#4d7cff", linewidth=1) +
      labs(
        title    = "NUTS-3 GSC: average GDP/cap gap (demoted vs counterfactual)",
        subtitle = sprintf("r*=%d; T0=1 (2000 as single pre-treatment year). N_tr=%d, N_co=%d.",
                           gsynth_out$r.cv, n_treated, n_control),
        x = "Year", y = "ln GDP/cap gap",
        caption = "Source: Eurostat. Note: T0=1 is a binding constraint; interpret with caution."
      ) +
      theme_minimal()
    ggsave(file.path(figures_dir(), "f11_nuts3_gsynth_gdp.png"),
           p_gsc, width=10, height=5, dpi=150)
    cat("Saved: f11_nuts3_gsynth_gdp.png\n")
  }, error = function(e) cat(sprintf("  [WARN] GSC plot: %s\n", e$message)))

} else {
  cat("[WARN] GSC skipped — writing empty gaps parquet.\n")
  nuts3_gaps <- tibble(nuts3=character(), year=integer(), actual=double(),
                       counterfactual=double(), gap=double(), att_avg=double())
  write_processed(nuts3_gaps, "nuts3_gsynth_gaps.parquet")
}

cat("\n=== Stage 11b complete ===\n")
