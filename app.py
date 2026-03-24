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

# --- 2. 데이터 로딩 ---
@st.cache_data(ttl=300)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip()
    
    # 열 위치 기반 매핑 (A=품목, B=브랜드, E=창고, F=소비기한)
    df['temp_품목'] = df.iloc[:, 0]    # A열
    df['temp_브랜드'] = df.iloc[:, 1]  # B열
    df['temp_창고'] = df.iloc[:, 4]    # E열
    df['temp_소비기한'] = df.iloc[:, 5] # F열
    
    # 소비기한 정렬용 (F열 기준)
    df['date_sort'] = pd.to_datetime(df['temp_소비기한'], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    
    # [핵심] '본점' 정렬용 플래그 (본점이면 1, 아니면 0) -> 정렬 시 0이 위, 1이 아래로 감
    df['is_bonjum'] = (df['temp_창고'] == '본점').astype(int)
    
    return df

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
        else: st.error("정보 불일치")
    st.stop()

df = load_inventory()

# --- 4. 상단 실시간 재고 현황 (중복 필터링 + 본점 최하단) ---
st.title("📦 에이젯 실시간 재고 현황")

col_top1, col_top2 = st.columns(2)
with col_top1: 
    filter_name = st.text_input("🔍 품명 검색 (중복 필터링)", "")
with col_top2: 
    filter_brand = st.text_input("🔍 브랜드 검색 (중복 필터링)", "")

view_df = df.copy()

# 중복 필터링 (품명 AND 브랜드)
if filter_name:
    view_df = view_df[view_df['temp_품목'].str.contains(filter_name, na=False, case=False)]
if filter_brand:
    view_df = view_df[view_df['temp_브랜드'].str.contains(filter_brand, na=False, case=False)]

# [반영] 정렬: 본점 여부(0부터) -> 소비기한 순
view_df = view_df.sort_values(by=['is_bonjum', 'date_sort'])

# AZS 권한에서 본점 숨김 해제 여부는 상명님 의도에 따라 유지 또는 삭제 가능
# 현재는 "본점을 맨 아래로 보내달라"고 하셨으므로 모든 사용자가 본점 데이터를 보되 맨 아래에서 보도록 설정했습니다.
# 만약 AZS가 여전히 본점을 보면 안 된다면 아래 주석을 해제하세요.
# if st.session_state.user_role == "AZS": view_df = view_df[view_df['temp_창고'] != '본점']

st.dataframe(view_df.drop(columns=['date_sort', 'is_bonjum', 'temp_품목', 'temp_브랜드', 'temp_창고', 'temp_소비기한']), use_container_width=True, hide_index=True)

# --- 5. 출고 등록 (본점 최하단 + 상세 포맷) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    item_query = st.text_input("출고할 품목 검색", placeholder="품명을 입력하세요.")
    
    selected_row = None
    if item_query:
        # 검색 필터링
        selection = df[df['temp_품목'].str.contains(item_query, na=False, case=False)]
        
        # [반영] 정렬 우선순위: 본점 여부(0->1) -> 브랜드명 -> 소비기한 순
        selection = selection.sort_values(by=['is_bonjum', 'temp_브랜드', 'date_sort'])
        
        if not selection.empty:
            # [반영] 드롭다운 포맷: F열(소비기한) / A열(품목) / B열(브랜드) / E열(창고)
            selection['display_label'] = selection.apply(
                lambda x: f"{x['temp_소비기한']} / {x['temp_품목']} / {x['temp_브랜드']} / {x['temp_창고']}", axis=1
            )
            target_label = st.selectbox("재고 선택 (본점 물량은 목록 최하단에 위치)", selection['display_label'].tolist())
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
                    st.success(f"✅ [{selected_row['temp_품목']}] 등록 완료!")
                    st.cache_data.clear()
                except Exception as e: st.error(f"실패: {e}")
