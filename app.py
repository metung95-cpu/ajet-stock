import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# --- 구글 인증 ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    return gspread.authorize(credentials)

# --- 데이터 로딩 ---
@st.cache_data(ttl=300)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip()
    
    # 필수 컬럼 탐색 및 이름 통일
    e_col = next((c for c in ['소비기한', '유통기한'] if c in df.columns), df.columns[0])
    p_col = next((c for c in ['품명', '품목'] if c in df.columns), df.columns[1])
    b_col = next((c for c in ['브랜드', '메이커'] if c in df.columns), df.columns[2])
    q_col = next((c for c in ['재고수량', '재고량', '수량'] if c in df.columns), df.columns[3])
    w_col = next((c for c in ['창고명', '창고'] if c in df.columns), df.columns[4])

    # 날짜 정렬용 데이터
    df['date_sort'] = pd.to_datetime(df[e_col], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    
    # 사용하기 편하게 이름 변경
    df = df.rename(columns={p_col: '품명', b_col: '브랜드', e_col: '소비기한', q_col: '재고량', w_col: '창고'})
    return df

# --- 출고 저장 함수 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 로그인 시스템 ---
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
        else: st.error("로그인 정보 오류")
    st.stop()

# --- 데이터 불러오기 ---
df = load_inventory()

# --- 1. 상단 실시간 재고 현황 (검색 필터 활성화) ---
st.title("📦 에이젯 실시간 재고 현황")

col_s1, col_s2 = st.columns(2)
with col_s1: top_search_name = st.text_input("🔍 품명으로 표 필터링", "")
with col_s2: top_search_brand = st.text_input("🔍 브랜드로 표 필터링", "")

view_df = df.copy()
if top_search_name: view_df = view_df[view_df['품명'].str.contains(top_search_name, na=False, case=False)]
if top_search_brand: view_df = view_df[view_df['브랜드'].str.contains(top_search_brand, na=False, case=False)]

# AZS는 본점 데이터 제외
if st.session_state.user_role == "AZS":
    if '창고' in view_df.columns: view_df = view_df[view_df['창고'] != '본점']

st.dataframe(view_df.drop(columns=['date_sort']), use_container_width=True, hide_index=True)

# --- 2. 출고 등록 (AZS 전용) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록 (브랜드별 묶음 & 소비기한순)")
    
    item_query = st.text_input("출고할 품목 검색 (예: 삼겹)", placeholder="품명을 입력하면 아래 드롭다운에 목록이 나타납니다.")
    
    selected_row = None
    if item_query:
        # 검색 필터링 + 브랜드별로 묶고 그 안에서 소비기한 순으로 정렬
        selection = df[df['품명'].str.contains(item_query, na=False, case=False)].sort_values(['브랜드', 'date_sort'])
        
        if not selection.empty:
            # 요청하신 형식: 소비기한 브랜드 품명 / 재고수량 / 창고명
            selection['display_label'] = selection.apply(
                lambda x: f"{x['소비기한']} {x['브랜드']} {x['품명']} / {x['재고량']} / {x['창고']}", axis=1
            )
            target_label = st.selectbox("정확한 재고 선택", selection['display_label'].tolist())
            selected_row = selection[selection['display_label'] == target_label].iloc[0]
        else:
            st.warning("검색된 재고가 없습니다.")

    with st.form("outbound_form", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            o_date = st.date_input("출고일", datetime.now())
            manager = st.selectbox("담당자", ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"])
            client = st.text_input("거래처")
        with f_col2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (L열 기록)")
            comments = st.text_input("변경사항 (M열 기록)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # 시트 전송 데이터 (A~M열 순서)
                row_to_save = [
                    str(o_date), manager, client, 
                    selected_row['품명'], selected_row['브랜드'], 
                    amount, selected_row['소비기한'],
                    "", "", "", "", # H~K열
                    "이체" if is_transfer else "", # L열
                    comments # M열
                ]
                try:
                    save_outbound(row_to_save)
                    st.success(f"✅ [{selected_row['품명']}] 등록 완료!")
                    st.cache_data.clear() # 재고 즉시 갱신
                except Exception as e: st.error(f"저장 실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력을 확인해 주세요.")
