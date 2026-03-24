import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# --- 1. 구글 인증 ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    return gspread.authorize(credentials)

# --- 2. 데이터 로딩 (본점 완전 제거 및 정렬) ---
@st.cache_data(ttl=60) 
def load_inventory():
    try:
        gc = get_gspread_client()
        doc = gc.open('에이젯광주 운영독스')
        worksheet = doc.worksheet('raw_운영부재고')
        data = worksheet.get_all_values()
        
        if len(data) <= 1:
            return pd.DataFrame()

        # 데이터프레임 생성 및 제목 공백 제거
        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip()
        
        # 열 위치 기반 매핑 (A:품목, B:브랜드, D:수량, E:창고, F:소비기한)
        df['temp_품목'] = df.iloc[:, 0].str.strip()
        df['temp_브랜드'] = df.iloc[:, 1].str.strip()
        df['temp_재고량'] = df.iloc[:, 3].str.strip()
        df['temp_창고'] = df.iloc[:, 4].str.strip()
        df['temp_소비기한'] = df.iloc[:, 5].str.strip()
        
        # [핵심] 모든 기능에서 '본점' 재고를 완전히 제거
        df = df[df['temp_창고'] != '본점']
        
        # [날짜 축소] 2026.11.20 -> 26.11.20
        def format_date(d):
            d = str(d).replace('-', '.').replace('/', '.')
            parts = d.split('.')
            if len(parts) == 3 and len(parts[0]) == 4:
                return f"{parts[0][2:]}.{parts[1]}.{parts[2]}"
            return d
        
        df['temp_소비기한_short'] = df['temp_소비기한'].apply(format_date)
        df['date_sort'] = pd.to_datetime(df['temp_소비기한'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
        
        return df
    except Exception as e:
        st.error(f"시트 데이터를 읽어오지 못했습니다: {e}")
        return pd.DataFrame()

# --- 3. 출고 저장 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 로그인 세션 ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if not st.session_state.logged_in:
    st.title("🔐 에이젯 재고관리 로그인")
    u_id = st.text_input("아이디")
    u_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인"):
        if (u_id == "AZ" and u_pw == "5835") or (u_id == "AZS" and u_pw == "0983"):
            st.session_state.logged_in = True
            st.session_state.user_role = u_id
            st.rerun()
    st.stop()

# 데이터 원본 확보 (여기서 본점은 이미 다 빠짐)
df = load_inventory()

# --- 4. 실시간 재고 현황 표 (중복 필터링) ---
st.title("📦 에이젯 실시간 재고 현황")

if df.empty:
    st.warning("현재 표시할 재고 데이터가 없습니다. 시트 상태를 확인해 주세요.")
else:
    col_t1, col_t2 = st.columns(2)
    with col_t1: f_name = st.text_input("🔍 품명 검색", "")
    with col_t2: f_brand = st.text_input("🔍 브랜드 검색", "")

    # 중복 필터링 (품명 AND 브랜드)
    view_df = df.copy()
    if f_name: view_df = view_df[view_df['temp_품목'].str.contains(f_name, na=False, case=False)]
    if f_brand: view_df = view_df[view_df['temp_브랜드'].str.contains(f_brand, na=False, case=False)]

    # 브랜드 묶음 & 소비기한 순 정렬
    view_df = view_df.sort_values(by=['temp_브랜드', 'date_sort'])

    # 표 표시용 정리
    display_df = view_df[['temp_소비기한_short', 'temp_품목', 'temp_브랜드', 'temp_재고량', 'temp_창고']]
    display_df.columns = ['소비기한', '품목', '브랜드', '재고', '창고']

    st.dataframe(display_df, use_container_width=True, hide_index=True)

# --- 5. 출고 등록 (본점 차단 및 포맷 적용) ---
if st.session_state.user_role == "AZS" and not df.empty:
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    item_query = st.text_input("출고할 품목 검색", placeholder="예: 삼겹")
    
    selected_row = None
    if item_query:
        # 본점이 제거된 df에서 필터링
        selection = df[df['temp_품목'].str.contains(item_query, na=False, case=False)]
        selection = selection.sort_values(by=['temp_브랜드', 'date_sort'])
        
        if not selection.empty:
            # [요청 포맷] 26.11.20 / 삼겹양지 / 브랜드 / 수량 / 창고
            selection['display_label'] = selection.apply(
                lambda x: f"{x['temp_소비기한_short']} / {x['temp_품목']} / {x['temp_브랜드']} / {x['temp_재고량']} / {x['temp_창고']}", axis=1
            )
            target_label = st.selectbox("재고 선택", selection['display_label'].tolist())
            selected_row = selection[selection['display_label'] == target_label].iloc[0]
        else:
            st.warning("검색된 재고가 없습니다.")

    with st.form("outbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            o_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"])
            client = st.text_input("거래처")
        with c2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (L열)")
            comments = st.text_input("변경사항 (M열)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                row = [
                    str(o_date), manager, client, 
                    selected_row['temp_품목'], selected_row['temp_브랜드'], 
                    amount, selected_row['temp_소비기한'],
                    "", "", "", "", 
                    "이체" if is_transfer else "", 
                    comments
                ]
                try:
                    save_outbound(row)
                    st.success(f"✅ [{selected_row['temp_품목']}] {amount}건 등록 완료!")
                    st.cache_data.clear() 
                except Exception as e: st.error(f"실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력이 필요합니다.")
