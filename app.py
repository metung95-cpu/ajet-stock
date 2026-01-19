import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1. 화면 설정
st.set_page_config(page_title="에이젯 재고관리", page_icon="🥩", layout="wide")

# 2. 사용자 로그인 (AZ / 5835)
USERS = {"AZ": "5835"}

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

def login_check(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = username
        st.rerun()
    else:
        st.error("아이디 또는 비밀번호를 확인하세요.")

# 로그인 로직
if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    input_id = st.text_input("아이디")
    input_pw = st.text_input("비밀번호", type="password")
    
    if st.button("로그인", type="primary", use_container_width=True):
        login_check(input_id, input_pw)
    st.stop()

# 3. 구글 시트 데이터 가져오기
@st.cache_data(ttl=60)
def load_google_sheet_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        spreadsheet = client.open('에이젯광주 운영독스') 
        sheet = spreadsheet.worksheet('raw_운영부재고')
        data = sheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"연결 오류: {e}")
        return pd.DataFrame()

# 4. 사이드바 메뉴
with st.sidebar:
    st.write(f"접속자: **{st.session_state.get('user_id', 'AZ')}**")
    if st.button("로그아웃"):
        st.session_state['logged_in'] = False
        st.rerun()
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

# 5. 메인 화면
st.title("🥩 에이젯광주 실시간 재고")
st.caption(f"최근 조회: {datetime.now().strftime('%H:%M:%S')}")

df = load_google_sheet_data()

if not df.empty:
    # --- 검색창 레이아웃 (품명과 브랜드를 나란히 배치) ---
    col1, col2 = st.columns(2)
    with col1:
        search_item = st.text_input("🔍 품명 검색", placeholder="예: 목살, 삼겹")
    with col2:
        search_brand = st.text_input("🏢 브랜드 검색", placeholder="예: Teys, JBS")
    
    # --- 정렬 및 필터링 로직 ---
    filtered_df = df.copy()
    
    # 1. 기본 정렬 (본점 우선 + 품명순)
    if '창고명' in filtered_df.columns and '품명' in filtered_df.columns:
        filtered_df['is_main'] = filtered_df['창고명'] == '본점'
        filtered_df = filtered_df.sort_values(by=['is_main', '품명'], ascending=[False, True])
        filtered_df = filtered_df.drop(columns=['is_main'])
    elif '품명' in filtered_df.columns:
        filtered_df = filtered_df.sort_values(by='품명')

    # 2. 품명 필터링
    if search_item:
        filtered_df = filtered_df[filtered_df['품명'].astype(str).str.contains(search_item)]
    
    # 3. 브랜드 필터링 (대소문자 구분 없이 'T'만 쳐도 검색되게 설정)
    if search_brand and '브랜드' in filtered_df.columns:
        # case=False: 대소문자 무시 (t를 쳐도 Teys 검색 가능)
        # na=False: 데이터가 비어있는 칸 에러 방지
        filtered_df = filtered_df[filtered_df['브랜드'].astype(str).str.contains(search_brand, case=False, na=False)]

    st.divider()
    st.subheader(f"총 {len(filtered_df)}건 발견")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
else:
    st.info("데이터를 불러오는 중이거나 연결에 실패했습니다.")
