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

# 세션 상태 초기화
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None

# ------------------------------------------------------------------
# 2. 쿠키 기반 로그인 시스템
# ------------------------------------------------------------------
cookie_manager = stx.CookieManager()

# 쿠키 값 확인 (앱 시작 시 한 번 실행)
if not st.session_state['logged_in']:
    cookie_val = cookie_manager.get(COOKIE_NAME)
    if cookie_val:
        st.session_state['logged_in'] = True
        st.session_state['user_id'] = cookie_val
        st.rerun()

def logout():
    cookie_manager.delete(COOKIE_NAME)
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.success("✅ 로그아웃 되었습니다.")
    time.sleep(1)
    st.rerun()

# ------------------------------------------------------------------
# 3. 로그인 화면 (비로그인 시 메인 화면 차단)
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
                st.success("✅ 로그인 성공! 잠시만 기다려주세요...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ 아이디 또는 비밀번호를 확인하세요.")
    st.stop()

# ------------------------------------------------------------------
# 4. 메인 화면 (사이드바 및 데이터 로드)
# ------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 **{st.session_state['user_id']}**님 접속 중")
    if st.button("로그아웃", use_container_width=True):
        logout()

@st.cache_data(ttl=60)
def load_data():
    try:
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        # st.secrets에 gcp_service_account가 설정되어 있어야 합니다.
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
        client = gspread.authorize(creds)
        sh = client.open('에이젯광주 운영독스').worksheet('raw_운영부재고')
        df = pd.DataFrame(sh.get_all_records())
        
        # 컬럼명 정리
        df.rename(columns={
            'B/L NO': 'BL넘버', 
            '식별번호': 'BL넘버', 
            'B/L NO,식별번호': 'BL넘버', 
            '브랜드-등급-est': '브랜드'
        }, inplace=True)
        
        # 데이터 클렌징 (공백 제거 등)
        return df.applymap(lambda x: str(x).strip() if x else "")
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

    # 사용자 권한별 필터링 및 컬럼 설정
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
        r_item = sc1.text_input("🔍 품목 필터", key="out_item_filter")
        r_brand = sc2.text_input("🏢 브랜드 필터", key="out_brand_filter")

        t_df = f_df.copy().reset_index(drop=True)
        if r_item: t_df = t_df[t_df['품명'].str.contains(r_item, na=False)]
        if r_brand: t_df = t_df[t_df['브랜드'].str.contains(r_brand, na=False, case=False)]

        if '소비기한' in t_df.columns:
            t_df = t_df.sort_values(by='소비기한', ascending=True)

        if not t_df.empty:
            opts = t_df.apply(lambda x: f"[{x.get('창고명','미지정')}] {x['품명']} / {x['브랜드']} (재고: {x.get('재고수량','0')}) [소비기한: {x.get('소비기한','')}]", axis=1)
            sel_idx = st.selectbox("출고 품목 선택 (소비기한 임박순)", opts.index, format_func=lambda i: opts[i])
            row = t_df.loc[sel_idx]

            # 가용 재고 계산
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
                changes = f2.text_input("변경사항", placeholder="특이사항 입력")
                qty = f3.number_input("수량", min_value=1, step=1, value=1)
                price = f3.number_input("단가", min_value=0, step=100)
                is_trans = f3.checkbox("이체 여부", value=False)

                if st.form_submit_button("출고 등록하기", type="primary"):
                    if float(qty) > available_stock:
                        st.error(f"❌ 재고가 부족합니다. (현재 재고: {available_stock})")
                    elif not client_name:
                        st.error("❌ 거래처를 입력해주세요.")
                    else:
                        try:
                            # 구글 시트 출고증 기록
                            scope_out = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
                            creds_out = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope_out)
                            gc = gspread.authorize(creds_out)
                            out_sh = gc.open_by_key('1xdRllSZ0QTS_h8-HNbs0RqFja9PKnklYon7xrKDHTbo').worksheet('출고증')

                            target_date = f"{out_date.month}. {out_date.day}"
                            vals = out_sh.get_all_values()
                            target_row_idx = -1

                            # 날짜에 맞는 빈 행 찾기 (C열 기준 날짜 매칭 후 D열 빈 곳 찾기)
                            for i, r in enumerate(vals, 1):
                                if len(r) > 2 and str(r[2]).strip() == target_date:
                                    if len(r) <= 3 or str(r[3]).strip() == "":
                                        target_row_idx = i
                                        break

                            if target_row_idx != -1:
                                out_data_list = [
                                    str(manager),
                                    str(client_name),
                                    str(row['품명']),
                                    str(row['브랜드']),
                                    str(row.get('BL넘버','-')),
                                    int(qty),
                                    str(row.get('창고명','')),
                                    int(price),
                                    "이체" if is_trans else "",
                                    str(changes)
                                ]
                                # D열부터 M열까지 업데이트
                                out_sh.update(range_name=f"D{target_row_idx}:M{target_row_idx}", values=[out_data_list], value_input_option='USER_ENTERED')
                                st.success(f"✅ {target_date} / {target_row_idx}행에 등록 완료!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error(f"❌ '{target_date}' 날짜의 빈 행이 없습니다. 구글 시트를 확인해 주세요.")
                        except Exception as e:
                            st.error(f"🚨 시스템 오류: {e}")
        else:
            st.warning("검색 결과가 없습니다.")
else:
    st.info("데이터를 불러오는 중이거나 재고가 없습니다.")
