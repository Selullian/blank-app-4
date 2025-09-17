import streamlit as st
import pandas as pd
import requests
import plotly.express as px
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
    # 정렬
    df = df.sort_values(["country", "year"]).reset_index(drop=True)
    return df

def load_data_with_fallback(start_year=1990):
    try:
        df = fetch_worldbank_pm25(start_year=start_year)
        # 캐시 파일 저장
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

    st.sidebar.header("설정")
    year_select = st.sidebar.slider("지도로 볼 연도 선택", min_value=min_year, max_value=max_year, value=max_year, step=1)
    cap_outliers = st.sidebar.checkbox("상위 1%로 캡핑하기", value=True)
    top_n = st.sidebar.slider("표에 표시할 상위(나쁨) 국가 수", min_value=5, max_value=30, value=10)

    # 지도 데이터 준비
    df_year = df[df['year'] == year_select].copy()
    df_grouped = df_year.groupby(['iso3', 'country'], as_index=False)['pm25'].mean()
    df_grouped.rename(columns={"pm25": "value"}, inplace=True)

    # 캡핑
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

    # 상위 n개국 표
    st.subheader(f"{year_select}년 — 연평균 미세먼지 매우 나쁜 상위 {top_n}개국")
    worst = df_grouped.sort_values("value", ascending=False).head(top_n)[["country", "value"]]
    worst['value'] = worst['value'].round(2).astype(str) + " µg/m³"
    st.dataframe(worst.reset_index(drop=True))

    # 추세 그래프
    st.subheader("📈 나라별 연도별 추세 그래프")

    # 레이아웃: 왼쪽(그래프) / 오른쪽(선택창)
    col1, col2 = st.columns([3, 1])  # 비율 3:1

    with col2:  # 오른쪽 선택 영역
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

    with col1:  # 왼쪽 그래프 영역
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

    # 출처 명시
    st.markdown("---")
    st.markdown(
        """
        **데이터 출처 & API**  
        - World Bank: *EN.ATM.PM25.MC.M3* (“Population-weighted mean annual PM2.5 exposure”) 지표 — REST API 사용  
        - World Bank 데이터 탐색: [PM2.5 air pollution, mean annual exposure (World Bank)](https://data.worldbank.org/indicator/EN.ATM.PM25.MC.M3)  
        """
    )

if __name__ == "__main__":
    main()
