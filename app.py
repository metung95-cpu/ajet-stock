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
# 2. 쿠키 기반 로그인 시스템 (30분 유지)
# ------------------------------------------------------------------
# TypeError 원인이었던 experimental_allow_widgets=True 제거 완료!
@st.cache_resource
def get_manager():
    return stx.CookieManager()

cookie_manager = get_manager()
time.sleep(0.5) # 쿠키 매니저 초기화 안정화

# 브라우저 쿠키를 확인하여 다른 탭/새로고침 시에도 로그인 유지
cookie_val = cookie_manager.get(COOKIE_NAME)
if cookie_val:
    st.session_state['logged_in'] = True
    st.session_state['user_id'] = cookie_val

# 30분(1800초) 자동 로그아웃 체크 로직
if st.session_state['logged_in']:
    elapsed = (datetime.now() - st.session_state.get('last_activity', datetime.now())).total_seconds()
    if elapsed > 1800:
        cookie_manager.delete(COOKIE_NAME)
        st.session_state['logged_in'] = False
        st.warning("🔒 30분간 활동이 없어 자동 로그아웃되었습니다.")
        time.sleep(1)
        st.rerun()
    else:
        st.session_state['last_activity'] = datetime.now()

def login_check(username, password):
    if username in USERS and USERS[username] == password:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = username
        st.session_state['last_activity'] = datetime.now()
        
        # 브라우저 쿠키 자체도 30분 뒤에 만료되도록 설정
        expire_date = datetime.now() + timedelta(minutes=30)
        cookie_manager.set(COOKIE_NAME, username, expires_at=expire_date)
        
        st.success("✅ 로그인 성공! (30분간 유지됩니다)")
        time.sleep(1)
        st.rerun()
    else:
        st.error("❌ 아이디 또는 비밀번호를 확인하세요.")

def logout():
    cookie_manager.delete(COOKIE_NAME)
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.rerun()

# ------------------------------------------------------------------
# 3. 로그인 화면 
# ------------------------------------------------------------------
if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    with st.form("login_form"):
        i_id = st.text_input("아이디")
        i_pw = st.text_input("비밀번호", type="password")
        submit = st.form_submit_button("로그인", type="primary", use_container_width=True)
        
        if submit:
            login_check(i_id.strip().upper(), i_pw.strip())
    st.stop()  # 로그인 전이면 아래 코드(데이터 로드) 실행 안 함

# ------------------------------------------------------------------
# 4. 메인 화면 시작 (데이터 로드 및 사이드바)
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
        return df.applymap(lambda x: str(x).strip() if x else "")
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 5. 조회 및 업무 로직
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
    
    # AZS 계정은 '본점' 창고 제외
    if current_user == "AZS":
        f_df = f_df[~f_df['창고명'].str.contains("본점", na=False)]
        cols = ['품명', '브랜드', '재고수량', 'BL넘버', '창고명', '소비기한']
    else:
        cols = ['품명', '브랜드', '재고수량', '창고명', '소비기한']

    # 열 이름 존재 여부 확인 후 출력 (안전 장치 추가)
    valid_cols = [c for c in cols if c in f_df.columns]
    st.dataframe(f_df[valid_cols], use_container_width=True, hide_index=True)

    # ------------------------------------------------------------------
    # 6. 출고 등록 (AZS 전용 기능)
    # ------------------------------------------------------------------
    if current_user == "AZS":
        st.divider()
        st.header("🚚 출고 등록")

        sc1, sc2 = st.columns(2)
        r_item = sc1.text_input("🔍 품목 필터", key="r_i")
        r_brand = sc2.text_input("🏢 브랜드 필터", key="r_b")

        t_df = f_df.copy().reset_index(drop=True)
        if r_item: t_df = t_df[t_df['품명'].str.contains(r_item, na=False)]
        if r_brand: t_df = t_df[t_df['브랜드'].str.contains(r_brand, na=False, case=False)]

        if '소비기한' in t_df.columns:
            t_df = t_df.sort_values(by='소비기한', ascending=True)

        if not t_df.empty:
            opts = t_df.apply(lambda x: f"[{x.get('창고명','미지정')}] {x['품명']} / {x['브랜드']} (재고: {x.get('재고수량','0')}) [소비기한: {x.get('소비기한','')}]".strip(), axis=1)
            sel_idx = st.selectbox("출고 품목 선택 (소비기한 임박순)", opts.index, format_func=lambda i: opts[i])
            row = t_df.loc[sel_idx]

            try:
                stock_val = str(row.get('재고수량', '0')).replace(',', '')
                available_stock = float(stock_val) if stock_val else 0.0
            except:
                available_stock = 0.0

            with st.form("out_form"):
                f1, f2, f3 = st.columns(3)
                out_date = f1.date_input("출고일", datetime.now())
                manager = f1.selectbox("담당자", MANAGERS)
                client_name = f1.text_input("거래처")

                qty = f3.number_input("수량", min_value=1.0, step=1.0, value=1.0)

                if qty > available_stock:
                    st.error(f"🚨 출고 가능한 재고({available_stock})를 초과했습니다.")

                price = f3.number_input("단가", min_value=0, step=100)
                is_trans = f3.checkbox("이체 여부 (필요 시 체크)", value=False)

                if st.form_submit_button("출고 등록하기", type="primary"):
                    if qty > available_stock:
                        st.error("❌ 재고가 부족하여 등록할 수 없습니다.")
                    elif not client_name:
                        st.error("❌ 거래처를 입력해주세요.")
                    else:
                        try:
                            creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets'])
                            gc = gspread.authorize(creds)
                            out_sh = gc.open_by_key('1xdRllSZ0QTS_h8-HNbs0RqFja9PKnklYon7xrKDHTbo').worksheet('출고증')

                            target_date = f"{out_date.month}. {out_date.day}"
                            vals = out_sh.get_all_values()
                            target_idx = -1
                            
                            for i, r in enumerate(vals, 1):
                                if len(r) > 2 and str(r[2]).strip() == target_date:
                                    if len(r) <= 3 or str(r[3]).strip() == "":
                                        target_idx = i
                                        break

                            if target_idx != -1:
                                data = [
                                    str(manager), str(client_name), str(row['품명']), 
                                    str(row['브랜드']), str(row.get('BL넘버','-')), 
                                    int(qty), str(row.get('창고명','')), int(price), 
                                    "이체" if is_trans else ""
                                ]
                                out_sh.update(range_name=f"D{target_idx}:L{target_idx}", values=[data], value_input_option='USER_ENTERED')
                                st.success(f"✅ {target_date} / {target_idx}행 등록 완료!")
                                st.session_state['last_activity'] = datetime.now()
                            else:
                                st.error(f"❌ '{target_date}' 날짜의 빈 행이 없습니다.")
                        except Exception as e:
                            st.error("🚨 시스템 오류!")
                            st.exception(e)
        else:
            st.warning("검색 결과가 없습니다.")
