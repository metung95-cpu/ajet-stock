import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import extra_streamlit_components as stx
import time

# ------------------------------------------------------------------
# 1. 기본 설정 및 스타일
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 재고관리", page_icon="🥩", layout="wide")

st.markdown("""
    <style>
        div[data-baseweb="select"] > div { white-space: normal !important; height: auto !important; min-height: 60px; }
        ul[role="listbox"] li span { white-space: normal !important; word-break: break-all !important; display: block !important; line-height: 1.6 !important; }
    </style>
""", unsafe_allow_html=True)

USERS = {"AZ": "5835", "AZS": "0983"}
MANAGERS = ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"]
COOKIE_NAME = "az_inventory_auth" 

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'last_activity' not in st.session_state:
    st.session_state['last_activity'] = datetime.now()

# ------------------------------------------------------------------
# 2. 쿠키 기반 로그인 시스템 (철통 방어 로직)
# ------------------------------------------------------------------
cookie_manager = stx.CookieManager()

if 'auth_checked' not in st.session_state:
    st.session_state['auth_checked'] = True
    time.sleep(0.5)
    st.rerun()

cookie_val = cookie_manager.get(COOKIE_NAME)

if cookie_val and not st.session_state['logged_in']:
    st.session_state['logged_in'] = True
    st.session_state['user_id'] = cookie_val
    st.session_state['last_activity'] = datetime.now()

if st.session_state['logged_in']:
    elapsed = (datetime.now() - st.session_state.get('last_activity', datetime.now())).total_seconds()
    if elapsed > 28800: 
        cookie_manager.delete(COOKIE_NAME)
        st.session_state['logged_in'] = False
        st.warning("🔒 8시간이 지나 자동 로그아웃되었습니다.")
        time.sleep(1)
        st.rerun()
    else:
        st.session_state['last_activity'] = datetime.now()

def logout():
    cookie_manager.delete(COOKIE_NAME)
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    time.sleep(1) 
    st.rerun()

# ------------------------------------------------------------------
# 3. 로그인 화면 (데이터 접근 차단)
# ------------------------------------------------------------------
if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    with st.form("login_form"):
        i_id = st.text_input("아이디")
        i_pw = st.text_input("비밀번호", type="password")
        submit = st.form_submit_button("로그인", type="primary", use_container_width=True)
        
        if submit:
            username = i_id.strip().upper()
            password = i_pw.strip()
            
            if username in USERS and USERS[username] == password:
                expire_date = datetime.now() + timedelta(hours=8)
                cookie_manager.set(COOKIE_NAME, username, expires_at=expire_date)
                
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = username
                st.session_state['last_activity'] = datetime.now()
                
                st.success("✅ 로그인 성공! (8시간 동안 유지됩니다. 잠시만 기다려주세요...)")
                time.sleep(1.5) 
                st.rerun()
            else:
                st.error("❌ 아이디 또는 비밀번호를 확인하세요.")
    st.stop() 

# ------------------------------------------------------------------
# 4. 메인 화면 시작 (사이드바)
# ------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 **{st.session_state['user_id']}**님 접속 중")
    if st.button("로그아웃"):
        logout()

@st.cache_data(ttl=60)
def load_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sh = client.open('에이젯광주 운영독스').worksheet('raw_운영부재고')
        df = pd.DataFrame(sh.get_all_records())
        df.rename(columns={'B/L NO':'BL넘버','식별번호':'BL넘버','B/L NO,식별번호':'BL넘버','브랜드-등급-est':'브랜드'}, inplace=True)
        return df.map(lambda x: str(x).strip() if x else "") 
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 5. 재고 조회 로직
# ------------------------------------------------------------------
st.title("🥩 에이젯광주 실시간 재고")
df = load_data()

if not df.empty:
    c1, c2 = st.columns(2)
    s_item = c1.text_input("🔍 품명 검색")
    s_brand = c2.text_input("🏢 브랜드 검색")

    f_df = df.copy()
    if s_item: f_df = f_df[f_df['품명'].str.contains(s_item, na=False)]
    if s_brand: f_df = f_df[f_df['브랜드'].str.contains(s_brand, na=False, case=False)]

    current_user = st.session_state['user_id']

    if current_user == "AZS":
        f_df = f_df[~f_df['창고명'].str.contains("본점", na=False)]
        cols = ['품명', '브랜드', '재고수량', 'BL넘버', '창고명', '소비기한']
    else:
        cols = ['품명', '브랜드', '재고수량', '창고명', '소비기한']

    valid_cols = [c for c in cols if c in f_df.columns]
    st.dataframe(f_df[valid_cols], use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 6. 출고 등록 (AZS 전용 기능)
    # ------------------------------------------------------------------
    if current_user == "AZS":
        st.divider()
        st.header("🚚 출고 등록")

        sc1, sc2 = st.columns(2)
