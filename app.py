import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import extra_streamlit_components as stx

# ------------------------------------------------------------------
# 1. 기본 설정 및 스타일
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 재고관리 Lite", page_icon="🥩", layout="wide")

st.markdown("""
    <style>
        div[data-baseweb="select"] > div { white-space: normal !important; height: auto !important; min-height: 60px; }
        .stMetric { background-color: #f0f2f6; padding: 10px; border-radius: 5px; }
    </style>
""", unsafe_allow_html=True)

USERS = {"AZ": "5835", "AZS": "0983"}
MANAGERS = ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"]
COOKIE_NAME = "ajet_lite_v1" 

# ------------------------------------------------------------------
# 2. 쿠키 및 세션 관리 (로딩 안정화)
# ------------------------------------------------------------------
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None

# 깃허브 환경에서 쿠키 로딩 지연 대응
cookie_val = cookie_manager.get(COOKIE_NAME)
if cookie_val and not st.session_state['logged_in']:
    st.session_state['logged_in'] = True
    st.session_state['user_id'] = cookie_val

# ------------------------------------------------------------------
# 3. 데이터 로드 (정적 데이터로 대체)
# ------------------------------------------------------------------
@st.cache_data
def load_inventory_data():
    # 실제 시트 연동 대신 샘플 데이터를 생성합니다.
    data = [
        {"품명": "알목심(냉장)", "브랜드": "EXCEL", "재고수량": "150", "BL넘버": "BL12345", "창고명": "곤지암", "소비기한": "2026-03-18"},
        {"품명": "진갈비살(냉장)", "브랜드": "IBP", "재고수량": "80", "BL넘버": "BL67890", "창고명": "독산", "소비기한": "2026-03-25"},
        {"품명": "토시살(냉장)", "브랜드": "TEYS", "재고수량": "45", "BL넘버": "BL13579", "창고명": "곤지암", "소비기한": "2026-03-10"}
    ]
    return pd.DataFrame(data)

@st.cache_data
def load_price_data():
    # 시세 샘플 데이터
    data = [
        {"품명": "알목심(냉장)", "브랜드": "EXCEL", "단가": "15500", "단가_숫자": 15500},
        {"품명": "진갈비살(냉장)", "브랜드": "IBP", "단가": "42000", "단가_숫자": 42000},
        {"품명": "토시살(냉장)", "브랜드": "TEYS", "단가": "28000", "단가_숫자": 28000}
    ]
    return pd.DataFrame(data)

# ------------------------------------------------------------------
# 4. 로그인 / 로그아웃 로직
# ------------------------------------------------------------------
def login_check(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = username
        expires = datetime.now() + timedelta(days=7)
        cookie_manager.set(COOKIE_NAME, username, expires_at=expires)
        st.success("✅ 로그인 성공!")
        time.sleep(1)
        st.rerun()
    else:
        st.error("아이디 또는 비밀번호 확인")

if not st.session_state['logged_in']:
    st.title("🔒 에이젯 관리 시스템 (Lite)")
    with st.form("login_form"):
        i_id = st.text_input("아이디")
        i_pw = st.text_input("비밀번호", type="password")
        if st.form_submit_button("로그인", type="primary"):
            login_check(i_id.strip().upper(), i_pw.strip())
    st.stop()

# ------------------------------------------------------------------
# 5. 메인 대시보드
# ------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 **{st.session_state['user_id']}**님")
    if st.button("로그아웃"):
        cookie_manager.delete(COOKIE_NAME)
        st.session_state['logged_in'] = False
        st.rerun()

st.title("🥩 에이젯광주 통합 관리 시스템 (오프라인 모드)")

df_inventory = load_inventory_data()
df_price = load_price_data()

# [검색/필터링/출고 로직은 기존과 동일하되, 시트 쓰기 부분만 모의 동작으로 변경]
c1, c2 = st.columns(2)
s_item = c1.text_input("🔍 품명 검색")
s_brand = c2.text_input("🏢 브랜드 검색")

f_df = df_inventory.copy()
if s_item: f_df = f_df[f_df['품명'].str.contains(s_item, na=False)]
if s_brand: f_df = f_df[f_df['브랜드'].str.contains(s_brand, na=False, case=False)]

st.subheader("📦 현재고 현황")
st.dataframe(f_df, use_container_width=True, hide_index=True)

# 출고 등록 섹션 (시트 쓰기 제외)
if st.session_state['user_id'] == "AZS":
    st.divider()
    st.header("🚚 출고 등록 (시뮬레이션)")
    
    # ... (기존 폼 로직 유지) ...
    if st.button("출고 시뮬레이션 버튼"):
        st.success("✅ [오프라인 모드] 실제 시트 연동 없이 등록 로직만 테스트되었습니다.")
