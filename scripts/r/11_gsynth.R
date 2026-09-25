#!/usr/bin/env Rscript
# Stage 11 — Generalised Synthetic Control (Xu 2017)
# Produces per-city counterfactual trajectories for all 31 demoted cities.
# Reads:  data/processed/panel_powiat.parquet
# Writes: data/processed/gsynth_gaps.parquet
#         figures/f10_gsynth_aggregate.png
#         figures/f10_gsynth_grid.png
#         figures/f10_gsynth_ebar.png

suppressPackageStartupMessages({
  library(arrow)
  library(gsynth)
  library(tidyverse)
})

source("scripts/r/utils.R")
cat("=== Stage 11: Generalised Synthetic Control ===\n\n")

panel <- read_panel()

# Prepare balanced population panel (1995-2023)
pop_panel <- panel |>
  filter(!is.na(ln_population), year >= 1995, year <= 2023) |>
  select(teryt_powiat, year, ln_population, treated) |>
  mutate(
    treated_post = treated * as.integer(year >= 1999),
    teryt_powiat = as.character(teryt_powiat)
  )

# Keep only units with complete observations across all years
n_years <- n_distinct(pop_panel$year)
complete_units <- pop_panel |>
  group_by(teryt_powiat) |>
  summarise(n = n(), nas = sum(is.na(ln_population)), .groups = "drop") |>
  filter(nas == 0, n == n_years) |>
  pull(teryt_powiat)

pop_panel <- pop_panel |> filter(teryt_powiat %in% complete_units)

treated_ids <- pop_panel |>
  filter(treated == 1) |>
  pull(teryt_powiat) |>
  unique()

cat(sprintf("Balanced panel: %d units (%d treated, %d control), %d years\n",
    n_distinct(pop_panel$teryt_powiat),
    length(treated_ids),
    n_distinct(pop_panel$teryt_powiat) - length(treated_ids),
    n_years))

set.seed(42)
cat("Fitting gsynth (CV over r={0..5}, parametric bootstrap, B=500)...\n")

out <- gsynth(
  ln_population ~ treated_post,
  data      = as.data.frame(pop_panel),
  index     = c("teryt_powiat", "year"),
  force     = "two-way",
  CV        = TRUE,
  r         = c(0, 5),
  se        = TRUE,
  inference = "parametric",
  nboots    = 500,
  seed      = 42,
  min.T0    = 4,
  estimator = "ife"
)

cat(sprintf("Optimal r = %d\n", out$r.cv))
cat(sprintf("Average ATT (post-treatment): %.4f\n", mean(out$att, na.rm = TRUE)))

# --- Build gaps parquet ---
# out$eff: T × N matrix, rownames=years, colnames=teryt codes (all units)
# out$rawtime: time vector; out$tr: 1-based treated unit indices in full ordering
all_yrs   <- as.integer(rownames(out$eff))
eff_mat   <- out$eff  # T × N, all units

gaps_list <- lapply(treated_ids, function(uid) {
  gap_vec    <- as.numeric(eff_mat[, uid])
  actual_vec <- pop_panel[pop_panel$teryt_powiat == uid,
                          c("year", "ln_population")] |>
                  dplyr::arrange(year) |>
                  dplyr::pull(ln_population)
  data.frame(
    teryt_powiat   = uid,
    year           = all_yrs,
    actual         = actual_vec,
    counterfactual = actual_vec - gap_vec,
    gap            = gap_vec,
    se_gap         = NA_real_,
    stringsAsFactors = FALSE
  )
})

gaps <- as_tibble(do.call(rbind, gaps_list))
gaps$year <- as.integer(gaps$year)

# Per-city average post-treatment ATT (HTE hook for Stage 12)
att_avg <- gaps[gaps$year >= 1999L & gaps$teryt_powiat %in% treated_ids, ] |>
  group_by(teryt_powiat) |>
  summarise(att_avg = mean(gap, na.rm = TRUE), .groups = "drop")

gaps <- gaps |> left_join(att_avg, by = "teryt_powiat")

write_processed(gaps, "gsynth_gaps.parquet")
cat(sprintf("gsynth_gaps.parquet: %d rows, %d units\n", nrow(gaps), n_distinct(gaps$teryt_powiat)))

# --- Figures ---

# Aggregate gap plot — ggplot2 from gaps data
tryCatch({
  agg_gap <- gaps[gaps$teryt_powiat %in% treated_ids, ] |>
    group_by(year) |>
    summarise(gap_mean = mean(gap, na.rm = TRUE), .groups = "drop")
  p_agg <- ggplot(agg_gap, aes(x = year, y = gap_mean)) +
    geom_hline(yintercept = 0, colour = "grey60") +
    geom_vline(xintercept = 1999, linetype = "dashed", colour = "#e8a800") +
    geom_line(colour = "#4d7cff", linewidth = 1) +
    labs(title = "Average GSC gap: demoted vs counterfactual (ln population)",
         x = "Year", y = "Mean gap (actual − counterfactual)") +
    theme_minimal()
  ggsave(file.path(figures_dir(), "f10_gsynth_aggregate.png"),
         p_agg, width = 9, height = 4.5, dpi = 120)
  cat("Saved: f10_gsynth_aggregate.png\n")
}, error = function(e) cat(sprintf("  [WARN] aggregate plot: %s\n", e$message)))

# 3x4 grid of selected cities
selected <- treated_ids[1:min(12, length(treated_ids))]
tryCatch({
  png(file.path(figures_dir(), "f10_gsynth_grid.png"),
      width = 1200, height = 900, res = 120)
  par(mfrow = c(3, 4), mar = c(3, 3, 2, 1))
  for (uid in selected) {
    city_data <- gaps |> filter(teryt_powiat == uid) |> arrange(.data[["year"]])
    y_range <- range(c(exp(city_data$actual), exp(city_data$counterfactual)), na.rm = TRUE)
    plot(city_data$year, exp(city_data$actual),
         type = "l", col = "#4d7cff", lwd = 2,
         main = uid, xlab = "", ylab = "Pop",
         ylim = y_range)
    lines(city_data$year, exp(city_data$counterfactual),
          col = "#4dffb4", lwd = 2, lty = 2)
    abline(v = 1999, col = "#e8ff47", lty = 3, lwd = 1)
  }
  dev.off()
  cat("Saved: f10_gsynth_grid.png\n")
}, error = function(e) cat(sprintf("  [WARN] grid plot: %s\n", e$message)))

# Ordered ATT bar chart
tryCatch({
  att_plot <- att_avg |> arrange(att_avg)
  png(file.path(figures_dir(), "f10_gsynth_ebar.png"),
      width = 900, height = 600, res = 120)
  bar_cols <- ifelse(att_plot$att_avg < 0, "#ff4d4d", "#4dffb4")
  barplot(att_plot$att_avg,
          names.arg = att_plot$teryt_powiat,
          las = 2, col = bar_cols,
          main = "Per-city average ATT (log population, 1999-2023)",
          ylab = "ATT", cex.names = 0.7)
  abline(h = 0, lwd = 1)
  dev.off()
  cat("Saved: f10_gsynth_ebar.png\n")
}, error = function(e) cat(sprintf("  [WARN] ebar plot: %s\n", e$message)))

cat("\n=== Stage 11 complete ===\n")
