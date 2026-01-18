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

# 로그인 화면 (미리보기 글자 삭제 완료)
if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    input_id = st.text_input("아이디")
    input_pw = st.text_input("비밀번호", type="password")
    
    if st.button("로그인", type="primary", use_container_width=True):
        login_check(input_id, input_pw)
    st.stop()

# 3. 구글 시트 데이터 가져오기 (클라우드 보안 버전)
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

# 4. 메인 화면
with st.sidebar:
    st.write(f"접속자: **{st.session_state.get('user_id', 'AZ')}**")
    if st.button("로그아웃"):
        st.session_state['logged_in'] = False
        st.rerun()
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

st.title("🥩 에이젯광주 실시간 재고")
st.caption(f"최근 조회: {datetime.now().strftime('%H:%M:%S')}")

df = load_google_sheet_data()

# 5. 검색 및 표 출력 (검색창 추가 완료)
if not df.empty:
    search_item = st.text_input("🔍 품명 검색", placeholder="예: 목살, 삼겹")
    filtered_df = df.copy()
    
    if search_item:
        # '품명' 열에서 검색어가 포함된 데이터만 필터링
        filtered_df = filtered_df[filtered_df['품명'].astype(str).str.contains(search_item)]

    st.divider()
    st.subheader(f"총 {len(filtered_df)}건 발견")
    st.dataframe(filtered_df, use_container_width=True, hide_index=True)
else:
    st.info("데이터를 불러오는 중이거나 연결에 실패했습니다.")
