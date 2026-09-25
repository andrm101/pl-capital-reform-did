# Run once: Rscript scripts/r/install_packages.R
options(repos = c(CRAN = "https://cloud.r-project.org"))

cran_pkgs <- c("arrow", "tidyverse", "gsynth", "did", "plm", "sandwich",
               "lmtest", "renv", "remotes")

missing <- cran_pkgs[!cran_pkgs %in% installed.packages()[, "Package"]]
if (length(missing) > 0) {
  cat(sprintf("Installing %d missing CRAN packages: %s\n", length(missing), paste(missing, collapse=", ")))
  install.packages(missing)
}

# synthdid is not on CRAN for R >= 4.5 — install from GitHub
if (!requireNamespace("synthdid", quietly = TRUE)) {
  cat("Installing synthdid from GitHub (synth-inference/synthdid)...\n")
  remotes::install_github("synth-inference/synthdid")
}

for (pkg in c("synthdid", "gsynth", "arrow")) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(sprintf("Package '%s' failed to install.", pkg))
  }
}

cat("All packages installed and verified.\n")
