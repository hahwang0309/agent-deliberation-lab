# 혼합 모형 적합 (src/analysis/mixed.py가 호출)
# 사용: Rscript fit_mixed.R <data.csv> <formula> <gaussian|binomial> <out.json>
# gaussian: lmerTest::lmer (REML, Satterthwaite 자유도), binomial: lme4::glmer (Wald z)
# 무선 효과가 없는 식이면 lm / glm으로 적합한다.
suppressPackageStartupMessages({
  library(lme4)
  library(lmerTest)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
data <- read.csv(args[1], stringsAsFactors = TRUE)
form <- as.formula(args[2])
family <- args[3]
out <- args[4]

msgs <- character(0)
has_re <- !is.null(reformulas::findbars(form))
fit <- withCallingHandlers(
  if (!has_re) {
    if (family == "binomial") glm(form, data = data, family = binomial) else lm(form, data = data)
  } else if (family == "binomial") {
    glmer(form, data = data, family = binomial, control = glmerControl(optimizer = "bobyqa"))
  } else {
    lmerTest::lmer(form, data = data, REML = TRUE)
  },
  warning = function(w) { msgs <<- c(msgs, conditionMessage(w)); invokeRestart("muffleWarning") },
  message = function(m) { msgs <<- c(msgs, conditionMessage(m)); invokeRestart("muffleMessage") }
)

co <- summary(fit)$coefficients
p_col <- grep("^Pr\\(", colnames(co))
df_col <- which(colnames(co) == "df")
rows <- lapply(rownames(co), function(term) {
  est <- co[term, 1]; se <- co[term, 2]
  if (length(df_col)) {
    q <- qt(0.975, co[term, df_col]); dfv <- co[term, df_col]
  } else if (!has_re && family != "binomial") {
    dfv <- df.residual(fit); q <- qt(0.975, dfv)
  } else {
    q <- qnorm(0.975); dfv <- NA
  }
  list(term = term, estimate = est, se = se, df = dfv, p = co[term, p_col],
       ci_low = est - q * se, ci_high = est + q * se)
})
singular <- if (has_re) isSingular(fit) else FALSE
res <- list(n = nobs(fit), singular = singular, messages = unique(msgs), coefficients = rows,
            groups = if (has_re) as.list(ngrps(fit)) else list())
write_json(res, out, auto_unbox = TRUE, digits = NA, na = "null")
