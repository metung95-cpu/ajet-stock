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

# --- 2. 데이터 로딩 (공간 절약형) ---
@st.cache_data(ttl=120) # 2분마다 자동 갱신
def load_inventory():
    try:
        gc = get_gspread_client()
        doc = gc.open('에이젯광주 운영독스')
        worksheet = doc.worksheet('raw_운영부재고')
        data = worksheet.get_all_values()
        
        # 데이터가 비어있는지 확인
        if len(data) <= 1:
            return pd.DataFrame()

        df = pd.DataFrame(data[1:], columns=data[0])
        df.columns = df.columns.str.strip() # 제목 공백 제거
        
        # 열 위치 기반 매핑 (A:0, B:1, D:3, E:4, F:5)
        # 만약 시트 위치가 바뀌면 숫자만 수정하면 됩니다.
        df['temp_품목'] = df.iloc[:, 0]    # A열
        df['temp_브랜드'] = df.iloc[:, 1]  # B열
        df['temp_재고량'] = df.iloc[:, 3]  # D열 (수량)
        df['temp_창고'] = df.iloc[:, 4]    # E열
        df['temp_소비기한'] = df.iloc[:, 5] # F열
        
        # [본점 제외]
        df = df[df['temp_창고'] != '본점']
        
        # [날짜 축소] 2027.01.01 -> 27.01.01
        def shorten_date(d):
            d = str(d).strip()
            return d[2:] if d.startswith('20') else d
        
        df['temp_소비기한_short'] = df['temp_소비기한'].apply(shorten_date)
        df['date_sort'] = pd.to_datetime(df['temp_소비기한'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
        
        return df
    except Exception as e:
        st.error(f"데이터를 불러오는 중 오류 발생: {e}")
        return pd.DataFrame()

# --- 3. 출고 저장 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 로그인 ---
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

# 데이터 불러오기
df = load_inventory()

# --- 4. 실시간 재고 현황 (표 복구 완료) ---
st.title("📦 에이젯 실시간 재고 현황")

if df.empty:
    st.warning("데이터가 없거나 불러오지 못했습니다. 시트 이름을 확인해주세요.")
else:
    col_t1, col_t2 = st.columns(2)
    with col_t1: f_name = st.text_input("🔍 품명 검색 (필터링)", "")
    with col_t2: f_brand = st.text_input("🔍 브랜드 검색 (필터링)", "")

    view_df = df.copy()
    # 중복 필터링 (품명 AND 브랜드)
    if f_name: view_df = view_df[view_df['temp_품목'].str.contains(f_name, na=False, case=False)]
    if f_brand: view_df = view_df[view_df['temp_브랜드'].str.contains(f_brand, na=False, case=False)]

    view_df = view_df.sort_values(by=['temp_브랜드', 'date_sort'])

    # 표 표시용 정리 (불필요한 열 제외)
    # 제목: 소비기한 | 브랜드 | 품명 | 재고 | 창고
    display_df = view_df[['temp_소비기한_short', 'temp_브랜드', 'temp_품목', 'temp_재고량', 'temp_창고']]
    display_df.columns = ['소비기한', '브랜드', '품명', '재고', '창고']

    st.dataframe(display_df, use_container_width=True, hide_index=True)

# --- 5. 출고 등록 (글자 수 최적화) ---
if st.session_state.user_role == "AZS" and not df.empty:
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    item_query = st.text_input("출고할 품목 검색", placeholder="예: 삼겹")
    
    selected_row = None
    if item_query:
        selection = df[df['temp_품목'].str.contains(item_query, na=False, case=False)]
        selection = selection.sort_values(by=['temp_브랜드', 'date_sort'])
        
        if not selection.empty:
            # [수정] 수량:15 -> 15 / 간격 좁혀서 창고명 확보
            selection['display_label'] = selection.apply(
                lambda x: f"{x['temp_소비기한_short']} {x['temp_품목']} {x['temp_브랜드']} {x['temp_재고량']} {x['temp_창고']}", axis=1
            )
            target_label = st.selectbox("재고 선택 (소비기한순)", selection['display_label'].tolist())
            selected_row = selection[selection['display_label'] == target_label].iloc[0]
        else:
            st.warning("검색된 재고가 없습니다.")

    with st.form("outbound_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            o_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"])
            client = st.text_input("거래처")
        with c2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (L열)")
            comments = st.text_input("변경사항 (M열)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                row = [
                    str(o_date), manager, client, 
                    selected_row['temp_품목'], selected_row['temp_브랜드'], 
                    amount, selected_row['temp_소비기한'],
                    "", "", "", "", 
                    "이체" if is_transfer else "", 
                    comments
                ]
                try:
                    save_outbound(row)
                    st.success(f"✅ [{selected_row['temp_품목']}] {amount}건 등록 완료!")
                    st.cache_data.clear() # 즉시 갱신
                except Exception as e: st.error(f"실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력이 필요합니다.")
