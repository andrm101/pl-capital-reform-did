# Shared utilities for R estimation stages.
library(arrow)
library(tidyverse)

# ROOT resolves to PL-Capital-Reform-DiD/ when Rscript is called from that directory.
# The .git is in the parent Sandbox/, so here::here() would be wrong.
ROOT <- getwd()

read_panel <- function() {
  read_parquet(file.path(ROOT, "data/processed/panel_powiat.parquet")) |>
    mutate(teryt_powiat = str_pad(as.character(teryt_powiat), 4, pad = "0"))
}

read_nuts3 <- function() {
  path <- file.path(ROOT, "data/processed/nuts3_panel.parquet")
  if (!file.exists(path)) stop("nuts3_panel.parquet not found. Run Stage 01 first.")
  read_parquet(path)
}

write_processed <- function(df, filename) {
  out <- file.path(ROOT, "data/processed", filename)
  write_parquet(df, out)
  cat(sprintf("Saved -> data/processed/%s  (%d rows)\n", filename, nrow(df)))
}

figures_dir <- function() {
  d <- file.path(ROOT, "figures")
  dir.create(d, showWarnings = FALSE, recursive = TRUE)
  d
}
