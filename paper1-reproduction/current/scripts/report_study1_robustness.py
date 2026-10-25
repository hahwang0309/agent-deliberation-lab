"""Render the targeted robustness results and explain the scope of each check."""
import hashlib
import json
import os
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR','/private/tmp/robustness-matplotlib')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/research/robustness';SRC=OUT/'source-data'
MODELS=['claude','gemini','mistral']
read=lambda n:json.loads((SRC/n).read_text())


def fmt(r,scale=1,digits=3):
    return f"{r['estimate']*scale:+.{digits}f} [{r['ci'][0]*scale:+.{digits}f}, {r['ci'][1]*scale:+.{digits}f}]"


def main():
    people={m:read(m+'-persona.json')for m in MODELS}
    h={m:read(m+'-h1.json')for m in MODELS};s=read('s4.json')
    original=json.loads((ROOT/'docs/research/novelty-review/source-data/results.json').read_text())['results']
    lines=['# 첫 논문 강건성 점검', '',
           '계산·검토일: 2026-10-20. **기존 자료를 사용한 사후 점검**이며 등록 결과 파일은 그대로 보존했다. 추가 시뮬레이션·사람 판정은 수행하지 않았다.', '',
           '핵심 결과는 유지되지만 일부 표현은 좁혀야 한다. 초기 정답자의 존재와 성과의 관계는 인간과 AI에서 다르고, 규칙 추가 후 집단별 결론의 차이와 초기 평균의 연결은 반복 인물 설정을 반영한 모형에서도 커졌다. Mistral의 집단 내부 분산 감소는 효과가 작고 최적화에 민감하다. 논거 방향에 따른 다수 지지 효과의 차이는 직접 비교에서 뚜렷하지 않았다.', '',
           '## 1. 무엇을 점검했는가', '',
           '| 점검 | 질문 | 방법 | 상태 |','|---|---|---|---|',
           '| H1 | 큰 로그오즈 계수 없이도 인간·AI 차이가 보이는가? | 실제 정답률·원집단 재표집·집단 크기 조정·최적화/무선효과 진단 | 수행 |',
           '| 인물 설정 반복 | 같은 인물이 여러 집단·문항에 나온 점을 반영해도 새 관계가 남는가? | 다중 소속 혼합 모형·인물별 전체 제외 | 핵심 분산·초기 평균 관계에 수행 |',
           '| S4 | 중립 논거를 빼도 결과가 같고, 방향에 따라 효과가 실제로 다른가? | 중립 2세트 제외·15대15 비교·직접 상호작용 검정 | 수행 |','',
           '사람 검증은 별도 진행한다. 이 보고서는 모든 7+7 지표의 의존성을 일괄 해결했다는 기록이 아니라, 우선순위가 높은 세 점검의 결과다.', '',
           '## 2. 초기 정답자의 존재와 최종 정답률', '',
           'k는 토론을 시작할 때 정답을 가진 사람의 수다. k=0과 k=1의 최종 정답률 차이를 계산했다. AI 일반 토론의 세 반복을 원집단과 함께 묶어 재표집했으며, 같은 인간 집단을 독립 표본으로 세 번 늘리지 않았다.', '',
           '| 자료 | k=0 정답률 | k=1 정답률 | k=1−0 차이 [95% 구간], %포인트 |','|---|---:|---:|---:|']
    for model in ['human']+MODELS:
        z=h['claude']['probability_scale']if model=='human'else h[model]['probability_scale']
        col='human'if model=='human'else'ai';gain='human_gain'if model=='human'else'ai_gain'
        lines.append(f"| {model.title()} | {z['cells']['0'][col]:.1%} | {z['cells']['1'][col]:.1%} | {fmt(z['contrasts'][gain],100,2)} |")
    lines += ['', '- **관찰:** 인간은 초기 정답자가 한 명 있는 집단에서 최종 정답률이 크게 높다. AI는 정답자가 없어도 높은 정답률을 보이며, 정답자 한 명의 존재와 연결된 차이는 훨씬 작다.',
              '- **해석:** 이 조건의 AI 성과는 인간처럼 처음 정답을 가진 구성원의 존재에 크게 의존하지 않는다. k 집단의 구성이 다른 관찰 비교이므로, 정답자를 한 명 추가했을 때의 인과효과로 쓰지 않는다.', '',
              '| AI−인간의 정답률 증가 차이 | 원집단 재표집 [95% 구간], %포인트 | 집단 크기 조정 선형확률모형 [95% 구간], %포인트 |','|---|---:|---:|']
    for m in MODELS:
        lines.append(f"| {m.title()} | {fmt(h[m]['probability_scale']['contrasts']['ai_minus_human_gain'],100,2)} | {fmt(h[m]['size_adjusted_linear_probability'],100,2)} |")
    lines += ['', '### 큰 등록 계수의 진단', '',
              '등록 H1은 정답 여부를 로지스틱 혼합 모형으로 분석한 조건부 로그오즈 상호작용이다. 위 표의 %포인트와 단위·추정 대상이 다르다. 등록 계수·P값은 변경하지 않고, 실제 정답률 차이를 보조 근거로 제시한다.', '',
              '| 모델 | 재적합 계수, bobyqa | 표준오차, bobyqa | 표준오차, nloptwrap | 실행 무선효과 SD, bobyqa |','|---|---:|---:|---:|---:|']
    for m in MODELS:
        a=h[m]['diagnostics']['registered_bobyqa'];b=h[m]['diagnostics']['registered_nloptwrap']
        coef=lambda r:next(v for v in r['coefficients']if v['term']=='k1:ai')
        run=next(v['sdcor']for v in a['random_effects']if v['grp']=='run')
        lines.append(f"| {m.title()} | {coef(a)['estimate']:.3f} | {coef(a)['se']:.3f} | {coef(b)['se']:.3f} | {run:.3f} |")
    lines += ['', '모든 k×자료 유형 셀에 정답과 오답이 함께 존재한다. 단순한 셀의 완전분리가 확인된 자료는 아니다. 실행별 응답이 강하게 묶여 있고, Claude·Mistral의 큰 조건부 계수와 Claude의 표준오차는 적합 사양·최적화의 영향을 받는다. 실행 무선효과를 뺀 진단 모형도 별도 보관했다. 크기가 큰 로그오즈 자체를 핵심 효과 크기로 강조하기보다 확률 차이와 집단 재표집 결과로 독자가 실제 차이를 판단하게 한다.', '',
              '## 3. 반복 인물 설정을 반영한 정책 집단 분석', '',
              '495개의 원 응답자 설정이 여러 문항·집단에 재사용되었다. 한 집단의 결과에 다섯 인물 설정의 공통 성향이 함께 들어가도록 **다중 소속 혼합 모형(multiple-membership mixed model)**을 적합했다. 같은 인물이 다른 집단에 등장하면 그 공통 성향을 공유한다. 문항 차이와 집단별 잔여 차이도 포함했다.', '',
              '비교는 같은 구성원·초기 점수의 규칙 토론−일반 토론이다. 집단 내부 분산은 한 토론 안의 다섯 점수 차이, 집단 평균 사이 분산은 같은 정책을 토론한 여러 집단의 평균 차이다. 둘 다 0–10점 정책 척도의 제곱 단위다.', '',
              '| 모델 | 기존 집단 내부 분산 차이 | 반복 설정 모형 | 기존 집단 평균 사이 분산 차이 | 반복 설정 모형 |','|---|---:|---:|---:|---:|']
    for m in MODELS:
        r=people[m];o=original[m]['contrasts']
        lines.append(f"| {m.title()} | {fmt(o['within'])} | {fmt(r['within_delta']['coefficients']['intercept'])} | {fmt(o['between'])} | {fmt(r['between_delta']['coefficients']['intercept'])} |")
    lines += ['', '- **관찰:** 집단별 최종 평균의 차이가 커지는 결과는 세 모델 모두에서 유지됐다. Claude·Gemini의 내부 분산 감소도 유지됐다.',
              '- **Mistral:** 가장 높은 우도의 적합에서는 내부 분산 감소 구간이 0 아래지만, 다른 수렴 적합의 구간은 0을 포함했다. 감소 방향과 작은 크기는 일관되지만, 구간의 0 포함 여부는 최적화에 민감하다.',
              '- **해석:** 한 토론 안의 합의가 여러 토론 집단이 같은 결론을 낸다는 뜻은 아니다. 가장 안정적인 추가 관계는 집단 평균 차이의 증가와 초기 구성 연결의 강화다.', '',
              '### 초기 평균과 최종 평균의 연결', '',
              '다음 계수는 초기 집단 평균이 같은 문항 안에서 1점 높을 때, 규칙 조건의 최종 평균이 일반 토론보다 얼마나 더 높아지는지를 나타낸다. 초기 점수를 주지 않은 별도 응답의 집단 평균(D)도 함께 고려했다.', '',
              '| 모델 | 초기 평균 연결의 추가 계수 [95% 구간] | 유효 집단 수 |','|---|---:|---:|']
    for m in MODELS:
        r=people[m]['initial_mean_association_delta'];lines.append(f"| {m.title()} | {fmt(r['coefficients']['pre_centered'])} | {r['n_groups']} |")
    lines += ['', '- **관찰:** 초기 집단 평균과의 연결은 반복 인물 설정을 반영해도 세 모델에서 강해졌다.',
              '- **해석:** 같은 자료·같은 정당 혼합비 아래에서도 누가 어떤 초기 입장으로 모였는지가 규칙 토론의 최종 평균과 더 강하게 연결된다. 집단 내부 수렴과 집단별 결론 차이를 함께 평가할 근거다.', '',
              'Mistral은 D 응답 한 개가 없는 집단을 초기 평균 연결 모형에서만 제외해 414집단을 사용했다. 분산 모형은 D가 필요 없어 415집단을 유지했다. Claude·Gemini는 각 416집단이다.', '',
              '### 특정 인물 하나가 결과를 좌우하는가?', '',
              '인물 설정을 하나씩 골라 그 설정이 등장한 모든 집단을 제외하고, 원래의 문항별 분산 차이를 다시 계산했다. 이는 영향력 점검이며 신뢰구간 보정과 구분한다.', '',
              '| 모델 | 495번 제외 계산의 내부 분산 차이 범위 | 집단 평균 사이 분산 차이 범위 |','|---|---:|---:|']
    for m in MODELS:
        r=people[m]['leave_persona_out'];lines.append(f"| {m.title()} | {r['within_min_max'][0]:+.3f} ~ {r['within_min_max'][1]:+.3f} | {r['between_min_max'][0]:+.3f} ~ {r['between_min_max'][1]:+.3f} |")
    lines += ['', '모든 인물별 제외 계산에서 감소·증가의 점추정 방향이 유지됐다. 특정 인물 한 명의 반복만으로 생긴 결과는 아니라는 근거다.', '',
              '### 모형의 범위와 최적화 기록', '',
              '반복 설정 모형은 가우스 분포와 인물·문항 효과의 가산성을 가정한 보조 분석이다. 기존 분석은 문항별 같은 가중치의 평균이며, 혼합 모형은 공분산 구조를 사용해 추정하므로 점추정도 조금 다를 수 있다. 제한최대우도(REML)로 적합하고 문항 수−1=29 자유도의 t 구간을 사용했다. 여러 최적화와 공통 시작값 재적합을 비교하고, 수렴·유한 표준오차를 충족한 적합 중 우도가 가장 높은 것을 표에 제시했다.', '',
              '일부 분산 성분이 0 근처에서 추정되어 경계 적합·수치 경고·최적화 실패가 있었다. 이를 삭제하지 않고 JSON에 보존했다. 아래 범위는 수렴 적합들의 구간 양 끝을 모은 **최적화 민감도 범위**이며 하나의 새로운 95% 신뢰구간은 아니다.', '',
              '| 모델 | 내부 분산 차이: 최적화 구간 범위 | 집단 평균 사이 분산 차이: 최적화 구간 범위 |','|---|---:|---:|']
    for m in MODELS:
        r=people[m];v=r['within_delta']['optimizer_interval_envelope']['intercept'];b=r['between_delta']['optimizer_interval_envelope']['intercept'];lines.append(f'| {m.title()} | {v[0]:+.3f} ~ {v[1]:+.3f} | {b[0]:+.3f} ~ {b[1]:+.3f} |')
    lines += ['', '## 4. 중립 논거를 제외한 방향별 다수 지지 효과', '',
              '모델의 별도 기본 입장 D가 50인 argq14의 두 세트(48실행)를 제외했다. 남은 720실행은 기본 입장과 같은 방향 15세트·360실행과 반대 방향 15세트·360실행이다. 이동량은 0–100점 척도에서 대본 상대의 주장 쪽으로 움직인 점수이며, 재응답 조건의 변화를 뺐다.', '',
              '| 비교 | 다수−소수 지지의 추가 이동 [95% 구간], 점 |','|---|---:|']
    for name in ['aligned','opposing']:
        r=s['models'][name]['coefficients']['sup'];lines.append(f"| {'같은 방향'if name=='aligned'else'반대 방향'} | {r['estimate']:+.3f} [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}] |")
    r=s['direct_direction_tests']['sup:aligned']
    lines += [f"| 방향에 따른 지지 효과 차이: 같은−반대 | {r['estimate']:+.3f} [{r['ci_low']:+.3f}, {r['ci_high']:+.3f}] |", '',
              f"직접 상호작용 검정 P={r['p']:.3f}, 네 방향 관련 상호작용을 Holm 보정하면 P={s['direction_tests_holm']['sup:aligned']['p_holm']:.3f}다. 논거 질·토론 규칙에 따른 나머지 방향 상호작용도 뚜렷하지 않았다.", '',
              f"두 찬반 세트와 모든 처치 조건을 묶어 15주제를 재표집한 별도 점검에서도 지지 효과 방향 차이는 {fmt(s['topic_bootstrap']['contrasts']['sup:aligned'])}점이었다. 이는 주제별 반복 의존성을 보존한 10,000회 백분위 구간이며 0을 포함했다.", '',
              '- **관찰:** 점추정상 같은 방향의 다수 지지 효과가 더 크지만, 두 방향의 차이 구간은 0을 포함한다.',
              '- **해석:** 다수 지지와 추가 이동의 연결을 보고하되, 그 효과가 기본 입장과 같은 방향에만 나타난다는 주장으로 쓰지 않는다. 기존 비정렬 17세트 결과는 원본 기록으로 보존하고 현행 그림은 중립을 제외한 결과로 갱신한다.', '',
              '공동 모형은 q×sup×eng×aligned, 초기 찬반 side, 세트별 절편·질 기울기와 주제 절편을 포함했다. 같은 방향과 공동 모형은 경계 적합이므로 보조·탐색 결과로 보고한다.', '',
              '## 5. 원고 반영과 남은 작업', '',
              '| 항목 | 반영 원칙 |','|---|---|',
              '| H1 | 큰 로그오즈만으로 크기를 설명하지 않고 원 정답률·%포인트 차이를 함께 제시 |',
              '| 집단 안·사이 | 평균 사이 차이와 초기 평균 연결을 가장 안정적인 추가 관계로 제시; Mistral 내부 분산의 작은 효과와 민감성 명시 |',
              '| S4 | 중립 제외 결과와 직접 차이를 제시; 특정 방향에서만 효과가 있다고 쓰지 않음 |',
              '| 7+7 | 재현·심화·확장의 종합 구조 유지; 새 관계를 전체 논문의 유일한 결과로 좁히지 않음 |',
              '| 남은 검증 | 준비된 사람 판정, 다른 지표의 반복 의존성 범위 점검, 최종 원고·그림·투고 서류 |','',
              '전체 7+7의 수치·모형을 모두 다시 적합한 것은 아니다. 동일 집단 반복과 규칙 구성요소 분리 실험도 별도 후속 과제다.', '',
              '## 방법 근거·재현 자료', '',
              '다중 소속의 개념은 [다중 소속 모형의 방법론 원문](https://arxiv.org/abs/1907.04148), 구현은 [statsmodels 분산 성분 공식 문서](https://www.statsmodels.org/stable/examples/notebooks/generated/variance_components.html)와 [VCSpec 공식 문서](https://www.statsmodels.org/stable/generated/statsmodels.regression.mixed_linear_model.VCSpec.html)를 확인했다. 혼합 모형의 수치적 점검은 [lme4 공식 수렴 문서](https://lme4.github.io/lme4/reference/convergence.html)를 참조했다. 본 연구에 적용한 모형과 보수적 보고 범위는 위에 명시한 분석자 선택이다.', '',
              '입력 파일 해시·추출 표·모형 계수·경고·최적화 비교는 [source-data](source-data/manifest.json)에 보존했다. 원 등록 분석과 기존 탐색 JSON은 변경하지 않았다.', '',
              '![반복 인물 설정을 고려한 민감도 비교](figures/persona-sensitivity.png)', '',
              '- **그림 읽는 법:** 세로축은 모델, 가로축은 규칙 추가−일반 토론의 차이다. a는 내부 분산, b는 집단 평균 사이 분산, c는 초기 집단 평균과 최종 평균 연결의 추가 계수다. 파란 원은 기존 분석, 주황 삼각형은 반복 인물 설정 모형이다. 회색 얇은 선은 최적화 민감도 범위다.',
              '- **핵심 관찰:** b와 c의 증가가 세 모델에서 유지된다. a의 Mistral은 효과가 작고 최적화 범위가 0에 걸친다. 이 차이를 원고에 함께 반영한다.',
              '- **단위:** a·b는 점수 제곱, c는 초기 평균 1점당 추가 최종 점수다. 기존 문항 재표집과 혼합 모형의 추정 대상·가중 방식이 조금 달라, 두 색의 위치가 완전히 같을 필요는 없다.','']
    (OUT/'README.md').write_text('\n'.join(lines))
    (OUT/'figures').mkdir(exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    fig,axes=plt.subplots(1,3,figsize=(14,5))
    for ax,k,title in zip(axes,['within','between','initial'],['a  Within-discussion variance','b  Between-discussion means','c  Initial-mean association']):
        for i,m in enumerate(MODELS):
            if k=='initial':
                old=original[m]['composition']['rule_minus_baseline']['initial_mean'];new=people[m]['initial_mean_association_delta'];term='pre_centered'
            else:
                old=original[m]['contrasts'][k];new=people[m][k+'_delta'];term='intercept'
            env=new['optimizer_interval_envelope'][term]
            ax.plot(env,[i+.12,i+.12],color='#b4b4b4',linewidth=4,zorder=1)
            for r,offset,color,marker,label in [(old,-.12,'#2776bd','o','Item bootstrap'),(new['coefficients'][term],.12,'#d85a24','^','Repeated-persona model')]:
                e=r['estimate'];lo,hi=r['ci'];ax.errorbar(e,i+offset,xerr=[[e-lo],[hi-e]],fmt=marker,color=color,capsize=3,label=label if i==0 else None,zorder=2)
        ax.axvline(0,color='#666',linestyle='--');ax.set(yticks=range(3),yticklabels=[m.title()for m in MODELS],ylim=(2.5,-.6),title=title,xlabel='Rules minus baseline\n'+('coefficient'if k=='initial'else'squared score points'))
    axes[0].legend(frameon=False,fontsize=8,loc='lower left')
    fig.suptitle('Targeted sensitivity: shared persona settings across groups and items',fontsize=14)
    fig.text(.5,.02,'Colored whiskers: 95% intervals. Gray: optimizer interval envelope (not a confidence interval).',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.06,1,.93))
    for ext in ['png','pdf']:fig.savefig(OUT/f'figures/persona-sensitivity.{ext}',dpi=220)
    plt.close(fig)
    display={'status':'Post-hoc, neutral sets excluded; derived from s4.json','raw_source':'docs/research/robustness/source-data/s4.json','by_split':{},'joint':{}}
    for name in ['aligned','opposing']:
        r=s['models'][name];display['by_split'][name]={'model_delta_c':{k:{'estimate':v['estimate'],'ci':[v['ci_low'],v['ci_high']],'p':v['p'],'n':r['n'],'singular':r['singular']}for k,v in r['coefficients'].items()}}
    for k,v in s['direct_direction_tests'].items():display['joint'][k]={'estimate':v['estimate'],'ci':[v['ci_low'],v['ci_high']],'p':v['p'],'p_holm':s['direction_tests_holm'][k]['p_holm']}
    (SRC/'s4-display.json').write_text(json.dumps(display,ensure_ascii=False,indent=2)+'\n')
    print('Report, figure, and corrected display records written.')


if __name__=='__main__':main()
