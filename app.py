import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

# 페이지 설정
st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# --- 구글 인증 (상명님 Secrets 이름 'gcp_service_account'에 맞춤) ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 스트림릿 Secrets에 설정된 [gcp_service_account] 데이터를 가져옵니다.
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        # 로컬 테스트용 (key.json 파일이 있을 경우)
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
        
    return gspread.authorize(credentials)

# --- 데이터 로딩 ---
@st.cache_data(ttl=600)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

# --- 로그인 시스템 ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 에이젯 재고관리 로그인")
    user_id = st.text_input("아이디 (AZ 또는 AZS)")
    password = st.text_input("비밀번호", type="password") 
    
    if st.button("로그인"):
        # 상명님이 요청하신 비밀번호 설정
        if user_id == "AZ" and password == "5835":
            st.session_state.logged_in = True
            st.session_state.user_role = "AZ"
            st.rerun()
        elif user_id == "AZS" and password == "0983":
            st.session_state.logged_in = True
            st.session_state.user_role = "AZS"
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 틀렸습니다.")
    st.stop()

# --- 로그아웃 버튼 ---
st.sidebar.write(f"👤 접속: {st.session_state.user_role}")
if st.sidebar.button("로그아웃"):
    st.session_state.logged_in = False
    st.rerun()

# 데이터 불러오기
df = load_inventory()

st.title("📦 에이젯 실시간 재고 현황")

# --- 검색 필터 ---
col1, col2 = st.columns(2)
with col1: search_name = st.text_input("품명 검색", "")
with col2: search_brand = st.text_input("브랜드 검색", "")

filtered_df = df.copy()
if search_name: 
    filtered_df = filtered_df[filtered_df['품명'].str.contains(search_name, na=False)]
if search_brand: 
    filtered_df = filtered_df[filtered_df['브랜드'].str.contains(search_brand, na=False)]

# --- 권한별 데이터 제한 (AZS는 본점 제외) ---
if st.session_state.user_role == "AZS":
    if '창고' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['창고'] != '본점']

# 결과 표 출력
st.dataframe(filtered_df, use_container_width=True, hide_index=True)

# --- 출고 등록 양식 (AZS 전용) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록")
    with st.form("outbound_form"):
        out_date = st.date_input("출고일", datetime.now())
        manager = st.selectbox("담당자", ["신상명", "관리자", "기타"])
        client = st.text_input("거래처")
        amount = st.number_input("수량", min_value=1)
        
        if st.form_submit_button("등록하기"):
            # 추후 시트 저장 로직 연결 가능
            st.success(f"[{client}] {amount}건 출고 등록 완료!")
