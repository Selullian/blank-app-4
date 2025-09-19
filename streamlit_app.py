import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# -----------------------------
# 설정 (World Bank API)
# -----------------------------

WB_URL = "https://api.worldbank.org/v2/country/all/indicator/EN.ATM.PM25.MC.M3"
CACHE_FILE = "pm25_worldbank_cache.csv"

@st.cache_data(show_spinner=False)
def fetch_worldbank_pm25(start_year: int = 1990, end_year: int | None = None):
    if end_year is None:
        end_year = datetime.now().year
    params = {
        "date": f"{start_year}:{end_year}",
        "format": "json",
        "per_page": 20000
    }
    resp = requests.get(WB_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if (not data) or len(data) < 2:
        raise ValueError("World Bank API 응답이 예상치 않거나 비었어요.")

    rows = []
    for rec in data[1]:
        iso3 = rec.get("countryiso3code")
        value = rec.get("value")
        country = rec["country"]["value"]
        year = rec.get("date")
        if not iso3 or value is None or country is None or year is None:
            continue
        try:
            year_int = int(year)
        except:
            continue
        rows.append({
            "iso3": iso3,
            "country": country,
            "year": year_int,
            "pm25": float(value)
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["country", "year"]).reset_index(drop=True)
    return df

def load_data_with_fallback(start_year=1990):
    try:
        df = fetch_worldbank_pm25(start_year=start_year)
        try:
            df.to_csv(CACHE_FILE, index=False)
        except Exception:
            pass
    except Exception as e:
        if os.path.exists(CACHE_FILE):
            df = pd.read_csv(CACHE_FILE)
            st.warning(f"World Bank API 호출 실패 → 로컬 캐시 사용됨. 오류: {e}")
        else:
            st.error(f"데이터를 불러올 수 없습니다. 오류: {e}")
            st.stop()
    return df

# -----------------------------
# 앱 본문
# -----------------------------
def main():
    st.set_page_config(page_title="국가별 PM2.5 지도/추세", layout="wide")
    st.title("🌍 국가별 PM2.5 (미세먼지) 지도 및 추세 시각화")
    st.markdown(
        "이 앱은 **World Bank**의 'population-weighted mean annual PM2.5' 데이터를 사용합니다. \n"
        "즉, 연평균 미세먼지 수치만 제공합니다."
        "\n 자세한 출처는 웹사이트를 맨 아래로 내려 확인해주세요."
    )

    df = load_data_with_fallback(start_year=1990)
    min_year = int(df['year'].min())
    max_year = int(df['year'].max())

    # -----------------------------
    # 사이드바 (설정)
    # -----------------------------
    st.sidebar.title("⚙️ 설정 메뉴")

    st.sidebar.markdown("""🗓️ **연도 선택** 
    보고 싶은 연도를 선택하세요.""")
    year_select = st.sidebar.slider(
        "지도로 볼 연도 선택",
        min_value=min_year,
        max_value=max_year,
        value=max_year,
        step=1
    )

    cap_outliers = st.sidebar.checkbox("색깔을 상대적으로 나타내기", value=True)

    st.sidebar.markdown("""📊 **상위 국가 수**  
    미세먼지 수치가 높은 상위 몇 개 나라를 표로 볼지 정하세요.""")
    top_n = st.sidebar.slider(
        "표에 표시할 상위(나쁨) 국가 수",
        min_value=5, max_value=30, value=10
    )

    # 지도 데이터 준비
    df_year = df[df['year'] == year_select].copy()
    df_grouped = df_year.groupby(['iso3', 'country'], as_index=False)['pm25'].mean()
    df_grouped.rename(columns={"pm25": "value"}, inplace=True)

    if cap_outliers:
        vmax = float(df_grouped['value'].quantile(0.99))
    else:
        vmax = float(df_grouped['value'].max())

    fig_map = px.choropleth(
        df_grouped,
        locations="iso3",
        color="value",
        hover_name="country",
        hover_data={"value": ":.2f"},
        color_continuous_scale="RdYlBu_r",
        range_color=(0, vmax),
        labels={"value": "PM2.5 (연평균) µg/m³"},
        title=f"{year_select}년 — 국가별 PM2.5 (연평균)"
    )
    fig_map.update_geos(showframe=False, showcoastlines=False)
    st.plotly_chart(fig_map, use_container_width=True)

    st.write("")
    st.write("")

    # -----------------------------
    # 상위 n개국 피라미드형 막대 그래프
    # -----------------------------
    worst = df_grouped.sort_values("value", ascending=False).head(top_n)
    fig_bar = go.Figure(go.Bar(
        x=worst['value'][::-1],
        y=worst['country'][::-1],
        orientation='h',
        marker=dict(
            color=worst['value'][::-1],
            colorscale='OrRd',
            showscale=True,
            colorbar=dict(title="PM2.5 µg/m³")
        ),
        text=worst['value'][::-1].round(2).astype(str) + " µg/m³",
        textposition='outside'
    ))
    fig_bar.update_layout(
        xaxis_title="PM2.5 (연평균, µg/m³)",
        yaxis_title="국가",
        margin=dict(l=100, r=20, t=40, b=40),
        height=400
    )
    st.subheader(f"{year_select}년 — 연평균 미세먼지 매우 나쁜 상위 {top_n}개국")
    st.plotly_chart(fig_bar, use_container_width=True)

    st.write("")
    st.write("")

    # 추세 그래프
    st.subheader("📈 나라별 연도별 추세 그래프")
    col1, col2 = st.columns([3, 1])

    with col2:
        default_countries = [c for c in ["China", "India", "Korea, Rep."] if c in df['country'].unique()]
        countries = st.multiselect(
            "국가 선택",
            sorted(df['country'].unique()),
            default=default_countries
        )
        range_start, range_end = st.slider(
            "연도 범위",
            min_value=min_year,
            max_value=max_year,
            value=(max_year - 10, max_year),
            step=1
        )

    with col1:
        if countries:
            df_ts = df[(df['country'].isin(countries)) & (df['year'].between(range_start, range_end))].copy()
            fig_ts = px.line(
                df_ts,
                x='year', y='pm25',
                color='country',
                markers=True,
                labels={"pm25": "PM2.5 (연평균) µg/m³", "year": "연도"},
                title=f"{range_start}–{range_end}년 간 국가별 PM2.5 (연평균) 추세"
            )
            try:
                fig_ts.add_hline(y=5, line_dash="dash",
                                 annotation_text="WHO guideline: 5 µg/m³",
                                 annotation_position="bottom right")
            except Exception:
                pass
            st.plotly_chart(fig_ts, use_container_width=True)

            # -----------------------------
            # 선택 국가 연도별 수치 표 (가로 스크롤)
            # -----------------------------
            pivot_df = df_ts.pivot(index='country', columns='year', values='pm25').round(2)
            st.subheader("📋 선택 국가 연도별 PM2.5 수치")
            st.dataframe(pivot_df, use_container_width=True)

    # 보고서와 출처는 기존 코드 그대로
    st.write("")
    st.write("")

    st.subheader("📄 미림마이스터고 1학년 4반 학생을 위한 미세먼지 위험 알림과 실천 방법 연구")
    st.markdown(
        """
**서론: 우리가 이 보고서를 쓰게 된 이유**  
최근 몇 년 동안 날씨 예보에서 가장 자주 등장하는 단어 중 하나가 ‘미세먼지’이다.  
등굣길 아침마다 마스크를 쓰고, 체육 수업이 실내로 바뀌는 일이 흔해졌다. 하지만 단순히 불편함을 넘어서, 미세먼지가 우리 건강과 생활에 어떤 영향을 주는지, 그리고 청소년인 우리가 스스로 어떻게 대응해야 하는지는 제대로 이야기되지 않는다.  
그래서 우리는 미세먼지 문제를 데이터와 실제 사례를 통해 확인하고, 학생으로서 실천할 수 있는 방법을 제시하기 위해 이 보고서를 작성하게 되었다.  

---  

**본론 1: 데이터로 보는 미세먼지의 영향**  
(P)oint: 지난 10년간 미세먼지는 우리 삶에 점점 더 큰 위협이 되고 있다.  
(R)eason: 미세먼지 농도는 꾸준히 상승하고 있으며, 계절과 지역에 따라 심각한 수준을 기록해 청소년 건강에도 직접적인 영향을 미치고 있다.  
(E)xample: 환경부 자료에 따르면, 수도권의 연평균 초미세먼지(PM2.5) 농도는 2013년 23㎍/㎥에서 2022년 29㎍/㎥로 증가했다. 또한 질병관리청 조사 결과, 미세먼지 농도가 높았던 시기에는 청소년 천식·기관지염 진료 건수가 최대 1.4배 늘어난 것으로 확인되었다.  
(P)oint: 이처럼 미세먼지 증가는 단순한 환경 문제가 아니라, 청소년의 건강과 학교 생활을 직접적으로 위협하는 요인임이 분명하다.  

---  

**본론 2: 미세먼지가 학생 건강과 활동에 미치는 실제 영향**  
(P)oint: 미세먼지는 청소년의 건강을 해치고 학교 생활의 기본적인 활동까지 제한한다.  
(R)eason: 호흡기와 면역 체계가 아직 완전히 발달하지 않은 청소년은 미세먼지에 더욱 취약하며, 이는 곧 학습권과 생활권의 제약으로 이어진다.  
(E)xample: 실제로 미세먼지 ‘나쁨’ 단계가 지속되면 학교 체육 수업이 실내 이론으로 대체되거나 취소되고, 운동장·야외 놀이 시설 이용이 제한된다. 또한 보건복지부 통계에 따르면, 미세먼지 고농도 주간에 청소년의 호흡기 질환 진료율은 평소 대비 18% 이상 높아졌다. 학생 개인 차원에서는 기침, 두통, 피부 가려움, 피로감 등 다양한 증상이 보고되었다.  
(P)oint: 따라서 미세먼지는 단순히 ‘마스크 착용으로 해결되는 문제’가 아니라, 학생들의 건강권과 생활권을 동시에 위협하는 심각한 사회적 문제로 인식해야 한다.  

---  

**결론: 청소년 건강과 안전한 활동을 위한 학생 주도 제언**  
(P)oint: 미세먼지는 청소년의 건강과 일상 활동에 실질적 피해를 주기 때문에, 학생 스스로 대응하고 행동해야 한다.  
(R)eason: 정부와 학교 차원의 대책도 중요하지만, 일상에서 학생이 스스로 실천할 수 있는 작은 행동이 모여 더 큰 변화를 만든다.  
(E)xample: 첫째, 마스크 착용과 등하교 전 공기질 확인은 기본적인 자기 보호 수단이다. 둘째, ‘미세먼지 경보 알림제’를 학급 단위로 운영하여 실외 활동 여부를 학생 스스로 판단할 수 있도록 한다. 셋째, 교실 내 공기정화기·식물 키우기 같은 작은 실천도 효과가 있으며, 장기적으로는 ‘학생 미세먼지 감시단’을 만들어 교내 대기질 변화를 기록하고 교육청에 건의할 수도 있다.  
(P)oint: 결국 청소년은 단순한 피해자가 아니라, 스스로 건강을 지키고 사회적 변화를 만들어낼 수 있는 주체다. 따라서 우리는 미세먼지를 정확히 이해하고, 생활 속에서 실천하며, 목소리를 내는 행동을 통해 안전한 학교 환경을 만들어가야 한다.  

---  

**참고 자료**  
- 환경부 대기환경연보 (2013~2022)  
- 질병관리청 청소년 건강행태조사 (2019~2022)  
- 보건복지부 보건의료 빅데이터 개방시스템  
    """
    )

    # 출처
    st.markdown("---")
    st.markdown(
        """
        **데이터 출처 & API**  
        - World Bank: *EN.ATM.PM25.MC.M3* 지표 — REST API 사용  
        - World Bank 데이터 탐색: [PM2.5 air pollution, mean annual exposure (World Bank)](https://data.worldbank.org/indicator/EN.ATM.PM25.MC.M3)  
        """
    )

if __name__ == "__main__":
    main()
