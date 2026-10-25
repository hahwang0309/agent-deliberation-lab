# Supplementary optimizer / random-effect diagnostics. Registered output unchanged.
suppressPackageStartupMessages({library(lme4);library(jsonlite)})
args<-commandArgs(trailingOnly=TRUE)
d<-read.csv(args[1]);out<-args[2]
forms<-list(
 registered="correct ~ k1 + k2p + ai + k1:ai + k2p:ai + group_size + (1|block) + (1|run) + (1|card_set)",
 no_run_RE="correct ~ k1 + k2p + ai + k1:ai + k2p:ai + group_size + (1|block) + (1|card_set)")
results<-list()
for(nm in names(forms))for(opt in if(nm=="registered")c("bobyqa","nloptwrap")else"bobyqa"){
 msgs<-character(0)
 fit<-withCallingHandlers(glmer(as.formula(forms[[nm]]),data=d,family=binomial,
  control=glmerControl(optimizer=opt,optCtrl=if(opt=="bobyqa")list(maxfun=100000)else list(maxeval=100000))),
  warning=function(w){msgs<<-c(msgs,conditionMessage(w));invokeRestart("muffleWarning")},
  message=function(m){msgs<<-c(msgs,conditionMessage(m));invokeRestart("muffleMessage")})
 co<-summary(fit)$coef
 vc<-as.data.frame(VarCorr(fit))
 he<-fit@optinfo$derivs$Hessian
 results[[paste(nm,opt,sep="_")]]<-list(formula=forms[[nm]],optimizer=opt,n=nobs(fit),
  logLik=as.numeric(logLik(fit)),singular=isSingular(fit),warnings=unique(msgs),
  optimizer_code=fit@optinfo$conv$opt,convergence_messages=fit@optinfo$conv$lme4$messages,
  hessian_eigenvalues=if(is.null(he))NULL else eigen(he,symmetric=TRUE,only.values=TRUE)$values,
  conditional_probability_range=range(fitted(fit)),random_effects=vc,
  coefficients=lapply(rownames(co),function(term)list(term=term,estimate=co[term,1],se=co[term,2],p=co[term,4])))
}
write_json(results,out,auto_unbox=TRUE,digits=NA,na="null")
