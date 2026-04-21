import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import extra_streamlit_components as stx
import time
import re

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

# 상수 설정
USERS = {"AZ": "5835", "AZS": "0983"}
MANAGERS = ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"]
COOKIE_NAME = "az_inventory_auth"

# ------------------------------------------------------------------
# 2. 구글 서비스 연결 함수
# ------------------------------------------------------------------
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    return gspread.authorize(creds)

# ------------------------------------------------------------------
# 3. 로그인 및 쿠키 시스템
# ------------------------------------------------------------------
cookie_manager = stx.CookieManager()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

cookie_val = cookie_manager.get(COOKIE_NAME)
if cookie_val and not st.session_state['logged_in']:
    st.session_state['logged_in'] = True
    st.session_state['user_id'] = cookie_val

def logout():
    cookie_manager.delete(COOKIE_NAME)
    st.session_state['logged_in'] = False
    st.session_state['user_id'] = None
    st.rerun()

if not st.session_state['logged_in']:
    st.title("🔒 에이젯 재고관리 로그인")
    with st.form("login_form"):
        i_id = st.text_input("아이디").strip().upper()
        i_pw = st.text_input("비밀번호", type="password").strip()
        submit = st.form_submit_button("로그인", type="primary", use_container_width=True)

        if submit:
            if i_id in USERS and USERS[i_id] == i_pw:
                expire_date = datetime.now() + timedelta(hours=8)
                cookie_manager.set(COOKIE_NAME, i_id, expires_at=expire_date)
                st.session_state['logged_in'] = True
                st.session_state['user_id'] = i_id
                st.success("✅ 로그인 성공! 잠시만 기다려주세요...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("❌ 아이디 또는 비밀번호가 틀렸습니다.")
    st.stop()

# ------------------------------------------------------------------
# 4. 데이터 로딩 (캐시 적용)
# ------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_data():
    try:
        gc = get_gspread_client()
        sh = gc.open('에이젯광주 운영독스').worksheet('raw_운영부재고')
        data = sh.get_all_records()
        df = pd.DataFrame(data)
        
        df.rename(columns={
            'B/L NO': 'BL넘버', 
            '식별번호': 'BL넘버', 
            'B/L NO,식별번호': 'BL넘버', 
            '브랜드-등급-est': '브랜드'
        }, inplace=True)
        
        df = df.map(lambda x: str(x).strip() if x else "")
        df['_is_bonjum'] = df['창고명'].apply(lambda x: 1 if "본점" in str(x) else 0)
        df['_date_sort'] = pd.to_datetime(df['소비기한'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
        
        return df
    except Exception as e:
        st.error(f"🚨 데이터 로드 실패: {e}")
        return pd.DataFrame()

# ------------------------------------------------------------------
# 5. 메인 화면 - 재고 현황
# ------------------------------------------------------------------
with st.sidebar:
    st.write(f"👤 **{st.session_state['user_id']}**님 접속 중")
    if st.button("로그아웃"):
        logout()

st.title("🥩 에이젯광주 실시간 재고")
df = load_data()

if not df.empty:
    c1, c2 = st.columns(2)
    s_item = c1.text_input("🔍 품명 검색")
    s_brand = c2.text_input("🏢 브랜드 검색")

    f_df = df.copy()
    if s_item: f_df = f_df[f_df['품명'].str.contains(s_item, na=False, case=False)]
    if s_brand: f_df = f_df[f_df['브랜드'].str.contains(s_brand, na=False, case=False)]

    current_user = st.session_state['user_id']
    f_df = f_df.sort_values(by=['_is_bonjum', '_date_sort'])

    if current_user == "AZS":
        f_df = f_df[f_df['_is_bonjum'] == 0]
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
        st.header("🚚 출고 등록 (본점 제외)")

        sc1, sc2 = st.columns(2)
        r_item = sc1.text_input("🔍 출고 품목 필터", key="out_item")
        r_brand = sc2.text_input("🏢 출고 브랜드 필터", key="out_brand")

        t_df = f_df[f_df['_is_bonjum'] == 0].copy().reset_index(drop=True)
        if r_item: t_df = t_df[t_df['품명'].str.contains(r_item, na=False, case=False)]
        if r_brand: t_df = t_df[t_df['브랜드'].str.contains(r_brand, na=False, case=False)]

        if not t_df.empty:
            def make_compact_label(x):
                exp = str(x['소비기한']).strip()
                if exp.startswith("20") and len(exp) >= 8:
                    exp = exp[2:]
                exp = re.sub(r'([.-])0(\d)', r'\1\2', exp) 
                wh = str(x.get('창고명', '')).strip()
                return f"[{exp} | {wh}] {x['품명']} / {x['브랜드']} (재고:{x['재고수량']})"

            opts = t_df.apply(make_compact_label, axis=1)
            sel_idx = st.selectbox("출고할 재고 선택 (소비기한순)", opts.index, format_func=lambda i: opts[i])
            row = t_df.loc[sel_idx]

            try:
                available_stock = float(str(row['재고수량']).replace(',', ''))
            except:
                available_stock = 0.0

            with st.form("out_form", clear_on_submit=True):
                f1, f2, f3 = st.columns(3)
                
                out_date = f1.date_input("출고일", datetime.now())
                manager = f1.selectbox("담당자", MANAGERS)
                client_name = f1.text_input("거래처")
                
                changes = f2.text_input("변경사항(M열)", placeholder="특이사항 입력")
                
                # 💡 [수정] 중복 제거 및 정수형(int) 입력 고정
                qty = f3.number_input("출고 수량", min_value=1, step=1, value=1)
                price = f3.number_input("판매 단가", min_value=0, step=100)
                is_trans = f3.checkbox("이체 여부 (L열)", value=False)

                if st.form_submit_button("출고 확정 및 등록", type="primary"):
                    if qty > available_stock:
                        st.error(f"❌ 재고 부족! (현재 가용: {available_stock})")
                    elif not client_name:
                        st.error("❌ 거래처를 입력해주세요.")
                    else:
                        try:
                            gc = get_gspread_client()
                            out_sh = gc.open_by_key('1xdRllSZ0QTS_h8-HNbs0RqFja9PKnklYon7xrKDHTbo').worksheet('출고증')
                            
                            target_date = f"{out_date.month}. {out_date.day}"
                            all_vals = out_sh.get_all_values()
                            
                            target_row = -1
                            for i, r in enumerate(all_vals, 1):
                                if len(r) > 2 and str(r[2]).strip() == target_date:
                                    if len(r) <= 3 or str(r[3]).strip() == "":
                                        target_row = i
                                        break
                            
                            if target_row != -1:
                                out_data = [
                                    str(manager),             # D
                                    str(client_name),         # E
                                    str(row['품명']),          # F
                                    str(row['브랜드']),         # G
                                    str(row.get('BL넘버','-')), # H
                                    int(qty),                  # I
                                    str(row.get('창고명','')),  # J
                                    int(price),                # K
                                    "이체" if is_trans else "", # L
                                    str(changes)               # M
                                ]
                                out_sh.update(range_name=f"D{target_row}:M{target_row}", values=[out_data], value_input_option='USER_ENTERED')
                                st.success(f"✅ {target_date} 출고 등록 완료! ({target_row}행)")
                                time.sleep(1)
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"❌ '{target_date}' 날짜에 입력 가능한 빈 행이 없습니다.")
                        except Exception as e:
                            st.error(f"🚨 등록 중 오류 발생: {e}")
        else:
            st.warning("필터에 맞는 재고가 없습니다.")
else:
    st.info("데이터를 불러오는 중입니다...")
