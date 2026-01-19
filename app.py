import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ------------------------------------------------------------------
# 1. 기본 설정 및 드롭다운 줄바꿈 스타일
# ------------------------------------------------------------------
st.set_page_config(page_title="에이젯 재고관리", page_icon="🥩", layout="wide")

st.markdown("""
    <style>
        div[data-baseweb="select"] > div { white-space: normal !important; height: auto !important; min-height: 50px; }
        ul[role="listbox"] li span { white-space: normal !important; word-break: break-all !important; display: block !important; line-height: 1.5 !important; }
    </style>
""", unsafe_allow_html=True)

USERS = {"AZ": "5835", "AZS": "0983"}

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

def login_check(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = username
        st.rerun()
    else:
        st.error("아이디 또는 비밀번호를 확인하세요.")

if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    i_id = st.text_input("아이디")
    i_pw = st.text_input("비밀번호", type="password")
    if st.button("로그인", type="primary", use_container_width=True):
        login_check(i_id.strip().upper(), i_pw.strip())
    st.stop()

# ------------------------------------------------------------------
# 2. 데이터 로드 (재고 시트)
# ------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sh = client.open('에이젯광주 운영독스').worksheet('raw_운영부재고')
        df = pd.DataFrame(sh.get_all_records())
        df.rename(columns={'B/L NO':'BL넘버','식별번호':'BL넘버','B/L NO,식별번호':'BL넘버','브랜드-등급-est':'브랜드'}, inplace=True)
        return df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
    except: return pd.DataFrame()

# ------------------------------------------------------------------
# 3. 메인 화면 (조회)
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
    
    st.dataframe(f_df[cols], use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 4. 출고 등록 (AZS 전용) - 핵심 수정 부분
    # ------------------------------------------------------------------
    if current_user == "AZS":
        st.divider()
        st.header("🚚 출고 등록")
        
        # 품목 선택 필터
        sc1, sc2 = st.columns(2)
        r_item = sc1.text_input("🔍 품목 필터", key="r_i")
        r_brand = sc2.text_input("🏢 브랜드 필터", key="r_b")
        
        t_df = f_df.copy()
        if r_item: t_df = t_df[t_df['품명'].str.contains(r_item, na=False)]
        if r_brand: t_df = t_df[t_df['브랜드'].str.contains(r_brand, na=False, case=False)]
        
        if not t_df.empty:
            # 드롭다운 포맷: 브랜드 품명 창고 BL넘버 (요청하신 대로 공백 구분)
            opts = t_df.apply(lambda x: f"{x['브랜드']} {x['품명']} {x.get('창고명','')} {x.get('BL넘버','')}".strip(), axis=1)
            sel_idx = st.selectbox("출고 품목 선택", opts.index, format_func=lambda i: opts[i])
            row = t_df.loc[sel_idx]

            with st.form("out_form"):
                f1, f2, f3 = st.columns(3)
                out_date = f1.date_input("출고일", datetime.now())
                manager = f1.text_input("담당자", value="강경현")
                client_name = f1.text_input("거래처")
                qty = f3.number_input("수량", min_value=1, value=1)
                price = f3.number_input("단가", min_value=0, step=100)
                is_trans = f3.checkbox("이체 여부", value=True)
                
                if st.form_submit_button("출고 등록하기", type="primary"):
                    try:
                        # 시트 연결
                        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'])
                        gc = gspread.authorize(creds)
                        out_sh = gc.open('에이젯광주 출고증').worksheet('출고증')
                        
                        # [날짜 매칭 핵심] "1. 19" 형식 맞추기
                        target_date = f"{out_date.month}. {out_date.day}"
                        
                        # 모든 데이터 가져와서 날짜 줄 찾기
                        vals = out_sh.get_all_values()
                        target_idx = -1
                        for i, r in enumerate(vals, 1):
                            # C열(index 2)이 날짜와 일치하고 D열(index 3)이 비어있는지 확인
                            if len(r) > 2 and str(r[2]).strip() == target_date:
                                if len(r) <= 3 or str(r[3]).strip() == "":
                                    target_idx = i
                                    break
                        
                        if target_idx != -1:
                            # 데이터 클리닝 (Response 200 방지)
                            data = [
                                str(manager), str(client_name), str(row['품명']), 
                                str(row['브랜드']), str(row.get('BL넘버','-')), 
                                int(qty), str(row.get('창고명','')), int(price), 
                                "이체" if is_trans else ""
                            ]
                            
                            # 최신 gspread update 방식 (가장 안전)
                            out_sh.update(range_name=f"D{target_idx}:L{target_idx}", 
                                         values=[data], 
                                         value_input_option='USER_ENTERED')
                            
                            st.success(f"✅ {target_date} / {target_idx}행 등록 완료!")
                        else:
                            st.error(f"❌ '{target_date}' 날짜의 빈 행을 찾지 못했습니다. (C열 날짜 확인 필수)")
                    except Exception as e:
                        st.error("🚨 시스템 오류가 발생했습니다.")
                        st.exception(e) # 범인을 잡아주는 상세 에러 출력
        else:
            st.warning("검색 결과가 없습니다.")
