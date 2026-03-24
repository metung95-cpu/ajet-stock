import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime

st.set_page_config(page_title="에이젯 재고관리", layout="wide")

# --- 1. 구글 인증 설정 ---
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if "gcp_service_account" in st.secrets:
        creds_dict = st.secrets["gcp_service_account"]
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    else:
        credentials = Credentials.from_service_account_file('key.json', scopes=scope)
    return gspread.authorize(credentials)

# --- 2. 데이터 불러오기 (컬럼 자동 매칭) ---
@st.cache_data(ttl=300)
def load_inventory():
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 운영독스')
    worksheet = doc.worksheet('raw_운영부재고')
    data = worksheet.get_all_values()
    df = pd.DataFrame(data[1:], columns=data[0])
    df.columns = df.columns.str.strip()
    
    # [반영] 소비기한, 품명, 브랜드, 재고량, 창고명 컬럼 찾기
    e_col = next((c for c in ['소비기한', '유통기한'] if c in df.columns), df.columns[0])
    p_col = next((c for c in ['품명', '품목'] if c in df.columns), df.columns[1])
    b_col = next((c for c in ['브랜드', '메이커'] if c in df.columns), df.columns[2])
    q_col = next((c for c in ['재고수량', '재고량', '수량'] if c in df.columns), df.columns[3])
    w_col = next((c for c in ['창고명', '창고'] if c in df.columns), df.columns[4])

    df['date_sort'] = pd.to_datetime(df[e_col], errors='coerce').fillna(pd.Timestamp('2099-12-31'))
    df = df.rename(columns={p_col: '품명', b_col: '브랜드', e_col: '소비기한', q_col: '재고량', w_col: '창고'})
    return df

# --- 3. 출고 저장 함수 ---
def save_outbound(data_list):
    gc = get_gspread_client()
    doc = gc.open('에이젯광주 출고증')
    sheet = doc.get_worksheet(0)
    sheet.append_row(data_list)

# --- 로그인 시스템 (AZ: 5835 / AZS: 0983) ---
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
        else: st.error("로그인 정보가 틀렸습니다.")
    st.stop()

# 데이터 로드
df = load_inventory()

# --- [반영사항 1] 상단 실시간 재고 현황 필터링 활성화 ---
st.title("📦 에이젯 실시간 재고 현황")

col_top1, col_top2 = st.columns(2)
with col_top1: 
    main_filter_name = st.text_input("🔍 품명으로 전체 표 필터링", "")
with col_top2: 
    main_filter_brand = st.text_input("🔍 브랜드로 전체 표 필터링", "")

# 상단 표 필터 로직
main_view_df = df.copy()
if main_filter_name: 
    main_view_df = main_view_df[main_view_df['품명'].str.contains(main_filter_name, na=False, case=False)]
if main_filter_brand: 
    main_view_df = main_view_df[main_view_df['브랜드'].str.contains(main_filter_brand, na=False, case=False)]

if st.session_state.user_role == "AZS":
    if '창고' in main_view_df.columns: main_view_df = main_view_df[main_view_df['창고'] != '본점']

st.dataframe(main_view_df.drop(columns=['date_sort']), use_container_width=True, hide_index=True)

# --- 4. 출고 등록 (AZS 전용) ---
if st.session_state.user_role == "AZS":
    st.markdown("---")
    st.subheader("📝 출고 등록")
    
    # [반영사항 2] 출고 품목 검색 및 드롭다운 연동
    item_query = st.text_input("출고할 품목 검색 (예: 삼겹)", placeholder="여기에 품명을 입력하세요.")
    
    selected_row = None
    if item_query:
        # [반영사항 3] 브랜드별 묶음 + 소비기한순 정렬
        selection = df[df['품명'].str.contains(item_query, na=False, case=False)].sort_values(by=['브랜드', 'date_sort'])
        
        if not selection.empty:
            # [반영사항 4] 드롭다운 형식: 소비기한 브랜드 품명 / 재고수량 / 창고명
            selection['display_label'] = selection.apply(
                lambda x: f"{x['소비기한']} {x['브랜드']} {x['품명']} / {x['재고량']} / {x['창고']}", axis=1
            )
            # 드롭다운 표시
            target_label = st.selectbox("재고 선택 (브랜드별 그룹화 & 소비기한순)", selection['display_label'].tolist())
            selected_row = selection[selection['display_label'] == target_label].iloc[0]
        else:
            st.warning("검색된 재고가 없습니다.")

    # 출고 폼
    with st.form("outbound_form", clear_on_submit=True):
        f_col1, f_col2 = st.columns(2)
        with f_col1:
            o_date = st.date_input("출고일", datetime.now())
            # [반영사항 5] 담당자 목록 순서 고정
            manager_list = ["박정운", "강경현", "송광훈", "정기태", "김미남", "신상명", "백윤주"]
            manager = st.selectbox("담당자", manager_list)
            client = st.text_input("거래처")
        with f_col2:
            amount = st.number_input("수량", min_value=1, step=1)
            is_transfer = st.checkbox("이체 여부 (L열 기록)")
            comments = st.text_input("변경사항 (M열 기록)")

        if st.form_submit_button("등록하기"):
            if selected_row is not None and client:
                # [반영사항 6] L열(이체여부), M열(변경사항) 정확히 반영
                save_data = [
                    str(o_date), manager, client, 
                    selected_row['품명'], selected_row['브랜드'], 
                    amount, selected_row['소비기한'],
                    "", "", "", "", # H~K열 공백
                    "이체" if is_transfer else "", # L열
                    comments # M열
                ]
                try:
                    save_outbound(save_data)
                    st.success(f"✅ [{selected_row['품명']}] 등록 완료!")
                    st.cache_data.clear() # 재고 즉시 갱신
                except Exception as e: st.error(f"저장 실패: {e}")
            else:
                st.error("품목 선택과 거래처 입력이 필요합니다.")
