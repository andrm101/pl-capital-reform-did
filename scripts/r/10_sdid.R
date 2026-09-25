#!/usr/bin/env Rscript
# Stage 10 — Synthetic DiD (Arkhangelsky et al. 2021, PNAS)
# Reads:  data/processed/panel_powiat.parquet
# Writes: data/processed/sdid_estimates.parquet
#         figures/f09_sdid_weights.png
#         figures/f09_sdid_trend.png

suppressPackageStartupMessages({
  library(arrow)
  library(synthdid)
  library(tidyverse)
})

source("scripts/r/utils.R")
cat("=== Stage 10: Synthetic DiD ===\n\n")

panel <- read_panel()

# SDiD-viable outcomes: must have pre-1999 data (1995-1998)
outcomes <- list(
  list(var = "ln_population",   label = "Log population"),
  list(var = "nat_change_rate", label = "Natural change rate"),
  list(var = "birth_rate",      label = "Birth rate per 1,000")
)

results <- list()

# Build synthdid-ready matrices manually:
#   - balanced panel (complete cases only)
#   - Y matrix: control units first, treated units last
#   - N0 = number of control rows, T0 = number of pre-treatment columns
make_sdid_matrices <- function(sub, treat_year = 1999) {
  # Keep only units with data in EVERY year in the sub panel
  year_set <- sort(unique(sub$year))
  n_years  <- length(year_set)
  complete_units <- sub |>
    group_by(teryt_powiat) |>
    summarise(n = n(), .groups = "drop") |>
    filter(n == n_years) |>
    pull(teryt_powiat)
  sub <- sub |> filter(teryt_powiat %in% complete_units)

  control_ids <- sub |> filter(treated == 0) |> distinct(teryt_powiat) |> pull()
  treated_ids <- sub |> filter(treated == 1) |> distinct(teryt_powiat) |> pull()

  if (length(treated_ids) == 0) stop("No treated units remain after balancing.")

  # Wide outcome matrix: rows = units (control first), cols = years
  Y <- sub |>
    select(teryt_powiat, year, value) |>
    pivot_wider(names_from = year, values_from = value) |>
    mutate(.order = if_else(teryt_powiat %in% control_ids, 0L, 1L)) |>
    arrange(.order, teryt_powiat) |>
    select(-.order) |>
    column_to_rownames("teryt_powiat") |>
    as.matrix()

  N0 <- length(control_ids)
  T0 <- sum(year_set < treat_year)
  list(Y = Y, N0 = N0, T0 = T0,
       n_treated = length(treated_ids),
       n_control = length(control_ids))
}

for (oc in outcomes) {
  cat(sprintf("\n[%s]\n", oc$var))

  sub <- panel |>
    filter(!is.na(.data[[oc$var]]), year >= 1995, year <= 2023) |>
    select(teryt_powiat, year, value = all_of(oc$var), treated)

  tryCatch({
    mx <- make_sdid_matrices(sub)
    Y  <- mx$Y; N0 <- mx$N0; T0 <- mx$T0

    cat(sprintf("  Units: %d (%d treated, %d control)  T0=%d  T=%d\n",
        nrow(Y), mx$n_treated, mx$n_control, T0, ncol(Y)))

    if (any(is.na(Y))) stop("NAs remain in Y after balancing.")

    est <- synthdid_estimate(Y, N0, T0)
    se  <- tryCatch(
      sqrt(vcov(est, method = "placebo")),
      error = function(e) NA_real_
    )

    att <- as.numeric(est)
    cat(sprintf("  ATT = %.4f  SE = %.4f\n", att, se))

    results[[oc$var]] <- tibble(
      outcome   = oc$var,
      estimator = "SDiD",
      att       = att,
      se        = se,
      ci_lo     = att - 1.96 * se,
      ci_hi     = att + 1.96 * se,
      n_units   = nrow(Y),
      n_years   = ncol(Y)
    )

    # Diagnostic plots for ln_population only
    if (oc$var == "ln_population") {
      tryCatch({
        png(file.path(figures_dir(), "f09_sdid_weights.png"),
            width = 900, height = 500, res = 120)
        omega     <- attr(est, "weights")$omega
        top_units <- names(sort(omega, decreasing = TRUE))[1:min(20, length(omega))]
        synthdid_units_plot(est, units = top_units)
        dev.off()
        cat("  Saved: f09_sdid_weights.png\n")
      }, error = function(e) cat(sprintf("  [WARN] weights plot: %s\n", e$message)))

      tryCatch({
        png(file.path(figures_dir(), "f09_sdid_trend.png"),
            width = 900, height = 500, res = 120)
        synthdid_plot(est, se.method = "placebo")
        dev.off()
        cat("  Saved: f09_sdid_trend.png\n")
      }, error = function(e) cat(sprintf("  [WARN] trend plot: %s\n", e$message)))
    }

  }, error = function(e) {
    cat(sprintf("  [ERROR] %s\n", conditionMessage(e)))
  })
}

if (length(results) > 0) {
  out <- bind_rows(results)
  write_processed(out, "sdid_estimates.parquet")
  print(out[, c("outcome", "estimator", "att", "se", "ci_lo", "ci_hi")])
} else {
  cat("[WARN] No SDiD estimates produced.\n")
}

cat("\n=== Stage 10 complete ===\n")
