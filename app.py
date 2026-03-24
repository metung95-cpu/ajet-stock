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

# --- 2. 데이터 로딩 (스크린샷 열 순서 기준) ---
@st.cache_data(ttl=60)
def load_inventory():
    try:
        gc = get_gspread_client()
        doc = gc.open('에이젯광주 운영독스')
        worksheet = doc.worksheet('raw_운영부재고')
        data = worksheet.get_all_values()
        
        if len(data) <= 1: return pd.DataFrame()

        # 데이터프레임 생성
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # [스크린샷 기준 열 매핑]
        # A(0): 품명 / B(1): 브랜드-등급-est / D(3): 재고수량 / E(4): 창고명 / F(5): 소비기한
        df['item_품명'] = df.iloc[:, 0].str.strip()
        df['item_브랜드'] = df.iloc[:, 1].str.strip()
        df['item_수량'] = df.iloc[:, 3].str.strip()
        df['item_창고'] = df.iloc[:, 4].str.strip()
        df['item_소비'] = df.iloc[:, 5].str.strip()
        
        # [본점 제외]
        df = df[df['item_창고'] != '본점']
        
        # [날짜 축소] 2027.02.16 -> 27.02.16
        def shorten_date(d):
            d = str(d).replace('-', '.').replace('/', '.')
            if len(d) >= 10 and d.startswith('20'): return d[2:]
            return d
        
        df['소비_short'] = df['item_소비'].apply(shorten_date)
        df['date_sort'] = pd.to_datetime(df['item_소비'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
        
        return df
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        return pd.DataFrame()

# --- 3. 출고 저장 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 4. 로그인 시스템 ---
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

df = load_inventory()

# --- 5. 실시간 재고 현황 (중복 필터링) ---
st.title("📦 에이젯 실시간 재고 현황")

if df.empty:
    st.warning("표시할 재고가 없습니다. 시트를 확인해 주세요.")
else:
    col1, col2 = st.columns(2)
    with col1: f_name = st.text_input("🔍 품명 검색", "")
    with col2: f_brand = st.text_input("🔍 브랜드 검색", "")

    v_df = df.copy()
    if f_name: v_df = v_df[v_df['item_품명'].str.contains(f_name, na=False, case=False)]
    if f_brand: v_df = v_df[v_df['item_브랜드'].str.contains(f_brand, na=False, case=False)]

    v_df = v_df.sort_values(by=['item_브랜드', 'date_sort'])
    
    # 표 출력
    display_df = v_df[['소비_short', 'item_품명', 'item_브랜드', 'item_수량', 'item_창고']]
    display_df.columns = ['소비기한', '품목', '브랜드-등급', '재고', '창고']
    st.dataframe(display_df, use_container_width=True, hide_index=True)

# --- 6. 출고 등록 (AZS 전용) ---
if st.session_state.user_role == "AZS" and not df.empty:
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    query = st.text_input("출고할 품목 검색", placeholder="예: 삼겹")
    
    selected_row = None
    if query:
        sel = df[df['item_품명'].str.contains(query, na=False, case=False)].sort_values(by=['item_브랜드', 'date_sort'])
        
        if not sel.empty:
            # [요청 포맷] 26.11.20 / 품목 / 브랜드 / 수량 / 창고
            sel['label'] = sel.apply(lambda x: f"{x['소비_short']} / {x['item_품목']} / {x['item_브랜드']} / {x['item_수량']} / {x['item_창고']}", axis=1)
            target = st.selectbox("재고 선택", sel['label'].tolist())
            selected_row = sel[sel['label'] == target].iloc[0]
        else: st.warning("검색 결과 없음")

    with st.form("outbound", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            o_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"])
            client = st.text_input("거래처")
        with c2:
            amt = st.number_input("수량", min_value=1, step=1)
            is_trans = st.checkbox("이체 여부 (L열)")
            memo = st.text_input("변경사항 (M열)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                row = [str(o_date), manager, client, selected_row['item_품목'], selected_row['item_브랜드'], amt, selected_row['item_소비'], "", "", "", "", "이체" if is_trans else "", memo]
                try:
                    save_outbound(row)
                    st.success("등록 완료!")
                    st.cache_data.clear()
                except Exception as e: st.error(f"저장 실패: {e}")
