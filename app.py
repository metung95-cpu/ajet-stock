import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json # 새로 추가됨!

st.set_page_config(page_title="검역량 & 오퍼가 대시보드", layout="wide")

def check_password():
    password = st.sidebar.text_input("🔒 비밀번호 입력", type="password")
    if password == "0348":
        return True
    elif password != "":
        st.sidebar.error("비밀번호가 틀렸습니다.")
    return False

if not check_password():
    st.info("왼쪽 사이드바에 비밀번호를 입력해야 데이터를 볼 수 있습니다.")
    st.stop()

# --- 구글 인증 통합 함수 (인터넷/로컬 모두 알아서 작동) ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. 인터넷(스트림릿 클라우드) 비밀 금고에 열쇠가 있는 경우
    if "google_key" in st.secrets:
        creds_dict = json.loads(st.secrets["google_key"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    # 2. 내 컴퓨터(로컬)에 key.json 파일이 있는 경우
    else:
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
        
    return gspread.authorize(credentials)


# --- 1. 과거 데이터(Qrt) 불러오기 ---
@st.cache_data(ttl=7200)
def load_data():
    gc = get_gspread_client()
    doc = gc.open('전략데이터 원본데이터') 
    worksheet = doc.worksheet('Qrt')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip()
    df = df.loc[:, df.columns != '']
    df['검역량'] = pd.to_numeric(df['검역량'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    df['연월'] = df['연'].astype(str) + "-" + df['월'].astype(str).str.zfill(2)
    return df

# --- 2. 실시간 데이터(RAW) 불러오기 ---
@st.cache_data(ttl=3600)
def load_raw_data():
    gc = get_gspread_client()
    doc = gc.open_by_url('https://docs.google.com/spreadsheets/d/1lSMxR62Qes09fKqmWUya2jFuEG0U4ScqsfjKlFJudnk/edit?gid=1705869223#gid=1705869223') 
    worksheet = doc.worksheet('RAW')
    data = worksheet.get_all_values()
    df_raw = pd.DataFrame(data[1:], columns=data[0])
    df_raw.columns = df_raw.columns.str.strip()
    df_raw.rename(columns={'품명': '품목', '구분': '세부구분', '국가명': '국가별'}, inplace=True)
    if '당월누계(kg)' in df_raw.columns:
        df_raw['당월누계(kg)'] = pd.to_numeric(df_raw['당월누계(kg)'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
        df_raw['당월누계(Ton)'] = df_raw['당월누계(kg)'] / 1000.0
    return df_raw

# --- 3. 오퍼가 데이터 불러오기 ---
@st.cache_data(ttl=3600)
def load_offer_data():
    gc = get_gspread_client()
    doc = gc.open_by_url('https://docs.google.com/spreadsheets/d/1Ke8Q5BHqeeZUZ90Pe7WSWIlppndtebqsq0yoApek1go/edit?gid=1724697100#gid=1724697100') 
    worksheet = next((ws for ws in doc.worksheets() if ws.id == 1724697100), doc.sheet1)
    data = worksheet.get_all_values()
    df_offer = pd.DataFrame(data[1:], columns=data[0])
    df_offer.columns = df_offer.columns.str.strip()
    df_offer = df_offer.loc[:, df_offer.columns != '']
    if '보정오퍼가' in df_offer.columns:
        df_offer['보정오퍼가'] = pd.to_numeric(df_offer['보정오퍼가'].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    return df_offer

# 데이터 로딩
df = load_data()
df_raw = load_raw_data()
df_offer = load_offer_data()


# ==========================================
# 좌측 사이드바: 바로가기 네비게이션
# ==========================================
st.sidebar.markdown("### 🚀 빠른 이동")
st.sidebar.markdown('<a href="#quarantine" style="text-decoration:none; font-size:18px;">🥩 검역량 대시보드</a>', unsafe_allow_html=True)
st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.markdown('<a href="#offer" style="text-decoration:none; font-size:18px;">💵 오퍼가 분석</a>', unsafe_allow_html=True)


# ==========================================
# 메인 화면 1: 검역량 대시보드
# ==========================================
st.markdown('<div id="quarantine"></div>', unsafe_allow_html=True) 
st.title("🥩 검역량 통합 대시보드")

tab1, tab2, tab3 = st.tabs(["📊 조건별 통합 조회", "📈 월별 검역량 비교", "⚡ 실시간 검역 비교"])

with tab1:
    st.subheader("조건별 검역량 요약표")
    sorted_years = sorted(df['연'].unique(), key=lambda x: int(x) if str(x).isdigit() else str(x))
    sorted_months = sorted(df['월'].unique(), key=lambda x: int(x) if str(x).isdigit() else str(x))

    col1, col2, col3 = st.columns(3)
    with col1: selected_year = st.selectbox("연도 선택", ['전체'] + sorted_years, key="tab1_year")
    with col2: selected_month = st.selectbox("월 선택", ['전체'] + sorted_months, key="tab1_month")
    with col3: selected_category = st.selectbox("세부구분 선택", ['전체'] + sorted(df['세부구분'].unique()), key="tab1_cat")

    col4, col5, col6 = st.columns(3)
    with col4: selected_item = st.selectbox("품목 선택", ['전체'] + sorted(df['품목'].unique()), key="tab1_item")
    with col5: selected_part = st.selectbox("부위 선택", ['전체'] + sorted(df['부위'].unique()), key="tab1_part")
    with col6: selected_country = st.selectbox("국가별 선택", ['전체'] + sorted(df['국가별'].unique()), key="tab1_country")

    filtered_df = df.copy()
    if selected_year != '전체': filtered_df = filtered_df[filtered_df['연'] == selected_year]
    if selected_month != '전체': filtered_df = filtered_df[filtered_df['월'] == selected_month]
    if selected_category != '전체': filtered_df = filtered_df[filtered_df['세부구분'] == selected_category]
    if selected_item != '전체': filtered_df = filtered_df[filtered_df['품목'] == selected_item]
    if selected_part != '전체': filtered_df = filtered_df[filtered_df['부위'] == selected_part]
    if selected_country != '전체': filtered_df = filtered_df[filtered_df['국가별'] == selected_country]

    if not filtered_df.empty:
        pivot_df = pd.pivot_table(filtered_df, values='검역량', index=['연', '월', '세부구분', '품목', '부위', '국가별'], aggfunc='sum').reset_index()
        pivot_df['검역량'] = pivot_df['검역량'].apply(lambda x: f"{x:,.2f}")
        st.dataframe(pivot_df, use_container_width=True, hide_index=True)
    else:
        st.warning("선택한 조건에 맞는 데이터가 없습니다.")

with tab2:
    st.subheader("기준월 vs 비교월 검역량 차이 분석")
    col_t2_1, col_t2_2 = st.columns(2)
    with col_t2_1: selected_cat_t2 = st.selectbox("세부구분 선택", ['전체'] + sorted(df['세부구분'].unique()), key="t2_cat")
    with col_t2_2: selected_item_t2 = st.selectbox("품목 선택", ['전체'] + sorted(df['품목'].unique()), key="t2_item")
        
    col_t2_3, col_t2_4 = st.columns(2)
    with col_t2_3: selected_part_t2 = st.selectbox("부위 선택", ['전체'] + sorted(df['부위'].unique()), key="t2_part")
    with col_t2_4: selected_country_t2 = st.selectbox("국가별 선택", ['전체'] + sorted(df['국가별'].unique()), key="t2_country")

    f_df_t2 = df.copy()
    if selected_cat_t2 != '전체': f_df_t2 = f_df_t2[f_df_t2['세부구분'] == selected_cat_t2]
    if selected_item_t2 != '전체': f_df_t2 = f_df_t2[f_df_t2['품목'] == selected_item_t2]
    if selected_part_t2 != '전체': f_df_t2 = f_df_t2[f_df_t2['부위'] == selected_part_t2]
    if selected_country_t2 != '전체': f_df_t2 = f_df_t2[f_df_t2['국가별'] == selected_country_t2]

    sorted_ym = sorted(df['연월'].unique())
    col3, col4 = st.columns(2)
    with col3: base_month = st.selectbox("기준월 (A) 선택", sorted_ym, index=0, key="t2_base")
    with col4: target_month = st.selectbox("비교월 (B) 선택", sorted_ym, index=len(sorted_ym)-1, key="t2_target")

    if not f_df_t2.empty:
        comp_pivot = pd.pivot_table(f_df_t2, values='검역량', index=['세부구분', '품목', '부위', '국가별'], columns='연월', aggfunc='sum', fill_value=0)
        start_m, end_m = (base_month, target_month) if base_month <= target_month else (target_month, base_month)
        months_in_range = [m for m in sorted_ym if start_m <= m <= end_m]
        valid_months = [m for m in months_in_range if m in comp_pivot.columns]
        
        comp_pivot['평균'] = comp_pivot[valid_months].mean(axis=1) if valid_months else 0
        val_B = comp_pivot[target_month] if target_month in comp_pivot.columns else 0
        val_A = comp_pivot[base_month] if base_month in comp_pivot.columns else 0
        comp_pivot['차이 (B - A)'] = val_B - val_A
        
        display_cols = valid_months + ['평균', '차이 (B - A)']
        comp_pivot = comp_pivot[display_cols].reset_index()
        
        for col in comp_pivot.select_dtypes(include=['float64', 'int64']).columns:
            comp_pivot[col] = comp_pivot[col].apply(lambda x: f"{x:,.2f}")
        st.dataframe(comp_pivot, use_container_width=True, hide_index=True)
    else:
        st.warning("데이터가 없습니다.")

with tab3:
    st.subheader("⚡ 실시간 당월(Ton) vs 과거 특정월 비교")
    sorted_ym_desc = sorted(df['연월'].unique(), reverse=True)
    comp_hist_month = st.selectbox("비교할 과거 월 선택", sorted_ym_desc, index=0, key="t3_comp_month")
    
    col_t3_1, col_t3_2 = st.columns(2)
    with col_t3_1: sel_cat_t3 = st.selectbox("세부구분 선택", ['전체'] + sorted([x for x in df_raw['세부구분'].unique() if x]), key="t3_cat")
    with col_t3_2: sel_item_t3 = st.selectbox("품목 선택", ['전체'] + sorted([x for x in df_raw['품목'].unique() if x]), key="t3_item")
        
    col_t3_3, col_t3_4 = st.columns(2)
    with col_t3_3: sel_part_t3 = st.selectbox("부위 선택", ['전체'] + sorted([x for x in df_raw.get('부위', pd.Series()).unique() if x]), key="t3_part") if '부위' in df_raw.columns else st.empty()
    with col_t3_4: sel_country_t3 = st.selectbox("국가별 선택", ['전체'] + sorted([x for x in df_raw['국가별'].unique() if x]), key="t3_country")

    f_raw, f_hist = df_raw.copy(), df[df['연월'] == comp_hist_month].copy()

    if sel_cat_t3 != '전체': f_raw, f_hist = f_raw[f_raw['세부구분'] == sel_cat_t3], f_hist[f_hist['세부구분'] == sel_cat_t3]
    if sel_item_t3 != '전체': f_raw, f_hist = f_raw[f_raw['품목'] == sel_item_t3], f_hist[f_hist['품목'] == sel_item_t3]
    if '부위' in df_raw.columns and sel_part_t3 != '전체': f_raw, f_hist = f_raw[f_raw['부위'] == sel_part_t3], f_hist[f_hist['부위'] == sel_part_t3]
    if sel_country_t3 != '전체': f_raw, f_hist = f_raw[f_raw['국가별'] == sel_country_t3], f_hist[f_hist['국가별'] == sel_country_t3]

    if not f_raw.empty:
        merge_on = ['세부구분', '품목', '부위', '국가별'] if '부위' in f_raw.columns else ['세부구분', '품목', '국가별']
        raw_grp = f_raw.groupby(merge_on)['당월누계(Ton)'].sum().reset_index().rename(columns={'당월누계(Ton)': '실시간 당월 (Ton)'})
        hist_grp = f_hist.groupby(merge_on)['검역량'].sum().reset_index().rename(columns={'검역량': f'과거 {comp_hist_month} (Ton)'})
        
        merged_df = pd.merge(raw_grp, hist_grp, on=merge_on, how='outer').fillna(0)
        merged_df['차이 (실시간 - 과거)'] = merged_df['실시간 당월 (Ton)'] - merged_df[f'과거 {comp_hist_month} (Ton)']
        
        for col in ['실시간 당월 (Ton)', f'과거 {comp_hist_month} (Ton)', '차이 (실시간 - 과거)']:
            merged_df[col] = merged_df[col].apply(lambda x: f"{x:,.2f}")
        st.dataframe(merged_df, use_container_width=True, hide_index=True)
    else:
        st.warning("실시간 검역 데이터가 존재하지 않습니다.")

# =====================================================================
# 메인 화면 2: 오퍼가 분석
# =====================================================================
st.markdown("<br><br><br>", unsafe_allow_html=True) 
st.markdown("---") 
st.markdown('<div id="offer"></div>', unsafe_allow_html=True) 
st.title("💵 오퍼가")

if not df_offer.empty and '보정오퍼가' in df_offer.columns:
    col_o1, col_o2, col_o3 = st.columns(3)
    with col_o1: off_year = st.selectbox("연 선택", ['전체'] + sorted(df_offer['연'].unique())) if '연' in df_offer.columns else '전체'
    with col_o2: off_month = st.selectbox("월 선택", ['전체'] + sorted(df_offer['월'].unique())) if '월' in df_offer.columns else '전체'
    with col_o3: off_cat = st.selectbox("대분류 선택", ['전체'] + sorted(df_offer['대분류'].unique())) if '대분류' in df_offer.columns else '전체'
        
    col_o4, col_o5, col_o6 = st.columns(3)
    with col_o4: off_origin = st.selectbox("원산지 선택", ['전체'] + sorted(df_offer['원산지'].unique())) if '원산지' in df_offer.columns else '전체'
    with col_o5: off_item = st.selectbox("품목명 선택", ['전체'] + sorted(df_offer['품목명'].unique())) if '품목명' in df_offer.columns else '전체'
    with col_o6: off_grade = st.selectbox("등급 선택", ['전체'] + sorted(df_offer['등급'].unique())) if '등급' in df_offer.columns else '전체'

    filtered_offer = df_offer.copy()
    if off_year != '전체' and '연' in filtered_offer.columns: filtered_offer = filtered_offer[filtered_offer['연'] == off_year]
    if off_month != '전체' and '월' in filtered_offer.columns: filtered_offer = filtered_offer[filtered_offer['월'] == off_month]
    if off_cat != '전체' and '대분류' in filtered_offer.columns: filtered_offer = filtered_offer[filtered_offer['대분류'] == off_cat]
    if off_origin != '전체' and '원산지' in filtered_offer.columns: filtered_offer = filtered_offer[filtered_offer['원산지'] == off_origin]
    if off_item != '전체' and '품목명' in filtered_offer.columns: filtered_offer = filtered_offer[filtered_offer['품목명'] == off_item]
    if off_grade != '전체' and '등급' in filtered_offer.columns: filtered_offer = filtered_offer[filtered_offer['등급'] == off_grade]

    target_cols = ['대분류', '연', '월', '원산지', '품목명', '브랜드', 'EST', '등급']
    idx_cols = [c for c in target_cols if c in filtered_offer.columns]
    
    if idx_cols and not filtered_offer.empty:
        offer_pivot = pd.pivot_table(
            filtered_offer, 
            values='보정오퍼가', 
            index=idx_cols, 
            aggfunc='mean' 
        ).reset_index()

        offer_pivot['보정오퍼가'] = offer_pivot['보정오퍼가'].apply(lambda x: f"{x:,.2f}")
        st.dataframe(offer_pivot, use_container_width=True, hide_index=True)
    else:
        st.warning("선택한 조건에 맞는 데이터가 없습니다.")
else:
    st.warning("오퍼가 데이터를 불러오지 못했거나 '보정오퍼가' 컬럼이 존재하지 않습니다.")
